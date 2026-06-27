# The AI Agent Tech Stack

> An agent is a stack, not a model — six layers decide whether it works, scales, or falls over.

**Type:** Learn
**Prerequisites:** What is an AI Agent?, How AI Agents Chain Tools, Memory, and Reasoning, LLM Fundamentals, RAG basics
**Time:** ~30 minutes

---

## The Problem

Most teams ship an "AI agent" by calling a foundation model in a loop and stitching together a few API calls. It works in a demo. In production it breaks in five different places: the model hallucinates, the tool calls are unreliable, there is no memory between sessions, the agent cannot observe what it is doing, and nobody can tell why a particular run produced a particular answer. Each of those failures lives in a different layer of the stack, and fixing them requires picking the right technology for the right layer.

The temptation is to treat the agent as one big thing — pick a framework, write some prompts, ship it. But "an agent" is not a single piece of software. It is a composition of at least six distinct layers, each with its own design choices, failure modes, and operational concerns. Choosing the wrong vector store, the wrong memory backend, or the wrong observability tool means you will rebuild that layer six months in. This lesson gives you a working mental model of all six layers so you can decide deliberately which pieces to assemble.

---

## The Concept

### The six-layer architecture

An AI agent is built from six layers that cooperate at request time. Each layer has a single responsibility and several mature technology options.

```
┌─────────────────────────────────────────────────────────────┐
│  6. Memory Management                                       │
│     (short-term context, long-term episodic/semantic)       │
├─────────────────────────────────────────────────────────────┤
│  5. Observability                                           │
│     (traces, evals, prompt versioning, cost tracking)       │
├─────────────────────────────────────────────────────────────┤
│  4. Tool Execution                                          │
│     (function calling, MCP servers, browser/computer use)   │
├─────────────────────────────────────────────────────────────┤
│  3. Agent Development Framework                             │
│     (LangGraph, CrewAI, AutoGen, n8n, smolagents)           │
├─────────────────────────────────────────────────────────────┤
│  2. Data Storage                                            │
│     (vector DB, relational DB, object store, caches)        │
├─────────────────────────────────────────────────────────────┤
│  1. Foundation Model                                        │
│     (GPT-4o, Claude, Gemini, Llama, Mistral, DeepSeek)      │
└─────────────────────────────────────────────────────────────┘
```

The arrows between layers are not one-way. A tool execution layer may write to the data storage layer. Memory may feed the prompt. Observability taps into every layer. But the dependency order at runtime is always bottom-up: the framework calls the model, the model decides whether to call a tool, the tool reads or writes data, memory updates, observability logs everything.

---

### Layer 1 — Foundation Models

The foundation model is the agent's reasoning engine. It receives a prompt (system message + conversation history + retrieved context + tool descriptions), decides what to do next, and produces either text for the user or a structured tool call.

```
                    System prompt
                         │
   Conversation history  │
                         │
   Retrieved context ────┼──►  [Foundation Model]  ──►  Text response
                         │            │
   Available tools ──────┘            │
                                      ▼
                              Structured tool call
                              { "name": "...", "args": {...} }
```

Foundation models are usually accessed through an API (closed-source: OpenAI, Anthropic, Google) or self-hosted (open-weight: Llama, Mistral, Qwen, DeepSeek). The choice affects cost, latency, data residency, capability, and control.

**Closed-source APIs:** best-in-class capability on most reasoning benchmarks, fastest iteration on new features (vision, voice, longer context), but per-token pricing scales linearly with usage and you cannot inspect or fine-tune the weights.

**Open-weight models:** free at inference time on your own hardware, full control over weights and data, but you own the GPU cost and the operational burden of running inference reliably.

**What this layer solves:** natural language understanding, multi-step reasoning, code generation, tool/function calling, multimodal perception (text, image, audio).

**What this layer does not solve:** persistent memory, real-world action, knowledge of private data, observability of reasoning.

---

### Layer 2 — Data Storage

Agents need three kinds of storage that operate on different timescales:

```
   ┌───────────────────────┐    ┌──────────────────────────┐    ┌──────────────────────┐
   │  Working / scratch    │    │  Episodic & semantic     │    │  Long-term knowledge │
   │  (per-turn context)   │    │  memory                  │    │  (RAG corpus)        │
   │                       │    │                          │    │                      │
   │  Conversation buffer  │    │  Past interactions,      │    │  Documents, KBs,     │
   │  Tool results         │    │  user preferences,       │    │  embeddings          │
   │  Intermediate steps   │    │  learned facts           │    │                      │
   └───────────────────────┘    └──────────────────────────┘    └──────────────────────┘
        in-memory                   Redis, Postgres              Vector DB, S3
        short TTL                   minutes → months             durable
```

- **Vector databases** (Pinecone, Weaviate, Qdrant, Milvus, pgvector, Chroma) store embeddings for semantic search — the basis of RAG.
- **Relational databases** (Postgres, MySQL) store structured agent state, user preferences, conversation metadata.
- **Object stores** (S3, GCS) hold raw documents, uploaded files, generated artifacts.
- **Caches and key-value stores** (Redis, Memcached) absorb rate spikes and store ephemeral session data.

The data layer is where most performance and cost surprises hide. An agent that re-embeds the same document on every run, or that scans a million-vector index without a filter, will burn budget before it answers one question.

---

### Layer 3 — Agent Development Frameworks

The framework is the orchestration glue. It defines how state flows between steps, how the model is called, how tool results are fed back, and how the loop terminates.

```
   ┌──────────────┐
   │   Trigger    │ (user message, cron, webhook)
   └──────┬───────┘
          ▼
   ┌──────────────┐    ┌──────────────────┐
   │   Planner    │◄──►│  Foundation Model │
   └──────┬───────┘    └──────────────────┘
          │
          ▼
   ┌──────────────┐    ┌──────────────────┐
   │  Tool call?  │───►│  Tool Execution  │
   └──────┬───────┘    └──────────────────┘
          │ no
          ▼
   ┌──────────────┐
   │  Final reply │
   └──────────────┘
```

Frameworks fall into two philosophical camps:

| Camp | Examples | Mental model | Best for |
|---|---|---|---|
| Graph / code-first | LangGraph, AutoGen, smolagents, CrewAI | Explicit nodes and edges, full Python control | Production agents with complex branching |
| Visual / low-code | n8n, Flowise, Langflow, Dust | Drag-and-drop nodes, JSON serializable workflows | Rapid prototyping, non-engineers, business workflows |

Graph-based frameworks give you predictability and testability — you can inspect the state at every node. Visual frameworks give you speed and accessibility — a non-engineer can build and modify a workflow without touching code. Many teams use both: prototype in n8n, then port to LangGraph once the workflow is stable and needs reliability.

The framework does not decide whether your agent works. It decides whether you can debug, version, and evolve it.

---

### Layer 4 — Tool Execution

Tools are how agents touch the real world. A tool is anything the model can invoke by name with structured arguments: a database query, a REST API call, a file system operation, a browser action, a code execution sandbox.

```
   Model decides:    "I need to call get_user(user_id=42)"
                         │
                         ▼
   ┌──────────────────────────────────┐
   │        Tool execution layer       │
   │                                   │
   │  • Validate arguments             │
   │  • Authorize the call             │
   │  • Invoke the underlying system   │
   │  • Format the response            │
   │  • Handle errors / retries        │
   └──────────────────────────────────┘
                         │
                         ▼
   Structured result returned to model
```

The tool execution layer is where the agent's safety and reliability live. A model that decides to call a tool is making a *proposal*. The tool layer must validate the proposal (are the arguments well-formed?), authorize it (is the user allowed to delete that record?), execute it (does the API actually work?), and shape the response (will the model understand the error?). Skipping any of these steps is how agents make news for the wrong reasons.

Two standards have emerged:

- **Function calling / JSON schemas** — the model emits a JSON object, your code executes it. Proprietary to each model provider but well-supported.
- **Model Context Protocol (MCP)** — a uniform protocol that lets agents discover and call tools exposed by *any* MCP-compatible server, regardless of which model is driving the agent. Treats tools as first-class resources with self-describing schemas.

The execution layer also decides what to do when a tool fails. Retry once with the same arguments? Retry with corrected arguments? Surface the error to the user? Defer to a human? These policies are part of the layer, not the framework.

---

### Layer 5 — Memory Management

Memory is what makes an agent feel continuous rather than amnesiac. Without memory, every conversation starts from zero; the agent forgets what the user told it yesterday, repeats the same clarifying questions, and cannot learn from past mistakes.

Memory comes in three forms:

```
   Short-term (working memory)
       │
       │  Persisted to:
       ▼
   Long-term episodic  (specific past interactions)
       │
       │  Compressed / abstracted to:
       ▼
   Long-term semantic  (generalized facts about the user)
```

- **Short-term memory** is the conversation buffer — the last N turns that fit in the context window. Most frameworks handle this automatically; you usually just need to bound the length.
- **Long-term episodic memory** stores specific past interactions. Retrieval uses semantic similarity ("what did we discuss last time the user asked about pricing?") or recency ("the last 10 conversations").
- **Long-term semantic memory** stores distilled facts ("the user's name is Alex", "they prefer terse replies", "they are a backend engineer"). The agent extracts these from conversations and updates them over time.

The trap is unbounded memory growth. Every fact and every past turn the agent remembers costs tokens at inference. Without a policy to summarize, deduplicate, and forget, the prompt balloons, latency climbs, and bills explode. The memory layer needs explicit write paths (what gets remembered), read paths (how it is surfaced), and decay policies (what gets forgotten).

---

### Layer 6 — Observability

Agents are non-deterministic systems. The same prompt can produce different tool calls on different runs. Without observability you cannot answer the three questions that always come up: what did the agent do, why did it do it, and how much did it cost.

Observability spans four concerns:

| Concern | What it captures | Tooling examples |
|---|---|---|
| Tracing | Every LLM call, every tool invocation, every state transition, with timestamps and parent-child links | LangSmith, Langfuse, Arize Phoenix, Helicone, OpenLLMetry |
| Evaluation | Automated quality scoring on golden datasets, regression tests across prompt versions | Braintrust, LangSmith Evals, RAGAS, custom graders |
| Prompt versioning | Source-controlled prompts with A/B testing and rollback | PromptLayer, LangSmith Hub, internal Git repos |
| Cost & latency tracking | Token counts per call, dollar spend per user/feature, p50/p95/p99 latencies | Helicone, OpenAI usage dashboard, custom dashboards |

The minimum viable observability story for a production agent is a structured trace per run: prompt in, tool calls, tool responses, final output, total tokens, total cost, total latency. Without it you are flying blind.

---

## Build It / In Depth

### How the layers cooperate on a single request

Walk a user request through the stack to see where each layer contributes.

```
   User: "Find my last invoice from Acme Corp and email it to alex@acme.com"
                           │
                           ▼
   [1. Foundation Model]
       Receives: system prompt + conversation history + user request
       + tool descriptions (search_invoices, send_email)
       Decides: call search_invoices(company="Acme Corp")
                           │
                           ▼
   [4. Tool Execution]
       Validates arguments, authorizes the call,
       invokes billing API, returns invoice list
                           │
                           ▼
   [1. Foundation Model] (second turn)
       Decides: call send_email(to="alex@acme.com", attachment=invoice.pdf)
                           │
                           ▼
   [2. Data Storage]
       Fetches invoice.pdf from S3 by invoice ID
                           │
                           ▼
   [4. Tool Execution]
       Validates (file exists, attachment size limit),
       authorizes (does the user have permission to email invoices?),
       calls SMTP gateway, returns success/failure
                           │
                           ▼
   [5. Memory Management]
       Writes to long-term memory:
       "User has an account with Acme Corp"
                           │
                           ▼
   [6. Observability]
       Records the full trace:
       - 2 LLM calls (input/output tokens, cost)
       - 2 tool calls (success, latency)
       - 1 S3 read
       - 1 SMTP send
       - Total latency: 4.2s
                           │
                           ▼
   [1. Foundation Model] (third turn)
       "I've emailed your latest invoice from Acme Corp to alex@acme.com."
```

Every layer participated. Remove any one and the agent either cannot answer, cannot act, cannot remember, or cannot be improved.

---

### Choosing the right model for the right task

Not every layer-1 model fits every job. The selection problem looks like this:

```
                Latency-sensitive?  ───►  Yes  ──►  Small/fast model
                                          │
                                          No
                                          │
                                  Needs deep reasoning?
                                          │
                                  Yes  ──┴── No
                                   │         │
                                   ▼         ▼
                          Frontier model    Medium model
                          (GPT-4o, Claude   (GPT-4o-mini,
                           Opus, Gemini     Claude Haiku,
                           Ultra)           Llama 8B)
```

A common pattern is a tiered setup: a small fast model handles routing and classification, a large reasoning model handles complex generation, and an embedding model handles retrieval. Some teams run three different foundation models in one agent.

---

### Where the budget goes

For a typical production agent answering customer support questions at 10,000 conversations/day:

| Layer | Approximate share of cost |
|---|---|
| Foundation model tokens (input + output) | 60–75% |
| Embedding model (RAG) | 5–10% |
| Vector DB / storage | 5–10% |
| Tool API calls (third-party) | 5–15% |
| Observability / tracing | 1–3% |
| Framework overhead | <1% |

The foundation model dominates. Every optimization that reduces context size (better retrieval, tighter prompts, shorter memory, deduplicated tool descriptions) directly reduces the largest line item.

---

## Use It

### Decision cheat sheet

| If you need… | Reach for… |
|---|---|
| Best-in-class reasoning, multimodal, fastest path to production | Closed-source APIs (GPT-4o, Claude 3.5/4, Gemini) |
| Data residency, cost control, fine-tuning freedom, on-prem | Open-weight self-hosted (Llama 3.3, Mistral, Qwen, DeepSeek) |
| Standard RAG with semantic search | Managed vector DB (Pinecone, Weaviate Cloud, Qdrant Cloud) or Postgres + pgvector |
| Hybrid search (keyword + vector) | Elasticsearch / OpenSearch / Typesense |
| Complex multi-step agent with branching and cycles | LangGraph, AutoGen, smolagents |
| Quick prototype with non-engineers | n8n, Flowise, Langflow |
| Tool integration without writing glue code per service | MCP servers (filesystem, GitHub, Postgres, Slack, etc.) |
| Code execution sandbox | E2B, Modal, Code Interpreter API |
| Tracing and debugging | LangSmith, Langfuse, Arize Phoenix |
| Cost analytics | Helicone, OpenLLMetry |
| Evaluation framework | Braintrust, RAGAS, custom graders |
| User-facing long-term memory | Zep, Letta, mem0 |

### A pragmatic starter stack

For a small team shipping its first production agent:

1. **Model:** GPT-4o-mini or Claude Haiku (cheap, fast, good enough for most tasks)
2. **Storage:** Postgres + pgvector (one less system to operate)
3. **Framework:** LangGraph (Pythonic, explicit, testable)
4. **Tools:** MCP servers for the 3–5 systems you actually need (GitHub, Slack, internal DB)
5. **Memory:** LangGraph checkpointer for short-term, simple JSON or Postgres table for long-term
6. **Observability:** LangSmith (if LangGraph) or Langfuse (framework-agnostic)

This stack runs on a few hundred dollars a month for moderate traffic, scales to tens of thousands of conversations per day, and keeps operational complexity low. Add managed services (Pinecone, dedicated observability platforms, dedicated model routers) only when you have proven the agent's value and hit specific scaling limits.

---

## Common Pitfalls

- **Treating the foundation model as the whole agent.** The model is one of six layers. Shipping only a prompt and a few API calls leaves you with no memory, no observability, no tool safety, and no debuggability. Production agents are pipelines, not prompts.

- **Skipping observability until something breaks.** Adding tracing after the agent is in production means you have no data about the bugs that already happened. Wire LangSmith / Langfuse / OpenLLMetry into the first user, not the first incident.

- **Vector DB without a metadata filter.** Pure semantic search returns the most similar chunks in the entire corpus. Without metadata filters (tenant, user, document type, recency), the agent retrieves irrelevant content and confuses itself. Always store and query with metadata.

- **Unbounded memory.** "Remember everything" is not a memory policy. Every fact stored costs tokens forever. Without summarization, deduplication, and decay, prompts grow, latency climbs, and bills balloon. Decide what is worth remembering.

- **Tools without authorization.** Letting the model call `delete_user(user_id=...)` directly is how agents get headlines. The tool execution layer must enforce authorization, not the model. The model proposes; the layer decides.

- **Picking the framework before the use case.** "Let's use LangGraph" or "let's use CrewAI" is backwards. The framework is the last decision — after the model, the storage, the tool surface, and the memory shape are clear. Otherwise you are reverse-fitting requirements to a tool.

- **Ignoring the cost model until the bill arrives.** Agents in a loop with large context windows and long tool chains can spend dollars per request without warning. Track token usage per request, per user, per feature from day one.

---

## Exercises

1. **Easy** — Map the six layers onto a customer support agent you know (a real product or a hypothetical one). For each layer, write one sentence describing the technology you would pick and why.

2. **Medium** — You are building a research agent that searches the web, reads PDFs, and writes reports. The average conversation has 12 turns, the agent invokes ~5 tools per turn, and the user wants the agent to remember preferences across sessions. Sketch the data storage layer: what goes in the vector DB, what goes in Postgres, what stays in-memory, and what is written to long-term memory. Justify each placement.

3. **Hard** — A regulated-industry client wants an agent that can call internal APIs (CRM, billing, ticketing) on behalf of authenticated users. Design the tool execution layer so that: (a) the agent can only call APIs the user is authorized to use, (b) every call is auditable, (c) prompt injection from tool responses cannot escalate privileges, and (d) a runaway loop cannot rack up API costs. Describe the architectural controls at each step.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| AI agent | A chatbot that calls APIs | A multi-layer system that combines a foundation model, a development framework, tools, memory, data storage, and observability into a loop that pursues a goal autonomously |
| Foundation model | The agent | One layer of the agent — the reasoning engine; without the other five layers, a model is just a chatbot |
| Function calling | The agent's way of using tools | A protocol where the model emits a structured JSON object describing a desired tool invocation; the agent's tool execution layer is responsible for actually running it |
| MCP | A replacement for APIs | A standardized protocol for exposing tools and resources to any MCP-compatible agent; it does not replace APIs, it provides a uniform discovery and calling layer over them |
| Vector database | A search engine | A specialized database optimized for similarity search over high-dimensional embeddings; not a general-purpose database, and not a keyword search engine |
| Memory | Storing past conversations | A multi-tier system with short-term (conversation buffer), long-term episodic (specific past interactions), and long-term semantic (distilled facts) tiers — each with different read/write/decay policies |
| Observability | Reading logs | Structured traces of every LLM call, tool call, and state transition, correlated under a single run ID, with token counts, costs, and latencies attached — the only way to debug a non-deterministic system |
| Agent framework | The whole agent | The orchestration layer that manages the loop between model calls and tool calls; it does not include the model, the tools, the memory, or the storage — those are separate layers |

---

## Further Reading

- **LangGraph Documentation** — the canonical reference for graph-based agent orchestration, with patterns for state management, persistence, and human-in-the-loop: https://langchain-ai.github.io/langgraph/
- **Anthropic's "Building Effective Agents"** — research-backed guidance on when to use agents vs chains, and the failure modes that drive production costs: https://www.anthropic.com/research/building-effective-agents
- **Model Context Protocol Specification** — the open standard for tool and resource exposure that MCP-compatible agents and servers implement: https://modelcontextprotocol.io
- **Langfuse Documentation** — open-source LLM observability with tracing, evaluation, and prompt management: https://langfuse.com/docs
- **"The Six-Layer Cake of an AI Agent"** by Latent Space — a practitioner's breakdown of how the layers interact in production: https://www.latent.space