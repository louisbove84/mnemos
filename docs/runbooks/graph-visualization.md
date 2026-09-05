# Runbook: seeing the graph

Neo4j Community bundles **Neo4j Browser**, which renders Cypher results as an interactive
graph. It is already served on port 7474 of the `neo4j` Service, so there is nothing to
install and nothing new to deploy — the graph has been visualizable since the day Neo4j
came up.

This is the fastest way to answer "what does mnemos actually think it knows", and the fastest
way to see extraction going wrong. A wrong fact is obvious as a picture and easy to miss as
JSON.

## Open it

```bash
./scripts/graph-browser.sh
```

Then open <http://127.0.0.1:7474> and connect with:

| Field | Value |
| --- | --- |
| Connect URL | **`bolt://`** `127.0.0.1:7687` — change the scheme dropdown from `neo4j://` |
| Username | `neo4j` |
| Password | `MNEMOS_NEO4J_PASSWORD` in `~/.mnemos/credentials.env` |

**Change the scheme to `bolt://`.** The dialog defaults to `neo4j://`, which is the routing
protocol: the driver connects, asks the server where the database lives, and gets told
`neo4j-0` — the pod hostname, because the chart sets no `server.default_advertised_address`.
That name does not resolve on the workstation, so the connection dies immediately after you
submit credentials and Browser reports it as a login failure. The password is not the problem.
`bolt://` connects directly and skips the routing lookup.

To avoid mistyping a 28-character generated password, put it on the clipboard instead of
reading it off the screen:

```bash
grep MNEMOS_NEO4J_PASSWORD ~/.mnemos/credentials.env | cut -d= -f2 | tr -d '\n' | pbcopy
```

Neo4j Browser is a client-side application. It loads over HTTP on 7474 and then opens its own
Bolt connection *from the workstation*, which is why the script forwards two ports and why
Bolt has to land on 7687 locally: the browser reads that address out of the server's discovery
document. Remap it and the UI loads, then fails to connect.

For the same reason there is no `neo4j.mnemos.local` alongside Grafana and Argo CD. A Traefik
Ingress covers HTTP, so it would serve the UI and leave it unable to reach the database. Doing
it properly means putting Bolt on the LAN through a NodePort or a TCP entrypoint, which is a
decision about exposure rather than a config detail, and it is not needed for a tool one person
runs while debugging.

## What is in there

Graphiti stores two layers, and both are worth seeing:

| | |
| --- | --- |
| `(:Episodic)` | One node per conversation, holding the text that was extracted from |
| `(:Entity)` | People, places, and things found in that text |
| `-[:MENTIONS]->` | Provenance: which conversation produced which entity |
| `-[:RELATES_TO]->` | **The memory.** A fact between two entities, with validity times |

`Community` and `Saga` labels exist in the schema but the MVP never builds them
([ADR 0010](../adr/0010-recall-through-graphiti-search.md) skips community search for the same
reason).

## Starter queries

Save the ones you use with "Save as Favorite" in Browser; favorites live in the browser, not
on the server, so they do not survive a different machine.

The memory itself. This is the layer that makes mnemos more than a search index:

```cypher
MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
RETURN a, r, b
```

Provenance, which is how you catch a fact that came from nowhere:

```cypher
MATCH (ep:Episodic)-[m:MENTIONS]->(e:Entity)
RETURN ep, m, e
```

Both layers at once — the closest thing to a single picture of mnemos:

```cypher
MATCH (ep:Episodic)-[m:MENTIONS]->(e:Entity)
OPTIONAL MATCH (e)-[r:RELATES_TO]-(o:Entity)
RETURN ep, m, e, r, o
LIMIT 100
```

One conversation in isolation. `group_id` is the conversation id, the same one
`fetch_verbatim` takes:

```cypher
MATCH (n) WHERE n.group_id = 'conv-fixture-aurora'
OPTIONAL MATCH (n)-[r]-(m)
RETURN n, r, m
```

Facts with their temporal fields, as a table rather than a graph. `valid_at` is when the fact
became true and `created_at` is when the system learned it — the distinction
[ADR 0002](../adr/0002-temporal-graph-over-vector-only.md) exists for:

```cypher
MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
RETURN a.name AS subject, r.fact AS fact, b.name AS object,
       r.valid_at AS valid_from, r.created_at AS learned_at
ORDER BY r.created_at DESC
```

Duplicate entities, which is entity resolution failing:

```cypher
MATCH (e:Entity)
WITH e.name AS name, count(*) AS copies
WHERE copies > 1
RETURN name, copies ORDER BY copies DESC
```

## Two things that make it unpleasant

**Every node carries an embedding.** `Entity.name_embedding` is 768 floats and
`RELATES_TO.fact_embedding` is another. The graph view is unaffected, but clicking a node
fills the inspector with numbers, and returning many nodes ships all those vectors over Bolt.
Keep a `LIMIT` on exploratory queries. Cypher cannot return a node with a property removed —
only a map — so a clean inspector means projecting to columns and losing the graph view.

**Captions default to something unhelpful.** Click the `Entity` label chip above the result
frame and set the caption to `name`; do the same for `Episodic`. Browser remembers this per
database.

## Reading what you see

A healthy graph has episodes fanning out to entities that appear in the transcript, and facts
connecting entities that genuinely relate.

On the first full bring-up it looked nothing like that. Three episodes produced six entities,
of which one was the conversation's own filename and two were a duplicated `Jordan`, and the
single fact was:

> `Nisha's dad` —"Mustang is the owner of the dog named Nimbus"→ `Mustang`

No Mustang, Nisha, Jordan, or Alex appears in any transcript. The extraction model invented
all of them. That is the open problem recorded in
[the phase notes](../phases/03-04-memory-mvp.md#what-the-first-real-bring-up-taught), and this
runbook exists partly so it stays visible: the retrieval harness in
[ADR 0009](../adr/0009-measured-reranking.md) scores ranking over a hand-labeled set and cannot
see a fabricated fact at all.
