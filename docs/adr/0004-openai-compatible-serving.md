# 0004. OpenAI-compatible HTTP as the serving interface

Date: 2026-08-02

## Status

Accepted

## Context

Phase 0 needs a working GPU inference endpoint on Kubernetes. The original plan assumed
vLLM. The available homelab GPU is an NVIDIA GeForce GTX 1050 (Pascal, compute capability
6.1, 4 GB VRAM). Current upstream vLLM builds require substantially newer compute
capability and will not run on this hardware without a custom fork.

Downstream consumers (extraction, MCP tools, local stubs) should not hard-depend on a
particular inference engine. They need a stable HTTP contract.

## Decision

Expose model serving behind an **OpenAI-compatible** HTTP API (`/v1/models`,
`/v1/chat/completions`). The Phase 0 implementation uses **llama.cpp** (`server-cuda`)
with a small GGUF instruct model that fits the GPU.

When hardware allows, the container behind the same Service shape may be replaced with
vLLM (or another engine) without changing the client contract.

## Consequences

Clients and smoke tests talk to a URL and a JSON schema, not to “vLLM specifically.”

Phase 0 can complete on constrained hardware. Model quality and throughput are limited by
the GPU; that is acceptable for proving the platform path.

Helm/Argo in Phase 1 should parameterize image and model path so swapping engines is a
values change, not a redesign.
