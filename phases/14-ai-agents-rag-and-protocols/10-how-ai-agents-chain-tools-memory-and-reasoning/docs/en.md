# How AI Agents Chain Tools, Memory, and Reasoning

> The agent loop in three moves: think, act, remember. Repeat until done.

**Type:** Learn
**Prerequisites:** What is an AI Agent?, ReAct pattern, Function Calling
**Time:** ~20 minutes

---

## The Problem

You have a language model. You have a set of tools. You have a user with a goal. How does the model actually go from "the user said X" to "the user got Y, via four tool calls and a memory update"? The mechanics matter. The exact sequence — what triggers what, when memory is read or written, when the loop terminates — is what separates a working agent from a broken one.

The popular mental model is "the agent is a brain that calls tools." That is true but incomplete. The brain does not just call tools; it interleaves three operations in a tight loop:

1. **Reasoning** — what should I do next, given everything I know?
2. **Tool use** — actually doing it.
3. **Memory** — recording what happened so the next iteration has the context it needs.

Get the loop wrong and you get agents that loop forever, agents that forget the goal, agents that call tools but ignore the results. Get the loop right and the agent becomes a system that handles novel tasks reliably.

---

## The Concept

### The three-component loop

```
            ┌──────────────────────────────────────────────┐
            │                                              │
            ▼                                              │
   ┌────────────────┐         ┌─────────────────┐          │
   │   REASONING    │◄────────│     MEMORY      │          │
   │                │  read   │                 │          │
   │  (LLM call)    │         │  - conversation │          │
   │                │         │  - past runs    │          │
   │  Input:        │         │  - user facts   │          │
   │  - system      │         │                 │          │
   │  - memory      │         └────────▲────────┘          │
   │  - tools       │                  │                   │
   │                │                  │ write             │
   │  Output:       │                  │                   │
   │  - text OR     │                  │                   │
   │  - tool call   │                  │                   │
   └────────┬───────┘                   │                   │
            │                           │                   │
            ▼                           │                   │
   ┌────────────────┐                   │                   │
   │   TOOL USE     │                   │                   │
   │                │                   │                   │
   │  - validate    │                   │                   │
   │  - authorize   │                   │                   │
   │  - execute     │───────────────────┘                   │
   │  - format      │  (result goes to memory)              │
   └────────────────┘                                       │
                                                             │
   Loop continues until reasoning produces text              │
   instead of a tool call.                                   │
   └─────────────────────────────────────────────────────────┘
```

Each turn of the loop, exactly one of two things happens:

- **Reasoning produces a tool call** → execute it → record the result in memory → loop again.
- **Reasoning produces text** → that's the answer → exit.

The loop is bounded by `max_iterations` (5–20 typical) to prevent infinite loops and runaway costs.

---

### Component 1: Reasoning

Reasoning is the LLM call. It receives everything the agent knows right now and produces either a structured tool call or a final text response.

**What the reasoning step sees:**

```
   ┌──────────────────────────────────────────────────────────┐
   │ Reasoning input                                           │
   │                                                          │
   │  1. System prompt                                         │
   │     "You are a customer support agent for Acme Corp.     │
   │      Be terse. Cite the source for any factual claim.    │
   │      Never make promises about refunds."                 │
   │                                                          │
   │  2. Long-term memory (retrieved by similarity)            │
   │     - past interaction summary                           │
   │     - relevant user facts                                │
   │     - similar resolved tickets                           │
   │                                                          │
   │  3. Conversation history (short-term memory)              │
   │     - user's current message                             │
   │     - previous turns in this conversation                │
   │     - tool calls and their results                       │
   │                                                          │
   │  4. Tool catalog                                          │
   │     - search_docs(query) → list of matching documents    │
   │     - open_ticket(title, body) → ticket_id               │
   │     - send_email(to, subject, body) → success/error      │
   │                                                          │
   │  Output: structured tool call OR final text response     │
   └──────────────────────────────────────────────────────────┘
```

The reasoning step is where Chain-of-Thought happens. The model is implicitly or explicitly asked to "think step by step" before producing its action. The output is constrained — either valid text or a valid tool call matching the catalog. There is no in-between.

**Frameworks that implement reasoning:** the model itself (any LLM). The framework's job is to assemble the input (system prompt + memory + history + tool catalog) and parse the output (extract tool name and arguments, or detect the final response).

---

### Component 2: Tool use

When reasoning produces a tool call, the agent runtime takes over to actually execute it. This is **not** the model's job. The model proposes; the runtime validates, authorizes, executes, and formats.

```
   Model output: tool_call = {"name": "send_email", "args": {"to": "alex@acme.com"}}

   Runtime executes:
   ┌─────────────────────────────────────────────┐
   │  1. Validate                                │
   │     - args match schema?                    │
   │     - required fields present?              │
   │     - types correct?                        │
   │                                             │
   │  2. Authorize                               │
   │     - is this user allowed to call this?    │
   │     - is the recipient on an allowlist?    │
   │     - has the user hit a quota?            │
   │                                             │
   │  3. Execute                                 │
   │     - call the actual API/function          │
   │     - apply timeout                         │
   │     - handle network errors                 │
   │                                             │
   │  4. Format                                  │
   │     - shape the response for the model      │
   │     - truncate if too long                  │
   │     - redact secrets                        │
   └─────────────────────────────────────────────┘

   Runtime output: structured tool result
                   {"success": true, "message_id": "m-abc123"}
```

This is where most production bugs live. The model can be perfect; if the tool layer skips authorization, the agent is dangerous. If it skips validation, the agent crashes on malformed arguments. If it skips formatting, the model gets confused by the response.

---

### Component 3: Memory

Memory is what makes the agent continuous. Every turn, memory is read (to inform reasoning) and written (to capture what just happened).

```
   ┌─────────────────────────────────────────────────────────┐
   │                                                         │
   │   READ at the start of each reasoning step:             │
   │                                                         │
   │   - Conversation buffer: the last N turns               │
   │     (in-context, always available)                      │
   │                                                         │
   │   - Episodic memory: past interactions similar to        │
   │     the current task (retrieved by vector similarity)   │
   │                                                         │
   │   - Semantic memory: distilled facts about the user     │
   │     (retrieved by relevance to the current message)     │
   │                                                         │
   │   WRITE at the end of each turn:                        │
   │                                                         │
   │   - Append the new turn to the conversation buffer      │
   │   - Optionally summarize and store in episodic memory   │
   │   - Optionally extract and store facts in semantic      │
   │     memory                                              │
   │                                                         │
   └─────────────────────────────────────────────────────────┘
```

The memory layer is the most operationally subtle part of the agent. Three policies must be defined:

- **What gets read?** Decide on retrieval triggers (always? on demand? only when relevant?) and relevance scoring.
- **What gets written?** Decide on extraction (full turns? summaries? distilled facts?) and triggers (every turn? only on completion?).
- **What gets forgotten?** Decide on decay (time-based? size-based? never?) and eviction policy.

Without these policies, memory grows unbounded, retrieval returns noise, and prompts balloon. With them, the agent becomes more capable over the course of a session — and across sessions.

---

### The chain, in three turns

A concrete trace of how a single request flows through the three components:

```
   TURN 1
   ──────
   [Read memory]        Conversation: empty
                         Episodic: "similar past request about Acme invoices"
                         Semantic: "user is Alex, prefers terse replies"

   [Reason]              Thought: "User wants last invoice emailed.
                                    I need to find it first."
                         Output:  tool_call(search_invoices, {customer: "Alex"})

   [Act]                 search_invoices returns 3 invoices, latest INV-2024-009

   [Write memory]        Append to conversation buffer.

   TURN 2
   ──────
   [Read memory]         Conversation: turn 1 above
                         Episodic: same as above
                         Semantic: same as above

   [Reason]              Thought: "Found the invoice. Now I need the PDF
                                    and to send the email."
                         Output:  tool_call(get_invoice_pdf, {id: "INV-2024-009"})

   [Act]                 Returns PDF URL and amount.

   [Write memory]        Append.

   TURN 3
   ──────
   [Read memory]         Conversation: turns 1, 2 above.

   [Reason]              Thought: "I have the invoice details. Send the email."
                         Output:  tool_call(send_email,
                                           {to: "alex@acme.com",
                                            subject: "Your invoice",
                                            attachment: "..."})

   [Act]                 send_email returns success.

   [Write memory]        Append. Extract semantic fact: "Alex prefers invoices
                         emailed directly, not downloaded."

   TURN 4
   ──────
   [Read memory]         Conversation: full history.

   [Reason]              Thought: "Email sent. Reply to the user."
                         Output:  text response (no tool call)

   Exit loop.
```

Four turns. Three tool calls. The reasoning step stayed narrow ("what should I do next?"). Memory accumulated context. The tool layer executed safely. The final turn produced text instead of a tool call, which is what triggers the loop to exit.

---

## Build It / In Depth

### A minimal implementation, end to end

```python
from openai import OpenAI
import json

client = OpenAI()

# --- TOOLS --------------------------------------------------------------------

def search_invoices(customer: str) -> str:
    return json.dumps([
        {"id": "INV-2024-009", "amount": 1500, "date": "2024-12-01"},
        {"id": "INV-2024-008", "amount": 1500, "date": "2024-11-01"},
    ])

def send_email(to: str, subject: str, body: str) -> str:
    return json.dumps({"success": True, "message_id": "m-001"})

TOOL_FUNCTIONS = {
    "search_invoices": search_invoices,
    "send_email": send_email,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_invoices",
            "description": "Find invoices for a customer by name.",
            "parameters": {
                "type": "object",
                "properties": {"customer": {"type": "string"}},
                "required": ["customer"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
]

# --- MEMORY -------------------------------------------------------------------

class Memory:
    def __init__(self):
        self.buffer = []      # short-term conversation
        self.semantic = {}    # long-term user facts

    def read(self):
        return self.buffer, self.semantic

    def write_turn(self, role, content):
        self.buffer.append({"role": role, "content": content})
        # In production, also extract semantic facts here.

# --- AGENT LOOP ---------------------------------------------------------------

SYSTEM_PROMPT = """You are a billing assistant for Acme Corp.
Be terse. Use tools to find information before responding."""

def run_agent(user_message: str, max_turns: int = 8) -> str:
    memory = Memory()
    memory.write_turn("user", user_message)

    for turn in range(max_turns):
        # READ memory
        history, semantic = memory.read()

        # REASON
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history,
            tools=TOOL_SCHEMAS,
        )
        msg = response.choices[0].message

        # Did the model decide to call a tool?
        if msg.tool_calls:
            memory.write_turn("assistant", msg.content or "")
            memory.buffer[-1]["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name,
                              "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]

            # ACT — execute each tool call
            for tc in msg.tool_calls:
                fn = TOOL_FUNCTIONS[tc.function.name]
                args = json.loads(tc.function.arguments)
                result = fn(**args)         # validate + authorize + execute here
                memory.write_turn("tool", result)

        else:
            # Model produced text — that's the answer
            memory.write_turn("assistant", msg.content)
            return msg.content

    return "Agent exceeded max turns."

print(run_agent("Find my last invoice and email it to alex@acme.com"))
```

Walk through the code:

- **`Memory`** is a class, not a global. Short-term is the conversation buffer; semantic is a dict of user facts.
- **`TOOL_FUNCTIONS`** is the registry of executable tools. Schemas tell the model what tools exist; functions execute them. Validation, authorization, and execution all happen in the same line (`fn(**args)`) — in production, you would split these for safety.
- **`run_agent`** is the loop. It reads memory, calls the model, dispatches tools, writes memory, repeats.
- **Termination** is implicit: when the model produces text instead of a tool call, the loop exits.

This is the entire skeleton. Frameworks like LangGraph add explicit state types, conditional edges, persistence, and human-in-the-loop — but underneath, every agent does this loop.

---

### Where each component fails

Knowing the failure modes helps you debug:

| Failure | Symptom | Where to look |
|---|---|---|
| Model calls wrong tool | Wrong action taken | Reasoning — check tool descriptions, model selection |
| Model loops forever | Same tool call repeatedly | Reasoning — add termination signal, fix tool result clarity |
| Tool returns bad data | Model builds on bad info | Tool execution — check upstream system, validation |
| Model forgets goal | Drifts off topic mid-conversation | Memory — conversation buffer too short, summary missing |
| Model repeats itself | Same answer twice | Memory — duplicate turns in buffer, no dedup |
| Latency too high | Slow responses | Tool execution — slow upstream API; Reasoning — long context |

In production, every component needs its own observability. Trace per turn: which model was called, with what prompt, producing what output, executing what tool, getting what result, writing what memory. Without that trace, debugging an agent is guesswork.

---

## Use It

### Frameworks that implement the loop

| Framework | How it implements the chain | Best for |
|---|---|---|
| LangGraph | Explicit graph of nodes (reason → act → memory) | Production agents with complex control flow |
| AutoGen | Conversational agents that message each other | Multi-agent research and coding |
| CrewAI | Role-based crews with task handoffs | Structured team workflows |
| OpenAI Agents SDK | Provider-native loop with tracing | OpenAI-centric stacks |
| Claude Agent SDK | Provider-native loop with MCP support | Anthropic-centric stacks |
| smolagents | Minimal code-agent framework | Lightweight code-executing agents |
| Custom code | You write the loop | Full control, no framework dependencies |

Pick a framework when you want batteries-included observability, persistence, and error handling. Pick custom code when the loop is simple and you want zero dependencies.

### Memory tooling

| Tool | What it provides |
|---|---|
| LangGraph checkpointer | Per-thread state persistence (Postgres, Redis, SQLite) |
| Zep | Long-term memory for LLM apps with automatic summarization |
| Letta | Agents with built-in memory tiers (core, archival, recall) |
| mem0 | Memory layer for personalized agents |
| Redis | Short-term session state with TTL |
| Vector DB + Postgres | Custom memory tiers with full control |

---

## Common Pitfalls

- **The model decides tool authorization.** The model says "send the email" and the runtime sends it. The model has no authority to grant permission. Every tool must check the caller independently.

- **No termination condition.** An agent that loops 100 times because the model keeps calling tools will run up a giant bill. Always set `max_iterations` and detect repetition.

- **Memory writes happening on every turn.** Storing the full turn in semantic memory after every step creates noise. Decide which turns deserve long-term storage (completion, significant fact, explicit user instruction) and store only those.

- **No memory eviction.** Memory grows forever. Old facts become stale. New facts become hard to find in the noise. Implement TTL, size caps, and deduplication.

- **Confusing the buffer with memory.** The conversation buffer is short-term memory; it gets passed to the model on every turn. Long-term memory is retrieved on demand. Mixing them bloats the prompt.

- **Skipping tool result formatting.** The model gets back whatever the tool returns — sometimes 50 KB of JSON, sometimes a stack trace. Truncate, redact, and shape the response so the model can actually use it.

- **No tracing.** Without per-turn traces, debugging an agent means reproducing the issue manually. Wire observability (LangSmith, Langfuse, OpenLLMetry) from day one.

---

## Exercises

1. **Easy** — In one sentence each, describe the role of reasoning, tool use, and memory in an agent loop. Give one example of how each can fail.

2. **Medium** — Trace the agent loop for the request "What's the weather in Tokyo and in Paris, then email me the comparison." Write out each turn's reasoning, tool call, tool result, and memory update.

3. **Hard** — You are building a research agent that searches the web, reads PDFs, and writes a report. The agent runs for up to 30 minutes and may use dozens of tool calls. Design the memory system: what goes in the short-term buffer, what gets extracted to long-term memory, when, and how you prevent unbounded growth. Justify each policy.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Reasoning | The agent thinking | A single LLM call that takes the system prompt, memory, conversation history, and tool catalog as input, and produces either text or a structured tool call |
| Tool use | Calling an API | A four-step runtime operation — validate arguments, authorize the call, execute the underlying system, format the response — that turns a model's tool proposal into a real action |
| Memory | Conversation history | Three tiers with different read/write/decay policies — short-term buffer (in-context), long-term episodic (retrieved past interactions), long-term semantic (distilled user facts) |
| Chain | A sequence of LLM calls | The repeated execution of reason → act → memory until the model produces text instead of a tool call; bounded by max_iterations to prevent infinite loops |
| Termination | The agent decides to stop | The model emits text instead of a tool call, indicating it has enough information to answer; combined with max_iterations and repetition detection |
| Tool result | Whatever the API returns | The runtime-formatted, truncated, redacted output of a tool execution, fed back into the model's context for the next reasoning step |
| State | Whatever the agent remembers | The typed object passed between turns — messages, plan, scratchpad, counters — usually implemented as a TypedDict in LangGraph or a Pydantic model elsewhere |
| Trace | Debugging logs | A structured record of every turn: model input, model output, tool call, tool result, memory update, latency, cost — the only way to debug a non-deterministic system |

---

## Further Reading

- **ReAct Paper** — the original paper that introduced the Thought-Action-Observation loop: https://arxiv.org/abs/2210.03629
- **Lilian Weng's "LLM Powered Autonomous Agents"** — deep technical breakdown of the agent loop, planning, and memory: https://lilianweng.github.io/posts/2023-06-23-agent/
- **LangGraph Quickstart** — the canonical reference for building graph-based agents with explicit state and conditional edges: https://langchain-ai.github.io/langgraph/
- **OpenAI Function Calling Guide** — the definitive reference for the structured tool-use protocol: https://platform.openai.com/docs/guides/function-calling
- **Zep Documentation** — a long-term memory layer specifically designed for LLM agents: https://www.getzep.com