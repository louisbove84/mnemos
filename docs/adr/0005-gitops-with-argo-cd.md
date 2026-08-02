# 0005. GitOps with Argo CD in an App-of-Apps layout

Date: 2026-08-02

## Status

Accepted

## Context

Phase 0 put a model on a GPU by running `kubectl apply -f deploy/manifests/llm.yaml` from a
workstation. That worked, and it does not scale past one component. The cluster's real state
lives in the operator's shell history, nothing detects drift, and `deploy/README.md` already
claims something that is not yet true: that the directory describes what is running.

The roadmap adds roughly eight more deployable components between here and Phase 6 — object
storage, an ingestion pipeline, a transcript archive, a graph database, an extraction service,
an MCP server, and a web UI. Whatever replaces `kubectl apply` has to make adding the ninth
component cheaper than the first, not equally expensive.

Two project constraints narrow the field. The stack must eventually install into a
disconnected environment from a single bundle, so the deployment mechanism cannot assume it
can reach the public internet at sync time. And there is exactly one operator, so anything
requiring a rota or an on-call rotation to run is the wrong shape.

## Decision

Argo CD reconciles the cluster against this repository. It is installed once, by hand, with
Helm, and that bootstrap is the only `kubectl` a human is expected to run against the cluster
from this phase onward.

Applications are arranged **App-of-Apps**: a single root `Application` watches
`deploy/argocd/applications/`, and every child `Application` in that directory is discovered
and reconciled automatically. Adding a component is therefore a file in a pull request, not a
command on a node.

Each component is a local Helm chart under `deploy/helm/`. Charts that wrap upstream charts
declare them as dependencies with an exact version and a committed `Chart.lock`.

Argo CD does not manage Argo CD. It is upgraded by re-running the Helm install.

## Consequences

The cluster becomes auditable. What is deployed is what is in `main`, the sync status is
visible in a UI, and a change that someone makes by hand on the node gets reverted rather
than silently persisting.

One manual step survives. The bootstrap is irreducible — something has to install the thing
that installs everything else — and it needs its own runbook so that rebuilding the cluster
is a documented procedure rather than an act of memory.

Declining to self-manage Argo CD costs a small amount of purity and buys a safety property: a
bad sync cannot take out the component responsible for fixing bad syncs. Upgrades stay manual
as a result.

Git becomes a runtime dependency of deployment, which is in tension with the air-gap goal.
In a disconnected environment there is no `github.com` to poll, so Phase 2 must either ship a
local Git remote inside the bundle or bypass Argo CD entirely for the initial install. This
decision defers that problem rather than solving it, and it is the part of this ADR most
likely to need revisiting.

The App-of-Apps root is a single point of failure with a blast radius equal to the whole
platform. A malformed child manifest can wedge the root's sync. That is an acceptable trade
for one operator and roughly ten applications; it would not be at a hundred.

## Alternatives considered

**Flat Applications, hand-applied.** Fewer moving parts and no root object to wedge. Rejected
because it preserves the exact habit this phase exists to break: every new component would
mean another manual `kubectl apply` against the node, and `deploy/README.md` would keep making
a promise the repository does not keep.

**ApplicationSet with a Git directory generator.** Strictly less ceremony than App-of-Apps at
this scale — charts under `deploy/helm/` would be discovered with no per-component file at
all. Rejected for now because the indirection makes failures harder to trace, and legibility
matters more than keystrokes while the platform is being learned rather than operated. This is
the natural upgrade once the layout stops changing.

**Flux.** A credible alternative with a smaller footprint and no bundled UI. Rejected mainly
for the UI: on a headless GPU laptop, a web view of sync status is the cheapest available
answer to "what is the cluster doing," which is a stated goal of this phase.

**Push-based deployment from CI.** GitHub Actions holding a kubeconfig and running
`helm upgrade`. Rejected because it requires exposing the cluster's API server to the internet
or running a self-hosted runner, and it inverts the trust direction that makes an air-gapped
install plausible later.

**Continuing with `kubectl apply`.** Rejected. It is the problem statement.
