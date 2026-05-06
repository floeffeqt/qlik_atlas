import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.fetch_jobs.contracts import (  # type: ignore
    FETCH_STEP_ALL_ORDER,
    FetchJobRequest,
    _normalize_steps,
)
from app.fetch_jobs.runtime import _select_apps_for_app_edges  # type: ignore
from app.fetch_jobs.store import (  # type: ignore
    _app_data_metadata_snapshot_columns,
    _app_payload_columns,
    _audit_payload_columns,
    _chunk_rows,
    _dedupe_app_data_metadata_field_rows,
    _dedupe_rows_by_key,
    _license_consumption_payload_columns,
    _license_status_payload_columns,
    _reload_payload_columns,
    _sanitize_data_connection_payload_for_storage,
    _to_db_column_value_map,
)
from app.models import QlikApp  # type: ignore


def test_app_payload_columns_maps_flat_item_fields():
    payload = {
        "id": "item-1",
        "ownerId": "owner-1",
        "name": "Sales App",
        "description": "desc",
        "resourceType": "app",
        "resourceId": "app-1",
        "thumbnail": "thumb.png",
        "resourceAttributes_id": "app-1",
        "resourceAttributes_name": "Sales App Attr",
        "resourceAttributes_description": "desc-attr",
        "resourceAttributes_createdDate": "2024-02-01T10:00:00Z",
        "resourceAttributes_modifiedDate": "2024-02-02T11:00:00Z",
        "resourceAttributes_modifiedByUserName": "user@example.com",
        "resourceAttributes_publishTime": "2024-02-03T12:00:00Z",
        "resourceAttributes_lastReloadTime": "2024-02-04T13:00:00Z",
        "resourceAttributes_trashed": False,
        "resourceCustomAttributes_json": [{"id": "x", "value": "y"}],
        "source": "/api/v1/items",
        "tenant": "tenant.example.com",
    }
    cols = _app_payload_columns(payload)
    assert cols["item_id"] == "item-1"
    assert cols["owner_id"] == "owner-1"
    assert cols["resource_type"] == "app"
    assert cols["resource_id"] == "app-1"
    assert cols["resource_attributes_name"] == "Sales App Attr"
    assert cols["resource_attributes_trashed"] is False
    assert cols["source"] == "/api/v1/items"
    assert cols["tenant"] == "tenant.example.com"


def test_reload_payload_columns_maps_operational_fields():
    payload = {
        "id": "reload-1",
        "appId": "app-1",
        "log": "reload-log",
        "type": "full",
        "status": "SUCCEEDED",
        "userId": "user-1",
        "weight": 1,
        "endTime": "2024-02-01T10:05:00Z",
        "partial": False,
        "tenantId": "tenant-id",
        "errorCode": "0",
        "errorMessage": None,
        "startTime": "2024-02-01T10:00:00Z",
        "engineTime": "PT5M",
        "creationTime": "2024-02-01T09:59:59Z",
        "createdDate": "2024-02-01T10:00:00Z",
        "modifiedDate": "2024-02-02T11:00:00Z",
        "modifiedByUserName": "user@example.com",
        "ownerId": "owner-1",
        "title": "Nightly Reload",
        "description": "desc",
        "logAvailable": True,
        "operational_id": "op-1",
        "operational_nextExecution": "2024-02-05T12:00:00Z",
        "operational_timesExecuted": 4,
        "operational_state": "SUCCEEDED",
        "operational_hash": "h",
        "links_self_href": "/v1/reloads/reload-1",
        "source": "/api/v1/reloads",
        "tenant": "tenant.example.com",
    }
    cols = _reload_payload_columns(payload)
    assert cols["app_id"] == "app-1"
    assert cols["reload_type"] == "full"
    assert cols["status"] == "SUCCEEDED"
    assert cols["log_available"] is True
    assert cols["operational_state"] == "SUCCEEDED"
    assert cols["operational_times_executed"] == 4
    assert cols["source"] == "/api/v1/reloads"


def test_audit_payload_columns_maps_flat_fields():
    payload = {
        "id": "audit-1",
        "userId": "user-1",
        "eventId": "event-1",
        "tenantId": "tenant-id",
        "eventTime": "2024-02-01T10:00:00.000Z",
        "eventType": "com.qlik.v1.app.accessed",
        "links_self_href": "/api/v1/audits/audit-1",
        "extensions_actor_sub": "subject-1",
        "time": "2024-02-01T10:00:00.000Z",
        "subType": "app.accessed",
        "spaceId": "space-1",
        "spaceType": "shared",
        "category": "app",
        "type": "access",
        "actorId": "user-1",
        "actorType": "user",
        "origin": "qlik-ui",
        "context": "ctx",
        "ipAddress": "127.0.0.1",
        "userAgent": "UA",
        "properties_appId": "app-1",
        "data_message": "ok",
        "source": "/api/v1/audits",
        "tenant": "tenant.example.com",
    }
    cols = _audit_payload_columns(payload)
    assert cols["event_type"] == "com.qlik.v1.app.accessed"
    assert cols["event_id"] == "event-1"
    assert cols["audit_type"] == "access"
    assert cols["properties_app_id"] == "app-1"
    assert cols["actor_id"] == "user-1"
    assert cols["time_ts"] is not None


def test_license_consumption_payload_columns_maps_example_response_fields():
    payload = {
        "id": "consumption-1",
        "appId": "app-1",
        "userId": "user-1",
        "endTime": "2026-03-03T10:00:00Z",
        "duration": "PT30M",
        "sessionId": "sess-1",
        "allotmentId": "allot-1",
        "minutesUsed": 30,
        "capacityUsed": 42,
        "licenseUsage": "analyzer",
        "source": "/api/v1/licenses/consumption",
        "tenant": "tenant.example.com",
    }
    cols = _license_consumption_payload_columns(payload)
    assert cols["app_id_payload"] == "app-1"
    assert cols["user_id"] == "user-1"
    assert cols["session_id"] == "sess-1"
    assert cols["minutes_used"] == 30
    assert cols["capacity_used"] == 42
    assert cols["license_usage"] == "analyzer"


def test_license_status_payload_columns_maps_example_response_fields():
    payload = {
        "type": "professional",
        "trial": False,
        "valid": True,
        "origin": "subscription",
        "status": "active",
        "product": "Qlik Sense Enterprise SaaS",
        "deactivated": False,
        "source": "/api/v1/licenses/status",
        "tenant": "tenant.example.com",
    }
    cols = _license_status_payload_columns(payload)
    assert cols["license_type"] == "professional"
    assert cols["trial"] is False
    assert cols["valid"] is True
    assert cols["status"] == "active"
    assert cols["product"] == "Qlik Sense Enterprise SaaS"


def test_sanitize_data_connection_payload_for_storage_removes_q_connect_statement_only():
    payload = {
        "id": "conn-1",
        "qName": "SQL MAIN",
        "qConnectStatement": 'CUSTOM CONNECT TO "provider=QvOdbcConnectorPackage.exe;driver=mysql;host=db";',
    }
    sanitized = _sanitize_data_connection_payload_for_storage(payload)
    assert "qConnectStatement" not in sanitized
    assert sanitized["id"] == "conn-1"
    assert sanitized["qName"] == "SQL MAIN"


def test_sanitize_data_connection_payload_for_storage_keeps_original_input_unchanged():
    payload = {
        "id": "conn-1",
        "qConnectStatement": "sensitive",
    }
    sanitized = _sanitize_data_connection_payload_for_storage(payload)
    assert "qConnectStatement" in payload
    assert "qConnectStatement" not in sanitized


def test_app_data_metadata_snapshot_columns_maps_example_response_fields():
    payload = {
        "appId": "app-1",
        "fetchedAt": "2026-03-03T10:00:00Z",
        "staticByteSizeInfo": {
            "staticByteSize": 1234,
            "hasSectionAccess": True,
            "isDirectQueryMode": False,
        },
        "reloadMeta": {
            "cpuTimeSpentMs": 500,
            "peakMemoryBytes": 2000,
            "fullReloadPeakMemoryBytes": 2100,
            "partialReloadPeakMemoryBytes": 1300,
            "hardware": {
                "totalMemory": 64000000000,
                "logicalCores": 8,
            },
        },
        "schemaHash": "abc123",
        "source": "/api/v1/apps/app-1/data/metadata",
        "tenant": "tenant.example.com",
    }
    cols = _app_data_metadata_snapshot_columns(payload)
    assert cols["app_id"] == "app-1"
    assert cols["static_byte_size"] == 1234
    assert cols["has_section_access"] is True
    assert cols["reload_meta_peak_memory_bytes"] == 2000
    assert cols["reload_meta_hardware_logical_cores"] == 8
    assert cols["source"] == "/api/v1/apps/app-1/data/metadata"


def test_dedupe_app_data_metadata_field_rows_merges_duplicate_field_hash():
    rows = [
        {
            "project_id": 1,
            "snapshot_id": 10,
            "field_hash": "h1",
            "name": "FieldA",
            "comment": None,
            "tags": ["$numeric"],
            "src_tables": ["T1"],
            "extra_json": {"a": 1},
        },
        {
            "project_id": 1,
            "snapshot_id": 10,
            "field_hash": "h1",
            "name": None,
            "comment": "from duplicate",
            "tags": ["$date"],
            "src_tables": ["T2"],
            "extra_json": {"b": 2},
        },
    ]
    deduped = _dedupe_app_data_metadata_field_rows(rows)
    assert len(deduped) == 1
    merged = deduped[0]
    assert merged["field_hash"] == "h1"
    assert merged["name"] == "FieldA"
    assert merged["comment"] == "from duplicate"
    assert merged["tags"] == ["$numeric", "$date"]
    assert merged["src_tables"] == ["T1", "T2"]
    assert merged["extra_json"] == {"a": 1, "b": 2}


def test_dedupe_rows_by_key_keeps_latest_entry_per_unique_key():
    rows = [
        {"snapshot_id": 1, "name": "A", "value": 1},
        {"snapshot_id": 1, "name": "A", "value": 2},
        {"snapshot_id": 1, "name": "B", "value": 3},
    ]
    deduped = _dedupe_rows_by_key(rows, ("snapshot_id", "name"))
    deduped_by_name = {r["name"]: r for r in deduped}
    assert len(deduped) == 2
    assert deduped_by_name["A"]["value"] == 2
    assert deduped_by_name["B"]["value"] == 3


def test_chunk_rows_splits_batches_predictably():
    rows = [{"id": idx} for idx in range(5)]
    batches = _chunk_rows(rows, batch_size=2)
    assert [len(batch) for batch in batches] == [2, 2, 1]
    assert batches[0][0]["id"] == 0
    assert batches[-1][0]["id"] == 4


def test_to_db_column_value_map_uses_model_column_names():
    mapped = _to_db_column_value_map(
        QlikApp,
        {
            "name_value": "Sales App",
            "app_name": "Sales App",
            "space_id_payload": "space-1",
        },
    )
    assert mapped["name"] == "Sales App"
    assert mapped["appName"] == "Sales App"
    assert mapped["spaceId"] == "space-1"


def test_normalize_steps_defaults_to_all_steps():
    assert _normalize_steps(None) == list(FETCH_STEP_ALL_ORDER)


def test_normalize_steps_adds_dependencies_for_app_edges():
    normalized = _normalize_steps(["app-edges"])
    assert normalized == ["apps", "lineage", "app-edges"]


def test_normalize_steps_adds_dependency_for_app_data_metadata():
    normalized = _normalize_steps(["app-data-metadata"])
    assert normalized == ["apps", "app-data-metadata"]


def test_select_apps_for_app_edges_prefers_runtime_lineage_success():
    apps = [
        {"appId": "app-1", "name": "A", "lineageSuccess": True},
        {"appId": "app-2", "name": "B", "lineageSuccess": False},
    ]
    selected, source = _select_apps_for_app_edges(apps)
    assert source == "lineage_step_runtime"
    assert [a["appId"] for a in selected] == ["app-1"]


def test_select_apps_for_app_edges_falls_back_to_all_apps():
    apps = [
        {"appId": "app-1", "name": "A"},
        {"appId": "app-2", "name": "B"},
    ]
    selected, source = _select_apps_for_app_edges(apps, lineage_payloads=[])
    assert source == "fallback_all_apps"
    assert [a["appId"] for a in selected] == ["app-1", "app-2"]


def test_fetch_job_request_defaults_lineage_level_to_resource():
    req = FetchJobRequest(project_id=1)
    assert req.lineageLevel == "resource"


def test_fetch_job_request_accepts_field_level():
    req = FetchJobRequest(project_id=1, lineageLevel="field")
    assert req.lineageLevel == "field"
