# Working agreement

This is currently a solo project, but it is built to the standards of a team project. The
point is the habit, not the ceremony.

## Branches and pull requests

- `main` is always deployable and protected. No direct commits.
- Branch names: `feat/short-description`, `fix/short-description`, `docs/short-description`,
  `chore/short-description`.
- One logical change per pull request. If the description needs the word "also", split it.
- CI must pass before merge. Squash merge, so the PR title becomes the commit message.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/): `type(scope): summary`.

```
feat(mcp): expose point-in-time fact queries
fix(ingest): handle transcripts with missing timestamps
docs(adr): record decision to use a temporal graph
```

Explain *why* in the body when the reason is not obvious from the diff. Do not explain what
the code does — the code does that.

## Architecture changes

The C4 model in `docs/architecture/workspace.dsl` is part of the codebase, not documentation
about it. A pull request that adds or removes a container updates the model in the same PR.

**The phase rule:** nothing appears in the Container view that is not built or actively being
built in the current phase. Aspirational architecture belongs in a view explicitly labelled as
a target state. A diagram of a system that does not exist is a liability.

## Architecture decision records

Any decision that is expensive to reverse gets an ADR in `docs/adr` before the code lands.
Copy `template.md`, take the next number, and keep it short — one page is a good ADR.

Reversible decisions do not need an ADR. Choosing a graph database does. Choosing a
logging format does not.

## Tests

New behaviour ships with a test. The memory engine additionally has an evaluation suite
(Phase 4) that measures retrieval quality; regressions there are treated as failures, not
as noise.
