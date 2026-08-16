# 0010. Route recall through Graphiti hybrid search

Date: 2026-08-16

## Status

Accepted

## Context

[ADR 0009](0009-measured-reranking.md) measured embedders and rerankers against a labeled
set and defaulted recall-time reranking to the in-cluster LLM. Those numbers described
Graphiti's `search_` API. They did not describe mnemos.

Ingest calls `add_episode`. Entity dedup in that path uses the embedder for cosine
similarity and Graphiti's own comment on it is "without reranking". The MCP
`recall_memory` tool queried a Neo4j fulltext index (`node_name_and_summary`) and padded
with Postgres `ILIKE`. Neither the embedder nor the reranker ran on a user-facing read.

The harness, the Helm values, and the Graphiti client constructor were therefore all
pointing at a path nobody called. A keyword search cannot do the work
[ADR 0002](0002-temporal-graph-over-vector-only.md) exists for: matching "how did the puppy
handle that long walk" to a fact about Nimbus on Cedar Ridge.

## Decision

`recall_memory` calls Graphiti `search_` with the hybrid + cross-encoder recipe (BM25 and
cosine similarity, then the configured reranker), over facts, entities, and episodes.
Communities are omitted: the MVP does not build them, and each extra layer is another GPU
round-trip on an interactive request.

Postgres verbatim search still fills remaining slots when the graph is thin or unreachable.
`search_transcripts` and `fetch_verbatim` stay as keyword/id lookups over the archive;
they are a different job.

MCP constructs the same Graphiti client as ingest (embedder, reranker, LLM settings) but
does not create indexes. Ingest owns that.

## Consequences

The eval harness now measures the path a user actually hits. Changing `MNEMOS_RERANKER` or
the embedding model changes what `recall_memory` returns, which is the point.

Recall is no longer a cheap Cypher query. It embeds the query against `embed`, then the
reranker issues one LLM call per shortlisted passage, against the same 0.5B GPU that
extraction uses. Concurrent ingest and recall will queue. `MNEMOS_RERANKER=lexical` on the
MCP chart is the lever if that contention is worse than slightly worse ranking; ADR 0009
already records that lexical scores below doing nothing, so this is a latency trade, not a
quality upgrade.

MCP now depends on `embed` and `llm` at request time, not just Neo4j. If Graphiti fails to
start or search raises, the tool degrades to Postgres rather than failing the pod: transcript
search still works while the graph is coming up.

The JSON shape of `recall_memory` changes. Hits carry `kind` (`fact` / `entity` /
`episode` / `message`) and `conversation_id` (Graphiti `group_id`, which ingest sets to the
conversation id). Clients that parsed the old fulltext `{name, summary, labels}` payload
will need to follow this.

## Alternatives considered

**Keep Neo4j fulltext and call the change done.** No new dependencies on the MCP pod.
Rejected because it leaves the measured retrieval stack unwired, which is how the last two
ADRs ended up describing a path nobody used.

**Edges only (`EDGE_HYBRID_SEARCH_RRF`).** Cheaper, no reranker. Rejected because the
reranker is what paid for itself on discriminative queries in ADR 0009, and facts-only
drops entities when extraction is thin — which it will be, on 0.5B.

**Full `COMBINED_HYBRID_SEARCH_CROSS_ENCODER` including communities.** Graphiti's default.
Rejected for the extra GPU pass over a layer this cluster does not populate.

**Require Graphiti at MCP startup.** Fail the probe if Neo4j or embed is down. Honest, but
it takes transcript search down with the graph. Degrade-to-Postgres keeps the archive
reachable during the same bring-up that currently leaves postgres/neo4j pending on secrets.
