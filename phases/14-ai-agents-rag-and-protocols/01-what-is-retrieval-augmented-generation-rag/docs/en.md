# What is Retrieval-Augmented Generation (RAG)?

> Give the model a library card instead of a bigger brain.

**Type:** Learn
**Prerequisites:** Large Language Models (LLMs) Overview, Vector Databases, Embeddings and Semantic Search
**Time:** ~30 minutes

---

## The Problem

Large language models are trained once, then frozen. GPT-4's training data has a cutoff; so does every other publicly available model. Ask it about an earnings report from last week, a newly published CVE, or your company's internal API docs and it will either hallucinate an answer or admit it doesn't know. The knowledge inside the model is static and general — useful for reasoning, but blind to anything that happened after training, anything proprietary, and anything too niche to appear in the training corpus.

The naive fix is fine-tuning: take a base model and train it further on your private corpus. This costs real money (GPU hours, human labeling), takes days or weeks, and still doesn't scale to knowledge that changes daily. Worse, fine-tuned models are notorious for *forgetting* — the model overwrites general capability while learning specifics.

Retrieval-Augmented Generation solves this differently: instead of baking knowledge into weights, you fetch relevant facts at query time and inject them into the prompt. The model's reasoning engine stays generic and powerful; the facts it reasons over are always current and always specific. The analogy that sticks: you don't memorize an entire law library to become a lawyer — you learn *how to research and reason*, then look things up when a case requires it.

---

## The Concept

### The High-Level Pipeline

RAG has three distinct phases that run at query time:

```
User query
     │
     ▼
┌─────────────────────┐
│   1. EMBED QUERY    │  query → dense vector (e.g., [0.12, -0.87, … 1536 dims])
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   2. RETRIEVE       │  ANN search over vector index → top-k chunks
│   (Vector Store)    │  optionally re-rank with a cross-encoder
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   3. AUGMENT        │  system prompt + retrieved chunks + user query → full context
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   4. GENERATE       │  LLM produces grounded answer
└─────────────────────┘
```

### Offline Indexing (Must Happen First)

Before any query can be answered, you must build the index:

```
Raw documents (PDFs, HTML, Markdown, DB rows, …)
          │
          ▼
    [Chunking]       split into ~256–512 token segments with overlap
          │
          ▼
    [Embedding]      each chunk → dense vector via an embedding model
          │
          ▼
    [Vector Store]   store (vector, chunk text, metadata) as one record
```

This is the *offline* path — run it once per document, or continuously as documents change.

### Why Vectors?

Keyword search (BM25, Elasticsearch) matches exact or stemmed words. If a user asks "how do I revoke a credential?" and your doc says "invalidate an API key", keyword search misses it. Embedding models map semantically similar text to nearby points in high-dimensional space, so the query and the relevant chunk land close together even if they share no words.

### Chunking Strategy Matters More Than People Think

| Strategy | When to use | Watch out for |
|---|---|---|
| Fixed-size (token count) | Simple baseline, low latency | May cut sentences mid-thought |
| Sentence-aware | Narrative text (articles, books) | Sentences can be very short → noisy top-k |
| Recursive character split | General-purpose default | Needs tuning per doc type |
| Document-structure-aware | Code, Markdown, HTML | Parser complexity; worth it for structured docs |
| Sliding window with overlap | Anything where context spans chunk boundaries | Stores duplicate text; increases index size |

Overlap (typically 10–20% of chunk size) prevents useful context from being split across two chunks.

### Retrieval: Dense, Sparse, and Hybrid

| Method | Signal | Strength | Weakness |
|---|---|---|---|
| Dense (vector ANN) | Semantic similarity | Handles paraphrase, synonyms | Slow to cold-start; needs embedding model |
| Sparse (BM25 / TF-IDF) | Exact token match | Fast, no embedding needed | Fails on paraphrase |
| Hybrid (RRF fusion) | Both | Best recall in practice | More moving parts |

Reciprocal Rank Fusion (RRF) merges ranked lists from dense and sparse retrieval without needing score calibration:

```
score_rrf(d) = Σ  1 / (k + rank_i(d))
```

where *k* is a constant (typically 60) and *rank_i* is a document's rank in retrieval list *i*.

### Re-ranking

Top-k ANN results may include marginally relevant chunks. A *cross-encoder re-ranker* (e.g., `cross-encoder/ms-marco-MiniLM-L-6-v2`) scores each (query, chunk) pair jointly — more accurate but O(k) inference calls. Use it after retrieving top-20, then keep the final top-5 for the prompt.

---

## Build It / In Depth

Walk through a minimal but complete RAG system in Python using `sentence-transformers` for embedding, FAISS for the vector index, and the OpenAI API for generation.

### Step 1 — Install Dependencies

```bash
pip install sentence-transformers faiss-cpu openai tiktoken
```

### Step 2 — Chunk and Embed Your Documents

```python
from sentence_transformers import SentenceTransformer
import numpy as np, json, textwrap

CHUNK_SIZE = 400   # characters
OVERLAP    = 80

def chunk_text(text: str) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start += CHUNK_SIZE - OVERLAP
    return chunks

# Load your documents
docs = {
    "handbook.md":  open("handbook.md").read(),
    "api_guide.md": open("api_guide.md").read(),
}

model = SentenceTransformer("all-MiniLM-L6-v2")  # 384-dim, fast

chunks, metadata = [], []
for filename, content in docs.items():
    for i, chunk in enumerate(chunk_text(content)):
        chunks.append(chunk)
        metadata.append({"source": filename, "chunk_id": i})

embeddings = model.encode(chunks, batch_size=64, show_progress_bar=True)
embeddings = embeddings.astype("float32")
print(f"Indexed {len(chunks)} chunks, shape {embeddings.shape}")
```

### Step 3 — Build the FAISS Index

```python
import faiss

dim = embeddings.shape[1]          # 384
index = faiss.IndexFlatIP(dim)     # inner-product (cosine after normalization)

faiss.normalize_L2(embeddings)     # normalize so IP == cosine
index.add(embeddings)

# Persist
faiss.write_index(index, "rag.faiss")
with open("rag_meta.json", "w") as f:
    json.dump({"chunks": chunks, "meta": metadata}, f)
```

### Step 4 — Retrieve at Query Time

```python
import faiss, json
import numpy as np
from sentence_transformers import SentenceTransformer

index   = faiss.read_index("rag.faiss")
store   = json.load(open("rag_meta.json"))
model   = SentenceTransformer("all-MiniLM-L6-v2")

def retrieve(query: str, top_k: int = 5) -> list[dict]:
    q_vec = model.encode([query]).astype("float32")
    faiss.normalize_L2(q_vec)
    scores, indices = index.search(q_vec, top_k)
    results = []
    for score, idx in zip(scores[0], indices[0]):
        results.append({
            "score":  float(score),
            "text":   store["chunks"][idx],
            "source": store["meta"][idx]["source"],
        })
    return results
```

### Step 5 — Augment and Generate

```python
from openai import OpenAI

client = OpenAI()   # reads OPENAI_API_KEY from env

SYSTEM_PROMPT = """\
You are a helpful assistant. Answer the user's question using ONLY the
context provided below. If the answer is not in the context, say so.

Context:
{context}
"""

def answer(query: str) -> str:
    hits    = retrieve(query, top_k=5)
    context = "\n\n---\n\n".join(
        f"[{h['source']}]\n{h['text']}" for h in hits
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system",  "content": SYSTEM_PROMPT.format(context=context)},
            {"role": "user",    "content": query},
        ],
        temperature=0,
    )
    return response.choices[0].message.content

# Try it
print(answer("How do I rotate an API key?"))
```

### What the Full Context Window Looks Like

```
[system]
You are a helpful assistant. Answer using ONLY the context below.
If the answer is not in the context, say so.

Context:
[api_guide.md]
API keys can be invalidated from the dashboard under Settings → Security.
Click "Rotate" next to the key you want to invalidate. A new key is
generated and the old one is immediately rejected by the gateway …

[handbook.md]
Security policy requires rotating credentials every 90 days …

---
[user]
How do I rotate an API key?
```

The model sees exactly what it needs — nothing more.

---

## Use It

### Frameworks and Orchestration

| Tool | Role | When to reach for it |
|---|---|---|
| **LangChain** | Full RAG pipeline, chains, agents | Rapid prototyping; large plugin ecosystem |
| **LlamaIndex** | Document-centric RAG, advanced indexing | Production doc pipelines; better chunking primitives |
| **Haystack** | Production NLP pipelines | Enterprise, modular component design |
| **DSPy** | Programmatic prompt optimization | When you want to optimize retrieval + generation jointly |

### Vector Stores

| Store | Deployment | Strength |
|---|---|---|
| **Pinecone** | Managed cloud | Zero-ops, fast startup |
| **Weaviate** | Self-hosted or cloud | Hybrid search built-in; GraphQL API |
| **Qdrant** | Self-hosted or cloud | High-performance, Rust core |
| **pgvector** | Postgres extension | Already have Postgres; low ops overhead for <10M vecs |
| **FAISS** | In-process library | Research, offline batch, no infra |
| **Chroma** | Embedded / local | Local dev, open-source, LangChain default |
| **OpenSearch k-NN** | Self-hosted / AWS | Teams already running OpenSearch |

### Embedding Models

| Model | Dimensions | Notes |
|---|---|---|
| `text-embedding-3-small` (OpenAI) | 1536 | Good balance of quality and cost |
| `text-embedding-3-large` (OpenAI) | 3072 | Higher quality, 5× cost |
| `all-MiniLM-L6-v2` (SBERT) | 384 | Fast, free, runs on CPU |
| `bge-large-en-v1.5` (BAAI) | 1024 | Best open-source quality (MTEB) |
| `nomic-embed-text-v1.5` | 768 | Apache 2.0, long context (8k tokens) |

### Cloud-Managed RAG

AWS Bedrock Knowledge Bases, Azure AI Search with semantic ranker, and Google Vertex AI Search all wrap the full RAG pipeline — indexing, chunking, embedding, retrieval, generation — behind managed APIs. Reach for them when you don't want to own the infrastructure; accept their chunking defaults before customizing.

---

## Common Pitfalls

- **Chunking too large.** A 2 000-token chunk often buries the relevant sentence in noise. The model is grounded on irrelevant context. Start with 256–400 tokens and measure retrieval precision before increasing.

- **Not measuring retrieval separately from generation.** If your final answers are wrong, you don't know whether retrieval fetched the wrong chunks or the LLM reasoned badly over good chunks. Instrument retrieval recall (does the correct chunk appear in top-k?) independently from answer quality.

- **Embedding model mismatch.** If you embed documents with `text-embedding-3-large` and query with `all-MiniLM-L6-v2`, the vectors live in completely different spaces. Your retrieval will be random noise. Use the *same* model for both.

- **Stale index.** Documents change. If you don't re-embed and re-index changed documents, the model retrieves outdated facts and looks authoritative doing it. Build a document-change pipeline (webhook, polling, CDC) that triggers re-indexing on update.

- **Injecting too many chunks.** Stuffing 20 retrieved chunks into the prompt inflates cost, saturates the context window, and causes the model to lose focus on the most relevant passage (the "lost in the middle" problem). Top-5 after re-ranking is a common production sweet spot; tune based on your context budget.

---

## Exercises

1. **Easy — Trace the pipeline.** For the query "What is the refund policy?", draw the full RAG pipeline from query embedding through final generation. Label each step and identify which components run offline vs. at query time.

2. **Medium — Swap the retriever.** Take the FAISS-based example above and replace it with a hybrid retriever: use BM25 (via `rank_bm25`) for sparse retrieval and the existing FAISS index for dense retrieval, then fuse the ranked lists with RRF. Compare retrieval recall on five test queries before and after the change.

3. **Hard — Add a re-ranker and evaluate.** Build an evaluation harness: create 20 (question, ground-truth-chunk) pairs from your test corpus. Measure top-5 recall before and after adding a `cross-encoder/ms-marco-MiniLM-L-6-v2` re-ranker. Plot precision@1, precision@3, and recall@5 for both configurations and explain where the re-ranker helps and where it doesn't.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **RAG** | "Making the model smarter by giving it docs" | A retrieval pipeline that fetches relevant text at query time and injects it into the LLM's prompt context |
| **Embedding** | A compressed version of text | A dense numerical vector that encodes semantic meaning; nearby vectors represent semantically similar text |
| **Chunking** | Just splitting text into pieces | A deliberate segmentation strategy that balances retrieval granularity against context completeness |
| **Top-k retrieval** | "Return the k best results" | Return the k results with highest similarity score; the quality depends entirely on the embedding space and index type |
| **Re-ranking** | The same as retrieval | A second-pass scoring step that re-orders top-k candidates using a more expensive but more accurate cross-encoder model |
| **Hallucination** | The model making things up randomly | The model generating plausible-sounding text that is factually wrong; RAG reduces this by grounding responses in retrieved evidence |
| **Context window** | Unlimited in modern models | The hard token limit for a single LLM call; retrieved chunks + prompt + answer must fit within it |

---

## Further Reading

- [Original RAG paper — Lewis et al., 2020 (arXiv)](https://arxiv.org/abs/2005.11401) — the paper that coined the term and established the dense retriever + seq2seq generator architecture.
- [LlamaIndex documentation — Building RAG pipelines](https://docs.llamaindex.ai/en/stable/getting_started/concepts/) — production-grade patterns for chunking, indexing, and querying.
- [BEIR Benchmark](https://github.com/beir-cellar/beir) — the standard retrieval evaluation benchmark; use it to compare embedding models on your domain.
- [Pinecone Learning Center — What is RAG?](https://www.pinecone.io/learn/retrieval-augmented-generation/) — practical end-to-end guide with architecture diagrams.
- [Anthropic: Prompt Engineering for RAG](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/long-context-tips) — model-specific guidance on structuring retrieved context for best generation quality.
