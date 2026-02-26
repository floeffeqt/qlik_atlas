from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    LineageEdge,
    LineageNode,
    QlikApp,
    QlikAppScript,
    QlikAppUsage,
    QlikDataConnection,
    QlikSpace,
)
from fetchers.heuristics import dead_ends, never_referenced, orphan_outputs
from fetchers.subgraph import bfs_subgraph
from shared.models import Edge, GraphResponse, GraphSnapshot, InventoryResponse, Node, OrphansReport


def _dt_key(value: Optional[datetime]) -> tuple[int, str]:
    if not value:
        return (0, "")
    return (1, value.isoformat())


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _node_record_from_payload(node_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(payload.get("id") or node_id),
        "label": str(payload.get("label") or payload.get("id") or node_id),
        "type": str(payload.get("type") or "other"),
        "subtype": payload.get("subtype"),
        "group": payload.get("group"),
        "layer": str(payload.get("layer") or "other"),
        "meta": payload.get("meta") if isinstance(payload.get("meta"), dict) else None,
    }


def _edge_record_from_payload(edge_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(payload.get("id") or edge_id),
        "source": str(payload.get("source") or ""),
        "target": str(payload.get("target") or ""),
        "relation": str(payload.get("relation") or "OTHER"),
        "context": payload.get("context") if isinstance(payload.get("context"), dict) else None,
    }


def _space_name_from_row(row: QlikSpace) -> str | None:
    if getattr(row, "space_name", None):
        return str(row.space_name)
    payload = _safe_dict(row.data)
    for key in ("spaceName", "spacename", "name"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _space_id_from_row(row: QlikSpace) -> str | None:
    candidate = getattr(row, "space_id_payload", None) or getattr(row, "space_id", None)
    if candidate is not None and str(candidate).strip():
        return str(candidate).strip()
    payload = _safe_dict(row.data)
    for key in ("spaceId", "spaceID", "id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _app_name_from_row(row: QlikApp) -> str | None:
    if getattr(row, "app_name", None):
        return str(row.app_name)
    if getattr(row, "name_value", None):
        return str(row.name_value)
    payload = _safe_dict(row.data)
    for key in ("appName", "name"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _app_space_id_from_row(row: QlikApp) -> str | None:
    candidate = getattr(row, "space_id_payload", None) or getattr(row, "space_id", None)
    if candidate is not None and str(candidate).strip():
        return str(candidate).strip()
    payload = _safe_dict(row.data)
    value = payload.get("spaceId")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _app_lookup_keys_for_app_id(app_id: str) -> list[str]:
    value = str(app_id or "").strip()
    if not value:
        return []
    keys = [value]
    if not value.startswith("qri:app:sense://"):
        keys.append(f"qri:app:sense://{value}")
    if value.startswith("qri:app:sense://"):
        bare = value.split("://", 1)[1].strip()
        if bare:
            keys.append(bare)
    # preserve order, remove duplicates
    return list(dict.fromkeys(keys))


def _node_app_lookup_candidates(row: LineageNode, record: dict[str, Any]) -> list[str]:
    meta = record.get("meta") or {}
    raw_candidates: list[Any] = [
        getattr(row, "app_id", None),
        meta.get("appId") if isinstance(meta, dict) else None,
        meta.get("app_id") if isinstance(meta, dict) else None,
    ]
    if record.get("type") == "app":
        raw_candidates.extend([
            meta.get("id") if isinstance(meta, dict) else None,
            record.get("id"),
        ])
    keys: list[str] = []
    for raw in raw_candidates:
        if raw is None:
            continue
        for key in _app_lookup_keys_for_app_id(str(raw)):
            if key and key not in keys:
                keys.append(key)
    return keys


def _build_snapshot_from_rows(
    node_rows: Iterable[LineageNode],
    edge_rows: Iterable[LineageEdge],
    *,
    app_info_by_project_and_app: dict[tuple[int, str], dict[str, Any]] | None = None,
) -> GraphSnapshot:
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}
    out_adj: dict[str, set[str]] = {}
    in_adj: dict[str, set[str]] = {}

    app_info_by_project_and_app = app_info_by_project_and_app or {}

    for row in node_rows:
        payload = _safe_dict(row.data)
        record = _node_record_from_payload(str(row.node_id), payload)
        app_info = None
        app_lookup_key = None
        for candidate in _node_app_lookup_candidates(row, record):
            app_info = app_info_by_project_and_app.get((int(row.project_id), candidate))
            if app_info:
                app_lookup_key = candidate
                break
        if app_info or app_lookup_key:
            meta = dict(record.get("meta") or {})
            if app_info:
                canonical_app_id = str(app_info.get("appId") or "")
                if not record.get("group") and canonical_app_id:
                    record["group"] = canonical_app_id
                if canonical_app_id:
                    meta.setdefault("appId", canonical_app_id)
                app_name = app_info.get("appName")
                space_id = app_info.get("spaceId")
                space_name = app_info.get("spaceName")
                if app_name:
                    meta.setdefault("appName", str(app_name))
                if space_id:
                    meta.setdefault("spaceId", str(space_id))
                if space_name:
                    meta.setdefault("spaceName", str(space_name))
            elif app_lookup_key:
                meta.setdefault("appId", str(app_lookup_key))
            record["meta"] = meta
        nodes[record["id"]] = record

    for row in edge_rows:
        payload = _safe_dict(row.data)
        record = _edge_record_from_payload(str(row.edge_id), payload)
        if not record["source"] or not record["target"]:
            continue
        edges[record["id"]] = record
        out_adj.setdefault(record["source"], set()).add(record["id"])
        in_adj.setdefault(record["target"], set()).add(record["id"])
        if record["source"] not in nodes:
            nodes[record["source"]] = _node_record_from_payload(record["source"], {"id": record["source"]})
        if record["target"] not in nodes:
            nodes[record["target"]] = _node_record_from_payload(record["target"], {"id": record["target"]})

    return GraphSnapshot(nodes=nodes, edges=edges, out_adj=out_adj, in_adj=in_adj, apps={}, files_loaded=0)


def _graph_response_from_snapshot(snapshot: GraphSnapshot) -> GraphResponse:
    nodes: list[Node] = []
    for payload in snapshot.nodes.values():
        try:
            nodes.append(Node(**payload))
        except Exception:
            continue
    edges: list[Edge] = []
    for payload in snapshot.edges.values():
        try:
            edges.append(Edge(**payload))
        except Exception:
            continue
    return GraphResponse(nodes=nodes, edges=edges)


async def load_graph_snapshot(session: AsyncSession, *, project_id: int | None = None) -> GraphSnapshot:
    node_stmt = select(LineageNode)
    edge_stmt = select(LineageEdge)
    if project_id is not None:
        node_stmt = node_stmt.where(LineageNode.project_id == project_id)
        edge_stmt = edge_stmt.where(LineageEdge.project_id == project_id)

    node_rows = (await session.execute(node_stmt)).scalars().all()
    edge_rows = (await session.execute(edge_stmt)).scalars().all()
    project_ids = sorted({int(r.project_id) for r in node_rows} | {int(r.project_id) for r in edge_rows})

    app_info_by_project_and_app: dict[tuple[int, str], dict[str, Any]] = {}
    if project_ids:
        apps_rows = (
            await session.execute(select(QlikApp).where(QlikApp.project_id.in_(project_ids)))
        ).scalars().all()
        spaces_rows = (
            await session.execute(select(QlikSpace).where(QlikSpace.project_id.in_(project_ids)))
        ).scalars().all()
        space_name_by_project_and_space: dict[tuple[int, str], str] = {}
        for row in spaces_rows:
            space_id_val = _space_id_from_row(row)
            space_name_val = _space_name_from_row(row)
            if space_name_val:
                if space_id_val:
                    space_name_by_project_and_space[(int(row.project_id), space_id_val)] = space_name_val
                if getattr(row, "space_id", None):
                    space_name_by_project_and_space[(int(row.project_id), str(row.space_id))] = space_name_val

        for row in apps_rows:
            payload = _safe_dict(row.data)
            app_id_val = str(row.app_id)
            app_name_val = _app_name_from_row(row) or app_id_val
            space_id_val = _app_space_id_from_row(row)
            space_id_str = str(space_id_val) if space_id_val else None
            app_info = {
                "appId": app_id_val,
                "appName": str(app_name_val),
                "spaceId": space_id_str,
                "spaceName": (
                    space_name_by_project_and_space.get((int(row.project_id), space_id_str))
                    if space_id_str else None
                ),
            }
            for lookup_key in _app_lookup_keys_for_app_id(app_id_val):
                app_info_by_project_and_app[(int(row.project_id), lookup_key)] = app_info

    return _build_snapshot_from_rows(
        node_rows,
        edge_rows,
        app_info_by_project_and_app=app_info_by_project_and_app,
    )


async def load_graph_response(session: AsyncSession, *, project_id: int | None = None) -> GraphResponse:
    snapshot = await load_graph_snapshot(session, project_id=project_id)
    return _graph_response_from_snapshot(snapshot)


async def load_inventory(session: AsyncSession) -> InventoryResponse:
    apps_rows = (await session.execute(select(QlikApp))).scalars().all()
    spaces_rows = (await session.execute(select(QlikSpace))).scalars().all()
    nodes_count = int((await session.execute(select(sa_func.count()).select_from(LineageNode))).scalar() or 0)
    edges_count = int((await session.execute(select(sa_func.count()).select_from(LineageEdge))).scalar() or 0)

    space_names: dict[tuple[int, str], str] = {}
    for row in spaces_rows:
        space_name = _space_name_from_row(row)
        if isinstance(space_name, str) and space_name:
            if getattr(row, "space_id", None):
                space_names[(int(row.project_id), str(row.space_id))] = space_name
            space_id_val = _space_id_from_row(row)
            if space_id_val:
                space_names[(int(row.project_id), str(space_id_val))] = space_name

    items: list[dict[str, Any]] = []
    for row in apps_rows:
        payload = _safe_dict(row.data)
        app_id = str(row.app_id)
        app_name = _app_name_from_row(row) or app_id
        space_id = _app_space_id_from_row(row)
        status_raw = getattr(row, "status", None)
        if status_raw is None:
            status_raw = payload.get("status")
        try:
            status_val = int(status_raw) if status_raw is not None else None
        except Exception:
            status_val = None

        item = {
            "appId": app_id,
            "appName": str(app_name),
            "spaceId": str(space_id) if space_id else None,
            "spaceName": None,
            "rootNodeId": getattr(row, "root_node_id", None) or payload.get("rootNodeId"),
            "nodesCount": int((getattr(row, "nodes_count", None) if getattr(row, "nodes_count", None) is not None else payload.get("nodesCount")) or 0),
            "edgesCount": int((getattr(row, "edges_count", None) if getattr(row, "edges_count", None) is not None else payload.get("edgesCount")) or 0),
            "fetched_at": payload.get("fetched_at") or (row.fetched_at.isoformat() if row.fetched_at else None),
            "status": status_val,
            "fileName": getattr(row, "file_name", None) or payload.get("fileName"),
        }
        if item["spaceId"]:
            item["spaceName"] = space_names.get((int(row.project_id), str(item["spaceId"])))
        items.append(item)

    items.sort(key=lambda x: ((x.get("appName") or "").lower(), x.get("appId") or ""))
    totals = {"files": 0, "apps": len(items), "nodes": nodes_count, "edges": edges_count}
    return InventoryResponse(apps=items, totals=totals)


async def load_spaces_payload(session: AsyncSession) -> dict[str, Any]:
    rows = (await session.execute(select(QlikSpace))).scalars().all()
    seen: set[tuple[int, str]] = set()
    spaces: list[dict[str, Any]] = []
    for row in rows:
        key = (int(row.project_id), str(row.space_id))
        if key in seen:
            continue
        seen.add(key)
        payload = _safe_dict(row.data)
        if "spaceId" not in payload and getattr(row, "space_id_payload", None):
            payload["spaceId"] = str(row.space_id_payload)
        if "spaceId" not in payload:
            payload["spaceId"] = str(row.space_id)
        if "spaceName" not in payload and getattr(row, "space_name", None):
            payload["spaceName"] = str(row.space_name)
        if "type" not in payload and getattr(row, "space_type", None):
            payload["type"] = str(row.space_type)
        if "ownerId" not in payload and getattr(row, "owner_id", None):
            payload["ownerId"] = str(row.owner_id)
        if "tenantId" not in payload and getattr(row, "tenant_id", None):
            payload["tenantId"] = str(row.tenant_id)
        if "createdAt" not in payload and getattr(row, "created_at_source", None):
            payload["createdAt"] = str(row.created_at_source)
        if "updatedAt" not in payload and getattr(row, "updated_at_source", None):
            payload["updatedAt"] = str(row.updated_at_source)
        spaces.append(payload)
    spaces.sort(key=lambda x: (str(x.get("spaceName") or x.get("name") or "").lower(), str(x.get("spaceId") or "")))
    return {"count": len(spaces), "spaces": spaces}


async def load_data_connections_payload(session: AsyncSession) -> dict[str, Any]:
    rows = (await session.execute(select(QlikDataConnection))).scalars().all()
    data: list[dict[str, Any]] = []
    for row in rows:
        payload = _safe_dict(row.data)
        if "id" not in payload:
            payload["id"] = str(row.connection_id)
        data.append(payload)
    data.sort(key=lambda x: (str(x.get("qName") or x.get("name") or "").lower(), str(x.get("id") or "")))
    return {"count": len(data), "data": data}


def _pick_latest_row(rows: list[Any], *, attr_names: tuple[str, ...] = ("generated_at", "fetched_at")) -> Any | None:
    if not rows:
        return None

    def key(row: Any) -> tuple[tuple[int, str], ...]:
        return tuple(_dt_key(getattr(row, attr, None)) for attr in attr_names)

    return max(rows, key=key)


async def load_app_usage_payload(session: AsyncSession, app_id: str) -> dict[str, Any]:
    rows = (await session.execute(select(QlikAppUsage).where(QlikAppUsage.app_id == app_id))).scalars().all()
    row = _pick_latest_row(rows, attr_names=("generated_at",))
    if not row:
        raise KeyError("app usage not found")
    payload = _safe_dict(row.data)
    payload.setdefault("appId", app_id)
    if getattr(row, "app_id_payload", None):
        payload.setdefault("appId", str(row.app_id_payload))
    if getattr(row, "app_name", None):
        payload.setdefault("appName", str(row.app_name))
    if getattr(row, "window_days", None) is not None:
        payload.setdefault("windowDays", int(row.window_days))
    if getattr(row, "generated_at_payload", None):
        payload.setdefault("generatedAt", str(row.generated_at_payload))
    elif getattr(row, "generated_at", None):
        payload.setdefault("generatedAt", row.generated_at.isoformat())
    if getattr(row, "artifact_file_name", None):
        payload.setdefault("_artifactFileName", str(row.artifact_file_name))
    if isinstance(getattr(row, "connections", None), list):
        payload.setdefault("connections", list(row.connections))

    usage_payload = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    if not isinstance(payload.get("usage"), dict):
        payload["usage"] = usage_payload
    if getattr(row, "usage_reloads", None) is not None:
        usage_payload.setdefault("reloads", int(row.usage_reloads))
    if getattr(row, "usage_app_opens", None) is not None:
        usage_payload.setdefault("appOpens", int(row.usage_app_opens))
    if getattr(row, "usage_sheet_views", None) is not None:
        usage_payload.setdefault("sheetViews", int(row.usage_sheet_views))
    if getattr(row, "usage_unique_users", None) is not None:
        usage_payload.setdefault("uniqueUsers", int(row.usage_unique_users))
    if getattr(row, "usage_last_reload_at", None):
        usage_payload.setdefault("lastReloadAt", str(row.usage_last_reload_at))
    if getattr(row, "usage_last_viewed_at", None):
        usage_payload.setdefault("lastViewedAt", str(row.usage_last_viewed_at))
    if getattr(row, "usage_classification", None):
        usage_payload.setdefault("classification", str(row.usage_classification))
    return payload


async def load_app_script_payload(session: AsyncSession, app_id: str) -> dict[str, Any]:
    rows = (await session.execute(select(QlikAppScript).where(QlikAppScript.app_id == app_id))).scalars().all()
    row = _pick_latest_row(rows, attr_names=("fetched_at",))
    if not row:
        raise KeyError("app script not found")
    payload = _safe_dict(row.data)
    payload.setdefault("appId", app_id)
    payload.setdefault("script", row.script)
    if row.file_name:
        payload.setdefault("fileName", row.file_name)
    if row.source:
        payload.setdefault("source", row.source)
    return payload


def _detect_app_root(snapshot: GraphSnapshot, *, app_id: str, app_name: str | None = None) -> str | None:
    app_name_l = (app_name or "").lower()

    for node_id, node in snapshot.nodes.items():
        meta = node.get("meta") or {}
        meta_id = meta.get("id")
        original_id = meta.get("original_id")
        if meta_id == app_id or original_id == app_id:
            if node.get("type") == "app":
                return node_id

    if app_name_l:
        for node_id, node in snapshot.nodes.items():
            if node.get("type") == "app" and app_name_l in str(node.get("label") or "").lower():
                return node_id

    candidate_ids: list[str] = []
    for edge in snapshot.edges.values():
        context = edge.get("context") or {}
        app_ids = context.get("appIds") if isinstance(context.get("appIds"), list) else []
        if context.get("appId") == app_id or app_id in app_ids:
            for node_id in (edge.get("source"), edge.get("target")):
                if not node_id or node_id in candidate_ids:
                    continue
                if snapshot.nodes.get(node_id, {}).get("type") == "app":
                    return node_id
                candidate_ids.append(str(node_id))

    return candidate_ids[0] if candidate_ids else None


async def load_app_subgraph(session: AsyncSession, app_id: str, *, depth: int) -> GraphResponse:
    app_rows = (await session.execute(select(QlikApp).where(QlikApp.app_id == app_id))).scalars().all()
    app_row = _pick_latest_row(app_rows, attr_names=("fetched_at",))
    if not app_row:
        raise KeyError("app not found")

    app_payload = _safe_dict(app_row.data)
    root_node_id = getattr(app_row, "root_node_id", None) or app_payload.get("rootNodeId")
    snapshot = await load_graph_snapshot(session, project_id=int(app_row.project_id))
    if not root_node_id:
        root_node_id = _detect_app_root(
            snapshot,
            app_id=app_id,
            app_name=str(_app_name_from_row(app_row) or ""),
        )
    if not root_node_id:
        raise KeyError("app root node not found")

    node_ids, edge_ids = bfs_subgraph(snapshot, str(root_node_id), "both", depth)
    sub_snapshot = GraphSnapshot(
        nodes={nid: snapshot.nodes[nid] for nid in node_ids if nid in snapshot.nodes},
        edges={eid: snapshot.edges[eid] for eid in edge_ids if eid in snapshot.edges},
        out_adj={},
        in_adj={},
        apps={},
        files_loaded=0,
    )
    return _graph_response_from_snapshot(sub_snapshot)


async def load_node_subgraph(session: AsyncSession, node_id: str, *, direction: str, depth: int) -> GraphResponse:
    snapshot = await load_graph_snapshot(session)
    node_ids, edge_ids = bfs_subgraph(snapshot, node_id, direction, depth)
    sub_snapshot = GraphSnapshot(
        nodes={nid: snapshot.nodes[nid] for nid in node_ids if nid in snapshot.nodes},
        edges={eid: snapshot.edges[eid] for eid in edge_ids if eid in snapshot.edges},
        out_adj={},
        in_adj={},
        apps={},
        files_loaded=0,
    )
    return _graph_response_from_snapshot(sub_snapshot)


async def load_orphans_report(session: AsyncSession) -> OrphansReport:
    snapshot = await load_graph_snapshot(session)
    def _safe_nodes(ids: list[str]) -> list[Node]:
        out: list[Node] = []
        for nid in ids:
            if nid not in snapshot.nodes:
                continue
            try:
                out.append(Node(**snapshot.nodes[nid]))
            except Exception:
                continue
        return out

    return OrphansReport(
        orphanOutputs=_safe_nodes(orphan_outputs(snapshot)),
        deadEnds=_safe_nodes(dead_ends(snapshot)),
        neverReferenced=_safe_nodes(never_referenced(snapshot)),
    )
