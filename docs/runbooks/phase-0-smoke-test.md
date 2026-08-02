# Phase 0 smoke test

Prove GPU inference on k3s: list models, then get a chat completion from the Mac.

## Prerequisites

- k3s node Ready; Mac kubeconfig points at the cluster (`KUBECONFIG=~/.kube/mnemos-laptop.yaml`)
- NVIDIA device plugin advertising `nvidia.com/gpu`
- Model weights on the node at `/srv/mnemos/models/` (not in git)
- The `llm` Argo CD application Synced and Healthy (Phase 1 onward; nothing is applied by
  hand here anymore)

```bash
export KUBECONFIG=~/.kube/mnemos-laptop.yaml
kubectl -n mnemos get pods -l app.kubernetes.io/name=llm
```

Pod should be `Running` and Ready. On a cold start it stays unready for a minute or two
while the weights load; the startup probe allows up to ten.

## Port-forward

```bash
kubectl -n mnemos port-forward svc/llm 8000:8000
```

Leave that running. Use a second terminal for the curls below.

## List models

```bash
curl -s http://127.0.0.1:8000/v1/models | python3 -m json.tool
```

Expect JSON with the GGUF path under `data[].id` and `owned_by` of `llamacpp`.

## Chat completion

```bash
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "/models/qwen2.5-0.5b/qwen2.5-0.5b-instruct-q4_k_m.gguf",
    "messages": [
      {"role": "user", "content": "Say hello in one short sentence."}
    ],
    "max_tokens": 64,
    "temperature": 0.2
  }' | python3 -m json.tool
```

Expect `choices[0].message.content` with a short reply. A few seconds of latency on a
laptop GPU is normal.

## Done when

- [ ] `kubectl -n mnemos get pods -l app.kubernetes.io/name=llm` shows Ready
- [ ] `/v1/models` returns the loaded GGUF
- [ ] `/v1/chat/completions` returns text without SSHing onto the node to run inference by hand
