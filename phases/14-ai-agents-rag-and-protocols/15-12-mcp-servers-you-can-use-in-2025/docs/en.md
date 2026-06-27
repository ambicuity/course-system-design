# 12 MCP Servers You Can Use in 2025

> A curated starter set — install one of these, point your IDE or agent at it, and ship something useful today.

**Type:** Learn
**Prerequisites:** What is MCP?, How to run a local MCP server
**Time:** ~20 minutes

---

## The Problem

You have read about MCP, you understand the protocol, you are convinced it is useful — now you want to actually try it. The ecosystem has hundreds of servers, scattered across GitHub, npm, and PyPI. Picking which one to install first is friction. Setting each one up correctly is more friction. Knowing what is safe to run with broad permissions is yet more friction.

This lesson gives you a curated shortlist of twelve MCP servers that cover the most common use cases in 2025: filesystem access, code repositories, communication tools, databases, search, and AI-specific integrations. For each, you get a description, what it can do, installation steps, and a concrete use case. By the end of this lesson you should be able to install three or four of these and have a working agent doing real work.

The list is curated for breadth, not completeness. There are hundreds more; these twelve are the ones most teams install first.

---

## The Concept

### How to use this list

Each entry follows the same structure:

- **What it does** — one sentence on the capability.
- **Why it is on the list** — the common use case.
- **Install** — the exact command to add it to Claude Desktop or Cursor (the two most common hosts).
- **Sample tools** — what tools the server exposes.
- **Caveat** — one thing to watch out for.

To install any of these in Claude Desktop, edit your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "<server-name>": {
      "command": "npx",
      "args": ["-y", "<package-name>", "<args>"]
    }
  }
}
```

Restart Claude Desktop after editing. The tools will appear automatically.

---

### 1. File System MCP Server

**What it does:** Gives the agent direct, sandboxed access to the local file system.

**Why it is on the list:** The single most useful server for general-purpose coding and document work. Read files, write files, create directories, list contents — all within a directory you specify.

**Install:**
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/you/projects"]
    }
  }
}
```

The trailing path is the *root* — the agent can only access files under that directory.

**Sample tools:** `read_file`, `write_file`, `list_directory`, `create_directory`, `move_file`, `search_files`.

**Use case:** "Read the README, fix the typo in the second paragraph, and update the version number in package.json."

**Caveat:** Always restrict the root directory. Without it, the agent can read any file your user can read — including `~/.ssh/id_rsa`.

---

### 2. GitHub MCP Server

**What it does:** Connects the agent to GitHub — repos, issues, PRs, code search, file contents.

**Why it is on the list:** Every engineering team uses GitHub. This server turns any agent into a GitHub assistant.

**Install:**
```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_..."
      }
    }
  }
}
```

You need a GitHub personal access token with appropriate scopes (`repo`, `read:org`, etc.).

**Sample tools:** `search_repositories`, `get_file_contents`, `create_issue`, `create_pull_request`, `list_issues`, `search_code`, `get_commit`.

**Use case:** "Find all open issues labeled 'bug' in the last week and summarize the top three by comment count."

**Caveat:** The token's permissions are the agent's permissions. Use a fine-grained token with only the scopes you need. Rotate quarterly.

---

### 3. Slack MCP Server

**What it does:** Connects the agent to Slack — channels, messages, threads, search.

**Why it is on the list:** A huge amount of team context lives in Slack. Letting the agent search and read it makes it useful for triage, summarization, and incident response.

**Install:**
```json
{
  "mcpServers": {
    "slack": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-slack"],
      "env": {
        "SLACK_BOT_TOKEN": "xoxb-...",
        "SLACK_TEAM_ID": "T01234"
      }
    }
  }
}
```

You need a Slack bot token with the right OAuth scopes.

**Sample tools:** `list_channels`, `post_message`, `reply_to_thread`, `get_channel_history`, `search_messages`, `add_reaction`.

**Use case:** "Find the latest message in #incidents about the database outage and summarize the resolution."

**Caveat:** Read-only scopes by default. Add `chat:write` only if you intend to let the agent post. Most teams start read-only.

---

### 4. Google Maps MCP Server

**What it does:** Connects the agent to the Google Maps API for geocoding, directions, places, distance matrix.

**Why it is on the list:** Geospatial questions come up constantly in logistics, real estate, and travel planning. The Maps API is the canonical answer.

**Install:**
```json
{
  "mcpServers": {
    "google-maps": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-google-maps"],
      "env": {
        "GOOGLE_MAPS_API_KEY": "AIza..."
      }
    }
  }
}
```

**Sample tools:** `maps_geocode`, `maps_reverse_geocode`, `maps_search_places`, `maps_directions`, `maps_distance_matrix`, `maps_elevation`.

**Use case:** "Find coffee shops within walking distance of the office and rank by rating."

**Caveat:** Google Maps API is pay-per-call. Set usage limits on the API key to avoid surprise bills.

---

### 5. Docker MCP Server

**What it does:** Connects the agent to the local Docker daemon — containers, images, volumes, networks.

**Why it is on the list:** DevOps workflows revolve around Docker. Letting the agent manage containers turns "kubectl" into natural language.

**Install:**
```json
{
  "mcpServers": {
    "docker": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-docker"],
      "env": {
        "DOCKER_HOST": "unix:///var/run/docker.sock"
      }
    }
  }
}
```

**Sample tools:** `list_containers`, `create_container`, `start_container`, `stop_container`, `list_images`, `pull_image`, `logs`.

**Use case:** "Find all containers using more than 1 GB of memory and restart them."

**Caveat:** Mounting the Docker socket gives the agent root-equivalent access to the host. Run in a sandboxed environment, not on your production laptop.

---

### 6. Brave Search MCP Server

**What it does:** Web and local search via the Brave Search API.

**Why it is on the list:** Agents need to look things up. Brave Search is privacy-respecting, fast, and has a clean API.

**Install:**
```json
{
  "mcpServers": {
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": {
        "BRAVE_API_KEY": "BSA..."
      }
    }
  }
}
```

**Sample tools:** `brave_web_search`, `brave_local_search`, `brave_news_search`, `brave_image_search`, `brave_video_search`.

**Use case:** "What's the latest research on retrieval-augmented generation from this week?"

**Caveat:** The free tier is 2,000 queries/month. For production agents, expect to pay for the paid tier quickly.

---

### 7. PostgreSQL MCP Server

**What it does:** Connects the agent to a Postgres database — schema inspection, read-only queries.

**Why it is on the list:** Most production data lives in Postgres. Letting agents query it (safely) unlocks a huge range of analytics use cases.

**Install:**
```json
{
  "mcpServers": {
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://user:pass@localhost:5432/db"]
    }
  }
}
```

**Sample tools:** `list_tables`, `describe_table`, `execute_readonly_query`, `get_schema`.

**Use case:** "How many users signed up last week, broken down by referral source?"

**Caveat:** This server is read-only by design. Do not configure it with a write-capable connection. For write access, build a separate server with explicit, narrow tool definitions.

---

### 8. Google Drive MCP Server

**What it does:** Connects the agent to Google Drive — files, folders, sharing, search.

**Why it is on the list:** A surprising amount of business content lives in Drive. Letting agents read it (with appropriate scopes) is high-leverage.

**Install:**
```json
{
  "mcpServers": {
    "google-drive": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-google-drive"],
      "env": {
        "GOOGLE_CLIENT_ID": "...",
        "GOOGLE_CLIENT_SECRET": "...",
        "GOOGLE_REFRESH_TOKEN": "..."
      }
    }
  }
}
```

**Sample tools:** `search_files`, `get_file_content`, `list_folder`, `create_file`, `share_file`.

**Use case:** "Find the latest Q3 planning doc in the Strategy folder and summarize the key decisions."

**Caveat:** OAuth setup is heavier than API-key servers. Use a service account for production agents, not personal credentials.

---

### 9. Redis MCP Server

**What it does:** Connects the agent to Redis — keys, hashes, lists, sets, pub/sub.

**Why it is on the list:** Redis is everywhere — caches, queues, leaderboards, session stores. Letting agents inspect and query it makes debugging faster.

**Install:**
```json
{
  "mcpServers": {
    "redis": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-redis"],
      "env": {
        "REDIS_URL": "redis://localhost:6379"
      }
    }
  }
}
```

**Sample tools:** `get`, `set`, `del`, `keys`, `hget`, `hset`, `lpush`, `lrange`, `publish`.

**Use case:** "Inspect the cache for the user profile endpoint — what keys exist, what's the hit rate?"

**Caveat:** Redis commands can do destructive things (FLUSHALL, KEYS *) instantly. Restrict the server to a logically separate Redis instance or use ACLs.

---

### 10. Notion MCP Server

**What it does:** Connects the agent to Notion — pages, databases, blocks, search.

**Why it is on the list:** Many teams use Notion as their internal knowledge base. Letting agents query and update it is a 10× productivity boost for documentation work.

**Install:**
```json
{
  "mcpServers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-notion"],
      "env": {
        "NOTION_API_KEY": "secret_..."
      }
    }
  }
}
```

**Sample tools:** `search_pages`, `get_page`, `create_page`, `update_page`, `query_database`, `get_block_children`.

**Use case:** "Find all onboarding docs for new engineers and create a checklist from them."

**Caveat:** Notion's data model is rich (databases, relations, formulas). The server exposes the basics but not every feature. Complex Notion queries may need a custom server.

---

### 11. Stripe MCP Server

**What it does:** Connects the agent to Stripe — customers, payments, subscriptions, invoices.

**Why it is on the list:** Finance and operations teams need to answer billing questions. Letting an agent query Stripe (read-only by default) is high-value.

**Install:**
```json
{
  "mcpServers": {
    "stripe": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-stripe"],
      "env": {
        "STRIPE_API_KEY": "sk_..."
      }
    }
  }
}
```

**Sample tools:** `list_customers`, `get_customer`, `list_charges`, `create_refund`, `list_subscriptions`, `list_invoices`.

**Use case:** "Show me all failed payments this month with the customer email and amount."

**Caveat:** Use a restricted API key with read-only scopes for analytics use cases. Never give an agent write access to billing data without a human-in-the-loop.

---

### 12. Perplexity MCP Server

**What it does:** Connects the agent to the Perplexity Sonar API for real-time, citation-backed web search.

**Why it is on the list:** Perplexity returns synthesized answers with citations, not just a list of links. For research tasks, it is more useful than raw search.

**Install:**
```json
{
  "mcpServers": {
    "perplexity": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-perplexity"],
      "env": {
        "PERPLEXITY_API_KEY": "pplx-..."
      }
    }
  }
}
```

**Sample tools:** `perplexity_search`, `perplexity_research`, `perplexity_reason`.

**Use case:** "What are the most recent papers on long-context LLMs from this month?"

**Caveat:** Perplexity costs per query. Set rate limits and budget alerts. Cache results for repeated queries.

---

## Use It

### Which to install first

| If you are… | Start with |
|---|---|
| A developer using Claude Code or Cursor | **filesystem**, **github**, **postgres** |
| A data analyst | **postgres**, **brave-search**, **perplexity** |
| A finance / ops person | **stripe**, **google-drive**, **notion** |
| A DevOps engineer | **docker**, **github**, **slack** |
| A researcher | **perplexity**, **brave-search**, **google-drive** |
| Building a customer support agent | **slack**, **notion**, **github**, **postgres** |

### Installation recipe

For Claude Desktop, edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%/Claude/claude_desktop_config.json` (Windows).

For Cursor, edit `.cursor/mcp.json` in your project or user settings.

For VS Code with the Continue extension, configure in `.continue/config.json`.

### Security checklist before turning an agent loose

- [ ] Each server runs with the **minimum credentials** required.
- [ ] Each filesystem root is **scoped to a directory**.
- [ ] Each database connection is **read-only** unless writes are explicitly intended.
- [ ] Each API token has **rate limits** set.
- [ ] Each server is **version-pinned** (no `latest` tags in production).
- [ ] Each action that touches production data goes through a **human-in-the-loop** approval.
- [ ] Each server's logs are sent to a **centralized observability** stack.

---

## Common Pitfalls

- **Installing too many at once.** Start with three servers. Add more when you have a concrete use case. Each server is another surface to monitor and secure.

- **Using personal API tokens in agent config.** Tokens in `claude_desktop_config.json` are visible to anything running as your user. Use service accounts with restricted scopes for production.

- **Assuming the server is safe to run with full credentials.** Most reference servers are minimal implementations. They do exactly what the tool says, but they do not add authorization, audit logging, or rate limiting. Add those layers if you need them.

- **Skipping the root directory.** The filesystem server with no root argument can read any file. Always set the root.

- **Not version-pinning.** `"@modelcontextprotocol/server-filesystem@latest"` will silently upgrade. Pin to a specific version for reproducibility.

- **Ignoring cost.** Search APIs (Brave, Perplexity) and Maps APIs cost per query. A loop that calls them 100 times per request will ruin your week. Set budgets.

- **Treating MCP servers as production-ready.** Most are reference implementations maintained by the community. For production, audit the code, add tests, deploy behind your auth layer, and monitor.

---

## Exercises

1. **Easy** — Pick two servers from the list. For each, write one paragraph explaining what problem it solves and when you would install it.

2. **Medium** — Install three servers from this list in Claude Desktop or Cursor. Run a real task that uses all three (e.g., "Find the README in my project, summarize it, and post the summary to Slack"). Note where the integration breaks down and what would make it better.

3. **Hard** — Your team is building a customer support agent. You want it to read internal docs (Notion), check ticket history (Postgres), look up customer info (Stripe), and search for known issues (GitHub). Design the MCP configuration: which servers, what credentials, what scopes, how you enforce per-user authorization, and how you audit every tool call.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Reference server | A production-ready MCP server | A minimal, community-maintained implementation that demonstrates the protocol; usually safe for development but should be audited before production use |
| Host | The MCP server | The AI application (Claude Desktop, Cursor, IDE, custom runtime) that runs the MCP client and orchestrates user interactions |
| MCP server | An agent | A process that exposes tools, resources, and prompts over the MCP protocol; it does not reason or act, it responds to structured requests |
| stdio transport | The only way to run MCP | A local-server pattern where the server runs as a child process and communicates over stdin/stdout; the default for IDE integrations |
| HTTP+SSE transport | stdio for production | A remote-server pattern where the client sends requests via HTTP POST and receives responses via Server-Sent Events; used for cloud-hosted MCP servers |
| Fine-grained token | A regular API token | A GitHub / Google / Slack token with restricted scopes (e.g., read-only on a single repo); the only safe default for agent credentials |
| Service account | A user account | A non-human identity (in Google Cloud, AWS, etc.) used by automated systems; preferred over personal accounts for any agent that runs unattended |
| MCP config | A settings file | A JSON file (`claude_desktop_config.json`, `.cursor/mcp.json`, etc.) that lists the servers the host should connect to and their credentials |

---

## Further Reading

- **Awesome MCP Servers** — a curated, regularly updated list of community MCP servers: https://github.com/punkpeye/awesome-mcp-servers
- **Model Context Protocol Specification** — the canonical protocol docs: https://modelcontextprotocol.io
- **MCP Servers (Official)** — Anthropic's reference implementations: https://github.com/modelcontextprotocol/servers
- **Claude Desktop MCP Setup Guide** — Anthropic's official walkthrough for connecting servers: https://docs.anthropic.com/en/docs/agents-and-tools/mcp
- **MCP Security Best Practices** — Anthropic's guide on credentials, scoping, and audit: https://modelcontextprotocol.io/docs/concepts/security