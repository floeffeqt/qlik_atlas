import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.db_runtime_views import (  # type: ignore
    _build_snapshot_from_rows,
    _connection_group_candidates,
    _connection_node_id,
    _qri_prefix_before_hash,
    load_data_connections_payload,
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


def test_connection_group_candidates_use_qri_db_and_ignore_http_noise():
    row = QlikDataConnection(
        project_id=1,
        connection_id="conn-http-noise",
        qri="qri:db:mysql://abc123",
        data={
            "qri": "qri:db:mysql://abc123",
            "qConnectStatement": 'CUSTOM CONNECT TO "provider=QvRestConnector.exe;url=https://tenant.qlikcloud.com/api";',
        },
    )
    groups = _connection_group_candidates(dict(row.data or {}), row)
    assert "db:mysql" in groups
    assert "db:https" not in groups


def test_connection_to_table_edge_is_inferred_by_db_group():
    table_node_id = "qri:db:mysql://abc123#table-1"
    node_rows = [
        LineageNode(
            project_id=1,
            node_id=table_node_id,
            app_id=None,
            node_type="table",
            data={
                "id": table_node_id,
                "label": "orders",
                "type": "table",
                "group": "db:mysql",
            },
        )
    ]
    connection_row = QlikDataConnection(
        project_id=1,
        connection_id="conn-mysql",
        qri="qri:db:mysql://conn-xyz",
        data={
            "qName": "MYSQL MAIN",
            "qri": "qri:db:mysql://conn-xyz",
            "qConnectStatement": 'CUSTOM CONNECT TO "provider=QvOdbcConnectorPackage.exe;driver=mysql;host=db";',
        },
    )

    snapshot = _build_snapshot_from_rows(
        node_rows,
        [],
        data_connection_rows=[connection_row],
    )

    connection_node_id = _connection_node_id(connection_row)
    inferred = [
        edge for edge in snapshot.edges.values()
        if edge.get("source") == connection_node_id
        and edge.get("target") == table_node_id
        and edge.get("relation") == "DEPENDS"
    ]
    assert inferred, "expected inferred connection->table edge"


def test_group_match_skipped_when_qri_match_exists():
    root_node_id = "qri:app:sense://app-9#root"
    table_node_id = "qri:db:mysql://abc123#table-1"
    node_rows = [
        LineageNode(
            project_id=1,
            node_id=root_node_id,
            app_id="app-9",
            node_type="app",
            data={
                "id": root_node_id,
                "label": "Finance App",
                "type": "app",
                "meta": {"appId": "app-9"},
            },
        ),
        LineageNode(
            project_id=1,
            node_id=table_node_id,
            app_id=None,
            node_type="table",
            data={
                "id": table_node_id,
                "label": "transactions",
                "type": "table",
                "group": "db:mysql",
            },
        ),
    ]
    connection_row = QlikDataConnection(
        project_id=1,
        connection_id="conn-priority",
        qri="qri:app:sense://app-9#connection",
        data={
            "qName": "MYSQL PRIORITY",
            "qri": "qri:app:sense://app-9#connection",
            "qConnectStatement": 'CUSTOM CONNECT TO "provider=QvOdbcConnectorPackage.exe;driver=mysql;host=db";',
        },
    )

    snapshot = _build_snapshot_from_rows(
        node_rows,
        [],
        app_info_by_project_and_app={(1, "app-9"): {"appId": "app-9", "appName": "Finance App"}},
        data_connection_rows=[connection_row],
        connection_matches_by_project_and_connection={
            (1, "conn-priority"): [
                {"appId": "app-9", "appName": "Finance App", "rootNodeId": root_node_id}
            ]
        },
    )

    connection_node_id = _connection_node_id(connection_row)
    connection_meta = snapshot.nodes[connection_node_id].get("meta") or {}
    assert connection_meta.get("groupMatchStatus") == "skipped_due_to_qri_match"

    has_qri_edge = any(
        edge.get("source") == connection_node_id
        and edge.get("target") == root_node_id
        and (edge.get("context") or {}).get("matchMode") == "qri-prefix-before-hash"
        for edge in snapshot.edges.values()
    )
    assert has_qri_edge

    has_group_edge_to_table = any(
        edge.get("source") == connection_node_id
        and edge.get("target") == table_node_id
        for edge in snapshot.edges.values()
    )
    assert not has_group_edge_to_table


def test_connection_group_match_ignores_ambiguous_candidates():
    table_a = "qri:db:mysql://abc123#table-a"
    table_b = "qri:db:mysql://abc123#table-b"
    node_rows = [
        LineageNode(
            project_id=1,
            node_id=table_a,
            app_id=None,
            node_type="table",
            data={"id": table_a, "label": "orders", "type": "table", "group": "db:mysql"},
        ),
        LineageNode(
            project_id=1,
            node_id=table_b,
            app_id=None,
            node_type="table",
            data={"id": table_b, "label": "customers", "type": "table", "group": "db:mysql"},
        ),
    ]
    connection_row = QlikDataConnection(
        project_id=1,
        connection_id="conn-ambiguous",
        qri="qri:db:mysql://conn-xyz",
        data={
            "qName": "MYSQL AMBIGUOUS",
            "qri": "qri:db:mysql://conn-xyz",
            "qConnectStatement": 'CUSTOM CONNECT TO "provider=QvOdbcConnectorPackage.exe;driver=mysql;host=db";',
        },
    )

    snapshot = _build_snapshot_from_rows(
        node_rows,
        [],
        data_connection_rows=[connection_row],
    )

    connection_node_id = _connection_node_id(connection_row)
    connection_meta = snapshot.nodes[connection_node_id].get("meta") or {}
    assert connection_meta.get("groupMatchStatus") == "ambiguous"
    ambiguous = connection_meta.get("groupMatchAmbiguous") or []
    assert any(item.get("group") == "db:mysql" and int(item.get("candidateCount") or 0) == 2 for item in ambiguous)

    inferred = [
        edge for edge in snapshot.edges.values()
        if edge.get("source") == connection_node_id
        and edge.get("target") in {table_a, table_b}
        and edge.get("relation") == "DEPENDS"
    ]
    assert not inferred


def test_connection_qri_db_prefix_match_restores_precise_mapping():
    db_prefix = "qri:db:mysql://source-abc"
    table_a = f"{db_prefix}#table-a"
    table_b = f"{db_prefix}#table-b"
    other_mysql_table = "qri:db:mysql://other-source#table-x"
    node_rows = [
        LineageNode(
            project_id=1,
            node_id=table_a,
            app_id=None,
            node_type="table",
            data={"id": table_a, "label": "orders", "type": "table", "group": "db:mysql"},
        ),
        LineageNode(
            project_id=1,
            node_id=table_b,
            app_id=None,
            node_type="table",
            data={"id": table_b, "label": "customers", "type": "table", "group": "db:mysql"},
        ),
        LineageNode(
            project_id=1,
            node_id=other_mysql_table,
            app_id=None,
            node_type="table",
            data={"id": other_mysql_table, "label": "payments", "type": "table", "group": "db:mysql"},
        ),
    ]
    connection_row = QlikDataConnection(
        project_id=1,
        connection_id="conn-qri-db",
        qri=db_prefix,
        data={
            "qName": "MYSQL SOURCE ABC",
            "qri": db_prefix,
            "qType": "QvOdbcConnectorPackage.exe",
            "qConnectStatement": 'CUSTOM CONNECT TO "provider=QvOdbcConnectorPackage.exe;driver=mysql;host=db";',
        },
    )

    snapshot = _build_snapshot_from_rows(
        node_rows,
        [],
        data_connection_rows=[connection_row],
    )

    connection_node_id = _connection_node_id(connection_row)
    connection_meta = snapshot.nodes[connection_node_id].get("meta") or {}
    assert connection_meta.get("qriDbMatchMode") == "prefix-before-hash"
    assert connection_meta.get("groupMatchStatus") == "skipped_due_to_qri_db_match"

    inferred_qri_edges = [
        edge for edge in snapshot.edges.values()
        if edge.get("source") == connection_node_id
        and edge.get("target") in {table_a, table_b}
        and (edge.get("context") or {}).get("matchMode") == "qri-db-prefix-before-hash"
    ]
    assert len(inferred_qri_edges) == 2

    has_wrong_edge = any(
        edge.get("source") == connection_node_id and edge.get("target") == other_mysql_table
        for edge in snapshot.edges.values()
    )
    assert not has_wrong_edge


class _FakeScalarsResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeAsyncSession:
    def __init__(self, rows):
        self._rows = list(rows)

    async def execute(self, _stmt):
        return _FakeScalarsResult(self._rows)


@pytest.mark.asyncio
async def test_load_data_connections_payload_excludes_q_connect_statement():
    row = QlikDataConnection(
        project_id=1,
        connection_id="conn-1",
        q_name="ERP SQL",
        q_type="QvOdbcConnectorPackage.exe",
        q_connect_statement='CUSTOM CONNECT TO "provider=QvOdbcConnectorPackage.exe;driver=mysql;host=db";',
        data={
            "id": "conn-1",
            "qName": "ERP SQL",
            "qType": "QvOdbcConnectorPackage.exe",
            "qConnectStatement": 'CUSTOM CONNECT TO "provider=QvOdbcConnectorPackage.exe;driver=mysql;host=db";',
        },
    )
    session = _FakeAsyncSession([row])

    payload = await load_data_connections_payload(session)
    assert payload["count"] == 1
    item = payload["data"][0]
    assert item["id"] == "conn-1"
    assert item["qName"] == "ERP SQL"
    assert "qConnectStatement" not in item
