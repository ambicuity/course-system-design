# What is an AI Agent?

> A model answers questions. An agent pursues goals. The difference is a loop, tools, and memory.

**Type:** Learn
**Prerequisites:** LLM Fundamentals, Function Calling, Basic Python
**Time:** ~25 minutes

---

## The Problem

We have been calling everything that calls an LLM an "agent." A chatbot that calls a single API is an agent. A script that wraps a prompt template is an agent. A workflow that has an LLM step in the middle is an agent. The word has lost its meaning. Worse, it has lost its utility — you cannot make architectural decisions about "an agent" if you cannot agree on what counts as one.

A useful definition has to draw a line. It has to separate agents from chatbots, from chains, from workflows, and from plain API wrappers. It has to identify the properties that turn a language model from a text generator into an *actor* — something that perceives, decides, and acts in pursuit of a goal. And it has to be concrete enough that two engineers can read the same definition and agree on whether the system in front of them qualifies.

This lesson draws that line. It defines an AI agent by its required properties, contrasts it with related concepts, and gives you the vocabulary to talk about agents precisely in design reviews.

---

## The Concept

### The shortest definition that still means something

An **AI agent** is a software system that can perceive its environment, reason about a goal, choose actions, and execute them — possibly across many steps, possibly using tools, possibly with memory — without a human dictating each step.

Three words carry the weight: *perceive*, *decide*, *act*. A chatbot perceives a message and produces a reply, but it does not *act* on the world. A script perceives inputs and runs deterministically, but it does not *decide*. An agent does all three, and crucially, the decisions are made by a model that can adapt to inputs it has never seen before.

```
   ┌─────────────────────────────────────────────────────┐
   │                   AI AGENT                          │
   │                                                     │
   │   Environment ──► Perceive ──► Decide ──► Act       │
   │       ▲                                     │       │
   │       │                                     ▼       │
   │       └─────────────── Observe result ───────────    │
   │                                                     │
   │   (loop repeats until goal is met or agent stops)   │
   └─────────────────────────────────────────────────────┘
```

The loop is what makes it an agent. A single LLM call that returns a string is a generation, not an agent. A loop that calls the LLM, observes the result, and decides whether to keep going — that is an agent.

---

### The five required properties

To call something an agent, it must exhibit at least these five properties. Missing any one of them and you have a different thing — a chatbot, a chain, a workflow.

```
   ┌─────────────────────────────────────────────────────────┐
   │                                                         │
   │   1. Autonomy        Acts without a human dictating     │
   │                      each step (though humans may be    │
   │                      in the loop for approval).         │
   │                                                         │
   │   2. Perception      Reads from its environment:        │
   │                      user messages, tool responses,     │
   │                      retrieved documents, sensor data.   │
   │                                                         │
   │   3. Reasoning       Uses a model (usually an LLM) to   │
   │                      decide what to do next, given      │
   │                      the current state.                 │
   │                                                         │
   │   4. Tool use        Can call external systems: APIs,   │
   │                      databases, code, browsers, files.  │
   │                                                         │
   │   5. Memory          Remembers context across turns:    │
   │                      short-term (this conversation)     │
   │                      and long-term (past sessions).     │
   │                                                         │
   └─────────────────────────────────────────────────────────┘
```

A chatbot has property 3 (reasoning) and maybe 1 (autonomy over text). It usually lacks 4 (tools) and 5 (memory). A workflow has 1 (autonomy is mechanical), 4 (it calls tools), but lacks 3 (no reasoning; it follows fixed rules). An agent has all five.

---

### What an agent is not

Clearing up the most common confusions:

| System | Has reasoning? | Has tools? | Loops on results? | Is an agent? |
|---|---|---|---|---|
| LLM API call | Yes | No | No | No — it's a generation |
| Chatbot (no tools) | Yes | No | No | No — it's a conversation |
| RAG pipeline | Yes | Yes (retrieval) | No (single turn) | No — it's a retrieval pipeline |
| Chain (LangChain `Chain`) | Yes | Yes | No | No — it's a fixed sequence |
| Workflow (n8n, Zapier) | No | Yes | Sometimes | No — it's automation |
| Agent | Yes | Yes | Yes | **Yes** |

The discriminating feature is the **closed loop**. The agent runs, observes the outcome of its action, and decides whether to take another action, all within a single user request. A workflow might loop, but it loops on deterministic rules; an agent loops on model-driven decisions.

---

### The agent anatomy

```
   ┌──────────────────────────────────────────────────────┐
   │                      AGENT                            │
   │                                                      │
   │   ┌──────────────┐    ┌──────────────┐               │
   │   │   Reasoning  │◄──►│    Memory    │               │
   │   │   (LLM)      │    │              │               │
   │   └──────┬───────┘    └──────────────┘               │
   │          │                                           │
   │          ▼                                           │
   │   ┌──────────────┐    ┌──────────────┐               │
   │   │   Planner    │    │   Tool use   │               │
   │   │  (optional)  │    │   executor   │               │
   │   └──────┬───────┘    └──────┬───────┘               │
   │          │                   │                       │
   │          ▼                   ▼                       │
   │   ┌──────────────────────────────────────┐           │
   │   │        Action → Environment          │           │
   │   └──────────────────────────────────────┘           │
   │                                                      │
   └──────────────────────────────────────────────────────┘
```

- **Reasoning (LLM):** the brain. Receives the goal + context + tool descriptions, decides the next action.
- **Memory:** short-term (current task state), long-term (past interactions, user preferences).
- **Planner (optional):** decomposes a complex goal into sub-goals before acting.
- **Tool-use executor:** takes the LLM's structured output, validates it, calls the right tool, formats the response.
- **Environment:** everything the agent can affect — APIs, databases, browsers, files, other agents.

Some agents collapse planner and reasoning into one (most LangGraph agents). Others separate them explicitly (AutoGen, ReAct-style loops). Both are valid.

---

### Single agent vs. multi-agent vs. human-in-the-loop

Three architectural patterns, each suited to different problems.

```
   Single Agent
   ┌─────────────────────────┐
   │       User             │
   │         │               │
   │         ▼               │
   │   ┌──────────────┐      │
   │   │    Agent     │      │
   │   │  (one brain, │      │
   │   │ many tools)  │      │
   │   └──────────────┘      │
   └─────────────────────────┘
   When: tasks a single LLM can hold in its head.
   Pros: simplest to build and debug.
   Cons: limited by one model's context and skill.


   Multi-Agent
   ┌──────────────────────────────────────────┐
   │  User                                     │
   │    │                                      │
   │    ▼                                      │
   │  ┌──────────┐    ┌──────────┐             │
   │  │ Planner  │───►│Researcher│             │
   │  │  agent   │    │  agent   │             │
   │  └────┬─────┘    └────┬─────┘             │
   │       │               │                  │
   │       ▼               ▼                  │
   │  ┌──────────┐    ┌──────────┐             │
   │  │ Writer   │◄──►│ Reviewer │             │
   │  │  agent   │    │  agent   │             │
   │  └──────────┘    └──────────┘             │
   └──────────────────────────────────────────┘
   When: tasks need specialized roles (research, write,
         review, code, test).
   Pros: each agent can use a different model or prompt;
         roles are explicit; failures are localized.
   Cons: coordination overhead; harder to debug.


   Human-in-the-Loop
   ┌──────────────────────────────────────────────┐
   │  User                                         │
   │    │                                          │
   │    ▼                                          │
   │  ┌──────────┐                                 │
   │  │  Agent   │                                 │
   │  └────┬─────┘                                 │
   │       │                                       │
   │       ▼                                       │
   │  ┌──────────┐                                 │
   │  │  Human   │  ◄── approval / correction      │
   │  │ approval │                                 │
   │  └────┬─────┘                                 │
   │       │                                       │
   │       ▼                                       │
   │  ┌──────────┐                                 │
   │  │  Agent   │ (continues after approval)      │
   │  └──────────┘                                 │
   └──────────────────────────────────────────────┘
   When: high-stakes actions (delete, send money, deploy).
   Pros: safety; trust; regulatory compliance.
   Cons: latency; availability of humans.
```

Most production systems start as single agents, grow into multi-agent when one brain cannot hold the full task, and add human-in-the-loop the moment the agent touches irreversible actions.

---

## Build It / In Depth

### The minimal agent, in 30 lines of Python

```python
from openai import OpenAI
import json

client = OpenAI()

# Tool the agent can use
def get_weather(city: str) -> str:
    return f"It is 72°F and sunny in {city}."

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }
]

def run_agent(user_message: str) -> str:
    messages = [{"role": "user", "content": user_message}]

    for step in range(5):  # max 5 steps to prevent infinite loops
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOLS,
        )
        msg = response.choices[0].message

        if msg.tool_calls:
            # Agent decided to call a tool — execute it
            messages.append(msg)
            for tool_call in msg.tool_calls:
                args = json.loads(tool_call.function.arguments)
                result = get_weather(**args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
        else:
            # Agent decided it has the final answer
            return msg.content

    return "Agent exceeded max steps."

print(run_agent("What's the weather in Tokyo?"))
# → "It is currently 72°F and sunny in Tokyo."
```

Every line of this code corresponds to one of the five properties:

- Autonomy: `for step in range(5)` — the agent decides each step, not a human.
- Perception: `messages` carries the full context, including tool responses.
- Reasoning: `client.chat.completions.create` — the LLM decides what to do next.
- Tool use: `get_weather(...)` and the `TOOLS` schema.
- Memory: `messages` is the short-term memory; you would extend it with a vector store for long-term.

That is the entire skeleton. Everything more complex — frameworks, observability, multi-agent orchestration — builds on this loop.

---

### What "decide" actually means

The most misunderstood word in the definition is *decide*. People imagine the agent choosing between options like a person at a crossroads. The reality is narrower and more interesting.

```
   Given:
   - System prompt (the agent's role, constraints, style)
   - Conversation history (memory)
   - Available tool descriptions (what it can do)
   - User's goal (the task)

   Produce:
   - Either: a text response (the final answer)
   - Or: a structured tool call (the next action)
```

The model does not "think" in the human sense. It produces a probability distribution over the next token, conditioned on everything it has seen, and the structured output format (function call schema) constrains that distribution to either text or a tool call. The "decision" is which path it takes.

This is why agents are non-deterministic. Run the same prompt twice and you might get different tool choices, different orderings, different final answers. The non-determinism is what makes them powerful (they handle novel inputs) and what makes them hard to debug (the same input can produce different traces).

---

### Why the loop matters

The closed loop — observe, decide, act, repeat — is what separates agents from single-shot LLM calls. Consider:

**Without a loop:** "Translate this sentence to French." → LLM returns translation. Done.

**With a loop:** "Plan a 3-day trip to Tokyo, book the cheapest flights, and email me the itinerary."

```
   Step 1: LLM decides → call search_flights(origin, destination, dates)
   Step 2: Receives 10 flight options → decides → filter by price
   Step 3: Decides → call book_flight(cheapest_option)
   Step 4: Receives booking confirmation → decides → call send_email(...)
   Step 5: Decides → return final summary to user
```

Each step's output becomes the next step's input. The agent adapts to whatever the tools return. If the cheapest flight is sold out, it picks the next one. If the email service is down, it retries or surfaces the error. A single LLM call could never do this.

---

## Use It

### When you need an agent

| If your task is… | You need… |
|---|---|
| Single question → single answer | A chatbot (no agent) |
| Question + retrieval → grounded answer | A RAG pipeline (no agent loop) |
| Multi-step workflow with deterministic branching | A workflow engine (n8n, Temporal) |
| Multi-step goal that adapts to intermediate results | An **agent** |
| Goal that needs different specialized skills in sequence | A **multi-agent system** |
| Goal that includes irreversible actions | An **agent with human-in-the-loop** |

### When you do NOT need an agent

Agents are more complex, more expensive, less predictable, and harder to debug than the simpler alternatives. Reach for them only when the simpler things cannot do the job.

- If a single LLM call answers the question, ship that.
- If retrieval is enough, ship RAG.
- If the workflow is deterministic and known in advance, ship a workflow engine.
- If the workflow involves novel inputs that require reasoning at each step, then you need an agent.

The litmus test: *would a human need to read the previous step's output before deciding the next step?* If yes, an agent. If no, a workflow.

### Agent frameworks to know

| Framework | Mental model | Best for |
|---|---|---|
| LangGraph | Graph of nodes with explicit state | Production agents with complex control flow |
| AutoGen | Conversational agents that message each other | Multi-agent research and coding workflows |
| CrewAI | Role-based crews (researcher, writer, editor) | Structured team-style workflows |
| smolagents | Minimal code-agent framework | Lightweight, code-executing agents |
| n8n (with AI nodes) | Visual workflow + AI agent node | Citizen developers, business workflows |
| OpenAI Agents SDK | Provider-native agent runtime | OpenAI-centric stacks |
| Claude Agent SDK | Provider-native agent runtime | Anthropic-centric stacks |
| Semantic Kernel | Plugin-based, .NET-friendly | Enterprise .NET shops |

---

## Common Pitfalls

- **Calling every LLM-with-tools system an agent.** The loop is the discriminator. A single OpenAI function call wrapped in a Python script is not an agent. Calling it one confuses architecture discussions.

- **Agents for single-turn tasks.** If your task is one prompt in, one response out, you do not need an agent. A generation or a RAG pipeline is simpler, faster, cheaper, and easier to test.

- **No termination criteria.** An agent that loops forever will rack up costs and eventually time out. Always cap iterations (`max_steps`), require explicit "done" signals, and detect when the agent is repeating itself.

- **Confusing reasoning with intelligence.** The agent "reasons" via token prediction, not logic. It can be confidently wrong. Treat its outputs the same way you treat any statistical model — validate before acting on them.

- **Skipping the tool layer's safety.** Letting the model call `delete_user(id=...)` directly is how agents make headlines. The tool executor must authorize and validate; the model only proposes.

- **No observability.** Without structured traces of every step, debugging an agent is guesswork. Wire LangSmith, Langfuse, or equivalent from day one.

- **Confusing the agent with the LLM.** The LLM is one component of the agent. The agent includes the loop, the memory, the tools, and the validation logic. A great LLM with no loop is a chatbot, not an agent.

---

## Exercises

1. **Easy** — In one sentence, define "AI agent" so a colleague could tell whether a given system qualifies. List the five required properties.

2. **Medium** — Take a system you have built or used (a chatbot, a RAG app, a Zapier workflow, a search engine). For each, decide whether it qualifies as an agent and justify your answer by mapping each of the five properties to a concrete component (or to its absence).

3. **Hard** — You are designing an agent that books business travel. It must search flights, compare prices, hold bookings, request manager approval for trips over $2,000, send the itinerary to the traveler, and add the trip to the calendar. Which architectural pattern fits best: single agent, multi-agent, or human-in-the-loop? Justify by mapping each step of the workflow to a property (reasoning, tools, memory) and identifying which steps require human approval and why.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| AI agent | Any LLM with a prompt | A software system with five properties — autonomy, perception, reasoning, tool use, and memory — operating in a closed loop where the model decides each next action based on observations |
| Chatbot | An AI agent | A conversational interface that responds to messages; lacks tool use and the multi-step decision loop, so it does not meet the definition of an agent |
| Multi-agent system | Several agents running in parallel | A coordinated architecture where specialized agents (planner, researcher, writer, reviewer) hand off work to each other, often via message passing |
| Reasoning | The agent thinks | The LLM produces a probability distribution over the next token, conditioned on the prompt, conversation history, and tool descriptions; the structured output format constrains that to either text or a tool call |
| Tool use | Calling an API | A loop in which the model emits a structured function call, the runtime validates and authorizes it, the actual system executes it, and the result is fed back into the model's context for the next decision |
| Memory | Storing conversations | Multiple tiers — short-term (the conversation buffer), long-term episodic (past interactions), long-term semantic (distilled facts about the user) — each with different read/write/decay policies |
| Human-in-the-loop | Asking the user | A deliberate pause in the agent loop where the runtime surfaces the proposed action to a human and waits for approval before continuing; required for high-stakes or irreversible actions |
| Agent loop | The agent runs | The closed cycle of (observe state → model decides → execute action → observe result → repeat) that distinguishes an agent from a single LLM call; bounded by max iterations and termination signals to prevent runaway behavior |

---

## Further Reading

- **"Building Effective Agents"** — Anthropic's research-backed guide on when agents add value over chains, and the failure modes that hit production: https://www.anthropic.com/research/building-effective-agents
- **LangGraph Quickstart** — the canonical reference for building graph-based agents with explicit state and conditional edges: https://langchain-ai.github.io/langgraph/
- **OpenAI Function Calling Guide** — the definitive reference for the structured tool-use protocol that most agents build on: https://platform.openai.com/docs/guides/function-calling
- **"What is an AI Agent?"** by Lilian Weng — a deep technical breakdown of the agent loop, planning, and memory: https://lilianweng.github.io/posts/2023-06-23-agent/
- **ReAct: Synergizing Reasoning and Acting in Language Models** — the original paper that introduced the reasoning-action-observation loop most modern agents implement: https://arxiv.org/abs/2210.03629