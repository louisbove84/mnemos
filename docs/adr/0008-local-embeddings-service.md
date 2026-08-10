# 0008. A dedicated CPU embeddings service over the hash stand-in

Date: 2026-08-09

## Status

Accepted

## Context

Graphiti embeds every entity, edge, and episode it writes, and uses those vectors for
similarity search and for deciding whether a newly extracted entity is one it has already
seen. The MVP supplied `HashEmbedder`: SHA-256 of the input, stretched to the required width
and normalized. It satisfies the `EmbedderClient` interface, needs no service, and is
perfectly stable — the same string always yields the same vector.

It is also arbitrary by construction. A hash is designed so that similar inputs produce
unrelated outputs, which is the exact opposite of what an embedding is for. "the dog on Cedar
Ridge" and "Nimbus hiking the ridge" land in unrelated directions, so cosine similarity
carries no meaning. Every Graphiti behaviour that depends on vector distance therefore
degrades to exact string match: entity dedup stops merging, and hybrid search contributes
noise that the lexical reranker has to undo.

The constraint that kept it in place is hardware. The node has one 4 GB GTX 1050 and the
`llm` Deployment requests `nvidia.com/gpu: 1`, so there is no second device to schedule
against. Embedding models, unlike generation models, are small: `nomic-embed-text` is roughly
137M parameters, and ingest is a batch job where per-episode latency is not user-facing.

## Decision

Run embeddings as their own service, `embed`, serving `nomic-embed-text` at 768 dimensions on
CPU. The container is Ollama, chosen because it exposes `/v1/embeddings` and manages model
download and caching itself.

Graphiti talks to it through its stock `OpenAIEmbedder`, pointed at `http://embed:11434/v1`.
Both sides of the inference stack now speak the same contract as [ADR 0004](0004-openai-compatible-serving.md),
so the runtime behind either one is a values change rather than a code change.

`HashEmbedder` stays in the tree behind `MNEMOS_EMBEDDER=hash`. It is what CI uses, since unit
tests must not require a running model, and it is the lever to pull if `embed` is unavailable
and finishing an ingest run matters more than the quality of the vectors it writes.

## Consequences

Vector distance means something now, so entity resolution and hybrid search do the work they
were always assumed to be doing. Recall quality stops being bounded by the reranker.

Ingest gains a runtime dependency: with the default setting, a run fails if `embed` is not
reachable. That is the honest failure. Silently writing hash vectors would leave a graph that
looks populated and searches badly.

The dimension changed from 1024 to 768. Graphiti's Neo4j driver builds only range and
fulltext indexes and scores similarity per query with `vector.similarity.cosine`, which
requires both vectors to be the same width. So there is no index to migrate, but a graph
holding both widths makes every similarity query fail rather than quietly degrade.

The cutover is therefore a graph wipe and re-ingest, not a backfill of the vectors. Entity
resolution during the original ingest compared hash vectors, so the graph's structure — which
entities were judged to be the same entity — was decided on noise. Only re-running extraction
fixes that. Postgres is untouched, and holding every transcript verbatim is exactly what makes
throwing the graph away affordable.

First start pulls the model from the internet, which is in tension with the rule that charts
must not reach out at deploy time. `model.pullOnStart: false` against a pre-seeded cache
volume is the air-gapped path, and Phase 2 packaging has to seed that volume.

## Alternatives considered

**Put embeddings on the GPU.** Faster per call. Rejected because the only card is committed to
generation; sharing it means either evicting the LLM or time-slicing 4 GB between two models.

**Serve embeddings from the existing llm container.** llama.cpp will return embeddings for the
loaded model, so this costs nothing to deploy. Rejected because a 0.5B instruct model's hidden
states are a poor embedding space, and every embedding call would contend with generation on
the same GPU.

**Hugging Face TEI.** Leaner than Ollama and purpose-built for this one job. A reasonable
future swap, and the OpenAI-compatible contract makes it a values change. Not chosen now
because Ollama's built-in pull and cache handling is less chart machinery for the same result.

**A hosted embeddings API.** Best quality per unit of effort. Rejected on the project's
premise: memory that depends on someone else's endpoint is not sovereign, and this has to run
disconnected.

**Keep the hash embedder and lean on the lexical reranker.** No new component. Rejected because
it makes the graph's similarity claims untrue, and the whole point of [ADR 0002](0002-temporal-graph-over-vector-only.md)
is retrieval that a keyword search cannot do.
