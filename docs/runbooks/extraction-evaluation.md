# Runbook: measuring extraction quality

`mnemos-eval-extract` scores what the LLM pulls *out of* a transcript.
[`mnemos-eval`](retrieval-evaluation.md) scores how well the stack ranks passages that are
already correct, which means it cannot see a fabricated entity — and fabrication was the
failure that made the first real graph worthless while every retrieval number looked fine.

Run it after changing the extraction model, its quantization, its token budget, or the
version of `graphiti-core` that supplies the prompt.

## What it measures

Three transcripts in `src/mnemos/eval/extraction.py`, matching the repository fixtures. Each
pairs a conversation with the entities extraction has to recover.

- **recall** — the share of expected entities that came back. Low recall means the model is
  not reading the transcript.
- **contamination** — the share of returned entities that exist only in Graphiti's few-shot
  prompt (`Nisha's dad`, `Jordan's dog`, `Gamecube`, `Mustang`). **The only acceptable value
  is zero.** A graph holding one invented fact ranks it first for every query, so a little
  contamination is not a little problem.
- **looped** — cases where the model repeated a name or ran to the token ceiling.
- **filtered** — the same two numbers after discarding entities whose words do not appear in
  the transcript. This measures the remedy in the same run as the problem.

Recall and contamination are always read together, because returning nothing scores a
perfect zero contamination.

The harness sends **Graphiti's own `extract_nodes` prompt**, rendered from the installed
package, over `/v1/chat/completions` with a `json_schema`. That is deliberate. A hand-written
prompt would measure a model against text mnemos never sends, and the failure under test is
caused by the shape of Graphiti's prompt specifically: the transcript sits about 31% of the
way in, with roughly 4,900 characters of examples after it.

### Why the contaminant list is curated by hand

Scraping names out of the prompt looks tempting and is wrong. Graphiti's own example says
*"My spouse started a new role at Lockheed Martin"*, and the Gemini fixture is genuinely
about Lockheed Martin. Scraping would score a correct extraction as fabrication. The list in
`PROMPT_EXAMPLE_NAMES` holds only names that cannot legitimately appear in these transcripts,
and a test asserts no expected entity is also on it.

The list is tied to the `graphiti-core` version in `poetry.lock`. If that moves, re-read
`graphiti_core/prompts/extract_nodes.py` before trusting the numbers.

## Running it

Against the cluster. Start the forward and the run in one shell; forwards do not survive
between commands:

```bash
export KUBECONFIG=~/.kube/mnemos-laptop.yaml
kubectl -n mnemos port-forward svc/llm 18000:8000 >/tmp/pf-llm.log 2>&1 &
sleep 5

poetry run mnemos-eval-extract \
  --base-url http://127.0.0.1:18000/v1 \
  --label "candidate model" --verbose
```

| Flag | Effect |
| --- | --- |
| `--model` | Override the served model path; must match what the server has loaded |
| `--label` | Names the run in the output, for comparing two models |
| `--max-tokens` | Default 2048. Higher than the 512 ingest uses, so a looping model is scored on its output instead of being cut off and reported as a parse error |
| `--verbose` | Per-case entity lists — the fastest way to see *what* it invented |
| `--json` | Machine-readable, for diffing runs |

### Comparing candidate models without disturbing the cluster

The single GPU is held by the Argo-managed `llm` Deployment, and an eval is not worth risking
it. Serve candidates on the CPU instead, in a throwaway Deployment outside Argo, and delete it
afterwards. Model quality at `temperature=0` does not depend on which backend runs the
weights.

Use `strategy: Recreate` and a CPU request of 1. The node is a 4-core laptop already at ~90%
CPU requests, so the default rolling update cannot schedule a second pod and the rollout hangs
on `Insufficient cpu`.

Weights go in `/srv/mnemos/models/<name>/`, matching the layout the `llm` chart expects.

## Reading the output

```
qwen2.5-1.5b-instruct q4_k_m
  as returned by the model
    recall         1.000   (expected entities recovered)
    contamination  0.131   (entities lifted from the prompt's examples; must be 0)
    looped         2/3 cases
    verdict        NOT usable
  after dropping entities absent from the transcript
    recall         1.000
    contamination  0.000
    verdict        usable
```

Measured on the GTX 1050 node, one run each at `temperature=0`:

| Model | recall | contamination | looped | filtered recall | filtered contamination |
| --- | --- | --- | --- | --- | --- |
| qwen2.5-0.5b | 0.333 | 0.348 | 2/3 | 0.333 | 0.000 |
| qwen2.5-1.5b | 1.000 | 0.131 | 2/3 | 1.000 | 0.000 |
| qwen2.5-3b | 0.778 | 0.287 | 1/3 | 0.778 | 0.000 |

Two findings worth keeping:

**Contamination does not shrink with model size.** The 3B copies Graphiti's example names as
readily as the 0.5B. Six times the parameters bought nothing on the metric that matters, so
"use a bigger model" was the wrong instinct — the grounding filter is what takes contamination
to zero, and it does so at every size.

**Recall does scale, and it saturates early.** The 0.5B recovers a third of the expected
entities; the 1.5B recovers all of them. The 3B is no better and costs twice the VRAM.

**Do not read a single run as exact.** llama.cpp is not deterministic at `temperature=0`,
because results depend on what else was batched with them. Repeated 3B runs moved recall
between 0.778 and 0.889. Treat a difference under about 0.1 as noise, and take three runs
before concluding a model is better.

## When it fails

**`Connection error`** is almost always a dead port-forward rather than a dead Service.
Check with `curl -s localhost:18000/v1/models`.

**`returned unparseable JSON; salvaged N names`** is not an endpoint problem. Constrained
decoding still emits invalid JSON if the model runs out of tokens mid-string, which is what a
looping model does. The names committed before the cut are recovered and scored, so the run
reports looping as looping. Seeing this on a candidate model is a finding, not a failure.

**Every entity contaminated and recall zero** means the model is answering from the
instructions rather than the input. That is the qwen2.5-0.5b signature and the reason this
harness exists.
