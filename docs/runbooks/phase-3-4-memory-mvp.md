# Runbook — Phase 3–4 memory MVP

Smoke path: drop a ChatGPT export in the hostPath inbox → ingest → recall over MCP.

Prerequisites: Phase 0 LLM healthy, Phase 1 Argo apps healthy, kubeconfig pointed at the
GPU laptop (`KUBECONFIG=~/.kube/mnemos-laptop.yaml`).

## 0. Node directories and secrets (once)

On the GPU node:

```bash
sudo mkdir -p /srv/mnemos/data/{inbox,processed,archive}
sudo chmod -R 777 /srv/mnemos/data   # single-node MVP; tighten later
```

Create auth secrets in `mnemos` (out of band — same lesson as Grafana):

```bash
kubectl -n mnemos create secret generic postgres-auth \
  --from-literal=username=mnemos \
  --from-literal=password='CHANGE_ME_PG' \
  --from-literal=database=mnemos \
  --dry-run=client -o yaml | kubectl apply -f -

# Neo4j expects username/password in one NEO4J_AUTH value.
kubectl -n mnemos create secret generic neo4j-auth \
  --from-literal=auth='neo4j/CHANGE_ME_NEO4J' \
  --dry-run=client -o yaml | kubectl apply -f -
```

## 1. Build and import the mnemos image

From a machine that can reach the node (build on the node if easier):

```bash
cd /path/to/mnemos
docker build -t mnemos:0.1.0 .
# k3s example — import into containerd:
docker save mnemos:0.1.0 | sudo k3s ctr images import -
```

Confirm charts reference `mnemos:0.1.0` (`deploy/helm/ingest` and `deploy/helm/mcp`).

## 2. Wait for Argo apps

After merge to `main` (or while testing a branch via Application `targetRevision`):

```bash
kubectl -n argocd get applications
# expect postgres, neo4j, embed (wave 0), ingest, mcp (wave 1) Synced/Healthy
kubectl -n mnemos get pods,cronjobs,svc
```

The `embed` pod stays in `Init:0/1` while it downloads `nomic-embed-text` (~270 MB) into its
cache volume. That happens once; later restarts find the model already there.

```bash
kubectl -n mnemos logs deploy/embed -c pull-model
```

If the node pressure-stalls after Neo4j starts, temporarily scale observability down:

```bash
kubectl -n mnemos scale deploy -l app.kubernetes.io/name=grafana --replicas=0
# restore when done testing
```

Confirm embeddings before ingest depends on them. A 768-length vector back means Graphiti
will get real ones too, since it calls the same endpoint:

```bash
kubectl -n mnemos port-forward svc/embed 11434:11434
curl -s http://127.0.0.1:11434/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{"model":"nomic-embed-text","input":"Cedar Ridge Loop"}' \
  | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["data"][0]["embedding"]))'
# expect: 768
```

If `embed` is unreachable and you need an ingest run anyway, set `embed.mode: hash` in
`deploy/helm/ingest/values.yaml`. That writes non-semantic vectors, so graph search results
are meaningless until you re-ingest — see
[ADR 0008](../adr/0008-local-embeddings-service.md).

## 3. Drop exports into the inbox

Inbox layout (provider subfolders keep parsers unambiguous):

```text
/srv/mnemos/data/inbox/
  gemini/*.md          # AI Exporter Markdown from Gemini
  grok/*.md            # AI Exporter Markdown from Grok
  conversations.json   # ChatGPT / OpenAI data export (when available)
  *.zip                # ChatGPT export zip
```

Examples:

```bash
# Gemini / Grok from the Mac Downloads folders:
sudo mkdir -p /srv/mnemos/data/inbox/{gemini,grok}
sudo cp /path/to/Downloads/gemini/*.md /srv/mnemos/data/inbox/gemini/
sudo cp /path/to/Downloads/grok/*.md /srv/mnemos/data/inbox/grok/

# ChatGPT fixture (when ready):
sudo cp tests/fixtures/chatgpt_export/conversations.json /srv/mnemos/data/inbox/
```

## 4. Run ingest now

Do not wait for the CronJob schedule:

```bash
kubectl -n mnemos create job ingest-manual --from=cronjob/ingest
kubectl -n mnemos logs -f job/ingest-manual
```

Expect JSON summary with `conversations` ≥ 1. The file should move to
`/srv/mnemos/data/processed/`.

Verify Postgres:

```bash
kubectl -n mnemos exec -it statefulset/postgres -- \
  psql -U mnemos -d mnemos -c "SELECT id, title FROM conversations;"
kubectl -n mnemos exec -it statefulset/postgres -- \
  psql -U mnemos -d mnemos -c "SELECT role, left(content,80) FROM messages ORDER BY ordinal;"
```

You should see the Aurora hike / Nimbus fixture text.

Graphiti extraction quality on the 0.5B model is best-effort. Check Neo4j for any nodes:

```bash
kubectl -n mnemos exec -it statefulset/neo4j -- \
  cypher-shell -u neo4j -p 'CHANGE_ME_NEO4J' \
  'MATCH (n) RETURN labels(n) AS labels, count(*) AS c ORDER BY c DESC LIMIT 10;'
```

Entities carry the vectors that came back from `embed`, so their width is the proof that the
real embedder ran rather than the stand-in:

```bash
kubectl -n mnemos exec -it statefulset/neo4j -- \
  cypher-shell -u neo4j -p 'CHANGE_ME_NEO4J' \
  'MATCH (n:Entity) WHERE n.name_embedding IS NOT NULL
   RETURN size(n.name_embedding) AS dim LIMIT 1;'
# expect: 768
```

Even if extraction is thin, Postgres verbatim search still backs MCP recall.

## 5. Query via MCP

Port-forward the MCP SSE endpoint:

```bash
kubectl -n mnemos port-forward svc/mcp 8080:8080
```

SSE URL for clients: `http://127.0.0.1:8080/sse`

Quick tool smoke without a full MCP client (HTTP message flow varies by SDK). Prefer Cursor
or Claude Desktop pointed at that SSE URL, then call:

- `search_transcripts` with query `Nimbus` or `Cedar Ridge`
- `recall_memory` with the same query — expect `kind: fact` / `entity` / `episode` hits
  from Graphiti, with `conversation_id` set to the ingest group (the conversation id).
  Postgres `kind: message` hits only appear if the graph returned fewer than `limit`.
- `fetch_verbatim` with `conversation_id=conv-fixture-aurora`

You can also exercise the archive from a one-off Python shell inside the mcp pod if needed:

```bash
kubectl -n mnemos exec -it deploy/mcp -- \
  python -c "import asyncio; from mnemos.archive import store; from mnemos.config import get_settings; \
async def main():
 s=get_settings(); p=await store.connect(s.postgres_dsn); print(await store.search_messages(p,'Nimbus')); await p.close()
asyncio.run(main())"
```

## Changing the embedding model

Graphiti scores similarity with `vector.similarity.cosine`, which errors unless both vectors
have the same width, so a graph holding 1024-wide and 768-wide vectors at once breaks search
outright. Discard the graph rather than re-embedding in place: entity dedup during the old
run compared hash vectors, so the structure is as suspect as the vectors are. Postgres holds
every transcript verbatim, which is what makes that cheap, but the ingest CronJob only reads
the inbox, so the exports have to go back there first.

```bash
# 1. Point both charts at the new model, matching embed.dim to its output width:
#    deploy/helm/embed/values.yaml  -> model.name, model.dim
#    deploy/helm/ingest/values.yaml -> embed.model, embed.dim

# 2. Drop the graph. Postgres is untouched.
kubectl -n mnemos exec -it statefulset/neo4j -- \
  cypher-shell -u neo4j -p 'CHANGE_ME_NEO4J' 'MATCH (n) DETACH DELETE n;'

# 3. Move the processed exports back to the inbox and re-run.
kubectl -n mnemos create job ingest-reembed --from=cronjob/ingest
```

No index work is needed — the range and fulltext indexes Graphiti builds carry no dimension.

## Done when

- [ ] Fixture (or real export) ingested without hand SQL
- [ ] Messages visible in Postgres
- [ ] `embed` returns a 768-length vector and Neo4j entities carry embeddings of that width
- [ ] Neo4j has Graphiti data *or* extraction errors are logged and Postgres fallback works
- [ ] MCP `search_transcripts` / `recall_memory` returns fixture content
- [ ] `postgres`, `neo4j`, `embed`, `ingest`, `mcp` Synced/Healthy in Argo
