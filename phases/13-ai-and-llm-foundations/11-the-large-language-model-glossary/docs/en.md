# The Large-Language Model Glossary

> Every precision failure in an LLM system can be traced back to a misunderstood term.

**Type:** Learn
**Prerequisites:** Introduction to AI Systems, Transformer Architecture Basics
**Time:** ~35 minutes

---

## The Problem

You're on a team building an internal knowledge-base assistant. The product manager asks for "fine-tuning on our docs." The ML engineer suggests "just use RAG." The infrastructure lead wants to know "why the temperature is so high." Three people, same conversation, three completely different mental models — and none of them are obviously wrong, because the same words mean different things in different contexts.

This terminological ambiguity kills LLM projects. Teams spend cycles building the wrong solution. Engineers burn GPU budget fine-tuning a model when retrieval would have solved the problem at one-hundredth the cost. PMs set quality expectations based on demo-temperature outputs that are five times more creative than what production should run. Architects specify "embeddings" in a design doc without distinguishing between the model that produces them and the database that stores them.

LLM terminology forms a layered vocabulary across five concerns: **what the model is**, **how it was trained**, **how you prompt it**, **how it generates tokens**, and **how you augment its knowledge at runtime**. Mastering this taxonomy lets you read papers, evaluate vendors, debug production failures, and have precise technical conversations — all prerequisites for building reliable AI-powered systems.

---

## The Concept

### Layer 1 — Model Types

The word "model" is overloaded. In LLM contexts it usually means one of these:

| Type | What it is | When to reach for it |
|---|---|---|
| **Foundation Model** | Pretrained on massive unlabeled corpora; capable but unaligned | Base for fine-tuning; never deploy raw to users |
| **Instruction-Tuned Model** | Foundation model aligned with RLHF or DPO to follow human instructions | Default choice for chat / Q&A products |
| **Reasoning Model** | Generates a chain-of-thought scratchpad before answering (e.g., o1, DeepSeek-R1) | Math, multi-step logic, code debugging |
| **Multi-modal Model** | Accepts images, audio, or video in addition to text (e.g., GPT-4o, Gemini) | Vision tasks, document parsing, voice interfaces |
| **Small Language Model (SLM)** | Parameter count in the millions-to-low-billions; fits on-device (e.g., Phi-3, Mistral 7B) | Edge inference, low-latency, privacy-sensitive |

A foundation model is to a product as a raw ore is to a finished tool — it requires additional work before it is safe and useful for end users.

### Layer 2 — Training Pipeline

LLMs do not emerge from a single training run. They are built in stages:

```
 Raw Text Corpus
       │
       ▼
 ┌─────────────────────┐
 │  PRETRAINING         │  Next-token prediction on trillions of tokens
 │  (Self-supervised)   │  Produces: Foundation Model
 └─────────────────────┘
       │
       ▼
 ┌─────────────────────┐
 │  SUPERVISED         │  Human-labeled instruction-response pairs
 │  FINE-TUNING (SFT)  │  Teaches the model to follow instructions
 └─────────────────────┘
       │
       ▼
 ┌───────────────────────────────────┐
 │  ALIGNMENT                        │
 │  RLHF  — reward model + PPO       │  Maximises human preference scores
 │  DPO   — direct preference opt.   │  Simpler; no separate reward model
 └───────────────────────────────────┘
```

Key training concepts:

- **RLHF (Reinforcement Learning from Human Feedback):** Humans rank model outputs; a reward model learns those preferences; the LLM is optimised with PPO to score well on the reward model. Produces highly aligned but expensive-to-train models.
- **DPO (Direct Preference Optimisation):** Mathematically equivalent to RLHF but removes the reward model. Takes pairs of (preferred, rejected) completions and fine-tunes directly. Simpler, more stable training.
- **Synthetic Data:** AI-generated training examples used when human-labeled data is scarce or expensive. GPT-4 generating answers for a smaller model to learn from is a canonical example (e.g., Alpaca, Orca).
- **Fine-Tuning:** Further training a pretrained model on a task-specific dataset. Full fine-tuning updates all weights; parameter-efficient methods update only a subset.
- **LoRA / QLoRA:** Low-Rank Adaptation injects small trainable matrices into the attention layers — typically < 1% of total parameters — so fine-tuning fits on a single GPU. QLoRA adds 4-bit quantisation to the frozen base, cutting memory further.
- **Checkpoint:** A snapshot of model weights saved during training. Used for resuming, rollback, or evaluation at intermediate points.
- **Guardrails:** Output filters and classifiers that run before or after generation to detect harmful content, PII, or policy violations. Separate from the model itself.

### Layer 3 — Prompts

A prompt is the text sent to the model. Its structure shapes everything.

```
┌────────────────────────────────────────────┐
│  CONTEXT WINDOW                            │
│                                            │
│  ┌──────────────────────────────────────┐  │
│  │ SYSTEM PROMPT                        │  │  Persona, rules, output format
│  │ "You are a helpful finance assistant"│  │
│  └──────────────────────────────────────┘  │
│  ┌──────────────────────────────────────┐  │
│  │ FEW-SHOT EXAMPLES (optional)         │  │  In-context demonstrations
│  │ User: What is ROE?                   │  │
│  │ Assistant: Return on equity = ...    │  │
│  └──────────────────────────────────────┘  │
│  ┌──────────────────────────────────────┐  │
│  │ CONVERSATION HISTORY (multi-turn)    │  │
│  └──────────────────────────────────────┘  │
│  ┌──────────────────────────────────────┐  │
│  │ USER PROMPT                          │  │  Current user message
│  └──────────────────────────────────────┘  │
└────────────────────────────────────────────┘
              Tokens consumed: 0 ───────── max_tokens
```

- **System Prompt:** The persistent instruction block that establishes the model's persona, constraints, and output format. Injected at the start of every request.
- **User Prompt:** The message from the human turn.
- **Chain-of-Thought (CoT):** Prompting the model to reason step-by-step before producing a final answer. Dramatically improves accuracy on multi-step problems. Can be explicit ("Think step by step.") or implicit (reasoning models do it internally).
- **Zero-Shot:** No examples in the prompt; rely on the model's pretraining. Simpler but less reliable on niche tasks.
- **Few-Shot:** Include 2–8 worked examples in the prompt. The model infers the desired pattern in context. No weight updates required.
- **Prompt Tuning:** A parameter-efficient method where a small set of continuous vectors (soft prompts) are prepended to the input and trained while the base model stays frozen.
- **Context Window:** The maximum number of tokens a model can process in one call (input + output combined). GPT-4 Turbo: 128 K; Gemini 1.5 Pro: 1 M. Longer windows enable multi-document reasoning but increase latency and cost.

### Layer 4 — Inference Parameters

Inference is the process of generating tokens given a prompt. These knobs control that process:

| Parameter | Range | Effect |
|---|---|---|
| **Temperature** | 0.0 – 2.0 | Scales logits before sampling. 0 = greedy (deterministic); 1 = native distribution; > 1 = more random |
| **Top-P (nucleus)** | 0.0 – 1.0 | Sample from the smallest set of tokens whose cumulative probability ≥ P. Lower = safer |
| **Top-K** | 1 – vocab size | Restrict sampling to the K most probable tokens |
| **Max Tokens** | 1 – context limit | Hard ceiling on output length. Controls cost and latency |
| **Seed** | Any integer | Fixed seed → reproducible outputs given same prompt (where supported) |
| **Stop Sequences** | String list | Halt generation when any sequence is produced (e.g., `"\n\n"`, `"</answer>"`) |

**Latency** is end-to-end time from request to final token. It is dominated by two sub-metrics: Time to First Token (TTFT, driven by prefill of the context) and Time Per Output Token (TPOT, driven by autoregressive decode). Long context windows hurt TTFT; large models hurt TPOT.

**Hallucination** is the model generating confident, plausible, but factually incorrect statements. It is a structural consequence of next-token prediction — the model optimises for coherence, not truth. Mitigation strategies include RAG, grounding, and output verification chains.

### Layer 5 — Retrieval-Augmented Generation (RAG)

RAG grounds the model in external facts retrieved at inference time, bypassing the knowledge cutoff without fine-tuning.

```
 User Query
     │
     ▼
 ┌──────────────┐       ┌─────────────────────────┐
 │  Embedding   │──────▶│  Vector DB              │
 │  Model       │       │  (FAISS, Pinecone, etc.) │
 └──────────────┘       └───────────┬─────────────┘
                                    │  Top-K chunks
                                    ▼
                         ┌──────────────────────┐
                         │  Reranker (optional) │
                         └──────────┬───────────┘
                                    │  Reordered chunks
                                    ▼
              ┌──────────────────────────────────────┐
              │  Prompt = System + Retrieved Chunks  │
              │           + User Query               │
              └──────────────────┬───────────────────┘
                                 │
                                 ▼
                           LLM generates answer
```

Core RAG vocabulary:

- **Embedding:** A dense vector representation of text, produced by an encoder model (e.g., `text-embedding-3-large`). Semantically similar texts have high cosine similarity.
- **Chunk:** A fixed-length (by character, token, or sentence) segment of a document used as the unit of retrieval. Chunk size is a critical tuning parameter — too small loses context; too large dilutes relevance signals.
- **Vector DB:** A database optimised for approximate nearest-neighbour (ANN) search over high-dimensional vectors. Examples: Pinecone, Weaviate, Qdrant, pgvector, FAISS.
- **Semantic Search:** Retrieval based on embedding similarity rather than keyword matching. Finds conceptually related documents even when exact terms differ.
- **Indexing:** The process of embedding, chunking, and loading documents into the vector DB. Happens offline, usually triggered by document ingestion pipelines.
- **Reranking:** A second-pass model (often a cross-encoder) that scores query-document pairs for relevance. More accurate than ANN but too slow to run over the full corpus — only applied to the top-K candidates from retrieval.

---

## Build It / In Depth

**Scenario:** You are designing a customer-support chatbot for a SaaS product with 500 markdown help articles. Walk through how each glossary layer materialises in the system.

**Step 1 — Choose the model type**

You need instruction-following for Q&A. A reasoning model would over-engineer simple "How do I reset my password?" queries. Pick an instruction-tuned model (GPT-4o-mini or Claude Haiku) — cheaper and sufficient.

**Step 2 — Decide on adaptation strategy**

The model already knows how to do Q&A. You have 500 articles, not 500,000 support tickets. Fine-tuning is overkill and requires labeled examples you don't have. Use **RAG**.

**Step 3 — Build the indexing pipeline**

```python
# Pseudocode — production would add error handling, batching, metadata
import openai, pinecone, pathlib

client = openai.OpenAI()
index = pinecone.Index("support-docs")

for md_file in pathlib.Path("docs/").glob("**/*.md"):
    text = md_file.read_text()
    # Chunk at 512 tokens with 64-token overlap
    chunks = chunk_text(text, size=512, overlap=64)
    for chunk in chunks:
        vec = client.embeddings.create(
            input=chunk, model="text-embedding-3-small"
        ).data[0].embedding
        index.upsert([(str(hash(chunk)), vec, {"text": chunk})])
```

**Step 4 — Build the retrieval + generation pipeline**

```python
def answer(user_query: str) -> str:
    # Embed the query
    q_vec = client.embeddings.create(
        input=user_query, model="text-embedding-3-small"
    ).data[0].embedding

    # Retrieve top-5 chunks
    results = index.query(vector=q_vec, top_k=5, include_metadata=True)
    context = "\n\n---\n\n".join(r["metadata"]["text"] for r in results["matches"])

    # Compose the prompt
    messages = [
        {"role": "system", "content": (
            "You are a helpful support agent for AcmeSaaS. "
            "Answer only from the provided documentation. "
            "If the answer is not in the docs, say so."
        )},
        {"role": "user", "content": f"Documentation:\n{context}\n\nQuestion: {user_query}"},
    ]

    # Generate
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.2,      # Low: factual, consistent support answers
        max_tokens=512,
        seed=42,              # Reproducible for regression testing
    )
    return resp.choices[0].message.content
```

**Step 5 — Add a guardrail layer**

```python
BLOCKED_TOPICS = ["competitor pricing", "legal advice"]

def safe_answer(user_query: str) -> str:
    if any(t in user_query.lower() for t in BLOCKED_TOPICS):
        return "I can only help with AcmeSaaS product questions."
    raw = answer(user_query)
    # Run a classifier to check for PII in the output before returning
    return redact_pii(raw)
```

**Tuning guidance:**

| Situation | Recommended temperature |
|---|---|
| Factual Q&A, support bots | 0.0 – 0.3 |
| Summarisation, translation | 0.3 – 0.7 |
| Creative writing, brainstorming | 0.7 – 1.2 |
| Never in production | > 1.5 |

---

## Use It

| Capability | Tool / Service | Notes |
|---|---|---|
| Instruction-tuned chat | OpenAI GPT-4o, Anthropic Claude, Google Gemini | Hosted; fastest to ship |
| Open-weight SLM | Meta Llama 3, Microsoft Phi-3, Mistral 7B | Self-hosted; cost control, privacy |
| Embeddings | `text-embedding-3-large`, Cohere `embed-v3`, BGE-M3 | Match embedding model to retrieval task language |
| Vector DB (managed) | Pinecone, Weaviate Cloud, Zilliz | Fully managed ANN |
| Vector DB (self-hosted) | pgvector, Qdrant, Chroma | Lower cost, full data control |
| Reranking | Cohere Rerank, `bge-reranker-v2`, Jina Reranker | Add when RAG recall is high but precision is low |
| Guardrails / safety | Llama Guard, Nvidia NeMo Guardrails, AWS Bedrock Guardrails | Policy enforcement layer |
| LoRA fine-tuning infra | HuggingFace PEFT + TRL, Axolotl, OpenAI fine-tuning API | Use when few-shot prompting saturates |
| Observability | LangSmith, Helicone, Arize Phoenix | Trace prompts, tokens, latency, evals |

---

## Common Pitfalls

- **Fine-tuning when RAG would suffice.** Fine-tuning teaches style and format; RAG injects facts. If the problem is "the model doesn't know our private data," RAG is almost always cheaper, faster to iterate, and easier to update. Reserve fine-tuning for behaviour changes — tone, output schema, domain-specific reasoning patterns.

- **Temperature mismatches between development and production.** Demos often use high temperature (0.9+) for impressive variety. When the same setting ships to production, factual support bots hallucinate freely. Set temperature explicitly in code; never rely on API defaults.

- **Chunk size chosen arbitrarily.** Default chunk sizes (e.g., 1 000 characters) are rarely optimal. A chunk that splits a table in half destroys retrieval quality. Profile retrieval precision at multiple chunk sizes before committing to an indexing strategy.

- **Ignoring the context window budget.** Stuffing 20 retrieved chunks into the prompt can push the conversation history and system prompt into truncation territory. Always budget tokens explicitly: `system + history + retrieved_context + user_query + max_output ≤ context_window`.

- **Treating hallucination as a model bug to fix with prompting.** Hallucination is a structural property of autoregressive generation, not a configuration error. Prompting helps at the margin; the correct architectural fix is grounding — either via RAG, tool calls, or constrained decoding. Do not ship a high-stakes system (medical, legal, financial) relying solely on prompt-based mitigation.

---

## Exercises

1. **Easy:** List the five model types covered in this lesson and write one concrete use-case sentence for each. Then identify which type the public version of ChatGPT most closely represents and why.

2. **Medium:** A team wants to reduce hallucination in their LLM-powered news summariser. They are debating between fine-tuning on curated summaries versus building a RAG pipeline over live news feeds. Draft a one-paragraph recommendation with justification based on the concepts in this lesson.

3. **Hard:** Design a RAG system for a 10 million-document legal case database. Identify the bottlenecks at indexing time, at query time, and in the reranking stage. Propose chunk sizes, embedding model selection criteria, and a reranking strategy. Estimate per-query latency breakdown and identify which component dominates.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Hallucination** | The model is lying or broken | A structural consequence of next-token prediction; the model generates plausible text regardless of truth value |
| **Fine-tuning** | Teaching the model new facts | Updating weights to change behaviour, style, or task format — not for injecting knowledge (use RAG for that) |
| **Temperature** | "Creativity" slider | A divisor on the logits before softmax; higher values flatten the probability distribution, making unlikely tokens more probable |
| **Embedding** | A summary of text | A dense vector in a high-dimensional space where geometric proximity approximates semantic similarity |
| **RAG** | Giving the model access to a database | Retrieving relevant text passages at inference time and appending them to the prompt as grounding context |
| **LoRA** | A way to make models smaller | A parameter-efficient fine-tuning method that injects small trainable rank-decomposition matrices into frozen layers |
| **Context Window** | Memory of past messages | The total token budget for one API call — input plus output combined; once full, oldest tokens are truncated or the call fails |

---

## Further Reading

- [OpenAI Cookbook — Retrieval-Augmented Generation](https://cookbook.openai.com/examples/question_answering_using_embeddings) — canonical RAG walkthrough with real API calls
- [Lilian Weng — "Prompt Engineering" (lilianweng.github.io)](https://lilianweng.github.io/posts/2023-03-15-prompt-engineering/) — comprehensive survey of prompting strategies with empirical analysis
- [HuggingFace PEFT Documentation](https://huggingface.co/docs/peft/index) — LoRA, QLoRA, and prompt tuning in one library; start here for parameter-efficient fine-tuning
- [Pinecone Learning Center — Vector Databases Explained](https://www.pinecone.io/learn/vector-database/) — explains ANN indexing, HNSW, and the retrieval pipeline without assuming ML background
- [Anthropic Model Card (Claude 3)](https://www.anthropic.com/news/claude-3-family) — real-world example of how foundation → alignment → instruction-tuned pipeline is documented at the provider level
