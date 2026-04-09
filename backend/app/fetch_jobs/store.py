from __future__ import annotations

from functools import lru_cache
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import AsyncSessionLocal, apply_rls_context
from app.models import (
    AppDataMetadataField,
    AppDataMetadataFieldFrequencyDistribution,
    AppDataMetadataFieldMostFrequent,
    AppDataMetadataFieldProfile,
    AppDataMetadataSnapshot,
    AppDataMetadataTable,
    AppDataMetadataTableProfile,
    LineageEdge,
    LineageNode,
    QlikApp,
    QlikAppScript,
    QlikAppUsage,
    QlikAudit,
    QlikDataConnection,
    QlikLicenseConsumption,
    QlikLicenseStatus,
    QlikReload,
    QlikSpace,
)
from fetchers.artifact_graph import build_snapshot_from_payloads

_UPSERT_BATCH_SIZE = 250


def _space_payload_columns(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "space_type": _str_or_none(item.get("type")),
        "owner_id": _str_or_none(item.get("ownerId")),
        "space_id_payload": _str_or_none(item.get("spaceId") or item.get("id")),
        "tenant_id": _str_or_none(item.get("tenantId")),
        "created_at_source": _str_or_none(item.get("createdAt")),
        "space_name": _str_or_none(item.get("spaceName") or item.get("spacename") or item.get("name")),
        "updated_at_source": _str_or_none(item.get("updatedAt")),
    }


def _list_or_none(value: Any) -> list[Any] | None:
    return list(value) if isinstance(value, list) else None


def _dict_or_none(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, dict) else None


def _json_or_none(value: Any) -> Any:
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        return value
    return None


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "on"}:
        return True
    if text in {"false", "0", "no", "n", "off"}:
        return False
    return None


def _datetime_or_none(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _merge_text_list(left: Any, right: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in [left, right]:
        if not isinstance(raw, list):
            continue
        for item in raw:
            text = _str_or_none(item)
            if text is None or text in seen:
                continue
            seen.add(text)
            out.append(text)
    return out


def _merge_json_like(left: Any, right: Any) -> Any:
    if isinstance(left, dict) and isinstance(right, dict):
        merged = dict(left)
        merged.update(right)
        return merged
    if left is not None:
        return left
    return right


def _dedupe_rows_by_key(
    rows: list[dict[str, Any]],
    key_columns: tuple[str, ...],
) -> list[dict[str, Any]]:
    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key_values: list[Any] = []
        skip = False
        for col in key_columns:
            value = row.get(col)
            if value is None:
                skip = True
                break
            key_values.append(value)
        if skip:
            continue
        deduped[tuple(key_values)] = dict(row)
    return list(deduped.values())


def _dedupe_app_data_metadata_field_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scalar_columns = (
        "name",
        "comment",
        "cardinal",
        "byte_size",
        "is_hidden",
        "is_locked",
        "is_system",
        "is_numeric",
        "is_semantic",
        "total_count",
        "distinct_only",
        "always_one_selected",
    )
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        field_hash = _str_or_none(row.get("field_hash"))
        if field_hash is None:
            continue
        candidate = dict(row)
        candidate["field_hash"] = field_hash
        candidate["tags"] = _merge_text_list(candidate.get("tags"), [])
        candidate["src_tables"] = _merge_text_list(candidate.get("src_tables"), [])
        existing = deduped.get(field_hash)
        if existing is None:
            deduped[field_hash] = candidate
            continue
        for col in scalar_columns:
            if existing.get(col) is None and candidate.get(col) is not None:
                existing[col] = candidate.get(col)
        existing["tags"] = _merge_text_list(existing.get("tags"), candidate.get("tags"))
        existing["src_tables"] = _merge_text_list(existing.get("src_tables"), candidate.get("src_tables"))
        existing["extra_json"] = _merge_json_like(existing.get("extra_json"), candidate.get("extra_json"))
    return list(deduped.values())


def _chunk_rows(rows: list[dict[str, Any]], *, batch_size: int = _UPSERT_BATCH_SIZE) -> list[list[dict[str, Any]]]:
    if batch_size <= 0:
        return [list(rows)] if rows else []
    return [rows[index:index + batch_size] for index in range(0, len(rows), batch_size)]


@lru_cache(maxsize=None)
def _model_attr_to_column_map(model: Any) -> dict[str, str]:
    mapper = sa_inspect(model)
    attr_to_column: dict[str, str] = {}
    for attr in mapper.column_attrs:
        if not attr.columns:
            continue
        attr_to_column[attr.key] = attr.columns[0].name
    return attr_to_column


def _to_db_column_value_map(model: Any, values: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(values, dict):
        return {}
    attr_to_column = _model_attr_to_column_map(model)
    mapped: dict[str, Any] = {}
    for key, value in values.items():
        mapped[attr_to_column.get(key, key)] = value
    return mapped


async def _execute_bulk_upsert(
    session: Any,
    *,
    model: Any,
    rows: list[dict[str, Any]],
    index_elements: tuple[str, ...],
    update_columns: tuple[str, ...],
    batch_size: int = _UPSERT_BATCH_SIZE,
) -> int:
    if not rows:
        return 0

    stored_count = 0
    for batch in _chunk_rows(rows, batch_size=batch_size):
        insert_stmt = pg_insert(model)
        stmt = (
            insert_stmt
            .values(batch)
            .on_conflict_do_update(
                index_elements=list(index_elements),
                set_={column: getattr(insert_stmt.excluded, column) for column in update_columns},
            )
        )
        await session.execute(stmt)
        stored_count += len(batch)
    return stored_count


def _app_payload_columns(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {
            "name_value": None,
            "app_id_payload": None,
            "item_id": None,
            "owner_id": None,
            "description": None,
            "resource_type": None,
            "resource_id": None,
            "thumbnail": None,
            "resource_attributes_id": None,
            "resource_attributes_name": None,
            "resource_attributes_description": None,
            "resource_attributes_created_date": None,
            "resource_attributes_modified_date": None,
            "resource_attributes_modified_by_user_name": None,
            "resource_attributes_publish_time": None,
            "resource_attributes_last_reload_time": None,
            "resource_attributes_trashed": None,
            "resource_custom_attributes_json": None,
            "status": None,
            "app_name": None,
            "space_id_payload": None,
            "file_name": None,
            "item_type": None,
            "edges_count": None,
            "nodes_count": None,
            "root_node_id": None,
            "lineage_fetched": None,
            "lineage_success": None,
            "source": None,
            "tenant": None,
            "fetched_at": None,
        }
    return {
        "name_value": _str_or_none(item.get("name")),
        "app_id_payload": _str_or_none(item.get("appId") or item.get("id")),
        "item_id": _str_or_none(item.get("id")),
        "owner_id": _str_or_none(item.get("ownerId")),
        "description": _str_or_none(item.get("description")),
        "resource_type": _str_or_none(item.get("resourceType")),
        "resource_id": _str_or_none(item.get("resourceId")),
        "thumbnail": _str_or_none(item.get("thumbnail")),
        "resource_attributes_id": _str_or_none(item.get("resourceAttributes_id")),
        "resource_attributes_name": _str_or_none(item.get("resourceAttributes_name")),
        "resource_attributes_description": _str_or_none(item.get("resourceAttributes_description")),
        "resource_attributes_created_date": _str_or_none(item.get("resourceAttributes_createdDate")),
        "resource_attributes_modified_date": _str_or_none(item.get("resourceAttributes_modifiedDate")),
        "resource_attributes_modified_by_user_name": _str_or_none(item.get("resourceAttributes_modifiedByUserName")),
        "resource_attributes_publish_time": _str_or_none(item.get("resourceAttributes_publishTime")),
        "resource_attributes_last_reload_time": _str_or_none(item.get("resourceAttributes_lastReloadTime")),
        "resource_attributes_trashed": _bool_or_none(item.get("resourceAttributes_trashed")),
        "resource_custom_attributes_json": _json_or_none(item.get("resourceCustomAttributes_json")),
        "status": _int_or_none(item.get("status")),
        "app_name": _str_or_none(item.get("appName") or item.get("name")),
        "space_id_payload": _str_or_none(item.get("spaceId")),
        "file_name": _str_or_none(item.get("fileName")),
        "item_type": _str_or_none(item.get("itemType")),
        "edges_count": _int_or_none(item.get("edgesCount")),
        "nodes_count": _int_or_none(item.get("nodesCount")),
        "root_node_id": _str_or_none(item.get("rootNodeId")),
        "lineage_fetched": _bool_or_none(item.get("lineageFetched")),
        "lineage_success": _bool_or_none(item.get("lineageSuccess")),
        "source": _str_or_none(item.get("source")),
        "tenant": _str_or_none(item.get("tenant")),
        "fetched_at": _datetime_or_none(item.get("fetched_at")) or datetime.now(timezone.utc),
    }


def _usage_payload_columns(item: dict[str, Any]) -> dict[str, Any]:
    usage = item.get("usage") if isinstance(item.get("usage"), dict) else {}
    generated_at_text = _str_or_none(item.get("generatedAt"))
    return {
        "app_id_payload": _str_or_none(item.get("appId")),
        "app_name": _str_or_none(item.get("appName")),
        "window_days": _int_or_none(item.get("windowDays")),
        "usage_reloads": _int_or_none(usage.get("reloads")),
        "usage_app_opens": _int_or_none(usage.get("appOpens")),
        "usage_sheet_views": _int_or_none(usage.get("sheetViews")),
        "usage_unique_users": _int_or_none(usage.get("uniqueUsers")),
        "usage_last_reload_at": _str_or_none(usage.get("lastReloadAt")),
        "usage_last_viewed_at": _str_or_none(usage.get("lastViewedAt")),
        "usage_classification": _str_or_none(usage.get("classification")),
        "connections": item.get("connections") if isinstance(item.get("connections"), list) else [],
        "generated_at_payload": generated_at_text,
        "artifact_file_name": _str_or_none(item.get("_artifactFileName")),
        "generated_at": _datetime_or_none(generated_at_text) or datetime.now(timezone.utc),
    }


def _data_connection_payload_columns(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {
            "id_payload": None,
            "q_id": None,
            "qri": None,
            "tags": None,
            "user_name": None,
            "links": None,
            "q_name": None,
            "q_type": None,
            "space_payload": None,
            "q_log_on": None,
            "tenant": None,
            "created_source": None,
            "updated_source": None,
            "version": None,
            "privileges": None,
            "datasource_id": None,
            "q_architecture": None,
            "q_credentials_id": None,
            "q_engine_object_id": None,
            "q_connect_statement": None,
            "q_separate_credentials": None,
        }
    return {
        "id_payload": _str_or_none(item.get("id")),
        "q_id": _str_or_none(item.get("qID")),
        "qri": _str_or_none(item.get("qri")),
        "tags": _list_or_none(item.get("tags")),
        "user_name": _str_or_none(item.get("user")),
        "links": _dict_or_none(item.get("links")),
        "q_name": _str_or_none(item.get("qName") or item.get("name")),
        "q_type": _str_or_none(item.get("qType") or item.get("type")),
        "space_payload": _str_or_none(item.get("space")),
        "q_log_on": _bool_or_none(item.get("qLogOn")),
        "tenant": _str_or_none(item.get("tenant")),
        "created_source": _str_or_none(item.get("created")),
        "updated_source": _str_or_none(item.get("updated")),
        "version": _str_or_none(item.get("version")),
        "privileges": _list_or_none(item.get("privileges")),
        "datasource_id": _str_or_none(item.get("datasourceID")),
        "q_architecture": _json_or_none(item.get("qArchitecture")),
        "q_credentials_id": _str_or_none(item.get("qCredentialsID")),
        "q_engine_object_id": _str_or_none(item.get("qEngineObjectID")),
        "q_connect_statement": _str_or_none(item.get("qConnectStatement")),
        "q_separate_credentials": _bool_or_none(item.get("qSeparateCredentials")),
    }


def _sanitize_data_connection_payload_for_storage(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    sanitized = dict(item)
    sanitized.pop("qConnectStatement", None)
    return sanitized


def _reload_payload_columns(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {
            "app_id": None,
            "log": None,
            "reload_type": None,
            "status": None,
            "user_id": None,
            "weight": None,
            "end_time": None,
            "partial": None,
            "tenant_id_payload": None,
            "error_code": None,
            "error_message": None,
            "start_time": None,
            "engine_time": None,
            "creation_time": None,
            "created_date": None,
            "created_date_ts": None,
            "modified_date": None,
            "modified_by_user_name": None,
            "owner_id": None,
            "title": None,
            "description": None,
            "log_available": None,
            "operational_id": None,
            "operational_next_execution": None,
            "operational_times_executed": None,
            "operational_state": None,
            "operational_hash": None,
            "links_self_href": None,
            "source": None,
            "tenant": None,
            "fetched_at": datetime.now(timezone.utc),
        }
    return {
        "app_id": _str_or_none(item.get("appId")),
        "log": _str_or_none(item.get("log")),
        "reload_type": _str_or_none(item.get("type")),
        "status": _str_or_none(item.get("status")),
        "user_id": _str_or_none(item.get("userId")),
        "weight": _int_or_none(item.get("weight")),
        "end_time": _str_or_none(item.get("endTime")),
        "partial": _bool_or_none(item.get("partial")),
        "tenant_id_payload": _str_or_none(item.get("tenantId")),
        "error_code": _str_or_none(item.get("errorCode")),
        "error_message": _str_or_none(item.get("errorMessage")),
        "start_time": _str_or_none(item.get("startTime")),
        "engine_time": _str_or_none(item.get("engineTime")),
        "creation_time": _str_or_none(item.get("creationTime")),
        "created_date": _str_or_none(item.get("createdDate")),
        "created_date_ts": _datetime_or_none(item.get("createdDate")),
        "modified_date": _str_or_none(item.get("modifiedDate")),
        "modified_by_user_name": _str_or_none(item.get("modifiedByUserName")),
        "owner_id": _str_or_none(item.get("ownerId")),
        "title": _str_or_none(item.get("title")),
        "description": _str_or_none(item.get("description")),
        "log_available": _bool_or_none(item.get("logAvailable")),
        "operational_id": _str_or_none(item.get("operational_id")),
        "operational_next_execution": _str_or_none(item.get("operational_nextExecution")),
        "operational_times_executed": _int_or_none(item.get("operational_timesExecuted")),
        "operational_state": _str_or_none(item.get("operational_state")),
        "operational_hash": _str_or_none(item.get("operational_hash")),
        "links_self_href": _str_or_none(item.get("links_self_href")),
        "source": _str_or_none(item.get("source")),
        "tenant": _str_or_none(item.get("tenant")),
        "fetched_at": datetime.now(timezone.utc),
    }


def _audit_payload_columns(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {
            "user_id": None,
            "event_id": None,
            "tenant_id_payload": None,
            "event_time": None,
            "event_type": None,
            "links_self_href": None,
            "extensions_actor_sub": None,
            "time": None,
            "time_ts": None,
            "sub_type": None,
            "space_id": None,
            "space_type": None,
            "category": None,
            "audit_type": None,
            "actor_id": None,
            "actor_type": None,
            "origin": None,
            "context": None,
            "ip_address": None,
            "user_agent": None,
            "properties_app_id": None,
            "data_message": None,
            "source": None,
            "tenant": None,
            "fetched_at": datetime.now(timezone.utc),
        }
    return {
        "user_id": _str_or_none(item.get("userId")),
        "event_id": _str_or_none(item.get("eventId")),
        "tenant_id_payload": _str_or_none(item.get("tenantId")),
        "event_time": _str_or_none(item.get("eventTime")),
        "event_type": _str_or_none(item.get("eventType")),
        "links_self_href": _str_or_none(item.get("links_self_href")),
        "extensions_actor_sub": _str_or_none(item.get("extensions_actor_sub")),
        "time": _str_or_none(item.get("time")),
        "time_ts": _datetime_or_none(item.get("time")) or _datetime_or_none(item.get("eventTime")),
        "sub_type": _str_or_none(item.get("subType")),
        "space_id": _str_or_none(item.get("spaceId")),
        "space_type": _str_or_none(item.get("spaceType")),
        "category": _str_or_none(item.get("category")),
        "audit_type": _str_or_none(item.get("type")),
        "actor_id": _str_or_none(item.get("actorId")),
        "actor_type": _str_or_none(item.get("actorType")),
        "origin": _str_or_none(item.get("origin")),
        "context": _str_or_none(item.get("context")),
        "ip_address": _str_or_none(item.get("ipAddress")),
        "user_agent": _str_or_none(item.get("userAgent")),
        "properties_app_id": _str_or_none(item.get("properties_appId")),
        "data_message": _str_or_none(item.get("data_message")),
        "source": _str_or_none(item.get("source")),
        "tenant": _str_or_none(item.get("tenant")),
        "fetched_at": datetime.now(timezone.utc),
    }


def _license_consumption_payload_columns(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {
            "app_id_payload": None,
            "user_id": None,
            "end_time": None,
            "duration": None,
            "session_id": None,
            "allotment_id": None,
            "minutes_used": None,
            "capacity_used": None,
            "license_usage": None,
            "name": None,
            "display_name": None,
            "license_type": None,
            "excess": None,
            "allocated": None,
            "available": None,
            "used": None,
            "quarantined": None,
            "total": None,
            "source": None,
            "tenant": None,
            "fetched_at": datetime.now(timezone.utc),
        }
    return {
        "app_id_payload": _str_or_none(item.get("appId")),
        "user_id": _str_or_none(item.get("userId")),
        "end_time": _str_or_none(item.get("endTime")),
        "duration": _str_or_none(item.get("duration")),
        "session_id": _str_or_none(item.get("sessionId")),
        "allotment_id": _str_or_none(item.get("allotmentId")),
        "minutes_used": _int_or_none(item.get("minutesUsed")),
        "capacity_used": _int_or_none(item.get("capacityUsed")),
        "license_usage": _str_or_none(item.get("licenseUsage")),
        "name": _str_or_none(item.get("name")),
        "display_name": _str_or_none(item.get("displayName")),
        "license_type": _str_or_none(item.get("type")),
        "excess": _int_or_none(item.get("excess")),
        "allocated": _int_or_none(item.get("allocated")),
        "available": _int_or_none(item.get("available")),
        "used": _int_or_none(item.get("used")),
        "quarantined": _int_or_none(item.get("quarantined")),
        "total": _int_or_none(item.get("total")),
        "source": _str_or_none(item.get("source")),
        "tenant": _str_or_none(item.get("tenant")),
        "fetched_at": datetime.now(timezone.utc),
    }


def _license_status_payload_columns(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {
            "license_type": None,
            "trial": None,
            "valid": None,
            "origin": None,
            "status": None,
            "product": None,
            "deactivated": None,
            "source": None,
            "tenant": None,
            "fetched_at": datetime.now(timezone.utc),
        }
    return {
        "license_type": _str_or_none(item.get("type")),
        "trial": _bool_or_none(item.get("trial")),
        "valid": _bool_or_none(item.get("valid")),
        "origin": _str_or_none(item.get("origin")),
        "status": _str_or_none(item.get("status")),
        "product": _str_or_none(item.get("product")),
        "deactivated": _bool_or_none(item.get("deactivated")),
        "source": _str_or_none(item.get("source")),
        "tenant": _str_or_none(item.get("tenant")),
        "fetched_at": datetime.now(timezone.utc),
    }


def _app_data_metadata_snapshot_columns(item: dict[str, Any]) -> dict[str, Any]:
    static_info = item.get("staticByteSizeInfo") if isinstance(item.get("staticByteSizeInfo"), dict) else {}
    reload_meta = item.get("reloadMeta") if isinstance(item.get("reloadMeta"), dict) else {}
    hardware = reload_meta.get("hardware") if isinstance(reload_meta.get("hardware"), dict) else {}
    return {
        "app_id": _str_or_none(item.get("appId")),
        "fetched_at": _datetime_or_none(item.get("fetchedAt")) or datetime.now(timezone.utc),
        "static_byte_size": _int_or_none(static_info.get("staticByteSize")),
        "has_section_access": _bool_or_none(static_info.get("hasSectionAccess")),
        "is_direct_query_mode": _bool_or_none(static_info.get("isDirectQueryMode")),
        "reload_meta_cpu_time_spent_ms": _int_or_none(reload_meta.get("cpuTimeSpentMs")),
        "reload_meta_peak_memory_bytes": _int_or_none(reload_meta.get("peakMemoryBytes")),
        "reload_meta_full_reload_peak_memory_bytes": _int_or_none(reload_meta.get("fullReloadPeakMemoryBytes")),
        "reload_meta_partial_reload_peak_memory_bytes": _int_or_none(reload_meta.get("partialReloadPeakMemoryBytes")),
        "reload_meta_hardware_total_memory": _int_or_none(hardware.get("totalMemory")),
        "reload_meta_hardware_logical_cores": _int_or_none(hardware.get("logicalCores")),
        "schema_hash": _str_or_none(item.get("schemaHash")),
        "extra_json": _dict_or_none(item.get("extra")) or {},
        "source": _str_or_none(item.get("source")),
        "tenant": _str_or_none(item.get("tenant")),
    }


def _app_data_metadata_field_columns(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "field_hash": _str_or_none(item.get("fieldHash")),
        "name": _str_or_none(item.get("name")),
        "comment": _str_or_none(item.get("comment")),
        "cardinal": _int_or_none(item.get("cardinal")),
        "byte_size": _int_or_none(item.get("byteSize")),
        "is_hidden": _bool_or_none(item.get("isHidden")),
        "is_locked": _bool_or_none(item.get("isLocked")),
        "is_system": _bool_or_none(item.get("isSystem")),
        "is_numeric": _bool_or_none(item.get("isNumeric")),
        "is_semantic": _bool_or_none(item.get("isSemantic")),
        "total_count": _int_or_none(item.get("totalCount")),
        "distinct_only": _bool_or_none(item.get("distinctOnly")),
        "always_one_selected": _bool_or_none(item.get("alwaysOneSelected")),
        "tags": _list_or_none(item.get("tags")),
        "src_tables": _list_or_none(item.get("srcTables")),
        "extra_json": _dict_or_none(item.get("extra")) or {},
    }


def _app_data_metadata_table_columns(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": _str_or_none(item.get("name")),
        "comment": _str_or_none(item.get("comment")),
        "is_loose": _bool_or_none(item.get("isLoose")),
        "byte_size": _int_or_none(item.get("byteSize")),
        "is_system": _bool_or_none(item.get("isSystem")),
        "is_semantic": _bool_or_none(item.get("isSemantic")),
        "no_of_rows": _int_or_none(item.get("noOfRows")),
        "no_of_fields": _int_or_none(item.get("noOfFields")),
        "no_of_key_fields": _int_or_none(item.get("noOfKeyFields")),
        "extra_json": _dict_or_none(item.get("extra")) or {},
    }


def _table_profile_columns(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile_index": _int_or_none(item.get("profileIndex")) or 0,
        "no_of_rows": _int_or_none(item.get("noOfRows")),
        "extra_json": _dict_or_none(item.get("extra")) or {},
    }


def _field_profile_columns(item: dict[str, Any]) -> dict[str, Any]:
    number_format = item.get("numberFormat") if isinstance(item.get("numberFormat"), dict) else {}
    return {
        "profile_index": _int_or_none(item.get("profileIndex")) or 0,
        "name": _str_or_none(item.get("name")),
        "max_value": item.get("max"),
        "min_value": item.get("min"),
        "std_value": item.get("std"),
        "sum_value": item.get("sum"),
        "sum2_value": item.get("sum2"),
        "median_value": item.get("median"),
        "average_value": item.get("avg"),
        "kurtosis": item.get("kurtosis"),
        "skewness": item.get("skewness"),
        "field_tags": _list_or_none(item.get("fieldTags")),
        "fractiles": _dict_or_none(item.get("fractiles")),
        "neg_values": _int_or_none(item.get("negValues")),
        "pos_values": _int_or_none(item.get("posValues")),
        "last_sorted": _str_or_none(item.get("lastSorted")),
        "null_values": _int_or_none(item.get("nullValues")),
        "text_values": _int_or_none(item.get("textValues")),
        "zero_values": _int_or_none(item.get("zeroValues")),
        "first_sorted": _str_or_none(item.get("firstSorted")),
        "avg_string_len": item.get("avgStringLen"),
        "data_evenness": item.get("dataEvenness"),
        "empty_strings": _int_or_none(item.get("emptyStrings")),
        "max_string_len": _int_or_none(item.get("maxStringLen")),
        "min_string_len": _int_or_none(item.get("minStringLen")),
        "sum_string_len": _int_or_none(item.get("sumStringLen")),
        "numeric_values": _int_or_none(item.get("numericValues")),
        "distinct_values": _int_or_none(item.get("distinctValues")),
        "distinct_text_values": _int_or_none(item.get("distinctTextValues")),
        "distinct_numeric_values": _int_or_none(item.get("distinctNumericValues")),
        "number_format_dec": _str_or_none(number_format.get("dec")),
        "number_format_fmt": _str_or_none(number_format.get("fmt")),
        "number_format_thou": _str_or_none(number_format.get("thou")),
        "number_format_ndec": _int_or_none(number_format.get("ndec")),
        "number_format_use_thou": _int_or_none(number_format.get("useThou")),
        "extra_json": _dict_or_none(item.get("extra")) or {},
    }


def _field_most_frequent_columns(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": _int_or_none(item.get("rank")) or 0,
        "symbol_text": _str_or_none(item.get("symbolText")),
        "symbol_number": item.get("symbolNumber"),
        "frequency": _int_or_none(item.get("frequency")),
        "extra_json": _dict_or_none(item.get("extra")) or {},
    }


def _field_frequency_distribution_columns(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "bin_index": _int_or_none(item.get("binIndex")) or 0,
        "bin_edge": item.get("binEdge"),
        "frequency": _int_or_none(item.get("frequency")),
        "number_of_bins": _int_or_none(item.get("numberOfBins")),
        "extra_json": _dict_or_none(item.get("extra")) or {},
    }


async def _run_db_store_step(
    project_id: int,
    *,
    actor_user_id: int,
    actor_role: str,
    apps_data: list[dict[str, Any]] | None = None,
    spaces_data: list[dict[str, Any]] | None = None,
    data_connections_data: list[dict[str, Any]] | None = None,
    reloads_data: list[dict[str, Any]] | None = None,
    audits_data: list[dict[str, Any]] | None = None,
    licenses_consumption_data: list[dict[str, Any]] | None = None,
    licenses_status_data: list[dict[str, Any]] | None = None,
    app_data_metadata_data: list[dict[str, Any]] | None = None,
    scripts_data: list[dict[str, Any]] | None = None,
    usage_payloads: list[dict[str, Any]] | None = None,
    app_edges_payloads: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    stored: dict[str, int] = {
        "apps": 0,
        "nodes": 0,
        "edges": 0,
        "spaces": 0,
        "dataConnections": 0,
        "reloads": 0,
        "audits": 0,
        "licenseConsumption": 0,
        "licenseStatus": 0,
        "appDataMetadataSnapshots": 0,
        "appDataMetadataFields": 0,
        "appDataMetadataTables": 0,
        "tableProfiles": 0,
        "fieldProfiles": 0,
        "fieldMostFrequent": 0,
        "fieldFrequencyDistribution": 0,
        "usage": 0,
        "scripts": 0,
        "skippedLineageFiles": 0,
    }

    snapshot, skipped_lineage_files = build_snapshot_from_payloads(app_edges_payloads or [])
    stored["skippedLineageFiles"] = len(skipped_lineage_files)

    apps_inventory_by_id: dict[str, dict[str, Any]] = {}
    app_lookup_for_nodes: dict[str, dict[str, Any]] = {}
    for app_data in apps_data if isinstance(apps_data, list) else []:
        if not isinstance(app_data, dict):
            continue
        app_id = app_data.get("appId")
        if not app_id:
            continue
        apps_inventory_by_id[str(app_id)] = dict(app_data)

    try:
        async with AsyncSessionLocal() as session:
            await apply_rls_context(session, actor_user_id, actor_role)

            all_app_ids = set(apps_inventory_by_id) | set(snapshot.apps)
            app_rows: list[dict[str, Any]] = []
            for app_id in sorted(all_app_ids):
                inventory_payload = dict(apps_inventory_by_id.get(app_id) or {})
                lineage_app = dict(snapshot.apps.get(app_id) or {})
                merged_data: dict[str, Any] = {}
                merged_data.update(inventory_payload)
                merged_data.update(lineage_app)
                merged_data.setdefault("appId", app_id)
                if "appName" not in merged_data and inventory_payload.get("name"):
                    merged_data["appName"] = inventory_payload.get("name")
                if "name" not in merged_data and merged_data.get("appName"):
                    merged_data["name"] = merged_data.get("appName")
                app_lookup_for_nodes[app_id] = {
                    "appName": merged_data.get("appName") or merged_data.get("name") or app_id,
                    "spaceId": merged_data.get("spaceId"),
                }
                app_cols = _app_payload_columns(merged_data)
                app_cols_db = _to_db_column_value_map(QlikApp, app_cols)
                app_rows.append(
                    {
                        "project_id": project_id,
                        "app_id": app_id,
                        "space_id": merged_data.get("spaceId"),
                        **app_cols_db,
                        "data": merged_data,
                    }
                )
            app_rows = _dedupe_rows_by_key(app_rows, ("project_id", "app_id"))
            stored["apps"] += await _execute_bulk_upsert(
                session,
                model=QlikApp,
                rows=app_rows,
                index_elements=("project_id", "app_id"),
                update_columns=tuple(sorted({*(_to_db_column_value_map(QlikApp, _app_payload_columns({})).keys()), "data", "space_id"})),
            )

            spaces_list = spaces_data if isinstance(spaces_data, list) else []
            if spaces_list:
                space_name_by_id: dict[str, str] = {}
                space_rows: list[dict[str, Any]] = []
                for item in spaces_list:
                    if not isinstance(item, dict):
                        continue
                    space_id = item.get("spaceId") or item.get("id")
                    if not space_id:
                        continue
                    space_name = item.get("spaceName") or item.get("spacename") or item.get("name")
                    if isinstance(space_name, str) and space_name.strip():
                        space_name_by_id[str(space_id)] = space_name.strip()
                    space_cols = _space_payload_columns(item)
                    space_cols_db = _to_db_column_value_map(QlikSpace, space_cols)
                    space_rows.append(
                        {
                            "project_id": project_id,
                            "space_id": str(space_id),
                            **space_cols_db,
                            "data": item,
                        }
                    )
                space_rows = _dedupe_rows_by_key(space_rows, ("project_id", "space_id"))
                stored["spaces"] += await _execute_bulk_upsert(
                    session,
                    model=QlikSpace,
                    rows=space_rows,
                    index_elements=("project_id", "space_id"),
                    update_columns=tuple(sorted({*(_to_db_column_value_map(QlikSpace, _space_payload_columns({})).keys()), "data"})),
                )
            else:
                space_name_by_id = {}

            data_connection_rows: list[dict[str, Any]] = []
            for item in data_connections_data if isinstance(data_connections_data, list) else []:
                if not isinstance(item, dict):
                    continue
                connection_id = item.get("id") or item.get("qID") or item.get("qEngineObjectID")
                if not connection_id:
                    continue
                connection_cols = _data_connection_payload_columns(item)
                item_sanitized = _sanitize_data_connection_payload_for_storage(item)
                connection_cols_db = _to_db_column_value_map(QlikDataConnection, connection_cols)
                data_connection_rows.append(
                    {
                        "project_id": project_id,
                        "connection_id": str(connection_id),
                        "space_id": connection_cols["space_payload"],
                        **connection_cols_db,
                        "data": item_sanitized,
                    }
                )
            data_connection_rows = _dedupe_rows_by_key(data_connection_rows, ("project_id", "connection_id"))
            stored["dataConnections"] += await _execute_bulk_upsert(
                session,
                model=QlikDataConnection,
                rows=data_connection_rows,
                index_elements=("project_id", "connection_id"),
                update_columns=tuple(sorted({*(_to_db_column_value_map(QlikDataConnection, _data_connection_payload_columns({})).keys()), "data", "space_id"})),
            )

            reload_rows: list[dict[str, Any]] = []
            for item in reloads_data if isinstance(reloads_data, list) else []:
                if not isinstance(item, dict):
                    continue
                reload_id = item.get("id")
                if not reload_id:
                    continue
                reload_cols = _reload_payload_columns(item)
                reload_cols_db = _to_db_column_value_map(QlikReload, reload_cols)
                reload_rows.append(
                    {
                        "project_id": project_id,
                        "reload_id": str(reload_id),
                        **reload_cols_db,
                        "data": item,
                    }
                )
            reload_rows = _dedupe_rows_by_key(reload_rows, ("project_id", "reload_id"))
            stored["reloads"] += await _execute_bulk_upsert(
                session,
                model=QlikReload,
                rows=reload_rows,
                index_elements=("project_id", "reload_id"),
                update_columns=tuple(sorted({*(_to_db_column_value_map(QlikReload, _reload_payload_columns({})).keys()), "data"})),
            )

            audit_rows: list[dict[str, Any]] = []
            for item in audits_data if isinstance(audits_data, list) else []:
                if not isinstance(item, dict):
                    continue
                audit_id = item.get("id")
                if not audit_id:
                    continue
                audit_cols = _audit_payload_columns(item)
                audit_cols_db = _to_db_column_value_map(QlikAudit, audit_cols)
                audit_rows.append(
                    {
                        "project_id": project_id,
                        "audit_id": str(audit_id),
                        **audit_cols_db,
                        "data": item,
                    }
                )
            audit_rows = _dedupe_rows_by_key(audit_rows, ("project_id", "audit_id"))
            stored["audits"] += await _execute_bulk_upsert(
                session,
                model=QlikAudit,
                rows=audit_rows,
                index_elements=("project_id", "audit_id"),
                update_columns=tuple(sorted({*(_to_db_column_value_map(QlikAudit, _audit_payload_columns({})).keys()), "data"})),
            )

            license_consumption_rows: list[dict[str, Any]] = []
            for item in licenses_consumption_data if isinstance(licenses_consumption_data, list) else []:
                if not isinstance(item, dict):
                    continue
                consumption_id = item.get("id")
                if not consumption_id:
                    continue
                consumption_cols = _license_consumption_payload_columns(item)
                consumption_cols_db = _to_db_column_value_map(QlikLicenseConsumption, consumption_cols)
                license_consumption_rows.append(
                    {
                        "project_id": project_id,
                        "consumption_id": str(consumption_id),
                        **consumption_cols_db,
                        "data": item,
                    }
                )
            license_consumption_rows = _dedupe_rows_by_key(
                license_consumption_rows,
                ("project_id", "consumption_id"),
            )
            stored["licenseConsumption"] += await _execute_bulk_upsert(
                session,
                model=QlikLicenseConsumption,
                rows=license_consumption_rows,
                index_elements=("project_id", "consumption_id"),
                update_columns=tuple(sorted({*(_to_db_column_value_map(QlikLicenseConsumption, _license_consumption_payload_columns({})).keys()), "data"})),
            )

            license_status_rows: list[dict[str, Any]] = []
            for item in licenses_status_data if isinstance(licenses_status_data, list) else []:
                if not isinstance(item, dict):
                    continue
                status_id = item.get("id")
                if not status_id:
                    continue
                status_cols = _license_status_payload_columns(item)
                status_cols_db = _to_db_column_value_map(QlikLicenseStatus, status_cols)
                license_status_rows.append(
                    {
                        "project_id": project_id,
                        "status_id": str(status_id),
                        **status_cols_db,
                        "data": item,
                    }
                )
            license_status_rows = _dedupe_rows_by_key(license_status_rows, ("project_id", "status_id"))
            stored["licenseStatus"] += await _execute_bulk_upsert(
                session,
                model=QlikLicenseStatus,
                rows=license_status_rows,
                index_elements=("project_id", "status_id"),
                update_columns=tuple(sorted({*(_to_db_column_value_map(QlikLicenseStatus, _license_status_payload_columns({})).keys()), "data"})),
            )

            for snapshot_payload in app_data_metadata_data if isinstance(app_data_metadata_data, list) else []:
                if not isinstance(snapshot_payload, dict):
                    continue
                snapshot_cols = _app_data_metadata_snapshot_columns(snapshot_payload)
                app_id = snapshot_cols.get("app_id")
                if not app_id:
                    continue
                snapshot_cols_db = _to_db_column_value_map(AppDataMetadataSnapshot, snapshot_cols)
                snapshot_insert_stmt = (
                    pg_insert(AppDataMetadataSnapshot)
                    .values(project_id=project_id, **snapshot_cols_db)
                    .returning(AppDataMetadataSnapshot.snapshot_id)
                )
                snapshot_result = await session.execute(snapshot_insert_stmt)
                snapshot_id = snapshot_result.scalar_one()
                stored["appDataMetadataSnapshots"] += 1

                field_rows: list[dict[str, Any]] = []
                for field_item in snapshot_payload.get("fields", []):
                    if not isinstance(field_item, dict):
                        continue
                    field_cols = _app_data_metadata_field_columns(field_item)
                    if not field_cols.get("field_hash"):
                        continue
                    field_cols_db = _to_db_column_value_map(AppDataMetadataField, field_cols)
                    field_rows.append({"project_id": project_id, "snapshot_id": snapshot_id, **field_cols_db})
                field_rows = _dedupe_app_data_metadata_field_rows(field_rows)
                if field_rows:
                    field_insert_stmt = (
                        pg_insert(AppDataMetadataField)
                        .values(field_rows)
                        .on_conflict_do_nothing(index_elements=["snapshot_id", "field_hash"])
                        .returning(AppDataMetadataField.row_id)
                    )
                    field_insert_result = await session.execute(field_insert_stmt)
                    stored["appDataMetadataFields"] += len(field_insert_result.all())

                table_rows: list[dict[str, Any]] = []
                for table_item in snapshot_payload.get("tables", []):
                    if not isinstance(table_item, dict):
                        continue
                    table_cols = _app_data_metadata_table_columns(table_item)
                    if not table_cols.get("name"):
                        continue
                    table_cols_db = _to_db_column_value_map(AppDataMetadataTable, table_cols)
                    table_rows.append({"project_id": project_id, "snapshot_id": snapshot_id, **table_cols_db})
                table_rows = _dedupe_rows_by_key(table_rows, ("snapshot_id", "name"))
                if table_rows:
                    table_insert_stmt = (
                        pg_insert(AppDataMetadataTable)
                        .values(table_rows)
                        .on_conflict_do_nothing(index_elements=["snapshot_id", "name"])
                        .returning(AppDataMetadataTable.row_id)
                    )
                    table_insert_result = await session.execute(table_insert_stmt)
                    stored["appDataMetadataTables"] += len(table_insert_result.all())

                if bool(snapshot_payload.get("profiling_enabled")):
                    table_profiles = snapshot_payload.get("table_profiles")
                    if isinstance(table_profiles, list):
                        table_profile_rows: list[dict[str, Any]] = []
                        table_profile_sources: dict[int, dict[str, Any]] = {}
                        for table_profile in table_profiles:
                            if not isinstance(table_profile, dict):
                                continue
                            table_profile_cols = _table_profile_columns(table_profile)
                            table_profile_index = int(table_profile_cols.get("profile_index") or 0)
                            table_profile_cols_db = _to_db_column_value_map(AppDataMetadataTableProfile, table_profile_cols)
                            table_profile_rows.append(
                                {
                                    "project_id": project_id,
                                    "snapshot_id": snapshot_id,
                                    **table_profile_cols_db,
                                }
                            )
                            table_profile_sources[table_profile_index] = table_profile

                        table_profile_id_by_index: dict[int, int] = {}
                        if table_profile_rows:
                            table_profile_rows = _dedupe_rows_by_key(table_profile_rows, ("snapshot_id", "profile_index"))
                            table_profile_insert_stmt = (
                                pg_insert(AppDataMetadataTableProfile)
                                .values(table_profile_rows)
                                .on_conflict_do_nothing(index_elements=["snapshot_id", "profile_index"])
                                .returning(
                                    AppDataMetadataTableProfile.table_profile_id,
                                    AppDataMetadataTableProfile.profile_index,
                                )
                            )
                            table_profile_result = await session.execute(table_profile_insert_stmt)
                            for row in table_profile_result.all():
                                table_profile_id_by_index[int(row.profile_index)] = int(row.table_profile_id)
                            stored["tableProfiles"] += len(table_profile_id_by_index)

                        field_profile_rows: list[dict[str, Any]] = []
                        field_profile_sources: dict[tuple[int, int], dict[str, Any]] = {}
                        for table_profile_index, source_profile in table_profile_sources.items():
                            table_profile_id = table_profile_id_by_index.get(table_profile_index)
                            if table_profile_id is None:
                                continue
                            field_profiles = source_profile.get("field_profiles")
                            if not isinstance(field_profiles, list):
                                continue
                            for field_profile in field_profiles:
                                if not isinstance(field_profile, dict):
                                    continue
                                field_profile_cols = _field_profile_columns(field_profile)
                                field_profile_index = int(field_profile_cols.get("profile_index") or 0)
                                field_profile_cols_db = _to_db_column_value_map(AppDataMetadataFieldProfile, field_profile_cols)
                                field_profile_rows.append(
                                    {
                                        "project_id": project_id,
                                        "snapshot_id": snapshot_id,
                                        "table_profile_id": table_profile_id,
                                        **field_profile_cols_db,
                                    }
                                )
                                field_profile_sources[(table_profile_id, field_profile_index)] = field_profile

                        field_profile_id_by_key: dict[tuple[int, int], int] = {}
                        if field_profile_rows:
                            field_profile_rows = _dedupe_rows_by_key(
                                field_profile_rows,
                                ("table_profile_id", "profile_index"),
                            )
                            field_profile_insert_stmt = (
                                pg_insert(AppDataMetadataFieldProfile)
                                .values(field_profile_rows)
                                .on_conflict_do_nothing(index_elements=["table_profile_id", "profile_index"])
                                .returning(
                                    AppDataMetadataFieldProfile.field_profile_id,
                                    AppDataMetadataFieldProfile.table_profile_id,
                                    AppDataMetadataFieldProfile.profile_index,
                                )
                            )
                            field_profile_result = await session.execute(field_profile_insert_stmt)
                            for row in field_profile_result.all():
                                key = (int(row.table_profile_id), int(row.profile_index))
                                field_profile_id_by_key[key] = int(row.field_profile_id)
                            stored["fieldProfiles"] += len(field_profile_id_by_key)

                        most_frequent_rows: list[dict[str, Any]] = []
                        frequency_distribution_rows: list[dict[str, Any]] = []
                        for key, field_profile_id in field_profile_id_by_key.items():
                            source_profile = field_profile_sources.get(key)
                            if not isinstance(source_profile, dict):
                                continue
                            for mf_item in source_profile.get("most_frequent", []):
                                if not isinstance(mf_item, dict):
                                    continue
                                mf_cols = _field_most_frequent_columns(mf_item)
                                mf_cols_db = _to_db_column_value_map(AppDataMetadataFieldMostFrequent, mf_cols)
                                most_frequent_rows.append(
                                    {
                                        "project_id": project_id,
                                        "snapshot_id": snapshot_id,
                                        "field_profile_id": field_profile_id,
                                        **mf_cols_db,
                                    }
                                )
                            for fd_item in source_profile.get("frequency_distribution", []):
                                if not isinstance(fd_item, dict):
                                    continue
                                fd_cols = _field_frequency_distribution_columns(fd_item)
                                fd_cols_db = _to_db_column_value_map(AppDataMetadataFieldFrequencyDistribution, fd_cols)
                                frequency_distribution_rows.append(
                                    {
                                        "project_id": project_id,
                                        "snapshot_id": snapshot_id,
                                        "field_profile_id": field_profile_id,
                                        **fd_cols_db,
                                    }
                                )

                        if most_frequent_rows:
                            most_frequent_rows = _dedupe_rows_by_key(
                                most_frequent_rows,
                                ("field_profile_id", "rank"),
                            )
                            most_frequent_insert_stmt = (
                                pg_insert(AppDataMetadataFieldMostFrequent)
                                .values(most_frequent_rows)
                                .on_conflict_do_nothing(index_elements=["field_profile_id", "rank"])
                                .returning(AppDataMetadataFieldMostFrequent.row_id)
                            )
                            most_frequent_insert_result = await session.execute(most_frequent_insert_stmt)
                            stored["fieldMostFrequent"] += len(most_frequent_insert_result.all())
                        if frequency_distribution_rows:
                            frequency_distribution_rows = _dedupe_rows_by_key(
                                frequency_distribution_rows,
                                ("field_profile_id", "bin_index"),
                            )
                            frequency_distribution_insert_stmt = (
                                pg_insert(AppDataMetadataFieldFrequencyDistribution)
                                .values(frequency_distribution_rows)
                                .on_conflict_do_nothing(index_elements=["field_profile_id", "bin_index"])
                                .returning(AppDataMetadataFieldFrequencyDistribution.row_id)
                            )
                            frequency_distribution_insert_result = await session.execute(
                                frequency_distribution_insert_stmt
                            )
                            stored["fieldFrequencyDistribution"] += len(frequency_distribution_insert_result.all())

            usage_rows: list[dict[str, Any]] = []
            for usage_payload in usage_payloads if isinstance(usage_payloads, list) else []:
                app_id = usage_payload.get("appId") if isinstance(usage_payload, dict) else None
                if not app_id:
                    continue
                usage_cols = _usage_payload_columns(usage_payload if isinstance(usage_payload, dict) else {})
                usage_cols_db = _to_db_column_value_map(QlikAppUsage, usage_cols)
                usage_rows.append(
                    {
                        "project_id": project_id,
                        "app_id": str(app_id),
                        **usage_cols_db,
                        "data": usage_payload,
                    }
                )
            usage_rows = _dedupe_rows_by_key(usage_rows, ("project_id", "app_id"))
            stored["usage"] += await _execute_bulk_upsert(
                session,
                model=QlikAppUsage,
                rows=usage_rows,
                index_elements=("project_id", "app_id"),
                update_columns=tuple(sorted({*(_to_db_column_value_map(QlikAppUsage, _usage_payload_columns({})).keys()), "data"})),
            )

            script_rows: list[dict[str, Any]] = []
            for item in scripts_data if isinstance(scripts_data, list) else []:
                if not isinstance(item, dict):
                    continue
                app_id = item.get("app_id")
                script = item.get("script")
                if not app_id or script is None:
                    continue
                script_rows.append(
                    {
                        "project_id": project_id,
                        "app_id": str(app_id),
                        "script": script,
                        "source": item.get("source") or "qlik_api",
                        "file_name": item.get("file_name"),
                        "data": item.get("data") or {},
                        "fetched_at": datetime.now(timezone.utc),
                    }
                )
            script_rows = _dedupe_rows_by_key(script_rows, ("project_id", "app_id"))
            stored["scripts"] += await _execute_bulk_upsert(
                session,
                model=QlikAppScript,
                rows=script_rows,
                index_elements=("project_id", "app_id"),
                update_columns=("script", "source", "file_name", "data", "fetched_at"),
            )

            node_rows: list[dict[str, Any]] = []
            for node_id, node in snapshot.nodes.items():
                node_payload = dict(node)
                node_meta = dict(node_payload.get("meta") or {})
                node_app_id = (
                    node_payload.get("group")
                    or node_meta.get("appId")
                    or node_meta.get("app_id")
                    or ((node_meta.get("id") if node_payload.get("type") == "app" else None))
                )
                if node_app_id:
                    app_info = app_lookup_for_nodes.get(str(node_app_id))
                    node_meta.setdefault("appId", str(node_app_id))
                    if app_info:
                        app_name_val = app_info.get("appName")
                        space_id_val = app_info.get("spaceId")
                        if app_name_val:
                            node_meta.setdefault("appName", str(app_name_val))
                        if space_id_val:
                            node_meta.setdefault("spaceId", str(space_id_val))
                            space_name_val = space_name_by_id.get(str(space_id_val))
                            if space_name_val:
                                node_meta.setdefault("spaceName", str(space_name_val))
                if node_meta:
                    node_payload["meta"] = node_meta
                node_rows.append(
                    {
                        "project_id": project_id,
                        "node_id": node_id,
                        "app_id": (node_meta or {}).get("id") if node_payload.get("type") == "app" else None,
                        "node_type": node_payload.get("type"),
                        "data": node_payload,
                    }
                )
            node_rows = _dedupe_rows_by_key(node_rows, ("project_id", "node_id"))
            stored["nodes"] += await _execute_bulk_upsert(
                session,
                model=LineageNode,
                rows=node_rows,
                index_elements=("project_id", "node_id"),
                update_columns=("app_id", "node_type", "data"),
            )

            edge_rows: list[dict[str, Any]] = []
            for edge_id, edge in snapshot.edges.items():
                edge_context = edge.get("context") or {}
                edge_rows.append(
                    {
                        "project_id": project_id,
                        "edge_id": edge_id,
                        "app_id": edge_context.get("appId"),
                        "source_node_id": edge.get("source"),
                        "target_node_id": edge.get("target"),
                        "data": dict(edge),
                    }
                )
            edge_rows = _dedupe_rows_by_key(edge_rows, ("project_id", "edge_id"))
            stored["edges"] += await _execute_bulk_upsert(
                session,
                model=LineageEdge,
                rows=edge_rows,
                index_elements=("project_id", "edge_id"),
                update_columns=("app_id", "source_node_id", "target_node_id", "data"),
            )

            await session.commit()
    except Exception as exc:
        exc_msg = str(exc)
        missing_table_markers = (
            "qlik_app_scripts",
            "qlik_reloads",
            "qlik_audits",
            "qlik_license_consumption",
            "qlik_license_status",
            "app_data_metadata_snapshot",
            "app_data_metadata_fields",
            "app_data_metadata_tables",
            "table_profiles",
            "field_profiles",
            "field_most_frequent",
            "field_frequency_distribution",
        )
        if "does not exist" in exc_msg and any(marker in exc_msg for marker in missing_table_markers):
            raise RuntimeError(
                "DB schema for new fetch modules is missing. Run 'alembic upgrade head' in backend."
            ) from exc
        raise RuntimeError(f"DB store step failed: {exc}") from exc
    return stored
