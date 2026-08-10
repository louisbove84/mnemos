workspace "mnemos" "Air-gappable, provider-neutral long-term memory for AI conversations" {

    model {
        operator = person "Operator" "Deliberates long-running decisions with AI assistants and owns the record"

        clients = softwareSystem "AI Clients" "Claude, Cursor, Open WebUI, or any MCP-capable client" {
            tags "External"
        }

        mnemos = softwareSystem "mnemos" "Remembers conversations across providers, on hardware you control" {

            serving = container "Model Serving" "Local LLM inference for extraction and synthesis" "OpenAI-compatible HTTP, llama.cpp" {
                tags "Phase 0"
            }
            lake = container "Object Store" "S3-compatible artifact store for multi-writer and air-gap bundles" "MinIO" {
                tags "Phase 3" "Not Built"
            }
            inbox = container "Export Inbox" "Provider export landing zone on node disk" "hostPath /srv/mnemos/data" {
                tags "Phase 3" "In Progress"
            }
            ingest = container "Ingestion Pipeline" "Parses provider exports into timestamped episodes" "Python" {
                tags "Phase 3" "In Progress"
            }
            archive = container "Transcript Archive" "Immutable verbatim source of truth" "PostgreSQL" {
                tags "Phase 4" "In Progress"
            }
            extract = container "Extraction Service" "Turns episodes into temporal facts and resolves contradictions" "Python, Graphiti" {
                tags "Phase 4" "In Progress"
            }
            graph = container "Context Graph" "Bi-temporal knowledge graph with hybrid retrieval" "Neo4j" {
                tags "Phase 4" "In Progress"
            }
            mcp = container "MCP Server" "Exposes memory as tools over Model Context Protocol" "Python" {
                tags "Phase 4" "In Progress"
            }
            ui = container "Web UI" "Chat, decision journal, and timeline" "React, TypeScript" {
                tags "Phase 5" "Not Built"
            }
        }

        operator -> clients "Converses with"
        operator -> ui "Reviews decisions and history in"
        clients -> mcp "Reads and writes memory via MCP"
        ui -> mcp "Queries memory via"
        mcp -> graph "Hybrid retrieval from"
        mcp -> archive "Fetches verbatim excerpts from"
        mcp -> serving "Synthesises answers using"
        ingest -> inbox "Reads raw exports from"
        ingest -> lake "Will store raw exports in (deferred)"
        ingest -> archive "Writes transcripts to"
        ingest -> extract "Emits episodes to"
        extract -> serving "Extracts entities and facts using"
        extract -> graph "Writes temporal facts to"

        homelab = deploymentEnvironment "Homelab" {
            workstation = deploymentNode "Mac workstation" "Authoring and administration only; runs no workload" "macOS" {
                tools = infrastructureNode "kubectl, helm, browser" "Bootstraps the cluster once, then reads it" "CLI"
            }

            node = deploymentNode "GPU laptop" "Single-node cluster with an NVIDIA GPU" "Linux, k3s" {
                traefik = infrastructureNode "Traefik" "Routes hostnames to services" "Ingress, bundled with k3s"
                argocd = infrastructureNode "Argo CD" "Reconciles the cluster against the git repository" "GitOps"
                prometheus = infrastructureNode "Prometheus and Grafana" "Collects and displays cluster and GPU metrics" "kube-prometheus-stack"

                deploymentNode "namespace: mnemos" {
                    servingInstance = containerInstance serving
                    archiveInstance = containerInstance archive
                    graphInstance = containerInstance graph
                    ingestInstance = containerInstance ingest
                    mcpInstance = containerInstance mcp
                    inboxInstance = containerInstance inbox
                }
            }
        }

        tools -> argocd "Bootstraps, then observes"
        tools -> traefik "Reaches the UIs through"
        traefik -> argocd "Routes argocd.mnemos.local to"
        traefik -> prometheus "Routes grafana.mnemos.local to"
        argocd -> servingInstance "Deploys and self-heals"
        argocd -> archiveInstance "Deploys and self-heals"
        argocd -> graphInstance "Deploys and self-heals"
        argocd -> ingestInstance "Deploys and self-heals"
        argocd -> mcpInstance "Deploys and self-heals"
        prometheus -> servingInstance "Scrapes metrics from"
    }

    views {
        systemContext mnemos "Context" {
            include *
            autolayout lr
            description "Who uses mnemos and what it connects to."
        }

        container mnemos "Containers_Current" {
            include serving inbox ingest archive extract graph mcp
            autolayout lr
            description "Built or actively being built today. See README for phase status."
        }

        container mnemos "Containers_Target" {
            include *
            autolayout lr
            description "TARGET STATE. Aspirational - most of this does not exist yet."
        }

        deployment mnemos "Homelab" "Deployment_Homelab" {
            include *
            autolayout lr
            description "Where the built parts actually run, and the platform that puts them there."
        }

        styles {
            element "Person" {
                shape person
                background #2c3e50
                color #ffffff
            }
            element "Software System" {
                background #1168bd
                color #ffffff
            }
            element "External" {
                background #8e9499
                color #ffffff
            }
            element "Container" {
                background #438dd5
                color #ffffff
            }
            element "In Progress" {
                background #e08e0b
                color #ffffff
            }
            element "Not Built" {
                background #d8dcdf
                color #55606a
            }
        }
    }
}
