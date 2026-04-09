"""Qlik Engine API client — WebSocket / QIX protocol.

Flow per app:
  1. Connect  wss://{tenant}/app/{appId}  (Authorization: Bearer {api_key})
  2. OpenDoc   → get doc handle
  3. GetScript → get current load script text
  4. Close connection

Design notes:
- Each call opens its own WebSocket connection and closes it afterwards.
- Responses are matched by JSON-RPC ``id``; change notifications are ignored.
- Timeout applies to each individual ``ws.recv()`` wait.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

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


class QlikEngineClient:
    """Minimal QIX client for reading app scripts via the Qlik Engine API."""

    def __init__(
        self,
        creds: QlikCredentials,
        *,
        timeout: float = 30.0,
        logger: Optional[Any] = None,
    ) -> None:
        # Strip scheme so we can build the wss:// URI reliably
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

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _send_and_receive(
        self,
        ws: Any,
        msg_id: int,
        method: str,
        handle: int,
        params: list[Any],
    ) -> dict[str, Any]:
        """Send a JSON-RPC request and return the matching response.

        Ignores change notifications and other push messages until the
        response with the matching ``id`` arrives.
        """
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
                # Change notification or unrelated message — skip
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
