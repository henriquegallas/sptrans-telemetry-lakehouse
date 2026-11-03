"""Shared fixtures: an in-memory Olho Vivo API plugged into httpx through MockTransport."""

import itertools
import json
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from tenacity import wait_none

from collector.client import OlhoVivoClient, PositionsSnapshot

BASE_URL = "https://api.olhovivo.test/v2.1"


def _vehicle(prefix: int, accessible: bool, ts: str, lat: float, lon: float) -> dict[str, Any]:
    return {"p": prefix, "a": accessible, "ta": ts, "py": lat, "px": lon}


def positions_payload() -> dict[str, Any]:
    """Two lines and three vehicles, in the shape documented for GET /Posicao (v2.1)."""
    return {
        "hr": "22:31",
        "l": [
            {
                "c": "8000-10",
                "cl": 1273,
                "sl": 1,
                "lt0": "PCA. RAMOS DE AZEVEDO",
                "lt1": "TERM. LAPA",
                "qv": 2,
                "vs": [
                    _vehicle(12345, True, "2026-11-04T01:30:59Z", -23.55, -46.63),
                    _vehicle(12346, False, "2026-11-04T01:31:02Z", -23.54, -46.63),
                ],
            },
            {
                "c": "875A-10",
                "cl": 34041,
                "sl": 2,
                "lt0": "PERDIZES",
                "lt1": "AACD-SERVIDOR",
                "qv": 1,
                "vs": [_vehicle(71234, True, "2026-11-04T01:31:10Z", -23.53, -46.67)],
            },
        ],
    }


class FakeOlhoVivo:
    """Behaves like the real API: cookie session, `false` for a bad token, 401 once expired."""

    token = "0123456789abcdef" * 4

    def __init__(self) -> None:
        self.payload = positions_payload()
        self.requests: list[httpx.Request] = []
        self._scripted: dict[str, list[httpx.Response | Exception]] = {"login": [], "positions": []}
        self._sessions: set[str] = set()
        self._session_ids = itertools.count(1)

    def script(self, endpoint: str, *outcomes: httpx.Response | Exception) -> None:
        """Answer `endpoint` ("login" or "positions") with `outcomes` before behaving normally."""
        self._scripted[endpoint].extend(outcomes)

    def expire_sessions(self) -> None:
        self._sessions.clear()

    def calls(self, endpoint: str) -> list[httpx.Request]:
        return [r for r in self.requests if _endpoint(r) == endpoint]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        endpoint = _endpoint(request)
        if self._scripted[endpoint]:
            outcome = self._scripted[endpoint].pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return self._login(request) if endpoint == "login" else self._positions(request)

    def _login(self, request: httpx.Request) -> httpx.Response:
        if request.url.params.get("token") != self.token:
            return httpx.Response(200, json=False)
        session = f"session-{next(self._session_ids)}"
        self._sessions.add(session)
        return httpx.Response(
            200, json=True, headers={"Set-Cookie": f"apiCredentials={session}; Path=/"}
        )

    def _positions(self, request: httpx.Request) -> httpx.Response:
        cookies = dict(
            part.strip().split("=", 1)
            for part in request.headers.get("cookie", "").split(";")
            if "=" in part
        )
        if cookies.get("apiCredentials") not in self._sessions:
            return httpx.Response(
                401, json={"Message": "Authorization has been denied for this request."}
            )
        return httpx.Response(200, json=self.payload)


def _endpoint(request: httpx.Request) -> str:
    return "login" if request.url.path.endswith("/Login/Autenticar") else "positions"


@pytest.fixture
def fake_api() -> FakeOlhoVivo:
    return FakeOlhoVivo()


@pytest.fixture
def make_client(fake_api: FakeOlhoVivo) -> Iterator[Callable[..., OlhoVivoClient]]:
    clients: list[OlhoVivoClient] = []

    def factory(*, token: str = FakeOlhoVivo.token, max_attempts: int = 3) -> OlhoVivoClient:
        client = OlhoVivoClient(
            BASE_URL,
            token,
            timeout_seconds=5,
            max_attempts=max_attempts,
            wait=wait_none(),
            transport=httpx.MockTransport(fake_api),
        )
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.close()


@pytest.fixture
def snapshot() -> PositionsSnapshot:
    return PositionsSnapshot(
        content=json.dumps(positions_payload()).encode(),
        api_time="22:31",
        line_count=2,
        vehicle_count=3,
    )
