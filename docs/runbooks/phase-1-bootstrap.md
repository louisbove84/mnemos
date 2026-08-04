# Phase 1 bootstrap

Install Argo CD on a cluster that does not have it, and hand the platform over to GitOps.
This is the only procedure in the project that applies things by hand, and it is written
down so that rebuilding the cluster is a procedure rather than an act of memory.

Run it once per cluster. After it completes, changes reach the node by merging to `main`.

## Prerequisites

- k3s node Ready, Mac kubeconfig pointing at it (`KUBECONFIG=~/.kube/mnemos-laptop.yaml`)
- `helm` and `kubectl` on the workstation
- The node can reach `github.com` (see ADR 0005 on why this is a problem for Phase 2)

## 0. Remove the Phase 0 deployment

Phase 0 applied `llm` into the `default` namespace by hand. Phase 1 deploys it into `mnemos`
instead, and Argo CD will not adopt or prune something it never created. The node has one
GPU, so if the old pod is left running it keeps `nvidia.com/gpu` allocated and the new pod
stays `Pending` forever.

```bash
export KUBECONFIG=~/.kube/mnemos-laptop.yaml
kubectl -n default delete deployment/llm service/llm --ignore-not-found
```

Use the `type/name` form. Writing `delete deployment llm service llm` reads `service` as
another Deployment name, and `--ignore-not-found` then hides the fact that the Service was
never touched.

Verify the GPU is free before continuing:

```bash
kubectl describe node | grep -A3 'Allocated resources' -A12 | grep nvidia.com/gpu
```

## 1. Install Argo CD

```bash
export KUBECONFIG=~/.kube/mnemos-laptop.yaml

helm repo add argo https://argoproj.github.io/argo-helm
helm repo update

helm upgrade --install argocd argo/argo-cd \
  --version 10.2.2 \
  --namespace argocd --create-namespace \
  --values deploy/argocd/bootstrap/values.yaml \
  --wait
```

The chart version is pinned deliberately. Upgrading Argo CD means changing that number here
and re-running the command — Argo CD does not manage itself.

```bash
kubectl -n argocd get pods
```

Expect `argocd-server`, `argocd-repo-server`, `argocd-application-controller`, and
`argocd-redis` running. The applicationset controller shows `0/0`; that is intentional.

## 2. Create the Grafana admin credentials

Grafana's chart invents a random admin password every time it renders, which would leave Argo
CD permanently OutOfSync and rotating the password on every sync. The chart is configured to
read an existing secret instead, so that secret has to exist before the application syncs.

```bash
kubectl create namespace observability --dry-run=client -o yaml | kubectl apply -f -

kubectl -n observability create secret generic grafana-admin \
  --from-literal=admin-user=admin \
  --from-literal=admin-password="$(openssl rand -base64 24)"
```

Read the password back when you need it:

```bash
kubectl -n observability get secret grafana-admin \
  -o jsonpath='{.data.admin-password}' | base64 -d; echo
```

## 3. Hand over to the root application

```bash
kubectl apply -f deploy/argocd/root.yaml
```

This is the last `kubectl apply` in the project. From here the root app watches
`deploy/argocd/applications/` and everything else follows from git.

```bash
kubectl -n argocd get applications
```

Expect `root`, `llm`, and `observability`, all progressing toward `Synced` / `Healthy`. The
`llm` app creates the `mnemos` namespace itself. Observability takes a few minutes: it pulls
the Prometheus, Grafana, and DCGM images and waits on a volume claim.

## 4. Reach the UIs from the Mac

Traefik routes by hostname, so the workstation needs to resolve those names to the node.
Find the node's address and add both hostnames to `/etc/hosts`:

```bash
kubectl get nodes -o wide
```

```text
# /etc/hosts on the Mac — substitute the node's real address
192.168.1.10  argocd.mnemos.local grafana.mnemos.local
```

Fetch Argo CD's generated admin password:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d; echo
```

Open <http://argocd.mnemos.local> and log in as `admin`. Change the password, then delete the
bootstrap secret:

```bash
kubectl -n argocd delete secret argocd-initial-admin-secret
```

## Done when

- [ ] `kubectl -n argocd get applications` shows every application `Synced` and `Healthy`
- [ ] The Argo CD UI loads at <http://argocd.mnemos.local> without a port-forward
- [ ] Grafana loads at <http://grafana.mnemos.local> without a port-forward
- [ ] Deleting the `llm` Deployment by hand results in Argo CD recreating it within a minute
- [ ] The [Phase 0 smoke test](phase-0-smoke-test.md) still returns a chat completion
