from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import and_, func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AppDataMetadataField,
    AppDataMetadataSnapshot,
    AppDataMetadataTable,
    LineageEdge,
    LineageNode,
    QlikApp,
    QlikAppUsage,
    QlikSpace,
)


DEFAULT_DAYS = 30
DEFAULT_FIELDS_LIMIT = 200
MAX_FIELDS_LIMIT = 1000
DEFAULT_GOVERNANCE_LIMIT = 30
AREA_UNASSIGNED_KEY = "unassigned"
DATA_MODEL_PACK_METRICS = ("static_byte_size_latest", "complexity_latest")
DataModelPackMetric = Literal["static_byte_size_latest", "complexity_latest"]


@dataclass(frozen=True)
class _AreaRef:
    area_key: str
    area_name: str
    space_id: str | None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _window_start(days: int) -> datetime:
    return _utc_now() - timedelta(days=max(1, int(days)))


def _safe_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_min_max(values: list[float]) -> list[float]:
    if not values:
        return []
    min_v = min(values)
    max_v = max(values)
    if max_v <= min_v:
        return [50.0 for _ in values]
    span = max_v - min_v
    return [((v - min_v) / span) * 100.0 for v in values]


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def parse_area_key(area_key: str) -> tuple[str, str | None]:
    raw = str(area_key or "").strip()
    if not raw:
        raise ValueError("area_key must not be empty")
    if raw.lower() == AREA_UNASSIGNED_KEY:
        return (AREA_UNASSIGNED_KEY, None)
    if raw.lower().startswith("space:"):
        space_id = raw.split(":", 1)[1].strip()
        if not space_id:
            raise ValueError("invalid space area key")
        return (f"space:{space_id}", space_id)
    raise ValueError("unsupported area key")


def _area_from_snapshot_row(row: dict[str, Any]) -> _AreaRef:
    space_id = _safe_text(row.get("qs_space_id")) or _safe_text(row.get("qa_space_id"))
    if space_id:
        space_name = _safe_text(row.get("qs_space_name")) or space_id
        return _AreaRef(area_key=f"space:{space_id}", area_name=space_name, space_id=space_id)
    return _AreaRef(area_key=AREA_UNASSIGNED_KEY, area_name="Unassigned", space_id=None)


def _app_name_from_snapshot_row(row: dict[str, Any]) -> str:
    return (
        _safe_text(row.get("qa_app_name"))
        or _safe_text(row.get("qa_name_value"))
        or _safe_text(row.get("app_id"))
        or "unknown-app"
    )


async def _load_latest_snapshot_rows(
    session: AsyncSession,
    *,
    project_id: int | None,
) -> list[dict[str, Any]]:
    ranked_stmt = select(
        AppDataMetadataSnapshot.snapshot_id.label("snapshot_id"),
        AppDataMetadataSnapshot.project_id.label("project_id"),
        AppDataMetadataSnapshot.app_id.label("app_id"),
        AppDataMetadataSnapshot.fetched_at.label("fetched_at"),
        AppDataMetadataSnapshot.static_byte_size.label("static_byte_size"),
        AppDataMetadataSnapshot.has_section_access.label("has_section_access"),
        AppDataMetadataSnapshot.is_direct_query_mode.label("is_direct_query_mode"),
        AppDataMetadataSnapshot.reload_meta_cpu_time_spent_ms.label("reload_meta_cpu_time_spent_ms"),
        AppDataMetadataSnapshot.reload_meta_peak_memory_bytes.label("reload_meta_peak_memory_bytes"),
        AppDataMetadataSnapshot.schema_hash.label("schema_hash"),
        sa_func.row_number()
        .over(
            partition_by=(AppDataMetadataSnapshot.project_id, AppDataMetadataSnapshot.app_id),
            order_by=(
                AppDataMetadataSnapshot.fetched_at.desc(),
                AppDataMetadataSnapshot.snapshot_id.desc(),
            ),
        )
        .label("rn"),
    )
    if project_id is not None:
        ranked_stmt = ranked_stmt.where(AppDataMetadataSnapshot.project_id == project_id)
    ranked = ranked_stmt.subquery("ranked_snapshots")

    latest = (
        select(
            ranked.c.snapshot_id,
            ranked.c.project_id,
            ranked.c.app_id,
            ranked.c.fetched_at,
            ranked.c.static_byte_size,
            ranked.c.has_section_access,
            ranked.c.is_direct_query_mode,
            ranked.c.reload_meta_cpu_time_spent_ms,
            ranked.c.reload_meta_peak_memory_bytes,
            ranked.c.schema_hash,
            QlikApp.app_name.label("qa_app_name"),
            QlikApp.name_value.label("qa_name_value"),
            QlikApp.space_id.label("qa_space_id"),
            QlikSpace.space_id.label("qs_space_id"),
            QlikSpace.space_name.label("qs_space_name"),
        )
        .select_from(ranked)
        .outerjoin(
            QlikApp,
            and_(
                QlikApp.project_id == ranked.c.project_id,
                QlikApp.app_id == ranked.c.app_id,
            ),
        )
        .outerjoin(
            QlikSpace,
            and_(
                QlikSpace.project_id == QlikApp.project_id,
                QlikSpace.space_id == QlikApp.space_id,
            ),
        )
        .where(ranked.c.rn == 1)
    )

    rows = (await session.execute(latest)).mappings().all()
    return [dict(item) for item in rows]


async def _load_table_stats_by_snapshot(
    session: AsyncSession,
    *,
    snapshot_ids: list[int],
) -> dict[int, dict[str, int]]:
    if not snapshot_ids:
        return {}
    stmt = (
        select(
            AppDataMetadataTable.snapshot_id,
            sa_func.count().label("tables_count"),
            sa_func.coalesce(sa_func.sum(AppDataMetadataTable.no_of_fields), 0).label("nodes_estimate"),
        )
        .where(AppDataMetadataTable.snapshot_id.in_(snapshot_ids))
        .group_by(AppDataMetadataTable.snapshot_id)
    )
    rows = (await session.execute(stmt)).all()
    out: dict[int, dict[str, int]] = {}
    for snapshot_id, tables_count, nodes_estimate in rows:
        out[int(snapshot_id)] = {
            "tables_count": _safe_int(tables_count),
            "nodes_estimate": _safe_int(nodes_estimate),
        }
    return out


async def _load_field_count_by_snapshot(
    session: AsyncSession,
    *,
    snapshot_ids: list[int],
) -> dict[int, int]:
    if not snapshot_ids:
        return {}
    stmt = (
        select(
            AppDataMetadataField.snapshot_id,
            sa_func.count().label("fields_count"),
        )
        .where(AppDataMetadataField.snapshot_id.in_(snapshot_ids))
        .group_by(AppDataMetadataField.snapshot_id)
    )
    rows = (await session.execute(stmt)).all()
    return {int(snapshot_id): _safe_int(fields_count) for snapshot_id, fields_count in rows}


async def _load_schema_distinct_hash_counts(
    session: AsyncSession,
    *,
    days: int,
    project_id: int | None,
) -> dict[tuple[int, str], int]:
    stmt = (
        select(
            AppDataMetadataSnapshot.project_id,
            AppDataMetadataSnapshot.app_id,
            sa_func.count(sa_func.distinct(AppDataMetadataSnapshot.schema_hash)).label("hash_count"),
        )
        .where(AppDataMetadataSnapshot.fetched_at >= _window_start(days))
        .group_by(AppDataMetadataSnapshot.project_id, AppDataMetadataSnapshot.app_id)
    )
    if project_id is not None:
        stmt = stmt.where(AppDataMetadataSnapshot.project_id == project_id)
    rows = (await session.execute(stmt)).all()
    out: dict[tuple[int, str], int] = {}
    for p_id, app_id, hash_count in rows:
        out[(int(p_id), str(app_id))] = _safe_int(hash_count)
    return out


def _empty_area_totals() -> dict[str, int]:
    return {
        "areas_count": 0,
        "apps_count": 0,
        "nodes_estimate": 0,
        "total_static_byte_size_latest": 0,
        "peak_memory_latest_max": 0,
        "direct_query_apps_count": 0,
        "section_access_missing_count": 0,
        "schema_drift_apps_count": 0,
    }


def _metric_value_for_pack(*, metric: DataModelPackMetric, static_byte_size: int, complexity: int) -> float:
    if metric == "complexity_latest":
        return float(complexity)
    return float(static_byte_size)


async def load_analytics_areas(
    session: AsyncSession,
    *,
    project_id: int | None = None,
    days: int = DEFAULT_DAYS,
) -> dict[str, Any]:
    latest_rows = await _load_latest_snapshot_rows(session, project_id=project_id)
    if not latest_rows:
        return {"areas": [], "totals": _empty_area_totals()}

    snapshot_ids = [_safe_int(row.get("snapshot_id")) for row in latest_rows]
    table_stats_by_snapshot = await _load_table_stats_by_snapshot(session, snapshot_ids=snapshot_ids)
    drift_hash_counts = await _load_schema_distinct_hash_counts(session, days=days, project_id=project_id)

    areas: dict[str, dict[str, Any]] = {}
    for row in latest_rows:
        snapshot_id = _safe_int(row.get("snapshot_id"))
        project_id_val = _safe_int(row.get("project_id"))
        app_id_val = str(row.get("app_id") or "")
        area = _area_from_snapshot_row(row)
        stats = table_stats_by_snapshot.get(snapshot_id, {})
        bucket = areas.setdefault(
            area.area_key,
            {
                "area_key": area.area_key,
                "area_name": area.area_name,
                "apps_count": 0,
                "nodes_estimate": 0,
                "total_static_byte_size_latest": 0,
                "peak_memory_latest_max": 0,
                "direct_query_apps_count": 0,
                "section_access_missing_count": 0,
                "schema_drift_apps_count": 0,
            },
        )
        bucket["apps_count"] += 1
        bucket["nodes_estimate"] += _safe_int(stats.get("nodes_estimate"))
        bucket["total_static_byte_size_latest"] += _safe_int(row.get("static_byte_size"))
        bucket["peak_memory_latest_max"] = max(
            _safe_int(bucket["peak_memory_latest_max"]),
            _safe_int(row.get("reload_meta_peak_memory_bytes")),
        )
        if row.get("is_direct_query_mode") is True:
            bucket["direct_query_apps_count"] += 1
        if row.get("has_section_access") is False:
            bucket["section_access_missing_count"] += 1
        if drift_hash_counts.get((project_id_val, app_id_val), 0) > 1:
            bucket["schema_drift_apps_count"] += 1

    area_list = sorted(
        areas.values(),
        key=lambda item: (-_safe_int(item.get("apps_count")), str(item.get("area_name") or "").lower()),
    )
    totals = _empty_area_totals()
    totals["areas_count"] = len(area_list)
    totals["apps_count"] = sum(_safe_int(item["apps_count"]) for item in area_list)
    totals["nodes_estimate"] = sum(_safe_int(item["nodes_estimate"]) for item in area_list)
    totals["total_static_byte_size_latest"] = sum(
        _safe_int(item["total_static_byte_size_latest"]) for item in area_list
    )
    totals["peak_memory_latest_max"] = max(
        [_safe_int(item["peak_memory_latest_max"]) for item in area_list] + [0]
    )
    totals["direct_query_apps_count"] = sum(_safe_int(item["direct_query_apps_count"]) for item in area_list)
    totals["section_access_missing_count"] = sum(
        _safe_int(item["section_access_missing_count"]) for item in area_list
    )
    totals["schema_drift_apps_count"] = sum(_safe_int(item["schema_drift_apps_count"]) for item in area_list)
    return {"areas": area_list, "totals": totals}


async def load_analytics_area_apps(
    session: AsyncSession,
    *,
    area_key: str,
    project_id: int | None = None,
    days: int = DEFAULT_DAYS,
) -> dict[str, Any]:
    normalized_area_key, expected_space_id = parse_area_key(area_key)
    latest_rows = await _load_latest_snapshot_rows(session, project_id=project_id)
    if not latest_rows:
        return {
            "area_key": normalized_area_key,
            "area_name": "Unassigned" if expected_space_id is None else expected_space_id,
            "apps": [],
        }

    snapshot_ids = [_safe_int(row.get("snapshot_id")) for row in latest_rows]
    field_count_by_snapshot = await _load_field_count_by_snapshot(session, snapshot_ids=snapshot_ids)
    table_stats_by_snapshot = await _load_table_stats_by_snapshot(session, snapshot_ids=snapshot_ids)
    drift_hash_counts = await _load_schema_distinct_hash_counts(session, days=days, project_id=project_id)

    out_apps: list[dict[str, Any]] = []
    area_name_fallback = "Unassigned" if expected_space_id is None else expected_space_id
    for row in latest_rows:
        area = _area_from_snapshot_row(row)
        if area.area_key != normalized_area_key:
            continue
        area_name_fallback = area.area_name
        snapshot_id = _safe_int(row.get("snapshot_id"))
        p_id = _safe_int(row.get("project_id"))
        app_id_val = str(row.get("app_id") or "")
        hash_count = drift_hash_counts.get((p_id, app_id_val), 0)
        stats = table_stats_by_snapshot.get(snapshot_id, {})
        out_apps.append(
            {
                "project_id": p_id,
                "app_id": app_id_val,
                "app_name": _app_name_from_snapshot_row(row),
                "space_id": area.space_id,
                "space_name": area.area_name,
                "latest_fetched_at": row.get("fetched_at"),
                "static_byte_size_latest": row.get("static_byte_size"),
                "reload_meta_peak_memory_bytes_latest": row.get("reload_meta_peak_memory_bytes"),
                "reload_meta_cpu_time_spent_ms_latest": row.get("reload_meta_cpu_time_spent_ms"),
                "is_direct_query_mode_latest": row.get("is_direct_query_mode"),
                "has_section_access_latest": row.get("has_section_access"),
                "fields_count_latest": field_count_by_snapshot.get(snapshot_id, 0),
                "tables_count_latest": _safe_int(stats.get("tables_count")),
                "schema_hash_latest": row.get("schema_hash"),
                "schema_drift_count_in_window": max(hash_count - 1, 0),
            }
        )

    out_apps.sort(
        key=lambda item: (
            -_safe_int(item.get("static_byte_size_latest")),
            str(item.get("app_name") or "").lower(),
        )
    )
    return {
        "area_key": normalized_area_key,
        "area_name": area_name_fallback,
        "apps": out_apps,
    }


async def _ensure_app_exists(session: AsyncSession, *, project_id: int, app_id: str) -> None:
    exists_stmt = (
        select(sa_func.count())
        .select_from(QlikApp)
        .where(QlikApp.project_id == project_id, QlikApp.app_id == app_id)
    )
    app_count = _safe_int((await session.execute(exists_stmt)).scalar())
    if app_count <= 0:
        raise KeyError("app not found")


async def _latest_snapshot_for_app(
    session: AsyncSession,
    *,
    project_id: int,
    app_id: str,
) -> int | None:
    stmt = (
        select(AppDataMetadataSnapshot.snapshot_id)
        .where(
            AppDataMetadataSnapshot.project_id == project_id,
            AppDataMetadataSnapshot.app_id == app_id,
        )
        .order_by(
            AppDataMetadataSnapshot.fetched_at.desc(),
            AppDataMetadataSnapshot.snapshot_id.desc(),
        )
        .limit(1)
    )
    value = (await session.execute(stmt)).scalar()
    if value is None:
        return None
    return _safe_int(value)


FIELD_SORT_COLUMN_MAP = {
    "name": AppDataMetadataField.name,
    "byte_size": AppDataMetadataField.byte_size,
    "cardinal": AppDataMetadataField.cardinal,
    "total_count": AppDataMetadataField.total_count,
    "is_numeric": AppDataMetadataField.is_numeric,
    "is_semantic": AppDataMetadataField.is_semantic,
    "is_system": AppDataMetadataField.is_system,
    "is_hidden": AppDataMetadataField.is_hidden,
    "is_locked": AppDataMetadataField.is_locked,
    "distinct_only": AppDataMetadataField.distinct_only,
    "always_one_selected": AppDataMetadataField.always_one_selected,
}


async def load_analytics_app_fields(
    session: AsyncSession,
    *,
    project_id: int,
    app_id: str,
    limit: int = DEFAULT_FIELDS_LIMIT,
    offset: int = 0,
    sort_by: str = "byte_size",
    sort_dir: Literal["asc", "desc"] = "desc",
    search: str | None = None,
) -> dict[str, Any]:
    await _ensure_app_exists(session, project_id=project_id, app_id=app_id)
    snapshot_id = await _latest_snapshot_for_app(session, project_id=project_id, app_id=app_id)
    sort_key = sort_by if sort_by in FIELD_SORT_COLUMN_MAP else "byte_size"
    limit_val = min(max(1, int(limit)), MAX_FIELDS_LIMIT)
    offset_val = max(0, int(offset))
    search_text = _safe_text(search)
    paging = {
        "limit": limit_val,
        "offset": offset_val,
        "total": 0,
        "sort_by": sort_key,
        "sort_dir": sort_dir,
        "search": search_text,
    }
    if snapshot_id is None:
        return {
            "app_id": app_id,
            "project_id": project_id,
            "snapshot_id": None,
            "fields": [],
            "paging": paging,
        }

    filters = [
        AppDataMetadataField.project_id == project_id,
        AppDataMetadataField.snapshot_id == snapshot_id,
    ]
    if search_text:
        filters.append(sa_func.lower(sa_func.coalesce(AppDataMetadataField.name, "")).like(f"%{search_text.lower()}%"))

    count_stmt = (
        select(sa_func.count())
        .select_from(AppDataMetadataField)
        .where(*filters)
    )
    total_count = _safe_int((await session.execute(count_stmt)).scalar())
    paging["total"] = total_count

    sort_column = FIELD_SORT_COLUMN_MAP[sort_key]
    order_expr = sort_column.asc() if sort_dir == "asc" else sort_column.desc()
    stmt = (
        select(
            AppDataMetadataField.row_id,
            AppDataMetadataField.field_hash,
            AppDataMetadataField.name,
            AppDataMetadataField.byte_size,
            AppDataMetadataField.cardinal,
            AppDataMetadataField.total_count,
            AppDataMetadataField.is_numeric,
            AppDataMetadataField.is_semantic,
            AppDataMetadataField.is_system,
            AppDataMetadataField.is_hidden,
            AppDataMetadataField.is_locked,
            AppDataMetadataField.distinct_only,
            AppDataMetadataField.always_one_selected,
            AppDataMetadataField.tags,
            AppDataMetadataField.src_tables,
        )
        .where(*filters)
        .order_by(order_expr, AppDataMetadataField.row_id.asc())
        .limit(limit_val)
        .offset(offset_val)
    )
    rows = (await session.execute(stmt)).mappings().all()
    out_fields = []
    for row in rows:
        item = dict(row)
        if isinstance(item.get("tags"), tuple):
            item["tags"] = list(item["tags"])
        if isinstance(item.get("src_tables"), tuple):
            item["src_tables"] = list(item["src_tables"])
        out_fields.append(item)

    return {
        "app_id": app_id,
        "project_id": project_id,
        "snapshot_id": snapshot_id,
        "fields": out_fields,
        "paging": paging,
    }


async def load_analytics_app_trend(
    session: AsyncSession,
    *,
    project_id: int,
    app_id: str,
    days: int = DEFAULT_DAYS,
) -> dict[str, Any]:
    await _ensure_app_exists(session, project_id=project_id, app_id=app_id)
    stmt = (
        select(
            AppDataMetadataSnapshot.fetched_at,
            AppDataMetadataSnapshot.static_byte_size,
            AppDataMetadataSnapshot.reload_meta_peak_memory_bytes,
            AppDataMetadataSnapshot.reload_meta_cpu_time_spent_ms,
            AppDataMetadataSnapshot.schema_hash,
        )
        .where(
            AppDataMetadataSnapshot.project_id == project_id,
            AppDataMetadataSnapshot.app_id == app_id,
            AppDataMetadataSnapshot.fetched_at >= _window_start(days),
        )
        .order_by(AppDataMetadataSnapshot.fetched_at.asc(), AppDataMetadataSnapshot.snapshot_id.asc())
    )
    points = (await session.execute(stmt)).mappings().all()
    return {
        "app_id": app_id,
        "project_id": project_id,
        "days": max(1, int(days)),
        "points": [dict(item) for item in points],
    }


async def _load_usage_by_app(
    session: AsyncSession,
    *,
    project_id: int | None,
) -> dict[tuple[int, str], dict[str, Any]]:
    stmt = select(
        QlikAppUsage.project_id,
        QlikAppUsage.app_id,
        QlikAppUsage.usage_reloads,
        QlikAppUsage.usage_app_opens,
        QlikAppUsage.usage_sheet_views,
        QlikAppUsage.usage_unique_users,
    )
    if project_id is not None:
        stmt = stmt.where(QlikAppUsage.project_id == project_id)
    rows = (await session.execute(stmt)).all()
    out: dict[tuple[int, str], dict[str, Any]] = {}
    for p_id, app_id, usage_reloads, usage_app_opens, usage_sheet_views, usage_unique_users in rows:
        out[(int(p_id), str(app_id))] = {
            "usage_reloads": _safe_int(usage_reloads),
            "usage_app_opens": _safe_int(usage_app_opens),
            "usage_sheet_views": _safe_int(usage_sheet_views),
            "usage_unique_users": _safe_int(usage_unique_users),
        }
    return out


def _usage_signal_score(usage: dict[str, Any] | None) -> float:
    data = usage or {}
    return float(
        _safe_int(data.get("usage_app_opens"))
        + (_safe_int(data.get("usage_sheet_views")) * 0.6)
        + (_safe_int(data.get("usage_unique_users")) * 8.0)
        + (_safe_int(data.get("usage_reloads")) * 1.5)
    )


def _q1(values: list[float]) -> float:
    cleaned = sorted(max(0.0, _safe_float(item)) for item in values)
    if not cleaned:
        return 0.0
    if len(cleaned) == 1:
        return cleaned[0]
    idx = int(round((len(cleaned) - 1) * 0.25))
    idx = max(0, min(idx, len(cleaned) - 1))
    return cleaned[idx]


def _usage_classification(*, score: float, usage: dict[str, Any] | None, low_threshold: float) -> str:
    data = usage or {}
    has_any_usage = (
        _safe_int(data.get("usage_app_opens")) > 0
        or _safe_int(data.get("usage_sheet_views")) > 0
        or _safe_int(data.get("usage_unique_users")) > 0
        or _safe_int(data.get("usage_reloads")) > 0
    )
    if not has_any_usage or score <= 0.0:
        return "no-usage"
    if score <= max(1.0, low_threshold):
        return "low-usage"
    return "active"


def _is_qvd_node(*, node_type: Any, node_id: Any, data: dict[str, Any]) -> bool:
    node_type_text = str(_safe_text(node_type) or "").strip().lower()
    if node_type_text == "qvd":
        return True
    label = _safe_text(data.get("label")) or _safe_text(data.get("name")) or _safe_text(node_id) or ""
    return str(label).strip().lower().endswith(".qvd")


def _build_governance_action_plan(
    *,
    summary: dict[str, Any],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    low_or_no_apps = _safe_int(summary.get("low_or_no_usage_apps_count"))
    low_tables = _safe_int(summary.get("low_signal_tables_count"))
    low_fields = _safe_int(summary.get("low_signal_fields_count"))
    low_qvds = _safe_int(summary.get("low_signal_qvds_count"))

    if low_or_no_apps > 0:
        actions.append(
            {
                "action_id": "apps-retirement-review",
                "priority": "high",
                "title": "App-Rationalisierung fuer Low/No-Usage Kandidaten",
                "scope": "Apps",
                "candidate_count": low_or_no_apps,
                "target_metric": "Anteil Low/No-Usage Apps reduzieren",
                "rationale": "Apps mit sehr niedriger Nutzung und relevantem Footprint erzeugen Betriebsaufwand ohne klaren Wertbeitrag.",
                "suggested_steps": [
                    "Business-Owner pro Kandidat bestaetigen.",
                    "Stilllegung, Archivierung oder Konsolidierung je App entscheiden.",
                    "Entscheidung und Review-Zyklus als Governance-Workflow etablieren.",
                ],
            }
        )
    if low_tables > 0 or low_fields > 0:
        actions.append(
            {
                "action_id": "data-model-bloat-cleanup",
                "priority": "high",
                "title": "Bloat-Cleanup in Low/No-Usage Apps priorisieren",
                "scope": "Tabellen/Felder",
                "candidate_count": low_tables + low_fields,
                "target_metric": "Byte-Size in Low/No-Usage Segment reduzieren",
                "rationale": "Grosse Tabellen/Felder in schwach genutzten Apps sind direkte Optimierungskandidaten fuer Speicherkosten und Reload-Zeit.",
                "suggested_steps": [
                    "Top-Tabellen und Top-Felder nach Byte-Size im Modell-Review behandeln.",
                    "Nicht benoetigte Felder entfernen oder aggregieren.",
                    "Vor/Nach-Messung fuer static_byte_size und peak_memory dokumentieren.",
                ],
            }
        )
    if low_qvds > 0:
        actions.append(
            {
                "action_id": "qvd-lineage-cleanup",
                "priority": "medium",
                "title": "QVD-Abhaengigkeiten mit schwachem Signal pruefen",
                "scope": "QVD / Lineage",
                "candidate_count": low_qvds,
                "target_metric": "Orphan/Low-Signal QVD-Knoten reduzieren",
                "rationale": "QVDs mit geringer Einbindung oder nur schwach genutzten Consumer-Apps deuten auf veraltete Datenpfade hin.",
                "suggested_steps": [
                    "QVD-Kandidaten mit Fachbereich und Data-Owner validieren.",
                    "Nicht mehr benoetigte Stores/Loads im Skript bereinigen.",
                    "Lineage erneut laden und Kritikalitaetsaenderung pruefen.",
                ],
            }
        )
    if not actions:
        actions.append(
            {
                "action_id": "governance-baseline",
                "priority": "low",
                "title": "Governance-Baseline stabil halten",
                "scope": "Portfolio",
                "candidate_count": 0,
                "target_metric": "Nutzungstransparenz konstant halten",
                "rationale": "Aktuell sind keine deutlichen Low-Signal Cluster erkennbar; Monitoring sollte dennoch regelmaessig erfolgen.",
                "suggested_steps": [
                    "Monatlichen Review fuer Usage- und Metadata-KPIs beibehalten.",
                    "Abweichungsschwellen fuer Low-Usage und Drift beobachten.",
                ],
            }
        )
    return actions


async def _load_low_signal_table_candidates(
    session: AsyncSession,
    *,
    snapshot_ids: list[int],
    snapshot_to_app: dict[int, dict[str, Any]],
    low_usage_keys: set[tuple[int, str]],
    usage_by_app: dict[tuple[int, str], dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    if not snapshot_ids or not low_usage_keys:
        return []
    stmt = (
        select(
            AppDataMetadataTable.snapshot_id,
            AppDataMetadataTable.name,
            AppDataMetadataTable.byte_size,
            AppDataMetadataTable.no_of_rows,
            AppDataMetadataTable.no_of_fields,
            AppDataMetadataTable.no_of_key_fields,
            AppDataMetadataTable.is_system,
            AppDataMetadataTable.is_semantic,
        )
        .where(AppDataMetadataTable.snapshot_id.in_(snapshot_ids))
        .order_by(AppDataMetadataTable.byte_size.desc(), AppDataMetadataTable.row_id.asc())
        .limit(max(limit * 6, 120))
    )
    candidates: list[dict[str, Any]] = []
    for row in (await session.execute(stmt)).all():
        snapshot_id = _safe_int(row.snapshot_id)
        app_info = snapshot_to_app.get(snapshot_id)
        if not app_info:
            continue
        app_key = (app_info["project_id"], app_info["app_id"])
        if app_key not in low_usage_keys:
            continue
        if row.is_system is True:
            continue
        usage = usage_by_app.get(app_key, {})
        usage_score = round(_usage_signal_score(usage), 2)
        usage_class = str(app_info.get("usage_classification") or "low-usage")
        reason = "Keine App-Nutzung bei grossem Tabellen-Footprint." if usage_class == "no-usage" else "Niedrige App-Nutzung bei grossem Tabellen-Footprint."
        candidates.append(
            {
                "project_id": app_info["project_id"],
                "app_id": app_info["app_id"],
                "app_name": app_info["app_name"],
                "space_name": app_info["space_name"],
                "usage_classification": usage_class,
                "usage_signal_score": usage_score,
                "usage_app_opens": _safe_int(usage.get("usage_app_opens")),
                "usage_sheet_views": _safe_int(usage.get("usage_sheet_views")),
                "usage_unique_users": _safe_int(usage.get("usage_unique_users")),
                "usage_reloads": _safe_int(usage.get("usage_reloads")),
                "table_name": str(row.name or ""),
                "byte_size": _safe_int(row.byte_size),
                "no_of_rows": _safe_int(row.no_of_rows),
                "no_of_fields": _safe_int(row.no_of_fields),
                "no_of_key_fields": _safe_int(row.no_of_key_fields),
                "is_semantic": row.is_semantic,
                "reason": reason,
            }
        )
        if len(candidates) >= limit:
            break
    return candidates


async def _load_low_signal_field_candidates(
    session: AsyncSession,
    *,
    snapshot_ids: list[int],
    snapshot_to_app: dict[int, dict[str, Any]],
    low_usage_keys: set[tuple[int, str]],
    usage_by_app: dict[tuple[int, str], dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    if not snapshot_ids or not low_usage_keys:
        return []
    stmt = (
        select(
            AppDataMetadataField.snapshot_id,
            AppDataMetadataField.field_hash,
            AppDataMetadataField.name,
            AppDataMetadataField.byte_size,
            AppDataMetadataField.cardinal,
            AppDataMetadataField.total_count,
            AppDataMetadataField.is_hidden,
            AppDataMetadataField.is_system,
            AppDataMetadataField.is_semantic,
            AppDataMetadataField.src_tables,
        )
        .where(AppDataMetadataField.snapshot_id.in_(snapshot_ids))
        .order_by(AppDataMetadataField.byte_size.desc(), AppDataMetadataField.row_id.asc())
        .limit(max(limit * 8, 160))
    )
    candidates: list[dict[str, Any]] = []
    for row in (await session.execute(stmt)).all():
        snapshot_id = _safe_int(row.snapshot_id)
        app_info = snapshot_to_app.get(snapshot_id)
        if not app_info:
            continue
        app_key = (app_info["project_id"], app_info["app_id"])
        if app_key not in low_usage_keys:
            continue
        if row.is_system is True:
            continue
        usage = usage_by_app.get(app_key, {})
        usage_score = round(_usage_signal_score(usage), 2)
        src_tables = row.src_tables
        if isinstance(src_tables, tuple):
            src_tables = list(src_tables)
        usage_class = str(app_info.get("usage_classification") or "low-usage")
        reason = "Keine App-Nutzung bei grossem Feld-Footprint." if usage_class == "no-usage" else "Niedrige App-Nutzung bei grossem Feld-Footprint."
        candidates.append(
            {
                "project_id": app_info["project_id"],
                "app_id": app_info["app_id"],
                "app_name": app_info["app_name"],
                "space_name": app_info["space_name"],
                "usage_classification": usage_class,
                "usage_signal_score": usage_score,
                "usage_app_opens": _safe_int(usage.get("usage_app_opens")),
                "usage_sheet_views": _safe_int(usage.get("usage_sheet_views")),
                "usage_unique_users": _safe_int(usage.get("usage_unique_users")),
                "usage_reloads": _safe_int(usage.get("usage_reloads")),
                "field_hash": str(row.field_hash or ""),
                "name": _safe_text(row.name),
                "byte_size": _safe_int(row.byte_size),
                "cardinal": _safe_int(row.cardinal),
                "total_count": _safe_int(row.total_count),
                "is_hidden": row.is_hidden,
                "is_semantic": row.is_semantic,
                "src_tables": list(src_tables) if isinstance(src_tables, list) else None,
                "reason": reason,
            }
        )
        if len(candidates) >= limit:
            break
    return candidates


async def _load_low_signal_qvd_candidates(
    session: AsyncSession,
    *,
    project_id: int | None,
    app_meta_by_key: dict[tuple[int, str], dict[str, Any]],
    low_usage_keys: set[tuple[int, str]],
    usage_by_app: dict[tuple[int, str], dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    node_stmt = select(
        LineageNode.project_id,
        LineageNode.node_id,
        LineageNode.app_id,
        LineageNode.node_type,
        LineageNode.data,
    )
    edge_stmt = select(
        LineageEdge.project_id,
        LineageEdge.source_node_id,
        LineageEdge.target_node_id,
    )
    if project_id is not None:
        node_stmt = node_stmt.where(LineageNode.project_id == project_id)
        edge_stmt = edge_stmt.where(LineageEdge.project_id == project_id)

    node_rows = (await session.execute(node_stmt)).all()
    edge_rows = (await session.execute(edge_stmt)).all()

    qvd_nodes: dict[tuple[int, str], dict[str, Any]] = {}
    in_degree: dict[tuple[int, str], int] = {}
    out_degree: dict[tuple[int, str], int] = {}

    for row in node_rows:
        payload = dict(row.data) if isinstance(row.data, dict) else {}
        if not _is_qvd_node(node_type=row.node_type, node_id=row.node_id, data=payload):
            continue
        key = (int(row.project_id), str(row.node_id))
        label = _safe_text(payload.get("label")) or _safe_text(payload.get("name")) or str(row.node_id)
        app_id = _safe_text(row.app_id)
        app_key = (int(row.project_id), app_id) if app_id else None
        app_meta = app_meta_by_key.get(app_key) if app_key else None
        usage = usage_by_app.get(app_key, {}) if app_key else {}
        qvd_nodes[key] = {
            "project_id": int(row.project_id),
            "node_id": str(row.node_id),
            "label": label or str(row.node_id),
            "app_id": app_id,
            "app_name": _safe_text((app_meta or {}).get("app_name"))
            or _safe_text(payload.get("appName"))
            or _safe_text(payload.get("app_name"))
            or app_id,
            "space_name": _safe_text((app_meta or {}).get("space_name"))
            or _safe_text(payload.get("spaceName"))
            or _safe_text(payload.get("space_name"))
            or "Unassigned",
            "usage_signal_score": round(_usage_signal_score(usage), 2),
            "usage_app_opens": _safe_int(usage.get("usage_app_opens")),
            "usage_sheet_views": _safe_int(usage.get("usage_sheet_views")),
            "usage_unique_users": _safe_int(usage.get("usage_unique_users")),
            "usage_reloads": _safe_int(usage.get("usage_reloads")),
            "linked_app_low_usage": bool(app_key and app_key in low_usage_keys),
        }
        in_degree[key] = 0
        out_degree[key] = 0

    if not qvd_nodes:
        return []

    for row in edge_rows:
        p_id = int(row.project_id)
        source = _safe_text(row.source_node_id)
        target = _safe_text(row.target_node_id)
        if not source or not target:
            continue
        s_key = (p_id, source)
        t_key = (p_id, target)
        if s_key in qvd_nodes:
            out_degree[s_key] = _safe_int(out_degree.get(s_key)) + 1
        if t_key in qvd_nodes:
            in_degree[t_key] = _safe_int(in_degree.get(t_key)) + 1

    candidates: list[dict[str, Any]] = []
    for key, node in qvd_nodes.items():
        deg_in = _safe_int(in_degree.get(key))
        deg_out = _safe_int(out_degree.get(key))
        degree = deg_in + deg_out
        usage_score = _safe_float(node.get("usage_signal_score"))
        linked_low_usage = bool(node.get("linked_app_low_usage"))
        if degree > 1 and not linked_low_usage and usage_score > 0.0:
            continue
        if degree == 0:
            signal_class = "orphan-qvd"
            reason = "QVD ohne erkennbare Lineage-Verknuepfung im aktuellen Graph."
        elif linked_low_usage:
            signal_class = "linked-low-usage-app"
            reason = "QVD haengt an einer App mit niedriger oder fehlender Nutzung."
        else:
            signal_class = "low-lineage-degree"
            reason = "QVD hat nur geringe Lineage-Einbindung (Degree <= 1)."
        item = dict(node)
        item["degree"] = degree
        item["in_degree"] = deg_in
        item["out_degree"] = deg_out
        item["signal_classification"] = signal_class
        item["reason"] = reason
        candidates.append(item)

    candidates.sort(
        key=lambda item: (
            0 if str(item.get("signal_classification")) == "orphan-qvd" else 1,
            _safe_int(item.get("degree")),
            _safe_float(item.get("usage_signal_score")),
            str(item.get("label") or "").lower(),
        )
    )
    return candidates[:limit]


async def load_governance_operations(
    session: AsyncSession,
    *,
    project_id: int | None = None,
    limit: int = DEFAULT_GOVERNANCE_LIMIT,
) -> dict[str, Any]:
    limit_val = max(1, min(int(limit), 200))
    latest_rows = await _load_latest_snapshot_rows(session, project_id=project_id)
    if not latest_rows:
        summary = {
            "apps_total": 0,
            "low_or_no_usage_apps_count": 0,
            "no_usage_apps_count": 0,
            "low_usage_apps_count": 0,
            "low_signal_tables_count": 0,
            "low_signal_fields_count": 0,
            "low_signal_qvds_count": 0,
            "low_usage_signal_threshold": 0.0,
        }
        return {
            "summary": summary,
            "low_usage_apps": [],
            "low_signal_tables": [],
            "low_signal_fields": [],
            "low_signal_qvds": [],
            "action_plan": _build_governance_action_plan(summary=summary),
        }

    usage_by_app = await _load_usage_by_app(session, project_id=project_id)

    usage_scores_non_zero: list[float] = []
    app_rows: list[dict[str, Any]] = []
    snapshot_to_app: dict[int, dict[str, Any]] = {}
    app_key_to_snapshot_id: dict[tuple[int, str], int] = {}
    app_meta_by_key: dict[tuple[int, str], dict[str, Any]] = {}
    for row in latest_rows:
        p_id = _safe_int(row.get("project_id"))
        app_id = str(row.get("app_id") or "")
        snapshot_id = _safe_int(row.get("snapshot_id"))
        area = _area_from_snapshot_row(row)
        usage = usage_by_app.get((p_id, app_id), {})
        usage_score = _usage_signal_score(usage)
        if usage_score > 0.0:
            usage_scores_non_zero.append(usage_score)
        app_name = _app_name_from_snapshot_row(row)
        app_item = {
            "project_id": p_id,
            "app_id": app_id,
            "app_name": app_name,
            "space_name": area.area_name if area.area_key != AREA_UNASSIGNED_KEY else "Unassigned",
            "latest_fetched_at": row.get("fetched_at"),
            "static_byte_size_latest": _safe_int(row.get("static_byte_size")),
            "reload_meta_peak_memory_bytes_latest": _safe_int(row.get("reload_meta_peak_memory_bytes")),
            "reload_meta_cpu_time_spent_ms_latest": _safe_int(row.get("reload_meta_cpu_time_spent_ms")),
            "usage_app_opens": _safe_int(usage.get("usage_app_opens")),
            "usage_sheet_views": _safe_int(usage.get("usage_sheet_views")),
            "usage_unique_users": _safe_int(usage.get("usage_unique_users")),
            "usage_reloads": _safe_int(usage.get("usage_reloads")),
            "usage_signal_score": round(usage_score, 2),
        }
        app_rows.append(app_item)
        snapshot_to_app[snapshot_id] = {
            "project_id": p_id,
            "app_id": app_id,
            "app_name": app_name,
            "space_name": app_item["space_name"],
            "usage_classification": "active",
        }
        app_key_to_snapshot_id[(p_id, app_id)] = snapshot_id
        app_meta_by_key[(p_id, app_id)] = {
            "app_name": app_name,
            "space_name": app_item["space_name"],
        }

    low_threshold = _q1(usage_scores_non_zero)
    low_usage_apps: list[dict[str, Any]] = []
    low_usage_keys: set[tuple[int, str]] = set()
    no_usage_count = 0
    low_usage_count = 0
    for item in app_rows:
        app_key = (item["project_id"], item["app_id"])
        usage = {
            "usage_app_opens": item["usage_app_opens"],
            "usage_sheet_views": item["usage_sheet_views"],
            "usage_unique_users": item["usage_unique_users"],
            "usage_reloads": item["usage_reloads"],
        }
        class_name = _usage_classification(
            score=_safe_float(item.get("usage_signal_score")),
            usage=usage,
            low_threshold=low_threshold,
        )
        snapshot_id = app_key_to_snapshot_id.get(app_key)
        if snapshot_id is not None:
            snapshot_to_app[snapshot_id]["usage_classification"] = class_name
        if class_name == "active":
            continue
        low_usage_keys.add(app_key)
        if class_name == "no-usage":
            no_usage_count += 1
            reason = "Keine Nutzungsaktivitaet im vorhandenen Usage-Snapshot."
        else:
            low_usage_count += 1
            reason = "Niedrige Nutzungsaktivitaet relativ zum Portfolio."
        app_candidate = dict(item)
        app_candidate["usage_classification"] = class_name
        app_candidate["reason"] = reason
        low_usage_apps.append(app_candidate)

    low_usage_apps.sort(
        key=lambda item: (
            0 if str(item.get("usage_classification")) == "no-usage" else 1,
            -_safe_int(item.get("static_byte_size_latest")),
            _safe_float(item.get("usage_signal_score")),
        )
    )
    low_usage_apps = low_usage_apps[:limit_val]

    snapshot_ids = [_safe_int(row.get("snapshot_id")) for row in latest_rows]
    low_signal_tables = await _load_low_signal_table_candidates(
        session,
        snapshot_ids=snapshot_ids,
        snapshot_to_app=snapshot_to_app,
        low_usage_keys=low_usage_keys,
        usage_by_app=usage_by_app,
        limit=limit_val,
    )
    low_signal_fields = await _load_low_signal_field_candidates(
        session,
        snapshot_ids=snapshot_ids,
        snapshot_to_app=snapshot_to_app,
        low_usage_keys=low_usage_keys,
        usage_by_app=usage_by_app,
        limit=limit_val,
    )
    low_signal_qvds = await _load_low_signal_qvd_candidates(
        session,
        project_id=project_id,
        app_meta_by_key=app_meta_by_key,
        low_usage_keys=low_usage_keys,
        usage_by_app=usage_by_app,
        limit=limit_val,
    )

    summary = {
        "apps_total": len(app_rows),
        "low_or_no_usage_apps_count": len(low_usage_keys),
        "no_usage_apps_count": no_usage_count,
        "low_usage_apps_count": low_usage_count,
        "low_signal_tables_count": len(low_signal_tables),
        "low_signal_fields_count": len(low_signal_fields),
        "low_signal_qvds_count": len(low_signal_qvds),
        "low_usage_signal_threshold": round(max(1.0, low_threshold), 2) if low_threshold > 0 else 0.0,
    }
    return {
        "summary": summary,
        "low_usage_apps": low_usage_apps,
        "low_signal_tables": low_signal_tables,
        "low_signal_fields": low_signal_fields,
        "low_signal_qvds": low_signal_qvds,
        "action_plan": _build_governance_action_plan(summary=summary),
    }


async def load_cost_value_map(
    session: AsyncSession,
    *,
    project_id: int | None = None,
    days: int = DEFAULT_DAYS,
) -> dict[str, Any]:
    latest_rows = await _load_latest_snapshot_rows(session, project_id=project_id)
    if not latest_rows:
        return {
            "apps": [],
            "summary": {
                "apps_count": 0,
                "high_cost_low_value_count": 0,
                "avg_cost_score": 0.0,
                "avg_value_score": 0.0,
            },
        }

    snapshot_ids = [_safe_int(row.get("snapshot_id")) for row in latest_rows]
    field_count_by_snapshot = await _load_field_count_by_snapshot(session, snapshot_ids=snapshot_ids)
    table_stats_by_snapshot = await _load_table_stats_by_snapshot(session, snapshot_ids=snapshot_ids)
    usage_by_app = await _load_usage_by_app(session, project_id=project_id)

    app_rows: list[dict[str, Any]] = []
    cost_raw_values: list[float] = []
    value_usage_raw_values: list[float] = []
    value_proxy_raw_values: list[float] = []
    complexity_raw_values: list[float] = []

    for row in latest_rows:
        p_id = _safe_int(row.get("project_id"))
        app_id = str(row.get("app_id") or "")
        snapshot_id = _safe_int(row.get("snapshot_id"))
        usage = usage_by_app.get((p_id, app_id), {})
        table_stats = table_stats_by_snapshot.get(snapshot_id, {})
        fields_count = _safe_int(field_count_by_snapshot.get(snapshot_id))
        tables_count = _safe_int(table_stats.get("tables_count"))
        complexity_raw = float(fields_count + tables_count * 8)
        cost_raw = float(
            _safe_int(row.get("static_byte_size"))
            + _safe_int(row.get("reload_meta_peak_memory_bytes"))
            + (_safe_int(row.get("reload_meta_cpu_time_spent_ms")) * 1024)
            + int(complexity_raw * 1024 * 128)
        )
        value_usage_raw = float(
            _safe_int(usage.get("usage_app_opens"))
            + (_safe_int(usage.get("usage_sheet_views")) * 0.6)
            + (_safe_int(usage.get("usage_unique_users")) * 8)
            + (_safe_int(usage.get("usage_reloads")) * 1.5)
        )
        value_proxy_raw = float(
            (fields_count * 1.2)
            + (tables_count * 4.0)
            + (_safe_int(row.get("has_section_access")) * 12)
            + ((1 - _safe_int(row.get("is_direct_query_mode"))) * 5)
        )
        cost_raw_values.append(cost_raw)
        value_usage_raw_values.append(value_usage_raw)
        value_proxy_raw_values.append(value_proxy_raw)
        complexity_raw_values.append(complexity_raw)
        area = _area_from_snapshot_row(row)
        app_rows.append(
            {
                "project_id": p_id,
                "app_id": app_id,
                "app_name": _app_name_from_snapshot_row(row),
                "space_name": area.area_name if area.area_key != AREA_UNASSIGNED_KEY else "Unassigned",
                "latest_fetched_at": row.get("fetched_at"),
                "static_byte_size_latest": _safe_int(row.get("static_byte_size")),
                "reload_meta_peak_memory_bytes_latest": _safe_int(row.get("reload_meta_peak_memory_bytes")),
                "reload_meta_cpu_time_spent_ms_latest": _safe_int(row.get("reload_meta_cpu_time_spent_ms")),
                "has_section_access_latest": row.get("has_section_access"),
                "is_direct_query_mode_latest": row.get("is_direct_query_mode"),
                "fields_count_latest": fields_count,
                "tables_count_latest": tables_count,
                "usage_app_opens": _safe_int(usage.get("usage_app_opens")),
                "usage_sheet_views": _safe_int(usage.get("usage_sheet_views")),
                "usage_unique_users": _safe_int(usage.get("usage_unique_users")),
                "usage_reloads": _safe_int(usage.get("usage_reloads")),
                "complexity_raw": round(complexity_raw, 2),
                "cost_raw": round(cost_raw, 2),
                "value_usage_raw": round(value_usage_raw, 2),
                "value_proxy_raw": round(value_proxy_raw, 2),
            }
        )

    cost_norm = _normalize_min_max(cost_raw_values)
    value_usage_norm = _normalize_min_max(value_usage_raw_values)
    value_proxy_norm = _normalize_min_max(value_proxy_raw_values)
    complexity_norm = _normalize_min_max(complexity_raw_values)
    usage_span = max(value_usage_raw_values) - min(value_usage_raw_values) if value_usage_raw_values else 0.0
    usage_has_signal = usage_span > 0.0 and any(v > 0.0 for v in value_usage_raw_values)
    value_signal_mode = "usage-primary" if usage_has_signal else "proxy-assisted"
    value_usage_weight = 0.85 if usage_has_signal else 0.35
    value_proxy_weight = 0.15 if usage_has_signal else 0.65

    high_cost_low_value_count = 0
    for idx, item in enumerate(app_rows):
        cost_score = round((cost_norm[idx] * 0.8) + (complexity_norm[idx] * 0.2), 2)
        value_usage_score = round(value_usage_norm[idx], 2)
        value_proxy_score = round(value_proxy_norm[idx], 2)
        value_score = round((value_usage_score * value_usage_weight) + (value_proxy_score * value_proxy_weight), 2)
        efficiency_score = round((value_score + 1.0) / (cost_score + 1.0) * 100.0, 2)
        item["complexity_score"] = round(complexity_norm[idx], 2)
        item["cost_score"] = cost_score
        item["value_score"] = value_score
        item["value_usage_score"] = value_usage_score
        item["value_proxy_score"] = value_proxy_score
        item["value_signal_mode"] = value_signal_mode
        item["efficiency_score"] = efficiency_score
        if cost_score >= 60.0 and value_score < 40.0:
            quadrant = "high-cost-low-value"
            high_cost_low_value_count += 1
        elif cost_score >= 60.0 and value_score >= 40.0:
            quadrant = "high-cost-high-value"
        elif cost_score < 60.0 and value_score >= 40.0:
            quadrant = "efficient-value"
        else:
            quadrant = "low-cost-low-value"
        item["quadrant"] = quadrant

    app_rows.sort(
        key=lambda item: (
            0 if item.get("quadrant") == "high-cost-low-value" else 1,
            -_safe_float(item.get("cost_score")),
            _safe_float(item.get("value_score")),
        )
    )
    return {
        "apps": app_rows,
        "summary": {
            "apps_count": len(app_rows),
            "high_cost_low_value_count": high_cost_low_value_count,
            "avg_cost_score": round(_mean([_safe_float(item.get("cost_score")) for item in app_rows]), 2),
            "avg_value_score": round(_mean([_safe_float(item.get("value_score")) for item in app_rows]), 2),
            "value_signal_mode": value_signal_mode,
            "value_usage_weight": value_usage_weight,
            "value_proxy_weight": value_proxy_weight,
        },
    }


async def load_bloat_explorer(
    session: AsyncSession,
    *,
    project_id: int | None = None,
    days: int = DEFAULT_DAYS,
    limit: int = 25,
) -> dict[str, Any]:
    limit_val = max(1, min(int(limit), 200))
    latest_rows = await _load_latest_snapshot_rows(session, project_id=project_id)
    if not latest_rows:
        return {
            "top_apps": [],
            "top_tables": [],
            "top_fields": [],
            "schema_drift_apps": [],
            "summary": {
                "apps_count": 0,
                "top_tables_count": 0,
                "top_fields_count": 0,
                "schema_drift_apps_count": 0,
            },
        }

    snapshot_ids = [_safe_int(row.get("snapshot_id")) for row in latest_rows]
    field_count_by_snapshot = await _load_field_count_by_snapshot(session, snapshot_ids=snapshot_ids)
    table_stats_by_snapshot = await _load_table_stats_by_snapshot(session, snapshot_ids=snapshot_ids)
    drift_hash_counts = await _load_schema_distinct_hash_counts(session, days=days, project_id=project_id)

    snapshot_to_app: dict[int, dict[str, Any]] = {}
    top_apps: list[dict[str, Any]] = []
    for row in latest_rows:
        snapshot_id = _safe_int(row.get("snapshot_id"))
        p_id = _safe_int(row.get("project_id"))
        app_id = str(row.get("app_id") or "")
        area = _area_from_snapshot_row(row)
        snapshot_to_app[snapshot_id] = {
            "project_id": p_id,
            "app_id": app_id,
            "app_name": _app_name_from_snapshot_row(row),
            "space_name": area.area_name,
        }
        top_apps.append(
            {
                "project_id": p_id,
                "app_id": app_id,
                "app_name": _app_name_from_snapshot_row(row),
                "space_name": area.area_name,
                "static_byte_size_latest": _safe_int(row.get("static_byte_size")),
                "fields_count_latest": _safe_int(field_count_by_snapshot.get(snapshot_id)),
                "tables_count_latest": _safe_int(table_stats_by_snapshot.get(snapshot_id, {}).get("tables_count")),
                "schema_drift_count_in_window": max(drift_hash_counts.get((p_id, app_id), 0) - 1, 0),
            }
        )
    top_apps.sort(key=lambda item: (-_safe_int(item.get("static_byte_size_latest")), item.get("app_name") or ""))
    top_apps = top_apps[:limit_val]

    tables_stmt = (
        select(
            AppDataMetadataTable.snapshot_id,
            AppDataMetadataTable.name,
            AppDataMetadataTable.byte_size,
            AppDataMetadataTable.no_of_rows,
            AppDataMetadataTable.no_of_fields,
            AppDataMetadataTable.no_of_key_fields,
            AppDataMetadataTable.is_system,
            AppDataMetadataTable.is_semantic,
        )
        .where(AppDataMetadataTable.snapshot_id.in_(snapshot_ids))
        .order_by(AppDataMetadataTable.byte_size.desc(), AppDataMetadataTable.row_id.asc())
        .limit(limit_val)
    )
    top_tables: list[dict[str, Any]] = []
    for row in (await session.execute(tables_stmt)).all():
        snapshot_id = _safe_int(row.snapshot_id)
        app_info = snapshot_to_app.get(snapshot_id, {})
        top_tables.append(
            {
                "project_id": _safe_int(app_info.get("project_id")),
                "app_id": str(app_info.get("app_id") or ""),
                "app_name": str(app_info.get("app_name") or "unknown-app"),
                "space_name": _safe_text(app_info.get("space_name")) or "Unassigned",
                "table_name": str(row.name or ""),
                "byte_size": _safe_int(row.byte_size),
                "no_of_rows": _safe_int(row.no_of_rows),
                "no_of_fields": _safe_int(row.no_of_fields),
                "no_of_key_fields": _safe_int(row.no_of_key_fields),
                "is_system": row.is_system,
                "is_semantic": row.is_semantic,
            }
        )

    fields_stmt = (
        select(
            AppDataMetadataField.snapshot_id,
            AppDataMetadataField.field_hash,
            AppDataMetadataField.name,
            AppDataMetadataField.byte_size,
            AppDataMetadataField.cardinal,
            AppDataMetadataField.total_count,
            AppDataMetadataField.is_system,
            AppDataMetadataField.is_hidden,
            AppDataMetadataField.is_semantic,
            AppDataMetadataField.src_tables,
        )
        .where(AppDataMetadataField.snapshot_id.in_(snapshot_ids))
        .order_by(AppDataMetadataField.byte_size.desc(), AppDataMetadataField.row_id.asc())
        .limit(limit_val)
    )
    top_fields: list[dict[str, Any]] = []
    for row in (await session.execute(fields_stmt)).all():
        snapshot_id = _safe_int(row.snapshot_id)
        app_info = snapshot_to_app.get(snapshot_id, {})
        src_tables = row.src_tables
        if isinstance(src_tables, tuple):
            src_tables = list(src_tables)
        top_fields.append(
            {
                "project_id": _safe_int(app_info.get("project_id")),
                "app_id": str(app_info.get("app_id") or ""),
                "app_name": str(app_info.get("app_name") or "unknown-app"),
                "space_name": _safe_text(app_info.get("space_name")) or "Unassigned",
                "field_hash": str(row.field_hash or ""),
                "name": _safe_text(row.name),
                "byte_size": _safe_int(row.byte_size),
                "cardinal": _safe_int(row.cardinal),
                "total_count": _safe_int(row.total_count),
                "is_system": row.is_system,
                "is_hidden": row.is_hidden,
                "is_semantic": row.is_semantic,
                "src_tables": list(src_tables) if isinstance(src_tables, list) else None,
            }
        )

    schema_drift_apps = [item for item in top_apps if _safe_int(item.get("schema_drift_count_in_window")) > 0]
    schema_drift_apps.sort(
        key=lambda item: (
            -_safe_int(item.get("schema_drift_count_in_window")),
            -_safe_int(item.get("static_byte_size_latest")),
        )
    )
    return {
        "top_apps": top_apps,
        "top_tables": top_tables,
        "top_fields": top_fields,
        "schema_drift_apps": schema_drift_apps[:limit_val],
        "summary": {
            "apps_count": len(latest_rows),
            "top_tables_count": len(top_tables),
            "top_fields_count": len(top_fields),
            "schema_drift_apps_count": len(schema_drift_apps),
        },
    }


async def load_data_model_pack(
    session: AsyncSession,
    *,
    project_id: int | None = None,
    metric: DataModelPackMetric = "static_byte_size_latest",
) -> dict[str, Any]:
    latest_rows = await _load_latest_snapshot_rows(session, project_id=project_id)
    if not latest_rows:
        return {
            "metric": metric,
            "metric_options": list(DATA_MODEL_PACK_METRICS),
            "areas": [],
            "summary": {
                "areas_count": 0,
                "apps_count": 0,
                "total_metric_value": 0.0,
            },
        }

    snapshot_ids = [_safe_int(row.get("snapshot_id")) for row in latest_rows]
    field_count_by_snapshot = await _load_field_count_by_snapshot(session, snapshot_ids=snapshot_ids)
    table_stats_by_snapshot = await _load_table_stats_by_snapshot(session, snapshot_ids=snapshot_ids)

    area_buckets: dict[str, dict[str, Any]] = {}
    total_metric_value = 0.0
    for row in latest_rows:
        snapshot_id = _safe_int(row.get("snapshot_id"))
        fields_count_latest = _safe_int(field_count_by_snapshot.get(snapshot_id))
        tables_count_latest = _safe_int(table_stats_by_snapshot.get(snapshot_id, {}).get("tables_count"))
        static_byte_size_latest = _safe_int(row.get("static_byte_size"))
        complexity_latest = fields_count_latest + (tables_count_latest * 8)
        metric_value = _metric_value_for_pack(
            metric=metric,
            static_byte_size=static_byte_size_latest,
            complexity=complexity_latest,
        )
        area = _area_from_snapshot_row(row)

        bucket = area_buckets.setdefault(
            area.area_key,
            {
                "area_key": area.area_key,
                "area_name": area.area_name,
                "metric_value": 0.0,
                "apps": [],
            },
        )
        bucket["metric_value"] = round(_safe_float(bucket.get("metric_value")) + metric_value, 2)
        bucket["apps"].append(
            {
                "project_id": _safe_int(row.get("project_id")),
                "app_id": str(row.get("app_id") or ""),
                "app_name": _app_name_from_snapshot_row(row),
                "space_name": area.area_name if area.area_key != AREA_UNASSIGNED_KEY else "Unassigned",
                "static_byte_size_latest": static_byte_size_latest,
                "fields_count_latest": fields_count_latest,
                "tables_count_latest": tables_count_latest,
                "complexity_latest": complexity_latest,
                "metric_value": round(metric_value, 2),
            }
        )
        total_metric_value += metric_value

    areas = list(area_buckets.values())
    for area_item in areas:
        area_item["apps"].sort(
            key=lambda item: (
                -_safe_float(item.get("metric_value")),
                str(item.get("app_name") or "").lower(),
            )
        )
    areas.sort(
        key=lambda item: (
            -_safe_float(item.get("metric_value")),
            str(item.get("area_name") or "").lower(),
        )
    )

    return {
        "metric": metric,
        "metric_options": list(DATA_MODEL_PACK_METRICS),
        "areas": areas,
        "summary": {
            "areas_count": len(areas),
            "apps_count": sum(len(item.get("apps") or []) for item in areas),
            "total_metric_value": round(total_metric_value, 2),
        },
    }


async def load_lineage_criticality(
    session: AsyncSession,
    *,
    project_id: int | None = None,
    limit: int = 30,
) -> dict[str, Any]:
    limit_val = max(1, min(int(limit), 200))
    node_stmt = select(
        LineageNode.project_id,
        LineageNode.node_id,
        LineageNode.app_id,
        LineageNode.node_type,
        LineageNode.data,
    )
    edge_stmt = select(
        LineageEdge.project_id,
        LineageEdge.source_node_id,
        LineageEdge.target_node_id,
    )
    if project_id is not None:
        node_stmt = node_stmt.where(LineageNode.project_id == project_id)
        edge_stmt = edge_stmt.where(LineageEdge.project_id == project_id)

    node_rows = (await session.execute(node_stmt)).all()
    edge_rows = (await session.execute(edge_stmt)).all()

    node_meta: dict[tuple[int, str], dict[str, Any]] = {}
    out_adj: dict[tuple[int, str], set[tuple[int, str]]] = {}
    in_adj: dict[tuple[int, str], set[tuple[int, str]]] = {}

    for row in node_rows:
        key = (int(row.project_id), str(row.node_id))
        data = dict(row.data) if isinstance(row.data, dict) else {}
        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
        node_meta[key] = {
            "project_id": int(row.project_id),
            "node_id": str(row.node_id),
            "label": _safe_text(data.get("label")) or str(row.node_id),
            "node_type": _safe_text(row.node_type) or _safe_text(data.get("type")) or "other",
            "app_id": _safe_text(row.app_id),
            "app_name": _safe_text(meta.get("appName")) or _safe_text(meta.get("app_name")),
            "space_name": _safe_text(meta.get("spaceName")) or _safe_text(meta.get("space_name")) or _safe_text(meta.get("area")),
        }
        out_adj.setdefault(key, set())
        in_adj.setdefault(key, set())

    valid_edges = 0
    for row in edge_rows:
        source = _safe_text(row.source_node_id)
        target = _safe_text(row.target_node_id)
        if not source or not target:
            continue
        s_key = (int(row.project_id), source)
        t_key = (int(row.project_id), target)
        if s_key not in node_meta or t_key not in node_meta:
            continue
        out_adj.setdefault(s_key, set()).add(t_key)
        in_adj.setdefault(t_key, set()).add(s_key)
        valid_edges += 1

    if not node_meta:
        return {
            "critical_nodes": [],
            "summary": {"nodes_count": 0, "edges_count": 0, "critical_nodes_count": 0},
        }

    def _blast_radius(start_key: tuple[int, str], max_depth: int = 4, max_nodes: int = 4000) -> int:
        visited: set[tuple[int, str]] = {start_key}
        frontier: set[tuple[int, str]] = {start_key}
        for _ in range(max_depth):
            if not frontier:
                break
            next_frontier: set[tuple[int, str]] = set()
            for node_key in frontier:
                for nxt in out_adj.get(node_key, set()):
                    if nxt in visited:
                        continue
                    visited.add(nxt)
                    next_frontier.add(nxt)
                    if len(visited) >= max_nodes:
                        break
                if len(visited) >= max_nodes:
                    break
            frontier = next_frontier
            if len(visited) >= max_nodes:
                break
        return max(0, len(visited) - 1)

    scored_nodes: list[dict[str, Any]] = []
    degrees: list[float] = []
    blasts: list[float] = []
    for key, base in node_meta.items():
        out_degree = len(out_adj.get(key, set()))
        in_degree = len(in_adj.get(key, set()))
        degree = in_degree + out_degree
        if degree <= 0:
            continue
        blast = _blast_radius(key)
        item = dict(base)
        item["degree"] = degree
        item["in_degree"] = in_degree
        item["out_degree"] = out_degree
        item["blast_radius"] = blast
        scored_nodes.append(item)
        degrees.append(float(degree))
        blasts.append(float(blast))

    if not scored_nodes:
        return {
            "critical_nodes": [],
            "summary": {"nodes_count": len(node_meta), "edges_count": valid_edges, "critical_nodes_count": 0},
        }

    degree_norm = _normalize_min_max(degrees)
    blast_norm = _normalize_min_max(blasts)
    for idx, item in enumerate(scored_nodes):
        item["criticality_score"] = round((degree_norm[idx] * 0.65) + (blast_norm[idx] * 0.35), 2)

    scored_nodes.sort(
        key=lambda item: (
            -_safe_float(item.get("criticality_score")),
            -_safe_int(item.get("degree")),
            -_safe_int(item.get("blast_radius")),
        )
    )
    top_nodes = scored_nodes[:limit_val]
    return {
        "critical_nodes": top_nodes,
        "summary": {
            "nodes_count": len(node_meta),
            "edges_count": valid_edges,
            "critical_nodes_count": len(top_nodes),
        },
    }
