# Deployment

Everything that runs on the cluster is declared here. Nothing is applied by hand — Argo CD
reconciles the cluster against this directory, so this is the description of what is running.

| Directory | Contents | Phase |
| --- | --- | --- |
| `manifests/` | Hand-applied Phase 0 manifests (replaced by Helm/Argo in Phase 1) | 0 |
| `helm/` | Charts for each container in the architecture model | 1 |
| `argocd/` | Application definitions Argo CD watches | 1 |
| `zarf/` | Air-gapped bundle definitions for disconnected deployment | 2 |

Phase 0 serving lives in [`manifests/llm.yaml`](manifests/llm.yaml). Smoke test:
[`docs/runbooks/phase-0-smoke-test.md`](../docs/runbooks/phase-0-smoke-test.md).

## Target environment

A k3s cluster. Single node during early phases, control plane plus GPU worker from Phase 6.
The same manifests are expected to deploy into a disconnected environment via Zarf without
modification — if a chart reaches out to the public internet at deploy time, that is a bug.
