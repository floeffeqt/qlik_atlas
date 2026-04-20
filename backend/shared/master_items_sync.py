"""Master Items Sync — export, diff, and import Qlik master items via Engine API.

Uses ``QlikEngineClient.open_session`` from ``qlik_engine_client.py`` for the
WebSocket / JSON-RPC transport. All three public functions are async.

Public API:
    export_master_items(creds, app_id) -> dict
    diff_master_items(creds, source, target_app_id) -> dict
    import_master_items(creds, target_app_id, source, options) -> dict
"""
from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone
from typing import Optional

from shared.qlik_client import QlikCredentials
from shared.qlik_engine_client import EngineSession, QlikEngineClient, QlikEngineError

logger = logging.getLogger("qlik.master_items")


# ── Error ────────────────────────────────────────────────────────────────────

class MasterItemsSyncError(RuntimeError):
    """Raised on WebSocket or Engine errors during master-item operations."""

    def __init__(self, message: str, app_id: str = "") -> None:
        super().__init__(message)
        self.app_id = app_id


# ── Internal: read all master items from an open session ─────────────────────

async def _read_all_master_items(session: EngineSession) -> dict[str, list[dict]]:
    """Read dimensions, measures, and visualizations from the open app."""

    result: dict[str, list[dict]] = {
        "dimensions": [],
        "measures": [],
        "visualizations": [],
    }

    # ── Dimensions ──

    dim_list_handle = await session.create_session_object({
        "qInfo": {"qType": "DimensionList"},
        "qDimensionListDef": {"qType": "dimension"},
    })
    dim_layout = await session.get_layout(dim_list_handle)
    dim_items = dim_layout.get("qDimensionList", {}).get("qItems", [])
    logger.info("Found %d master dimensions", len(dim_items))

    for item in dim_items:
        qid = item.get("qInfo", {}).get("qId", "")
        try:
            _handle, props = await session.get_dimension(qid)
            result["dimensions"].append({
                "id": qid,
                "title": props.get("qMetaDef", {}).get("title", ""),
                "properties": props,
            })
        except Exception as exc:
            logger.warning("Skipping dimension %s: %s", qid, exc)

    # ── Measures ──

    meas_list_handle = await session.create_session_object({
        "qInfo": {"qType": "MeasureList"},
        "qMeasureListDef": {"qType": "measure"},
    })
    meas_layout = await session.get_layout(meas_list_handle)
    meas_items = meas_layout.get("qMeasureList", {}).get("qItems", [])
    logger.info("Found %d master measures", len(meas_items))

    for item in meas_items:
        qid = item.get("qInfo", {}).get("qId", "")
        try:
            _handle, props = await session.get_measure(qid)
            result["measures"].append({
                "id": qid,
                "title": props.get("qMetaDef", {}).get("title", ""),
                "properties": props,
            })
        except Exception as exc:
            logger.warning("Skipping measure %s: %s", qid, exc)

    # ── Visualizations (master objects) ──

    viz_list_handle = await session.create_session_object({
        "qInfo": {"qType": "masterobject"},
        "qAppObjectListDef": {
            "qType": "masterobject",
            "qData": {"title": "/qMetaDef/title", "description": "/qMetaDef/description"},
        },
    })
    viz_layout = await session.get_layout(viz_list_handle)
    viz_items = viz_layout.get("qAppObjectList", {}).get("qItems", [])
    logger.info("Found %d master visualizations", len(viz_items))

    for item in viz_items:
        qid = item.get("qInfo", {}).get("qId", "")
        try:
            _handle, props = await session.get_object(qid)
            result["visualizations"].append({
                "id": qid,
                "title": props.get("qMetaDef", {}).get("title", ""),
                "properties": props,
            })
        except Exception as exc:
            logger.warning("Skipping visualization %s: %s", qid, exc)

    return result


# ── Public: export ───────────────────────────────────────────────────────────

async def export_master_items(creds: QlikCredentials, app_id: str) -> dict:
    """Open a session to *app_id*, read all master items, return structured dict."""
    client = QlikEngineClient(creds)
    try:
        async with client.open_session(app_id) as session:
            items = await _read_all_master_items(session)
    except QlikEngineError as exc:
        raise MasterItemsSyncError(str(exc), app_id=app_id) from exc

    return {
        "app_id": app_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        **items,
    }


# ── Public: diff ─────────────────────────────────────────────────────────────

def _build_title_map(items: list[dict]) -> dict[str, dict]:
    """Build a case-insensitive title → item map. First occurrence wins on duplicate titles."""
    result: dict[str, dict] = {}
    for item in items:
        if not item.get("title"):
            continue
        key = item["title"].strip().lower()
        if key in result:
            logger.warning(
                "Duplicate master item title (case-insensitive) %r — keeping first, discarding id=%s",
                item["title"], item.get("id", "?"),
            )
        else:
            result[key] = item
    return result


def _strip_qinfo(p: dict) -> dict:
    """Shallow copy of props with qInfo removed (for visualization comparison)."""
    c = dict(p)
    c.pop("qInfo", None)
    return c


def _definitions_match(source_props: dict, target_props: dict, item_type: str) -> bool:
    """Check whether two items with the same title have identical definitions."""
    if item_type == "dimensions":
        s = source_props.get("qDim", {}).get("qFieldDefs", [])
        t = target_props.get("qDim", {}).get("qFieldDefs", [])
        return s == t
    if item_type == "measures":
        s = source_props.get("qMeasure", {}).get("qDef", "")
        t = target_props.get("qMeasure", {}).get("qDef", "")
        return s == t
    return _strip_qinfo(source_props) == _strip_qinfo(target_props)


async def diff_master_items(
    creds: QlikCredentials,
    source: dict,
    target_app_id: str,
) -> dict:
    """Compare *source* export against live master items in *target_app_id*."""
    client = QlikEngineClient(creds)
    try:
        async with client.open_session(target_app_id) as session:
            target_items = await _read_all_master_items(session)
    except QlikEngineError as exc:
        raise MasterItemsSyncError(str(exc), app_id=target_app_id) from exc

    result: dict[str, dict[str, list]] = {}

    for item_type in ("dimensions", "measures", "visualizations"):
        target_map = _build_title_map(target_items[item_type])
        new_items: list[dict] = []
        existing: list[dict] = []
        conflicts: list[dict] = []

        for src_item in source.get(item_type, []):
            key = (src_item.get("title") or "").strip().lower()
            if not key:
                new_items.append(src_item)
                continue
            tgt_item = target_map.get(key)
            if tgt_item is None:
                new_items.append(src_item)
            elif _definitions_match(
                src_item.get("properties", {}),
                tgt_item.get("properties", {}),
                item_type,
            ):
                existing.append(src_item)
            else:
                conflicts.append({"source": src_item, "target": tgt_item})

        result[item_type] = {"new": new_items, "existing": existing, "conflict": conflicts}

    return result


# ── Public: import ───────────────────────────────────────────────────────────

def _strip_source_id(props: dict) -> dict:
    """Return a copy of properties with qInfo.qId removed so the engine generates a new one."""
    props = copy.deepcopy(props)
    if "qInfo" in props:
        props["qInfo"].pop("qId", None)
    return props


async def import_master_items(
    creds: QlikCredentials,
    target_app_id: str,
    source: dict,
    options: Optional[dict] = None,
) -> dict:
    """Import master items from *source* into *target_app_id*."""
    opts = options or {}
    types: list[str] = opts.get("types", ["dimensions", "measures", "visualizations"])
    on_duplicate: str = opts.get("on_duplicate", "skip")
    dry_run: bool = opts.get("dry_run", False)

    counters = {
        "imported":    {t: 0 for t in ("dimensions", "measures", "visualizations")},
        "skipped":     {t: 0 for t in ("dimensions", "measures", "visualizations")},
        "overwritten": {t: 0 for t in ("dimensions", "measures", "visualizations")},
    }
    errors: list[dict] = []

    client = QlikEngineClient(creds)
    try:
        async with client.open_session(target_app_id) as session:
            target_items = await _read_all_master_items(session)

            for item_type in types:
                target_map = _build_title_map(target_items[item_type])

                for src_item in source.get(item_type, []):
                    title = (src_item.get("title") or "").strip()
                    key = title.lower()
                    src_props = src_item.get("properties", {})

                    try:
                        existing = target_map.get(key)

                        if existing is not None:
                            if on_duplicate == "skip":
                                counters["skipped"][item_type] += 1
                                logger.debug("Skip %s '%s' (exists)", item_type, title)
                                continue

                            if dry_run:
                                counters["overwritten"][item_type] += 1
                                continue

                            tgt_id = existing["id"]
                            if item_type == "dimensions":
                                handle, _old = await session.get_dimension(tgt_id)
                            elif item_type == "measures":
                                handle, _old = await session.get_measure(tgt_id)
                            else:
                                handle, _old = await session.get_object(tgt_id)

                            src_props.setdefault("qInfo", {})["qId"] = tgt_id
                            await session.set_properties(handle, src_props)
                            counters["overwritten"][item_type] += 1
                            logger.info("Overwritten %s '%s'", item_type, title)
                            continue

                        if dry_run:
                            counters["imported"][item_type] += 1
                            continue

                        clean_props = _strip_source_id(src_props)

                        if item_type == "dimensions":
                            await session.create_dimension(clean_props)
                        elif item_type == "measures":
                            await session.create_measure(clean_props)
                        else:
                            await session.create_object(clean_props)

                        counters["imported"][item_type] += 1
                        logger.info("Imported %s '%s'", item_type, title)

                    except Exception as exc:
                        errors.append({"type": item_type, "title": title, "error": str(exc)})
                        logger.warning("Error importing %s '%s': %s", item_type, title, exc)

            if not dry_run:
                await session.do_save()
                logger.info("DoSave completed for %s", target_app_id)

    except QlikEngineError as exc:
        raise MasterItemsSyncError(str(exc), app_id=target_app_id) from exc

    return {"dry_run": dry_run, **counters, "errors": errors}


__all__ = ["export_master_items", "diff_master_items", "import_master_items",
           "MasterItemsSyncError"]
