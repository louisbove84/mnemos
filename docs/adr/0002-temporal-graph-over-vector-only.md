# 0002. Temporal knowledge graph over vector-only retrieval

Date: 2026-07-31

## Status

Accepted

## Context

The problem this project exists to solve is that conversations with AI assistants do not
accumulate. The obvious implementation — embed every message and retrieve by similarity — is
what most retrieval-augmented systems do, and it fails in a specific way for this use case.

Similarity search has no representation of change. Beliefs, plans, and conclusions are not
static documents; they are claims with lifespans. "Relocating around 2028" was true when
said and may be false later. A vector store asked about relocation returns both the old and
the new statement with no way to tell which is current, and it cannot answer a point-in-time
question such as "what did I think about this in July" at all.

Published benchmarks reflect this. On LongMemEval, which tests temporal reasoning over long
conversation histories, a temporal-graph approach scores materially higher than a leading
vector-first system — roughly a fifteen point gap on exactly this class of question.

## Decision

The primary store is a bi-temporal knowledge graph, using Graphiti over Neo4j. Every fact
is an edge carrying both the time it became true and the time the system learned it. Facts
are never deleted; superseded facts are marked invalid with an end time and remain queryable.

Retrieval fuses graph traversal, semantic similarity, and keyword search rather than relying
on any one of them.

Raw transcripts are stored verbatim and permanently in PostgreSQL, separate from the graph.
Extraction quality is a function of the model doing the extraction, and models improve;
keeping the originals makes future re-extraction possible.

## Consequences

Ingestion becomes considerably more expensive. Every episode requires LLM-driven entity and
fact extraction plus contradiction resolution, rather than a single embedding call. This is
acceptable because ingestion is asynchronous and batched — it is a scheduled workload, not a
request path.

Operating a graph database alongside object storage and a relational archive is more
infrastructure than a single vector store would be. That cost is partly recovered by
Graphiti providing hybrid retrieval natively, which removes the need for a separate vector
database.

The bi-temporal model is genuinely harder to reason about than a key-value memory. Point-in-time
queries are the feature that justifies it; if that feature were dropped, this complexity would
be unwarranted.

## Alternatives considered

**Vector database only (Qdrant, pgvector).** Simplest and fastest to build. Rejected for the
reasons above: no temporal semantics, no relationship traversal, and demonstrably weaker on
the benchmark that matches this workload.

**Vector store with an optional graph layer (Mem0).** Easier adoption and good for
personalisation, but treats the graph as an add-on rather than the substrate, and does not
implement bi-temporality.

**Agent-managed hierarchical memory (Letta).** A strong fit when the agent should own its own
memory allocation. Rejected because memory here must outlive and stay independent of any single
agent or provider.
