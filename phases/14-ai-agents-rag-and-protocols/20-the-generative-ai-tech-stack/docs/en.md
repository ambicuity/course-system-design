# The Generative AI Tech Stack

> Nine layers, every one with credible tools — pick one at each, make them compose, ship something real.

**Type:** Learn
**Prerequisites:** LLM Fundamentals, Basic ML/DevOps, Cloud basics
**Time:** ~30 minutes

---

## The Problem

Generative AI is sold as "a model," but no production system runs on a model alone. A real GenAI application needs infrastructure to serve the model, frameworks to build with it, databases to ground it, observability to debug it, and safety layers to ship it responsibly. Each of these is its own decision, with its own trade-offs, its own vendors.

The temptation is to copy what a vendor recommends — "use our hosted runtime, our vector DB, our eval tool, our safety guardrails." That works, until you outgrow the lock-in, or until a competitor moves faster because they were not. The other temptation is to assemble everything from open-source parts without thinking — and ship a fragile, expensive mess.

The right answer is to know the layers, know the leading options at each, and pick deliberately. This lesson walks through the nine layers that make up a production GenAI stack. For each, you get the role, the leading tools, and the decision criteria. By the end, you should be able to map any GenAI application onto the stack and explain every choice.

---

## The Concept

### The nine layers

```
   ┌─────────────────────────────────────────────────────────────┐
   │  9. Model Safety & Guardrails                               │
   │     (LLM Guard, NeMo Guardrails, Guardrails AI, Garak)      │
   ├─────────────────────────────────────────────────────────────┤
   │  8. Model Supervision (Monitoring)                          │
   │     (Fiddler, WhyLabs, Helicone, Arize, Phoenix)            │
   ├─────────────────────────────────────────────────────────────┤
   │  7. Synthetic Data Generation                               │
   │     (Gretel, Tonic AI, Mostly AI, SDV)                      │
   ├─────────────────────────────────────────────────────────────┤
   │  6. Embeddings & Labeling                                   │
   │     (Cohere, Scale AI, Nomic, JinaAI, Label Studio)         │
   ├─────────────────────────────────────────────────────────────┤
   │  5. Fine-Tuning & Adaptation                                │
   │     (Weights & Biases, Hugging Face TRL, Axolotl, OctoML)  │
   ├─────────────────────────────────────────────────────────────┤
   │  4. Databases & Orchestration                               │
   │     (Pinecone, Weaviate, LangChain, LlamaIndex)             │
   ├─────────────────────────────────────────────────────────────┤
   │  3. AI Frameworks                                           │
   │     (LangChain, PyTorch, Hugging Face, DSPy)                │
   ├─────────────────────────────────────────────────────────────┤
   │  2. Foundation Models                                       │
   │     (GPT-4o, Claude, Gemini, Llama, Mistral, DeepSeek)      │
   ├─────────────────────────────────────────────────────────────┤
   │  1. Cloud Hosting & Inference                               │
   │     (AWS, GCP, Azure, NVIDIA NIM, Together, Fireworks)      │
   └─────────────────────────────────────────────────────────────┘
```

The stack is bottom-up: infrastructure hosts models, models are wrapped by frameworks, frameworks connect to databases, databases ground the model, fine-tuning customizes it, embeddings structure the inputs, synthetic data fills gaps, supervision monitors behavior, and safety layers prevent harm. Each layer depends on the ones below it.

---

### Layer 1: Cloud hosting & inference

The physical and virtual infrastructure that runs your models.

| Provider | Strengths |
|---|---|
| **AWS** | Broadest service catalog, Bedrock for managed model access, Inferentia / Trainium for cost-optimized inference |
| **GCP** | Best-in-class TPUs, Vertex AI for managed model serving, strong data tooling (BigQuery) |
| **Azure** | OpenAI partnership (exclusive Azure OpenAI Service), enterprise integrations |
| **NVIDIA NIM** | GPU-optimized inference microservices, fastest raw throughput |
| **Together AI** | Affordable open-model serving, simple API |
| **Fireworks AI** | Fast open-model inference, function-calling optimized |
| **Replicate** | Pay-per-second model running, huge model catalog |
| **Modal** | Serverless GPU, great developer experience |
| **Lambda Labs** | GPU cloud rental, cost-effective for self-hosted |

**Decision criteria:**
- **Already on AWS/GCP/Azure?** Stay there; use Bedrock / Vertex / Azure OpenAI.
- **Maximum throughput?** NVIDIA NIM or Fireworks.
- **Cheapest open-model serving?** Together AI or Replicate.
- **Burstable GPU for dev?** Modal or Replicate.

---

### Layer 2: Foundation models

The reasoning engine. See the [Open Source AI Stack](19-the-open-source-ai-stack/) chapter for a detailed model comparison.

**Closed (API):**

| Model | Strengths |
|---|---|
| **GPT-4o / GPT-4 Turbo** (OpenAI) | Best general reasoning, multimodal, broadest ecosystem |
| **Claude 3.5/4 Sonnet, Opus** (Anthropic) | Long context (200k), strong coding, careful reasoning |
| **Gemini 1.5 Pro/Flash** (Google) | Very long context (1M–2M tokens), multimodal |
| **Grok 2/3** (xAI) | Real-time X/Twitter data, fast |

**Open weights:**

| Model | Strengths |
|---|---|
| **Llama 3.3 70B** (Meta) | Strong general reasoning, broad ecosystem |
| **Mistral / Mixtral** | Excellent speed/quality, permissive license |
| **Qwen 2.5** (Alibaba) | Top multilingual, strong math/coding |
| **DeepSeek V3** | Frontier-level reasoning, open license |
| **Gemma 2** (Google) | Open-weights, strong at instruction following |
| **Phi-4** (Microsoft) | Compact, surprisingly capable |

**Decision criteria:**

```
   Need best quality and don't mind the bill?
   → GPT-4o, Claude Opus, Gemini Pro

   Need best cost-quality trade-off?
   → Claude Haiku, GPT-4o-mini, Gemini Flash

   Need data residency / on-prem?
   → Llama 3.3, DeepSeek V3, Qwen 2.5 (self-hosted)

   Need best at coding?
   → Claude Sonnet, DeepSeek V3, GPT-4o

   Need very long context?
   → Gemini 1.5 Pro (1M+), Claude (200k)
```

---

### Layer 3: AI frameworks

The libraries that wrap the model and connect it to your application.

| Framework | Strengths |
|---|---|
| **LangChain** | Broadest integration library, good for prototyping |
| **LangGraph** | Production-grade agent runtime (subset of LangChain) |
| **LlamaIndex** | Best-in-class for RAG over documents |
| **Haystack** | Production NLP pipelines, deepset-maintained |
| **DSPy** | Compiles prompts from examples, optimizable |
| **PyTorch** | The foundation; you write everything yourself |
| **Hugging Face Transformers** | The de facto standard for open-weight models |
| **Semantic Kernel** | Enterprise-grade, multi-language (C# especially) |

**Decision criteria:** see the AI agent frameworks chapter for a deeper comparison.

---

### Layer 4: Databases & orchestration

The data layer that grounds the model and stores agent state.

**Vector databases:**

| Tool | Strengths |
|---|---|
| **Pinecone** | Managed, scales effortlessly, serverless option |
| **Weaviate** | Open source, hybrid search built in |
| **Qdrant** | Open source, fast, Rust-based |
| **Milvus** | Open source, massive scale |
| **pgvector** | Postgres extension, simplest if you already run Postgres |
| **Chroma** | Open source, great for development |
| **LanceDB** | Embedded, serverless-friendly |

**Orchestration tools:** LangChain, LlamaIndex (covered above). They overlap with framework choice — usually pick one orchestration library and stick with it.

---

### Layer 5: Fine-tuning & adaptation

When the base model is not good enough, you customize it.

| Tool | Role |
|---|---|
| **Weights & Biases** | Experiment tracking, model registry, hyperparameter sweeps |
| **Hugging Face TRL** | SFT, DPO, PPO, reward modeling |
| **Axolotl** | End-to-end fine-tuning framework, YAML config |
| **LLaMA-Factory** | Unified fine-tuning across many model families |
| **Unsloth** | 2–5× faster fine-tuning via optimized kernels |
| **OctoML** | Optimized model compilation and deployment |
| **OpenPipe** | Managed fine-tuning for production agents |
| **Lamini** | Specialized fine-tuning for LLM applications |

**Decision criteria:**

```
   Need to customize a closed model (GPT, Claude, Gemini)?
   → OpenAI fine-tuning API, Anthropic fine-tuning (limited), Google tuning

   Need to customize an open-weight model?
   → Hugging Face TRL + Axolotl on your own GPUs
   → OR Replicate / Modal / Lambda Labs for rented GPUs

   Need to track experiments and compare runs?
   → Weights & Biases (best-in-class)

   Need fast iteration with low effort?
   → Unsloth for speed, OpenPipe for managed
```

---

### Layer 6: Embeddings & labeling

The layer that converts unstructured data into structured representations.

| Tool | Role |
|---|---|
| **Cohere Embed** | Best-in-class multilingual embeddings, hybrid search support |
| **OpenAI Embeddings** | `text-embedding-3-small/large` — reliable, slightly higher cost |
| **Nomic Embed** | Open weights, long context, strong performance |
| **JinaAI Embeddings** | Open weights, multilingual, task-specific LoRA |
| **Voyage AI** | High-quality embeddings optimized for RAG |
| **Scale AI** | Human-labeled data for fine-tuning and evaluation |
| **Label Studio** | Open-source data labeling platform |
| **Snorkel AI** | Programmatic labeling, weak supervision |

**When to label vs embed:**

- **Embeddings** turn text into vectors for semantic search — always needed for RAG.
- **Labeling** creates (input, expected output) pairs for fine-tuning or evaluation — needed only when you customize the model.

---

### Layer 7: Synthetic data generation

When real data is scarce, expensive, or privacy-restricted, you generate it.

| Tool | Role |
|---|---|
| **Gretel** | Synthetic tabular and text data with privacy guarantees |
| **Tonic AI** | Synthetic data for dev / test environments, PII-safe |
| **Mostly AI** | Synthetic tabular data that preserves statistical properties |
| **SDV (Synthetic Data Vault)** | Open-source synthetic data for tabular use cases |
| **MOSTLY AI** | Similar to Gretel, strong on enterprise compliance |
| **LangChain / LlamaIndex synthetic datasets** | Use LLMs to generate (prompt, response) pairs for fine-tuning |

**When to use synthetic data:**

- You need training data but cannot use real user data (privacy).
- You need to bootstrap a model before you have real traffic.
- You need test data that covers edge cases hard to find in production.

---

### Layer 8: Model supervision (monitoring)

You cannot fix what you cannot see. Supervision tools track production behavior.

| Tool | Role |
|---|---|
| **Fiddler AI** | Model monitoring, drift detection, explainability |
| **WhyLabs** | Data and model observability, drift detection |
| **Arize Phoenix** | Open-source tracing, drift, embedding analysis |
| **Helicone** | LLM proxy, logs every call, cost analytics |
| **Langfuse** | Open-source tracing, prompt management, evals |
| **MLflow** | Model registry, experiment tracking, now with tracing |
| **Datadog LLM Observability** | Part of Datadog, integrates with infra monitoring |

**Three categories of metrics to track:**

1. **Operational:** latency (p50, p95, p99), error rate, throughput, cost per request.
2. **Quality:** retrieval recall, answer faithfulness, hallucination rate, task success.
3. **Behavioral:** refusal rate, prompt-injection attempts, off-topic responses.

---

### Layer 9: Model safety & guardrails

The last line of defense before user-facing output.

| Tool | Role |
|---|---|
| **NeMo Guardrails** (NVIDIA) | Programmable rails, topic control, jailbreak prevention |
| **Guardrails AI** | Open-source validation framework, Pydantic-style specs |
| **LLM Guard** | Prompt injection detection, PII redaction, toxicity filtering |
| **Arthur AI** | Model monitoring + safety, bias detection |
| **Garak** | Red-teaming tool, finds vulnerabilities before attackers do |
| **Prompt Armor** | Input sanitization for production agents |

**What to guard against:**

```
   Prompt injection      → Input validation, system prompt hardening
   PII leakage          → Output filtering, redaction
   Toxic outputs        → Content moderation layer
   Jailbreaks           → Topic rails, behavioral constraints
   Hallucinations       → Grounding via RAG, fact-check layer
   Cost explosion       → Rate limits, token budgets, max-iteration caps
```

---

## Build It / In Depth

### A complete production stack, mapped to a real product

Imagine you are building a customer support agent for a SaaS company.

**Stack:**

| Layer | Choice | Why |
|---|---|---|
| 1. Hosting | AWS (Bedrock for managed models, ECS for agents) | Already on AWS, want managed where possible |
| 2. Foundation model | Claude Sonnet via Bedrock | Best at instruction following + tool use |
| 3. AI framework | LangGraph | Production agent with branching and retries |
| 4. Vector DB | OpenSearch Serverless (managed) | Hybrid search needed, already on AWS |
| 5. Fine-tuning | Not needed initially | RAG + good prompt covers the use case |
| 6. Embeddings | Amazon Titan Embeddings v2 | Bundled with Bedrock, no extra vendor |
| 7. Synthetic data | LangChain synthetic dataset | Bootstrap eval set before production traffic |
| 8. Monitoring | LangSmith + CloudWatch | LangSmith for traces, CloudWatch for infra |
| 9. Safety | LLM Guard + custom output filter | Prompt injection detection + PII redaction |

**Architecture diagram:**

```
   ┌────────────────────────────────────────────────────────────┐
   │   User → CloudFront → API Gateway → Lambda (LangGraph)    │
   │                                          │                │
   │                          ┌───────────────┼───────────┐    │
   │                          ▼               ▼           ▼    │
   │                     Bedrock:        Bedrock:     OpenSearch│
   │                     Claude          Titan        Serverless│
   │                     Sonnet          Embeddings            │
   │                          │               │           │    │
   │                          └───────────────┴───────────┘    │
   │                                          │                │
   │                                          ▼                │
   │                                  ┌──────────────────┐     │
   │                                  │ LLM Guard filter │     │
   │                                  │ (output check)   │     │
   │                                  └──────────────────┘     │
   │                                          │                │
   │                                          ▼                │
   │                                  LangSmith tracing        │
   └────────────────────────────────────────────────────────────┘
```

This is a real, shippable architecture. Every layer has a concrete choice. Every choice has a justification.

---

### Cost shape (modest production scale)

1,000 customer support conversations/day, ~10 turns each, ~1,500 tokens per turn:

| Layer | Approximate monthly cost |
|---|---|
| AWS compute (Lambda + API Gateway) | ~$50 |
| Bedrock Claude Sonnet (10M input + 5M output tokens/day) | ~$2,500 |
| Bedrock Titan Embeddings | ~$50 |
| OpenSearch Serverless (2 OCUs) | ~$350 |
| LangSmith | ~$80 |
| LLM Guard (self-hosted) | ~$30 |
| **Total** | **~$3,000/month** |

The model dominates again. Reducing context size, prompt size, or per-call tokens is the highest-leverage optimization.

---

### When to use which layers

Some layers are mandatory; some are optional. Use this checklist:

```
   [✓] Always: hosting, foundation model, framework, monitoring
   [✓] For RAG: embeddings + vector DB
   [✓] For production: safety / guardrails
   [ ] Fine-tuning: only when prompt + RAG plateau
   [ ] Synthetic data: only when real data is scarce or restricted
   [ ] Advanced monitoring: only at meaningful production scale
```

---

## Use It

### Quick decision guide

| If you are… | Start with |
|---|---|
| A solo developer building an MVP | Ollama + Llama 3 + LangChain + Chroma + Helicone |
| A startup building a B2B product | Claude Sonnet + LangGraph + Pinecone + Langfuse + LLM Guard |
| An enterprise with strict compliance | Bedrock (Claude / Llama) + OpenSearch + SageMaker + Fiddler + NeMo Guardrails |
| A research team | DeepSeek V3 / Llama 3.3 (self-hosted) + vLLM + MLflow + custom eval |
| A cost-sensitive team | GPT-4o-mini / Claude Haiku + pgvector + Langfuse self-hosted |

### Stack maturity matters

A production GenAI stack is not just a list of tools — it is a list of tools whose versions, integrations, failure modes, and upgrade paths you understand. The right stack for your team is:

1. **Composed of tools you can operate.** Each piece needs monitoring, debugging, and on-call coverage.
2. **Composable.** Swapping any one layer should not require rewriting the others.
3. **Observable end-to-end.** Every LLM call, every tool call, every retrieval is traced.
4. **Safe by default.** Input validation, output filtering, rate limits, and human-in-the-loop are not optional.

---

## Common Pitfalls

- **Skipping monitoring until something breaks.** Adding tracing after the agent is in production means you have no data about the bugs that already happened. Wire Langfuse / Phoenix / Helicone from the first user.

- **Choosing fine-tuning before evaluating the prompt.** Most teams fine-tune because their prompt is bad. Improve the prompt, add RAG, then decide if fine-tuning is needed.

- **Over-investing in synthetic data.** Synthetic data is a means, not an end. Use it to bootstrap evals and training, but never let it fully replace real production feedback.

- **No guardrails for user-facing agents.** Production agents need input validation, output filtering, and rate limits. Without them, the agent will be jailbroken within hours of launch.

- **Mixing too many vendors.** Each vendor in your stack is a billing relationship, an SLA, an upgrade risk. Aim for 3–5 core vendors across the nine layers, not one per layer.

- **No version pinning.** Every layer should be pinned to a specific version. The GenAI ecosystem moves fast; an unpinned dependency will surprise you at the worst time.

---

## Exercises

1. **Easy** — Map each of the nine layers to a specific tool. Justify each choice in one sentence.

2. **Medium** — Pick a real product (e.g., a chatbot, a RAG app, a coding assistant). Identify which of the nine layers it uses, which it skips, and where the gaps would hurt at scale.

3. **Hard** — Your company has built a GenAI product using OpenAI APIs end-to-end. The CFO wants to cut the AI bill by 60%. Design a stack migration: which layers to move to open weights, which to keep on closed APIs, what the cost / quality trade-off looks like at each step, and how you de-risk the migration.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Generative AI stack | The model | Nine layers of infrastructure — hosting, models, frameworks, data, fine-tuning, embeddings, synthetic data, monitoring, safety — that together make a production GenAI application |
| Foundation model | The brain | The reasoning engine of a GenAI app; usually an LLM, but also image, audio, or multimodal models |
| Vector database | A database | A specialized index for similarity search over embeddings; not a general-purpose DB |
| Fine-tuning | Customizing a model | Continued training of a base model on domain-specific data to instill behavior or knowledge that prompting cannot achieve |
| Embedding model | A way to encode text | A model that converts text (or images, audio) into dense vectors where semantic similarity is geometric proximity |
| Synthetic data | Fake data | Artificially generated data (usually via LLMs or statistical models) used to bootstrap training, evaluation, or testing when real data is scarce or restricted |
| Guardrails | Filters on output | Programmable constraints on model behavior — input validation, output filtering, topic rails, jailbreak prevention |
| Monitoring | Reading logs | Structured tracing of every LLM call, retrieval, and tool call with metrics on latency, cost, quality, and behavior |

---

## Further Reading

- **"The GenAI Stack"** — a curated overview of the production GenAI tech landscape: https://www.bvp.com/atlas/the-genai-stack
- **NVIDIA NIM Documentation** — GPU-optimized model serving for production: https://developer.nvidia.com/nim
- **Weights & Biases Documentation** — experiment tracking and model registry for fine-tuning workflows: https://docs.wandb.ai
- **Langfuse Documentation** — open-source LLM observability: https://langfuse.com/docs
- **NeMo Guardrails Documentation** — NVIDIA's programmable guardrail framework: https://docs.nvidia.com/deeplearning/nemo/user-guide/docs/en/latest/guardrails/overview.html
- **MTEB Leaderboard** — the canonical embedding model benchmark: https://huggingface.co/spaces/mteb/leaderboard
- **Open LLM Leaderboard** — Hugging Face's running ranking of open-weight models: https://huggingface.co/spaces/open-llm-leaderboard/open_llm_leaderboard