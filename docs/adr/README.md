# Architecture decision records

Short documents capturing decisions that are expensive to reverse, why they were made, and
what was given up. Written before the code lands, not after.

An ADR is immutable once accepted. If a decision changes, write a new ADR that supersedes
the old one and mark the original as superseded. The history is the point — being able to
see what was believed at the time is more valuable than a tidy current-state document.

| # | Title | Status |
| --- | --- | --- |
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0002](0002-temporal-graph-over-vector-only.md) | Temporal knowledge graph over vector-only retrieval | Accepted |
| [0003](0003-mcp-as-the-client-interface.md) | Model Context Protocol as the client interface | Accepted |
| [0004](0004-openai-compatible-serving.md) | OpenAI-compatible HTTP as the serving interface | Accepted |
| [0005](0005-gitops-with-argo-cd.md) | GitOps with Argo CD in an App-of-Apps layout | Accepted |
| [0006](0006-observability-stack.md) | kube-prometheus-stack for platform observability | Accepted |
| [0007](0007-hostpath-inbox-over-minio.md) | HostPath inbox over MinIO for the MVP landing zone | Accepted |
| [0008](0008-local-embeddings-service.md) | A dedicated CPU embeddings service over the hash stand-in | Accepted |
| [0009](0009-measured-reranking.md) | Rerank with the local LLM, chosen by measurement | Accepted |

Copy [`template.md`](template.md) and take the next number.
