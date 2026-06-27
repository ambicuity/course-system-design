# MCP Versus A2A Protocol

> Two protocols solving two different problems — agents talking to tools, and agents talking to agents. Combine them, do not confuse them.

**Type:** Learn
**Prerequisites:** What is MCP?, What is an AI Agent?, Multi-agent systems basics
**Time:** ~20 minutes

---

## The Problem

Two new protocols have entered the AI infrastructure vocabulary in the last two years, and the conversation around them is full of confusion. MCP (Model Context Protocol) connects an agent to *external tools*. A2A (Agent-to-Agent Protocol, from Google) connects *agents to each other*. They look similar — both are JSON-based, both have agents and servers, both talk about "messages." But they solve different problems, in different layers of the stack.

When teams start designing agent architectures, they reach for one of two extremes: "everything is MCP" or "everything is A2A." Both are wrong. The right mental model is: MCP is the agent's interface to the world; A2A is the interface between agents. You almost always need both — agents that use tools (MCP) and agents that collaborate with other agents (A2A).

This lesson explains what A2A actually is, how it differs from MCP, when each applies, and how to design a system that uses both without conflating them.

---

## The Concept

### Two protocols, two relationships

```
   MCP: Agent ──────► Tool (via MCP server)
   A2A: Agent ──────► Agent (via A2A)

   MCP answers: "How does my agent reach the world?"
   A2A answers: "How do my agents reach each other?"
```

```
                  ┌─────────────────────────────────────────────┐
                  │            MCP WORLD                         │
                  │                                             │
                  │   Agent ──MCP──► Tool A                     │
                  │   Agent ──MCP──► Tool B                     │
                  │   Agent ──MCP──► Tool C                     │
                  │                                             │
                  │   Each agent independently talks to tools.  │
                  └─────────────────────────────────────────────┘

                  ┌─────────────────────────────────────────────┐
                  │            A2A WORLD                         │
                  │                                             │
                  │   Agent 1 ──A2A──► Agent 2                  │
                  │   Agent 2 ──A2A──► Agent 3                  │
                  │   Agent 1 ──A2A──► Agent 3                  │
                  │                                             │
                  │   Agents collaborate, delegate, and share    │
                  │   results through peer-to-peer messages.    │
                  └─────────────────────────────────────────────┘
```

The split is the same as microservices: service-to-database (MCP) vs service-to-service (A2A). The protocols serve different relationships.

---

### What MCP is, in this context

MCP is the **standardized interface between an agent and its tools**. The agent speaks MCP to discover what tools are available (via `tools/list`) and to invoke them (via `tools/call`). The tool side speaks MCP to advertise its capabilities and respond to calls. The agent is the client; the tool is the server.

Key properties of MCP:

- **One agent, many tools.** A single agent connects to multiple MCP servers.
- **Tool-as-server.** Each tool (or group of tools) is a server.
- **Self-describing.** The tool publishes its capabilities; the agent discovers them.
- **Stateless requests.** Each tool call is independent; no implicit session.

---

### What A2A is, in this context

A2A is the **standardized interface between agents**. Agent A wants to delegate a subtask to Agent B; both speak A2A. The protocol defines how agents discover each other's capabilities, how they send tasks, how they stream progress, and how they return results.

Key properties of A2A:

- **Many agents, peer-to-peer.** Any agent can talk to any other agent.
- **Agent-as-server.** Each agent publishes an "Agent Card" describing its capabilities.
- **Task-based.** One agent sends another a task; the second agent works on it and returns the result (or streams progress).
- **Long-running.** A2A is designed for tasks that may take seconds, minutes, or hours.

---

### Side-by-side comparison

| Dimension | MCP | A2A |
|---|---|---|
| Relationship | Agent ↔ Tool | Agent ↔ Agent |
| Server side | A function, API, or system | Another agent |
| Discovery | `tools/list` — server publishes tools | Agent Card — agent publishes capabilities |
| Invocation | `tools/call` — one-shot request | `tasks/send` — long-running task with progress |
| State | Stateless per call | Stateful, multi-turn, streaming |
| Use case | "Send an email" | "Research this topic and report back" |
| Initiator | The agent decides what tool to call | The agent decides what other agent to delegate to |
| Standardized by | Anthropic + community | Google + community |

---

### How the two combine

A production multi-agent system uses both:

```
   ┌─────────────────────────────────────────────────────────────┐
   │                                                             │
   │   User ──► Orchestrator Agent                               │
   │                  │                                         │
   │                  │ A2A                                     │
   │                  │                                         │
   │       ┌──────────┼──────────┐                              │
   │       ▼          ▼          ▼                              │
   │   Researcher   Writer    Reviewer                           │
   │   Agent        Agent     Agent                              │
   │       │          │          │                               │
   │       │ MCP      │ MCP      │ MCP                           │
   │       │          │          │                               │
   │       ▼          ▼          ▼                               │
   │   ┌──────┐   ┌──────┐   ┌──────┐                           │
   │   │Web   │   │Google│   │GitHub│                           │
   │   │Search│   │Drive │   │ MCP  │                           │
   │   │ MCP  │   │ MCP  │   │Server│                           │
   │   └──────┘   └──────┘   └──────┘                           │
   │                                                             │
   └─────────────────────────────────────────────────────────────┘
```

The orchestrator delegates sub-tasks to specialized agents via A2A. Each specialized agent uses MCP to reach the tools it needs to do its work. The two protocols operate at different layers and serve different purposes.

---

### What A2A actually does

When one agent wants another agent to do something, it goes through five steps:

```
   ┌─────────────────────────────────────────────────────────────┐
   │                                                             │
   │  1. Discovery                                               │
   │     Agent A reads Agent B's "Agent Card" — a JSON           │
   │     manifest describing B's capabilities, inputs,           │
   │     outputs, and authentication requirements.              │
   │                                                             │
   │  2. Task submission                                         │
   │     A sends B a task via `tasks/send` with structured       │
   │     input (text, files, structured data).                   │
   │                                                             │
   │  3. Execution                                               │
   │     B works on the task. May take seconds to hours.         │
   │     Optionally streams progress updates.                    │
   │                                                             │
   │  4. Result return                                           │
   │     B returns a structured result (text, files, JSON)      │
   │     via the task handle.                                    │
   │                                                             │
   │  5. Status / history                                        │
   │     Either side can query the task's status, history,       │
   │     and artifacts via the task handle.                      │
   │                                                             │
   └─────────────────────────────────────────────────────────────┘
```

The task handle is the key abstraction. Unlike MCP's stateless calls, an A2A task is a long-lived object that can be queried, streamed, canceled, and reattached to.

---

### What A2A is not

Clearing up the most common confusions:

- ❌ **A2A is not a replacement for MCP.** They solve different problems. A2A cannot give an agent access to a database; MCP cannot let one agent delegate work to another.
- ❌ **A2A is not a chat protocol.** It is task-oriented. The unit of work is a task, not a message exchange.
- ❌ **A2A requires a shared runtime.** The two agents need to be discoverable to each other (via Agent Cards or a registry). Pure local agents cannot A2A.
- ❌ **A2A is the only way to do multi-agent.** You can build multi-agent systems entirely within LangGraph, AutoGen, or CrewAI without A2A. A2A is for *cross-runtime* agent communication.

---

## Build It / In Depth

### A concrete example

Scenario: A user asks the orchestrator agent to research a topic and produce a report.

**Without A2A (single agent does everything):**

```python
agent = Agent(
    model="claude-sonnet-4-5",
    tools=[web_search, scrape_url, write_file],
    system_prompt="Research the topic and write a report.",
)

# One agent, 50+ tool calls, very long context.
result = agent.run("Research quantum computing and write a report.")
```

**With A2A (orchestrator delegates to specialists):**

```python
orchestrator = Agent(
    model="claude-sonnet-4-5",
    system_prompt="""Delegate to specialists via A2A.
    Use the Researcher for fact-finding.
    Use the Writer for drafting.
    Use the Reviewer for quality checks.""",
)

# Orchestrator delegates via A2A:
#   A2A → Researcher (fact-find) → returns notes
#   A2A → Writer (draft report) → returns draft
#   A2A → Reviewer (quality check) → returns feedback
# Orchestrator assembles the final report.

result = orchestrator.run("Research quantum computing and write a report.")
```

The orchestrator's context stays small (it only sees summaries). The Researcher uses MCP to reach web search and scraping tools. The Writer uses MCP to reach Google Docs. The Reviewer uses MCP to reach internal style guides.

---

### When to use A2A, when to use MCP, when to use both

| Situation | Use |
|---|---|
| Agent needs to call a tool | MCP |
| Agent needs to delegate a sub-task to another agent | A2A |
| Multi-agent system where each agent uses tools | Both |
| Single agent with many tools | MCP only |
| Cross-organization agent collaboration | A2A |
| Real-time, low-latency tool call | MCP (faster, simpler) |
| Long-running research task | A2A (supports streaming, status, retries) |

---

### A note on maturity

As of mid-2025:

- **MCP** has broader ecosystem support (hundreds of servers, multiple SDKs, official support from Anthropic, OpenAI, and others).
- **A2A** is newer (announced by Google in April 2025), with growing but smaller ecosystem. Implementations exist for Python and TypeScript; Agent Card conventions are still evolving.

For production work today, MCP is the safer default for tool integration. A2A is worth piloting for multi-agent orchestration, especially when the agents are owned by different teams or runtimes.

---

## Use It

### Common patterns

**Pattern 1: Single-agent system with MCP tools.**
```
   Agent ──MCP──► Multiple tool servers
```
Use when: one agent can hold the full task in its head.

**Pattern 2: Multi-agent system with internal coordination (no A2A).**
```
   Agents within a single runtime coordinate via shared state (LangGraph, AutoGen, CrewAI).
```
Use when: all agents are owned by the same team and run in the same process.

**Pattern 3: Multi-agent system with A2A.**
```
   Agents in different runtimes collaborate via A2A.
```
Use when: agents are owned by different teams, run in different processes, or need to cross organizational boundaries.

**Pattern 4: Multi-agent system with MCP + A2A.**
```
   Orchestrator (A2A) → Specialists (A2A) → Tools (MCP)
```
Use when: you want specialization, modularity, and tool reuse.

---

### When MCP is enough

- Your agent is the only "smart" component.
- All the tools are stateless APIs.
- No long-running delegation.
- Single team owns the whole stack.

If all four are true, you do not need A2A.

### When A2A earns its place

- Multiple specialized agents with different capabilities.
- Agents owned by different teams or organizations.
- Tasks that take minutes or hours, not milliseconds.
- You need observability and audit trails across agent boundaries.
- You want to swap one agent for another without rewriting the orchestrator.

---

## Common Pitfalls

- **Conflating MCP and A2A.** They are different protocols for different relationships. Calling one "MCP" when it is A2A, or vice versa, makes architecture discussions impossible.

- **A2A for everything.** A2A adds discovery, task tracking, and message overhead. For tightly-coupled agents in the same process, shared state (LangGraph) is simpler and faster.

- **MCP for inter-agent communication.** A tool is not an agent. If you find yourself wanting to send stateful, multi-turn messages through MCP, you want A2A.

- **No Agent Card.** Without a discoverable description of what each agent does, the orchestrator cannot reason about delegation. Standardize Agent Cards as the contract.

- **No error handling.** A2A tasks can fail (timeout, dependency missing, agent crashed). The orchestrator must handle task failures, retries, and escalations.

- **Authentication gaps.** MCP authenticates the agent to the tool. A2A authenticates the calling agent to the called agent. Different credentials, different scopes, different revocation paths.

- **Skipping observability.** Without tracing across A2A boundaries, you cannot debug why a multi-agent workflow failed. Wire OpenTelemetry or equivalent.

---

## Exercises

1. **Easy** — In one sentence each, describe what MCP and A2A are, what relationship each serves, and how they differ.

2. **Medium** — Take a real task (e.g., "research a topic and produce a report"). Sketch the architecture twice: once using only MCP (one agent with all the tools) and once using both MCP and A2A (orchestrator delegating to specialists). Compare the architectures.

3. **Hard** — Your company has three internal teams, each building its own AI agent: a sales agent, a support agent, and a finance agent. Each currently uses MCP to reach its own tools. The CTO wants them to collaborate — the sales agent should be able to ask the support agent for ticket history, the support agent should be able to ask the finance agent for invoice status. Design the A2A layer: what Agent Cards look like, how authentication works, how the agents discover each other, and how you handle the case where one agent is down.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| MCP | The only AI protocol | A protocol for agent-to-tool communication; standardizes how agents discover and call external functions and resources |
| A2A | A replacement for MCP | A protocol for agent-to-agent communication; standardizes how agents delegate tasks, stream progress, and return results |
| Agent Card | A business card | A JSON manifest describing an agent's capabilities, inputs, outputs, and authentication; how other agents decide whether to delegate to it |
| Task | A tool call | A long-running unit of work in A2A; has a handle, status, history, and optional streaming; fundamentally different from a stateless MCP tool call |
| Multi-agent system | A network of agents | A coordinated architecture where specialized agents (planner, researcher, writer, reviewer) collaborate; coordination can be via shared state (in-process) or A2A (cross-process) |
| Tool | An agent | A function, API, or system exposed to an agent via MCP; does not reason, plan, or iterate — responds to structured requests |
| Orchestrator | The main agent | The agent in a multi-agent system that decides which specialist to delegate to, sequences the work, and assembles the final result |
| Discovery | Listing available tools | In MCP, `tools/list` returns the catalog of tools; in A2A, fetching an Agent Card returns the catalog of capabilities — the same idea, different layers |

---

## Further Reading

- **Model Context Protocol Specification** — the canonical docs for MCP: https://modelcontextprotocol.io
- **Google A2A Project Page** — the announcement and specification for the Agent-to-Agent Protocol: https://google.github.io/A2A/
- **"Building Effective Agents"** — Anthropic's research on when agents add value and how to compose them: https://www.anthropic.com/research/building-effective-agents
- **LangGraph Multi-Agent Patterns** — the canonical reference for in-process multi-agent coordination: https://langchain-ai.github.io/langgraph/concepts/multi_agent/
- **Awesome MCP Servers** — community-maintained list of MCP servers to use with your A2A agents: https://github.com/punkpeye/awesome-mcp-servers