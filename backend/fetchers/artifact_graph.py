from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
import json

from shared.models import AppInfoRecord, EdgeRecord, GraphSnapshot, NodeRecord

from .qlik_normalizer import normalize_file, normalize_payload


class LineageArtifactLoader:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.skipped_files: Dict[str, str] = {}

    def lineage_files(self) -> List[Path]:
        if not self.data_dir.exists():
            return []
        return sorted(self.data_dir.glob("*.json"))

    def load_lineage_records(self, files: Iterable[Path]) -> List[Tuple[Dict, List[Dict], List[Dict]]]:
        records: List[Tuple[Dict, List[Dict], List[Dict]]] = []
        self.skipped_files = {}
        for path in files:
            try:
                records.append(normalize_file(path))
            except Exception as exc:
                self.skipped_files[path.name] = str(exc)
        return records


class GraphBuilder:
    def build(self, records: Iterable[Tuple[Dict, List[Dict], List[Dict]]], files_loaded: int) -> GraphSnapshot:
        nodes: Dict[str, NodeRecord] = {}
        edges: Dict[str, EdgeRecord] = {}
        out_adj: Dict[str, Set[str]] = {}
        in_adj: Dict[str, Set[str]] = {}
        apps: Dict[str, AppInfoRecord] = {}

        for app_info, canonical_nodes, canonical_edges in records:
            for node in canonical_nodes:
                self._merge_node(nodes, node)

            for edge in canonical_edges:
                self._add_edge(edges, out_adj, in_adj, edge)

            for edge in canonical_edges:
                self._ensure_node(nodes, edge["source"])
                self._ensure_node(nodes, edge["target"])

            root = self._detect_root(canonical_nodes, app_info.get("appName", ""))
            if root:
                app_info["rootNodeId"] = root
            self._merge_app_info(apps, app_info)

        return GraphSnapshot(
            nodes=nodes,
            edges=edges,
            out_adj=out_adj,
            in_adj=in_adj,
            apps=apps,
            files_loaded=files_loaded,
        )

    def _ensure_node(self, nodes: Dict[str, NodeRecord], node_id: str) -> None:
        if node_id in nodes:
            return
        nodes[node_id] = {
            "id": node_id,
            "label": node_id,
            "type": "other",
            "subtype": None,
            "group": None,
            "layer": "other",
            "meta": None,
        }

    def _new_edge_context(self, incoming: Dict[str, Any]) -> Dict[str, Any]:
        incoming = incoming or {}
        app_id = incoming.get("appId")
        app_name = incoming.get("appName")
        file_name = incoming.get("file")
        fetched_at = incoming.get("fetched_at")
        return {
            "appId": app_id,
            "appName": app_name,
            "file": file_name,
            "fetched_at": fetched_at,
            "appIds": [app_id] if app_id else [],
            "appNames": [app_name] if app_name else [],
            "files": [file_name] if file_name else [],
            "firstFetchedAt": fetched_at,
            "lastFetchedAt": fetched_at,
            "occurrences": 1,
        }

    def _append_unique(self, values: List[Any], candidate: Any) -> None:
        if candidate is None:
            return
        if candidate not in values:
            values.append(candidate)

    def _merge_edge_context(self, existing: Dict[str, Any], incoming: Dict[str, Any]) -> None:
        incoming = incoming or {}
        existing["occurrences"] = int(existing.get("occurrences", 1)) + 1
        self._append_unique(existing.setdefault("appIds", []), incoming.get("appId"))
        self._append_unique(existing.setdefault("appNames", []), incoming.get("appName"))
        self._append_unique(existing.setdefault("files", []), incoming.get("file"))

        if not existing.get("appId") and incoming.get("appId"):
            existing["appId"] = incoming.get("appId")
        if not existing.get("appName") and incoming.get("appName"):
            existing["appName"] = incoming.get("appName")
        if not existing.get("file") and incoming.get("file"):
            existing["file"] = incoming.get("file")

        candidate = incoming.get("fetched_at")
        first_seen = existing.get("firstFetchedAt")
        last_seen = existing.get("lastFetchedAt")

        if candidate:
            if not first_seen or self._is_newer(first_seen, candidate):
                existing["firstFetchedAt"] = candidate
            if not last_seen or self._is_newer(candidate, last_seen):
                existing["lastFetchedAt"] = candidate
                existing["fetched_at"] = candidate

    def _add_edge(
        self,
        edges: Dict[str, EdgeRecord],
        out_adj: Dict[str, Set[str]],
        in_adj: Dict[str, Set[str]],
        edge: Dict[str, Any],
    ) -> None:
        edge_id = edge["id"]
        existing = edges.get(edge_id)
        if not existing:
            materialized: EdgeRecord = {
                "id": edge["id"],
                "source": edge["source"],
                "target": edge["target"],
                "relation": edge["relation"],
                "context": self._new_edge_context(edge.get("context") or {}),
            }
            edges[edge_id] = materialized
        else:
            self._merge_edge_context(existing.setdefault("context", {}), edge.get("context") or {})

        out_adj.setdefault(edge["source"], set()).add(edge_id)
        in_adj.setdefault(edge["target"], set()).add(edge_id)

    def _merge_node(self, nodes: Dict[str, NodeRecord], node: Dict[str, Any]) -> None:
        node_id = node["id"]
        existing = nodes.get(node_id)
        if not existing:
            nodes[node_id] = {
                "id": node["id"],
                "label": node.get("label") or node_id,
                "type": node.get("type") or "other",
                "subtype": node.get("subtype"),
                "group": node.get("group"),
                "layer": node.get("layer") or "other",
                "meta": node.get("meta"),
            }
            return

        if self._is_better_label(existing.get("label"), node.get("label"), node_id):
            existing["label"] = node.get("label")

        if existing.get("type") == "other" and node.get("type") != "other":
            existing["type"] = node.get("type")

        if not existing.get("layer") or existing.get("layer") == "other":
            if node.get("layer"):
                existing["layer"] = node.get("layer")

        if not existing.get("group") and node.get("group"):
            existing["group"] = node.get("group")

        if not existing.get("subtype") and node.get("subtype"):
            existing["subtype"] = node.get("subtype")

        existing_meta = existing.get("meta") or {}
        incoming_meta = node.get("meta") or {}
        for key, value in incoming_meta.items():
            if key not in existing_meta or existing_meta[key] is None:
                existing_meta[key] = value
        existing["meta"] = existing_meta or None

    def _is_better_label(self, current: Optional[str], candidate: Optional[str], node_id: str) -> bool:
        if not candidate or candidate == node_id:
            return False
        if not current or current == node_id:
            return True
        return len(candidate) > len(current)

    def _detect_root(self, nodes: List[Dict], app_name: str) -> Optional[str]:
        for node in nodes:
            meta = node.get("meta") or {}
            if meta.get("type") == "DA_APP":
                return node["id"]
        if app_name:
            name_l = app_name.lower()
            for node in nodes:
                if node.get("type") == "app" and name_l in (node.get("label") or "").lower():
                    return node["id"]
        for node in nodes:
            if node["id"].startswith("qri:app:sense://"):
                return node["id"]
        return nodes[0]["id"] if nodes else None

    def _merge_app_info(self, apps: Dict[str, AppInfoRecord], app_info: Dict[str, Any]) -> None:
        app_id = app_info.get("appId") or ""
        if not app_id:
            return

        existing = apps.get(app_id)
        if not existing:
            apps[app_id] = app_info
            return

        if self._is_newer(app_info.get("fetched_at"), existing.get("fetched_at")):
            apps[app_id] = app_info

    def _is_newer(self, candidate: Optional[str], current: Optional[str]) -> bool:
        if not candidate:
            return False
        if not current:
            return True
        try:
            candidate_dt = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            current_dt = datetime.fromisoformat(current.replace("Z", "+00:00"))
            return candidate_dt > current_dt
        except ValueError:
            return candidate > current


def build_snapshot_from_lineage_artifacts(data_dir: Path) -> tuple[GraphSnapshot, dict[str, str]]:
    loader = LineageArtifactLoader(data_dir=data_dir)
    files = loader.lineage_files()
    records = loader.load_lineage_records(files)
    snapshot = GraphBuilder().build(records, files_loaded=len(files))
    return snapshot, dict(loader.skipped_files)


def build_snapshot_from_payloads(payloads: list[dict[str, Any]]) -> tuple[GraphSnapshot, dict[str, str]]:
    records: list[Tuple[Dict, List[Dict], List[Dict]]] = []
    skipped: dict[str, str] = {}
    for idx, payload in enumerate(payloads, start=1):
        file_name = str(payload.get("_artifactFileName") or payload.get("fileName") or f"in-memory-{idx}.json")
        try:
            records.append(normalize_payload(payload, file_name=file_name))
        except Exception as exc:
            skipped[file_name] = str(exc)
    snapshot = GraphBuilder().build(records, files_loaded=0)
    return snapshot, skipped
