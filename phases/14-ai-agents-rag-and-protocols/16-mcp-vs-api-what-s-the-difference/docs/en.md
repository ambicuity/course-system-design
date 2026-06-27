# MCP vs API: what's the difference?

> APIs are how software talks to software. MCP is how agents talk to software. Same goal, very different client.

**Type:** Learn
**Prerequisites:** What is an AI Agent?, Function Calling, REST/gRPC basics
**Time:** ~25 minutes

---

## The Problem

Every company on earth has spent twenty years building APIs. REST endpoints, GraphQL schemas, gRPC services — these are the contracts that let one piece of software call another. They work beautifully when the caller is a deterministic program written by an engineer who has read the docs.

AI agents are not deterministic programs. An agent decides at runtime which endpoint to call, with what arguments, in what order, based on a user prompt it has never seen before. That changes three things about the calling contract:

1. The agent needs to **discover** what endpoints exist and what they do — without reading 200 pages of API docs.
2. The agent needs **structured guidance** on when to call each endpoint, what arguments are valid, and what the response means.
3. The agent needs to **compose** calls across many services without writing custom glue code for every integration.

Traditional APIs do none of these well. They assume the caller is a human or a deterministic client. The Model Context Protocol (MCP) is an attempt to fix that — to build an API standard that *targets agents as first-class clients*. This lesson explains what MCP actually is, how it differs from a traditional API, and when each one is the right choice.

---

## The Concept

### What an API actually does

An API is a contract between two software systems. The contract defines endpoints, request formats, and response formats. The caller knows the contract ahead of time (from documentation, code generation, or type definitions) and makes HTTP calls accordingly.

```
   Caller (engineer wrote this)
          │
          │  GET /v1/users/42
          │  Authorization: Bearer xxx
          ▼
   ┌────────────────────────────┐
   │   API server (REST/GraphQL)│
   │   - validates request      │
   │   - runs business logic    │
   │   - returns JSON           │
   └────────────────────────────┘
          │
          │  200 OK { "id": 42, "name": "Alex" }
          ▼
   Caller (parses response, handles errors)
```

Properties of a traditional API:

- **Caller is known.** The team that built the caller is identified, versioned, and tracked.
- **Contract is documented.** Swagger / OpenAPI / Postman collections / gRPC proto files describe every endpoint.
- **Transport is HTTP (usually).** REST over HTTPS, with standard status codes.
- **Authentication is identity-based.** API keys, OAuth tokens, mTLS — the caller proves *who it is*.
- **Variability is bounded.** The contract is a fixed schema. If you need a new field, you ship v2.

This contract model is excellent when the caller is deterministic software. It is awkward when the caller is a non-deterministic model.

---

### What an MCP server actually does

An MCP server is a process that exposes **tools**, **resources**, and **prompts** to any MCP-compatible client. The server self-describes what it offers — the client does not need external documentation to discover what is available.

```
   MCP Client (Claude, IDE, agent runtime)
          │
          │  tools/list  ──────►  "I have these 5 tools"
          │  ◄──────────────  [ {name, description, schema}, ... ]
          │
          │  tools/call   ──────►  get_user(id=42)
          │  ◄──────────────  { "id": 42, "name": "Alex" }
          │
   ┌────────────────────────────┐
   │   MCP Server               │
   │   - advertises capabilities│
   │   - validates arguments    │
   │   - returns structured     │
   │     responses              │
   └────────────────────────────┘
```

The Model Context Protocol is JSON-RPC based. It defines three primitives:

| Primitive | What it represents | Example |
|---|---|---|
| **Tools** | Functions the model can invoke (like function calling) | `search_docs(query)`, `create_ticket(title, body)` |
| **Resources** | Read-only data the model can fetch (like GET endpoints) | `file:///docs/handbook.md`, `db://users/42` |
| **Prompts** | Pre-built prompt templates the user can choose from | "Summarize this document", "Explain this code" |

The server advertises all three. The client (an agent) learns what is available by calling `tools/list` once, then invokes specific tools by name with structured arguments.

---

### The discovery problem

This is the single biggest practical difference between APIs and MCP. Look at what each requires of the caller.

**Traditional API:**

```
   1. Engineer reads Swagger docs at https://api.example.com/docs
   2. Engineer identifies the right endpoint
   3. Engineer writes code: requests.get("/v1/users/{id}", headers=...)
   4. Engineer handles auth, retries, pagination, errors
   5. Application ships
   6. API changes → engineer updates code
```

**MCP server:**

```
   1. Agent connects to MCP server at startup
   2. Agent calls tools/list — receives the catalog
   3. Agent decides which tool fits the user's request
   4. Agent calls tools/call with structured arguments
   5. Agent formats the response for the user
   6. Server changes → agent re-calls tools/list and adapts
```

The MCP model assumes the caller is an LLM that does not read documentation. The server must *tell* the model what it can do, in a format the model can parse and act on. That is the core of the protocol.

---

### What they share and what they don't

| Dimension | API (REST/GraphQL/gRPC) | MCP |
|---|---|---|
| Purpose | Software-to-software communication | Agent-to-software communication |
| Caller | Deterministic program written by an engineer | LLM-driven agent, chosen at runtime |
| Discovery | External documentation (Swagger, OpenAPI, Proto) | Self-describing (`tools/list`, `resources/list`) |
| Contract format | Schema files (OpenAPI, GraphQL SDL, Proto) | JSON-RPC method definitions returned by server |
| Standardization | Many flavors (REST, GraphQL, gRPC, SOAP…) | One uniform protocol |
| Authentication | API keys, OAuth, mTLS — proves caller identity | OAuth / API keys — often scoped to the end user |
| Argument validation | Server validates request body | Server validates arguments against the tool schema |
| Response format | JSON, Protobuf, XML — caller parses it | Structured content (text, JSON, images) — model parses it |
| Versioning | /v1, /v2 paths; semantic versioning of the schema | Tools are versioned individually; clients adapt by re-listing |
| Error handling | HTTP status codes (200, 4xx, 5xx); caller codes switch on status | JSON-RPC error codes + structured error messages the model can read |
| Best fit | Service-to-service, frontend-to-backend, mobile clients | Agent workflows, IDE integrations, LLM tool use |
| Maturity | Decades of tooling, observability, governance | Months/years old, ecosystem still growing |

---

### They are not competitors

MCP does not replace APIs. It sits *on top* of them.

```
   ┌──────────────────────────────────────┐
   │  AI Agent (Claude, IDE, custom)      │
   └────────────────┬─────────────────────┘
                    │ speaks MCP
                    ▼
   ┌──────────────────────────────────────┐
   │  MCP Server                          │
   │  - exposes tools/resources/prompts   │
   │  - translates MCP calls to API calls │
   └────────────────┬─────────────────────┘
                    │ speaks HTTP, REST, GraphQL, gRPC
                    ▼
   ┌──────────────────────────────────────┐
   │  Underlying API / database / system  │
   └──────────────────────────────────────┘
```

The MCP server is typically a thin wrapper that:

1. Advertises the capabilities of the underlying system as MCP tools.
2. Receives `tools/call` requests from the agent.
3. Translates them into HTTP calls to the existing API.
4. Returns structured responses the model can reason about.

This means every API you already have can become MCP-compatible by writing a small server in front of it. You do not rewrite your backend. You add a layer that speaks the protocol the agent expects.

---

### When to use which

```
                     Is the caller a human
                     or deterministic code?
                              │
                  YES ────────┴──────── NO
                   │                     │
                   ▼                     ▼
                API              Is the caller an
              (proven,           LLM-driven agent?
              standard)                  │
                              YES ───────┴────── NO
                               │                │
                               ▼                ▼
                            MCP             Either works;
                          (built for        pick what your
                          this case)       team can ship fastest
```

In practice: ship an API first. Add an MCP server in front of it when an agent becomes a real consumer. Most teams will end up with both — APIs for the deterministic services, MCP servers wrapping the same APIs for agent consumers.

---

## Build It / In Depth

### Worked example: A "get user" endpoint

**Traditional API (REST):**

```http
GET /v1/users/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer xxx
```

```json
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 42,
  "name": "Alex",
  "email": "alex@example.com",
  "role": "admin"
}
```

Caller behavior: an engineer wrote this code; it knows the path, the auth header format, and how to parse the JSON.

**Equivalent MCP server (Python, using the official SDK):**

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("user-service")

@mcp.tool()
def get_user(user_id: int) -> dict:
    """Look up a user by their numeric ID. Returns name, email, and role."""
    # Internally, this calls the existing REST API.
    response = requests.get(
        f"https://api.example.com/v1/users/{user_id}",
        headers={"Authorization": f"Bearer {API_TOKEN}"},
    )
    response.raise_for_status()
    return response.json()

if __name__ == "__main__":
    mcp.run()
```

The MCP server is ~15 lines. It wraps the existing API. It advertises the `get_user` tool with a description that the model can read. When an agent connects, it learns about this tool without reading any docs.

When the agent calls it:

```json
// Agent → MCP server
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "get_user",
    "arguments": { "user_id": 42 }
  }
}

// MCP server → Agent
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      { "type": "text", "text": "{\"id\": 42, \"name\": \"Alex\", ...}" }
    ]
  }
}
```

The agent receives the structured response and uses it in its reasoning.

---

### Worked example: Adding a resource

MCP supports read-only resources in addition to tools. A resource is anything the model can *fetch* but not *invoke* — like a file or a record.

```python
@mcp.resource("file:///docs/{path}")
def read_doc(path: str) -> str:
    """Read a document from the docs/ directory."""
    with open(f"docs/{path}") as f:
        return f.read()
```

The agent can now list available resources (`resources/list`), see URIs like `file:///docs/handbook.md`, and read them on demand. This is the MCP equivalent of a `GET` endpoint with a discoverable catalog.

---

### Where MCP earns its keep

Three concrete wins over writing custom function-calling glue for every API:

1. **One integration per service, many agents.** Write the MCP server once. Every MCP-compatible agent (Claude, Cursor, custom LangGraph agent, OpenAI agents with MCP support) can use it without additional code.

2. **No prompt engineering to describe tools.** The MCP server publishes the tool name, description, and argument schema. The agent reads them at runtime. You do not paste JSON schemas into system prompts.

3. **Dynamic capability.** When you add a new tool to the MCP server, every connected agent sees it on the next `tools/list` call. No code changes on the agent side, no new releases.

---

## Use It

### When to build an MCP server

| If you have… | Consider MCP because… |
|---|---|
| An existing REST API that agents will call | One MCP server wraps the API once; every agent can use it |
| Multiple internal tools an agent needs (Slack, Jira, GitHub, DB) | MCP standardizes how the agent discovers and calls them |
| An IDE integration (Cursor, Claude Code, etc.) | MCP is the protocol those tools support natively |
| A team building agent infrastructure | MCP gives you a single integration contract across model providers |
| A service only deterministic code will ever call | An API is simpler — MCP adds overhead with no benefit |

### MCP servers worth knowing

| Server | What it exposes |
|---|---|
| `@modelcontextprotocol/server-filesystem` | Read/write files in a sandboxed directory |
| `@modelcontextprotocol/server-github` | Repos, issues, PRs, code search |
| `@modelcontextprotocol/server-postgres` | Read-only SQL queries against a Postgres DB |
| `@modelcontextprotocol/server-slack` | Channels, messages, threads |
| `@modelcontextprotocol/server-puppeteer` | Browser automation |
| `@modelcontextprotocol/server-google-drive` | Drive files, sharing, search |
| `@modelcontextprotocol/server-git` | Git operations (status, diff, commit, log) |
| `@modelcontextprotocol/server-memory` | Persistent note-taking across conversations |
| `@modelcontextprotocol/server-fetch` | HTTP fetch with HTML→Markdown conversion |
| `@modelcontextprotocol/server-everything` | Demo / reference implementation |

These are official reference servers maintained by Anthropic and the community. Most can be installed and configured in under five minutes.

### When APIs are still the right answer

- Your caller is a frontend, mobile app, or backend service written by an engineer.
- You need strict typed contracts enforced by code generation (gRPC, OpenAPI generators).
- You operate at scale and need API gateway features (rate limiting, analytics, monetization).
- Your caller does not benefit from self-description because it is hard-coded.
- You have regulatory or compliance constraints (auditing, scoping) that govern the API layer directly.

---

## Common Pitfalls

- **Treating MCP as a replacement for APIs.** MCP is a wrapper layer, not a substitute. The underlying systems still need real APIs. Plan for both.

- **Building a custom integration instead of checking for MCP first.** Before writing function-calling glue for GitHub, Slack, Postgres, etc., check if an MCP server already exists. The community maintains hundreds.

- **Exposing too much through one MCP server.** A single mega-server with 80 tools is hard for the model to navigate. Split by domain (one server per service, or one server per bounded context).

- **Ignoring authentication.** MCP servers must authenticate the agent and the user the agent acts on behalf of. Pass-through authentication to the underlying API; do not assume "the agent is trusted."

- **Treating tool descriptions as throwaway.** The model picks which tool to call based on the description string. A vague description ("user operations") means the model will not reliably pick the right tool. Write descriptions like docstrings — specific, behavior-describing, example-including.

- **No version pinning.** MCP servers evolve. Pin the server version your agent connects to, or accept that capability drift will break agents in production.

- **Assuming MCP solves prompt injection.** A malicious response from a tool can still manipulate the model. MCP gives structure; it does not give security. Treat tool outputs the same way you treat any user input.

---

## Exercises

1. **Easy** — Pick a public API you have used before (e.g., GitHub, Stripe, OpenWeather). Sketch the MCP server you would write to expose one of its endpoints as a tool. What would the tool name, description, and arguments be?

2. **Medium** — You have three internal services: a CRM (REST), a ticketing system (GraphQL), and a metrics store (gRPC). Each will be called by an internal agent. Design the MCP layer: how many MCP servers, what tools each exposes, how authentication is handled. Justify the boundaries.

3. **Hard** — Your company's API has grown organically over five years. There are 200 endpoints across 12 services, with inconsistent auth, overlapping functionality, and stale documentation. The CTO wants to "add MCP" so the new AI assistant can use everything. Propose a phased rollout that does not require rewriting all 200 endpoints at once. Address: which endpoints to wrap first, how to handle the long tail, how to prevent the MCP layer from becoming another source of undocumented behavior, and how to keep the agent from getting overwhelmed by too many tools.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| API | The only way software talks to software | A family of contract styles (REST, GraphQL, gRPC, SOAP) for software-to-software communication; assumes the caller is deterministic and was written by an engineer who read the docs |
| MCP | A new kind of API | A JSON-RPC-based protocol designed for agent-to-software communication; the server self-describes its capabilities so the model does not need external docs |
| Tools (MCP) | Just like function calling | A standardized form of function calling exposed via MCP — the model calls `tools/list` to discover what's available, then `tools/call` to invoke; works across MCP-compatible agents without per-agent glue code |
| Resources (MCP) | Files for the model | Read-only data exposed by the server via URIs (e.g., `file:///docs/x.md`, `db://users/42`); the agent fetches them by URI, like a discoverable `GET` endpoint |
| Prompts (MCP) | System prompts | Pre-built prompt templates the user can select from a menu (e.g., "Summarize this doc"); helps users discover capabilities without prompt engineering |
| Discovery | An API has docs | MCP servers return their capability catalog on demand via `tools/list` and `resources/list`; agents adapt to changes without code updates |
| JSON-RPC | A wire format | The transport underneath MCP; lightweight, language-agnostic, and well-suited to model tool calls because the request and response are simple JSON the model can parse and produce |
| Authentication | Same as APIs | The agent proves its identity (and often the end user's identity) to the MCP server; the server then passes those credentials through to the underlying API; OAuth and API keys are common |

---

## Further Reading

- **Model Context Protocol Specification** — the canonical protocol docs from Anthropic and the open-source community: https://modelcontextprotocol.io
- **MCP Python SDK** — the official Python implementation for building MCP servers and clients: https://github.com/modelcontextprotocol/python-sdk
- **"APIs Are for Humans. MCP Is for Agents."** — a practitioner's framing of why agents need a different contract than deterministic clients: https://www.latent.space/p/mcp
- **Awesome MCP Servers** — a curated list of community-built MCP servers for GitHub, Slack, Postgres, browsers, and dozens more: https://github.com/punkpeye/awesome-mcp-servers
- **OpenAPI Specification** — the dominant API description standard; MCP complements it for agent consumers, does not replace it: https://swagger.io/specification/