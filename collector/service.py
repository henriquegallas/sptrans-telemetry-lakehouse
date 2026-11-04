"""Fixed-rate polling loop that lands one raw snapshot per tick."""

import math
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

import structlog

from collector.client import ApiUnavailableError, PositionsSnapshot
from collector.storage import RawWriter, raw_key

log = structlog.get_logger(__name__)


class PositionsSource(Protocol):
    def fetch_positions(self) -> PositionsSnapshot: ...


def utc_now() -> datetime:
    return datetime.now(UTC)


def next_tick(previous: float, now: float, interval: float) -> float:
    """Fixed rate, not fixed delay: ticks stay `interval` apart however long a poll takes.

    Ticks missed while a poll was stuck retrying are skipped instead of fired in a burst.
    """
    tick = previous + interval
    if tick < now:
        tick += math.ceil((now - tick) / interval) * interval
    return tick


class Collector:
    def __init__(
        self,
        source: PositionsSource,
        writer: RawWriter,
        *,
        interval_seconds: float,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._source = source
        self._writer = writer
        self._interval = interval_seconds
        self._clock = clock

    def poll_once(self) -> str:
        snapshot = self._source.fetch_positions()
        location = self._writer.write(raw_key(self._clock()), snapshot.content)
        log.info(
            "snapshot_written",
            location=location,
            api_time=snapshot.api_time,
            lines=snapshot.line_count,
            vehicles=snapshot.vehicle_count,
            size_bytes=len(snapshot.content),
        )
        return location

    def run(self, stop: threading.Event) -> None:
        """Poll until `stop` is set. AuthenticationError propagates: it needs a human."""
        log.info("collector_started", interval_seconds=self._interval)
        tick = time.monotonic()
        while not stop.is_set():
            try:
                self.poll_once()
            except (ApiUnavailableError, OSError) as exc:
                # Losing one snapshot is acceptable; the next tick tries again.
                log.error("poll_failed", error=str(exc))
            tick = next_tick(tick, time.monotonic(), self._interval)
            stop.wait(max(0.0, tick - time.monotonic()))
        log.info("collector_stopped")
