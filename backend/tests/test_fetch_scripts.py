"""Tests for the 'scripts' fetch step.

Covers:
- _run_scripts_step: payload structure, concurrency, per-app error handling
- _run_db_store_step: scripts_data parameter exists
- contracts: 'scripts' step ordering and dependency injection
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.fetch_jobs.runtime import _run_scripts_step  # type: ignore
from shared.qlik_client import QlikCredentials  # type: ignore
from shared.qlik_engine_client import QlikEngineError  # type: ignore


# ── Fake Engine Client ────────────────────────────────────────────────────────

class _FakeEngineClient:
    """Minimal QlikEngineClient stand-in."""

    def __init__(self, scripts: dict[str, str], fail_ids: set[str] | None = None):
        self._scripts = scripts
        self._fail_ids = fail_ids or set()
        self._logger = _FakeLogger()

    async def get_script(self, app_id: str) -> str:
        if app_id in self._fail_ids:
            raise QlikEngineError(f"simulated engine error for {app_id}", app_id=app_id)
        if app_id not in self._scripts:
            raise QlikEngineError(f"app {app_id} not found", app_id=app_id)
        return self._scripts[app_id]


class _FakeLogger:
    def info(self, *a, **kw): pass
    def warning(self, *a, **kw): pass
    def error(self, *a, **kw): pass


_CREDS = QlikCredentials(tenant_url="https://tenant.example.com", api_key="test-key")


# ── _run_scripts_step tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_scripts_step_basic_payload():
    apps = [{"appId": "app-1"}, {"appId": "app-2"}]
    fake_scripts = {
        "app-1": "LOAD * FROM [lib://Data/file.qvd];",
        "app-2": "SET ThousandSep='.';",
    }

    with patch("app.fetch_jobs.runtime._build_engine_client", return_value=_FakeEngineClient(fake_scripts)):
        payloads, meta = await _run_scripts_step(apps, _CREDS)

    assert meta["apps"] == 2
    assert meta["success"] == 2
    assert meta["failed"] == 0
    assert meta["storage"] == "db-first-memory"
    assert meta["localArtifactWritten"] is False

    by_id = {p["app_id"]: p for p in payloads}
    assert by_id["app-1"]["script"] == "LOAD * FROM [lib://Data/file.qvd];"
    assert by_id["app-1"]["source"] == "qlik_engine"
    assert by_id["app-1"]["data"]["length"] == len("LOAD * FROM [lib://Data/file.qvd];")
    assert by_id["app-2"]["script"] == "SET ThousandSep='.';"


@pytest.mark.asyncio
async def test_run_scripts_step_empty_apps():
    with patch("app.fetch_jobs.runtime._build_engine_client", return_value=_FakeEngineClient({})):
        payloads, meta = await _run_scripts_step([], _CREDS)

    assert payloads == []
    assert meta["apps"] == 0
    assert meta["success"] == 0
    assert meta["failed"] == 0


@pytest.mark.asyncio
async def test_run_scripts_step_skips_apps_without_app_id():
    apps = [{"appId": "app-1"}, {"no_id": True}, {}]
    fake_scripts = {"app-1": "LOAD * INLINE [];"}

    with patch("app.fetch_jobs.runtime._build_engine_client", return_value=_FakeEngineClient(fake_scripts)):
        payloads, meta = await _run_scripts_step(apps, _CREDS)

    assert meta["apps"] == 1
    assert meta["success"] == 1
    assert len(payloads) == 1
    assert payloads[0]["app_id"] == "app-1"


@pytest.mark.asyncio
async def test_run_scripts_step_handles_per_app_errors():
    apps = [{"appId": "app-ok"}, {"appId": "app-fail"}]
    fake_scripts = {"app-ok": "LOAD * INLINE [];"}

    with patch("app.fetch_jobs.runtime._build_engine_client",
               return_value=_FakeEngineClient(fake_scripts, fail_ids={"app-fail"})):
        payloads, meta = await _run_scripts_step(apps, _CREDS)

    assert meta["apps"] == 2
    assert meta["success"] == 1
    assert meta["failed"] == 1
    assert len(payloads) == 1
    assert payloads[0]["app_id"] == "app-ok"


@pytest.mark.asyncio
async def test_run_scripts_step_all_fail():
    apps = [{"appId": "app-1"}, {"appId": "app-2"}]

    with patch("app.fetch_jobs.runtime._build_engine_client",
               return_value=_FakeEngineClient({}, fail_ids={"app-1", "app-2"})):
        payloads, meta = await _run_scripts_step(apps, _CREDS)

    assert payloads == []
    assert meta["success"] == 0
    assert meta["failed"] == 2


# ── store / contracts tests ───────────────────────────────────────────────────

def test_run_db_store_step_scripts_parameter_exists():
    from app.fetch_jobs import store as store_module  # type: ignore
    import inspect
    sig = inspect.signature(store_module._run_db_store_step)
    assert "scripts_data" in sig.parameters


def test_contracts_scripts_step_in_all_orders():
    from app.fetch_jobs.contracts import (  # type: ignore
        FETCH_STEP_ALL_ORDER,
        FETCH_STEP_ORDER,
        INDEPENDENT_FETCH_STEPS,
    )
    assert "scripts" in FETCH_STEP_ORDER
    assert "scripts" in FETCH_STEP_ALL_ORDER
    assert "scripts" not in INDEPENDENT_FETCH_STEPS


def test_contracts_normalize_steps_adds_apps_dependency():
    from app.fetch_jobs.contracts import _normalize_steps  # type: ignore
    normalized = _normalize_steps(["scripts"])
    assert "apps" in normalized
    assert "scripts" in normalized
