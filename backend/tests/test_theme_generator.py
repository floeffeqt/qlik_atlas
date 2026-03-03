import io
import json
import sys
import zipfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.auth.utils import create_access_token  # type: ignore
from main import app  # type: ignore


def _auth_headers() -> dict[str, str]:
    token = create_access_token("7", role="admin", email="admin@example.com")
    return {"Authorization": f"Bearer {token}"}


def _build_payload() -> dict:
    return {
        "theme_name": "Atlas Ocean",
        "file_basename": "atlas-ocean-prod",
        "qext": {
            "name": "Atlas Ocean",
            "description": "Production theme package",
            "author": "QA",
            "version": "1.0.0",
            "keywords": ["atlas", "blue"],
        },
        "theme_json": {
            "_inherit": True,
            "_variables": {
                "@primaryColor": "#3366ff",
                "@secondaryColor": "#22aa99",
            },
            "object": {
                "title": {"color": "@primaryColor"},
            },
        },
    }


@pytest.mark.asyncio
async def test_theme_build_returns_production_zip_with_only_theme_and_qext():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post("/api/themes/build", json=_build_payload(), headers=_auth_headers())

    assert res.status_code == 200, res.text
    assert res.headers.get("content-type", "").startswith("application/zip")
    assert "attachment;" in res.headers.get("content-disposition", "")

    with zipfile.ZipFile(io.BytesIO(res.content), mode="r") as zf:
        names = set(zf.namelist())
        assert names == {"theme.json", "atlas-ocean-prod.qext"}

        theme_data = json.loads(zf.read("theme.json").decode("utf-8"))
        assert theme_data.get("_inherit") is True
        assert theme_data.get("_variables", {}).get("@primaryColor") == "#3366ff"

        qext_data = json.loads(zf.read("atlas-ocean-prod.qext").decode("utf-8"))
        assert qext_data.get("name") == "Atlas Ocean"
        assert qext_data.get("type") == "theme"
        assert qext_data.get("version") == "1.0.0"


@pytest.mark.asyncio
async def test_theme_build_rejects_non_object_theme_json():
    payload = _build_payload()
    payload["theme_json"] = ["invalid"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post("/api/themes/build", json=payload, headers=_auth_headers())

    assert res.status_code == 422


@pytest.mark.asyncio
async def test_theme_upload_stub_returns_not_implemented():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post("/api/themes/upload", json={"target": "qlik-cloud"}, headers=_auth_headers())

    assert res.status_code == 501
    payload = res.json()
    assert payload.get("status") == "not_implemented"
    assert "not implemented" in payload.get("detail", "").lower()
