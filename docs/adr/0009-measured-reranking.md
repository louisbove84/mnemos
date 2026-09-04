# 0009. Rerank with the local LLM, chosen by measurement

Date: 2026-08-10

## Status

Accepted

## Context

A cross-encoder reorders the shortlist that vector search returns. It is the last stage that
can fix a bad ordering, and it is the only stage that reads the query and the passage
together rather than comparing two independently computed vectors.

The MVP supplied `LexicalReranker`, which scored a passage by the fraction of its words that
appeared in the query. [ADR 0008](0008-local-embeddings-service.md) replaced the hash embedder
on the argument that the reranker should not have to undo the embedder's noise, but left the
reranker itself untouched and unmeasured.

Unmeasured was the real problem. There was no way to answer whether any of this worked, so
the retrieval stack was three components chosen by plausibility. The eval harness added in
this change exists to end that: 15 passages and 13 labeled queries, scored by MRR and
recall@k. Six of those queries are *discriminative* — several passages share the subject and
only one answers — because that is the case a reranker exists to handle, and a benchmark
where the embedder already scores perfectly cannot tell two rerankers apart.

Graphiti ships an `OpenAIRerankerClient` that asks the model a True/False relevance question
and ranks by the probability of "True". It is not usable here as-is. It pins
`logit_bias` to OpenAI's token ids for those two words, which address unrelated tokens under
Qwen's tokenizer; it reads only the single most likely token, which on a small model is often
whitespace; and it drops passages whose logprobs are missing before a `strict=True` zip, so a
partial response raises instead of degrading.

## Decision

Rerank with the existing `llm` Service by default, through our own `LLMReranker`. It asks
Graphiti's question but reads the answer out of `top_logprobs` by string, so no tokenizer
assumption is baked in, and it scores every passage or leaves the order alone rather than
raising.

Two alternatives stay available through `MNEMOS_RERANKER`: `bge` for a purpose-built
cross-encoder, behind an optional `sentence-transformers` extra, and `lexical` for the
no-dependency fallback.

Measured against `nomic-embed-text` on the harness, embedding order alone scores 0.801 MRR
overall and 0.806 on the discriminative subset:

| Reranker | Overall MRR | Discriminative MRR | Cost |
| --- | --- | --- | --- |
| none | 0.801 | 0.806 | — |
| lexical | 0.763 | 0.722 | none |
| llm (qwen2.5-0.5b) | 0.833–0.923 | 0.833–0.917 | one call per passage |
| bge-reranker-v2-m3 | 0.885 | 0.833 | torch, 2.2 GB of weights |

`llm` is the default because it matches BGE within measurement noise while needing no new
dependency, no new model download, and no new Deployment.

## Consequences

The reranker earns its place now, which is a claim that can be re-checked with one command
rather than argued. The same harness will judge whatever replaces it.

The LLM path is not deterministic. Repeated runs at `temperature=0` moved overall MRR between
0.833 and 0.923, because llama.cpp's batching makes results depend on what else was in flight.
Any future comparison has to be read as a band, not a number, and a change smaller than about
0.05 MRR on this dataset means nothing.

Reranking now costs one generation call per shortlisted passage, against the same 0.5B model
and the same single GPU that extraction uses. `MNEMOS_RERANK_CONCURRENCY` bounds the fan-out.
This is affordable because it happens during a batch CronJob; it would need rethinking the
moment recall becomes interactive.

`lexical` scored *below* doing nothing, on both subsets. It is retained only so that ingest
can finish when `llm` is unreachable, and the ADR records that choosing it trades away
accuracy rather than merely quality.

The result that mattered least is the one that was easiest to predict: a purpose-built
cross-encoder did not beat a general 0.5B model here. On 13 queries that comparison is weak
evidence, and the honest reading is that the dataset is too small to separate them rather
than that BGE is not better.

**Nothing in production calls the reranker yet, and recall does not use the embedder
either.** The wiring is in place on the Graphiti client, but mnemos never invokes
Graphiti's hybrid search API today.

During ingest, Graphiti's entity dedup runs cosine similarity through the embedder
directly — Graphiti's own comment on that path is "without reranking". The 0.5B LLM
still runs there, but for extraction and dedupe prompts, not for vectors or reranking.

The MCP `recall_memory` tool bypasses Graphiti entirely: it queries a Neo4j fulltext
index and falls back to a Postgres `ILIKE`. No embedder, no reranker, no hybrid search.

The eval harness is therefore measuring the path Graphiti's `search_` API would take
(embeddings to shortlist, reranker to reorder), not what ingest or recall currently
do. Routing `recall_memory` through Graphiti's hybrid search is what makes these
numbers describe what a user experiences: see [ADR 0010](0010-recall-through-graphiti-search.md).

## Alternatives considered

**Use Graphiti's `OpenAIRerankerClient` unmodified.** No code to own. Rejected for the three
defects above; the wrong-tokenizer `logit_bias` is silent, which is the worst kind.

**Default to BGE.** Strongest on paper and purpose-built. Rejected because it did not
measurably beat the LLM here while adding torch and a 2.2 GB download to an image that is
otherwise small, and because it needs CPU that the node is already spending on embeddings.
It stays one setting away if a larger dataset shows a real gap.

**Drop reranking.** Defensible when the only implementation was making results worse, and
still the right call if the LLM is unavailable. Rejected because both real rerankers beat
raw embedding order on exactly the queries that motivate the graph.

**Fix the lexical scorer and keep it as default.** Its scoring was rewritten here — query-term
coverage, stopwords dropped, no length normalization, ties preserving embedding order — which
moved it from actively harmful to roughly neutral. Rejected as a default because "roughly
neutral" is the ceiling for a method that cannot tell two passages on the same subject apart.
