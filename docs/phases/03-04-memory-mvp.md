# Phases 3–4 MVP — Local memory from provider exports

**Goal:** Drop provider exports on the node (Gemini / Grok Markdown now; ChatGPT when
available), ingest them, and recall something over MCP — without MinIO, Spark, or an
air-gap bundle.

## What runs where

| Machine | Role |
| --- | --- |
| Linux GPU laptop | k3s; llm; Postgres; Neo4j; ingest Job; MCP server; hostPath inbox |
| Mac | `kubectl`, copy exports into the inbox, MCP client (Cursor / Claude) |

## Delivered in this MVP

- HostPath landing zone under `/srv/mnemos/data/` ([ADR 0007](../adr/0007-hostpath-inbox-over-minio.md))
- Parsers: Gemini + Grok (AI Exporter Markdown); ChatGPT JSON/zip ready when the export arrives
- PostgreSQL transcript archive (verbatim messages)
- Neo4j + Graphiti extraction against the existing OpenAI-compatible `llm` Service
- MCP server with search/recall and verbatim fetch
- Helm charts and Argo Applications for postgres, neo4j, ingest, mcp
- Smoke test: [`docs/runbooks/phase-3-4-memory-mvp.md`](../runbooks/phase-3-4-memory-mvp.md)

## Explicitly deferred

| Item | Why |
| --- | --- |
| Phase 2 Harbor / Zarf | Package a product worth delivering, not the scaffolding |
| MinIO | Folder inbox is enough on one node |
| Spark / Delta Lake | No batch volume that justifies the stack |
| Cursor / Claude / other exporters | Add parsers when real samples land; ChatGPT pending |
| Web UI | Phase 5 |
| Strong extraction quality on the 0.5B model | Swap the model via llm chart values when hardware allows |

## Done when

- [x] Gemini / Grok Markdown in `inbox/gemini` and `inbox/grok` ingest without hand SQL
- [x] ChatGPT export ingests when available (same pipeline) — ran against the fixture
- [x] Messages queryable in Postgres — 3 conversations, 8 messages
- [x] Graphiti has written entities/facts to Neo4j — 6 entities, 3 episodes, 768-wide embeddings
- [x] MCP recall returns something from that export
- [x] `postgres`, `neo4j`, `ingest`, `mcp` are Synced and Healthy in Argo

The mechanism is complete. The output is not yet trustworthy — see below.

## What the first real bring-up taught

Nothing here showed up in unit tests. All of it needed the actual node.

**Neo4j could never have started, and the error that said so was hidden behind
another error.** A Service named `neo4j` makes the kubelet inject
`NEO4J_PORT_7687_TCP_PORT` and its siblings into the pod. Neo4j 5 maps every `NEO4J_*`
variable onto a config setting and validates strictly, so it refused to boot on a setting
Kubernetes invented. This was true from the day the chart was written and stayed invisible
for 24 days, because the pod could not get its auth secret and never reached config
parsing. Fixed by `enableServiceLinks: false`.

**A StatefulSet cannot roll out its own fix.** Argo synced that correction, and `neo4j-0`
went on crash-looping on the old pod template: a rolling update replaces a pod only after
the current one is Ready, and the current one was the broken one. Deleting the pod by hand
was the only way out. This is the second time this deadlock has cost real time — Phase 1 hit
it with dcgm-exporter — which makes it a property of reconciling against a single node, not
bad luck. Argo is not self-correcting when the unhealthy resource is the thing that is
wrong.

**An OpenAI-compatible endpoint can accept a request, return 200, and ignore the part that
mattered.** Graphiti extracted nothing from any export. Every episode came back as prose
where JSON was required, and the retry — which tells the model it got the format wrong —
produced an apology in prose. The obvious reading was that a 0.5B model is too small to
emit structured output. That reading was wrong. `OpenAIClient` extracts through
`responses.parse()`, and llama.cpp answers `/v1/responses` with 200 while dropping the
schema, so the model was never constrained. Sending the identical prompt to
`/v1/chat/completions` with the same `json_schema` returns valid JSON every time. Switching
to `OpenAIGenericClient` moved extraction from 0/3 episodes to 3/3.

The general lesson is worth more than the fix: **"compatible" is a claim about the shape of
the request, not about the behaviour behind it.** The failure was silent, it looked exactly
like a model-quality problem, and the cheapest way to tell the two apart was to send one
request to each endpoint and compare. [ADR 0004](../adr/0004-openai-compatible-serving.md)
assumed the interface was the contract. It is the contract for *routing*; per-feature
support has to be probed.

**The 0.5B model hallucinates, and now there is evidence.** With extraction finally running,
qwen2.5-0.5b produced one fact from the hike transcript:

> "Mustang is the owner of the dog named Nimbus"

There is no Mustang. Entities include "Nisha's dad", "Jordan", and "Alex", none of which
appear in any transcript, and several entity summaries came back empty. Because the graph
holds exactly one fact, it ranks first for every query, including ones about housing and
defense contractors.

So recall works and returns the wrong thing. Retrieval quality
([ADR 0009](../adr/0009-measured-reranking.md)) was measured against a hand-labeled set and
says nothing about extraction quality, which is now the binding constraint. The next
decision is a bigger extraction model, and it needs its own evaluation — the current harness
cannot see this failure at all.
