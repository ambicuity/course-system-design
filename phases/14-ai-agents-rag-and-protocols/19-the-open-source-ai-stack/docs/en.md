# The Open Source AI Stack

> Every layer of a production AI application has a credible open-source option — the trick is knowing which to pick and when to assemble them.

**Type:** Learn
**Prerequisites:** LLM Fundamentals, RAG basics, Vector Databases, Basic DevOps
**Time:** ~25 minutes

---

## The Problem

You want to build an AI application. You do not want to lock yourself into one vendor's API, one cloud's services, or one model's roadmap. You have heard the open-source ecosystem is mature enough to ship on. You are right — but the ecosystem is wide, the components are uneven, and assembling them into a production system takes more than `pip install`.

The open-source AI stack is real: production-grade embedding models, vector databases, agent frameworks, observability tools, and LLM-serving runtimes all exist under permissive licenses. But "open source" does not mean "free of decisions." You still have to pick the embedding model, the vector DB, the orchestration library, the serving infrastructure, and the observability layer — and you have to make those choices such that they compose.

This lesson maps the open-source stack end-to-end, names the leading project at each layer, and gives you a pragmatic default stack you can ship today.

---

## The Concept

### The five layers of the open-source AI stack

```
   ┌─────────────────────────────────────────────────────────────┐
   │  5. Observability & Evaluation                              │
   │     (Langfuse, Phoenix/Arize, RAGAS, Helicone, MLflow)      │
   ├─────────────────────────────────────────────────────────────┤
   │  4. Agent / Orchestration Framework                         │
   │     (LangGraph, AutoGen, CrewAI, smolagents, Haystack)     │
   ├─────────────────────────────────────────────────────────────┤
   │  3. Foundation Models (open weights)                        │
   │     (Llama 3.3, Mistral, Qwen 2.5, DeepSeek, Gemma, Phi-4)  │
   ├─────────────────────────────────────────────────────────────┤
   │  2. Data, Embeddings & Retrieval                            │
   │     (pgvector, Qdrant, Milvus, Weaviate, FAISS, BGE, Nomic) │
   ├─────────────────────────────────────────────────────────────┤
   │  1. Application & Serving                                   │
   │     (Next.js, SvelteKit, FastAPI, Streamlit, vLLM, Ollama)  │
   └─────────────────────────────────────────────────────────────┘
```

Each layer has at least three credible open-source options. The decision at each layer is independent of the others — but the layers have to compose, which constrains the choices.

---

### Layer 1: Application & Serving

This layer covers what the user sees (frontend) and what runs the model (serving).

**Frontend frameworks:**

| Tool | Best for |
|---|---|
| **Next.js** | Production-grade AI apps with chat UIs, streaming, auth |
| **SvelteKit** | Lighter-weight apps, faster cold starts |
| **Streamlit** | Internal tools, data science demos, rapid prototyping |
| **Gradio** | ML demo interfaces, model playgrounds |
| **Vercel AI SDK** | Streaming-first React components for LLM UIs |

**Model serving runtimes:**

| Tool | Best for |
|---|---|
| **vLLM** | High-throughput LLM inference on GPUs (PagedAttention) |
| **Ollama** | Local LLM serving on a laptop or small server |
| **llama.cpp** | CPU inference, edge devices, smallest footprint |
| **TGI (Text Generation Inference)** | Hugging Face's production server, multi-GPU |
| **SGLang** | Fast structured generation, function calling |
| **TensorRT-LLM** | NVIDIA-optimized inference, maximum throughput |

A typical open-source stack for serving: **Ollama** for local development, **vLLM** for production GPU serving, **TGI** as an alternative for Hugging Face ecosystems.

---

### Layer 2: Data, Embeddings & Retrieval

This is the heart of any RAG system: how you store documents, embed them, and search them.

**Vector databases:**

| Tool | Best for |
|---|---|
| **pgvector** | Postgres shops that want one less system to operate |
| **Qdrant** | Production vector search with rich filtering |
| **Milvus** | Massive scale (billions of vectors), distributed |
| **Weaviate** | Hybrid search (vector + BM25) built in |
| **Chroma** | Local development, embeddings + metadata in one |
| **FAISS** | Pure library, fastest similarity search, no server |
| **LanceDB** | Embedded vector DB for serverless / edge |

A pragmatic default: **pgvector** for modest scale (≤10M vectors), **Qdrant** when you need rich filtering or scale beyond pgvector, **FAISS** when you need raw speed and can build the serving layer yourself.

**Embedding models (open weights):**

| Model | Strengths |
|---|---|
| **BGE (BAAI)** | Top of MTEB leaderboard, multilingual, multiple sizes |
| **Nomic Embed Text v2** | Open weights, long context (8k), strong English performance |
| **Jina Embeddings v3** | Multilingual, task-specific LoRA adapters |
| **E5 / Multilingual-E5** | Microsoft's line, well-documented, multiple sizes |
| **Cohere Embed v3** | Closed weights but free tier; multilingual, hybrid search support |
| **Sentence-Transformers (all-MiniLM)** | Fast, small, decent quality for prototyping |

**Retrieval frameworks:**

| Tool | Best for |
|---|---|
| **LangChain** | Broad integrations, prototype quickly |
| **LlamaIndex** | Document-heavy RAG, indexing pipelines |
| **Haystack** | Production RAG pipelines, NLP focus |
| **txtai** | Semantic graph search, all-in-one |

A pragmatic default: **BGE-small or Nomic Embed v2** for embeddings, **pgvector or Qdrant** for the vector store, **LlamaIndex or LangChain** for the orchestration library.

---

### Layer 3: Foundation Models (open weights)

The reasoning engine. Open-weight models have closed the gap with frontier closed models for many tasks, though not all.

**Leading open-weight model families (mid-2025):**

| Model | Sizes | Strengths |
|---|---|---|
| **Llama 3.3** | 70B (and smaller variants) | Strong general reasoning, broad ecosystem |
| **Mistral / Mixtral** | 7B, 8x7B, large variants | Excellent speed/quality trade-off, permissive license |
| **Qwen 2.5** | 0.5B to 72B | Top multilingual performance, strong at math/coding |
| **DeepSeek V3** | 67B (MoE) | Excellent reasoning, math, code; open license |
| **Gemma 2** | 2B, 9B, 27B | Google's open line, strong instruction following |
| **Phi-4** | 14B | Microsoft's compact, strong reasoning per parameter |
| **Command R+** | 104B | Cohere's open line, RAG and tool use focused |

**How to choose:**

```
   Need best reasoning at any cost?
   → DeepSeek V3 or Llama 3.3 70B

   Need fast, cheap, decent quality?
   → Mistral 7B, Qwen 2.5 7B, Gemma 2 9B

   Need multilingual (non-English)?
   → Qwen 2.5 or multilingual-E5 embeddings

   Need to run on CPU or edge?
   → Phi-4 14B (quantized), Llama 3.2 1B/3B, Gemma 2 2B

   Need coding / agentic tasks?
   → DeepSeek V3, Qwen 2.5 Coder, Code Llama

   Need tool use and function calling?
   → Command R+, Llama 3.3, Mistral Large
```

Open-weight models are not one-size-fits-all. The leaderboard rankings shift every month. Run your own evaluation against your actual workload before committing.

---

### Layer 4: Agent / Orchestration Framework

The runtime that owns the loop, the state, the memory, and the tool dispatch.

| Framework | Language | Mental model | Best for |
|---|---|---|---|
| **LangGraph** | Python, JS | Graph of nodes, explicit state | Production agents with complex control flow |
| **AutoGen** | Python | Conversational agents | Multi-agent research, coding workflows |
| **CrewAI** | Python | Role-based crews | Structured team workflows |
| **smolagents** | Python | Code-agent minimalism | Lightweight code-executing agents |
| **Haystack** | Python | Pipeline-based NLP | Production RAG, document processing |
| **LlamaIndex** | Python | Data framework for LLM apps | Document-heavy RAG, indexing |
| **Semantic Kernel** | Python, C#, JS | Plugin architecture | Enterprise .NET shops |

A pragmatic default: **LangGraph** for new production agents, **LlamaIndex** for document-heavy RAG, **smolagents** for code-executing agents.

---

### Layer 5: Observability & Evaluation

You cannot debug what you cannot see. Open-source observability for AI is now mature.

**Tracing & logging:**

| Tool | Best for |
|---|---|
| **Langfuse** | Open-source LLM tracing, prompt management, evaluations |
| **Phoenix (Arize)** | Open-source tracing, drift detection, embeddings analysis |
| **OpenLLMetry** | OpenTelemetry instrumentation for LLM apps |
| **MLflow Tracing** | MLflow's new tracing, integrates with the MLflow ecosystem |
| **Helicone** | Proxy-based logging, cost analytics, fast to set up |

**Evaluation:**

| Tool | Best for |
|---|---|
| **RAGAS** | RAG-specific metrics (retrieval recall, answer faithfulness) |
| **DeepEval** | General LLM evaluation framework |
| **Braintrust** | Eval framework with hosted UI (limited open source) |
| **Promptfoo** | Prompt regression testing, red-teaming |
| **lm-evaluation-harness** | Standardized model benchmarks (EleutherAI) |

A pragmatic default: **Langfuse** or **Phoenix** for tracing, **RAGAS** for RAG-specific evaluation, **Promptfoo** for prompt regression tests.

---

### The complete stack on one diagram

```
   ┌────────────────────────────────────────────────────────────┐
   │  User Interface                                           │
   │  (Next.js + Vercel AI SDK)                                │
   └────────────────────────┬───────────────────────────────────┘
                            │
                            ▼
   ┌────────────────────────────────────────────────────────────┐
   │  Agent Orchestration                                       │
   │  (LangGraph + LlamaIndex for RAG)                         │
   └───────┬─────────────────────────────┬─────────────────────┘
           │                             │
           ▼                             ▼
   ┌─────────────────────┐    ┌──────────────────────────────┐
   │  Embedding Model    │    │  Foundation Model            │
   │  (BGE-large / Nomic)│    │  (Llama 3.3 / Mistral via   │
   │                     │    │   vLLM or Ollama)            │
   └──────────┬──────────┘    └──────────────────────────────┘
              │
              ▼
   ┌────────────────────────────────────────────┐
   │  Vector Store + Metadata                   │
   │  (Qdrant / pgvector / Milvus)              │
   └────────────────────────────────────────────┘

   ┌────────────────────────────────────────────┐
   │  Observability                              │
   │  (Langfuse + RAGAS + Promptfoo)             │
   └────────────────────────────────────────────┘
```

This stack runs on your own infrastructure (or any cloud), uses no proprietary APIs for the core path, and can be deployed for tens to hundreds of dollars per month at modest scale.

---

## Build It / In Depth

### A starter stack for a small team

For a team of two engineers building their first production AI app:

```yaml
# The starter stack
frontend:    Next.js + Vercel AI SDK
agent:       LangGraph (Python)
embedding:   BGE-small-en-v1.5 (or Nomic Embed v1.5)
vector_db:   pgvector (in your existing Postgres)
llm:         Llama 3.3 70B via vLLM on a single A100
             OR OpenAI / Anthropic API for the first 3 months
observability: Langfuse (self-hosted) + RAGAS (evals)
auth:        NextAuth + Postgres
deployment:  Docker Compose on a single Hetzner / RunPod box
```

Total cost: ~$200–500/month for moderate traffic. No per-token API lock-in. You can swap the LLM at any time.

---

### A scaling stack for a mid-size team

When traffic grows beyond what one box can handle:

```yaml
frontend:    Next.js + Vercel AI SDK (Vercel hosting)
agent:       LangGraph on Kubernetes
embedding:   BGE-large-en-v1.5 served via TEI
vector_db:   Qdrant cluster (3+ nodes)
llm:         Llama 3.3 70B on a 4xA100 GPU node
             OR a router that picks between open and closed models
observability: Langfuse cluster + Grafana + Prometheus
              + RAGAS + DeepEval
auth:        Auth0 or Clerk
deployment:  Kubernetes (EKS / GKE) + ArgoCD
load_testing: k6 + Langfuse replays
```

Total cost: $3,000–10,000/month at 100k requests/day. Still no per-token lock-in if you stay on open weights.

---

### When to mix in closed APIs

Even teams committed to open source usually mix in closed APIs for specific cases:

| Use case | Why closed APIs win |
|---|---|
| Frontier reasoning (cutting-edge math, code, multi-step planning) | Open models lag by 6–12 months on hardest benchmarks |
| Multimodal (image, audio, video) | Open multimodal models are improving fast but still lag |
| Latency-critical paths | Closed APIs often have lower per-call latency than self-hosted |
| Compliance / data residency | Some regulators prefer specific certified providers |

A pragmatic pattern: **router model** — a small classifier picks between open and closed models per request, based on task type, cost budget, or latency requirement.

```python
def route_request(prompt, max_latency_ms, max_cost_cents):
    if is_simple_qa(prompt) and max_latency_ms < 200:
        return call_local_llm(prompt)         # fast, cheap
    if is_complex_reasoning(prompt):
        return call_claude_opus(prompt)       # highest quality
    return call_local_llm(prompt)              # default
```

---

## Use It

### Decision cheat sheet

| If you need… | Reach for… |
|---|---|
| Local development on a laptop | Ollama + Chroma + LangChain |
| Production RAG with modest scale | pgvector + BGE + LangGraph |
| Maximum-scale vector search | Milvus or Qdrant cluster |
| High-throughput LLM serving | vLLM (GPU) or TGI |
| CPU / edge inference | llama.cpp + GGUF-quantized models |
| Tracing & debugging | Langfuse or Phoenix |
| RAG evaluation | RAGAS |
| Prompt regression testing | Promptfoo |
| General-purpose agent runtime | LangGraph |
| Document-heavy workflows | LlamaIndex |
| .NET / enterprise | Semantic Kernel |

### Avoiding common traps

- **Open source does not mean free.** GPU time, engineering hours, and maintenance are real costs. A closed API at $0.01/request is often cheaper than running your own GPU for low traffic.
- **Permissive licenses matter.** MIT and Apache 2.0 let you ship without legal review. Llama's community license, Gemma's prohibited use policy, and others have restrictions. Read the license.
- **Open source does not mean production-ready.** A library with 50 GitHub stars and no releases is not production-ready. Look for active maintenance, semantic versioning, and a community.
- **Mixing versions breaks things.** Pin all versions, use lockfiles, and update deliberately. The open-source AI ecosystem moves fast and breaking changes are common.

---

## Common Pitfalls

- **Choosing components in isolation.** Each layer has many good options; the wrong combination fails to compose. Pick components known to work together (e.g., pgvector + LangChain + Next.js is a tested combination).

- **GPU costs dominating the bill.** Self-hosting Llama 70B on a 4xA100 node costs $4,000+/month before traffic. If your traffic is low, the closed API is cheaper.

- **No evaluation harness.** Without RAGAS / DeepEval / Promptfoo, you cannot tell if your open-source stack is performing as well as the closed alternative. Build the harness before committing.

- **Skipping observability.** Open-source stacks fail in more places than closed APIs (because there are more components). Tracing is non-optional.

- **License non-compliance.** Some "open" models restrict commercial use, fine-tuning, or redistribution. Read the license before shipping.

- **Vendor lock-in by another name.** Using OpenAI's embeddings and vector store is not "open source" even if the framework is. The lock-in is in the data format and the API.

---

## Exercises

1. **Easy** — Pick three of the five layers in the open-source stack. For each, name two credible open-source options and the trade-off between them.

2. **Medium** — Design an open-source stack for a 50-person company's internal knowledge base assistant. Specify each layer, justify each choice, and estimate monthly cost.

3. **Hard** — Your team has built an AI app using OpenAI APIs and Pinecone. The CTO wants to migrate to 100% open source. Propose a phased migration plan that minimizes risk: which components to migrate first, how to run both in parallel, how to evaluate parity, and what to do if the open-source stack underperforms.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Open-source AI stack | A free way to build AI | A collection of permissive-license projects covering every layer of an AI application — but each component must be chosen, integrated, operated, and paid for in compute time |
| Open weights | The model is open | The model weights are downloadable and (usually) modifiable; the training data and process are typically not — important distinction for compliance |
| Vector database | A database | A specialized index optimized for similarity search over high-dimensional embeddings; not a general-purpose database, and not a keyword search engine |
| Embedding model | A way to convert text to numbers | A model (usually a transformer) that maps text to dense vectors where semantic similarity is geometric proximity; quality varies widely by model size and training data |
| Self-hosting | Free inference | Running the model on your own GPU/CPU hardware; you pay for hardware, electricity, and engineering time, but no per-token fees |
| Ollama | A tool for running LLMs | A local model server that wraps llama.cpp with a clean CLI and API; the easiest way to run open-weight models on a laptop |
| vLLM | Another inference server | A high-throughput LLM serving system using PagedAttention; the production default for self-hosted open-weight models on GPUs |
| Langfuse | A logging tool | An open-source LLM observability platform with tracing, prompt management, evaluation, and cost analytics; self-hostable |

---

## Further Reading

- **vLLM Documentation** — the production-grade open-weight LLM serving system: https://docs.vllm.ai
- **LangChain / LangGraph Documentation** — the most-used open-source agent framework: https://langchain-ai.github.io/langgraph/
- **LlamaIndex Documentation** — the leading open-source RAG framework: https://docs.llamaindex.ai
- **MTEB Leaderboard** — the canonical benchmark for embedding models, updated regularly: https://huggingface.co/spaces/mteb/leaderboard
- **RAGAS Documentation** — the open-source framework for evaluating RAG pipelines: https://docs.ragas.io
- **Open LLM Leaderboard (Hugging Face)** — the running ranking of open-weight models on standard benchmarks: https://huggingface.co/spaces/open-llm-leaderboard/open_llm_leaderboard
- **Awesome Open-Source AI** — a curated list of open-source AI projects across all layers: https://github.com/jamez-bondos/awesome-gpt4o-images