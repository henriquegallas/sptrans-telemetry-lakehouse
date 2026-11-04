"""Raw landing zone: one gzipped API snapshot per poll, partitioned by UTC collection time."""

import gzip
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

DATASET = "posicao"


def raw_key(collected_at: datetime) -> str:
    """Relative key, e.g. `posicao/dt=2026-11-04/hour=01/posicao_20261104T013100Z.json.gz`."""
    if collected_at.tzinfo is None:
        raise ValueError("collected_at must be timezone-aware")
    ts = collected_at.astimezone(UTC)
    return f"{DATASET}/dt={ts:%Y-%m-%d}/hour={ts:%H}/{DATASET}_{ts:%Y%m%dT%H%M%SZ}.json.gz"


class RawWriter(Protocol):
    def write(self, key: str, content: bytes) -> str:
        """Persist `content` gzipped under `key` and return where it landed."""
        ...


class LocalRawWriter:
    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    def write(self, key: str, content: bytes) -> str:
        target = self._base_dir / key
        target.parent.mkdir(parents=True, exist_ok=True)
        # Spark/Hadoop ignore dot-files, so readers never see a half-written snapshot.
        tmp = target.with_name(f".{target.name}.tmp")
        tmp.write_bytes(gzip.compress(content, compresslevel=6))
        tmp.replace(target)
        return str(target)
