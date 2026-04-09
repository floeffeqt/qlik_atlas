import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import httpx


LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def _build_default_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def resolve_logger(logger: Optional[Any], default_name: str) -> Any:
    if isinstance(logger, logging.Logger):
        return logger
    return _build_default_logger(default_name)


class QlikApiError(RuntimeError):
    def __init__(self, status_code: int, message: str, response_text: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


@dataclass(frozen=True)
class QlikCredentials:
    """Immutable credentials container — pass by reference, never store in os.environ."""

    tenant_url: str
    api_key: str


@dataclass
class QlikClient:
    base_url: str
    api_key: str
    timeout: float = 30.0
    max_retries: int = 5
    logger: Optional[Any] = None

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        self.logger = resolve_logger(self.logger, "qlik.fetch.client")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=httpx.Timeout(self.timeout),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Tuple[Any, int]:
        retryable_statuses = {429} | set(range(500, 600))
        attempt = 0
        logger = self.logger

        while True:
            attempt += 1
            logger.info("GET %s attempt=%s params=%s", path, attempt, params or {})
            try:
                resp = await self._client.get(path, params=params)
            except httpx.HTTPError as exc:
                if attempt > self.max_retries:
                    logger.error("GET %s failed after retries: %s", path, exc)
                    raise QlikApiError(0, f"HTTP error after retries: {exc}") from exc
                logger.warning("GET %s http error, retrying: %s", path, exc)
                await self._sleep_backoff(attempt)
                continue

            if resp.status_code in retryable_statuses:
                if attempt > self.max_retries:
                    logger.error("GET %s max retries reached with status=%s", path, resp.status_code)
                    raise QlikApiError(resp.status_code, "Max retries reached", resp.text)
                logger.warning("GET %s retryable status=%s", path, resp.status_code)
                await self._sleep_backoff(attempt, resp)
                continue

            if resp.status_code >= 400:
                logger.error("GET %s failed status=%s", path, resp.status_code)
                raise QlikApiError(resp.status_code, f"HTTP {resp.status_code}", resp.text)

            if not resp.content:
                logger.info("GET %s -> %s (empty body)", path, resp.status_code)
                return None, resp.status_code

            try:
                logger.info("GET %s -> %s", path, resp.status_code)
                return resp.json(), resp.status_code
            except ValueError as exc:
                logger.error("GET %s returned invalid JSON (status=%s)", path, resp.status_code)
                raise QlikApiError(resp.status_code, "Invalid JSON response", resp.text) from exc

    async def post_json(
        self,
        path: str,
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, int]:
        retryable_statuses = {429} | set(range(500, 600))
        attempt = 0
        logger = self.logger

        while True:
            attempt += 1
            logger.info("POST %s attempt=%s", path, attempt)
            try:
                resp = await self._client.post(path, json=json_body, params=params)
            except httpx.HTTPError as exc:
                if attempt > self.max_retries:
                    logger.error("POST %s failed after retries: %s", path, exc)
                    raise QlikApiError(0, f"HTTP error after retries: {exc}") from exc
                logger.warning("POST %s http error, retrying: %s", path, exc)
                await self._sleep_backoff(attempt)
                continue

            if resp.status_code in retryable_statuses:
                if attempt > self.max_retries:
                    logger.error("POST %s max retries reached status=%s", path, resp.status_code)
                    raise QlikApiError(resp.status_code, "Max retries reached", resp.text)
                logger.warning("POST %s retryable status=%s", path, resp.status_code)
                await self._sleep_backoff(attempt, resp)
                continue

            if resp.status_code >= 400:
                logger.error("POST %s failed status=%s body=%s", path, resp.status_code, resp.text[:500])
                raise QlikApiError(resp.status_code, f"HTTP {resp.status_code}", resp.text)

            if not resp.content:
                logger.info("POST %s -> %s (empty body)", path, resp.status_code)
                return None, resp.status_code

            try:
                logger.info("POST %s -> %s", path, resp.status_code)
                return resp.json(), resp.status_code
            except ValueError:
                logger.info("POST %s -> %s (non-JSON body)", path, resp.status_code)
                return resp.text, resp.status_code

    async def get_text(self, path: str, params: Optional[Dict[str, Any]] = None) -> Tuple[str, int]:
        """GET returning plain text (e.g. script content)."""
        attempt = 0
        logger = self.logger
        retryable_statuses = {429} | set(range(500, 600))

        while True:
            attempt += 1
            logger.info("GET(text) %s attempt=%s", path, attempt)
            try:
                resp = await self._client.get(path, params=params)
            except httpx.HTTPError as exc:
                if attempt > self.max_retries:
                    raise QlikApiError(0, f"HTTP error after retries: {exc}") from exc
                await self._sleep_backoff(attempt)
                continue

            if resp.status_code in retryable_statuses:
                if attempt > self.max_retries:
                    raise QlikApiError(resp.status_code, "Max retries reached", resp.text)
                await self._sleep_backoff(attempt, resp)
                continue

            if resp.status_code >= 400:
                raise QlikApiError(resp.status_code, f"HTTP {resp.status_code}", resp.text)

            # Guard: reject HTML responses (login-page redirects, CDN catch-alls, etc.)
            content_type = resp.headers.get("content-type", "")
            text = resp.text
            if "text/html" in content_type or text.lstrip().lower().startswith("<!doctype html"):
                raise QlikApiError(
                    resp.status_code,
                    f"Expected plain text but received HTML (content-type: {content_type!r}). "
                    "Check tenant URL and API key.",
                    text[:200],
                )

            logger.info("GET(text) %s -> %s", path, resp.status_code)
            return text, resp.status_code

    async def post_file(
        self,
        path: str,
        file_content: bytes,
        file_name: str = "file.zip",
        mime_type: str = "application/zip",
        params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, int]:
        """POST a file as multipart/form-data."""
        retryable_statuses = {429} | set(range(500, 600))
        attempt = 0
        logger = self.logger

        while True:
            attempt += 1
            logger.info("POST(file) %s attempt=%s filename=%s", path, attempt, file_name)
            try:
                files = {"file": (file_name, file_content, mime_type)}
                resp = await self._client.post(path, files=files, params=params)
            except httpx.HTTPError as exc:
                if attempt > self.max_retries:
                    logger.error("POST(file) %s failed after retries: %s", path, exc)
                    raise QlikApiError(0, f"HTTP error after retries: {exc}") from exc
                logger.warning("POST(file) %s http error, retrying: %s", path, exc)
                await self._sleep_backoff(attempt)
                continue

            if resp.status_code in retryable_statuses:
                if attempt > self.max_retries:
                    logger.error("POST(file) %s max retries status=%s", path, resp.status_code)
                    raise QlikApiError(resp.status_code, "Max retries reached", resp.text)
                logger.warning("POST(file) %s retryable status=%s", path, resp.status_code)
                await self._sleep_backoff(attempt, resp)
                continue

            if resp.status_code >= 400:
                logger.error("POST(file) %s failed status=%s body=%s", path, resp.status_code, resp.text[:500])
                raise QlikApiError(resp.status_code, f"HTTP {resp.status_code}", resp.text)

            if not resp.content:
                logger.info("POST(file) %s -> %s (empty body)", path, resp.status_code)
                return None, resp.status_code

            try:
                logger.info("POST(file) %s -> %s", path, resp.status_code)
                return resp.json(), resp.status_code
            except ValueError:
                logger.info("POST(file) %s -> %s (non-JSON body)", path, resp.status_code)
                return resp.text, resp.status_code

    async def _sleep_backoff(self, attempt: int, resp: Optional[httpx.Response] = None) -> None:
        logger = self.logger
        retry_after = None
        if resp is not None:
            retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                delay = float(retry_after)
                logger.info("Backoff using Retry-After=%s seconds (attempt=%s)", delay, attempt)
                await asyncio.sleep(delay)
                return
            except ValueError:
                pass

        base = 0.5
        cap = 10.0
        delay = min(cap, base * (2 ** (attempt - 1)))
        jitter = random.uniform(0, 0.5)
        total_delay = delay + jitter
        logger.info("Backoff sleep %.2fs (attempt=%s)", total_delay, attempt)
        await asyncio.sleep(total_delay)
