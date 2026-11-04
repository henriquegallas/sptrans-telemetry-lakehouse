import gzip
import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
from structlog.testing import capture_logs

from collector.client import ApiUnavailableError, AuthenticationError, PositionsSnapshot
from collector.service import Collector, next_tick
from collector.storage import LocalRawWriter

T0 = datetime(2026, 11, 4, 1, 31, tzinfo=UTC)


class ScriptedSource:
    """Returns or raises each outcome in turn and sets `stop` once the script runs out."""

    def __init__(self, outcomes: list[PositionsSnapshot | Exception], stop: threading.Event):
        self._outcomes = outcomes
        self._stop = stop

    def fetch_positions(self) -> PositionsSnapshot:
        outcome = self._outcomes.pop(0)
        if not self._outcomes:
            self._stop.set()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def minute_clock():
    ticks = (T0 + timedelta(minutes=i) for i in range(1000))
    return lambda: next(ticks)


def test_poll_once_lands_snapshot_and_logs_counts(tmp_path, snapshot):
    collector = Collector(
        ScriptedSource([snapshot], threading.Event()),
        LocalRawWriter(tmp_path),
        interval_seconds=60,
        clock=lambda: T0,
    )

    with capture_logs() as logs:
        location = collector.poll_once()

    expected = tmp_path / "posicao/dt=2026-11-04/hour=01/posicao_20261104T013100Z.json.gz"
    assert location == str(expected)
    assert gzip.decompress(expected.read_bytes()) == snapshot.content
    assert logs[0]["event"] == "snapshot_written"
    assert (logs[0]["lines"], logs[0]["vehicles"]) == (2, 3)


def test_run_survives_an_api_outage(tmp_path, snapshot):
    stop = threading.Event()
    source = ScriptedSource([snapshot, ApiUnavailableError("HTTP 503"), snapshot], stop)
    collector = Collector(
        source, LocalRawWriter(tmp_path), interval_seconds=0.001, clock=minute_clock()
    )

    with capture_logs() as logs:
        collector.run(stop)

    assert len(list(tmp_path.rglob("*.json.gz"))) == 2
    assert [e["event"] for e in logs if e["log_level"] == "error"] == ["poll_failed"]


def test_run_stops_on_rejected_token(tmp_path):
    stop = threading.Event()
    source = ScriptedSource([AuthenticationError("rejected")], stop)
    collector = Collector(source, LocalRawWriter(tmp_path), interval_seconds=0.001)

    with pytest.raises(AuthenticationError):
        collector.run(stop)


def test_run_returns_promptly_when_stopped_mid_wait(tmp_path, snapshot):
    stop = threading.Event()
    source = ScriptedSource([snapshot, snapshot], stop=threading.Event())
    collector = Collector(source, LocalRawWriter(tmp_path), interval_seconds=60)
    threading.Timer(0.1, stop.set).start()

    started = time.monotonic()
    collector.run(stop)

    assert time.monotonic() - started < 5


@pytest.mark.parametrize(
    ("previous", "now", "expected"),
    [
        (0, 1, 60),  # normal: next tick one interval later
        (0, 59.9, 60),  # slow poll, still on schedule
        (0, 130, 180),  # poll overran two ticks: skip them, no burst
    ],
)
def test_next_tick_keeps_a_fixed_rate(previous, now, expected):
    assert next_tick(previous, now, interval=60) == expected
