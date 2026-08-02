# mnemos

Air-gappable, provider-neutral long-term memory for AI conversations.

Conversations with AI assistants start amnesiac. Each provider that offers memory keeps it
in their cloud, tied to their models. `mnemos` is the opposite bet: a memory layer that runs
on your own hardware, remembers across every assistant you use, and continues to work with
no internet connection at all.

## Why a temporal knowledge graph

Vector search alone cannot represent how understanding changes. "I plan to relocate in 2028"
is not a document to embed — it is a fact with a validity window that a later conversation
may invalidate. `mnemos` stores facts as graph edges with both a *valid time* (when it became
true) and a *transaction time* (when the system learned it). Facts are never deleted, only
superseded, which makes point-in-time questions answerable:

> "What did I believe about this decision six months ago, and what changed?"

Retrieval fuses graph traversal, semantic similarity, and keyword search. Raw transcripts are
preserved verbatim so that better models can re-extract from the originals later.

## Design principles

1. **Local first.** No data leaves the host unless you deliberately send it.
2. **Air-gappable.** The full stack deploys into a disconnected environment from a single bundle.
3. **Provider neutral.** Memory is exposed over Model Context Protocol, so any client can use it.
4. **Nothing is thrown away.** Extraction improves over time; the source of truth is immutable.
5. **Evaluated, not vibed.** Memory quality is measured against a versioned test suite.

## Architecture

Modelled in C4 using Structurizr. See [`docs/architecture`](docs/architecture) for the
source model and instructions for viewing it locally. Decisions and their rationale are
recorded as ADRs in [`docs/adr`](docs/adr).

## Status

Early. Building in phases, in the open.

| Phase | Focus | State |
| --- | --- | --- |
| 0 | GPU inference on Kubernetes (k3s; local OpenAI-compatible server today, any local or paid model API later) | Complete — see [`docs/phases/00-gpu-inference.md`](docs/phases/00-gpu-inference.md) |
| 1 | Platform foundation (GitOps, Helm, observability) | Not started |
| 2 | Air-gapped delivery (Harbor, Zarf) | Not started |
| 3 | Data platform (MinIO, Spark, Delta Lake) | Not started |
| 4 | Memory engine (Graphiti, Neo4j, MCP server) | Not started |
| 5 | Web UI and decision journal | Not started |
| 6 | Multi-node cluster, scale-to-zero serving | Not started |

## Development

Open the repository in the provided dev container. Python 3.12 and Poetry are pinned there,
so the local environment matches CI exactly and nothing is installed on the host.

```bash
poetry run pytest
poetry run ruff check .
poetry run mypy
```

Working without the container requires Python 3.12 and [Poetry](https://python-poetry.org/),
then `poetry install`.

Note that the dev container is for authoring only. Model serving and the cluster run on
separate Linux hardware with a GPU; see [`deploy/`](deploy).

Conventions for branches, commits, and architecture changes are in
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache License 2.0. See [LICENSE](LICENSE).
