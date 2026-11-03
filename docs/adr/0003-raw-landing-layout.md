# 3. Raw landing layout: one gzipped snapshot per poll, partitioned by UTC collection time

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

Each poll returns one JSON document with every vehicle in service. Bronze must be able to
reprocess any hour from raw, and the hourly DAG selects its input by Airflow's `data_interval`,
which is in UTC. The payload's own `hr` field is São Paulo local time as `HH:MM`, with no date.

## Decision

- Store each response body **byte for byte**, gzipped, as one file per poll:
  `posicao/dt=YYYY-MM-DD/hour=HH/posicao_<YYYYMMDDTHHMMSSZ>.json.gz`.
- Partition by **UTC collection time**, taken when the response arrives.
- Write to a dot-prefixed temporary file and rename it into place.

## Consequences

- Raw is an exact, replayable record; any parsing bug is fixable by reprocessing, never by
  re-collecting (which is impossible for past positions).
- An hourly run maps to exactly one `dt`/`hour` prefix, so idempotent reprocessing is a matter of
  overwriting that hour's bronze partition.
- Hadoop-based readers skip dot-files, so Spark never sees a partially written snapshot.
- One file per minute means ~1,440 small files a day. That is fine at this volume; bronze compacts
  them into Iceberg files, and a lifecycle rule can expire raw objects on S3.
- Local-time reporting (rush hours) is a presentation concern handled in gold or at query time.
