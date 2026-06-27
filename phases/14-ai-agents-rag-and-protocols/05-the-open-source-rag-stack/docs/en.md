# The Open Source RAG Stack

> Every layer you own is a layer you can tune — and a layer you can break.

**Type:** Learn
**Prerequisites:** Vector Databases, Embeddings and Similarity Search, LLM Fundamentals
**Time:** ~35 minutes

---

## The Problem

A large language model trained on a public corpus has no idea what is in your internal knowledge base, your product documentation, or the support ticket filed this morning. Fine-tuning can encode new knowledge but it is expensive, slow to iterate, and bakes facts into weights at training time — you cannot patch a weight the moment a policy changes. Prompt stuffing (injecting raw documents into the context window) works for small data sets, but breaks down when relevant knowledge spans thousands of pages and context windows cost money per token.

Retrieval-Augmented Generation (RAG) solves this by splitting the problem: store knowledge externally, retrieve only the relevant pieces at query time, then hand those pieces to the LLM as grounded context. The model generates from evidence, not from memorised hallucination. The knowledge base is live — update a document and the next query sees the new version automatically.

The catch is that "RAG" is not a single product. It is a pipeline of seven distinct responsibilities — ingestion, embedding, storage, retrieval, ranking, orchestration, and presentation. Each responsibility has multiple open-source contenders. Choosing the wrong tool for one layer, or connecting the layers incorrectly, produces a system that is slow, inaccurate, or operationally fragile. This lesson maps the full stack, explains what each layer actually does, and gives you the mental model to pick and assemble the pieces confidently.

---

## The Concept

### The Seven-Layer Architecture

A production RAG system has a clear separation of concerns across seven layers. Below is the canonical stack from bottom to top:

```
┌─────────────────────────────────────────────────────┐
│  7. Frontend / Application Layer                     │
│     (NextJS, SvelteKit, Streamlit, Gradio)          │
├─────────────────────────────────────────────────────┤
│  6. LLM Orchestration / Framework Layer             │
│     (LangChain, LlamaIndex, Haystack, DSPy)        │
├─────────────────────────────────────────────────────┤
│  5. Large Language Models                           │
│     (Llama 3, Mistral, Gemma, Phi-3, Qwen)        │
├─────────────────────────────────────────────────────┤
│  4. Retrieval & Reranking Layer                     │
│     (BM25, FAISS, Hybrid Search, Cross-Encoders)   │
├─────────────────────────────────────────────────────┤
│  3. Vector Store                                    │
│     (Weaviate, Milvus, pgvector, Chroma, Qdrant)  │
├─────────────────────────────────────────────────────┤
│  2. Embedding Model                                 │
│     (Sentence-Transformers, Nomic, BGE, JinaAI)   │
├─────────────────────────────────────────────────────┤
│  1. Ingest & Data Processing Layer                  │
│     (Airflow, NiFi, Unstructured, LangChain loaders│
└─────────────────────────────────────────────────────┘
```

Data flows in two separate paths:

**Offline (indexing) path**: raw documents → ingest → embed → store in vector DB.  
**Online (query) path**: user query → embed query → retrieve chunks → rerank → inject into prompt → LLM generates → return to frontend.

### Layer 1 — Ingest & Data Processing

This layer extracts raw text from heterogeneous sources (PDFs, HTML, DOCX, databases, wikis, Slack exports), cleans it, chunks it into segments the embedding model can handle, and hands those chunks to the embedding layer.

**Chunking strategy is critical.** Chunks that are too small lose context; chunks too large dilute the relevance signal. Common strategies:

| Strategy | How it works | Best for |
|---|---|---|
| Fixed-size | Split every N tokens with overlap | Simple text, fast to implement |
| Sentence / paragraph | Split on sentence boundaries | Prose documents |
| Recursive character | Try `\n\n`, then `\n`, then space | Mixed content |
| Semantic | Embed sentences, split where cosine similarity drops | Dense technical docs |
| Document-aware | Respect headings, sections, tables | Structured docs (Markdown, HTML) |

An overlap of ~10–20% of the chunk size (e.g., 50 tokens overlap on 512-token chunks) prevents context from being cut at chunk boundaries.

**Key tools**: `unstructured` (handles 25+ file types), LangChain document loaders, LlamaIndex node parsers, Apache Airflow / Kubeflow for orchestrated batch pipelines, Apache NiFi for streaming ingestion.

### Layer 2 — Embedding Model

The embedding model converts a chunk of text into a dense vector (typically 384–4096 dimensions). Every query and every stored chunk must be embedded by the *same model*; switching models later requires re-embedding the entire corpus.

Bi-encoders (the standard embedding model) encode text independently and compute similarity with a dot product or cosine distance. They are fast but sacrifice some accuracy. Cross-encoders attend to both query and chunk jointly — much more accurate but far slower (used in the reranking layer, not bulk retrieval).

**Open-source embedding models ranked by quality/cost trade-off:**

| Model | Dimensions | Best use |
|---|---|---|
| `all-MiniLM-L6-v2` | 384 | Low-latency, small corpora |
| `bge-large-en-v1.5` (BAAI) | 1024 | English, strong benchmark scores |
| `nomic-embed-text-v1.5` | 768 | Long context (8192 tokens), open weights |
| `jina-embeddings-v3` | 1024 | Multilingual, long context |
| `e5-mistral-7b-instruct` | 4096 | Maximum quality, expensive |

### Layer 3 — Vector Store

The vector store indexes embeddings for approximate nearest-neighbour (ANN) search and stores the associated chunk metadata (source URL, section, timestamp). ANN indexes (HNSW, IVF) trade a small recall penalty for orders-of-magnitude faster lookup compared to exact search.

Most modern vector databases also support **hybrid search**: combining ANN (semantic) with BM25 (keyword) retrieval and merging results with Reciprocal Rank Fusion (RRF) or a weighted sum. Hybrid search outperforms pure vector search on queries with specific keywords, codes, or named entities.

### Layer 4 — Retrieval & Reranking

The retrieval step returns the top-K candidates (commonly K=20–100) quickly. Reranking then re-scores those candidates with a more expensive cross-encoder model to produce the final top-N (typically N=3–10) chunks that go into the prompt.

```
Query → [Vector Search (K=50)] → [Reranker (top-5)] → LLM Prompt
```

This two-stage design separates recall (retrieval) from precision (reranking). You do not have to sacrifice one for the other.

**Reranker options**: `cross-encoder/ms-marco-MiniLM-L-6-v2`, Cohere Rerank, JinaAI Reranker, BGE Reranker. Rerankers consistently add 5–15 percentage points on downstream QA benchmarks at the cost of ~50–200ms latency.

### Layer 5 — Large Language Models

The LLM receives a structured prompt containing the user question and the retrieved chunks, then synthesises a grounded answer. In a fully open-source stack this model runs locally (Ollama, vLLM, llama.cpp) or on a self-hosted GPU cluster.

Leading open-weight models as of mid-2026:

| Model | Params | Context | Strength |
|---|---|---|---|
| Llama 3.1 | 8B / 70B / 405B | 128K | Balanced, widely supported |
| Mistral 7B / Mixtral 8x22B | 7B / 141B active | 32K / 64K | Efficient, strong instruction following |
| Gemma 2 | 9B / 27B | 8K | Google quality, compact |
| Phi-3 / Phi-3.5 | 3.8B / 14B | 128K | Small, strong reasoning |
| Qwen2.5 | 7B–72B | 128K | Multilingual, code |
| DeepSeek-R1 | 8B–671B | 128K | Reasoning-heavy tasks |

### Layer 6 — LLM Orchestration / Framework Layer

Orchestration frameworks wire the layers together: load documents, call the embedding model, query the vector store, format the prompt, call the LLM, parse the output, and optionally loop (for agents). They provide abstractions for chains, memory, tool use, and evaluation.

| Framework | Philosophy | Sweet spot |
|---|---|---|
| LangChain | Composable chains + huge ecosystem | Rapid prototyping, broad integrations |
| LlamaIndex | Document-centric data framework | Complex retrieval pipelines, structured data |
| Haystack | Pipeline DAG, production-ready | Enterprise pipelines, REST-first design |
| DSPy | Programmatic prompt optimisation | When prompts are a hyperparameter |
| Semantic Kernel | Microsoft SDK, multi-language | .NET/Java/Python polyglot teams |

### Layer 7 — Frontend / Application Layer

The UI exposes the RAG system to end users — a chat interface, a document search portal, or an embedded widget. For internal tools, Streamlit and Gradio ship an interactive UI in ~50 lines of Python. For production web apps, NextJS or SvelteKit provide full control over UX and streaming token display.

Streaming is important here: LLM responses should be streamed token-by-token so the user sees output within ~200ms rather than waiting 5–10 seconds for the full response.

---

## Build It / In Depth

The following walkthrough builds a minimal but complete local RAG pipeline using `sentence-transformers`, `chromadb`, and `llama.cpp` (via `ollama`). Each step corresponds to a stack layer.

### Step 1 — Install and ingest

```bash
pip install langchain langchain-community chromadb sentence-transformers unstructured
ollama pull llama3.1:8b
```

```python
# ingest.py  — Layer 1: load, chunk, embed, store
from langchain_community.document_loaders import DirectoryLoader, UnstructuredMarkdownLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

# Load raw documents
loader = DirectoryLoader("./docs", glob="**/*.md", loader_cls=UnstructuredMarkdownLoader)
raw_docs = loader.load()

# Chunk with overlap
splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=64)
chunks = splitter.split_documents(raw_docs)
print(f"Created {len(chunks)} chunks from {len(raw_docs)} documents")

# Embed and persist (Layers 2 + 3)
embedding_model = HuggingFaceEmbeddings(model_name="BAAI/bge-large-en-v1.5")
vectorstore = Chroma.from_documents(
    chunks,
    embedding=embedding_model,
    persist_directory="./chroma_db"
)
vectorstore.persist()
print("Index saved to ./chroma_db")
```

### Step 2 — Retrieval and generation

```python
# query.py  — Layers 4, 5, 6
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.llms import Ollama
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate

embedding_model = HuggingFaceEmbeddings(model_name="BAAI/bge-large-en-v1.5")
vectorstore = Chroma(persist_directory="./chroma_db", embedding_function=embedding_model)

# Layer 4: retrieve top-20, rerank to top-5 with MMR
retriever = vectorstore.as_retriever(
    search_type="mmr",           # Maximal Marginal Relevance — diversity + relevance
    search_kwargs={"k": 5, "fetch_k": 20}
)

# Layer 5: local LLM via Ollama
llm = Ollama(model="llama3.1:8b", temperature=0.1)

# Layer 6: wire together with a grounding prompt
PROMPT = PromptTemplate(
    input_variables=["context", "question"],
    template="""You are a helpful assistant. Answer ONLY from the context below.
If the answer is not in the context, say "I don't know."

Context:
{context}

Question: {question}
Answer:"""
)

qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    retriever=retriever,
    chain_type_kwargs={"prompt": PROMPT},
    return_source_documents=True
)

result = qa_chain.invoke({"query": "What is our refund policy?"})
print(result["result"])
for doc in result["source_documents"]:
    print(f"  ↳ {doc.metadata.get('source', 'unknown')}")
```

### Step 3 — Adding a reranker

```python
# rerank.py  — Layer 4 enhancement
from sentence_transformers import CrossEncoder

cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

def rerank(query: str, chunks: list[str], top_n: int = 5) -> list[str]:
    pairs = [(query, chunk) for chunk in chunks]
    scores = cross_encoder.predict(pairs)
    ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
    return [text for _, text in ranked[:top_n]]

# Usage: retrieve 20 with vector search, rerank to 5
candidates = retriever.get_relevant_documents(user_query)  # K=20
candidate_texts = [doc.page_content for doc in candidates]
top_chunks = rerank(user_query, candidate_texts, top_n=5)
```

### Step 4 — Streaming frontend (Layer 7)

```python
# app.py  — Streamlit streaming UI
import streamlit as st
from langchain_community.llms import Ollama
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler

st.title("Internal Knowledge Assistant")

if prompt := st.chat_input("Ask a question..."):
    with st.chat_message("assistant"):
        with st.spinner("Retrieving..."):
            candidates = retriever.get_relevant_documents(prompt)
            top_chunks = rerank(prompt, [d.page_content for d in candidates])
            context = "\n\n".join(top_chunks)

        # Stream tokens to the UI
        placeholder = st.empty()
        full_response = ""
        for token in llm.stream(PROMPT.format(context=context, question=prompt)):
            full_response += token
            placeholder.markdown(full_response + "▌")
        placeholder.markdown(full_response)
```

---

## Use It

### Choosing a Vector Store

| Store | Deployment | Hybrid search | Scale | Choose when |
|---|---|---|---|---|
| **Chroma** | In-process / Docker | No (vector only) | <1M vecs | Local dev, prototypes |
| **pgvector** | Postgres extension | Via full-text | Medium | You already run Postgres |
| **Qdrant** | Docker / Cloud | Yes (BM25 + vec) | Large | High write throughput, filtering |
| **Weaviate** | Docker / Cloud | Yes (BM25 + vec) | Large | GraphQL API, multi-tenancy |
| **Milvus** | Kubernetes | Yes | Very large | 100M+ vectors, cloud-native |

### Choosing an Orchestration Framework

- **LangChain** is the right default for new projects — the ecosystem is vast and most tutorials use it. The abstraction layer has improved significantly; chains and LCEL are composable without deep magic.
- **LlamaIndex** shines when your data is structured (tables, knowledge graphs) or when you need advanced retrieval strategies (sub-question decomposition, recursive retrieval).
- **Haystack** is the correct choice for teams that want a clear REST-first deployment story and a YAML-defined pipeline DAG.
- **DSPy** replaces hand-written prompts with optimised programs — worth evaluating when accuracy on a defined benchmark matters more than development speed.

### Serving Open-Weight LLMs

| Tool | Best for |
|---|---|
| **Ollama** | Local dev, macOS/Linux, single GPU |
| **vLLM** | Production inference, batching, OpenAI-compatible API |
| **llama.cpp** | CPU-only or mixed CPU/GPU, minimal RAM |
| **text-generation-inference** (TGI) | HuggingFace models, streaming, quantisation |
| **Triton Inference Server** | NVIDIA GPU fleet, maximum throughput |

---

## Common Pitfalls

- **Mismatched embedding models**: Re-embedding at query time with a different model than was used to index documents produces garbage similarity scores. Pin the model name and version in your pipeline config, and version the index alongside it.

- **Chunks too large for context budgets**: A 2048-token chunk leaves no room for system prompt, conversation history, and multiple retrieved chunks. Design chunk size relative to the LLM's context window and how many chunks you plan to inject. A rule of thumb: each chunk should consume no more than ~10% of the context window.

- **Ignoring BM25 / keyword retrieval**: Pure vector search fails for queries with specific identifiers (order numbers, product SKUs, named entities). Add hybrid search from the start; retrofitting it later requires re-indexing.

- **No chunking overlap**: A sentence cut exactly at a chunk boundary loses context for both the ending chunk and the starting one. Always set `chunk_overlap` to at least 10% of `chunk_size`.

- **Skipping evaluation**: "It feels right" is not a metric. Run your pipeline against a held-out set of question–answer pairs and measure Context Recall (did retrieval find the relevant chunk?) and Answer Faithfulness (did the LLM stay grounded?) using RAGAS or a similar framework before shipping.

---

## Exercises

1. **Easy — Layer mapping**: Take a RAG system you use daily (e.g., a chatbot on a documentation site) and identify which tool or service is likely fulfilling each of the seven layers. Write a short paragraph for each layer explaining your reasoning.

2. **Medium — Chunking strategy comparison**: Index the same 50-page PDF using three different chunking strategies (fixed-size 256 tokens, recursive character splitter, and sentence-level). Run 10 representative queries and compare the top-3 retrieved chunks for each strategy. Which produces the most self-contained, relevant chunks? Document the trade-offs.

3. **Hard — Build a hybrid retrieval reranking pipeline**: Extend the code in the Build It section to use Qdrant instead of Chroma. Enable hybrid search (BM25 + vector). Add the `cross-encoder/ms-marco-MiniLM-L-6-v2` reranker and instrument your pipeline to log retrieval latency, reranking latency, and final answer latency separately. Run RAGAS evaluation on 20 Q&A pairs and compare accuracy versus the baseline (vector-only, no reranker).

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **RAG** | A single feature you toggle on | A multi-layer pipeline: ingest, embed, store, retrieve, rerank, prompt, generate |
| **Embedding** | How you "make text searchable" | Projecting text into a high-dimensional vector space where semantic similarity corresponds to geometric proximity |
| **Chunk** | An arbitrary document split | A purposefully sized, possibly overlapping segment of a source document, sized to balance retrieval precision and context completeness |
| **Hybrid search** | Keyword search + vector search somehow combined | Running BM25 and ANN retrieval in parallel, then merging ranked lists (e.g., Reciprocal Rank Fusion) to exploit both lexical and semantic signals |
| **Reranker** | A second vector search | A cross-encoder model that reads query and candidate jointly, producing much more accurate relevance scores at the cost of latency |
| **Hallucination grounding** | The LLM reads the documents | The LLM receives retrieved text as part of its prompt context and is instructed (via the system prompt) to answer only from that context — it still can ignore the instruction |
| **ANN index** | Exact similarity search | Approximate Nearest Neighbour index (HNSW, IVF) that trades a small recall penalty for orders-of-magnitude faster search |

---

## Further Reading

- **LangChain RAG Tutorial** — end-to-end walkthrough with LCEL: https://python.langchain.com/docs/tutorials/rag/
- **LlamaIndex — Building RAG** — structured retrieval and evaluation: https://docs.llamaindex.ai/en/stable/understanding/rag/
- **RAGAS** — open-source RAG evaluation framework: https://docs.ragas.io/en/latest/
- **Weaviate RAG Best Practices** — hybrid search, chunking, and reranking guide: https://weaviate.io/developers/weaviate/tutorials/rag
- **Hugging Face MTEB Leaderboard** — authoritative ranking of open embedding models across retrieval tasks: https://huggingface.co/spaces/mteb/leaderboard
