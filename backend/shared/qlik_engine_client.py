"""Qlik Engine API client — WebSocket / QIX protocol.

Flow per app:
  1. Connect  wss://{tenant}/app/{appId}  (Authorization: Bearer {api_key})
  2. OpenDoc   → get doc handle
  3. Perform Engine calls (GetScript, CreateSessionObject, …)
  4. Close connection

Design notes:
- ``get_script`` opens its own connection for a single call.
- ``open_session`` is an async context manager for multi-step operations
  (master items export/diff/import etc.).
- Responses are matched by JSON-RPC ``id``; change notifications are ignored.
- Timeout applies to each individual ``ws.recv()`` wait.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

import websockets
import websockets.exceptions

from shared.qlik_client import QlikCredentials


def _build_default_logger() -> logging.Logger:
    logger = logging.getLogger("qlik.engine.client")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


class QlikEngineError(RuntimeError):
    """Raised when the Qlik Engine API returns an error or the connection fails."""

    def __init__(self, message: str, app_id: str = "", code: int = 0) -> None:
        super().__init__(message)
        self.app_id = app_id
        self.code = code


class EngineSession:
    """Active multi-call session within a single Qlik Engine WebSocket connection.

    Obtained via ``QlikEngineClient.open_session(app_id)``. Do not instantiate directly.
    """

    def __init__(self, ws: Any, doc_handle: int, app_id: str, client: "QlikEngineClient") -> None:
        self._ws = ws
        self._doc_handle = doc_handle
        self._app_id = app_id
        self._client = client
        self._next_id = 10  # OpenDoc used id=1; start above it

    @property
    def doc_handle(self) -> int:
        return self._doc_handle

    async def _rpc(self, method: str, handle: int, params: list[Any] | None = None) -> dict[str, Any]:
        msg_id = self._next_id
        self._next_id += 1
        return await self._client._send_and_receive(self._ws, msg_id, method, handle, params or [])

    async def create_session_object(self, definition: dict) -> int:
        resp = await self._rpc("CreateSessionObject", self._doc_handle, [definition])
        return resp["result"]["qReturn"]["qHandle"]

    async def get_layout(self, obj_handle: int) -> dict:
        resp = await self._rpc("GetLayout", obj_handle)
        return resp["result"]["qLayout"]

    async def get_properties(self, obj_handle: int) -> dict:
        resp = await self._rpc("GetProperties", obj_handle)
        return resp["result"]["qProp"]

    async def set_properties(self, obj_handle: int, props: dict) -> None:
        await self._rpc("SetProperties", obj_handle, [props])

    async def get_dimension(self, dim_id: str) -> tuple[int, dict]:
        resp = await self._rpc("GetDimension", self._doc_handle, [dim_id])
        handle = resp["result"]["qReturn"]["qHandle"]
        return handle, await self.get_properties(handle)

    async def get_measure(self, measure_id: str) -> tuple[int, dict]:
        resp = await self._rpc("GetMeasure", self._doc_handle, [measure_id])
        handle = resp["result"]["qReturn"]["qHandle"]
        return handle, await self.get_properties(handle)

    async def get_object(self, obj_id: str) -> tuple[int, dict]:
        resp = await self._rpc("GetObject", self._doc_handle, [obj_id])
        handle = resp["result"]["qReturn"]["qHandle"]
        return handle, await self.get_properties(handle)

    async def create_dimension(self, props: dict) -> str:
        resp = await self._rpc("CreateDimension", self._doc_handle, [props])
        return resp["result"]["qReturn"]["qInfo"]["qId"]

    async def create_measure(self, props: dict) -> str:
        resp = await self._rpc("CreateMeasure", self._doc_handle, [props])
        return resp["result"]["qReturn"]["qInfo"]["qId"]

    async def create_object(self, props: dict) -> str:
        resp = await self._rpc("CreateObject", self._doc_handle, [props])
        return resp["result"]["qReturn"]["qInfo"]["qId"]

    async def do_save(self) -> None:
        await self._rpc("DoSave", self._doc_handle)


class QlikEngineClient:
    """QIX client for the Qlik Engine API.

    Use ``get_script`` for a one-shot script fetch, or ``open_session`` as
    an async context manager for multi-step operations.
    """

    def __init__(
        self,
        creds: QlikCredentials,
        *,
        timeout: float = 30.0,
        logger: Optional[Any] = None,
    ) -> None:
        host = creds.tenant_url.rstrip("/")
        for prefix in ("https://", "http://"):
            if host.startswith(prefix):
                host = host[len(prefix):]
                break
        self._tenant_host = host
        self._api_key = creds.api_key
        self._timeout = timeout
        self._logger = logger or _build_default_logger()

    # ── Public interface ──────────────────────────────────────────────────────

    async def get_script(self, app_id: str) -> str:
        """Return the current load script for *app_id* via the Engine API."""
        uri = f"wss://{self._tenant_host}/app/{app_id}"
        headers = [("Authorization", f"Bearer {self._api_key}")]
        self._logger.info("Engine: connecting to %s", uri)
        try:
            async with websockets.connect(
                uri,
                extra_headers=headers,
                open_timeout=self._timeout,
                close_timeout=5,
            ) as ws:
                handle = await self._open_doc(ws, app_id)
                script = await self._get_script(ws, handle)
                self._logger.info("Engine: GetScript %s -> %d chars", app_id, len(script))
                return script
        except QlikEngineError:
            raise
        except websockets.exceptions.WebSocketException as exc:
            raise QlikEngineError(
                f"WebSocket error for app {app_id}: {exc}", app_id=app_id
            ) from exc
        except asyncio.TimeoutError as exc:
            raise QlikEngineError(
                f"Timeout waiting for Engine response for app {app_id}", app_id=app_id
            ) from exc
        except Exception as exc:
            raise QlikEngineError(
                f"Engine connection failed for app {app_id}: {exc}", app_id=app_id
            ) from exc

    @asynccontextmanager
    async def open_session(self, app_id: str) -> AsyncIterator[EngineSession]:
        """Open a WebSocket, OpenDoc, yield an EngineSession, then close.

        Use for multi-step operations (master items, custom RPC sequences).
        ``QlikEngineError`` propagates to the caller; connection is always closed.
        """
        uri = f"wss://{self._tenant_host}/app/{app_id}"
        headers = [("Authorization", f"Bearer {self._api_key}")]
        self._logger.info("Engine: open_session %s", uri)
        try:
            async with websockets.connect(
                uri,
                extra_headers=headers,
                open_timeout=self._timeout,
                close_timeout=5,
            ) as ws:
                handle = await self._open_doc(ws, app_id)
                yield EngineSession(ws, handle, app_id, self)
                self._logger.info("Engine: session closed for %s", app_id)
        except QlikEngineError:
            raise
        except websockets.exceptions.WebSocketException as exc:
            raise QlikEngineError(
                f"WebSocket error for app {app_id}: {exc}", app_id=app_id
            ) from exc
        except asyncio.TimeoutError as exc:
            raise QlikEngineError(
                f"Timeout waiting for Engine response for app {app_id}", app_id=app_id
            ) from exc

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _send_and_receive(
        self,
        ws: Any,
        msg_id: int,
        method: str,
        handle: int,
        params: list[Any],
    ) -> dict[str, Any]:
        """Send a JSON-RPC request and return the matching response."""
        await ws.send(json.dumps({
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "handle": handle,
            "params": params,
        }))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=self._timeout)
            msg = json.loads(raw)
            if msg.get("id") != msg_id:
                continue
            if "error" in msg:
                err = msg["error"]
                raise QlikEngineError(
                    f"{method} error: {err.get('message', str(err))} "
                    f"(code {err.get('code', '?')})",
                    code=int(err.get("code", 0)),
                )
            return msg

    async def _open_doc(self, ws: Any, app_id: str) -> int:
        resp = await self._send_and_receive(ws, 1, "OpenDoc", -1, [app_id])
        handle: int = resp["result"]["qReturn"]["qHandle"]
        self._logger.info("Engine: OpenDoc %s -> handle=%d", app_id, handle)
        return handle

    async def _get_script(self, ws: Any, handle: int) -> str:
        resp = await self._send_and_receive(ws, 2, "GetScript", handle, [])
        return resp["result"]["qScript"]
