# N8N versus LangGraph

> Same problem, opposite philosophies — pick the canvas or the codebase, but know what you are trading.

**Type:** Learn
**Prerequisites:** What is an AI Agent?, How AI Agents Chain Tools, Memory, and Reasoning, Basic Python
**Time:** ~25 minutes

---

## The Problem

You want to build an AI agent that takes a user request, decides which tools to call, calls them, and returns a result. Two camps have emerged with very different ideas about *how* that agent should be expressed. One camp says: draw it on a canvas, connect nodes visually, ship in an afternoon. The other camp says: write it in code, make every state transition explicit, ship something you can test and version. Both approaches work. Both have fanatics. Both fail in different ways.

n8n is the leading open-source visual workflow platform. It now ships first-class AI agent nodes, supports any LLM, integrates with 400+ services, and runs as self-hosted or cloud. Teams without dedicated engineers can build production workflows in it.

LangGraph is the code-first graph framework from the LangChain team. It models agents as Python state machines — explicit nodes, explicit edges, explicit state, full type checking, full unit testing. It is the framework teams reach for when their agent has to be reliable enough to bet the business on.

The hard part is knowing which one fits your situation. Pick n8n when the workflow changes weekly, the builder is a non-engineer, or the integration surface is wide and shallow. Pick LangGraph when the workflow needs branching logic, conditional retry, persistent state across runs, and rigorous testing. This lesson gives you a decision framework so you do not pick wrong and discover it six months in.

---

## The Concept

### What n8n actually is

n8n is a node-based workflow editor. You build workflows by dragging nodes onto a canvas, configuring each node through a form, and drawing connections between them. When the workflow runs, n8n executes each node in order, passing the output of one into the input of the next.

```
   ┌───────────┐      ┌─────────────┐      ┌──────────────┐
   │  Trigger  │─────►│  AI Agent   │─────►│  Tool Call   │
   │ (Webhook) │      │  (LLM node) │      │ (HTTP/DB/etc)│
   └───────────┘      └──────┬──────┘      └──────────────┘
                             │
                             ▼
                      ┌─────────────┐
                      │   Memory    │ (window buffer, vector store)
                      └─────────────┘
                             │
                             ▼
                      ┌──────────────┐
                      │ Decision node│ (if/else/router)
                      └──────┬───────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
       ┌──────────┐   ┌──────────┐   ┌──────────┐
       │  Reply A │   │  Reply B │   │  Reply C │
       └──────────┘   └──────────┘   └──────────┘
```

The agent itself is one node. The LLM is configured inside that node. Tools, memory, and decision logic are other nodes wired into the canvas. The workflow is a JSON document — versionable in Git, deployable via CLI, inspectable as a graph.

**What n8n solves:** fast prototyping, integration breadth (400+ built-in nodes), non-engineer authorship, visual debugging, easy handoff between product and engineering.

**What n8n does not solve:** complex conditional logic expressed clearly, programmatic testing, type safety, fine-grained state management, sub-second latency-sensitive loops.

---

### What LangGraph actually is

LangGraph is a Python framework that models an agent as a directed graph where each node is a function and each edge is a transition. State is a typed object that flows through the graph; nodes read from it and write to it. Conditional edges let the model itself decide which node runs next.

```python
# LangGraph: a minimal agent with tool-calling and a retry loop

from typing import TypedDict, Annotated, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

class State(TypedDict):
    messages: Annotated[list, add_messages]

@tool
def get_weather(city: str) -> str:
    """Return the current weather for a city."""
    return f"It is 72°F and sunny in {city}."

tools = [get_weather]
llm = ChatOpenAI(model="gpt-4o").bind_tools(tools)

def call_model(state: State) -> dict:
    return {"messages": [llm.invoke(state["messages"])]}

def should_continue(state: State) -> Literal["tools", "__end__"]:
    last = state["messages"][-1]
    if last.tool_calls:
        return "tools"
    return "__end__"

graph = (
    StateGraph(State)
    .add_node("agent", call_model)
    .add_node("tools", ToolNode(tools))
    .add_edge(START, "agent")
    .add_conditional_edges("agent", should_continue, {"tools": "tools", "__end__": END})
    .add_edge("tools", "agent")
    .compile()
)

result = graph.invoke({"messages": [("user", "Weather in Tokyo?")]})
```

Every line is Python. The graph is a Python object. The state is typed. The retry loop is explicit. The whole thing is unit-testable with `pytest`. There is no canvas, no JSON serialization, no hidden runtime — just code.

**What LangGraph solves:** complex branching, explicit state, programmatic testing, long-running persistence, human-in-the-loop patterns, production observability.

**What LangGraph does not solve:** non-engineer authorship, rapid visual prototyping, integration breadth without writing glue code.

---

### The mental model difference

| Dimension | n8n | LangGraph |
|---|---|---|
| Primary author | Ops, product, citizen developer | Software engineer |
| Authoring surface | Visual canvas (web UI) | Python code (IDE) |
| State representation | Implicit, passed node-to-node | Explicit, typed object |
| Conditional logic | Visual "if" / "switch" nodes | Conditional edges, Python functions |
| Looping | Visual loop-back edges | Built-in graph cycles |
| Persistence | Built-in execution history | Checkpointers (Postgres, Redis) |
| Testing | Manual / execution replay | Unit tests with `pytest`, mocked nodes |
| Versioning | JSON export in Git | Code in Git, same as any Python service |
| Deployment | n8n instance (self-hosted or cloud) | Python service (container, serverless) |
| Latency overhead | Higher (per-node IPC) | Lower (in-process function calls) |
| Debugging | Visual execution trace, re-run nodes | Standard Python debugger + LangSmith |
| Integrations | 400+ built-in nodes | Write Python wrappers or use MCP servers |
| Best fit | Stable, wide, business workflows | Stateful, branching, mission-critical agents |

---

### Where each one shines

```
                  ┌──────────────────────────────────┐
                  │  Need to ship a working agent    │
                  │  THIS WEEK with non-engineers    │
                  └────────────────┬─────────────────┘
                                   │
                                   ▼
                              n8n
                                   │
            ┌──────────────────────┼──────────────────────────┐
            │                      │                          │
   Workflow stable,           Need unit tests,            Need sub-second
   changing rarely            type safety, CI/CD          latency, tight
            │                      │                       control over state
            ▼                      ▼                          ▼
   Stay in n8n              LangGraph                   LangGraph
   (it will run fine)       (port the JSON to Python)
```

```
                  ┌──────────────────────────────────┐
                  │  Agent has loops, retries,       │
                  │  branching, persistent state     │
                  └────────────────┬─────────────────┘
                                   │
                                   ▼
                              LangGraph
                                   │
            ┌──────────────────────┼──────────────────────────┐
            │                      │                          │
   Builder is engineer       Builder is non-engineer     Workflow is simple,
   who wants Python          who needs to ship fast       one-shot (no loops)
            │                      │                          │
            ▼                      ▼                          ▼
       LangGraph                 n8n                       Either works
                                                        (n8n is faster)
```

---

## Build It / In Depth

### Side-by-side example: An agent that answers questions using a weather API

**n8n version:** drag four nodes onto the canvas. Connect them. Configure each.

```
   [Chat Trigger] ──► [AI Agent] ──► [Tool: HTTP Request to weather API]
                          │
                          ▼
                   [Memory: Window Buffer]
                          │
                          ▼
                   [Reply to User]
```

Configuration steps in the UI:
1. Add a **Chat Trigger** node (input).
2. Add an **AI Agent** node, select OpenAI as the provider, paste the system prompt.
3. Inside the AI Agent, add a **Tool** sub-node of type **HTTP Request**, configure URL and parameters.
4. Add a **Window Buffer Memory** sub-node, set message window to 10.
5. Connect the AI Agent output back to the Chat Trigger's reply.

Time to working agent: 5–15 minutes for someone familiar with n8n.

**LangGraph version:** write 30–60 lines of Python (see the example above). Add a checkpointer if you want state to survive restarts. Run the script.

Time to working agent: 30–60 minutes for a Python developer who has not used LangGraph before.

The n8n version is faster to build and easier to hand to a non-engineer. The LangGraph version is easier to test, version, deploy, and evolve.

---

### Side-by-side example: Adding a retry loop

Suppose the weather API sometimes returns 503. You want the agent to retry up to three times before giving up.

**n8n:** add an **IF** node that checks the HTTP status code. On error, route to another **HTTP Request** node. Add a counter. After three failures, route to a "give up" node that replies with an apology.

```
   [HTTP Request] ──► [IF status == 200?]
                          │yes        │no
                          ▼           ▼
                   [Use response]   [Counter < 3?]
                                       │yes      │no
                                       ▼         ▼
                                 [Retry]    [Apology]
```

You can do this, but the canvas gets busy. Conditional branches compose multiplicatively — three retries means three more nodes and more edges.

**LangGraph:** add a counter to the state. Modify `should_continue` to check both `tool_calls` and `retry_count`. Loop back to the tool node with an incremented counter.

```python
class State(TypedDict):
    messages: Annotated[list, add_messages]
    retry_count: int

MAX_RETRIES = 3

def call_model(state: State) -> dict:
    return {"messages": [llm.invoke(state["messages"])]}

def call_tool_with_retry(state: State) -> dict:
    try:
        result = tool_node.invoke(state)
        return {"messages": result["messages"], "retry_count": 0}
    except Exception:
        return {"retry_count": state["retry_count"] + 1}

def should_continue(state: State) -> Literal["tools", "__end__"]:
    if state["retry_count"] >= MAX_RETRIES:
        return "__end__"
    last = state["messages"][-1]
    if last.tool_calls:
        return "tools"
    return "__end__"
```

The retry policy lives in one function. The state has a typed counter. You can unit-test `call_tool_with_retry` by mocking the tool to raise an exception. Doing the same in n8n requires manually triggering the error path and observing the canvas.

---

### When to migrate from n8n to LangGraph

Most teams that succeed with n8n eventually hit one of these walls:

1. **Complex branching.** A workflow with more than ~10 conditional branches becomes unreadable on a canvas.
2. **Need for unit tests.** Visual workflows cannot be tested programmatically in any standard CI sense.
3. **Latency.** n8n adds per-node overhead (typically 50–200 ms per node); a workflow with 15 nodes adds seconds.
4. **State management.** Storing complex, structured state across long-running workflows is awkward in n8n.
5. **Engineering ownership.** Once an agent is business-critical, the engineering team needs to own it — and engineers want code.

The migration path: keep n8n as the no-code prototyping tool, port the workflows to LangGraph once they stabilize and need reliability. The two can coexist — n8n for experimentation, LangGraph for production.

---

## Use It

### Tooling comparison

| Concern | n8n | LangGraph |
|---|---|---|
| Hosting | Self-hosted (Docker) or n8n Cloud | Any Python runtime (container, Lambda, Cloud Run) |
| Pricing | Self-hosted: free (Sustainable Use License). Cloud: from €20/mo | Free OSS; you pay for hosting and LLM API calls |
| Community | Large, active, lots of templates | Smaller, more technical |
| Integrations | 400+ built-in nodes | MCP servers, Python libraries, custom HTTP wrappers |
| Observability | Execution log, retry UI | LangSmith, Langfuse, OpenLLMetry |
| State persistence | Built-in (execution DB) | Checkpointers (Postgres, Redis, SQLite) |
| Human-in-the-loop | Wait node, approval node | `interrupt()` API, configurable approval gates |
| Multi-agent | Multiple AI agent nodes wired together | Sub-graphs, supervisor pattern, swarms |

### Decision cheat sheet

| If your situation looks like… | Reach for |
|---|---|
| Non-engineers need to build and modify workflows | n8n |
| Workflow changes every week by the ops team | n8n |
| Wide integration surface (20+ SaaS tools, no custom logic) | n8n |
| MVP / prototype in a hackathon | n8n or LangGraph |
| Production agent with strict SLAs | LangGraph |
| Complex branching, retries, conditional loops | LangGraph |
| Need unit tests in CI | LangGraph |
| Sub-second latency requirements | LangGraph |
| Long-running workflows (hours, days) with persistent state | LangGraph |
| Multiple engineers collaborating on the agent | LangGraph |
| Strict type safety and IDE autocomplete | LangGraph |

### Hybrid approach (common in practice)

Many production teams run both:

1. **n8n** as the integration platform for non-AI workflows (data sync, notifications, CRM updates, simple ETL).
2. **LangGraph** as the AI agent runtime for the LLM-driven core.

n8n calls into the LangGraph service over HTTP when it needs LLM reasoning. The LangGraph service calls back into n8n (or directly into the same APIs) when it needs to take action. This split keeps the no-code workflows where they shine and the AI agent where it can be engineered properly.

---

## Common Pitfalls

- **Choosing n8n because "we do not have engineers."** When the agent becomes business-critical, you will need engineers. Plan the migration path before the prototype becomes the production system.

- **Choosing LangGraph because "we want production-grade."** A team that has never shipped an agent will spend weeks on tooling and infrastructure before they ship anything. Prototype in n8n, then port.

- **Treating them as mutually exclusive.** They solve different problems. n8n is great for non-AI integrations. LangGraph is great for stateful AI reasoning. Using both is normal and often correct.

- **Building complex logic in n8n's expression language.** When you find yourself writing nested JavaScript expressions inside an n8n node, that is a signal the logic should move to a small Python service or a LangGraph subgraph.

- **Forgetting n8n's per-node overhead.** A workflow with 30 nodes adds seconds of latency. Profile before you optimize — sometimes the right fix is fewer, fatter nodes.

- **Forgetting LangGraph's steeper learning curve.** LangGraph rewards engineers who think in graphs and state machines. Teams without that background will struggle; n8n is a gentler on-ramp.

- **No observability in either.** Both platforms fail silently if you do not wire logging and tracing from day one. n8n has an execution log; LangGraph should be paired with LangSmith or Langfuse.

---

## Exercises

1. **Easy** — Pick a workflow you can describe in one sentence (e.g., "When a new customer signs up, add them to the CRM and send a welcome email"). Decide whether n8n or LangGraph is the better fit. Justify in three sentences.

2. **Medium** — Sketch the same multi-agent workflow in both n8n and LangGraph: a triage agent routes incoming tickets to one of three specialist agents (billing, technical, account), each of which has access to a different tool. Describe the trade-offs you see.

3. **Hard** — A financial services team has built a customer-facing agent in n8n. The workflow has grown to 45 nodes, handles 8,000 conversations per day, and has had three production outages in the last quarter because of logic bugs in nested conditional branches. Propose a migration plan to LangGraph that minimizes risk during the cutover. Address: what to migrate first, how to run both in parallel, how to validate parity, and how to roll back if LangGraph underperforms.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| n8n | A Zapier clone | An open-source, self-hostable workflow automation platform with first-class AI agent nodes, 400+ integrations, and a visual canvas; well-suited to non-engineer authors |
| LangGraph | LangChain with extra steps | A Python framework that models agents as typed state machines with explicit nodes, edges, and conditional transitions; gives engineers full control over state and loop semantics |
| Visual workflow | Easier than code | Different from code, not easier — it shifts complexity from logic to graph layout, and large workflows become hard to read on a canvas |
| State | Whatever the workflow remembers | In LangGraph, a typed object that flows through every node; in n8n, an implicit per-execution JSON document with limited typing |
| Checkpointer | A database for state | In LangGraph, a pluggable backend (Postgres, Redis, SQLite) that persists state across turns and restarts, enabling time-travel debugging and resumable workflows |
| Tool node | The way an agent calls an API | In n8n, a pre-built node wrapping a specific service; in LangGraph, a Python function decorated with `@tool` or any callable that returns a structured response |
| Conditional edge | An if statement | In LangGraph, a function that inspects the current state and returns the name of the next node to execute; supports cycles, not just branching |
| Human-in-the-loop | Asking the user a question | A first-class pattern in both frameworks — the workflow pauses at a defined point, surfaces its current state to a human, and resumes after approval; LangGraph's `interrupt()` API makes this explicit; n8n's Wait and Approval nodes do the same visually |

---

## Further Reading

- **n8n AI Agent Documentation** — the official guide to building AI agents in n8n with tool calling, memory, and chat triggers: https://docs.n8n.io/advanced-ai/
- **LangGraph Quickstart** — the canonical intro to graph-based agent orchestration, with the state machine mental model: https://langchain-ai.github.io/langgraph/tutorials/introduction/
- **"Building LangGraph Agents with LangChain"** — practical patterns for tool use, persistence, and human-in-the-loop: https://blog.langchain.dev/langgraph/
- **n8n vs LangChain Comparison** — a third-party breakdown of when each tool fits, including cost and operational considerations: https://n8n.io/vs/langchain/
- **LangGraph Studio** — the visual debugger for LangGraph graphs, useful for engineers who want a canvas view of their code: https://langchain-ai.github.io/langgraph/concepts/langgraph_studio/