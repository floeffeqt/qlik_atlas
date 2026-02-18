import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .qri_heuristics import normalize_qri, derive_type_group_layer, infer_group_from_label


def map_relation(relation: str) -> str:
    rel = (relation or "OTHER").upper()
    if rel in {"LOAD", "STORE", "DEPENDS"}:
        return rel
    return "OTHER"


def build_semantic_edge_id(source: str, target: str, relation: str, app_id: str) -> str:
    raw = f"{source}|{target}|{relation}|{app_id}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def build_node(qri_key: str, node_obj: Dict, app: Dict) -> Dict:
    node_obj = node_obj or {}
    metadata = node_obj.get("metadata", {}) or {}
    label = node_obj.get("label") or metadata.get("label") or qri_key
    raw_id = metadata.get("id") or qri_key
    norm_id, original_id = normalize_qri(raw_id)

    hints = derive_type_group_layer(norm_id, label, metadata)
    node_type = hints.get("type")
    layer = hints.get("layer")
    group = hints.get("group")

    meta_type = metadata.get("type")
    subtype = metadata.get("subtype")

    if meta_type == "DA_APP":
        node_type = "app"
        layer = "app"
    if meta_type == "DATASET" and node_type == "other":
        node_type = "dataset"
        layer = "transform"
    if subtype == "TABLE":
        if node_type in {"db", "table", "other"} or norm_id.startswith("qri:db:"):
            node_type = "table"
            layer = layer or "db"

    if node_type == "app" and app.get("spaceId"):
        group = app.get("spaceId")

    if not group:
        group = infer_group_from_label(label)

    meta = dict(metadata) if metadata else {}
    if original_id and original_id != norm_id:
        meta.setdefault("original_id", original_id)

    return {
        "id": norm_id,
        "label": label or norm_id,
        "type": node_type or "other",
        "subtype": subtype,
        "group": group,
        "layer": layer or "other",
        "meta": meta or None,
    }


def build_edge(
    edge: Dict,
    app_id: str,
    app_name: str,
    fetched_at: Optional[str],
    file_name: str,
) -> Optional[Dict]:
    edge = edge or {}
    source = normalize_qri(edge.get("source", ""))[0]
    target = normalize_qri(edge.get("target", ""))[0]
    if not source or not target:
        return None
    relation = map_relation(edge.get("relation"))
    edge_id = build_semantic_edge_id(source, target, relation, app_id)
    context = {
        "appId": app_id,
        "appName": app_name,
        "file": file_name,
        "fetched_at": fetched_at,
    }
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "relation": relation,
        "context": context,
    }


def normalize_file(path: Path) -> Tuple[Dict, List[Dict], List[Dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("lineage artifact must be a JSON object")

    app = data.get("app", {}) or {}
    app_id = app.get("id") or ""
    app_name = app.get("name") or ""
    space_id = app.get("spaceId")
    fetched_at = data.get("fetched_at")
    status = data.get("status")
    file_name = path.name

    graph: Dict[str, Any] = {}
    raw_payload = data.get("raw")
    if isinstance(raw_payload, dict):
        raw_graph = raw_payload.get("graph")
        if isinstance(raw_graph, dict):
            graph = raw_graph
        elif isinstance(raw_payload.get("nodes"), dict) or isinstance(raw_payload.get("edges"), list):
            graph = raw_payload

    nodes_dict = graph.get("nodes", {}) or {}
    edges_list = graph.get("edges", []) or []
    if not isinstance(nodes_dict, dict):
        nodes_dict = {}
    if not isinstance(edges_list, list):
        edges_list = []

    canonical_nodes = [build_node(k, v, app) for k, v in nodes_dict.items()]
    canonical_edges: List[Dict] = []
    for edge in edges_list:
        canonical = build_edge(edge, app_id, app_name, fetched_at, file_name)
        if canonical:
            canonical_edges.append(canonical)

    app_info = {
        "appId": app_id,
        "appName": app_name,
        "spaceId": space_id,
        "fetched_at": fetched_at,
        "status": status,
        "fileName": file_name,
        "rootNodeId": None,
        "nodesCount": len(canonical_nodes),
        "edgesCount": len(canonical_edges),
    }
    return app_info, canonical_nodes, canonical_edges
