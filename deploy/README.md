# Deployment

Everything that runs on the cluster is declared here. Nothing is applied by hand — Argo CD
reconciles the cluster against this directory, so this is the description of what is running.

| Directory | Contents | Phase |
| --- | --- | --- |
| `helm/` | Charts for each container in the architecture model | 1 |
| `argocd/` | Application definitions Argo CD watches | 1 |
| `zarf/` | Air-gapped bundle definitions for disconnected deployment | 2 |

## How a change reaches the cluster

Commit a change to a chart under `helm/`, merge it to `main`, and Argo CD applies it.
There is no deploy step. A component joins the platform by adding one `Application` to
[`argocd/applications/`](argocd/applications); the root app in
[`argocd/root.yaml`](argocd/root.yaml) discovers everything in that directory.

The single exception is Argo CD itself, which cannot install itself. That bootstrap uses
[`argocd/bootstrap/values.yaml`](argocd/bootstrap/values.yaml) and is documented in
[`docs/runbooks/phase-1-bootstrap.md`](../docs/runbooks/phase-1-bootstrap.md). Rationale for
both choices is in [ADR 0005](../docs/adr/0005-gitops-with-argo-cd.md).

Model serving lives in [`helm/llm`](helm/llm) and runs in the `mnemos` namespace. Smoke test:
[`docs/runbooks/phase-0-smoke-test.md`](../docs/runbooks/phase-0-smoke-test.md).

## Target environment

A k3s cluster. Single node during early phases, control plane plus GPU worker from Phase 6.
The same manifests are expected to deploy into a disconnected environment via Zarf without
modification — if a chart reaches out to the public internet at deploy time, that is a bug.
