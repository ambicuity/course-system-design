# The Agentic AI Learning Roadmap

> Seven stages from "I know Python" to "I ship a multi-agent production system" — the path that turns a developer into an AI engineer.

**Type:** Learn
**Prerequisites:** Basic programming, command-line comfort
**Time:** ~20 minutes

---

## The Problem

There are now dozens of "learn AI" roadmaps. Most are lists of models, frameworks, and papers — long, undifferentiated, and missing the actual skills you need to build things. They confuse *knowing* with *doing*. You can read every chapter in this phase and still not be able to ship an agent that handles 1000 user requests a day.

A learning roadmap for AI agents needs to do more than enumerate topics. It needs to sequence them. It needs to make clear which skills are prerequisites for which. And it needs to identify the moments where you stop learning and start building — because that is when the real learning happens.

This lesson is a seven-stage roadmap, ordered by dependency, that takes you from "I have written Python before" to "I have shipped a multi-agent production system." Each stage has a concrete goal, a list of topics, and a recommended project. Follow the stages in order; do not skip ahead.

---

## The Concept

### The seven stages

```
   Stage 1: Foundations
   ────────────────────
   Python, Git, APIs, JSON, command line
   You can build things with code.

           │
           ▼
   Stage 2: LLM Fundamentals
   ────────────────────────
   How LLMs work, tokenization, context, prompting
   You can talk to a model and understand its limits.

           │
           ▼
   Stage 3: RAG & Embeddings
   ─────────────────────────
   Vector databases, embeddings, retrieval pipelines
   You can ground a model in external knowledge.

           │
           ▼
   Stage 4: Agent Foundations
   ───────────────────────────
   Function calling, ReAct, tool use, memory
   You can build an agent that does multi-step work.

           │
           ▼
   Stage 5: Agent Frameworks
   ─────────────────────────
   LangGraph, AutoGen, CrewAI, smolagents
   You can pick the right framework for the job.

           │
           ▼
   Stage 6: Production Concerns
   ────────────────────────────
   Observability, evaluation, safety, cost
   You can run an agent at scale without surprises.

           │
           ▼
   Stage 7: Multi-Agent Systems
   ────────────────────────────
   A2A, handoffs, supervisor patterns, MCP at scale
   You can ship a system where agents collaborate.
```

Each stage takes roughly 2–6 weeks of focused work. The full path is 6–12 months for someone programming full-time.

---

### Stage 1: Foundations (2–4 weeks)

**Goal:** be able to build, test, and deploy small Python applications.

**Topics:**

- Python (intermediate level): functions, classes, async, virtual environments, packaging
- Git: branching, PRs, rebasing, conflict resolution
- Command line: bash, navigating the filesystem, running scripts, environment variables
- HTTP / REST: methods, status codes, headers, JSON
- APIs: calling them, authenticating, handling errors and rate limits
- JSON / data formats
- Basic Linux: process management, file permissions, SSH

**Resources:**

- *Automate the Boring Stuff with Python* — free, friendly intro
- *Python Crash Course* — solid foundation
- The Git Book — free, official

**Project:** build a CLI tool that pulls data from three public APIs (weather, news, GitHub) and writes a daily report to a file. Deploy it on a small VM.

**Done when:** you can write a 200-line Python script that calls APIs, processes JSON, and handles errors gracefully.

---

### Stage 2: LLM Fundamentals (2–3 weeks)

**Goal:** understand how large language models work and how to use them well.

**Topics:**

- What an LLM is: tokenization, transformer architecture, attention
- Context windows: what fits, what doesn't, how to manage long inputs
- Prompting: zero-shot, few-shot, chain-of-thought, system prompts
- Model selection: GPT-4o, Claude, Gemini, Llama — when to use which
- Token economics: how cost is computed, how to estimate
- Streaming: server-sent events, how to handle partial responses
- Limitations: hallucinations, knowledge cutoffs, what models cannot do

**Resources:**

- Andrej Karpathy's "Intro to LLMs" — one-hour video
- 3Blue1Brown's transformer series — visual explanations
- The OpenAI / Anthropic quickstarts

**Project:** build a chat interface (Next.js or Streamlit) that talks to GPT-4o or Claude, with streaming, conversation history, and a cost counter.

**Done when:** you can explain to a non-technical colleague what a token is, why a model hallucinates, and what context length means — and you can build a chat app that uses any major model API.

---

### Stage 3: RAG & Embeddings (2–3 weeks)

**Goal:** ground a model's responses in external knowledge.

**Topics:**

- Embeddings: what they are, how they are computed, cosine similarity
- Vector databases: pgvector, Qdrant, Chroma, Pinecone
- Chunking strategies: fixed-size, semantic, recursive
- Hybrid search: vector + BM25
- Re-ranking: cross-encoders, Cohere Rerank
- RAG evaluation: retrieval recall, answer faithfulness (RAGAS)
- Document parsing: PDF, DOCX, HTML, Markdown

**Resources:**

- The RAG chapter in this phase
- LlamaIndex documentation
- Pinecone's learning center

**Project:** build a RAG system over a corpus of 100+ documents (your company's wiki, a set of papers, a documentation site). Include hybrid search, re-ranking, and a RAGAS eval harness.

**Done when:** you can build a RAG system from scratch, evaluate it properly, and tune it for better recall.

---

### Stage 4: Agent Foundations (3–4 weeks)

**Goal:** build an agent that takes a goal, calls tools, and iterates.

**Topics:**

- Function calling: schemas, structured output, validation
- The ReAct loop: Thought → Action → Observation → repeat
- Tool design: what makes a good tool description
- Memory: short-term (buffer), long-term (episodic), long-term (semantic)
- Termination: max iterations, done signals, repetition detection
- Error handling: tool failures, malformed outputs, retries
- A simple hand-written agent (no framework, just an LLM call in a loop)

**Resources:**

- The "What is an AI Agent?" and "How AI Agents Chain Tools" chapters in this phase
- Lilian Weng's "LLM Powered Autonomous Agents"
- The ReAct paper

**Project:** build a research agent that searches the web, reads 3 articles, and produces a summary with citations. Hand-write the loop; do not use a framework yet.

**Done when:** you can build a working agent in 50–100 lines of Python without a framework, and you can debug it by adding logging at each step.

---

### Stage 5: Agent Frameworks (2–4 weeks)

**Goal:** pick the right framework and use it idiomatically.

**Topics:**

- LangGraph: graphs, state, conditional edges, persistence
- AutoGen: conversational agents, multi-agent patterns
- CrewAI: role-based crews, sequential and hierarchical processes
- smolagents: code-agent minimalism
- Provider SDKs: OpenAI Agents SDK, Claude Agent SDK
- MCP: Model Context Protocol basics

**Resources:**

- The "Top AI Agent Frameworks" chapter in this phase
- Framework docs (the quickstart + the concepts page, in that order)

**Project:** rewrite your Stage 4 agent in two of the frameworks above. Compare: lines of code, debuggability, observability, ease of adding new tools.

**Done when:** you can read a framework's documentation and identify which of your projects would benefit from it — and which would be hurt by it.

---

### Stage 6: Production Concerns (3–4 weeks)

**Goal:** run agents at scale with observability, evaluation, and safety.

**Topics:**

- Observability: tracing, logging, cost tracking (LangSmith, Langfuse, Phoenix)
- Evaluation: golden datasets, automated graders, regression testing
- Safety: prompt injection, output filtering, jailbreak prevention
- Cost control: caching, model routing, token budgets
- Performance: latency budgets, parallelization, batching
- Failure modes: rate limits, timeouts, retries with backoff
- Memory at scale: persistence, retrieval, decay policies

**Resources:**

- Langfuse documentation
- Anthropic's "Building Effective Agents"
- The "Common Pitfalls" sections of every chapter in this phase

**Project:** take your Stage 5 agent and put it in front of 100 real users for a week. Instrument everything. Build an eval harness. Find and fix at least three failure modes you did not anticipate.

**Done when:** you can deploy an agent, monitor it, evaluate it, and debug production incidents without panicking.

---

### Stage 7: Multi-Agent Systems (3–4 weeks)

**Goal:** ship systems where multiple agents collaborate, each with specialized roles.

**Topics:**

- Multi-agent patterns: supervisor, swarm, debate, hierarchical
- Agent-to-agent protocols: A2A, handoffs, message passing
- Cross-agent state: shared memory, message queues, event buses
- MCP at scale: many servers, discovery, version pinning
- Cross-runtime collaboration: LangGraph + CrewAI + custom agents
- Operational concerns at the system level: per-agent tracing, cost attribution

**Resources:**

- The "MCP vs A2A" chapter in this phase
- AutoGen's multi-agent documentation
- LangGraph's multi-agent cookbook

**Project:** build a multi-agent system for a real business problem — research → write → review → publish. Each agent uses different tools and runs in a different process. Use A2A (or equivalent) for inter-agent communication.

**Done when:** you can design a multi-agent architecture for a new problem, justify each agent's role and tools, and ship it with proper observability across agent boundaries.

---

## Build It / In Depth

### The recommended order, with time estimates

```
   Weeks  1–4   Stage 1: Foundations (Python, Git, APIs)
   Weeks  5–7   Stage 2: LLM Fundamentals
   Weeks  8–10  Stage 3: RAG & Embeddings
   Weeks 11–14  Stage 4: Agent Foundations
   Weeks 15–18  Stage 5: Agent Frameworks
   Weeks 19–22  Stage 6: Production Concerns
   Weeks 23–26  Stage 7: Multi-Agent Systems

   Total: ~6 months full-time, ~12 months part-time.
```

You can compress or stretch individual stages based on your prior experience. A senior backend engineer with Python skills can skip most of Stage 1 and probably much of Stage 2. A data scientist will find Stage 3 familiar.

---

### Skills by stage, at a glance

| Stage | Hard skills | Soft skills |
|---|---|---|
| 1. Foundations | Python, Git, HTTP, JSON | Debugging, reading docs |
| 2. LLM Fundamentals | Prompting, streaming, model selection | Critical thinking about model output |
| 3. RAG | Embeddings, vector DBs, evaluation | Information retrieval thinking |
| 4. Agent Foundations | Function calling, ReAct, debugging non-deterministic code | Patience for flaky behavior |
| 5. Frameworks | LangGraph, AutoGen, MCP | Framework-agnostic thinking |
| 6. Production | Observability, evals, cost control | Operational discipline |
| 7. Multi-agent | A2A, distributed systems thinking | System design at scale |

---

### What to learn alongside the roadmap

These skills accelerate every stage:

- **Linux / shell** — most production agents run on Linux
- **Docker** — agents are deployed as containers
- **Postgres** — most systems need a relational DB alongside the vector store
- **Cloud basics** (AWS / GCP / Azure) — you will deploy somewhere
- **TypeScript or modern frontend** — to build UIs for the agent
- **System design** — to design the architecture around the agent

---

## Use It

### What to read at each stage

| Stage | Read first |
|---|---|
| 1. Foundations | Automate the Boring Stuff |
| 2. LLM Fundamentals | Karpathy's "Intro to LLMs", this phase's transformer chapters |
| 3. RAG | The RAG chapters in this phase |
| 4. Agent Foundations | "What is an AI Agent?", "How AI Agents Chain Tools" |
| 5. Frameworks | The frameworks chapter, then the chosen framework's docs |
| 6. Production | Anthropic's "Building Effective Agents", Langfuse docs |
| 7. Multi-agent | The "MCP vs A2A" chapter, AutoGen multi-agent docs |

### What to build at each stage

Already covered in each stage above. The pattern is consistent: each stage ends with a project that uses the skills you just learned and demonstrates them concretely.

### When to deviate from the order

The roadmap is a default. Adjust based on your goals:

```
   Want to ship a personal assistant ASAP?
   Skip Stage 3, rush Stage 4–5.

   Want to be a researcher?
   Spend more time on Stage 2 and 3.

   Want to be a platform engineer?
   Spend more time on Stage 6 and 7.

   Already a backend engineer?
   Compress Stages 1 and 2 to a week.

   Already an ML engineer?
   Compress Stage 3, focus on Stages 4–7.
```

---

## Common Pitfalls

- **Endless tutorials, no projects.** Watching a 4-hour course on LangGraph without building anything leaves you unable to build anything. Every stage must end with a project.

- **Skipping the foundations.** Stage 1 is unglamorous, but the agents you build on a weak foundation will be flaky and hard to debug.

- **Jumping to multi-agent too early.** Multi-agent systems are not "better" than single-agent systems. Most problems are well-served by a single agent with good tools. Master Stage 4–5 before attempting Stage 7.

- **Ignoring production concerns.** A working agent on your laptop is not a production system. Stage 6 is what separates hobbyists from professionals. Do not skip it.

- **Pursuing the latest framework.** The frameworks change every six months. The underlying skills (Stage 1–4) do not. Invest in foundations.

- **No community.** Learning AI in isolation is slow. Find a Discord, a study group, or a co-worker pair-programming. The fastest learners have people to ask.

---

## Exercises

1. **Easy** — Identify which stage you are currently in. Write one sentence about what you would build as the project for that stage.

2. **Medium** — For each of the seven stages, identify one resource (book, course, video, doc) that you have found or would recommend. Justify each pick in one sentence.

3. **Hard** — Design a 6-month learning plan for someone in your situation (your background, your goals). Use the seven-stage roadmap as a scaffold, but adjust the timing, the projects, and the resources to fit your constraints.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| AI engineer | A data scientist who uses ChatGPT | A software engineer who builds production AI applications — typically agents, RAG systems, or fine-tuned models deployed at scale |
| Agent | Any LLM with a prompt | An autonomous system with five properties — perception, reasoning, tool use, memory, and a closed decision loop |
| Multi-agent system | A network of agents | A coordinated architecture where specialized agents (planner, researcher, writer, reviewer) collaborate, typically via shared state or A2A |
| MCP | A new API | The Model Context Protocol — a JSON-RPC standard for agent-to-tool communication that lets any agent discover and call any tool |
| A2A | A replacement for MCP | The Agent-to-Agent Protocol — a standard for inter-agent communication, focused on long-running tasks with progress streaming |
| Observability | Reading logs | Structured tracing of every LLM call, retrieval, and tool call with metrics on latency, cost, and quality — required for debugging non-deterministic systems |
| Eval harness | Running a few test cases | A systematic framework for measuring agent quality against a golden dataset, with regression testing, automated graders, and CI integration |
| Production agent | An agent that works | An agent deployed at scale with observability, safety guardrails, cost controls, and a feedback loop for continuous improvement |

---

## Further Reading

- **The full Phase 13 and 14 chapters** — the chapters in these two phases walk through Stages 2–7 in detail
- **"How to Build a Career in AI"** — a roadmap for the human side of becoming an AI engineer: https://www.mlyearning.org/
- **Andrej Karpathy's "A Recipe for Training Neural Networks"** — practical wisdom applicable to any ML/DL project: https://karpathy.github.io/2019/04/25/recipe/
- **LangChain Academy** — a free course that walks Stages 4–6 with LangGraph: https://academy.langchain.com/
- **DeepLearning.AI Short Courses** — free, focused courses on individual skills (RAG, agents, evals): https://www.deeplearning.ai/short-courses/