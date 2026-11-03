# 2. Standalone collector service instead of an Airflow task

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

The Olho Vivo API only exposes the *current* position of each bus; history exists only if someone
polls it. A one-minute cadence is needed for meaningful speed and stop metrics. Airflow is already in
the stack and could schedule a task every minute.

## Decision

Run ingestion as a small, always-on Python service in Docker Compose, separate from Airflow. It
polls at a fixed rate, retries transient failures with exponential backoff, and only writes immutable
raw files. Airflow takes over from there with an hourly batch DAG.

## Consequences

- Airflow is built for batch orchestration: per-task scheduling overhead of several seconds, a
  metadata-database row per run (1,440 a day) and scheduler restarts would all eat into a 60-second
  budget and leave gaps in the data.
- Ingestion keeps running while Airflow is down, being upgraded or backfilling; the two only meet at
  the raw zone, which makes reprocessing independent of collection.
- The collector needs its own operability: JSON logs, a restart policy, and (in production) an alert
  on missing snapshots. See "What I would do in production" in the README.
