import httpx
import pytest
from structlog.testing import capture_logs

from collector.client import USER_AGENT, ApiUnavailableError, AuthenticationError


def test_logs_in_then_returns_snapshot(fake_api, make_client):
    snapshot = make_client().fetch_positions()

    assert snapshot.api_time == "22:31"
    assert (snapshot.line_count, snapshot.vehicle_count) == (2, 3)
    assert [r.url.path for r in fake_api.requests] == ["/v2.1/Login/Autenticar", "/v2.1/Posicao"]


def test_body_is_kept_byte_for_byte(fake_api, make_client):
    client = make_client()
    client.fetch_positions()
    raw = b'{"hr": "22:32",  "l": []}\n'  # spacing a re-serialisation would not preserve
    fake_api.script("positions", httpx.Response(200, content=raw))

    assert client.fetch_positions().content == raw


def test_login_request_matches_what_the_api_accepts(fake_api, make_client):
    make_client().fetch_positions()

    login = fake_api.calls("login")[0]
    assert login.method == "POST"
    assert login.url.params["token"] == fake_api.token
    assert login.headers["content-length"] == "0"
    assert login.headers["user-agent"] == USER_AGENT


def test_session_is_reused_across_polls(fake_api, make_client):
    client = make_client()
    client.fetch_positions()
    client.fetch_positions()

    assert len(fake_api.calls("login")) == 1
    assert len(fake_api.calls("positions")) == 2


def test_expired_session_triggers_a_new_login(fake_api, make_client):
    client = make_client()
    client.fetch_positions()
    fake_api.expire_sessions()

    assert client.fetch_positions().vehicle_count == 3
    assert len(fake_api.calls("login")) == 2


def test_rejected_token_fails_fast_without_retrying(fake_api, make_client):
    with pytest.raises(AuthenticationError):
        make_client(token="not-the-token").fetch_positions()

    assert len(fake_api.calls("login")) == 1


@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(503),
        httpx.Response(429),
        httpx.ConnectError("connection refused"),
        httpx.ReadTimeout("timed out"),
        httpx.Response(200, content=b"<html>maintenance</html>"),
    ],
    ids=["503", "429", "connect-error", "read-timeout", "not-json"],
)
def test_transient_failures_are_retried(fake_api, make_client, failure):
    fake_api.script("positions", failure)

    assert make_client().fetch_positions().vehicle_count == 3
    assert len(fake_api.calls("positions")) == 2


def test_gives_up_after_max_attempts(fake_api, make_client):
    fake_api.script("positions", *(httpx.Response(503) for _ in range(3)))

    with pytest.raises(ApiUnavailableError, match=r"HTTP 503 from /v2\.1/Posicao"):
        make_client(max_attempts=3).fetch_positions()
    assert len(fake_api.calls("positions")) == 3


def test_client_errors_are_not_retried(fake_api, make_client):
    fake_api.script("positions", httpx.Response(403, text="error code: 1010"))

    with pytest.raises(ApiUnavailableError, match="HTTP 403"):
        make_client().fetch_positions()
    assert len(fake_api.calls("positions")) == 1


def test_token_never_reaches_errors_or_logs(fake_api, make_client):
    fake_api.script("login", *(httpx.Response(500) for _ in range(3)))

    with capture_logs() as logs, pytest.raises(ApiUnavailableError) as excinfo:
        make_client(max_attempts=3).fetch_positions()

    assert fake_api.token not in str(excinfo.value)
    assert excinfo.value.__suppress_context__
    assert [entry["event"] for entry in logs] == ["api_retry", "api_retry"]
    assert fake_api.token not in repr(logs)
