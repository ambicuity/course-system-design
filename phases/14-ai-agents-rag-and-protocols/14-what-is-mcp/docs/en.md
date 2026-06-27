# What is MCP?

> The protocol that lets any agent talk to any tool — without writing per-agent glue code.

**Type:** Learn
**Prerequisites:** What is an AI Agent?, AI Agent versus MCP, Function Calling, JSON-RPC basics
**Time:** ~25 minutes

---

## The Problem

Your agent needs to talk to GitHub, Slack, Postgres, your CRM, and your internal metrics store. Each integration requires:

1. Reading the API documentation.
2. Writing a function-calling wrapper that describes the tool to the model.
3. Handling authentication, pagination, errors, retries.
4. Re-doing all of it when you switch from GPT-4o to Claude to Gemini.
5. Re-doing all of it when you build a second agent that needs the same tool.

That is five integrations × five agents × three model providers = seventy-five custom integrations to maintain. Each one a place to introduce bugs. Each one a different abstraction. Each one a per-team implementation of the same idea: "let the model call this thing."

The Model Context Protocol (MCP) is an attempt to fix this. It is an open standard — like HTTP, but for tool calls — that defines a single way for any agent (any model, any framework) to discover and invoke any tool exposed by any server. One integration per tool. Every MCP-compatible agent can use it. No glue code per agent.

This lesson explains what MCP actually is, the three roles (host, client, server), the five primitives, and how to think about it as infrastructure rather than magic.

---

## The Concept

### What MCP is, in one sentence

MCP is a **JSON-RPC-based protocol** that standardizes how clients (agents, IDEs, LLM runtimes) discover and call tools, fetch resources, and use prompt templates exposed by servers.

That sentence packs in five ideas worth unpacking:

1. **JSON-RPC** — a lightweight, language-agnostic remote procedure call format. Every MCP message is a JSON object with a method name and parameters.
2. **Standardized** — there is one spec, not a family of conventions. Clients and servers implement the spec, not a per-vendor API.
3. **Clients** — anything that wants to use tools. Usually an agent runtime or an IDE.
4. **Servers** — anything that exposes tools. Usually a wrapper around an API, database, or file system.
5. **Three things can be exposed:** tools (callable functions), resources (read-only data), and prompts (pre-built templates).

```
   ┌──────────────┐                              ┌──────────────┐
   │    Agent     │  ── tools/list ────────►    │  MCP Server  │
   │   (client)   │  ◄── [tool schemas] ────    │  (filesystem)│
   │              │                              │              │
   │              │  ── tools/call ────────►    │              │
   │              │  ◄── tool result ───────    │              │
   └──────────────┘                              └──────────────┘
         speaks MCP                                    speaks MCP
```

The agent speaks MCP to discover what the server offers, then to invoke specific tools. The server speaks MCP to advertise its capabilities and respond to calls. Neither knows the other exists beyond the protocol.

---

### The three roles: host, client, server

```
   ┌──────────────────────────────────────────────────────────────┐
   │  HOST (AI application: Claude Desktop, Cursor, VS Code)       │
   │                                                              │
   │  ┌────────────┐       ┌────────────┐       ┌────────────┐    │
   │  │ MCP Client │       │ MCP Client │       │ MCP Client │    │
   │  │  (file)    │       │  (git)     │       │ (postgres) │    │
   │  └─────┬──────┘       └─────┬──────┘       └─────┬──────┘    │
   │        │ JSON-RPC            │ JSON-RPC            │          │
   └────────┼─────────────────────┼─────────────────────┼──────────┘
            ▼                     ▼                     ▼
   ┌────────────────┐    ┌────────────────┐    ┌────────────────┐
   │ MCP Server     │    │ MCP Server     │    │ MCP Server     │
   │ (filesystem)   │    │ (git)          │    │ (postgres)     │
   └────────────────┘    └────────────────┘    └────────────────┘
```

- **Host:** the AI application the user interacts with — Claude Desktop, Cursor, an IDE, a custom agent runtime. The host runs one or more MCP clients.
- **MCP Client:** a component inside the host that speaks MCP to one server. One client per server. Translates between the agent's tool calls and the MCP wire format.
- **MCP Server:** a process that exposes tools, resources, and prompts over MCP. Typically a small wrapper around an existing API, database, or file system.

A single host may run many clients, each connected to a different server. The user configures which servers the host should connect to; the host spawns the clients automatically.

---

### The five primitives

MCP defines five building blocks, divided between client-side and server-side capabilities.

**Client-side (what the client offers to the server):**

| Primitive | What it does | Example |
|---|---|---|
| **Roots** | Tells the server which directories it is allowed to access | `/Users/alex/projects` |
| **Sampling** | Asks the host's LLM to generate something (e.g., generate a SQL query) | "Generate a SQL query for: count users by signup date" |

**Server-side (what the server exposes to the client):**

| Primitive | What it does | Example |
|---|---|---|
| **Tools** | Functions the model can invoke with structured arguments | `search_docs(query)`, `create_ticket(title, body)` |
| **Resources** | Read-only data the model can fetch by URI | `file:///docs/handbook.md`, `db://users/42` |
| **Prompts** | Pre-built prompt templates the user can select | "Summarize this document", "Explain this code" |

The most-used primitives in production are **tools** (model invokes a function) and **resources** (model reads data). Prompts are useful for discoverability — users see a menu of available actions. Roots and Sampling are less common but provide important safety (Roots) and capability extension (Sampling).

---

### The wire format, concretely

MCP messages are JSON-RPC 2.0. Here is what a typical exchange looks like:

```json
// Client → Server: discover available tools
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list"
}

// Server → Client: catalog of tools
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "search_docs",
        "description": "Search the documentation by keyword. Returns up to 5 matches.",
        "inputSchema": {
          "type": "object",
          "properties": {
            "query": {"type": "string", "description": "Search query"},
            "limit": {"type": "integer", "default": 5}
          },
          "required": ["query"]
        }
      },
      {
        "name": "create_ticket",
        "description": "Open a support ticket.",
        "inputSchema": {
          "type": "object",
          "properties": {
            "title": {"type": "string"},
            "body": {"type": "string"}
          },
          "required": ["title", "body"]
        }
      }
    ]
  }
}
```

Then a tool call:

```json
// Client → Server: invoke search_docs
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "search_docs",
    "arguments": {"query": "rate limiting", "limit": 3}
  }
}

// Server → Client: result
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [
      {"type": "text", "text": "Rate limiting protects against..."},
      {"type": "text", "text": "Token bucket algorithm..."},
      {"type": "text", "text": "Sliding window counter..."}
    ]
  }
}
```

The format is deliberately simple. Any language with a JSON parser can speak it. Any HTTP or stdio transport can carry it.

---

### Transports

MCP supports two main transports:

| Transport | When to use |
|---|---|
| **stdio** | Local servers run as child processes. The client communicates over stdin/stdout. Used by most reference servers. |
| **HTTP + Server-Sent Events** | Remote servers. The client sends requests via HTTP POST, receives responses via SSE. Used for cloud-hosted MCP servers. |
| **Streamable HTTP** | The newer standard that replaces HTTP+SSE for some use cases. Better for bidirectional streaming. |

For local development (Claude Desktop, Cursor, VS Code), stdio is the default. For production deployments with many agents connecting to a shared server, HTTP is the standard.

---

## Build It / In Depth

### Build a tiny MCP server in 30 lines

The official Python SDK makes this trivial:

```python
# weather_server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("weather-service")

@mcp.tool()
def get_weather(city: str) -> str:
    """Return the current weather for a city."""
    # In production, call a real weather API.
    return f"It is 72°F and sunny in {city}."

@mcp.resource("weather://{city}")
def weather_resource(city: str) -> str:
    """Get the weather as a readable resource."""
    return f"<weather><city>{city}</city><temp>72°F</temp></weather>"

if __name__ == "__main__":
    mcp.run()
```

Three lines define a tool, a resource, and the server entry point. Run it with `python weather_server.py` and any MCP-compatible client (Claude Desktop, Cursor, your custom agent) can connect.

---

### Connect an agent to the server

Using the official MCP client SDK with a LangGraph agent:

```python
import asyncio
from langgraph.prebuilt import create_react_agent
from langchain_mcp_adapters import load_mcp_tools
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    server_params = StdioServerParameters(
        command="python",
        args=["weather_server.py"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # This internally calls tools/list on the server
            tools = await load_mcp_tools(session)

            # The agent gets the tools as if they were local functions
            agent = create_react_agent(
                model="anthropic:claude-sonnet-4-5",
                tools=tools,
            )

            result = await agent.ainvoke({
                "messages": [("user", "What's the weather in Tokyo?")]
            })
            print(result)

asyncio.run(main())
```

The agent runtime does not know that `get_weather` is an MCP tool. It just sees a tool with a name, description, and schema. The MCP client transparently translates the agent's tool call into a JSON-RPC message, sends it to the server, and returns the result.

---

### What changes when you switch models

Without MCP, switching from Claude to GPT-4o might require rewriting tool-calling glue because each provider has a slightly different function-calling API. With MCP, the integration is identical:

```python
# Same MCP server, different model
agent_gpt = create_react_agent(model="openai:gpt-4o", tools=tools)
agent_claude = create_react_agent(model="anthropic:claude-sonnet-4-5", tools=tools)

# Both call get_weather the same way.
```

The server speaks MCP. Both clients speak MCP. The model is interchangeable.

---

### Reference servers worth knowing

The community maintains hundreds of MCP servers. The most useful reference set:

| Server | Purpose |
|---|---|
| `@modelcontextprotocol/server-filesystem` | Read/write files in a sandboxed directory |
| `@modelcontextprotocol/server-git` | Git operations (status, diff, commit, log) |
| `@modelcontextprotocol/server-github` | GitHub repos, issues, PRs, code search |
| `@modelcontextprotocol/server-postgres` | Read-only SQL queries against Postgres |
| `@modelcontextprotocol/server-slack` | Slack channels, messages, threads |
| `@modelcontextprotocol/server-puppeteer` | Browser automation |
| `@modelcontextprotocol/server-fetch` | HTTP fetch with HTML-to-Markdown conversion |
| `@modelcontextprotocol/server-memory` | Persistent note-taking across conversations |
| `@modelcontextprotocol/server-everything` | Reference implementation demonstrating all primitives |

These are open-source, maintained by Anthropic and the community, and can be installed in minutes.

---

## Use It

### When MCP is the right choice

| If you are… | Use MCP because… |
|---|---|
| Building an agent that needs many tools | One MCP server per tool, one client per server — no per-agent glue |
| Building multiple agents that share tools | Each MCP server is reusable across all agents |
| Integrating with GitHub, Slack, Postgres, etc. | Community-maintained MCP servers already exist |
| Building an IDE or developer tool that hosts agents | MCP is the de facto standard for tool integration |
| Standardizing agent infrastructure across teams | MCP gives a single contract across model providers |

### When MCP is overkill

- **A single agent calling a single internal API.** Write a function-calling wrapper directly. MCP adds process management and protocol overhead with no benefit.
- **Latency-critical paths.** MCP adds ~10–50 ms of overhead per call. For sub-100ms paths, in-process function calls are faster.
- **You need fine-grained transport control.** HTTP/REST gives you more knobs than MCP for things like HTTP/2 multiplexing, custom headers, or specific TLS settings.

### How MCP compares to alternatives

| Approach | Standardization | Cross-agent reuse | Setup cost |
|---|---|---|---|
| Custom function-calling wrapper per agent | None | No | Low |
| OpenAI function calling | OpenAI only | No | Low |
| Anthropic tool use | Anthropic only | No | Low |
| REST API + custom client | HTTP standard | Partial | Medium |
| **MCP** | **Open spec** | **Yes** | **Low–medium** |

MCP's value compounds as the number of agents and tools grows. One server, many agents.

---

## Common Pitfalls

- **Treating MCP as a replacement for APIs.** MCP is a wrapper layer. The underlying systems still need real APIs. You do not "MCP your database" — you write an MCP server that wraps your database client.

- **Mega-servers.** A single MCP server that exposes 80 tools is hard for the model to navigate. Split by domain: one server per service or per bounded context.

- **Ignoring authentication.** MCP servers must authenticate the agent and the user the agent acts on behalf of. Pass-through authentication to the underlying API; do not assume "the agent is trusted."

- **Vague tool descriptions.** The model picks tools based on their description string. A description like "user operations" is useless. Write descriptions like docstrings — specific, behavior-describing, example-including.

- **No version pinning.** MCP servers evolve. Pin the version in your client config, or accept that capability drift will break agents.

- **Assuming MCP solves prompt injection.** A malicious tool response can still manipulate the model. MCP provides structure; it does not provide security. Treat tool outputs as untrusted input.

- **Skipping stdio hygiene.** stdio servers communicate over stdin/stdout. Any debug print or stray log line will corrupt the JSON-RPC stream. Send all logs to stderr, not stdout.

---

## Exercises

1. **Easy** — In one sentence each, describe the three roles in MCP (host, client, server) and the three server-side primitives (tools, resources, prompts).

2. **Medium** — Build a tiny MCP server that exposes two tools: one that returns a static fact from a dictionary, one that calls a public API (e.g., OpenWeatherMap). Connect it to a Claude or LangGraph agent. Verify the agent can discover and call both tools.

3. **Hard** — Your company has 50 internal services, each with a REST API. You want to expose them as MCP servers for agents. Propose: how many MCP servers to build (one per service? one mega-server? grouped by domain?), how to handle authentication and authorization per user, how to version server capabilities without breaking agents, and how to handle the long tail of services that are rarely used.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| MCP | A new kind of API | A JSON-RPC-based open protocol for agent-to-tool communication; the server self-describes its capabilities, so the agent does not need external docs |
| JSON-RPC | A wire format | The lightweight remote procedure call format that MCP uses; simple JSON messages with a method name and parameters, easy to generate and parse in any language |
| Host | The agent | The AI application (Claude Desktop, Cursor, IDE, custom runtime) that runs MCP clients and orchestrates the user's interactions |
| MCP Client | The agent's tool dispatcher | A component inside the host that speaks MCP to one specific server; one client per server |
| MCP Server | An agent | A process that exposes tools, resources, and prompts over MCP; it does not reason, plan, or iterate — it responds to structured requests |
| Tools (MCP) | Function calling | Server-exposed functions with structured input schemas; the model invokes them by name with JSON arguments |
| Resources (MCP) | Read-only endpoints | Server-exposed data accessible by URI; the model fetches them, like a discoverable GET endpoint |
| Prompts (MCP) | System prompts | Server-exposed prompt templates the user can select from a menu; helps users discover capabilities without prompt engineering |

---

## Further Reading

- **Model Context Protocol Specification** — the canonical protocol documentation: https://modelcontextprotocol.io
- **MCP Python SDK** — the official Python implementation: https://github.com/modelcontextprotocol/python-sdk
- **MCP TypeScript SDK** — the official TypeScript implementation: https://github.com/modelcontextprotocol/typescript-sdk
- **Awesome MCP Servers** — a curated list of community-built servers: https://github.com/punkpeye/awesome-mcp-servers
- **"Building Agents with Model Context Protocol"** — Anthropic's guide to building MCP-aware agents: https://www.anthropic.com/news/model-context-protocol