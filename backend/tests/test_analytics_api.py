import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import main as main_module  # type: ignore


@pytest.fixture
def override_session_dep():
    async def _fake_session():
        yield object()

    main_module.app.dependency_overrides[main_module._session_with_rls_context] = _fake_session
    try:
        yield
    finally:
        main_module.app.dependency_overrides.pop(main_module._session_with_rls_context, None)


@pytest.mark.asyncio
async def test_analytics_areas_endpoint_contract(override_session_dep, monkeypatch):
    async def fake_loader(*_args, **_kwargs):
        return {
            "areas": [
                {
                    "area_key": "space:s-1",
                    "area_name": "Finance",
                    "apps_count": 2,
                    "nodes_estimate": 12,
                    "total_static_byte_size_latest": 1000,
                    "peak_memory_latest_max": 2048,
                    "direct_query_apps_count": 1,
                    "section_access_missing_count": 0,
                    "schema_drift_apps_count": 1,
                }
            ],
            "totals": {
                "areas_count": 1,
                "apps_count": 2,
                "nodes_estimate": 12,
                "total_static_byte_size_latest": 1000,
                "peak_memory_latest_max": 2048,
                "direct_query_apps_count": 1,
                "section_access_missing_count": 0,
                "schema_drift_apps_count": 1,
            },
        }

    monkeypatch.setattr(main_module, "load_analytics_areas", fake_loader)
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/analytics/areas?days=30")
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["areas"][0]["area_key"] == "space:s-1"
    assert payload["totals"]["apps_count"] == 2


@pytest.mark.asyncio
async def test_analytics_area_apps_invalid_key_returns_400(override_session_dep, monkeypatch):
    async def fake_loader(*_args, **_kwargs):
        raise ValueError("unsupported area key")

    monkeypatch.setattr(main_module, "load_analytics_area_apps", fake_loader)
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/analytics/areas/invalid/apps")
    assert res.status_code == 400
    payload = res.json()
    assert payload["detail"]["code"] == "invalid_area_key"
    assert "unsupported area key" in payload["detail"]["message"]


@pytest.mark.asyncio
async def test_analytics_fields_requires_project_id_query(override_session_dep):
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/analytics/apps/app-1/fields")
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_analytics_fields_not_found_maps_to_404(override_session_dep, monkeypatch):
    async def fake_loader(*_args, **_kwargs):
        raise KeyError("app not found")

    monkeypatch.setattr(main_module, "load_analytics_app_fields", fake_loader)
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/analytics/apps/app-404/fields?project_id=7")
    assert res.status_code == 404
    payload = res.json()
    assert payload["detail"]["code"] == "app_not_found"
    assert "App nicht gefunden" in payload["detail"]["message"]


@pytest.mark.asyncio
async def test_analytics_areas_runtime_error_maps_to_structured_500(override_session_dep, monkeypatch):
    async def fake_loader(*_args, **_kwargs):
        raise RuntimeError("db failed")

    monkeypatch.setattr(main_module, "load_analytics_areas", fake_loader)
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/analytics/areas?days=30")
    assert res.status_code == 500
    payload = res.json()
    assert payload["detail"]["code"] == "analytics_areas_query_failed"


@pytest.mark.asyncio
async def test_analytics_trend_endpoint_contract(override_session_dep, monkeypatch):
    async def fake_loader(*_args, **_kwargs):
        return {
            "app_id": "app-9",
            "project_id": 3,
            "days": 30,
            "points": [
                {
                    "fetched_at": "2026-03-03T12:00:00Z",
                    "static_byte_size": 100,
                    "reload_meta_peak_memory_bytes": 200,
                    "reload_meta_cpu_time_spent_ms": 50,
                    "schema_hash": "abc",
                }
            ],
        }

    monkeypatch.setattr(main_module, "load_analytics_app_trend", fake_loader)
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/analytics/apps/app-9/trend?project_id=3&days=30")
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["app_id"] == "app-9"
    assert len(payload["points"]) == 1


@pytest.mark.asyncio
async def test_cost_value_insight_endpoint_contract(override_session_dep, monkeypatch):
    async def fake_loader(*_args, **_kwargs):
        return {
            "apps": [
                {
                    "project_id": 1,
                    "app_id": "app-1",
                    "app_name": "Sales",
                    "space_name": "Finance",
                    "latest_fetched_at": "2026-03-03T12:00:00Z",
                    "static_byte_size_latest": 123,
                    "reload_meta_peak_memory_bytes_latest": 456,
                    "reload_meta_cpu_time_spent_ms_latest": 789,
                    "fields_count_latest": 10,
                    "tables_count_latest": 5,
                    "usage_app_opens": 9,
                    "usage_sheet_views": 8,
                    "usage_unique_users": 7,
                    "usage_reloads": 6,
                    "complexity_score": 55.0,
                    "cost_score": 71.0,
                    "value_score": 34.0,
                    "efficiency_score": 48.0,
                    "quadrant": "high-cost-low-value",
                }
            ],
            "summary": {
                "apps_count": 1,
                "high_cost_low_value_count": 1,
                "avg_cost_score": 71.0,
                "avg_value_score": 34.0,
            },
        }

    monkeypatch.setattr(main_module, "load_cost_value_map", fake_loader)
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/analytics/insights/cost-value?days=30")
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["summary"]["apps_count"] == 1
    assert payload["apps"][0]["quadrant"] == "high-cost-low-value"


@pytest.mark.asyncio
async def test_bloat_insight_endpoint_contract(override_session_dep, monkeypatch):
    async def fake_loader(*_args, **_kwargs):
        return {
            "top_apps": [
                {
                    "project_id": 1,
                    "app_id": "app-1",
                    "app_name": "Sales",
                    "space_name": "Finance",
                    "static_byte_size_latest": 1000,
                    "fields_count_latest": 10,
                    "tables_count_latest": 3,
                    "schema_drift_count_in_window": 2,
                }
            ],
            "top_tables": [
                {
                    "project_id": 1,
                    "app_id": "app-1",
                    "app_name": "Sales",
                    "space_name": "Finance",
                    "table_name": "FactSales",
                    "byte_size": 4000,
                    "no_of_rows": 100,
                    "no_of_fields": 12,
                    "no_of_key_fields": 1,
                    "is_system": False,
                    "is_semantic": False,
                }
            ],
            "top_fields": [
                {
                    "project_id": 1,
                    "app_id": "app-1",
                    "app_name": "Sales",
                    "space_name": "Finance",
                    "field_hash": "f-h-1",
                    "name": "CustomerId",
                    "byte_size": 2400,
                    "cardinal": 80,
                    "total_count": 1000,
                    "is_system": False,
                    "is_hidden": False,
                    "is_semantic": False,
                    "src_tables": ["FactSales"],
                }
            ],
            "schema_drift_apps": [
                {
                    "project_id": 1,
                    "app_id": "app-1",
                    "app_name": "Sales",
                    "space_name": "Finance",
                    "static_byte_size_latest": 1000,
                    "fields_count_latest": 10,
                    "tables_count_latest": 3,
                    "schema_drift_count_in_window": 2,
                }
            ],
            "summary": {
                "apps_count": 1,
                "top_tables_count": 1,
                "top_fields_count": 1,
                "schema_drift_apps_count": 1,
            },
        }

    monkeypatch.setattr(main_module, "load_bloat_explorer", fake_loader)
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/analytics/insights/bloat?limit=20")
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["summary"]["top_fields_count"] == 1
    assert payload["top_apps"][0]["space_name"] == "Finance"
    assert payload["top_tables"][0]["space_name"] == "Finance"
    assert payload["top_fields"][0]["space_name"] == "Finance"


@pytest.mark.asyncio
async def test_data_model_pack_insight_endpoint_contract(override_session_dep, monkeypatch):
    async def fake_loader(*_args, **_kwargs):
        return {
            "metric": "static_byte_size_latest",
            "metric_options": ["static_byte_size_latest", "complexity_latest"],
            "areas": [
                {
                    "area_key": "space:s-1",
                    "area_name": "Finance",
                    "metric_value": 1500.0,
                    "apps": [
                        {
                            "project_id": 1,
                            "app_id": "app-1",
                            "app_name": "Sales",
                            "space_name": "Finance",
                            "static_byte_size_latest": 1000,
                            "fields_count_latest": 10,
                            "tables_count_latest": 5,
                            "complexity_latest": 50,
                            "metric_value": 1000.0,
                        }
                    ],
                }
            ],
            "summary": {"areas_count": 1, "apps_count": 1, "total_metric_value": 1500.0},
        }

    monkeypatch.setattr(main_module, "load_data_model_pack", fake_loader)
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/analytics/insights/data-model-pack?metric=static_byte_size_latest")
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["metric"] == "static_byte_size_latest"
    assert payload["summary"]["areas_count"] == 1
    assert payload["areas"][0]["apps"][0]["app_id"] == "app-1"


@pytest.mark.asyncio
async def test_data_model_pack_insight_runtime_error_code(override_session_dep, monkeypatch):
    async def fake_loader(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(main_module, "load_data_model_pack", fake_loader)
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/analytics/insights/data-model-pack?metric=complexity_latest")
    assert res.status_code == 500
    payload = res.json()
    assert payload["detail"]["code"] == "analytics_data_model_pack_query_failed"


@pytest.mark.asyncio
async def test_data_model_pack_insight_invalid_metric_returns_422(override_session_dep):
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/analytics/insights/data-model-pack?metric=unknown_metric")
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_lineage_criticality_insight_error_code(override_session_dep, monkeypatch):
    async def fake_loader(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(main_module, "load_lineage_criticality", fake_loader)
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/analytics/insights/lineage-criticality")
    assert res.status_code == 500
    payload = res.json()
    assert payload["detail"]["code"] == "analytics_lineage_criticality_query_failed"


@pytest.mark.asyncio
async def test_governance_ops_insight_endpoint_contract(override_session_dep, monkeypatch):
    async def fake_loader(*_args, **_kwargs):
        return {
            "summary": {
                "apps_total": 3,
                "low_or_no_usage_apps_count": 2,
                "no_usage_apps_count": 1,
                "low_usage_apps_count": 1,
                "low_signal_tables_count": 2,
                "low_signal_fields_count": 2,
                "low_signal_qvds_count": 1,
                "low_usage_signal_threshold": 12.5,
            },
            "low_usage_apps": [
                {
                    "project_id": 1,
                    "app_id": "app-1",
                    "app_name": "Sales",
                    "space_name": "Finance",
                    "latest_fetched_at": "2026-03-03T12:00:00Z",
                    "static_byte_size_latest": 1000,
                    "reload_meta_peak_memory_bytes_latest": 400,
                    "reload_meta_cpu_time_spent_ms_latest": 120,
                    "usage_app_opens": 0,
                    "usage_sheet_views": 0,
                    "usage_unique_users": 0,
                    "usage_reloads": 0,
                    "usage_signal_score": 0.0,
                    "usage_classification": "no-usage",
                    "reason": "Keine Nutzungsaktivitaet im vorhandenen Usage-Snapshot.",
                }
            ],
            "low_signal_tables": [],
            "low_signal_fields": [],
            "low_signal_qvds": [],
            "action_plan": [
                {
                    "action_id": "apps-retirement-review",
                    "priority": "high",
                    "title": "App-Rationalisierung",
                    "scope": "Apps",
                    "candidate_count": 2,
                    "target_metric": "Low/No Usage reduzieren",
                    "rationale": "Test",
                    "suggested_steps": ["step-1", "step-2"],
                }
            ],
        }

    monkeypatch.setattr(main_module, "load_governance_operations", fake_loader)
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/analytics/insights/governance-ops?project_id=1&limit=25")
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["summary"]["apps_total"] == 3
    assert payload["low_usage_apps"][0]["usage_classification"] == "no-usage"
    assert payload["action_plan"][0]["action_id"] == "apps-retirement-review"


@pytest.mark.asyncio
async def test_governance_ops_insight_error_code(override_session_dep, monkeypatch):
    async def fake_loader(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(main_module, "load_governance_operations", fake_loader)
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/analytics/insights/governance-ops")
    assert res.status_code == 500
    payload = res.json()
    assert payload["detail"]["code"] == "analytics_governance_ops_query_failed"
