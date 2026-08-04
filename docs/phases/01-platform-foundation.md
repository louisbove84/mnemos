# Phase 1 — Platform foundation

**Goal:** Stop deploying. Change a file, merge it, and the cluster catches up on its own —
then be able to see that it did, from a browser.

## What runs where

| Machine | Role |
| --- | --- |
| Linux GPU laptop | k3s, Argo CD, Prometheus and Grafana, the model server |
| Mac (or any workstation) | One bootstrap, then a browser |

## Delivered in this phase

- Phase 0's manifest templated as a Helm chart: [`deploy/helm/llm`](../../deploy/helm/llm).
  Image, model file, context size, and GPU layers are values, which is what
  [ADR 0004](../adr/0004-openai-compatible-serving.md) asked for.
- Argo CD reconciling the cluster against this repository, App-of-Apps
  ([ADR 0005](../adr/0005-gitops-with-argo-cd.md)). The root app is in
  [`deploy/argocd/root.yaml`](../../deploy/argocd/root.yaml).
- kube-prometheus-stack with GPU metrics
  ([ADR 0006](../adr/0006-observability-stack.md)):
  [`deploy/helm/observability`](../../deploy/helm/observability).
- Grafana and the Argo CD UI on hostnames through Traefik, so nothing needs a port-forward.
- Chart linting and manifest schema validation in CI.
- A deployment view in the architecture model showing the two machines.
- Bootstrap runbook: [`docs/runbooks/phase-1-bootstrap.md`](../runbooks/phase-1-bootstrap.md).

## The one thing still applied by hand

Argo CD cannot install itself, so the bootstrap is irreducible: one `helm upgrade --install`
and one `kubectl apply` of the root application. Everything after that is a commit. Argo CD
is deliberately not self-managed, so upgrading it means re-running that same command with a
new pinned version.

## Things that bite on this hardware

k3s runs the controller manager, scheduler, proxy, and etcd inside a single process, so
kube-prometheus-stack's default scrape jobs for those four components have nothing to talk
to. They are disabled in values; leaving them on produces four permanently failing targets
and no useful signal.

Prometheus defaults to `emptyDir`, which quietly discards every series on restart and makes
the retention setting meaningless. It gets a `local-path` volume claim instead.

Alertmanager is off. There is no notification path worth routing to yet, and the RAM is
better spent on inference. The consequence is real: the cluster can fail quietly, and
problems get found by looking rather than by being told.

## Explicitly out of scope

Harbor, Zarf, secret management, backups, multi-node scheduling, scale-to-zero, and every
container from Phase 3 onward. Alerting is deferred with the rest of it.

## Done when

- [ ] Editing `model.file` in the chart's values and merging redeploys the model, with no
      `kubectl` involved
- [ ] `kubectl -n argocd get applications` shows `root`, `llm`, and `observability` Synced
      and Healthy
- [ ] Deleting the `llm` Deployment by hand results in Argo CD putting it back
- [ ] Grafana loads at `grafana.mnemos.local` with GPU utilisation and VRAM on screen
- [ ] The [Phase 0 smoke test](../runbooks/phase-0-smoke-test.md) still returns a chat
      completion
