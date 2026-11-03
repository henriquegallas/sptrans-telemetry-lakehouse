"""Client for the SPTrans Olho Vivo API (v2.1)."""

import json
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self

import httpx
import structlog
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)
from tenacity.wait import wait_base

log = structlog.get_logger(__name__)

USER_AGENT = "sptrans-telemetry-lakehouse/0.1 (+https://github.com/henriquegallas/sptrans-telemetry-lakehouse)"
DEFAULT_WAIT = wait_exponential_jitter(initial=1, max=16)


class CollectorError(Exception):
    """Base class for collector failures."""


class AuthenticationError(CollectorError):
    """The API rejected the token. Retrying will not fix it."""


class ApiUnavailableError(CollectorError):
    """The API kept failing after every retry."""


class InvalidPayloadError(CollectorError):
    """The API answered with something that is not the expected JSON document."""


@dataclass(frozen=True, slots=True)
class PositionsSnapshot:
    content: bytes  # body exactly as received; parsing into a schema is bronze's job
    api_time: str  # `hr`: São Paulo local HH:MM of the snapshot, with no date
    line_count: int
    vehicle_count: int


class OlhoVivoClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout_seconds: float,
        max_attempts: int,
        wait: wait_base = DEFAULT_WAIT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._token = token
        self._authenticated = False
        self._http = httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
            # Cloudflare in front of the API answers 403 "error code: 1010" to some default
            # client signatures (Python-urllib), so identify the project explicitly.
            headers={"User-Agent": USER_AGENT},
            transport=transport,
        )
        self._retrying = Retrying(
            stop=stop_after_attempt(max_attempts),
            wait=wait,
            retry=retry_if_exception(_is_transient),
            before_sleep=_log_retry,
            reraise=True,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def fetch_positions(self) -> PositionsSnapshot:
        """GET /Posicao, logging in when needed and retrying transient failures."""
        try:
            return self._retrying(self._fetch_once)
        except (httpx.HTTPError, InvalidPayloadError) as exc:
            # `from None`: httpx errors embed the request URL, and the login URL carries the token.
            raise ApiUnavailableError(_describe(exc)) from None

    def _fetch_once(self) -> PositionsSnapshot:
        if not self._authenticated:
            self._authenticate()
        response = self._http.get("/Posicao")
        if response.status_code == httpx.codes.UNAUTHORIZED:
            # Sessions expire silently; the first sign is a 401 on a data call.
            self._authenticated = False
            self._authenticate()
            response = self._http.get("/Posicao")
        response.raise_for_status()
        return _parse_snapshot(response.content)

    def _authenticate(self) -> None:
        # Without an explicit empty body the API answers 411 Length Required.
        response = self._http.post("/Login/Autenticar", params={"token": self._token}, content=b"")
        response.raise_for_status()
        # A rejected token is HTTP 200 with a JSON `false`, not a 401.
        if _parse_json(response.content) is not True:
            raise AuthenticationError("SPTrans rejected the API token")
        self._authenticated = True
        log.info("api_authenticated")


def _parse_json(content: bytes) -> Any:
    try:
        return json.loads(content)
    except ValueError:
        raise InvalidPayloadError(f"response is not JSON: {content[:80]!r}") from None


def _parse_snapshot(content: bytes) -> PositionsSnapshot:
    payload = _parse_json(content)
    lines = payload.get("l") if isinstance(payload, dict) else None
    if not isinstance(lines, list) or "hr" not in payload:
        raise InvalidPayloadError("unexpected /Posicao payload shape")
    return PositionsSnapshot(
        content=content,
        api_time=str(payload["hr"]),
        line_count=len(lines),
        vehicle_count=sum(len(line.get("vs") or []) for line in lines if isinstance(line, dict)),
    )


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == httpx.codes.TOO_MANY_REQUESTS or status >= 500
    return isinstance(exc, httpx.TransportError | InvalidPayloadError)


def _describe(exc: BaseException) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code} from {exc.request.url.path}"
    return f"{type(exc).__name__}: {exc}"


def _log_retry(state: RetryCallState) -> None:
    exc = state.outcome.exception() if state.outcome else None
    log.warning(
        "api_retry",
        attempt=state.attempt_number,
        sleep_seconds=round(state.upcoming_sleep, 2),
        error=_describe(exc) if exc else None,
    )
