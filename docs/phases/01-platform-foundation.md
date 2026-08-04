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

## What the first real bootstrap taught

Three things only showed up when this ran against actual hardware.

**A chart that generates a random value cannot be reconciled.** Grafana invents an admin
password every time it renders, so every sync produced a different Secret and Argo CD never
reached Synced. With self-heal on it would have rotated the password indefinitely. Reading
credentials from a secret created out of band fixes it. The general lesson is that any chart
with a random default is a GitOps hazard, and it is worth checking for before adding a
dependency.

**A sync that waits on an unhealthy resource blocks its own fix.** dcgm-exporter was
`OOMKilled` because the memory ceiling here was a guess, and Argo sat in a Running sync
waiting for it to become healthy. Because the operation never finished, the corrected values
could not be applied — the deadlock had to be broken by hand. Argo is not self-correcting when
the thing it is waiting on is the thing that is wrong.

**The GPU was never the problem.** ADR 0006 predicted trouble from running datacentre GPU
tooling on a consumer Pascal card. DCGM initialised cleanly every time and reports
utilisation, VRAM, and temperature; the crash was an ordinary resource limit. The prediction
was reasonable and simply wrong, which is worth leaving on the record.

## Explicitly out of scope

Harbor, Zarf, secret management, backups, multi-node scheduling, scale-to-zero, and every
container from Phase 3 onward. Alerting is deferred with the rest of it.

## Done when

- [x] Editing the chart's values and merging redeploys the model, with no `kubectl` involved —
      raising the context window to 4096 reached the node about 30 seconds after merge
- [x] `kubectl -n argocd get applications` shows `root`, `llm`, and `observability` Synced
      and Healthy
- [x] Deleting the `llm` Deployment by hand results in Argo CD putting it back — restored in
      under 15 seconds
- [x] Grafana loads at `grafana.mnemos.local` with GPU utilisation and VRAM on screen
- [x] The [Phase 0 smoke test](../runbooks/phase-0-smoke-test.md) still returns a chat
      completion
