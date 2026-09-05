#!/usr/bin/env bash
# Open the Neo4j Browser against the cluster graph, from the workstation.
#
# Neo4j Browser is a client-side application: it loads over HTTP on 7474, then opens its own
# Bolt connection from the workstation. Both ports have to be forwarded, and Bolt has to land
# on 7687 locally, because the browser reads the Bolt address out of the server's discovery
# document at /. Remapping it to another local port makes the UI load and then fail to connect.
set -euo pipefail

NAMESPACE="${MNEMOS_NAMESPACE:-mnemos}"
SERVICE="${MNEMOS_NEO4J_SERVICE:-neo4j}"
HTTP_PORT=7474
BOLT_PORT=7687
CREDENTIALS="${MNEMOS_CREDENTIALS:-$HOME/.mnemos/credentials.env}"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl not found on PATH" >&2
  exit 1
fi

if [[ -z "${KUBECONFIG:-}" && -f "$HOME/.kube/mnemos-laptop.yaml" ]]; then
  export KUBECONFIG="$HOME/.kube/mnemos-laptop.yaml"
fi

for port in "$HTTP_PORT" "$BOLT_PORT"; do
  if nc -z 127.0.0.1 "$port" >/dev/null 2>&1; then
    echo "Port $port is already in use. Another forward is probably running." >&2
    exit 1
  fi
done

pids=()
cleanup() {
  for pid in "${pids[@]:-}"; do
    [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

kubectl -n "$NAMESPACE" port-forward "svc/$SERVICE" "$HTTP_PORT:$HTTP_PORT" >/tmp/pf-neo4j-http.log 2>&1 &
pids+=($!)
kubectl -n "$NAMESPACE" port-forward "svc/$SERVICE" "$BOLT_PORT:$BOLT_PORT" >/tmp/pf-neo4j-bolt.log 2>&1 &
pids+=($!)

for _ in $(seq 1 20); do
  if nc -z 127.0.0.1 "$HTTP_PORT" >/dev/null 2>&1 && nc -z 127.0.0.1 "$BOLT_PORT" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if ! nc -z 127.0.0.1 "$HTTP_PORT" >/dev/null 2>&1; then
  echo "Port-forward did not come up. See /tmp/pf-neo4j-http.log" >&2
  exit 1
fi

cat <<EOF

Neo4j Browser:  http://127.0.0.1:$HTTP_PORT
Connect URL:    bolt://127.0.0.1:$BOLT_PORT
                Change the scheme dropdown from neo4j:// to bolt://. The default routing
                scheme asks the server for its address, gets the pod hostname back, and
                fails in a way that looks like a rejected password.
Username:       neo4j
EOF

if [[ -f "$CREDENTIALS" ]]; then
  echo "Password:       \$MNEMOS_NEO4J_PASSWORD in $CREDENTIALS"
  if command -v pbcopy >/dev/null 2>&1; then
    echo "                copy it without displaying it:"
    echo "                grep MNEMOS_NEO4J_PASSWORD $CREDENTIALS | cut -d= -f2 | tr -d '\\n' | pbcopy"
  fi
else
  echo "Password:       from the neo4j-auth secret; $CREDENTIALS not found"
fi

cat <<'EOF'

Starter queries are in docs/runbooks/graph-visualization.md.
Ctrl-C to close the forwards.
EOF

wait
