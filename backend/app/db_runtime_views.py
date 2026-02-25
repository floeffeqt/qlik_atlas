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


def _build_snapshot_from_rows(
    node_rows: Iterable[LineageNode],
    edge_rows: Iterable[LineageEdge],
) -> GraphSnapshot:
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}
    out_adj: dict[str, set[str]] = {}
    in_adj: dict[str, set[str]] = {}

    for row in node_rows:
        payload = _safe_dict(row.data)
        record = _node_record_from_payload(str(row.node_id), payload)
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
    return _build_snapshot_from_rows(node_rows, edge_rows)


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
        payload = _safe_dict(row.data)
        space_name = payload.get("spaceName") or payload.get("name")
        if isinstance(space_name, str) and space_name:
            space_names[(int(row.project_id), str(row.space_id))] = space_name

    items: list[dict[str, Any]] = []
    for row in apps_rows:
        payload = _safe_dict(row.data)
        app_id = str(row.app_id)
        app_name = payload.get("appName") or payload.get("name") or app_id
        space_id = payload.get("spaceId") or row.space_id
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
            "rootNodeId": payload.get("rootNodeId"),
            "nodesCount": int(payload.get("nodesCount") or 0),
            "edgesCount": int(payload.get("edgesCount") or 0),
            "fetched_at": payload.get("fetched_at") or (row.fetched_at.isoformat() if row.fetched_at else None),
            "status": status_val,
            "fileName": payload.get("fileName"),
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
        if "spaceId" not in payload:
            payload["spaceId"] = str(row.space_id)
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
    root_node_id = app_payload.get("rootNodeId")
    snapshot = await load_graph_snapshot(session, project_id=int(app_row.project_id))
    if not root_node_id:
        root_node_id = _detect_app_root(
            snapshot,
            app_id=app_id,
            app_name=str(app_payload.get("appName") or app_payload.get("name") or ""),
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
