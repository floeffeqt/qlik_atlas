import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from main import (  # type: ignore
    FETCH_STEP_ALL_ORDER,
    _app_payload_columns,
    _audit_payload_columns,
    _license_consumption_payload_columns,
    _license_status_payload_columns,
    _normalize_steps,
    _reload_payload_columns,
    _select_apps_for_app_edges,
)


def test_app_payload_columns_maps_flat_item_fields():
    payload = {
        "id": "item-1",
        "ownerId": "owner-1",
        "name": "Sales App",
        "description": "desc",
        "resourceType": "app",
        "resourceId": "app-1",
        "thumbnail": "thumb.png",
        "resourceAttributes_id": "app-1",
        "resourceAttributes_name": "Sales App Attr",
        "resourceAttributes_description": "desc-attr",
        "resourceAttributes_createdDate": "2024-02-01T10:00:00Z",
        "resourceAttributes_modifiedDate": "2024-02-02T11:00:00Z",
        "resourceAttributes_modifiedByUserName": "user@example.com",
        "resourceAttributes_publishTime": "2024-02-03T12:00:00Z",
        "resourceAttributes_lastReloadTime": "2024-02-04T13:00:00Z",
        "resourceAttributes_trashed": False,
        "resourceCustomAttributes_json": [{"id": "x", "value": "y"}],
        "source": "/api/v1/items",
        "tenant": "tenant.example.com",
    }
    cols = _app_payload_columns(payload)
    assert cols["item_id"] == "item-1"
    assert cols["owner_id"] == "owner-1"
    assert cols["resource_type"] == "app"
    assert cols["resource_id"] == "app-1"
    assert cols["resource_attributes_name"] == "Sales App Attr"
    assert cols["resource_attributes_trashed"] is False
    assert cols["source"] == "/api/v1/items"
    assert cols["tenant"] == "tenant.example.com"


def test_reload_payload_columns_maps_operational_fields():
    payload = {
        "id": "reload-1",
        "appId": "app-1",
        "log": "reload-log",
        "type": "full",
        "status": "SUCCEEDED",
        "userId": "user-1",
        "weight": 1,
        "endTime": "2024-02-01T10:05:00Z",
        "partial": False,
        "tenantId": "tenant-id",
        "errorCode": "0",
        "errorMessage": None,
        "startTime": "2024-02-01T10:00:00Z",
        "engineTime": "PT5M",
        "creationTime": "2024-02-01T09:59:59Z",
        "createdDate": "2024-02-01T10:00:00Z",
        "modifiedDate": "2024-02-02T11:00:00Z",
        "modifiedByUserName": "user@example.com",
        "ownerId": "owner-1",
        "title": "Nightly Reload",
        "description": "desc",
        "logAvailable": True,
        "operational_id": "op-1",
        "operational_nextExecution": "2024-02-05T12:00:00Z",
        "operational_timesExecuted": 4,
        "operational_state": "SUCCEEDED",
        "operational_hash": "h",
        "links_self_href": "/v1/reloads/reload-1",
        "source": "/api/v1/reloads",
        "tenant": "tenant.example.com",
    }
    cols = _reload_payload_columns(payload)
    assert cols["app_id"] == "app-1"
    assert cols["reload_type"] == "full"
    assert cols["status"] == "SUCCEEDED"
    assert cols["log_available"] is True
    assert cols["operational_state"] == "SUCCEEDED"
    assert cols["operational_times_executed"] == 4
    assert cols["source"] == "/api/v1/reloads"


def test_audit_payload_columns_maps_flat_fields():
    payload = {
        "id": "audit-1",
        "userId": "user-1",
        "eventId": "event-1",
        "tenantId": "tenant-id",
        "eventTime": "2024-02-01T10:00:00.000Z",
        "eventType": "com.qlik.v1.app.accessed",
        "links_self_href": "/api/v1/audits/audit-1",
        "extensions_actor_sub": "subject-1",
        "time": "2024-02-01T10:00:00.000Z",
        "subType": "app.accessed",
        "spaceId": "space-1",
        "spaceType": "shared",
        "category": "app",
        "type": "access",
        "actorId": "user-1",
        "actorType": "user",
        "origin": "qlik-ui",
        "context": "ctx",
        "ipAddress": "127.0.0.1",
        "userAgent": "UA",
        "properties_appId": "app-1",
        "data_message": "ok",
        "source": "/api/v1/audits",
        "tenant": "tenant.example.com",
    }
    cols = _audit_payload_columns(payload)
    assert cols["event_type"] == "com.qlik.v1.app.accessed"
    assert cols["event_id"] == "event-1"
    assert cols["audit_type"] == "access"
    assert cols["properties_app_id"] == "app-1"
    assert cols["actor_id"] == "user-1"
    assert cols["time_ts"] is not None


def test_license_consumption_payload_columns_maps_example_response_fields():
    payload = {
        "id": "consumption-1",
        "appId": "app-1",
        "userId": "user-1",
        "endTime": "2026-03-03T10:00:00Z",
        "duration": "PT30M",
        "sessionId": "sess-1",
        "allotmentId": "allot-1",
        "minutesUsed": 30,
        "capacityUsed": 42,
        "licenseUsage": "analyzer",
        "source": "/api/v1/licenses/consumption",
        "tenant": "tenant.example.com",
    }
    cols = _license_consumption_payload_columns(payload)
    assert cols["app_id_payload"] == "app-1"
    assert cols["user_id"] == "user-1"
    assert cols["session_id"] == "sess-1"
    assert cols["minutes_used"] == 30
    assert cols["capacity_used"] == 42
    assert cols["license_usage"] == "analyzer"


def test_license_status_payload_columns_maps_example_response_fields():
    payload = {
        "type": "professional",
        "trial": False,
        "valid": True,
        "origin": "subscription",
        "status": "active",
        "product": "Qlik Sense Enterprise SaaS",
        "deactivated": False,
        "source": "/api/v1/licenses/status",
        "tenant": "tenant.example.com",
    }
    cols = _license_status_payload_columns(payload)
    assert cols["license_type"] == "professional"
    assert cols["trial"] is False
    assert cols["valid"] is True
    assert cols["status"] == "active"
    assert cols["product"] == "Qlik Sense Enterprise SaaS"


def test_normalize_steps_defaults_to_all_steps():
    assert _normalize_steps(None) == list(FETCH_STEP_ALL_ORDER)


def test_normalize_steps_adds_dependencies_for_app_edges():
    normalized = _normalize_steps(["app-edges"])
    assert normalized == ["apps", "lineage", "app-edges"]


def test_select_apps_for_app_edges_prefers_runtime_lineage_success():
    apps = [
        {"appId": "app-1", "name": "A", "lineageSuccess": True},
        {"appId": "app-2", "name": "B", "lineageSuccess": False},
    ]
    selected, source = _select_apps_for_app_edges(apps)
    assert source == "lineage_step_runtime"
    assert [a["appId"] for a in selected] == ["app-1"]


def test_select_apps_for_app_edges_falls_back_to_all_apps():
    apps = [
        {"appId": "app-1", "name": "A"},
        {"appId": "app-2", "name": "B"},
    ]
    selected, source = _select_apps_for_app_edges(apps, lineage_payloads=[])
    assert source == "fallback_all_apps"
    assert [a["appId"] for a in selected] == ["app-1", "app-2"]
