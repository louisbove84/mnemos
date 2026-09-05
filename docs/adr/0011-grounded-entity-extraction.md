# 0011. Ground extracted entities in the source text

Date: 2026-09-05

## Status

Accepted

## Context

The first real bring-up produced a graph of six entities and one fact. The fact was:

> "Mustang is the owner of the dog named Nimbus"

There is no Mustang in any transcript. The other entities included `Nisha's dad`, `Jordan` and
`Alex`, none of which appear in anything mnemos ingested. Recorded at the time as the 0.5B
model hallucinating, with a larger extraction model as the obvious next step.

That diagnosis was wrong in a way that mattered. Every invented name is **verbatim from
Graphiti's own few-shot prompt**. `graphiti_core/prompts/extract_nodes.py` teaches possessive
qualification with *"Nisha: My dad is visiting next week"* and object extraction with *"the
windshield on my Mustang got cracked"*. The model was not inventing anything. It was extracting
from the instructions.

The prompt's shape explains why. The transcript sits about 31% into a 7,143-character prompt,
with roughly 4,900 characters of examples after it, and the examples are formatted as
`Message: "..."` blocks — structurally identical to the real `<CURRENT MESSAGE>` block. Nothing
in the input distinguishes the demonstration from the task.

Two cheaper explanations were tested and rejected first:

- **Truncation.** llama.cpp reports `truncated = 0` on every request, and the prompt is about
  2,050 tokens against a 4,096-token window. Nothing was being dropped.
- **Position.** Restating the transcript at the very end of the prompt, nearest generation,
  changed the 0.5B's output not at all — the same example names in the same order.

Measured with `mnemos-eval-extract` ([runbook](../runbooks/extraction-evaluation.md)), one run
each at `temperature=0`, where *contamination* is the share of returned entities that exist
only in Graphiti's prompt:

| Model | recall | contamination | looped | recall if grounded | contamination if grounded |
| --- | --- | --- | --- | --- | --- |
| qwen2.5-0.5b | 0.333 | 0.348 | 2/3 | 0.333 | 0.000 |
| qwen2.5-1.5b | 1.000 | 0.131 | 2/3 | 1.000 | 0.000 |
| qwen2.5-3b | 0.778 | 0.287 | 1/3 | 0.778 | 0.000 |

The table contains two separate findings. **Contamination does not fall with model size** — the
3B copies example names as readily as the 0.5B, so six times the parameters bought nothing on
the metric that made the graph worthless. **Recall does scale, and it saturates early** — the
0.5B recovers a third of the expected entities and the 1.5B recovers all of them, while the 3B
is no better and needs twice the VRAM on a 4 GB card.

## Decision

Two independent changes, because there are two independent problems.

**Discard any extracted entity whose significant words do not all appear in the episode.**
`GroundedEntityClient` wraps `OpenAIGenericClient` and filters node-extraction responses,
keyed on the `prompt_name` Graphiti already passes. It also deduplicates, because a looping
model returned one name eighty-eight times in a single episode and Graphiti would otherwise
resolve each copy separately.

The check is on words rather than substrings. Graphiti asks for assembled names — "Nisha's
dad" rather than a bare "dad" — so a correct entity is frequently not quoted from the source.
Requiring its words to be present accepts a name built from the transcript and rejects one
built from nothing.

**Serve qwen2.5-1.5b-instruct instead of qwen2.5-0.5b-instruct**, for recall.

## Consequences

Contamination goes to zero, and it does so deterministically rather than probabilistically. A
prompt-engineering fix or a larger model would have made fabrication less likely; this makes a
fabricated *name* impossible, because the graph cannot contain an entity absent from the text
it came from.

The filter costs no recall. That is not luck, it is definitional: a real entity appears in its
own transcript, which is exactly the predicate being tested. The eval reports filtered recall
separately anyway, so a filter that ever became too aggressive would show up as lost recall
rather than as silence.

Looping stops mattering for graph contents, since deduplication collapses it. It still wastes
tokens and time, and an overrun can still truncate entities that were never emitted, so the
eval keeps reporting it.

**The filter can be silently disabled by an upstream rename.** It fires on Graphiti's
`prompt_name` values, and if those change, filtering stops and nothing complains. A test reads
the pinned `graphiti-core` source and fails if the names are gone, which turns a silent
regression into a failed build. This is the main maintenance cost of the design and the reason
that test exists.

The episode text reaches the filter through a `ContextVar` set around `add_episode`, because
Graphiti does not pass the source text down to the LLM client. If extraction ever runs outside
that scope the client logs a warning and filters nothing, rather than checking against a stale
episode.

**Only entities are grounded, not facts.** Edge extraction runs on the resolved entity list, so
removing fabricated entities removes most fabricated relationships — the original bad fact
needed `Mustang` to exist. But an edge's *fact sentence* is still free text from the model, and
nothing here verifies it. That gap is real and unmeasured.

The 1.5B is roughly twice the weights of the 0.5B, about 940 MB against 469 MB, still fully
offloaded to a 4 GB GTX 1050 at 4,096 context. Extraction and reranking both got slower in
proportion; both run in a batch CronJob, so this is affordable in a way it would not be if
recall were interactive.

`qwen2.5-3b-instruct` remains downloaded on the node and unused. Keeping it costs 1.9 GB of
disk and makes the comparison re-runnable.

**Grounding is a floor, not a guarantee.** It cannot catch a name whose words are scattered
across an unrelated part of the transcript, and it happily keeps the low-quality entities the
1.5B also emits — `madison wi's housing market remains a competitive seller's market` is a real
extraction from a real run, grounded and useless. Precision of that kind is a separate problem
from fabrication, and this ADR does not address it.

## Alternatives considered

**Use a larger extraction model and nothing else.** The plan recorded in the phase notes.
Rejected on measurement: the 3B contaminates at 0.287 against the 0.5B's 0.348, which is no
improvement, and it costs twice the VRAM for worse recall than the 1.5B.

**Rewrite Graphiti's extraction prompt.** Addresses the actual cause rather than filtering the
symptom, and would help every model. Rejected as the first move because it means owning a fork
of a prompt that upstream will keep changing, and because it trades a deterministic guarantee
for a probabilistic improvement — a rewritten prompt makes copying less likely, while grounding
makes it impossible. Worth revisiting if precision becomes the binding constraint, since a
better prompt is the only thing that fixes *useless-but-grounded* entities.

**Pass explicit `entity_types` to constrain extraction.** A supported Graphiti feature that
would likely reduce junk. Rejected for now only because it is untested here; it is
complementary rather than an alternative, and the harness can now measure whether it helps.

**Filter inside the ingest pipeline after `add_episode` returns.** No coupling to Graphiti's
internals. Rejected because by then the entities are already written to Neo4j, resolved against
existing nodes, and used to extract edges — removing them afterwards means undoing work rather
than preventing it.

**Do nothing and accept a thin graph.** Rejected because the failure is worse than emptiness. A
graph holding one fabricated fact ranks that fact first for every query, so recall confidently
returned Graphiti's documentation in response to questions about housing and defense
contractors.
