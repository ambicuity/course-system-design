# RAG vs Fine-tuning: Which one should you use?

> Give a model new knowledge at query time, or bake it into the weights — the choice defines your cost, freshness, and failure mode.

**Type:** Learn
**Prerequisites:** How LLMs Work (token prediction, context window), Vector Databases and Embeddings, Introduction to RAG
**Time:** ~25 minutes

---

## The Problem

You have a capable foundation model — GPT-4, Claude, Llama 3 — but it doesn't know your company's internal documentation, your product's latest API, or the proprietary data that makes your answers valuable. Out of the box it hallucinates, cites stale information, and misses domain-specific terminology.

Two paths fix this. The first is **Retrieval-Augmented Generation (RAG)**: at query time, you fetch relevant chunks from an external store and inject them into the prompt. The model never changes; the knowledge lives outside it. The second is **fine-tuning**: you run additional training passes on domain data so that knowledge is encoded directly into the model's weights. The knowledge lives inside it.

Both improve a model's usefulness on a specific domain. But they do so by solving fundamentally different problems, have opposite cost curves, and fail in opposite ways. Choosing wrong means paying 10× more than you need to, rebuilding your pipeline six months later, or shipping a product that gets confidently wrong answers. This lesson gives you a decision framework so you choose right the first time.

---

## The Concept

### What RAG actually does

RAG adds a **retrieval step** before generation. When a user sends a query, the system:

1. Embeds the query into a vector.
2. Searches a vector store (or hybrid BM25 + vector index) for the top-k most semantically similar document chunks.
3. Inserts those chunks into the prompt as context.
4. Sends the augmented prompt to the LLM.
5. The LLM generates an answer grounded in the retrieved chunks.

```
User query
    │
    ▼
[Embed query]
    │
    ▼
[Vector Search] ──► [Document Store]
    │                 (PDFs, wikis, DBs)
    ▼
Top-k chunks
    │
    ▼
[Build prompt: system + chunks + query]
    │
    ▼
[LLM] ──► Answer (with citations)
```

The model weights are **never touched**. You can swap the model tomorrow, update a document tonight, and the change is live on the next query. The knowledge source is transparent and auditable — you know exactly which chunks grounded each answer.

**What RAG solves:** Knowledge that changes over time, proprietary facts the model was never trained on, grounding and citation requirements, strict access control over which users see which content.

**What RAG does not solve:** How the model reasons, how it formats outputs for a specific task, its tone or persona, or its vocabulary for a specialized domain. If your model calls a surgical instrument by its consumer name instead of the clinical term, no retrieval step fixes that.

---

### What fine-tuning actually does

Fine-tuning continues the training process on a smaller, domain-specific dataset. You provide examples — usually (prompt, completion) pairs — and run supervised learning with a reduced learning rate so the model adapts without catastrophically forgetting its pretraining.

```
Domain dataset
(prompt, completion) pairs
         │
         ▼
   [Gradient descent]
   [on frozen base model]
         │
         ▼
   Fine-tuned model weights
         │
         ▼
[Inference: no retrieval needed]
    User query ──► Fine-tuned LLM ──► Answer
```

The fine-tuned model internalizes patterns: terminology, reasoning style, output format, tone, and domain-specific relationships. It can answer common questions from memory without any retrieved context — lower latency, lower token cost per query, consistent behavior.

**What fine-tuning solves:** Teaching the model *how* to respond (format, style, persona), internalizing stable knowledge that never changes, improving fluency in specialized jargon, and reducing the cost of inference when retrieval would otherwise add 1000+ tokens of context every call.

**What fine-tuning does not solve:** Knowledge that changes after training. Fine-tuned weights are a snapshot. A policy that changes quarterly means a retraining run every quarter. It also does not solve traceability — you cannot easily explain *why* a fine-tuned model gave a specific answer.

---

### Side-by-side comparison

| Dimension | RAG | Fine-tuning |
|---|---|---|
| Knowledge location | External store (vector DB, SQL, APIs) | Model weights |
| Knowledge freshness | Real-time — update the store | Static — requires retraining |
| Setup cost | Medium (embedding pipeline, vector DB) | High (labeled data, GPU compute) |
| Per-query cost | Higher (retrieval + longer prompts) | Lower (short prompts, no retrieval) |
| Latency | Higher (retrieval adds ~50–200 ms) | Lower |
| Interpretability | High — cite the source chunks | Low — weights are opaque |
| Best for | Factual recall, dynamic knowledge | Style, format, tone, stable skills |
| Failure mode | Wrong chunk retrieved → wrong answer | Hallucination of stale or missing data |
| Iteration speed | Fast — edit a document, done | Slow — collect data, train, evaluate |
| Data requirements | Documents (unstructured OK) | Labeled (prompt, completion) pairs |

---

### The fundamental insight

RAG and fine-tuning operate on **different axes**:

- RAG extends **what the model knows** (knowledge retrieval).
- Fine-tuning changes **how the model behaves** (skill and style).

This means they are not mutually exclusive. Many production systems use both: fine-tune first to instill the right reasoning style and output format, then add RAG so the fine-tuned model always has access to current facts.

```
         │ Knowledge changes?
         │
    YES  │  NO
    ─────┼──────
     RAG │  Fine-tune
         │
         └─ Both if: style matters AND knowledge is dynamic
```

---

### The cost curves

For a content-heavy Q&A system, assume each RAG query adds ~800 tokens of retrieved context. At GPT-4 pricing that is ~$0.024 per query in context alone. At 1 million queries/day that is $24,000/day — just for context injection.

Fine-tuning a Llama 3 8B model on a few thousand examples costs roughly $200–$500 on a cloud GPU. After that, every inference is cheaper because you no longer inject long context. The crossover point: if you have stable knowledge and high query volume, fine-tuning pays for itself quickly. If knowledge changes daily, fine-tuning never pays off because you are always retraining.

---

## Build It / In Depth

### Decision procedure

Work through this checklist in order. Stop at the first "yes."

```
1. Does the knowledge change more than once per quarter?
   YES → RAG (fine-tuning is too slow to keep up)

2. Do you need citations / source attribution?
   YES → RAG (weights don't store provenance)

3. Do you need strict access control (user A cannot see doc B)?
   YES → RAG (filter at retrieval time; weights can't enforce this)

4. Is the problem about output style, format, or persona?
   YES → Fine-tune (RAG cannot change how the model reasons)

5. Is query volume > 100k/day and knowledge is stable?
   YES → Fine-tune or fine-tune + small RAG (cost optimization)

6. Is labeled data scarce (< 500 examples)?
   YES → RAG (fine-tuning needs enough data to generalize)

DEFAULT → Start with RAG. Introduce fine-tuning when you have enough
          data and a clear behavioral problem that retrieval can't fix.
```

---

### Worked example: Internal support bot

**Scenario:** A software company wants an AI assistant that answers questions about its internal engineering handbook (500 pages, updated monthly) and its product APIs (versioned, updated weekly).

**Step 1 — identify knowledge type:**
- The handbook and API docs change frequently (monthly/weekly).
- Answers require citing a specific section or version.
- Engineers with different roles should see different docs.

**Verdict: RAG.**

```python
# Simplified RAG pipeline (pseudocode)

from openai import OpenAI
from qdrant_client import QdrantClient

client = OpenAI()
qdrant = QdrantClient("localhost", port=6333)

def answer(user_query: str, user_role: str) -> str:
    # 1. Embed the query
    embedding = client.embeddings.create(
        model="text-embedding-3-small",
        input=user_query
    ).data[0].embedding

    # 2. Search with role-based filter
    results = qdrant.search(
        collection_name="handbook",
        query_vector=embedding,
        query_filter={"must": [{"key": "role", "match": {"value": user_role}}]},
        limit=5
    )

    # 3. Build the prompt
    context = "\n\n".join(r.payload["text"] for r in results)
    prompt = f"""You are an internal support assistant.
Use ONLY the context below. Cite the source section.

CONTEXT:
{context}

QUESTION: {user_query}
"""

    # 4. Generate
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content
```

**Step 2 — where would fine-tuning add value?**
After RAG is live, the team notices the model's tone is too generic — engineers want terse, code-first answers, not marketing prose. That is a **behavioral** problem. Now fine-tune on 300 curated (question, ideal-terse-answer) pairs. The fine-tuned model + RAG pipeline now has both fresh knowledge and the right personality.

---

### Worked example: Medical coding assistant

**Scenario:** A healthcare company wants to map clinical notes to ICD-10 billing codes. The ICD-10 codebook has 70,000+ codes, is updated annually, and the mapping task requires specialized reasoning patterns.

**Step 1 — identify knowledge type:**
- ICD-10 codes change once per year (stable enough to train on).
- The reasoning pattern (note → code) is a learnable skill.
- Volume is high: 50,000 notes/day.

**Verdict: Fine-tune** (with a small RAG layer for edge-case code lookups).

Fine-tuning teaches the model *how* to map symptoms to codes. RAG handles the long tail of rare codes that appear only a few times in training data — retrieve the official code description at query time when confidence is low.

---

### Estimating fine-tuning data requirements

| Task complexity | Minimum examples | Recommended |
|---|---|---|
| Style / tone shift | 100–300 | 500 |
| Domain vocabulary | 300–500 | 1,000 |
| Complex reasoning pattern | 1,000–3,000 | 5,000+ |
| New capability (not in base model) | Rarely feasible | — |

If you cannot reach minimum examples, fine-tuning will overfit or fail to generalize. Use RAG with few-shot examples in the prompt instead.

---

## Use It

### RAG tooling landscape

| Tool | Role | When to use |
|---|---|---|
| LangChain / LlamaIndex | RAG orchestration frameworks | Rapid prototyping, standard pipelines |
| Qdrant, Weaviate, Pinecone | Vector databases | Production vector search |
| Elasticsearch / OpenSearch | Hybrid BM25 + vector | When keyword precision matters alongside semantic search |
| pgvector | Postgres extension | When you already run Postgres and scale is modest |
| AWS Bedrock Knowledge Bases | Managed RAG | Fully managed, AWS-native, low ops overhead |
| Azure AI Search | Managed RAG + hybrid | Azure-native; strong enterprise access control |
| Google Vertex AI Search | Managed RAG | GCP-native, strong for unstructured docs |

### Fine-tuning tooling landscape

| Tool | Role | When to use |
|---|---|---|
| OpenAI fine-tuning API | Fine-tune GPT-3.5/4o-mini | Fastest path for OpenAI users; no GPU needed |
| Together AI / Replicate | Fine-tune open models | Llama, Mistral, etc.; cost-effective GPU rental |
| Axolotl / LLaMA-Factory | OSS fine-tuning frameworks | Full control over training loop; on-prem |
| QLoRA / LoRA | Parameter-efficient fine-tuning | Reduce GPU memory by 4–8×; train on consumer hardware |
| Hugging Face TRL | RLHF / SFT library | When you need preference tuning (DPO, PPO) alongside SFT |
| AWS SageMaker | Managed training | Enterprise MLOps, integrated with AWS infra |

### When cloud-managed RAG makes sense

If your team has no ML engineers and the knowledge base is a set of PDFs, start with a managed offering (Bedrock Knowledge Bases, Azure AI Search). You upload documents, the service handles chunking, embedding, and retrieval, and you call an API. You trade control for speed-to-production.

---

## Common Pitfalls

- **Fine-tuning for factual recall.** Teams fine-tune a model on their product FAQ expecting it to memorize the answers. It partially works at first, then the FAQ changes and the model confidently returns outdated information. Use RAG for facts. Fine-tune for behavior.

- **RAG with no re-ranking.** Embedding similarity is not the same as answer relevance. The top-1 cosine result is often not the best chunk. Add a cross-encoder re-ranker (e.g., Cohere Rerank, BGE re-ranker) to sort the top-k results before injecting them into the prompt. Without it, retrieval noise compounds into generation errors.

- **Chunking too coarsely or too finely.** Chunks of 5,000 tokens defeat the purpose of retrieval — you're back to injecting entire documents. Chunks of 50 tokens lose context and return orphaned sentences. Target 300–600 tokens with ~20% overlap between adjacent chunks, and always include the document title and section heading as metadata.

- **Assuming fine-tuning is a one-time event.** Once you fine-tune, you own the retraining loop. Every time the base model updates (OpenAI releases a new GPT-4o checkpoint), your fine-tune may need to be re-run against the new base. Build this into your ML ops budget and timeline.

- **Skipping evaluation.** Both approaches need systematic eval before shipping. For RAG, measure retrieval recall (does the right chunk appear in top-k?) and answer faithfulness (does the LLM answer match the retrieved context?). For fine-tuning, hold out a test set before training — never evaluate on training examples. Tools: RAGAS for RAG evaluation, Eleuther lm-eval-harness for fine-tuned models.

---

## Exercises

1. **Easy** — You are building a customer support chatbot for a SaaS product. Your knowledge base is a 200-page help center that your docs team updates every two weeks. New features ship monthly. Write a one-paragraph justification for which approach you would use and why.

2. **Medium** — A legal tech startup wants to build a contract review tool. It needs to identify non-standard clauses by comparing them to a library of 10,000 standard clause templates (which rarely change). Response latency must be under 300 ms and the system will handle 20,000 contracts per day. Design the high-level architecture: would you use RAG, fine-tuning, or both? Justify the cost trade-off.

3. **Hard** — You have a fine-tuned model for a medical Q&A product. A regulatory change means 15% of the training data is now incorrect. Describe a remediation strategy that avoids a full retraining run. Consider: continued fine-tuning on corrected data only, RAG to override stale weight knowledge, prompt-level guardrails, and hybrid approaches. What are the risks of each?

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Fine-tuning | Fully retraining a model from scratch | Continuing training on a pretrained model with a small domain dataset and a reduced learning rate; the base weights are the starting point, not discarded |
| RAG | Asking the model to search the web | Injecting retrieved context chunks into the prompt *before* generation; no web browsing, just a vector or keyword search against a private index you control |
| Embeddings | A fancy way of saying "summarize text" | Dense floating-point vectors where semantic similarity is measurable as cosine distance; they are not summaries — they are coordinate representations in high-dimensional space |
| Context window | Infinite memory the model can use | A hard token limit (e.g., 128k) on how much text the model can attend to at once; longer context adds latency and cost, and attention quality degrades at extreme lengths |
| LoRA / QLoRA | A cheaper version of fine-tuning that is worse | A parameter-efficient technique that trains small rank-decomposition matrices attached to frozen base weights; quality is on par with full fine-tuning for most tasks, at a fraction of the memory cost |
| Hallucination | The model is lying | The model is generating plausible-sounding text based on statistical patterns, with no mechanism for verifying truth; RAG reduces it by grounding generation in retrieved facts, but doesn't eliminate it |
| Knowledge cutoff | The model knows nothing after a date | The date after which the training corpus ends; RAG sidesteps this for domain knowledge, but the model's general world understanding still reflects the cutoff |

---

## Further Reading

- **"Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"** — the original RAG paper by Lewis et al. (2020): https://arxiv.org/abs/2005.11401
- **OpenAI Fine-tuning Guide** — authoritative docs on when and how to fine-tune GPT models, including data formatting and evaluation: https://platform.openai.com/docs/guides/fine-tuning
- **RAGAS: Evaluation Framework for RAG Pipelines** — automated metrics for retrieval recall, answer faithfulness, and context precision: https://docs.ragas.io
- **"LoRA: Low-Rank Adaptation of Large Language Models"** — the foundational paper for parameter-efficient fine-tuning: https://arxiv.org/abs/2106.09685
- **LlamaIndex RAG Best Practices** — practical chunking strategies, re-ranking, and hybrid search patterns with code examples: https://docs.llamaindex.ai/en/stable/optimizing/production_rag/
