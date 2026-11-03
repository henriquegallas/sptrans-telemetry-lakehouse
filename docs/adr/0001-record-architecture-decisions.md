# 1. Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

This project makes several non-obvious trade-offs (local Airflow instead of MWAA, Iceberg instead
of Delta, a standalone collector instead of an Airflow task, zero-cost AWS footprint). The reasoning
behind them should be reviewable without reading the whole codebase or commit history.

## Decision

Record every significant architecture decision as a short ADR in `docs/adr/`, using the format
described by Michael Nygard: context, decision, consequences. Files are numbered sequentially and
never renumbered; a superseded ADR is kept and marked as such.

## Consequences

- Reviewers can follow the "why" of the design in a few minutes.
- Each ADR is small and written when the decision is made, not reconstructed at the end.
