# 0001. Record architecture decisions

Date: 2026-07-31

## Status

Accepted

## Context

This project is intended to be refined over years rather than finished and abandoned. The
decisions that will matter most — how memory is stored, how clients reach it, what runs
locally — are being made now, while the reasoning is fresh and the alternatives are still
visible. In six months the code will show what was chosen but not why, and not what was
rejected.

Design rationale that lives only in a person's head is lost on the first long gap between
working sessions.

## Decision

Architecture decisions that are expensive to reverse are recorded as numbered markdown files
in `docs/adr`, written before the corresponding code is merged. Records are immutable once
accepted; a changed decision produces a new record that supersedes the old one.

## Consequences

Every significant decision costs an extra thirty minutes of writing. That is the price, and
it is real. In exchange, the repository carries its own reasoning, contradictions between
past and present intent become visible instead of silent, and the discipline of writing the
alternatives down tends to expose weak decisions before they are implemented.

The main risk is over-application: an ADR for every choice would turn into bureaucracy that
gets abandoned. The threshold is reversibility, not importance.

## Alternatives considered

**Nothing.** Rely on commit messages and memory. Rejected because commit messages explain
changes, not the options that were rejected, and because the gaps between sessions on a
side project are long enough to lose context entirely.

**A single running design document.** Rejected because editing one document destroys the
historical record. The value here is being able to see what was believed at a point in time.
