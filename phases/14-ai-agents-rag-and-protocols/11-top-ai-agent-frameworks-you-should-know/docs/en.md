# Top AI Agent Frameworks You Should Know

> Eight frameworks, four philosophies — pick the one whose mental model matches your team, not the one with the most stars.

**Type:** Learn
**Prerequisites:** What is an AI Agent?, How AI Agents Chain Tools, Memory, and Reasoning
**Time:** ~25 minutes

---

## The Problem

"Which AI agent framework should we use?" is the question every team asks first. The answer is rarely "the best one" — it is "the one whose mental model fits how your team thinks." Pick the wrong framework and you spend months fighting it instead of building. Pick the right one and the framework disappears into the background.

There are now dozens of frameworks, each with its own philosophy. Some are graphs. Some are crews. Some are conversations between agents. Some are visual canvases. Some are provider-locked. Some are language-locked. The marketing pages blur the differences; the docs reveal them.

This lesson walks through the eight frameworks you will actually encounter in production work — what each one does, how it thinks about agents, and when to reach for it.

---

## The Concept

### Frameworks at a glance

| Framework | Mental model | Language | Provider | Best for |
|---|---|---|---|---|
| LangGraph | Graph of nodes, explicit state | Python, JS | Any | Production agents with complex control flow |
| LangChain | Chains of LLM calls | Python, JS | Any | Rapid prototyping, broad integrations |
| AutoGen | Conversational agents | Python | Any | Multi-agent research, coding |
| CrewAI | Role-based crews | Python | Any | Structured team workflows |
| smolagents | Code-agent minimalism | Python | Any | Lightweight code-executing agents |
| OpenAI Agents SDK | Provider-native runtime | Python | OpenAI | OpenAI-centric stacks |
| Claude Agent SDK | Provider-native runtime | Python, TS | Anthropic | Anthropic-centric stacks |
| Semantic Kernel | Plugin orchestration | C#, Python, JS | Any | Enterprise .NET shops |
| n8n | Visual workflow + AI nodes | Visual + JS | Any | Citizen developers, business workflows |

Three philosophical camps:

```
   Graph / Code-First              Visual / Low-Code             Provider-Native
   (you write the structure)       (you draw the structure)      (you stay close to the API)

   LangGraph                        n8n                          OpenAI Agents SDK
   LangChain                        Flowise                      Claude Agent SDK
   AutoGen                          Langflow                     Google ADK
   CrewAI
   smolagents
```

Code-first frameworks give you precision and testability. Visual frameworks give you speed and accessibility. Provider-native SDKs give you the smoothest path on a single cloud. Most production teams end up with a code-first framework for the core agent and visual tools for non-engineers to extend it.

---

### LangChain and LangGraph

LangChain is the original framework. It started as a chain library (sequence of LLM calls) and grew into an ecosystem for any LLM application. Its agent layer has gone through several iterations: `AgentExecutor`, LangGraph, and now LangGraph as the recommended path for production agents.

**LangGraph** is the production-grade part. It models agents as directed graphs with explicit state, conditional edges, and persistence.

```python
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from typing import TypedDict, Annotated, Literal
from langgraph.graph.message import add_messages

class State(TypedDict):
    messages: Annotated[list, add_messages]

@tool
def get_weather(city: str) -> str:
    """Return the current weather for a city."""
    return f"72°F and sunny in {city}."

tools = [get_weather]
llm = ChatOpenAI(model="gpt-4o").bind_tools(tools)

def call_model(state: State) -> dict:
    return {"messages": [llm.invoke(state["messages"])]}

def should_continue(state: State) -> Literal["tools", "__end__"]:
    last = state["messages"][-1]
    return "tools" if last.tool_calls else "__end__"

graph = (
    StateGraph(State)
    .add_node("agent", call_model)
    .add_node("tools", ToolNode(tools))
    .add_edge(START, "agent")
    .add_conditional_edges("agent", should_continue, {"tools": "tools", "__end__": END})
    .add_edge("tools", "agent")
    .compile()
)

graph.invoke({"messages": [("user", "Weather in Tokyo?")]})
```

**Strengths:** explicit state, conditional edges, persistence (checkpointers), human-in-the-loop, integrates with LangChain's huge tool ecosystem, LangSmith observability built in.

**Weaknesses:** steeper learning curve than visual frameworks; verbose for simple agents; the LangChain core library is bloated and opinionated.

**Reach for:** production agents with branching logic, retries, persistent state across runs, anything you need to test rigorously.

---

### AutoGen

AutoGen (Microsoft) is a framework for **conversational agents** — agents that message each other to complete a task. Each agent is a "ConversableAgent" with a role, an LLM backend, and optionally human-in-the-loop termination.

```python
from autogen import AssistantAgent, UserProxyAgent

assistant = AssistantAgent(
    name="engineer",
    llm_config={"model": "gpt-4o"},
    system_message="You write Python code to solve the user's problem.",
)

user_proxy = UserProxyAgent(
    name="user",
    human_input_mode="TERMINATE",  # ask the human before executing code
    code_execution_config={"work_dir": "coding"},
)

user_proxy.initiate_chat(
    assistant,
    message="Write a function that computes the Fibonacci sequence up to n.",
)
```

**Strengths:** excellent for code-generation tasks (built-in code execution), multi-agent conversation patterns are natural to express, strong Microsoft research backing.

**Weaknesses:** conversation patterns are harder to debug than graph patterns; the "conversation between agents" model is opinionated and doesn't fit every use case; documentation has historically lagged the API.

**Reach for:** multi-agent research, code generation and execution, tasks that benefit from agent-to-agent negotiation.

---

### CrewAI

CrewAI frames agents as a **crew** with roles — researcher, writer, reviewer, project manager. You define agents, tasks, and a process (sequential or hierarchical), and CrewAI orchestrates them.

```python
from crewai import Agent, Task, Crew

researcher = Agent(
    role="Senior Researcher",
    goal="Find the latest research on RAG architectures.",
    backstory="Expert in retrieval-augmented generation with 10 years experience.",
    tools=[search_tool],
)

writer = Agent(
    role="Technical Writer",
    goal="Write a clear summary of the research.",
    backstory="Specializes in explaining technical concepts to engineers.",
)

research_task = Task(
    description="Find 5 recent papers on RAG.",
    agent=researcher,
    expected_output="A list of papers with summaries.",
)

writing_task = Task(
    description="Write a 500-word summary based on the research.",
    agent=writer,
    expected_output="A polished blog post.",
)

crew = Crew(agents=[researcher, writer], tasks=[research_task, writing_task])
result = crew.kickoff()
```

**Strengths:** role-based mental model is intuitive; sequential and hierarchical processes cover most multi-agent patterns; nice developer experience.

**Weaknesses:** the role metaphor can be constraining when the task does not fit a team structure; less flexible than LangGraph for arbitrary control flow; smaller ecosystem.

**Reach for:** structured multi-agent workflows where the roles are obvious (research → write → review), business process automation with AI agents.

---

### smolagents

smolagents (Hugging Face) is the minimalist entry. It implements one pattern well: the **code agent** — an agent that writes and executes Python code to solve problems.

```python
from smolagents import CodeAgent, DuckDuckGoSearchTool, HfApiModel

agent = CodeAgent(
    tools=[DuckDuckGoSearchTool()],
    model=HfApiModel(),
)

agent.run("Find the population of Tokyo and Paris, then compute the ratio.")
```

The agent writes Python code, executes it, observes the output, and iterates. It is "smol" (small) — single file, few abstractions, easy to read.

**Strengths:** minimal abstractions, code agents are powerful for data analysis and computation tasks, Hugging Face integration.

**Weaknesses:** code execution is dangerous if not sandboxed; not designed for conversational or multi-step business workflows; smaller community than LangChain or AutoGen.

**Reach for:** data analysis agents, computational tasks where the agent writes code to solve them, teams that prefer minimal dependencies.

---

### OpenAI Agents SDK

OpenAI's official agent runtime. Tighter integration with OpenAI-specific features (Responses API, hosted tools, tracing) than LangChain or AutoGen.

```python
from agents import Agent, Runner, function_tool

@function_tool
def get_weather(city: str) -> str:
    return f"72°F and sunny in {city}."

agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant.",
    tools=[get_weather],
)

result = Runner.run_sync(agent, "What's the weather in Tokyo?")
print(result.final_output)
```

**Strengths:** first-class OpenAI support (Responses API, hosted tools like web search and code interpreter, built-in tracing), clean API, official.

**Weaknesses:** locked to OpenAI models; newer framework, smaller ecosystem; less flexible control flow than LangGraph.

**Reach for:** OpenAI-centric stacks, teams that want official support and don't need cross-provider portability.

---

### Claude Agent SDK

Anthropic's agent SDK. Designed around Claude's strengths (long context, tool use, computer use) and MCP-native.

```python
from claude_agent_sdk import Agent, tool

@tool
def get_weather(city: str) -> str:
    return f"72°F and sunny in {city}."

agent = Agent(
    model="claude-sonnet-4-5",
    tools=[get_weather],
    system_prompt="You are a helpful assistant.",
)

result = agent.run("What's the weather in Tokyo?")
print(result.text)
```

**Strengths:** MCP-native (uses MCP servers as tool sources out of the box), strong Claude-specific optimizations, clean API.

**Weaknesses:** Anthropic-centric; newer; smaller ecosystem than LangChain.

**Reach for:** Anthropic-centric stacks, MCP-heavy integrations, teams that want Claude-specific optimizations.

---

### Semantic Kernel

Microsoft's enterprise-focused framework. Strong in .NET environments, plugin-based architecture, supports multiple LLM providers.

```python
import semantic_kernel as sk
from semantic_kernel.functions import kernel_function

class WeatherPlugin:
    @kernel_function(description="Get the current weather for a city.")
    def get_weather(self, city: str) -> str:
        return f"72°F and sunny in {city}."

kernel = sk.Kernel()
kernel.add_plugin(WeatherPlugin(), plugin_name="Weather")

result = await kernel.invoke_prompt(
    "What's the weather in {{$city}}?",
    city="Tokyo",
)
```

**Strengths:** first-class .NET support, plugin architecture is clean for enterprise apps, multi-provider.

**Weaknesses:** smaller Python community compared to LangChain; less momentum in the agent space specifically; more enterprise-oriented than startup-oriented.

**Reach for:** .NET shops, enterprise apps with strict plugin architectures, multi-provider strategies.

---

### n8n (and other visual frameworks)

n8n is a visual workflow platform with first-class AI agent nodes. Not a "framework" in the traditional sense — more like Zapier with LLM superpowers.

```
   [Chat Trigger] → [AI Agent] → [Tool: HTTP Request]
                          ↓
                   [Memory: Window Buffer]
                          ↓
                   [Reply to User]
```

**Strengths:** non-engineers can build agents; visual debugging; huge integration library (400+ nodes); rapid prototyping.

**Weaknesses:** complex logic gets unwieldy on a canvas; no programmatic testing; per-node latency overhead; harder to version-control meaningfully.

**Reach for:** prototyping, citizen developers, business workflows where the logic changes weekly. See the n8n vs LangGraph chapter for a deeper comparison.

---

## Build It / In Depth

### Same task in three frameworks

Task: a customer support agent that searches the knowledge base and replies with citations.

**LangGraph:**
```python
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_community.tools.tavily_search import TavilySearchResults

class State(TypedDict):
    messages: Annotated[list, add_messages]

tools = [TavilySearchResults(max_results=3)]
llm = ChatOpenAI(model="gpt-4o-mini").bind_tools(tools)

def call_model(state: State) -> dict:
    return {"messages": [llm.invoke(state["messages"])]}

def should_continue(state: State) -> Literal["tools", "__end__"]:
    last = state["messages"][-1]
    return "tools" if last.tool_calls else "__end__"

graph = (
    StateGraph(State)
    .add_node("agent", call_model)
    .add_node("tools", ToolNode(tools))
    .add_edge(START, "agent")
    .add_conditional_edges("agent", should_continue, {"tools": "tools", "__end__": END})
    .add_edge("tools", "agent")
    .compile()
)

graph.invoke({"messages": [("user", "How do I reset my password?")]})
```

**AutoGen:**
```python
from autogen import AssistantAgent, UserProxyAgent

kb_agent = AssistantAgent(
    name="kb_agent",
    llm_config={"model": "gpt-4o-mini"},
    system_message="You search the knowledge base and answer with citations.",
)

user = UserProxyAgent(
    name="user",
    human_input_mode="NEVER",
    code_execution_config=False,
)

user.initiate_chat(kb_agent, message="How do I reset my password?")
```

**OpenAI Agents SDK:**
```python
from agents import Agent, Runner, function_tool

@function_tool
def search_kb(query: str) -> str:
    return "[doc1] To reset your password: go to Settings > Security > Reset."

agent = Agent(
    name="Support",
    instructions="Search the KB and reply with citations.",
    tools=[search_kb],
)

result = Runner.run_sync(agent, "How do I reset my password?")
print(result.final_output)
```

All three produce the same outcome. The differences are in:

- **State management** — LangGraph is explicit; AutoGen is implicit (in the conversation); OpenAI SDK is internal.
- **Multi-agent patterns** — AutoGen excels at agent-to-agent; LangGraph requires more wiring; OpenAI SDK has handoff primitives.
- **Provider lock-in** — OpenAI SDK is locked; LangGraph and AutoGen are provider-agnostic.

---

### Decision procedure

```
   Is your team non-engineer-heavy?
   (PM, ops, support building their own workflows)
              │
      YES ────┴──── NO
       │             │
       ▼             ▼
    n8n         Do you have engineers who can write
                Python and want full control?
                          │
                  YES ────┴──── NO
                   │             │
                   ▼             ▼
                LangGraph    Are you all-in on one provider?
                or AutoGen            │
                or smolagents   YES ──┴── NO
                                │       │
                                ▼       ▼
                          OpenAI or  Pick the
                          Claude SDK  provider-agnostic
                                       option with the
                                       best docs
```

---

## Use It

### What to use for what

| If you need… | Reach for… |
|---|---|
| Production agent with complex branching, retries, persistence | **LangGraph** |
| Multi-agent conversation, code generation | **AutoGen** |
| Role-based team workflow (research → write → review) | **CrewAI** |
| Lightweight code-executing agent | **smolagents** |
| OpenAI-centric stack with official support | **OpenAI Agents SDK** |
| Anthropic-centric stack with MCP-native | **Claude Agent SDK** |
| .NET / enterprise plugin architecture | **Semantic Kernel** |
| Non-engineer authors, rapid prototyping | **n8n / Flowise / Langflow** |
| Cross-provider with maximum ecosystem | **LangGraph + LangChain** |

### Combining frameworks

Many production systems use more than one:

- **n8n for business workflows** (notifications, CRM updates, simple ETL).
- **LangGraph for the AI agent core** (the part that requires reasoning).
- **OpenAI / Claude SDK** for specific provider features (Responses API, computer use).
- **Custom MCP servers** for standardized tool access.

Pick one framework as the agent runtime. Add others only when they solve a problem the runtime cannot.

---

## Common Pitfalls

- **Choosing a framework before the use case.** "Let's use LangGraph" backwards. Pick the framework that fits the problem, not the one with the most stars.

- **Mixing too many frameworks.** Each framework has its own abstractions and mental model. Two is sometimes necessary; three is chaos.

- **Ignoring the learning curve.** LangGraph and AutoGen reward engineers who think in graphs and conversations. Teams without that background will struggle; n8n is a gentler on-ramp.

- **Skipping observability.** Every framework has different observability tools (LangSmith for LangGraph, OpenAI Traces for OpenAI SDK, etc.). Pick one and wire it in from day one.

- **Choosing a provider-native SDK for cross-provider needs.** If you might switch from OpenAI to Anthropic, do not start with the OpenAI Agents SDK. Use LangGraph or smolagents.

- **Forgetting that frameworks are scaffolding.** The framework does not decide whether your agent works — your prompt, your tools, your memory, and your evaluation do. A great framework with a bad prompt still fails.

---

## Exercises

1. **Easy** — Pick three of the eight frameworks. For each, write one sentence describing its mental model and one type of problem it fits best.

2. **Medium** — Take a real task you have worked on (or a hypothetical one). Design it in two of the frameworks above. Compare the code: which is more readable? Which is easier to test? Which gives you better observability?

3. **Hard** — Your company has standardized on LangGraph but a new team wants to use n8n for a business workflow that feeds data into the LangGraph agent. Design the integration: how does the n8n workflow call the LangGraph agent, how do they share state, what are the failure modes, and how do you monitor the cross-framework boundary?

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| LangChain | An LLM framework | A broad ecosystem for LLM applications; the production-grade agent runtime is now LangGraph (a separate library in the same family) |
| LangGraph | LangChain with graphs | A Python framework that models agents as typed state machines with explicit nodes, edges, and conditional transitions; the recommended path for production LangChain-family agents |
| AutoGen | A chatbot framework | Microsoft's framework for conversational agents that message each other to complete tasks; particularly strong for code generation and execution |
| CrewAI | A team simulator | A role-based framework where you define agents as team members (researcher, writer, reviewer) and tasks; sequential or hierarchical processes |
| smolagents | A toy framework | A minimalist Hugging Face framework focused on code-executing agents; small in code size, opinionated in approach |
| OpenAI Agents SDK | Just an OpenAI wrapper | OpenAI's official agent runtime with first-class Responses API, hosted tools, and tracing integration; provider-locked |
| Claude Agent SDK | Just an Anthropic wrapper | Anthropic's official agent SDK with MCP-native tool integration and Claude-specific optimizations |
| Semantic Kernel | Microsoft's LangChain | An enterprise-focused framework with first-class .NET support and a plugin-based architecture |

---

## Further Reading

- **LangGraph Quickstart** — the canonical reference for graph-based agents: https://langchain-ai.github.io/langgraph/
- **AutoGen Documentation** — Microsoft's multi-agent conversation framework: https://microsoft.github.io/autogen/
- **CrewAI Documentation** — role-based agent orchestration: https://docs.crewai.com
- **smolagents** — the minimalist code-agent framework: https://github.com/huggingface/smolagents
- **OpenAI Agents SDK Documentation** — the official OpenAI agent runtime: https://openai.github.io/openai-agents-python/
- **Claude Agent SDK Documentation** — the official Anthropic agent SDK: https://docs.anthropic.com/en/docs/agents