# Deployment

Everything that runs on the cluster is declared here. Nothing is applied by hand — Argo CD
reconciles the cluster against this directory, so this is the description of what is running.

| Directory | Contents | Phase |
| --- | --- | --- |
| `helm/` | Charts for each container in the architecture model | 0–1 |
| `argocd/` | Application definitions Argo CD watches | 1 |
| `zarf/` | Air-gapped bundle definitions for disconnected deployment | 2 |

## Target environment

A k3s cluster. Single node during early phases, control plane plus GPU worker from Phase 6.
The same manifests are expected to deploy into a disconnected environment via Zarf without
modification — if a chart reaches out to the public internet at deploy time, that is a bug.
