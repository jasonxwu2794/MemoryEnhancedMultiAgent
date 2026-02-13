# OpenClaw Distro — Complete Architecture Document

## Project Vision

A batteries-included distribution wrapper around OpenClaw that provides:
- **One-command installer** with TUI wizard (using `gum`)
- **5 isolated AI agents** orchestrated via message bus
- **Layered memory system** with LanceDB (vectors) + SQLite (structured)
- **GitOps pipeline** for config management and deployment
- **Auto-updating configs** that merge upstream defaults with user overrides
- **Guided tool installation** for MCP servers and integrations

## The 5 Default Agents

### 🧠 Brain (Chief of Staff)
- **Role**: Intent classification, task decomposition, delegation, response synthesis, memory gatekeeper
- **Model**: Best available (moonshot/kimi-k2.5 or claude)
- **Permissions**: Can delegate, can write shared memory, talks to user
- **Sub-agents**: NEVER — must maintain unified coherence
- **Network**: Internal agent bus only
- **Container**: Reads shared memory, owns conversation state

### 🔨 Builder (Engineer)
- **Role**: Code generation, file operations, tool execution, debugging
- **Model**: Fast code model (deepseek-chat or codestral)
- **Permissions**: Can execute code, NO internet, NO memory writes, flags factual claims
- **Sub-agents**: YES for multi-component builds (architect step → parallel build → integration → test)
- **Network**: Agent bus + sandboxed execution network (no internet)
- **Container**: Workspace volume, sandbox isolation

### ✅ Fact Checker (Editor/QA)
- **Role**: Claim verification, source checking, consistency analysis, hallucination detection, knowledge cache updates
- **Model**: Precise reasoning model (qwen-max or claude)
- **Permissions**: Can search web, can update knowledge cache, NO code execution
- **Sub-agents**: YES for batch verification (parallel claim checking)
- **Network**: Agent bus + external (web access)
- **Container**: Knowledge cache volume

### 🔬 Researcher (Analyst/Librarian)
- **Role**: Proactive information gathering, multi-source synthesis, documentation reading, prior art discovery
- **Model**: Good at synthesis (qwen-max or kimi-k2.5)
- **Permissions**: Full web access, can read repos/docs, feeds knowledge cache
- **Sub-agents**: ALWAYS — research is embarrassingly parallel (3-6 threads per query, then synthesis)
- **Network**: Agent bus + external (web access)
- **Container**: Knowledge cache volume (read/write)

### 🛡️ Guardian (Security Lead)
- **Role**: Security review of Builder output, config validation before deploy, prompt injection detection, permissions monitoring, cost tracking
- **Model**: Precise model (claude or qwen-max)
- **Permissions**: Read-only on all agent outputs, can BLOCK deployments, monitors costs
- **Sub-agents**: NEVER — must see full picture, security gaps hide between scoped reviews
- **Network**: Agent bus only (no external needed)
- **Container**: Read-only access to all workspaces

## Sub-Agent Design

Sub-agents are NOT separate containers. They are lightweight concurrent LLM calls within the parent agent's container with isolated context.

### Sub-Agent Decision Matrix
| Agent | Sub-Agents? | Trigger Condition |
|-------|-------------|-------------------|
| Brain | ✗ Never | N/A |
| Builder | ✓ Conditional | Multi-component builds only. Single scripts stay single-threaded. |
| Fact Checker | ✓ Conditional | Batch verification (3+ claims). Single claims stay single-threaded. |
| Researcher | ✓ Always | Every research query decomposes into 3-6 parallel threads. |
| Guardian | ✗ Never | N/A |

### Sub-Agent Flow (Builder example)
1. **Architect step** (single-threaded): Define interfaces, contracts, conventions
2. **Parallel build**: Sub-agents each build one component with shared interface contracts
3. **Integration** (single-threaded): Merge components, resolve conflicts
4. **Test** (single-threaded): Run integration tests

### Sub-Agent Flow (Researcher example)
1. **Decompose**: Break query into 3-6 independent investigation threads
2. **Parallel research**: Each sub-agent pursues one thread (web search, cache, docs)
3. **Synthesize** (single-threaded): Merge findings into coherent research brief

## Communication Protocol

All agents communicate through a Redis message bus. No direct agent-to-agent communication.

### Message Format
```python
@dataclass
class AgentMessage:
    task_id: str          # UUID
    from_agent: AgentRole # brain, builder, fact_checker, researcher, guardian
    to_agent: AgentRole
    action: str           # "build", "verify", "research", "review", "synthesize"
    payload: dict         # Task-specific data
    context: dict         # SCOPED — only what this agent needs
    constraints: dict     # Budget limits, time limits, scope limits
    status: TaskStatus    # pending, in_progress, completed, failed, needs_review
    result: Optional[dict]
```

### Context Scoping (Critical)
The Brain acts as a privacy/relevance filter. Each agent ONLY receives the context it needs:
- **Builder** gets: recent code context, file state, available tools, interface contracts
- **Fact Checker** gets: claims to verify, knowledge cache excerpts, conversation claims
- **Researcher** gets: research query, known knowledge gaps, preferred source types
- **Guardian** gets: full output under review, permissions config, cost metrics

## Memory Architecture

### Three Tiers
1. **Working Memory**: Current conversation context (in-context window)
2. **Short-term Memory**: Recent interactions, high recency score (LanceDB vectors)
3. **Long-term Memory**: Consolidated knowledge, high importance score (LanceDB + SQLite)

### Knowledge Cache (SQLite)
Verified facts with no decay. Updated by Fact Checker and Researcher.

### Scoring System
Each memory gets a composite score:
- **Semantic similarity**: Cosine distance from query embedding (via LanceDB)
- **Recency score**: Exponential decay with 7-day half-life
- **Importance score**: Heuristic based on signals (user explicit, decision, error correction, preference, repetition)

### Retrieval Strategies
- `"balanced"`: 0.4 semantic + 0.3 recency + 0.3 importance
- `"recency"`: 0.3 semantic + 0.5 recency + 0.2 importance
- `"importance"`: 0.3 semantic + 0.2 recency + 0.5 importance
- `"exact"`: Check knowledge cache first, fallback to semantic

### Memory Permissions
- **Brain**: Read + write shared memory (gatekeeper)
- **Builder**: Read shared memory only
- **Fact Checker**: Read shared memory, write knowledge cache
- **Researcher**: Read shared memory, write knowledge cache
- **Guardian**: Read all memory (audit), no writes

## Config System

### Three-Layer Precedence (highest → lowest)
1. **User overrides** (`configs/user/local.yaml`) — never auto-modified
2. **Distro defaults** (`configs/overlays/{use_case}/`) — auto-updated with distro
3. **OpenClaw upstream** (`configs/base/openclaw.yaml`) — auto-updated

### Auto-Update Flow
1. Cron/systemd timer runs `updater/auto_update.sh`
2. Pulls latest distro defaults from git
3. `config_merger.py` deep-merges: upstream ← distro ← user
4. Writes final config to `data/.openclaw/config.yaml`
5. Git hooks detect change → restart services

## GitOps Pipeline

### Local GitOps
- Pre-commit hook: Validate configs (YAML schema, permissions check)
- Post-merge hook: Auto-restart services on config pull
- `make deploy` / `make rollback` / `make update`

### Optional Remote CI/CD
- GitHub Actions: On push to `configs/**`, validate and SSH deploy to VPS

## Docker Architecture

### Containers
- `brain` — Brain agent
- `builder` — Builder agent + code sandbox
- `fact_checker` — Fact Checker agent
- `researcher` — Researcher agent
- `guardian` — Guardian agent (interceptor on message bus)
- `message-bus` — Redis for agent communication
- `vector-db` — LanceDB service (or embedded in each agent)

### Networks
- `agent-bus` (internal) — All agents communicate here
- `sandbox` (internal, no internet) — Builder's code execution
- `external` (bridge) — Fact Checker + Researcher web access

### Volumes
- `shared-memory` — Shared LanceDB + SQLite (read by all, written by Brain)
- `knowledge-cache` — Verified facts (written by Fact Checker + Researcher)
- `workspace` — Builder's code sandbox
- `conversations` — Conversation history
- `configs` — Configuration files

## Wizard Flow

### Steps
1. Prerequisites check (Docker, gum, git)
2. Use case selection (General, Coding, Research, Trading/DeFi, Custom)
3. Primary/fallback model selection per agent
4. API key entry (guided, per provider)
5. Memory tier selection (Full / Standard / Minimal)
6. Tool selection (MCP servers, integrations)
7. Integration setup (GitHub, Telegram, Discord)
8. Agent mode (Full trio+2, Duo, Solo)
9. GitOps setup (init repo, optional remote)
10. Generate configs from templates → Docker compose up

## File Structure

```
openclaw-distro/
├── install.sh                          # Entry point
├── wizard/
│   ├── tui.sh                          # Main wizard (gum-based)
│   ├── steps/
│   │   ├── 01_prerequisites.sh
│   │   ├── 02_use_case.sh
│   │   ├── 03_model_selection.sh
│   │   ├── 04_api_keys.sh
│   │   ├── 05_memory_setup.sh
│   │   ├── 06_tools_install.sh
│   │   ├── 07_integrations.sh
│   │   ├── 08_agent_mode.sh
│   │   └── 09_gitops_setup.sh
│   ├── templates/
│   │   ├── docker-compose.yml.j2
│   │   ├── .env.j2
│   │   └── agent_configs.yaml.j2
│   └── generate_configs.sh
├── agents/
│   ├── common/
│   │   ├── protocol.py                 # AgentMessage, MessageBus
│   │   ├── base_agent.py               # Shared agent scaffolding
│   │   ├── sub_agent.py                # SubAgentPool
│   │   ├── llm_client.py               # Unified LLM interface
│   │   └── Dockerfile.base
│   ├── brain/
│   │   ├── brain.py
│   │   ├── classifier.py
│   │   ├── decomposer.py
│   │   ├── synthesizer.py
│   │   ├── system_prompt.md
│   │   └── Dockerfile
│   ├── builder/
│   │   ├── builder.py
│   │   ├── sandbox.py
│   │   ├── tool_runner.py
│   │   ├── system_prompt.md
│   │   └── Dockerfile
│   ├── fact_checker/
│   │   ├── fact_checker.py
│   │   ├── consistency.py
│   │   ├── web_verifier.py
│   │   ├── system_prompt.md
│   │   └── Dockerfile
│   ├── researcher/
│   │   ├── researcher.py
│   │   ├── source_evaluator.py
│   │   ├── synthesizer.py
│   │   ├── system_prompt.md
│   │   └── Dockerfile
│   └── guardian/
│       ├── guardian.py
│       ├── security_scanner.py
│       ├── cost_tracker.py
│       ├── system_prompt.md
│       └── Dockerfile
├── memory/
│   ├── engine.py                       # MemoryEngine orchestration
│   ├── vector_store.py                 # LanceDB wrapper
│   ├── scored_memory.py                # Importance + recency scoring
│   ├── knowledge_cache.py              # SQLite fact cache
│   ├── embeddings.py                   # Embedding generation
│   ├── consolidation.py                # Background memory maintenance
│   ├── schemas/
│   │   ├── lancedb_tables.py
│   │   └── sqlite_schema.sql
│   └── retrieval.py                    # Layered search
├── configs/
│   ├── base/
│   │   ├── openclaw.yaml
│   │   ├── agents.yaml
│   │   ├── routing_rules.yaml
│   │   ├── permissions.yaml
│   │   └── system-prompts/
│   ├── overlays/
│   │   ├── coding-assistant/
│   │   ├── research-agent/
│   │   ├── trading-analyst/
│   │   └── general-purpose/
│   └── user/                           # gitignored
│       └── local.yaml
├── gitops/
│   ├── watcher.py
│   ├── hooks/
│   │   ├── pre-commit
│   │   └── post-merge
│   ├── Makefile
│   └── ci/
│       └── github-actions.yml
├── updater/
│   ├── auto_update.sh
│   ├── config_merger.py
│   └── openclaw_updater.py
├── tools/
│   ├── registry.yaml
│   └── installers/
│       ├── mcp_filesystem.sh
│       ├── mcp_github.sh
│       ├── mcp_browser.sh
│       ├── web_search.sh
│       └── custom_tool_template/
├── docker-compose.yml
├── Makefile
├── ARCHITECTURE.md                     # This file
└── README.md
```

## Implementation Phases

### Phase 1 — Foundation (MVP)
- Wizard (gum TUI) with all steps
- Docker Compose generation from Jinja2 templates
- Config overlay system (base + use-case + user)
- Single-agent mode working (classic OpenClaw wrapper)
- Basic auto-updater

### Phase 2 — Memory System
- LanceDB vector store integration
- SQLite knowledge cache + scoring tables
- Retrieval API with importance/recency scoring
- Embedding generation (local or API)
- Hook into OpenClaw conversation flow

### Phase 3 — Multi-Agent
- Redis message bus
- Brain agent (classifier, decomposer, synthesizer)
- Builder agent with sandbox
- Fact Checker agent with web verification
- Researcher agent with parallel sub-agents
- Guardian agent as interceptor

### Phase 4 — GitOps + Polish
- Git hooks for config validation + auto-restart
- GitHub Actions for remote deploy
- Tool registry + guided installers
- Sub-agent pools for Builder and Fact Checker
- Cost tracking dashboard
- Memory consolidation background job

## Key Design Decisions

1. **Redis for message bus** (not HTTP/gRPC) — simple, proven, supports pub/sub for interceptor pattern (Guardian)
2. **LanceDB embedded** (not Pinecone/Weaviate) — no separate server, pip install, good enough for single-VPS scale
3. **SQLite for structured storage** (not Postgres) — zero config, file-based, perfect for knowledge cache
4. **gum for TUI** (not curses/textual) — single binary, beautiful defaults, shell-native
5. **Jinja2 templates** (not Helm/Kustomize) — familiar to Python devs, flexible enough
6. **Sub-agents as concurrent calls** (not containers) — lightweight, fast spawn, shared model connection
7. **Guardian as interceptor** (not peer agent) — sees all traffic, can block, doesn't need delegation
