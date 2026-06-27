# AI Agent versus MCP

> The agent decides what to do. MCP is how it gets to do it. Conflating them is the most common mistake in modern AI architecture.

**Type:** Learn
**Prerequisites:** What is an AI Agent?, What is MCP?, How AI Agents Chain Tools, Memory, and Reasoning
**Time:** ~20 minutes

---

## The Problem

Two terms have entered the AI vocabulary in the last two years, and they are constantly used interchangeably by people who should know better. *AI agent* and *Model Context Protocol* (MCP) appear in the same sentences, the same diagrams, the same architecture reviews. They are not the same thing. They are not even the same *category* of thing. One is a system. The other is a protocol. Conflating them produces architectures that are confused at best and broken at worst.

An AI agent is the *thing that acts*. It reasons, plans, decides, calls tools, observes results, iterates. It is the actor in the system. MCP is the *way the actor talks to its tools*. It is the protocol that lets the agent discover what tools are available, understand what each tool does, and invoke them with structured arguments. The agent is the chef; MCP is the language the chef uses to talk to the kitchen.

This distinction matters because every architectural decision follows from it. You do not "build an MCP" — you build an agent. You do not "deploy an agent" over MCP alone — you deploy an agent that *uses* MCP to reach its tools. This lesson sharpens the distinction, shows how the two work together, and helps you talk about them precisely.

---

## The Concept

### What an AI agent actually is

An AI agent is a software system that can perceive its environment, reason about goals, choose actions, and execute them — autonomously or semi-autonomously — to achieve an objective. It has three defining properties:

```
   ┌─────────────────────────────────────────────────────────────┐
   │                       AI AGENT                               │
   │                                                             │
   │   1. Goal-oriented                                         │
   │      "Find the user's last invoice and email it."          │
   │                                                             │
   │   2. Autonomous (within bounds)                            │
   │      Decides which steps to take, in what order,            │
   │      when to ask for help, when to stop.                   │
   │                                                             │
   │   3. Stateful / iterative                                  │
   │      Remembers what it has tried, observes what worked,    │
   │      adapts the plan as new information arrives.           │
   │                                                             │
   │   Components:                                               │
   │   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
   │   │ Reasoning│  │  Memory  │  │ Planning │  │ Tool-use │    │
   │   │ (LLM)    │  │          │  │          │  │ executor │    │
   │   └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
   └─────────────────────────────────────────────────────────────┘
```

The agent is a *runtime*. It contains the orchestration logic, the model, the memory, the state, and the loop that calls the model, decides what to do, calls tools, observes results, and repeats. The agent is what your application code creates and runs:

```python
# You build an agent
agent = Agent(
    model="claude-sonnet-4-5",
    tools=[...],
    memory=...,
    system_prompt="..."
)

# You give it a task
result = agent.run("Find my last invoice and email it to alex@acme.com")
```

The agent might take five steps, call three tools, retrieve some memory, decide to ask a clarifying question, or decide it is done. That whole loop is the agent.

---

### What MCP actually is

MCP is a *protocol*. It is a standardized way for an agent (or any client) to discover and invoke tools, fetch resources, and use pre-built prompt templates exposed by *servers*. It is JSON-RPC over a transport (stdio, HTTP, Server-Sent Events). It defines a small set of methods and message shapes.

```
   ┌─────────────────────────────────────────────────────────────┐
   │                       MCP (Protocol)                        │
   │                                                             │
   │   Wire format:    JSON-RPC 2.0                              │
   │   Transports:     stdio, HTTP+SSE, streamable HTTP          │
   │   Methods:        initialize, tools/list, tools/call,       │
   │                   resources/list, resources/read,            │
   │                   prompts/list, prompts/get                  │
   │   Server types:   tool servers, resource servers,            │
   │                   prompt servers, composite servers          │
   │                                                             │
   │   MCP defines HOW a client talks to a server.               │
   │   MCP does NOT decide what to do.                           │
   │   MCP does NOT contain reasoning, memory, or planning.      │
   └─────────────────────────────────────────────────────────────┘
```

MCP is to AI tooling what HTTP is to the web. It is a contract — a set of message shapes and behaviors — that any client and any server can implement. Like HTTP, it does not contain logic; it transports messages.

---

### How they relate

The relationship is *agent uses MCP to reach tools*. MCP is the integration layer between the agent runtime and the outside world.

```
   ┌─────────────────────────────────────────────────────────────┐
   │                       AI AGENT                               │
   │                                                             │
   │   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
   │   │ Reasoning│  │  Memory  │  │ Planning │  │ Tool-use │    │
   │   │ (LLM)    │  │          │  │          │  │ executor │    │
   │   └──────────┘  └──────────┘  └──────────┘  └─────┬────┘    │
   │                                                  │          │
   └──────────────────────────────────────────────────┼──────────┘
                                                      │ speaks MCP
                                                      ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                       MCP SERVERS                            │
   │                                                             │
   │   ┌────────────┐  ┌────────────┐  ┌────────────┐             │
   │   │  GitHub    │  │   Slack    │  │  Postgres  │   ...       │
   │   │  MCP Server│  │ MCP Server │  │ MCP Server │             │
   │   └────────────┘  └────────────┘  └────────────┘             │
   │                                                             │
   │   Each server exposes its capabilities via MCP:              │
   │   - tools (functions the model can call)                    │
   │   - resources (read-only data the model can fetch)          │
   │   - prompts (pre-built prompt templates)                    │
   └─────────────────────────────────────────────────────────────┘
```

The agent contains the *decision-making*. The MCP layer contains the *messaging format*. Without MCP, the agent would still decide to call a tool — it would just do so over a custom JSON schema. Without the agent, MCP is just a protocol waiting for a client.

---

### What each one solves

| Concern | Solved by the agent | Solved by MCP |
|---|---|---|
| Deciding *what* to do | ✅ | ❌ |
| Planning multi-step workflows | ✅ | ❌ |
| Storing short-term and long-term memory | ✅ | ❌ |
| Iterating after observing tool results | ✅ | ❌ |
| Choosing when to stop or ask for help | ✅ | ❌ |
| Discovering what tools exist | ❌ (or partly) | ✅ |
| Standardizing tool argument schemas | ❌ (or partly) | ✅ |
| Transporting tool calls across processes | ❌ | ✅ |
| Interoperability across model providers | ❌ | ✅ |
| Reusing one integration across many agents | ❌ | ✅ |

The left column is the agent's job. The right column is MCP's job. Both are necessary for a production AI system; neither covers the other.

---

### A common mental model: agent vs. kitchen

Think of a restaurant kitchen.

- **The agent** is the chef. The chef decides what to cook, in what order, with what ingredients. The chef has memory (recipes they have learned), planning (the sequence of steps), reasoning (substituting ingredients when something is missing), and tools (knives, pans, ovens).

- **MCP** is the language spoken between the chef and the kitchen equipment. It is the standardized interface the chef uses to say "turn on the oven to 350°F" or "set a timer for 20 minutes" — regardless of which brand of oven or timer is installed.

- **MCP servers** are the appliances. The oven speaks MCP (the protocol), exposes tools (`set_temperature`, `set_timer`), and the chef can use any brand of oven as long as it speaks MCP.

- **The underlying systems** (the gas line, the electricity, the building) are the actual APIs and infrastructure — completely invisible to the chef, but essential.

In this analogy, asking "should I use an agent or MCP?" is like asking "should I hire a chef or buy an oven?" Both. They solve different problems.

---

### What MCP servers are NOT

A subtle but important point: an MCP server is not an agent. It does not reason, plan, or make decisions. It exposes capabilities to a client.

```
   ❌  "An MCP server that monitors my codebase and fixes bugs autonomously"
       → That is an AGENT. It uses MCP servers (filesystem, git, code exec) as tools.

   ❌  "An MCP that chats with users about their problems"
       → That is an AGENT. It might use an MCP server (e.g., a CRM lookup) as one of its tools.

   ✅  "An MCP server that exposes my Postgres database as read-only SQL queries"
       → That is what MCP is for: a thin, well-defined interface to a specific resource.
```

If your system is making decisions, looping on results, or pursuing goals, it is an agent. If it is responding to structured requests and returning structured responses, it might be an MCP server.

---

## Build It / In Depth

### Anatomy of an agent that uses MCP

Here is what a concrete agent + MCP integration looks like at the code level.

```python
# The agent: a LangGraph agent with MCP tool access

from langgraph.prebuilt import create_react_agent
from langchain_mcp_adapters import load_mcp_tools
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import asyncio

async def build_agent():
    # 1. Spin up an MCP server (filesystem in this case)
    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp/docs"],
    )

    # 2. Open a client session to that server
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 3. Load the MCP server's tools into the agent
            tools = await load_mcp_tools(session)

            # 4. Build the agent with those tools
            agent = create_react_agent(
                model="anthropic:claude-sonnet-4-5",
                tools=tools,
            )

            # 5. Run it
            result = await agent.ainvoke({
                "messages": [("user", "List the .md files in /tmp/docs")]
            })
            return result

asyncio.run(build_agent())
```

Walking through the layers:

- **Lines 1–6:** launch an MCP server (`server-filesystem`) as a child process.
- **Lines 7–10:** open an MCP client session — this speaks MCP, the JSON-RPC protocol.
- **Lines 11–14:** call `load_mcp_tools`, which internally calls `tools/list` (MCP method) and converts the result into tool objects the agent understands.
- **Lines 15–19:** build the agent. The agent runtime contains the reasoning loop. It does not know what MCP is; it just sees a list of tools.
- **Lines 20–22:** run the agent. When the model decides to call a tool, the agent runtime dispatches the call *back through the MCP client* to the MCP server.

The agent runtime never sees MCP. MCP is invisible plumbing between the agent's tool executor and the actual servers. That is the clean separation.

---

### When MCP is optional

MCP is not the only way for an agent to use tools. Three common patterns:

```
   Pattern 1: Direct function calling
   ┌─────────────┐
   │   Agent     │
   │  (LangGraph)│
   └──────┬──────┘
          │ calls Python function directly (in-process)
          ▼
   ┌─────────────┐
   │ search_docs │
   │ (function)  │
   └─────────────┘
   Pros: lowest latency, simplest debugging
   Cons: tightly coupled, no cross-agent reuse


   Pattern 2: MCP
   ┌─────────────┐
   │   Agent     │
   └──────┬──────┘
          │ MCP protocol (JSON-RPC)
          ▼
   ┌─────────────┐
   │ MCP Server  │
   └──────┬──────┘
          │ HTTP / SQL / etc.
          ▼
   ┌─────────────┐
   │ Underlying  │
   │  system     │
   └─────────────┘
   Pros: standardized, reusable across agents, self-describing
   Cons: per-call overhead, more moving parts


   Pattern 3: Traditional API + custom glue
   ┌─────────────┐
   │   Agent     │
   └──────┬──────┘
          │ custom tool wrapper
          ▼
   ┌─────────────┐
   │  REST API   │
   └─────────────┘
   Pros: full control, no protocol overhead
   Cons: you write the glue code per agent per API
```

Use direct function calling for tools that are tightly coupled to your agent and never need to be reused. Use MCP when you want one integration reused across many agents, or when you are integrating with third-party tools that already ship MCP servers.

---

### Decision procedure: agent + MCP vs. agent + custom tools

```
   Will more than one agent or model runtime
   need access to this tool?
                │
        YES ────┴──── NO
         │                │
         ▼                ▼
      MCP             Direct function calling
      (one server,     (simpler, lower latency)
       many agents)

   Is there already a community MCP server
   for this tool (GitHub, Slack, Postgres, etc.)?
                │
        YES ────┴──── NO
         │                │
         ▼                ▼
      Use it            Build an MCP server only if
      directly          the tool will be reused; otherwise
                        wrap it as a direct function
```

---

## Use It

### Who provides what

| Layer | Provided by |
|---|---|
| Agent runtime / orchestration | LangGraph, CrewAI, AutoGen, smolagents, custom code |
| Reasoning model | OpenAI, Anthropic, Google, Meta (Llama), Mistral, DeepSeek |
| MCP protocol | Anthropic (initial design), open-source community (evolution) |
| MCP servers | Anthropic (reference servers), community (e.g., `@modelcontextprotocol/server-*`), your own engineering team |
| Underlying systems being wrapped | Your existing APIs, databases, file systems, SaaS tools |

If you are building the agent, you choose the runtime (LangGraph, etc.) and the model (Claude, GPT-4o, etc.). If you are exposing a tool, you write an MCP server (15–200 lines of code). If you are using a tool, you connect to its MCP server.

---

### When the distinction matters in practice

| If you are… | You are building… | MCP is… |
|---|---|---|
| Designing the agent's reasoning loop | The **agent** | Irrelevant; pick any tool-calling mechanism |
| Wrapping an internal database for agents to query | An **MCP server** | Required if you want it discoverable and standardized |
| Integrating with GitHub in your agent | A **tool integration** | Optional — use the existing GitHub MCP server, or call the API directly |
| Building a multi-agent system | A **multi-agent runtime** | Useful for inter-agent tool sharing |
| Debugging why a tool call failed | Debugging the **agent's decision** *or* the **MCP server's response** | Know which layer failed before you start fixing |

---

### Common phrases that reveal confusion

- ❌ *"We deployed an MCP for our customer support."* — You deployed an **agent**. MCP is the protocol it might use.
- ❌ *"Our MCP thinks the user wants to escalate."* — Your **agent** thinks that. MCP servers do not think.
- ✅ *"Our agent uses an MCP server to query the CRM."* — Correct: the agent (decision-maker) reaches the CRM (system) via MCP (protocol).
- ✅ *"We built an MCP server that exposes our analytics API."* — Correct: a tool integration exposed via the MCP standard.

---

## Common Pitfalls

- **Calling an agent an "MCP."** An agent is a runtime. MCP is a protocol. Use the right words in design reviews; the confusion leads to architectural misunderstandings.

- **Calling an MCP server an "agent."** A server exposes tools and resources. It does not reason, plan, or iterate. If your server is making decisions, it is probably an agent in disguise.

- **Assuming MCP is required for agent tool use.** An agent can call any function directly. MCP is one standardized way to do it across many tools and many agents. Direct function calling is simpler when scope is limited.

- **Trying to reason inside the MCP server.** The server's job is to expose capabilities and respond to structured requests. Put reasoning in the agent. Putting it in the server breaks the clean separation and creates tools that are harder to compose.

- **Using MCP where a simple API call suffices.** If your agent needs to call one internal service and no other agent will ever need it, a thin function wrapper is faster to build and easier to debug than an MCP server.

- **Forgetting that MCP is just transport.** MCP does not authenticate, authorize, rate-limit, audit, or monitor by itself. Those are responsibilities of the agent runtime or the underlying systems.

- **Mixing layers in one diagram.** A diagram that conflates "agent" with "MCP server" makes it impossible to discuss failure modes, because failures live in different layers. Keep the layers separate.

---

## Exercises

1. **Easy** — In one sentence each, define "AI agent" and "MCP" so a non-technical stakeholder could tell them apart.

2. **Medium** — Sketch a concrete architecture for a customer support agent that uses an MCP server wrapping a CRM. Label every box with which category it falls into: agent runtime, model, MCP server, MCP protocol, or underlying system. Identify what would happen if (a) the model hallucinates a tool call, (b) the MCP server returns malformed JSON, (c) the underlying CRM is down.

3. **Hard** — Your company has built three agents over the past year: a sales agent (uses HubSpot + email), a support agent (uses Zendesk + Slack), and an analytics agent (uses Snowflake + an internal metrics API). Each agent has its own custom tool wrappers. Propose a migration plan to consolidate around MCP: which existing wrappers become MCP servers, what new capabilities unlock, what the rollout phases look like, and what could go wrong.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| AI agent | Any LLM that calls a tool | A runtime that contains reasoning, planning, memory, and a tool-execution loop; the actor that decides *what* to do and *when* to stop |
| MCP | A new kind of agent | A JSON-RPC protocol that standardizes how a client (often an agent) discovers and calls tools and resources exposed by servers; transport, not intelligence |
| Agent runtime | The same as the model | The orchestration code that owns the loop, the state, the memory, and the tool executor — usually LangGraph, CrewAI, AutoGen, or custom; the model is just one component inside it |
| MCP server | An agent that lives near the data | A process that exposes tools, resources, and prompts over MCP; it does not reason or act, it responds to structured requests from clients |
| Tool | A function the agent calls | The unit of capability the agent can invoke — whether exposed via direct function calling, MCP, or a REST API; the choice of mechanism is independent of what the tool does |
| Protocol | Just plumbing | A defined set of message shapes and behaviors that clients and servers agree on; MCP is plumbing for tool calls, the same way HTTP is plumbing for documents |
| Discovery | An API has docs; MCP has it built-in | MCP servers return their capability catalog (`tools/list`, `resources/list`) on demand; agents adapt to changes without code updates or external documentation lookups |
| Layers | One big thing | A production agentic system has at least three layers — the agent runtime (decides), the protocol (transports), and the underlying systems (provide the actual capability); each layer fails differently and needs its own observability |

---

## Further Reading

- **What is an AI Agent?** — the prerequisite lesson on agent architecture, reasoning loops, and tool use: see chapter 07 in this phase
- **What is MCP?** — the prerequisite lesson on the Model Context Protocol, its primitives, and its transports: see chapter 14 in this phase
- **Model Context Protocol Specification** — the canonical protocol documentation: https://modelcontextprotocol.io
- **LangGraph + MCP Integration Guide** — the official pattern for using MCP servers inside LangGraph agents: https://langchain-ai.github.io/langgraph/concepts/mcp/
- **"Agents vs. Protocols: A Mental Model"** — a practitioner's breakdown of where the boundary lies and why conflating them causes architectural problems: https://www.latent.space