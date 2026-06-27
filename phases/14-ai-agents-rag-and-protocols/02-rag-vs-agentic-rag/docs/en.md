# RAG vs Agentic RAG

> Retrieval gives an LLM memory; agency gives it judgment about what to retrieve and when.

**Type:** Learn
**Prerequisites:** Large Language Model Fundamentals, Vector Databases, AI Agents Overview
**Time:** ~35 minutes

---

## The Problem

A product team ships a customer-support chatbot backed by a vector database of 50,000 support articles. For straightforward questions—"How do I reset my password?"—the bot performs well: embed the question, fetch the top-3 chunks, stuff them into the prompt, return the answer. Accuracy is ~85% and latency is under one second. The team declares success.

Then real users arrive. A user asks: "I bought the Pro plan last Tuesday, upgraded storage yesterday, and now my sync is broken on the Android app only—but not on iOS. Is this a known issue?" A single vector search cannot satisfy this. The answer requires correlating a recent subscription-change event with a platform-specific bug report and the user's account tier. Standard RAG retrieves chunks about sync generally, misses the plan-upgrade edge case entirely, and confidently generates a wrong answer.

More broadly: traditional RAG treats retrieval as a one-shot reflex—embed, search, generate. It cannot pause mid-generation to realize its retrieved context is wrong, issue a follow-up query, call an external API, or chain multiple lookups. The moment your question requires reasoning *about* what to look up, or *whether* one retrieval is enough, single-pass RAG becomes a liability. Agentic RAG solves exactly this by placing an autonomous planning loop around retrieval.

---

## The Concept

### Traditional RAG

The pipeline is linear and stateless:

```
User Query
    │
    ▼
[ Embed query ]
    │
    ▼
[ Vector DB similarity search ] ──► top-k chunks
    │
    ▼
[ Assemble prompt: system + chunks + query ]
    │
    ▼
[ LLM generates answer ]
    │
    ▼
Response
```

Retrieval happens exactly once. The LLM receives a frozen context window and has no mechanism to say "I need more" or "these chunks are contradictory." This is fast and cheap, but the ceiling is low.

### Agentic RAG

An AI agent sits between the user and the retrieval infrastructure. The agent owns the reasoning loop:

```
User Query
    │
    ▼
┌───────────────────────────────────────────────┐
│                  AI Agent                     │
│                                               │
│  ┌──────────┐    ┌─────────────────────────┐  │
│  │ Planning │───►│  Tool Selection         │  │
│  │ (chain-  │    │  • vector_search()      │  │
│  │  of-     │    │  • keyword_search()     │  │
│  │  thought)│    │  • api_call()           │  │
│  └──────────┘    │  • sub_agent_spawn()    │  │
│       ▲          └──────────┬──────────────┘  │
│       │                     │                 │
│  ┌────┴──────┐   ┌──────────▼──────────────┐  │
│  │ Evaluate  │◄──│  Execute & Observe       │  │
│  │ result    │   │  (retrieval results)     │  │
│  └────┬──────┘   └─────────────────────────┘  │
│       │ (enough context?)                     │
│       │ No ──► plan next action               │
│       │ Yes ──► synthesize                    │
└───────┼───────────────────────────────────────┘
        ▼
  Final Response (+ citations, confidence)
```

The agent maintains **short-term memory** (the current task's scratchpad—retrieved chunks, intermediate conclusions) and can access **long-term memory** (user preferences, prior session context) to inform its retrieval strategy. It iterates until it judges the context sufficient, then calls the LLM for synthesis.

### Side-by-Side Comparison

| Dimension | Traditional RAG | Agentic RAG |
|---|---|---|
| Retrieval count | Fixed: one pass | Dynamic: 1–N passes |
| Query reformulation | None | Agent rewrites queries mid-loop |
| Tool diversity | Vector search only | Vector, keyword, SQL, APIs, sub-agents |
| Memory | None between calls | Short-term scratchpad + optional long-term store |
| Latency | Low (~200–800 ms) | Higher (1–10 s per hop) |
| Cost | Low (1 LLM call) | Higher (multiple LLM calls per turn) |
| Failure mode | Silent wrong retrieval | Agent loop divergence or over-retrieval |
| Best for | Single-hop factual Q&A | Multi-hop, ambiguous, real-time queries |

### How the Agent Decides When to Stop

Agentic RAG typically uses one of three stopping strategies:

1. **Fixed-budget**: stop after at most N retrieval steps (simple, predictable cost).
2. **Confidence-threshold**: the agent's LLM self-evaluates context sufficiency in a structured output field before synthesis.
3. **Reflection step**: a separate "critic" call checks whether the retrieved evidence logically supports answering the original question.

The reflection approach delivers the highest accuracy but nearly doubles token cost per turn.

---

## Build It / In Depth

### Traditional RAG in 30 Lines

```python
from openai import OpenAI
import numpy as np

client = OpenAI()
DOCS = [
    "Password reset: visit account settings and click 'Forgot password'.",
    "Pro plan includes 100 GB storage and priority support.",
    "Android sync issues on v4.2.1 have been resolved in v4.2.2.",
]

def embed(text: str) -> list[float]:
    return client.embeddings.create(
        input=text, model="text-embedding-3-small"
    ).data[0].embedding

# Pre-index (done once, stored in a real vector DB in production)
doc_embeddings = [embed(d) for d in DOCS]

def cosine(a, b):
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

def rag(query: str, top_k: int = 2) -> str:
    q_emb = embed(query)
    ranked = sorted(range(len(DOCS)),
                    key=lambda i: cosine(q_emb, doc_embeddings[i]),
                    reverse=True)
    context = "\n".join(DOCS[i] for i in ranked[:top_k])
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": f"Answer using only this context:\n{context}"},
            {"role": "user", "content": query},
        ],
    )
    return response.choices[0].message.content
```

This handles single-hop questions correctly. Ask "How do I reset my password?" and it works. Ask "Is the sync issue fixed if I'm on the Pro plan?" and it retrieves sync docs OR Pro plan docs—not both—and hallucinates the join.

### Agentic RAG: Adding the Planning Loop

```python
import json

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "vector_search",
            "description": "Search the knowledge base for relevant chunks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query string"},
                    "top_k": {"type": "integer", "default": 3}
                },
                "required": ["query"]
            }
        }
    }
]

def vector_search(query: str, top_k: int = 3) -> list[str]:
    q_emb = embed(query)
    ranked = sorted(range(len(DOCS)),
                    key=lambda i: cosine(q_emb, doc_embeddings[i]),
                    reverse=True)
    return [DOCS[i] for i in ranked[:top_k]]

def agentic_rag(user_query: str, max_hops: int = 4) -> str:
    messages = [
        {"role": "system", "content": (
            "You are a research agent. Use vector_search to gather evidence "
            "before answering. Search multiple times with different queries if needed."
        )},
        {"role": "user", "content": user_query},
    ]
    for _ in range(max_hops):
        response = client.chat.completions.create(
            model="gpt-4o", messages=messages, tools=TOOLS
        )
        msg = response.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:          # agent decided it has enough context
            return msg.content

        for call in msg.tool_calls:
            args = json.loads(call.function.arguments)
            result = vector_search(**args)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result),
            })

    # Fallback: force synthesis after max_hops
    messages.append({"role": "user", "content": "Synthesize an answer from what you've found."})
    return client.chat.completions.create(model="gpt-4o", messages=messages).choices[0].message.content
```

Now the agent can issue `vector_search("android sync bug")` and then `vector_search("pro plan storage")` in separate hops, accumulate both results, and synthesize a grounded answer.

### When to Prefer Each Architecture

```
Query complexity
     ▲
     │                         Agentic RAG
High │          ┌──────────────────────────────┐
     │          │ Multi-hop, ambiguous,        │
     │          │ real-time, tool-requiring    │
     │          └──────────────────────────────┘
     │   Traditional RAG
Low  │   ┌────────────────────────┐
     │   │ Single-hop factual Q&A │
     │   │ High-volume, low-cost  │
     │   └────────────────────────┘
     └──────────────────────────────────► Retrieval budget
          Cheap                    Expensive
```

---

## Use It

### Frameworks

| Framework | Agentic RAG Support | Notes |
|---|---|---|
| **LangGraph** | Native | Graph-based agent orchestration; define retrieval nodes and edges explicitly |
| **LlamaIndex** | Native (`AgentRunner`) | High-level abstractions for tool-use RAG; good for document workflows |
| **Haystack** | Native (Pipeline + Agent) | Production-grade; strong support for hybrid search |
| **AutoGen** | Multi-agent | Useful when you need specialized sub-agents per domain |
| **OpenAI Assistants API** | Managed | Handles memory and file search server-side; less control over retrieval strategy |
| **Anthropic Claude + tool use** | Manual wiring | Claude follows tool-use instructions precisely; wire `vector_search` as a tool and control the loop yourself |

### Choosing Architecture by Use Case

- **FAQ bots, documentation Q&A, single-source lookups**: Traditional RAG. One retrieval pass is sufficient. Optimize for latency and cost.
- **Analyst assistants, enterprise search across heterogeneous sources**: Agentic RAG with hybrid search (dense + sparse) and structured tool calls.
- **Code assistants (multi-file context)**: Agentic RAG with file-system and AST tools; the agent navigates the codebase iteratively.
- **Customer support with account context**: Agentic RAG combining a vector KB, a CRM API tool, and a user-session memory store.

---

## Common Pitfalls

- **Using agents when RAG suffices.** Agent overhead (multiple LLM calls, latency, cost) is unjustified for 80% of single-hop Q&A workloads. Profile your query distribution before committing to agentic architecture.

- **Infinite agent loops.** Without a hard `max_hops` ceiling and a per-turn timeout, a badly-prompted agent issues retrieval calls in circles. Always enforce a budget, log the loop, and surface a graceful fallback.

- **Trusting the agent's self-reported confidence.** Agents instructed to "stop when confident" frequently stop too early on ambiguous questions or loop too long on unanswerable ones. Use a separate critic LLM call or a structured `done: bool` field in the tool-call schema to make stopping explicit and auditable.

- **Ignoring retrieval quality in the agentic case.** Teams swap to agentic RAG hoping the agent will compensate for a poor vector index. It cannot. The agent orchestrates retrieval; it does not improve the quality of what the index returns. Fix chunking strategy, embedding model, and reranking first.

- **Blowing the context window with accumulated chunks.** Each retrieval hop adds more tokens. By hop 3, you may have 8,000 tokens of retrieved context competing with the system prompt. Implement a compressor step (LLM-based summarization or a sliding window) after each hop to keep the context focused.

---

## Exercises

1. **Easy** — Take the traditional RAG code from this lesson and swap the embedding model to `text-embedding-3-large`. Measure whether retrieval precision improves on a 10-question test set. Why might a bigger embedding model not always produce better end-to-end answers?

2. **Medium** — Extend the agentic RAG loop to support two tools: `vector_search` (existing) and `get_user_account(user_id: str)` (a mock that returns the user's subscription tier and recent activity). Write a test query that requires both tools to answer correctly. Measure the number of LLM calls per turn and total token cost.

3. **Hard** — Design an agentic RAG system for a financial analyst assistant that must (a) search an earnings-report vector index, (b) call a live stock-price API, and (c) write a short memo. Add a critic agent that grades the memo for factual consistency against the retrieved documents. Define the system's failure modes and propose a circuit-breaker strategy to prevent runaway costs.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **RAG** | "LLM + Google search" | A specific pattern: pre-index documents into a vector store, embed the query, retrieve top-k chunks, pass chunks + query to an LLM for grounded generation |
| **Agentic RAG** | "RAG with a chatbot personality" | RAG inside an autonomous reasoning loop where the agent controls when, what, and how many times to retrieve before generating |
| **Vector search** | "Exact keyword matching" | Approximate nearest-neighbor search in high-dimensional embedding space—finds semantically similar text, not exact tokens |
| **Chunking** | "Splitting documents in half" | Deliberate segmentation of source documents into retrieval units; chunk size and overlap directly affect context quality |
| **Retrieval hop** | Any external call | One round of retrieval (embed → search → return results) within a single user turn; agentic RAG enables multiple hops per turn |
| **Reranking** | "Sorting search results" | A second-pass scoring model (usually a cross-encoder) that re-orders retrieved chunks for relevance before stuffing them into the prompt |
| **Tool use / Function calling** | "Writing Python code" | An LLM capability where the model emits structured JSON specifying which external function to call and with what arguments, enabling orchestration without string parsing |

---

## Further Reading

- [LangGraph documentation — Retrieval Agents](https://langchain-ai.github.io/langgraph/tutorials/rag/langgraph_agentic_rag/) — Canonical tutorial for building agentic RAG with explicit graph control flow.
- [LlamaIndex — Agentic RAG overview](https://docs.llamaindex.ai/en/stable/use_cases/agents/) — High-level patterns and code for tool-using retrieval agents.
- [Anthropic — Building effective agents](https://www.anthropic.com/research/building-effective-agents) — Authoritative guide on when agentic loops are warranted vs. simpler patterns, with specific RAG guidance.
- [RAGAS: Automated Evaluation of RAG Pipelines](https://docs.ragas.io/en/stable/) — Framework for measuring retrieval precision, faithfulness, and answer correctness; essential before choosing between RAG and agentic RAG.
- [Pinecone — Chunking strategies for LLM applications](https://www.pinecone.io/learn/chunking-strategies/) — Detailed treatment of fixed-size, semantic, and hierarchical chunking and their effect on downstream retrieval quality.
