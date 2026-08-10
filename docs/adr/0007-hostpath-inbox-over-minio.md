# 0007. HostPath inbox over MinIO for the MVP landing zone

Date: 2026-08-05

## Status

Accepted

## Context

Provider exports (OpenAI, Grok, and similar) arrive as files — zip archives and JSON
trees. The architecture model assumed MinIO as an object store for those blobs, with Spark
and Delta Lake as the processing path. That stack is correct for a multi-node lakehouse and
wrong for a single GPU laptop whose immediate goal is a working memory MVP.

The node already keeps model weights on disk under `/srv/mnemos/`. The operator copies files
onto that machine with `scp` or a USB stick. An S3-compatible API adds a Deployment, credentials,
and failure modes without changing that workflow.

Spark was considered for resume signal and batch scale. Neither applies at current volume.

## Decision

Raw exports land in a hostPath directory on the cluster node:

```text
/srv/mnemos/data/inbox/      # drop exports here
/srv/mnemos/data/processed/  # successfully ingested
/srv/mnemos/data/archive/    # optional copies of originals
```

Ingest Jobs mount that path. Verbatim transcripts go to PostgreSQL. Extracted memory goes to
Neo4j via Graphiti. MinIO, Spark, and Delta Lake are deferred until object APIs or volume
justify them.

Phase 2 (Harbor, Zarf) remains deferred until this MVP exists and is worth packaging.

## Consequences

Ingest stays a "read files from a folder" problem, which is easy to test and operate on one
node. The C4 "Object Store" container stays aspirational; the current Container view shows a
hostPath landing zone instead of MinIO.

Adding MinIO later means teaching the ingest client an S3 API while keeping the same
Postgres and graph contracts. That is a contained change.

What is given up: browser uploads, multi-writer bucket semantics, and a cloud-shaped artifact
store for air-gap bundles. Those matter for Phase 2+, not for proving MCP recall.

## Alternatives considered

**MinIO in the first slice.** Matches the original roadmap literally. Rejected as platform
weight before product value — the operator already has a way to put files on the node.

**Postgres bytea for raw exports.** Avoids a second store. Rejected for large zip exports and
because the verbatim *message* archive is a different, query-shaped concern from opaque blobs.

**Skip a landing zone and parse only from the developer laptop.** Rejected because ingest must
run next to Neo4j, Postgres, and the cluster LLM Service.
