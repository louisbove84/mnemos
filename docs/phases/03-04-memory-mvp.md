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

- [ ] Gemini / Grok Markdown in `inbox/gemini` and `inbox/grok` ingest without hand SQL
- [ ] ChatGPT export ingests when available (same pipeline)
- [ ] Messages queryable in Postgres
- [ ] Graphiti has written entities/facts to Neo4j
- [ ] MCP recall returns something from that export
- [ ] `postgres`, `neo4j`, `ingest`, `mcp` are Synced and Healthy in Argo
