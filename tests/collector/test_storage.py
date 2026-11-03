import gzip
from datetime import UTC, datetime, timedelta, timezone

import pytest

from collector.storage import LocalRawWriter, raw_key

SAO_PAULO = timezone(timedelta(hours=-3))


def test_key_is_partitioned_by_utc_collection_time():
    # 22:31 in São Paulo is already the next day in UTC.
    collected_at = datetime(2026, 11, 3, 22, 31, 5, tzinfo=SAO_PAULO)

    assert raw_key(collected_at) == (
        "posicao/dt=2026-11-04/hour=01/posicao_20261104T013105Z.json.gz"
    )


def test_naive_timestamps_are_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        raw_key(datetime(2026, 11, 4, 1, 31))  # noqa: DTZ001


def test_local_writer_stores_gzipped_content(tmp_path):
    key = raw_key(datetime(2026, 11, 4, 1, 31, tzinfo=UTC))

    location = LocalRawWriter(tmp_path).write(key, b'{"hr": "22:31", "l": []}')

    assert location == str(tmp_path / key)
    assert gzip.decompress((tmp_path / key).read_bytes()) == b'{"hr": "22:31", "l": []}'


def test_local_writer_leaves_no_temporary_files(tmp_path):
    writer = LocalRawWriter(tmp_path)
    for minute in range(3):
        writer.write(raw_key(datetime(2026, 11, 4, 1, minute, tzinfo=UTC)), b"{}")

    files = sorted(p.name for p in tmp_path.rglob("*") if p.is_file())
    assert files == [
        "posicao_20261104T010000Z.json.gz",
        "posicao_20261104T010100Z.json.gz",
        "posicao_20261104T010200Z.json.gz",
    ]
