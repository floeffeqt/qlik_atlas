from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
import json

from shared.models import AppInfoRecord, EdgeRecord, GraphSnapshot, NodeRecord

from .heuristics import dead_ends, never_referenced, orphan_outputs
from .qlik_normalizer import normalize_file
from .subgraph import bfs_subgraph


class LineageArtifactLoader:
    def __init__(
        self,
        data_dir: Path,
        spaces_file: Optional[Path] = None,
        usage_dir: Optional[Path] = None,
        scripts_dir: Optional[Path] = None,
        data_connections_file: Optional[Path] = None,
    ):
        self.data_dir = Path(data_dir)
        self.spaces_file = spaces_file
        self.usage_dir = Path(usage_dir) if usage_dir else None
        self.scripts_dir = Path(scripts_dir) if scripts_dir else None
        self.data_connections_file = Path(data_connections_file) if data_connections_file else None
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

    def _load_json_file(self, path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    def _find_app_artifact_file(
        self,
        directory: Optional[Path],
        app_id: str,
        suffixes: List[str],
    ) -> Optional[Path]:
        if not directory or not directory.exists() or not directory.is_dir():
            return None

        for suffix in suffixes:
            exact = directory / f"{app_id}{suffix}"
            if exact.exists() and exact.is_file():
                return exact

        for suffix in suffixes:
            matches = sorted(directory.glob(f"*__{app_id}{suffix}"))
            if matches:
                return matches[-1]
        return None

    def get_data_connections(self) -> Dict[str, Any]:
        candidates: List[Path] = []
        if self.data_connections_file:
            candidates.append(self.data_connections_file)
        candidates.append(self.data_dir / "tenant_data_connections.json")
        candidates.append(self.data_dir.parent / "lineage" / "tenant_data_connections.json")

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                payload = self._load_json_file(candidate)
                if isinstance(payload, dict):
                    return payload
                break
        raise FileNotFoundError("data connections artifact not found")

    def get_app_usage(self, app_id: str) -> Dict[str, Any]:
        usage_file = self._find_app_artifact_file(self.usage_dir, app_id, [".json"])
        if not usage_file:
            raise FileNotFoundError("usage artifact not found")

        payload = self._load_json_file(usage_file)
        if not isinstance(payload, dict):
            raise ValueError("usage artifact is invalid")
        payload.setdefault("appId", app_id)
        payload.setdefault("fileName", usage_file.name)
        return payload

    def get_app_script(self, app_id: str) -> Dict[str, Any]:
        script_file = self._find_app_artifact_file(self.scripts_dir, app_id, [".qvs", ".txt", ".json"])
        if not script_file:
            raise FileNotFoundError("script artifact not found")

        if script_file.suffix.lower() == ".json":
            payload = self._load_json_file(script_file)
            if not isinstance(payload, dict):
                raise ValueError("script artifact is invalid")
            script_text = (
                payload.get("script")
                or payload.get("loadScript")
                or payload.get("load_script")
                or payload.get("text")
            )
            if not isinstance(script_text, str):
                raise ValueError("script artifact is missing script text")
            return {
                "appId": app_id,
                "script": script_text,
                "fileName": script_file.name,
                "source": "json",
            }

        script_text = script_file.read_text(encoding="utf-8")
        return {
            "appId": app_id,
            "script": script_text,
            "fileName": script_file.name,
            "source": script_file.suffix.lower().lstrip("."),
        }

    def load_space_names(self) -> Dict[str, str]:
        if not self.spaces_file or not self.spaces_file.exists():
            return {}
        try:
            data = json.loads(self.spaces_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

        mapping: Dict[str, str] = {}
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, str):
                    mapping[str(key)] = value
        elif isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                space_id = item.get("spaceId") or item.get("id")
                space_name = item.get("spaceName") or item.get("name")
                if space_id and space_name:
                    mapping[str(space_id)] = str(space_name)
        return mapping


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


class GraphStore:
    def __init__(
        self,
        data_dir: Path,
        spaces_file: Optional[Path] = None,
        usage_dir: Optional[Path] = None,
        scripts_dir: Optional[Path] = None,
        data_connections_file: Optional[Path] = None,
    ):
        self.loader = LineageArtifactLoader(
            data_dir=data_dir,
            spaces_file=spaces_file,
            usage_dir=usage_dir,
            scripts_dir=scripts_dir,
            data_connections_file=data_connections_file,
        )
        self.builder = GraphBuilder()
        self.snapshot: GraphSnapshot = GraphSnapshot.empty()

        self.nodes: Dict[str, NodeRecord] = {}
        self.edges: Dict[str, EdgeRecord] = {}
        self.out_adj: Dict[str, Set[str]] = {}
        self.in_adj: Dict[str, Set[str]] = {}
        self.apps: Dict[str, AppInfoRecord] = {}
        self.files_loaded = 0
        self.space_names: Dict[str, str] = {}
        self.skipped_lineage_files: Dict[str, str] = {}

        self._apply_snapshot(self.snapshot)

    def _apply_snapshot(self, snapshot: GraphSnapshot) -> None:
        self.snapshot = snapshot
        self.nodes = snapshot.nodes
        self.edges = snapshot.edges
        self.out_adj = snapshot.out_adj
        self.in_adj = snapshot.in_adj
        self.apps = snapshot.apps
        self.files_loaded = snapshot.files_loaded

    def load(self) -> None:
        self.space_names = self.loader.load_space_names()
        files = self.loader.lineage_files()
        records = self.loader.load_lineage_records(files)
        snapshot = self.builder.build(records, files_loaded=len(files))
        self.skipped_lineage_files = dict(self.loader.skipped_files)
        self._apply_snapshot(snapshot)

    def inventory(self) -> Dict:
        apps = []
        for app in self.apps.values():
            item = dict(app)
            space_id = item.get("spaceId")
            if space_id and space_id in self.space_names:
                item["spaceName"] = self.space_names[space_id]
            apps.append(item)
        apps = sorted(apps, key=lambda x: (x.get("appName") or "", x.get("appId") or ""))
        totals = {"files": self.files_loaded, "nodes": len(self.nodes), "edges": len(self.edges)}
        return {"apps": apps, "totals": totals}

    def get_data_connections(self) -> Dict[str, Any]:
        return self.loader.get_data_connections()

    def get_app_usage(self, app_id: str) -> Dict[str, Any]:
        return self.loader.get_app_usage(app_id)

    def get_app_script(self, app_id: str) -> Dict[str, Any]:
        return self.loader.get_app_script(app_id)

    def get_app_subgraph(self, app_id: str, depth: int) -> Dict:
        app = self.apps.get(app_id)
        if not app or not app.get("rootNodeId"):
            raise KeyError("app not found")
        return self.get_node_subgraph(app["rootNodeId"], "both", depth)

    def get_full_graph(self) -> Dict:
        nodes = list(self.nodes.values())
        edges = list(self.edges.values())
        return {"nodes": nodes, "edges": edges}

    def get_node_subgraph(self, node_id: str, direction: str, depth: int) -> Dict:
        nodes_set, edges_set = bfs_subgraph(self.snapshot, node_id, direction, depth)
        nodes = [self.nodes[nid] for nid in nodes_set]
        edges = [self.edges[eid] for eid in edges_set]
        return {"nodes": nodes, "edges": edges}

    def orphans_report(self) -> Dict:
        never = never_referenced(self.snapshot)
        dead = dead_ends(self.snapshot)
        orphan = orphan_outputs(self.snapshot)
        return {
            "neverReferenced": [self.nodes[nid] for nid in never],
            "deadEnds": [self.nodes[nid] for nid in dead],
            "orphanOutputs": [self.nodes[nid] for nid in orphan],
        }
