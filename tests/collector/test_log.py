import json
import logging

import pytest
import structlog

from collector.log import configure_logging


@pytest.fixture
def restore_structlog():
    yield
    structlog.reset_defaults()


@pytest.mark.usefixtures("restore_structlog")
def test_emits_one_json_object_per_event(capsys):
    configure_logging("INFO")

    structlog.get_logger().info("snapshot_written", vehicles=3)
    structlog.get_logger().debug("filtered_out")

    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["event"] == "snapshot_written"
    assert event["vehicles"] == 3
    assert event["level"] == "info"
    assert event["timestamp"].endswith("Z")


@pytest.mark.usefixtures("restore_structlog")
def test_silences_httpx_request_logging_because_urls_carry_the_token():
    configure_logging("DEBUG")

    assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
