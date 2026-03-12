import sys
from pathlib import Path

from fastapi.routing import APIRoute


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.customers import routes as customer_routes  # type: ignore
from app.models import Customer, Project  # type: ignore
from app.projects import routes as project_routes  # type: ignore


def _route_by_name(router, endpoint_name: str) -> APIRoute:
    for route in router.routes:
        if isinstance(route, APIRoute) and route.endpoint.__name__ == endpoint_name:
            return route
    raise AssertionError(f"route {endpoint_name} not found")


def test_project_out_customer_ref_omits_tenant_url():
    customer = Customer(id=7, name="Acme")
    customer.tenant_url = "https://tenant.example"
    customer.api_key = "secret-key"
    project = Project(id=3, name="Atlas", description="desc", customer_id=7)

    payload = project_routes._to_out(project, customer).model_dump()

    assert payload["customer"] == {"id": 7, "name": "Acme"}
    assert "tenant_url" not in payload["customer"]


def test_customer_out_keeps_admin_fields():
    customer = Customer(id=9, name="Admin Customer", notes="internal")
    customer.tenant_url = "https://tenant.example"
    customer.api_key = "secret-key"

    payload = customer_routes._to_out(customer).model_dump()

    assert payload["tenant_url"] == "https://tenant.example"
    assert payload["api_key_preview"].endswith("key")


def test_customer_list_route_uses_admin_scoped_session():
    route = _route_by_name(customer_routes.router, "list_customers")
    assert route.dependant.dependencies
    assert route.dependant.dependencies[0].call is customer_routes._admin_scoped_session


def test_customer_get_route_uses_admin_scoped_session():
    route = _route_by_name(customer_routes.router, "get_customer")
    assert route.dependant.dependencies
    assert route.dependant.dependencies[0].call is customer_routes._admin_scoped_session
