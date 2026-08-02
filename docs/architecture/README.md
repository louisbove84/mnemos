# Architecture

The system is modelled in [C4](https://c4model.com) using the
[Structurizr DSL](https://docs.structurizr.com/dsl). `workspace.dsl` is the single source of
truth — every view is generated from it, so the Context and Container diagrams cannot drift
apart.

## Viewing it locally

The Structurizr local server runs offline, needs no account, and hot-reloads when you save
the DSL:

```bash
docker run -it --rm -p 8080:8080 \
  -v "$(pwd)/docs/architecture:/usr/local/structurizr" \
  structurizr/structurizr local
```

Then open <http://localhost:8080>.

## Views

| View | Purpose |
| --- | --- |
| `Context` | Who uses mnemos and what it connects to |
| `Containers_Current` | Only what is built or actively being built |
| `Containers_Target` | The full intended system, explicitly aspirational |
| `Deployment_Homelab` | Which machine runs what, and the platform that puts it there |

The split is deliberate. Diagramming a system that does not exist is how architecture
becomes fiction, so current state and target state are never mixed in one view. Containers
are tagged with the phase that delivers them and shaded by build status.

Argo CD, Traefik, and Prometheus are infrastructure nodes in the deployment view rather than
containers. They are how mnemos is operated, not parts of what mnemos is, and putting them
in the Container view would blur a distinction worth keeping.

## Exporting diagrams

GitHub does not render Structurizr DSL natively, so images are exported for the README and
blog posts:

```bash
docker run --rm -v "$(pwd)/docs/architecture:/usr/local/structurizr" \
  structurizr/structurizr export -workspace workspace.dsl -format mermaid -output images
```

CI validates the DSL on every pull request. Regenerate images when a view changes.
