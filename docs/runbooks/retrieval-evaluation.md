# Runbook: measuring retrieval quality

`mnemos-eval` scores the embedder and the reranker against a labeled set, so a change to
either can be defended with a number instead of an argument. Run it after changing a model, a
dimension, a reranker, or a prompt.

It talks to any OpenAI-compatible endpoint, so the same command works against the cluster or
against a model running on your own machine.

## What it measures

Fifteen passages and thirteen queries live in `src/mnemos/eval/dataset.py`. The queries
deliberately share no content words with the passage that answers them, so a keyword matcher
cannot score well and anything that does is matching meaning.

- **Phrase pairs** — cosine similarity for pairs labeled `related` and `unrelated`. The
  headline is **separation**, the gap between the two means. Near zero means the vectors carry
  no meaning regardless of how wide they are.
- **Near-duplicates** — pairs with the same words and opposite intent ("start the server" vs
  "stop the server"). Reported without a verdict; every model scores these high. It is a known
  blind spot, tracked so a future model can be checked against it.
- **Retrieval** — MRR and recall@k over the embedding ranking, then over that ranking after
  each reranker reorders the top five.
- **Discriminative subset** — the six queries whose subject matches several passages and where
  only one answers. This is the number to watch when comparing rerankers, because the other
  seven are answerable from topic alone.

## Running it

Against the cluster, with both Services port-forwarded. Start the forwards and the run in one
shell; they do not survive between commands:

```bash
export KUBECONFIG=~/.kube/mnemos-laptop.yaml
kubectl -n mnemos port-forward svc/embed 21434:11434 >/tmp/pf-embed.log 2>&1 &
kubectl -n mnemos port-forward svc/llm 18000:8000 >/tmp/pf-llm.log 2>&1 &
sleep 5

poetry run mnemos-eval \
  --base-url http://127.0.0.1:21434/v1 \
  --llm-base-url http://127.0.0.1:18000/v1 \
  --rerankers lexical,llm
```

Useful flags:

| Flag | Effect |
| --- | --- |
| `--rerankers a,b` | Compare any of `lexical`, `llm`, `bge`, `none` on one embedding run |
| `--no-baseline` | Skip the hash comparison run |
| `--hash-only` | Run offline; needs no service at all |
| `--verbose` | Per-query winners, for seeing *which* query moved |
| `--json` | Machine-readable, for diffing two runs |

`--rerankers bge` needs the optional extra and downloads roughly 2.2 GB on first use:

```bash
poetry install --extras bge
```

## Reading the output

```
nomic-embed-text at http://127.0.0.1:21434/v1  [768d]
  phrase pairs     related +0.668   unrelated +0.371   separation +0.297
  near-duplicates  +0.839   (same words, opposite meaning: expected to score high)
  embeddings only  MRR 0.801   recall@1 0.692   recall@3 0.923
  + lexical        MRR 0.763   recall@1 0.615   (-0.038 MRR vs embeddings alone)
  + llm            MRR 0.885   recall@1 0.769   (+0.083 MRR vs embeddings alone)
  discriminative cases only (6 queries)
    embeddings only  MRR 0.806
    + lexical        MRR 0.722   (-0.083)
    + llm            MRR 0.833   (+0.028)
```

Rough expectations on the current stack:

| Signal | Healthy | Investigate |
| --- | --- | --- |
| separation | above +0.20 | below +0.10 means the embedder is not working |
| embeddings-only MRR | around 0.80 | below 0.60 suggests a wrong model or dimension |
| reranker delta | zero or positive | negative means the reranker is costing you accuracy |

**Do not read a single run as exact.** The LLM reranker is not deterministic even at
`temperature=0`, because llama.cpp results depend on what else was batched with them.
Repeated runs on an unchanged stack moved overall MRR between 0.833 and 0.923. Take three
runs, and treat anything under about 0.05 MRR as noise.

The hash baseline is the control. It should show separation near zero; if it ever shows
strong separation, the harness is measuring something other than semantic similarity and the
numbers above it cannot be trusted either.

## When it fails

`Connection error` against the embed URL is almost always a dead port-forward rather than a
dead Service. Check with `curl -s localhost:21434/api/tags`.

If the run works but every number is poor, check the dimension first. `--dim` must match what
the model actually emits: `nomic-embed-text` is 768 wide, and a mismatch silently truncates
before it fails.
