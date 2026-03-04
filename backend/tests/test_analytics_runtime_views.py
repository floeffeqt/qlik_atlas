import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import analytics_runtime_views as arv  # type: ignore


@pytest.mark.asyncio
async def test_load_analytics_areas_aggregates_space_and_unassigned(monkeypatch):
    async def fake_latest_rows(*_args, **_kwargs):
        return [
            {
                "snapshot_id": 10,
                "project_id": 1,
                "app_id": "app-a",
                "static_byte_size": 100,
                "reload_meta_peak_memory_bytes": 400,
                "is_direct_query_mode": True,
                "has_section_access": False,
                "qa_app_name": "App A",
                "qa_name_value": None,
                "qa_space_id": "space-1",
                "qs_space_id": "space-1",
                "qs_space_name": "Finance",
            },
            {
                "snapshot_id": 11,
                "project_id": 1,
                "app_id": "app-b",
                "static_byte_size": 300,
                "reload_meta_peak_memory_bytes": 200,
                "is_direct_query_mode": False,
                "has_section_access": True,
                "qa_app_name": "App B",
                "qa_name_value": None,
                "qa_space_id": None,
                "qs_space_id": None,
                "qs_space_name": None,
            },
        ]

    async def fake_table_stats(*_args, **_kwargs):
        return {10: {"tables_count": 2, "nodes_estimate": 9}, 11: {"tables_count": 1, "nodes_estimate": 4}}

    async def fake_drift_counts(*_args, **_kwargs):
        return {(1, "app-a"): 3, (1, "app-b"): 1}

    monkeypatch.setattr(arv, "_load_latest_snapshot_rows", fake_latest_rows)
    monkeypatch.setattr(arv, "_load_table_stats_by_snapshot", fake_table_stats)
    monkeypatch.setattr(arv, "_load_schema_distinct_hash_counts", fake_drift_counts)

    payload = await arv.load_analytics_areas(session=object(), project_id=1, days=30)
    assert len(payload["areas"]) == 2
    finance = next(item for item in payload["areas"] if item["area_key"] == "space:space-1")
    unassigned = next(item for item in payload["areas"] if item["area_key"] == "unassigned")

    assert finance["nodes_estimate"] == 9
    assert finance["direct_query_apps_count"] == 1
    assert finance["section_access_missing_count"] == 1
    assert finance["schema_drift_apps_count"] == 1
    assert unassigned["area_name"] == "Unassigned"

    totals = payload["totals"]
    assert totals["areas_count"] == 2
    assert totals["apps_count"] == 2
    assert totals["total_static_byte_size_latest"] == 400
    assert totals["peak_memory_latest_max"] == 400


@pytest.mark.asyncio
async def test_load_analytics_area_apps_filters_and_counts(monkeypatch):
    async def fake_latest_rows(*_args, **_kwargs):
        return [
            {
                "snapshot_id": 22,
                "project_id": 3,
                "app_id": "app-1",
                "fetched_at": None,
                "static_byte_size": 700,
                "reload_meta_peak_memory_bytes": 1000,
                "reload_meta_cpu_time_spent_ms": 200,
                "is_direct_query_mode": True,
                "has_section_access": True,
                "schema_hash": "hash-a",
                "qa_app_name": "Sales",
                "qa_name_value": None,
                "qa_space_id": "s-1",
                "qs_space_id": "s-1",
                "qs_space_name": "North",
            },
            {
                "snapshot_id": 23,
                "project_id": 3,
                "app_id": "app-2",
                "fetched_at": None,
                "static_byte_size": 100,
                "reload_meta_peak_memory_bytes": 300,
                "reload_meta_cpu_time_spent_ms": 50,
                "is_direct_query_mode": False,
                "has_section_access": False,
                "schema_hash": "hash-b",
                "qa_app_name": "Ops",
                "qa_name_value": None,
                "qa_space_id": "s-2",
                "qs_space_id": "s-2",
                "qs_space_name": "South",
            },
        ]

    async def fake_field_counts(*_args, **_kwargs):
        return {22: 33, 23: 11}

    async def fake_table_stats(*_args, **_kwargs):
        return {22: {"tables_count": 4, "nodes_estimate": 12}, 23: {"tables_count": 1, "nodes_estimate": 3}}

    async def fake_drift_counts(*_args, **_kwargs):
        return {(3, "app-1"): 4, (3, "app-2"): 1}

    monkeypatch.setattr(arv, "_load_latest_snapshot_rows", fake_latest_rows)
    monkeypatch.setattr(arv, "_load_field_count_by_snapshot", fake_field_counts)
    monkeypatch.setattr(arv, "_load_table_stats_by_snapshot", fake_table_stats)
    monkeypatch.setattr(arv, "_load_schema_distinct_hash_counts", fake_drift_counts)

    payload = await arv.load_analytics_area_apps(session=object(), area_key="space:s-1", project_id=3, days=30)
    assert payload["area_key"] == "space:s-1"
    assert payload["area_name"] == "North"
    assert len(payload["apps"]) == 1
    app = payload["apps"][0]
    assert app["app_id"] == "app-1"
    assert app["fields_count_latest"] == 33
    assert app["tables_count_latest"] == 4
    assert app["schema_drift_count_in_window"] == 3


class _FakeResult:
    def __init__(self, *, scalar_value: Any = None, mapping_rows: list[dict[str, Any]] | None = None):
        self._scalar_value = scalar_value
        self._mapping_rows = mapping_rows or []

    def scalar(self):
        return self._scalar_value

    def mappings(self):
        return self

    def all(self):
        return list(self._mapping_rows)


class _FakeSession:
    def __init__(self, results: list[_FakeResult]):
        self._results = list(results)

    async def execute(self, _stmt):
        if not self._results:
            raise AssertionError("no more fake results")
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_load_analytics_app_fields_applies_paging_and_default_sort(monkeypatch):
    async def fake_ensure(*_args, **_kwargs):
        return None

    async def fake_latest(*_args, **_kwargs):
        return 999

    monkeypatch.setattr(arv, "_ensure_app_exists", fake_ensure)
    monkeypatch.setattr(arv, "_latest_snapshot_for_app", fake_latest)

    session = _FakeSession(
        [
            _FakeResult(scalar_value=2),
            _FakeResult(
                mapping_rows=[
                    {
                        "row_id": 1,
                        "field_hash": "h1",
                        "name": "Country",
                        "byte_size": 12,
                        "cardinal": 3,
                        "total_count": 10,
                        "is_numeric": False,
                        "is_semantic": True,
                        "is_system": False,
                        "is_hidden": False,
                        "is_locked": False,
                        "distinct_only": False,
                        "always_one_selected": False,
                        "tags": ["$text"],
                        "src_tables": ["Sales"],
                    }
                ]
            ),
        ]
    )

    payload = await arv.load_analytics_app_fields(
        session=session,
        project_id=1,
        app_id="app-x",
        limit=5000,
        offset=0,
        sort_by="unknown_column",
        sort_dir="desc",
        search="cou",
    )
    assert payload["snapshot_id"] == 999
    assert payload["paging"]["limit"] == arv.MAX_FIELDS_LIMIT
    assert payload["paging"]["sort_by"] == "byte_size"
    assert payload["paging"]["total"] == 2
    assert payload["fields"][0]["field_hash"] == "h1"


def test_parse_area_key_validates_format():
    assert arv.parse_area_key("unassigned") == ("unassigned", None)
    assert arv.parse_area_key("space:abc") == ("space:abc", "abc")
    with pytest.raises(ValueError):
        arv.parse_area_key("space:")
    with pytest.raises(ValueError):
        arv.parse_area_key("foo")


@pytest.mark.asyncio
async def test_load_cost_value_map_marks_high_cost_low_value(monkeypatch):
    async def fake_latest_rows(*_args, **_kwargs):
        return [
            {
                "snapshot_id": 1,
                "project_id": 2,
                "app_id": "app-1",
                "fetched_at": None,
                "static_byte_size": 900,
                "reload_meta_peak_memory_bytes": 700,
                "reload_meta_cpu_time_spent_ms": 500,
                "qa_app_name": "Costly",
                "qa_name_value": None,
                "qa_space_id": "space-a",
                "qs_space_id": "space-a",
                "qs_space_name": "Area A",
            },
            {
                "snapshot_id": 2,
                "project_id": 2,
                "app_id": "app-2",
                "fetched_at": None,
                "static_byte_size": 100,
                "reload_meta_peak_memory_bytes": 100,
                "reload_meta_cpu_time_spent_ms": 10,
                "qa_app_name": "Valuable",
                "qa_name_value": None,
                "qa_space_id": "space-a",
                "qs_space_id": "space-a",
                "qs_space_name": "Area A",
            },
        ]

    async def fake_field_counts(*_args, **_kwargs):
        return {1: 80, 2: 10}

    async def fake_table_stats(*_args, **_kwargs):
        return {1: {"tables_count": 20, "nodes_estimate": 100}, 2: {"tables_count": 2, "nodes_estimate": 20}}

    async def fake_usage(*_args, **_kwargs):
        return {
            (2, "app-1"): {"usage_reloads": 0, "usage_app_opens": 1, "usage_sheet_views": 1, "usage_unique_users": 1},
            (2, "app-2"): {"usage_reloads": 10, "usage_app_opens": 100, "usage_sheet_views": 150, "usage_unique_users": 20},
        }

    monkeypatch.setattr(arv, "_load_latest_snapshot_rows", fake_latest_rows)
    monkeypatch.setattr(arv, "_load_field_count_by_snapshot", fake_field_counts)
    monkeypatch.setattr(arv, "_load_table_stats_by_snapshot", fake_table_stats)
    monkeypatch.setattr(arv, "_load_usage_by_app", fake_usage)

    payload = await arv.load_cost_value_map(session=object(), project_id=2, days=30)
    assert payload["summary"]["apps_count"] == 2
    assert payload["summary"]["high_cost_low_value_count"] >= 1
    top = payload["apps"][0]
    assert top["app_id"] == "app-1"
    assert top["quadrant"] == "high-cost-low-value"


@pytest.mark.asyncio
async def test_load_governance_operations_builds_candidates_and_actions(monkeypatch):
    async def fake_latest_rows(*_args, **_kwargs):
        return [
            {
                "snapshot_id": 31,
                "project_id": 4,
                "app_id": "app-a",
                "fetched_at": None,
                "static_byte_size": 1000,
                "reload_meta_peak_memory_bytes": 800,
                "reload_meta_cpu_time_spent_ms": 120,
                "qa_app_name": "App A",
                "qa_name_value": None,
                "qa_space_id": "s-1",
                "qs_space_id": "s-1",
                "qs_space_name": "Finance",
            },
            {
                "snapshot_id": 32,
                "project_id": 4,
                "app_id": "app-b",
                "fetched_at": None,
                "static_byte_size": 500,
                "reload_meta_peak_memory_bytes": 200,
                "reload_meta_cpu_time_spent_ms": 30,
                "qa_app_name": "App B",
                "qa_name_value": None,
                "qa_space_id": "s-2",
                "qs_space_id": "s-2",
                "qs_space_name": "Operations",
            },
        ]

    async def fake_usage(*_args, **_kwargs):
        return {
            (4, "app-a"): {"usage_reloads": 0, "usage_app_opens": 0, "usage_sheet_views": 0, "usage_unique_users": 0},
            (4, "app-b"): {"usage_reloads": 3, "usage_app_opens": 5, "usage_sheet_views": 20, "usage_unique_users": 2},
        }

    async def fake_tables(*_args, **_kwargs):
        return [
            {
                "project_id": 4,
                "app_id": "app-a",
                "app_name": "App A",
                "space_name": "Finance",
                "usage_classification": "no-usage",
                "usage_signal_score": 0.0,
                "usage_app_opens": 0,
                "usage_sheet_views": 0,
                "usage_unique_users": 0,
                "usage_reloads": 0,
                "table_name": "FactLarge",
                "byte_size": 6400,
                "no_of_rows": 100,
                "no_of_fields": 20,
                "no_of_key_fields": 2,
                "is_semantic": False,
                "reason": "Keine App-Nutzung bei grossem Tabellen-Footprint.",
            }
        ]

    async def fake_fields(*_args, **_kwargs):
        return [
            {
                "project_id": 4,
                "app_id": "app-a",
                "app_name": "App A",
                "space_name": "Finance",
                "usage_classification": "no-usage",
                "usage_signal_score": 0.0,
                "usage_app_opens": 0,
                "usage_sheet_views": 0,
                "usage_unique_users": 0,
                "usage_reloads": 0,
                "field_hash": "h-1",
                "name": "CustomerId",
                "byte_size": 4200,
                "cardinal": 40,
                "total_count": 1000,
                "is_hidden": False,
                "is_semantic": False,
                "src_tables": ["FactLarge"],
                "reason": "Keine App-Nutzung bei grossem Feld-Footprint.",
            }
        ]

    async def fake_qvds(*_args, **_kwargs):
        return [
            {
                "project_id": 4,
                "node_id": "qvd:1",
                "label": "sales.qvd",
                "app_id": "app-a",
                "app_name": "App A",
                "space_name": "Finance",
                "usage_signal_score": 0.0,
                "usage_app_opens": 0,
                "usage_sheet_views": 0,
                "usage_unique_users": 0,
                "usage_reloads": 0,
                "linked_app_low_usage": True,
                "degree": 1,
                "in_degree": 1,
                "out_degree": 0,
                "signal_classification": "linked-low-usage-app",
                "reason": "QVD haengt an einer App mit niedriger oder fehlender Nutzung.",
            }
        ]

    monkeypatch.setattr(arv, "_load_latest_snapshot_rows", fake_latest_rows)
    monkeypatch.setattr(arv, "_load_usage_by_app", fake_usage)
    monkeypatch.setattr(arv, "_load_low_signal_table_candidates", fake_tables)
    monkeypatch.setattr(arv, "_load_low_signal_field_candidates", fake_fields)
    monkeypatch.setattr(arv, "_load_low_signal_qvd_candidates", fake_qvds)

    payload = await arv.load_governance_operations(session=object(), project_id=4, limit=20)
    summary = payload["summary"]
    assert summary["apps_total"] == 2
    assert summary["low_or_no_usage_apps_count"] >= 1
    assert summary["no_usage_apps_count"] >= 1
    assert summary["low_signal_tables_count"] == 1
    assert summary["low_signal_fields_count"] == 1
    assert summary["low_signal_qvds_count"] == 1
    assert payload["low_usage_apps"][0]["app_id"] == "app-a"
    action_ids = [item["action_id"] for item in payload["action_plan"]]
    assert "apps-retirement-review" in action_ids
    assert "data-model-bloat-cleanup" in action_ids


@pytest.mark.asyncio
async def test_load_data_model_pack_static_metric_aggregates_by_area(monkeypatch):
    async def fake_latest_rows(*_args, **_kwargs):
        return [
            {
                "snapshot_id": 101,
                "project_id": 7,
                "app_id": "app-a",
                "static_byte_size": 1000,
                "qa_app_name": "App A",
                "qa_name_value": None,
                "qa_space_id": "s-1",
                "qs_space_id": "s-1",
                "qs_space_name": "Finance",
            },
            {
                "snapshot_id": 102,
                "project_id": 7,
                "app_id": "app-b",
                "static_byte_size": 600,
                "qa_app_name": "App B",
                "qa_name_value": None,
                "qa_space_id": "s-1",
                "qs_space_id": "s-1",
                "qs_space_name": "Finance",
            },
            {
                "snapshot_id": 103,
                "project_id": 7,
                "app_id": "app-c",
                "static_byte_size": 700,
                "qa_app_name": "App C",
                "qa_name_value": None,
                "qa_space_id": "s-2",
                "qs_space_id": "s-2",
                "qs_space_name": "Operations",
            },
        ]

    async def fake_field_counts(*_args, **_kwargs):
        return {101: 10, 102: 11, 103: 12}

    async def fake_table_stats(*_args, **_kwargs):
        return {101: {"tables_count": 2}, 102: {"tables_count": 3}, 103: {"tables_count": 1}}

    monkeypatch.setattr(arv, "_load_latest_snapshot_rows", fake_latest_rows)
    monkeypatch.setattr(arv, "_load_field_count_by_snapshot", fake_field_counts)
    monkeypatch.setattr(arv, "_load_table_stats_by_snapshot", fake_table_stats)

    payload = await arv.load_data_model_pack(
        session=object(),
        project_id=7,
        metric="static_byte_size_latest",
    )
    assert payload["metric"] == "static_byte_size_latest"
    assert payload["summary"]["areas_count"] == 2
    assert payload["summary"]["apps_count"] == 3
    assert payload["summary"]["total_metric_value"] == 2300.0
    assert payload["areas"][0]["area_name"] == "Finance"
    assert payload["areas"][0]["metric_value"] == 1600.0
    assert payload["areas"][0]["apps"][0]["app_id"] == "app-a"
    assert payload["areas"][0]["apps"][0]["metric_value"] == 1000.0


@pytest.mark.asyncio
async def test_load_data_model_pack_complexity_metric_uses_fields_and_tables(monkeypatch):
    async def fake_latest_rows(*_args, **_kwargs):
        return [
            {
                "snapshot_id": 201,
                "project_id": 9,
                "app_id": "app-x",
                "static_byte_size": 10,
                "qa_app_name": "App X",
                "qa_name_value": None,
                "qa_space_id": "s-1",
                "qs_space_id": "s-1",
                "qs_space_name": "Area 1",
            },
            {
                "snapshot_id": 202,
                "project_id": 9,
                "app_id": "app-y",
                "static_byte_size": 999,
                "qa_app_name": "App Y",
                "qa_name_value": None,
                "qa_space_id": "s-1",
                "qs_space_id": "s-1",
                "qs_space_name": "Area 1",
            },
        ]

    async def fake_field_counts(*_args, **_kwargs):
        return {201: 20, 202: 5}

    async def fake_table_stats(*_args, **_kwargs):
        return {201: {"tables_count": 4}, 202: {"tables_count": 1}}

    monkeypatch.setattr(arv, "_load_latest_snapshot_rows", fake_latest_rows)
    monkeypatch.setattr(arv, "_load_field_count_by_snapshot", fake_field_counts)
    monkeypatch.setattr(arv, "_load_table_stats_by_snapshot", fake_table_stats)

    payload = await arv.load_data_model_pack(
        session=object(),
        project_id=9,
        metric="complexity_latest",
    )
    assert payload["metric"] == "complexity_latest"
    assert payload["summary"]["areas_count"] == 1
    assert payload["summary"]["apps_count"] == 2
    # app-x: 20 + 4*8 = 52, app-y: 5 + 1*8 = 13
    assert payload["summary"]["total_metric_value"] == 65.0
    apps = payload["areas"][0]["apps"]
    assert apps[0]["app_id"] == "app-x"
    assert apps[0]["complexity_latest"] == 52
    assert apps[0]["metric_value"] == 52.0


class _RowsOnlyResult:
    def __init__(self, rows: list[Any]):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _BloatFakeSession:
    def __init__(self, execute_results: list[_RowsOnlyResult]):
        self._results = list(execute_results)

    async def execute(self, _stmt):
        if not self._results:
            raise AssertionError("no more fake results")
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_load_bloat_explorer_includes_space_name_for_all_lists(monkeypatch):
    async def fake_latest_rows(*_args, **_kwargs):
        return [
            {
                "snapshot_id": 501,
                "project_id": 5,
                "app_id": "app-1",
                "static_byte_size": 1000,
                "qa_app_name": "Sales App",
                "qa_name_value": None,
                "qa_space_id": "s-fin",
                "qs_space_id": "s-fin",
                "qs_space_name": "Finance",
            },
            {
                "snapshot_id": 502,
                "project_id": 5,
                "app_id": "app-2",
                "static_byte_size": 500,
                "qa_app_name": "No Space App",
                "qa_name_value": None,
                "qa_space_id": None,
                "qs_space_id": None,
                "qs_space_name": None,
            },
        ]

    async def fake_field_counts(*_args, **_kwargs):
        return {501: 12, 502: 8}

    async def fake_table_stats(*_args, **_kwargs):
        return {501: {"tables_count": 3}, 502: {"tables_count": 1}}

    async def fake_drift_counts(*_args, **_kwargs):
        return {(5, "app-1"): 2, (5, "app-2"): 1}

    monkeypatch.setattr(arv, "_load_latest_snapshot_rows", fake_latest_rows)
    monkeypatch.setattr(arv, "_load_field_count_by_snapshot", fake_field_counts)
    monkeypatch.setattr(arv, "_load_table_stats_by_snapshot", fake_table_stats)
    monkeypatch.setattr(arv, "_load_schema_distinct_hash_counts", fake_drift_counts)

    session = _BloatFakeSession(
        [
            _RowsOnlyResult(
                [
                    SimpleNamespace(
                        snapshot_id=501,
                        name="FactSales",
                        byte_size=4000,
                        no_of_rows=100,
                        no_of_fields=10,
                        no_of_key_fields=1,
                        is_system=False,
                        is_semantic=False,
                    )
                ]
            ),
            _RowsOnlyResult(
                [
                    SimpleNamespace(
                        snapshot_id=501,
                        field_hash="f-hash-1",
                        name="CustomerId",
                        byte_size=2500,
                        cardinal=80,
                        total_count=1000,
                        is_system=False,
                        is_hidden=False,
                        is_semantic=False,
                        src_tables=["FactSales"],
                    )
                ]
            ),
        ]
    )

    payload = await arv.load_bloat_explorer(session=session, project_id=5, days=30, limit=20)
    assert payload["top_apps"][0]["space_name"] == "Finance"
    assert payload["top_apps"][1]["space_name"] == "Unassigned"
    assert payload["top_tables"][0]["space_name"] == "Finance"
    assert payload["top_fields"][0]["space_name"] == "Finance"
    assert payload["schema_drift_apps"][0]["space_name"] == "Finance"
