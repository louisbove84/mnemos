# Phase 0 — GPU inference on Kubernetes

**Goal:** One cluster, one model, one HTTP endpoint. Curl it from the workstation and get tokens back.

## What runs where

| Machine | Role |
| --- | --- |
| Linux GPU laptop | k3s single-node cluster, NVIDIA toolkit, model weights under `/srv/mnemos/` |
| Mac (or any workstation) | `kubectl`, port-forward, smoke-test curls |

## Delivered in this phase

- k3s with GPU scheduling (`runtimeClassName: nvidia`, device plugin, `nvidia.com/gpu`)
- OpenAI-compatible serving via llama.cpp CUDA server (see [ADR 0004](../adr/0004-openai-compatible-serving.md))
- Hand-applied manifest: [`deploy/manifests/llm.yaml`](../../deploy/manifests/llm.yaml)
- Smoke test: [`docs/runbooks/phase-0-smoke-test.md`](../runbooks/phase-0-smoke-test.md)

## Node-local layout (not in git)

```text
/srv/mnemos/
  models/     # GGUF weights (downloaded on the node)
  data/       # reserved for later phases
```

## Explicitly out of scope

GitOps, Helm, Prometheus, Harbor, Zarf, Graphiti, MCP. Manual `kubectl apply` is acceptable here; Phase 1 replaces that habit.

## Done when

- [x] Node Ready from the workstation
- [x] GPU-requesting pod schedules and sees the device
- [x] Chat completion over HTTP without running inference by hand on the node
