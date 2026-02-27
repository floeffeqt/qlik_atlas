import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.db_runtime_views import (  # type: ignore
    _build_snapshot_from_rows,
    _connection_node_id,
    _qri_prefix_before_hash,
)
from app.models import LineageNode, QlikDataConnection  # type: ignore


def test_qri_prefix_before_hash_extracts_normalized_prefix():
    assert _qri_prefix_before_hash("qri:app:sense://APP-123#node-1") == "qri:app:sense://app-123"
    assert _qri_prefix_before_hash("  qri:db:postgresql://sales#table  ") == "qri:db:postgresql://sales"
    assert _qri_prefix_before_hash("qri:app:sense://app-123") == "qri:app:sense://app-123"
    assert _qri_prefix_before_hash("") is None
    assert _qri_prefix_before_hash(None) is None


def test_qri_prefix_match_links_connection_to_app_root_and_exposes_source_system():
    root_node_id = "qri:app:sense://app-1#root"
    node_rows = [
        LineageNode(
            project_id=1,
            node_id=root_node_id,
            app_id="app-1",
            node_type="app",
            data={
                "id": root_node_id,
                "label": "Sales App",
                "type": "app",
                "meta": {"appId": "app-1"},
            },
        )
    ]

    connection_row = QlikDataConnection(
        project_id=1,
        connection_id="conn-1",
        qri="qri:app:sense://app-1#connection",
        data={
            "qName": "ERP SQL",
            "qri": "qri:app:sense://app-1#connection",
        },
    )

    snapshot = _build_snapshot_from_rows(
        node_rows,
        [],
        app_info_by_project_and_app={(1, "app-1"): {"appId": "app-1", "appName": "Sales App"}},
        data_connection_rows=[connection_row],
        connection_matches_by_project_and_connection={
            (1, "conn-1"): [
                {"appId": "app-1", "appName": "Sales App", "rootNodeId": root_node_id}
            ]
        },
    )

    connection_node_id = _connection_node_id(connection_row)
    assert connection_node_id in snapshot.nodes
    connection_meta = snapshot.nodes[connection_node_id].get("meta") or {}
    assert connection_meta.get("qriPrefix") == "qri:app:sense://app-1"
    assert connection_meta.get("qriMatchMode") == "prefix-before-hash"
    assert "Sales App" in (connection_meta.get("qriMatchAppNames") or [])

    root_meta = snapshot.nodes[root_node_id].get("meta") or {}
    assert "ERP SQL" in (root_meta.get("sourceSystems") or [])
    assert "conn-1" in (root_meta.get("sourceConnectionIds") or [])

    has_qri_edge = any(
        edge.get("source") == connection_node_id
        and edge.get("target") == root_node_id
        and (edge.get("context") or {}).get("matchMode") == "qri-prefix-before-hash"
        for edge in snapshot.edges.values()
    )
    assert has_qri_edge
