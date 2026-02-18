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
