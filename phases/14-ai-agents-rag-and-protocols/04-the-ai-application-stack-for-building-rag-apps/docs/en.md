# The AI Application Stack for Building RAG Apps

> RAG quality is a chain — every layer you misunderstand becomes a failure mode you can't debug.

**Type:** Learn
**Prerequisites:** What is RAG, Vector Databases and Similarity Search, Embeddings Explained
**Time:** ~30 minutes

---

## The Problem

A team builds a document Q&A system for their internal knowledge base: 10,000 PDFs, wiki pages, and support tickets. They pick a popular LLM, bolt on a vector database, wire it together over a weekend, and demo it on Monday. It looks impressive. By Thursday, users report it confidently answers questions with completely wrong source material. The team has no idea which part failed — the chunking? the embedding model? the retrieval threshold? the prompt? They can't fix what they can't isolate.

This is the central challenge of RAG engineering: the pipeline has five distinct layers, each with its own failure modes, and they interact non-trivially. An embedding model mismatch silently degrades retrieval. A bad chunking strategy makes perfect embedding irrelevant. A retrieval strategy that returns too many documents overwhelms the LLM's context window. None of these failures produce a thrown exception — they produce quietly wrong answers.

Understanding the AI application stack for RAG means knowing what each layer does, why it exists, how layers depend on each other, and what tool to pick for each job. Without that map, you're debugging by guessing.

---

## The Concept

A RAG system is not a single component — it is a five-layer data pipeline with an inference step bolted onto the end. Each layer has one job. Get it wrong, and downstream layers compensate poorly or silently produce garbage.

```
┌────────────────────────────────────────────────────────┐
│                  USER QUERY                            │
└──────────────────────┬─────────────────────────────────┘
                       │
          ┌────────────▼────────────┐
          │   ORCHESTRATION LAYER   │  ← LangChain, LlamaIndex,
          │  (Framework / Router)   │    Haystack
          └──────┬──────────┬───────┘
                 │          │
    ┌────────────▼──┐  ┌────▼──────────────┐
    │  EMBED QUERY  │  │  VECTOR STORE     │  ← Pinecone, Weaviate,
    │  (Embedding   │  │  (Similarity      │    pgvector, Chroma
    │   Model)      │  │   Search)         │
    └────────────┬──┘  └────┬──────────────┘
                 │          │ top-k chunks
                 └────┬─────┘
          ┌───────────▼──────────────┐
          │    GENERATION LAYER      │  ← GPT-4o, Claude, Gemini,
          │    (LLM + Prompt)        │    Llama 3, Mistral
          └───────────┬──────────────┘
                      │
               GROUNDED ANSWER

━━━━━━━━━━━━━━━━ INGESTION PATH (offline) ━━━━━━━━━━━━━━━━

  Raw Sources  →  Extraction  →  Chunking  →  Embedding  →  Vector Store
  (PDFs, HTML,    (Llamaparse,   (Strategy    (Embedding    (Index +
   DB, APIs)       Firecrawl)     + Size)      Model)        Metadata)
```

### Layer 1 — Data Extraction

Raw sources rarely arrive clean. PDFs have multi-column layouts, tables, footnotes, headers. HTML mixes nav, ads, and content. The extraction layer's job is to produce clean, plain text (or structured markdown) from each source type.

This matters more than most teams realize. An OCR error in a policy document propagates through embedding and surfaces as a confidently wrong answer. Garbage in, garbage out — but at embedding time, not runtime, so it's hard to catch late.

### Layer 2 — Chunking (often treated as part of extraction)

Before embedding, text must be split into chunks. Chunk size controls the precision/recall tradeoff at retrieval time:

| Chunk Size | Retrieval Behavior | Risk |
|---|---|---|
| Too small (50-100 tokens) | High precision, missing context | Fragments answer; LLM lacks surrounding text |
| Moderate (256-512 tokens) | Balanced | Good default starting point |
| Too large (1000+ tokens) | High recall, low precision | Irrelevant text fills context window; costs more |

Chunking strategy matters too: naive sentence-boundary splitting often cuts mid-thought. Semantic chunking (split on topic shift) or document-structure chunking (split on H2/H3 boundaries) tends to produce better retrieval.

### Layer 3 — Embeddings

Embeddings convert a text chunk into a high-dimensional vector (typically 384–3072 dimensions). At query time, the query is embedded with the **same model**, and nearest-neighbor search finds the most semantically similar chunks.

Three things matter enormously:

1. **Model consistency**: Index-time and query-time must use the identical embedding model. Switching models without re-indexing is a silent disaster.
2. **Domain fit**: General-purpose models (OpenAI `text-embedding-3-small`) work well across domains. For code, legal text, or medical literature, domain-specific or fine-tuned models can improve recall by 15-30%.
3. **Embedding dimensionality vs. cost**: Larger embeddings (3072d vs 512d) capture more nuance but cost more to store and search. Many systems use Matryoshka Representation Learning (MRL) models that let you truncate vectors without retraining.

### Layer 4 — Vector Storage and Retrieval

Vector databases store the embedded chunks and serve approximate nearest-neighbor (ANN) queries efficiently. At scale, exact k-NN search over millions of vectors is too slow — ANN indexes (HNSW, IVF) trade a small accuracy loss for orders-of-magnitude speedup.

Beyond pure vector search, most production RAG systems add:
- **Metadata filtering**: filter by date, source, user permissions before vector search
- **Hybrid search**: combine BM25 keyword search with vector search, fuse with RRF (Reciprocal Rank Fusion)
- **Reranking**: a cross-encoder model reorders top-k retrieved chunks to improve precision before passing to the LLM

### Layer 5 — Orchestration Frameworks

Frameworks like LangChain and LlamaIndex exist to wire the layers together and manage the complexity:
- Prompt templates and context injection
- Memory across conversation turns
- Routing queries to different retrieval pipelines
- Chaining multiple LLM calls (query expansion, summarization before generation)
- Streaming, callbacks, and observability hooks

They are not magic — they are glue code with opinions. When their opinions match your use case, they accelerate development. When they don't, they add indirection that's harder to debug than writing the pipeline yourself.

### Layer 6 — LLM (Generation)

The LLM receives: the user query + the retrieved chunks (the "context") + a system prompt instructing it to answer using only the context. Its job is synthesis, not retrieval. If retrieval is good, even a smaller model can produce excellent answers. If retrieval is bad, a better LLM merely hallucinates more fluently.

---

## Build It

Here is a minimal RAG pipeline in Python using `langchain` and `chromadb`. It builds from ingestion through query.

**Install dependencies:**

```bash
pip install langchain langchain-community langchain-openai chromadb pypdf tiktoken
```

**Step 1 — Load and split a document:**

```python
from langchain.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter

loader = PyPDFLoader("policy_document.pdf")
pages = loader.load()  # list of Document objects, one per page

splitter = RecursiveCharacterTextSplitter(
    chunk_size=512,
    chunk_overlap=64,          # 64-token overlap to preserve cross-chunk context
    separators=["\n\n", "\n", ". ", " "],
)
chunks = splitter.split_documents(pages)
print(f"Split into {len(chunks)} chunks")
```

**Step 2 — Embed and store:**

```python
from langchain_openai import OpenAIEmbeddings
from langchain.vectorstores import Chroma

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

vectorstore = Chroma.from_documents(
    documents=chunks,
    embedding=embeddings,
    persist_directory="./chroma_db",
    collection_name="policy_docs",
)
vectorstore.persist()
print("Index built.")
```

**Step 3 — Retrieval and generation:**

```python
from langchain_openai import ChatOpenAI
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate

# Load existing index
vectorstore = Chroma(
    persist_directory="./chroma_db",
    embedding_function=embeddings,
    collection_name="policy_docs",
)

retriever = vectorstore.as_retriever(
    search_type="mmr",          # Maximum Marginal Relevance: diverse, non-redundant results
    search_kwargs={"k": 5, "fetch_k": 20},
)

prompt = PromptTemplate.from_template("""
You are an assistant that answers questions using only the provided context.
If the answer is not in the context, say "I don't have that information."

Context:
{context}

Question: {question}
Answer:
""")

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

chain = RetrievalQA.from_chain_type(
    llm=llm,
    retriever=retriever,
    chain_type="stuff",         # "stuff" = inject all chunks into a single prompt
    chain_type_kwargs={"prompt": prompt},
    return_source_documents=True,
)

result = chain.invoke({"query": "What is the vacation policy for remote employees?"})
print(result["result"])
for doc in result["source_documents"]:
    print(f"  Source: {doc.metadata.get('source', 'unknown')}, page {doc.metadata.get('page', '?')}")
```

**Adding hybrid search (BM25 + vector) with a reranker:**

```python
from langchain.retrievers import BM25Retriever, EnsembleRetriever
from langchain.retrievers.contextual_compression import ContextualCompressionRetriever
from langchain_cohere import CohereRerank  # pip install langchain-cohere

bm25_retriever = BM25Retriever.from_documents(chunks, k=10)
vector_retriever = vectorstore.as_retriever(search_kwargs={"k": 10})

# Reciprocal Rank Fusion hybrid
ensemble = EnsembleRetriever(
    retrievers=[bm25_retriever, vector_retriever],
    weights=[0.4, 0.6],        # tune: higher weight on vector for semantic queries
)

# Rerank top results with a cross-encoder
compressor = CohereRerank(model="rerank-english-v3.0", top_n=5)
compressed_retriever = ContextualCompressionRetriever(
    base_compressor=compressor,
    base_retriever=ensemble,
)
```

The pipeline now: BM25 finds keyword matches → vector search finds semantic matches → RRF merges them → Cohere reranker reorders by relevance → top 5 go to the LLM.

---

## Use It

### Choosing Tools at Each Layer

| Layer | Lightweight / Local | Managed / Production | When to Upgrade |
|---|---|---|---|
| **Extraction** | PyPDF, BeautifulSoup, Unstructured | Llamaparse, AWS Textract, Google Document AI | Complex PDFs with tables, forms, scanned images |
| **Embeddings** | Ollama + `nomic-embed-text` | OpenAI `text-embedding-3-small/large`, Cohere Embed v3 | Domain-specific corpus; run cost benchmarks |
| **Vector Store** | Chroma (local), FAISS | Pinecone, Weaviate, Qdrant, pgvector | >1M vectors, multi-tenancy, hybrid search, metadata filtering at scale |
| **Orchestration** | Direct API calls | LangChain, LlamaIndex, Haystack | When chaining 3+ steps or need memory/streaming/callbacks |
| **LLM** | Ollama + Llama 3 / Mistral | OpenAI GPT-4o, Anthropic Claude 3.5, Google Gemini 1.5 | Larger context window, better instruction following |
| **Reranking** | Cross-encoder via sentence-transformers | Cohere Rerank, Jina Reranker | Retrieval precision below ~70% |

### Key Architectural Patterns

**Naive RAG** (baseline): chunk → embed → retrieve top-k → stuff into prompt. Works for clean, factual corpora. Breaks on ambiguous queries.

**Advanced RAG**: adds query rewriting, HyDE (generate a hypothetical answer and embed that for retrieval), hybrid search, and reranking. Significant accuracy gains at moderate complexity cost.

**Modular RAG**: treats each step as a swappable module (different retrievers per query type, different LLMs for summarization vs. generation). Maximum flexibility; highest operational complexity.

### When pgvector is Enough

If you already run Postgres, `pgvector` gives you vector similarity search without adding a new infra dependency. Use it when:
- Corpus is under ~5M vectors
- You need strong ACID semantics alongside vector data
- Your team doesn't want to operate another database

Switch to Pinecone/Weaviate/Qdrant when you need multi-tenancy, sub-50ms P99 at 100M+ vectors, or advanced filtering across large namespaces.

---

## Common Pitfalls

- **Using different embedding models at index time vs. query time.** This is the single most common silent failure. The vectors are incomparable; you get random retrieval. Always version-pin your embedding model and re-index when you upgrade it.

- **Chunking without overlap.** If a sentence spans a chunk boundary, its meaning is split across two chunks and neither retrieves with full precision. A 10-20% overlap (relative to chunk size) is a cheap fix with consistent benefit.

- **Returning too many chunks to the LLM.** More context is not always better. At >4,000 tokens of retrieved context, most LLMs struggle with the "lost in the middle" problem — they under-attend to information in the middle of a long context. Retrieve broadly, rerank, then pass only the top 3-5 chunks.

- **Skipping metadata.** Storing chunks as pure text means you can't filter by date, author, or department at retrieval time. Tag every chunk with its source, timestamp, and any structural metadata at index time. You cannot add this retroactively without re-indexing.

- **Evaluating only end-to-end answer quality.** When answers degrade, you need to know if the retrieval layer or the generation layer failed. Evaluate retrieval precision (were the right chunks returned?) independently from generation quality (did the LLM use them correctly?). Tools like RAGAS and TruLens instrument both.

---

## Exercises

1. **Easy** — Take a 10-page PDF and build a working RAG pipeline using the code in "Build It". Then change `chunk_size` from 256 to 1024 tokens and compare which chunk size produces better answers for summary questions vs. specific factual questions. Write down your observations.

2. **Medium** — Add metadata to each chunk (at minimum: source filename, page number, ingest date). Then modify the retriever to filter only chunks ingested in the last 30 days. Verify that a query returns only recent results. Explain what this would look like in Chroma's filter syntax vs. pgvector's SQL WHERE clause.

3. **Hard** — Implement an evaluation harness using RAGAS. Generate 20 question-answer pairs from your corpus, then measure Context Recall and Answer Faithfulness. Now swap the embedding model from `text-embedding-3-small` to `nomic-embed-text` (via Ollama, without changing anything else) and compare the two models' retrieval metrics. Write a 200-word analysis of the tradeoffs.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **RAG** | A feature you add to a chatbot | A retrieval pipeline that grounds LLM generation in external documents at inference time; the LLM itself is just the last step |
| **Vector Database** | A special kind of database for AI | A database with an ANN index optimized for high-dimensional similarity search; most also support structured metadata and hybrid search |
| **Embedding** | What you do before vector search | A learned, fixed-length floating-point vector representing the semantic content of a text; embedding quality directly determines retrieval quality |
| **Chunking** | Just splitting text into pieces | A strategy for dividing documents into units that are coherent enough to embed meaningfully and small enough to fit in a context window with other chunks |
| **Reranking** | A fancier embedding | A second-pass cross-encoder model that scores (query, chunk) pairs jointly for relevance; much more accurate than cosine similarity but ~100x slower, so applied only to a small candidate set |
| **LlamaIndex / LangChain** | The AI layer that does RAG | Orchestration frameworks; they manage the plumbing between layers — they do not perform retrieval or generation themselves |
| **Context Window** | How much the LLM can read | The maximum token count the LLM processes in a single forward pass; the retrieved chunks + the prompt + the response must all fit within it |

---

## Further Reading

- **LangChain RAG documentation** — [https://python.langchain.com/docs/use_cases/question_answering/](https://python.langchain.com/docs/use_cases/question_answering/) — end-to-end RAG tutorials with code for the main vector stores
- **LlamaIndex Getting Started** — [https://docs.llamaindex.ai/en/stable/getting_started/concepts/](https://docs.llamaindex.ai/en/stable/getting_started/concepts/) — covers the index, query engine, and retriever abstractions clearly
- **RAGAS: Automated Evaluation of RAG Pipelines** — [https://docs.ragas.io/en/stable/](https://docs.ragas.io/en/stable/) — the standard library for measuring context precision, recall, and answer faithfulness
- **"Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks" (Lewis et al., 2020)** — [https://arxiv.org/abs/2005.11401](https://arxiv.org/abs/2005.11401) — the original RAG paper; still the best single document for understanding the design rationale
- **Pinecone Learning Center: Chunking Strategies** — [https://www.pinecone.io/learn/chunking-strategies/](https://www.pinecone.io/learn/chunking-strategies/) — practical guide comparing fixed-size, recursive, semantic, and document-structure chunking with retrieval accuracy benchmarks
