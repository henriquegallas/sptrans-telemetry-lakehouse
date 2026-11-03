"""Entry point: `python -m collector`."""

import signal
import sys
import threading

import structlog

from collector.client import AuthenticationError, OlhoVivoClient
from collector.config import load_settings
from collector.log import configure_logging
from collector.service import Collector
from collector.storage import LocalRawWriter


def main() -> int:
    settings = load_settings()
    configure_logging(settings.log_level)
    structlog.contextvars.bind_contextvars(service="collector")
    log = structlog.get_logger(__name__)

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    with OlhoVivoClient(
        str(settings.api_base_url),
        settings.api_token.get_secret_value(),
        timeout_seconds=settings.request_timeout_seconds,
        max_attempts=settings.max_attempts,
    ) as client:
        collector = Collector(
            client,
            LocalRawWriter(settings.raw_dir),
            interval_seconds=settings.poll_interval_seconds,
        )
        try:
            collector.run(stop)
        except AuthenticationError as exc:
            log.critical("authentication_failed", error=str(exc))
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
