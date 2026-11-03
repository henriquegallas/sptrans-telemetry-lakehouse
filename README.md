# SPTrans Telemetry Lakehouse

[![CI](https://github.com/henriquegallas/sptrans-telemetry-lakehouse/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/henriquegallas/sptrans-telemetry-lakehouse/actions/workflows/ci.yml)

> **Work in progress.** The project is being built in phases — see the [roadmap](#roadmap).

Continuously collects the GPS position of every bus running in São Paulo from the SPTrans
**Olho Vivo** API and turns it into a bronze/silver/gold lakehouse on **Apache Iceberg**, processed
with **PySpark** and orchestrated by **Airflow**. The gold layer exposes hourly operational metrics
per bus line — average speed, active fleet and long stops — queryable with **Athena** or locally,
at zero (or a few cents of) cloud cost.

## Architecture

```mermaid
flowchart LR
    API[SPTrans Olho Vivo API] -->|every 60 s| COL[collector]
    COL --> RAW[(raw<br/>JSON.gz by dt/hour)]
    GTFS[SPTrans static GTFS] --> SIL

    subgraph DAG[Airflow · hourly DAG]
        BRZ[bronze] --> SIL[silver] --> GLD[gold]
        DQ{{data quality checks<br/>fail the DAG}}
        SIL -.-> DQ
        GLD -.-> DQ
    end

    RAW --> BRZ
    GLD --> ICE[(Iceberg tables)]
    ICE --> ATH[Athena + Glue Data Catalog<br/>ENV=aws]
    ICE --> LOC[DuckDB / Spark SQL<br/>ENV=local]
```

The whole pipeline runs **100% locally** (`ENV=local`). AWS is an alternative mode (`ENV=aws`)
that only uses pay-per-use services with tiny volumes: S3, Glue Data Catalog, Athena and IAM.

## Stack

| Layer | Choice | Why |
|---|---|---|
| Language & tooling | Python 3.12, uv, ruff, pytest | Fast, reproducible environments from a single lockfile. |
| Processing | Spark 4 / PySpark (`local[*]`) | Same code runs locally and on EMR Serverless / Glue; no cluster bill. |
| Table format | Apache Iceberg | Athena and the Glue Data Catalog read it natively; partition overwrite and `MERGE` make reprocessing idempotent. |
| Orchestration | Airflow 3 on Docker Compose | Full Airflow semantics (backfill, `data_interval`) without paying for an always-on MWAA environment. |
| Ingestion | Lightweight Python collector | Polling an API every minute is a service's job, not a scheduler's. |
| Infrastructure | Terraform | Every AWS resource is created — and destroyed — as code, starting with a US$ 1 budget alert. |

Architecture decisions are recorded as ADRs in [`docs/adr/`](docs/adr/).

## Running locally

Requirements: [uv](https://docs.astral.sh/uv/) and `make` (Linux, macOS or WSL2).
Docker and Java are added as the pipeline phases land.

```bash
uv sync          # create .venv with the pinned Python and dev tools
cp .env.example .env
make check       # lint + tests
```

Run `make help` to list every target.

## Running on AWS

_Coming in phase 7: Terraform (budget alert first), Glue Data Catalog + S3, Athena workgroup with a
scan limit, and expected costs._

## Data model

| Layer | Table | Grain |
|---|---|---|
| Bronze | `bronze.bus_positions_raw` | One row per vehicle per API snapshot, as received, plus ingestion metadata. |
| Silver | `silver.bus_positions` | One deduplicated position per `(vehicle_id, position_ts_utc)`, with speed and GTFS enrichment. |
| Gold | `gold.line_speed_hourly` | Average / p50 / p90 speed per line, direction and hour. |
| Gold | `gold.active_fleet_hourly` | Distinct vehicles per line and hour. |
| Gold | `gold.long_stops` | Periods where a vehicle stayed still for more than 5 minutes. |

_Column-level documentation will be added as each layer is implemented._

## Repository layout

```
collector/        SPTrans Olho Vivo collector service
spark_jobs/       PySpark jobs: common/, bronze/, silver/, gold/
dags/             Airflow DAGs
quality/          Data quality suites
infra/terraform/  AWS resources
docker/           Dockerfiles (Airflow, collector)
tests/            Unit and integration tests
docs/             Diagrams and ADRs
```

## Roadmap

- [ ] **Phase 0 — Setup:** repository, uv, ruff, pytest, Makefile, CI
- [ ] **Phase 1 — Collector:** authentication, 60 s polling, retry with backoff, partitioned JSON.gz
- [ ] **Phase 2 — Bronze:** raw → Iceberg
- [ ] **Phase 3 — Silver:** cleaning, deduplication, speed, GTFS enrichment
- [ ] **Phase 4 — Gold:** hourly metrics tables
- [ ] **Phase 5 — Airflow:** hourly DAG, idempotency, backfill
- [ ] **Phase 6 — Data quality:** checks that fail the DAG
- [ ] **Phase 7 — AWS:** Terraform, Glue Catalog, S3, Athena
- [ ] **Phase 8 — Polish:** docs, example queries, ADRs
- [ ] **Phase 9 — Streaming (optional):** Redpanda + Spark Structured Streaming

## Development workflow

Branches follow `feature/<name>` off `development`; commits follow
[Conventional Commits](https://www.conventionalcommits.org/). `make check` (lint + tests) must pass
before every commit; CI runs the same Makefile targets, so a green `make check` means a green build.

## License

[MIT](LICENSE)
