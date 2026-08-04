# 0006. kube-prometheus-stack for platform observability

Date: 2026-08-02

## Status

Accepted

## Context

The only way to see what the Phase 0 cluster is doing is to hold a `kubectl port-forward`
open and read pod logs. That is adequate for one pod and useless as an answer to the
questions this project will actually ask: is the GPU saturated, is the model server being
OOM-killed, did ingestion fall behind.

Every phase from here adds components that emit metrics worth collecting. Whatever gets
chosen now determines how much work it is to monitor the ninth component, so the important
property is not what it can graph today but how cheaply a new service joins.

The hardware pushes the other way. The cluster is a single laptop whose GPU has 4 GB of VRAM
and whose RAM is shared with model inference. Observability that costs a gigabyte of RAM is
taking that gigabyte from the thing being observed.

Two further constraints apply. k3s bundles the controller manager, scheduler, proxy, and etcd
into one process rather than running them as separate components, so tooling that assumes a
conventional control plane will look permanently broken. And the local-first principle rules
out shipping telemetry to a hosted backend.

## Decision

Deploy **kube-prometheus-stack**, pinned to an exact chart version, as a dependency of a local
wrapper chart at `deploy/helm/observability/`. It provides Prometheus, Grafana,
`node-exporter`, and `kube-state-metrics` already wired together, and it installs the
Prometheus Operator's custom resources.

`ServiceMonitor` is the reason for choosing the bundle over its parts. With it available, a
component opts into monitoring by shipping a few lines inside its own chart, and no central
scrape configuration is ever edited.

Alertmanager is disabled. The four control-plane scrape jobs that do not apply to k3s —
`kubeControllerManager`, `kubeScheduler`, `kubeProxy`, and `kubeEtcd` — are disabled.
Prometheus retains 7 days of data under an explicit memory limit.

NVIDIA's `dcgm-exporter` is deployed alongside it so GPU utilisation and VRAM appear as
metrics rather than as the output of running `nvidia-smi` over SSH.

Grafana is published through the Traefik ingress that k3s already runs, so it is reachable
from a browser without a port-forward.

## Consequences

Monitoring becomes a property a chart declares about itself. That is the durable win, and it
is why this lands in the platform phase rather than being deferred until there is something
interesting to graph.

The stack costs roughly a gigabyte of RAM on a node whose job is inference. Short retention
and an explicit memory ceiling keep it bounded, at the price of a metrics history too short
to answer questions about last month.

Disabling Alertmanager means nothing will tell the operator that something broke; problems are
found by looking. This is the right trade while there is no notification path worth routing
to, and it is a values change to reverse — but it does mean the cluster can fail quietly.

The Prometheus Operator's custom resource definitions are cluster-scoped and outlive any
release that installed them. They become a shared dependency that later charts rely on and
that a clean uninstall will not remove. Practically, the observability release can no longer
be casually deleted.

`dcgm-exporter` targets datacentre GPUs. On a consumer Pascal card some metrics, particularly
the profiling series, are expected to be missing or unsupported. Basic utilisation and memory
should still report; if the exporter proves unstable on this hardware it will be dropped
without affecting the rest of the stack.

## Alternatives considered

**Separate Prometheus and Grafana charts.** Fewer components than the full bundle. Rejected
because it means wiring the datasource by hand, adding `node-exporter` and
`kube-state-metrics` as further installs, and either doing without `ServiceMonitor` or
installing the operator anyway — arriving at the same place with more assembly.

**Prometheus only, adding Grafana later.** Cheapest in RAM. Rejected because the phase goal is
being able to see the cluster, and Prometheus' own expression browser is a query tool, not an
answer to that.

**metrics-server alone.** Enough for `kubectl top` and autoscaling, and nearly free. Rejected
as it stores no history, so it cannot answer any question phrased in the past tense.

**VictoriaMetrics.** Materially lighter on memory than Prometheus and a genuine fit for
constrained hardware. Rejected on ecosystem grounds: kube-prometheus-stack is the assumed
substrate for the air-gapped tooling in Phase 2, and divergence there costs more than the RAM
saves.

**Grafana Cloud or any hosted backend.** Rejected outright. Design principle one is that no
data leaves the host unless deliberately sent, and that applies to telemetry.
