# How to Build a Basic RAG Application on AWS?

> The shortest path from "we have PDFs in S3" to "the agent answers questions grounded in those PDFs" — managed, serverless, and AWS-native.

**Type:** Learn
**Prerequisites:** What is RAG?, S3, Lambda basics, AWS Bedrock overview
**Time:** ~30 minutes

---

## The Problem

You have documents. Hundreds of them, in S3, in mixed formats — PDFs, DOCX, HTML, plain text. You want users to ask questions in natural language and get answers grounded in those documents, with citations. You do not want to operate a vector database, an embedding pipeline, and a retrieval service from scratch. You use AWS. What is the shortest path?

AWS offers a stack that maps cleanly to every stage of a RAG pipeline, and most of it is serverless or fully managed. S3 for storage, Lambda for glue, Bedrock for embeddings and generation, OpenSearch Serverless or Aurora pgvector for vector search, API Gateway in front. The whole thing can run on managed services end-to-end, with no EC2 instances to babysit.

This lesson walks through the architecture, the ingestion pipeline, and the query pipeline. You will see what each component does, why it is the right choice on AWS, and how to wire it together with the least custom code.

---

## The Concept

### The two-stage architecture

A RAG application has two stages that run on different cadences:

```
   ┌─────────────────────────────────────────────────────────────┐
   │                                                             │
   │   INGESTION STAGE (runs when documents change)              │
   │                                                             │
   │   S3 bucket                                                 │
   │      │                                                      │
   │      │  (S3 Event Notification)                              │
   │      ▼                                                      │
   │   Lambda: ingest function                                   │
   │      │                                                      │
   │      │  - read raw file                                     │
   │      │  - extract text (PDF, DOCX, ...)                      │
   │      │  - chunk text (300–600 tokens, ~20% overlap)          │
   │      ▼                                                      │
   │   Bedrock Titan Embeddings                                  │
   │      │                                                      │
   │      │  - convert chunks → vectors                          │
   │      ▼                                                      │
   │   Vector store                                              │
   │   (OpenSearch Serverless / Aurora pgvector / Neptune)        │
   │                                                             │
   └─────────────────────────────────────────────────────────────┘

   ┌─────────────────────────────────────────────────────────────┐
   │                                                             │
   │   QUERYING STAGE (runs on every user request)               │
   │                                                             │
   │   User                                                      │
   │      │                                                      │
   │      ▼                                                      │
   │   API Gateway                                               │
   │      │                                                      │
   │      ▼                                                      │
   │   Lambda: query function                                    │
   │      │                                                      │
   │      ├──► Bedrock Titan Embeddings                         │
   │      │      (embed user question)                           │
   │      │                                                      │
   │      ├──► Vector store (k-NN search)                       │
   │      │      (top-k chunks)                                  │
   │      │                                                      │
   │      └──► Bedrock LLM (Claude / Llama / etc.)              │
   │             (prompt = system + chunks + question)           │
   │                                                             │
   │      │                                                      │
   │      ▼                                                      │
   │   Response to user (with citations)                         │
   │                                                             │
   └─────────────────────────────────────────────────────────────┘
```

The two stages share only the vector store. Everything else is decoupled. The ingestion stage runs on document upload (rare). The querying stage runs on every request (hot path). Optimizing them separately is one of the architectural wins of this design.

---

### Why these specific services

| Layer | AWS service | Why this one |
|---|---|---|
| Object storage | S3 | Durable, cheap, native event notifications for triggering ingestion |
| Compute | Lambda | Serverless, scales to zero, no servers to patch; cold starts acceptable for ingestion |
| Text extraction | Lambda + libraries (`pypdf`, `python-docx`) or Amazon Textract | Textract handles scanned PDFs via OCR; libraries are fine for digital PDFs |
| Chunking | Lambda (custom logic) | Chunk size and overlap are domain-specific; no managed service does this well |
| Embedding model | Amazon Bedrock (Titan Embeddings v2, Cohere Embed v3) | Pay-per-token, no model hosting, supports batch embedding |
| Vector store | OpenSearch Serverless, Aurora pgvector, Neptune Analytics, MemoryDB | Pick based on scale and query patterns |
| Generation | Amazon Bedrock (Claude 3.5/4, Llama 3, Mistral, Cohere Command) | Multiple model options behind one API; switch without code changes |
| API | API Gateway + Lambda | Managed HTTPS endpoint with auth, throttling, monitoring |
| Identity | Cognito or IAM | Cognito for end-user auth, IAM for service-to-service |

The whole stack is serverless except the vector store choice (which has both serverless and provisioned options). You can run a production RAG system on AWS without owning a single EC2 instance.

---

### Choosing the vector store

Three realistic options on AWS, each with a different trade-off:

| Option | Best for | Trade-off |
|---|---|---|
| **OpenSearch Serverless** | Production scale, hybrid (vector + BM25) search | Most expensive at small scale; mature, well-supported |
| **Aurora pgvector** | Teams already on Postgres; modest scale (≤10M vectors) | Cheapest if you already run Aurora; pure vector, no hybrid |
| **MemoryDB (with vector search)** | Lowest latency, Redis-compatible | Less mature; smaller community; good for hot-path latency |

A reasonable default: start with Aurora pgvector if your team already runs Postgres. Switch to OpenSearch Serverless when you need hybrid search or exceed pgvector's scale. MemoryDB if you are latency-bound.

---

## Build It / In Depth

### The ingestion pipeline, end to end

```python
# lambda_function_ingest.py — runs on S3 ObjectCreated event

import boto3
import json
from pypdf import PdfReader

s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

def lambda_handler(event, context):
    # 1. Get the new file's bucket + key from the S3 event
    bucket = event["Records"][0]["s3"]["bucket"]["name"]
    key = event["Records"][0]["s3"]["object"]["key"]

    # 2. Download the file
    obj = s3.get_object(Bucket=bucket, Key=key)
    raw_bytes = obj["Body"].read()

    # 3. Extract text (PDF example)
    if key.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(raw_bytes))
        text = "\n".join(page.extract_text() for page in reader.pages)
    else:
        text = raw_bytes.decode("utf-8")

    # 4. Chunk into ~500-token pieces with ~20% overlap
    chunks = chunk_text(text, chunk_size=500, overlap=100)

    # 5. Embed each chunk with Bedrock Titan
    vectors = []
    for i, chunk in enumerate(chunks):
        response = bedrock.invoke_model(
            modelId="amazon.titan-embed-text-v2:0",
            body=json.dumps({"inputText": chunk}),
        )
        embedding = json.loads(response["body"].read())["embedding"]
        vectors.append({
            "id": f"{key}::{i}",
            "values": embedding,
            "metadata": {
                "source": key,
                "chunk_index": i,
                "text": chunk,
            },
        })

    # 6. Upsert into the vector store
    opensearch.bulk(index="docs", body=vectors)

    return {"statusCode": 200, "chunks_indexed": len(vectors)}
```

A few design notes:

- **S3 event trigger** is what kicks off the function. You configure it once in the S3 bucket's properties — every new object fires the Lambda automatically.
- **Chunking** is the most underestimated step. Tune `chunk_size` and `overlap` for your content. Long chunks dilute the embedding signal; short chunks lose context. 300–600 tokens with 20% overlap is a sensible default.
- **Storing the original text as metadata** lets the query function return citations without a second lookup against S3.
- **Batch embeddings** (Titan supports up to 100 chunks per call) reduce cost and latency dramatically.

---

### The query pipeline, end to end

```python
# lambda_function_query.py — runs on API Gateway request

import boto3
import json

bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
opensearch = boto3.client("opensearchserverless")

def lambda_handler(event, context):
    user_query = json.loads(event["body"])["question"]

    # 1. Embed the question
    q_response = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=json.dumps({"inputText": user_query}),
    )
    q_embedding = json.loads(q_response["body"].read())["embedding"]

    # 2. Search the vector store for top-k chunks
    search_response = opensearch.search(
        index="docs",
        body={
            "size": 5,
            "query": {"knn": {"values": q_embedding, "k": 5}},
        },
    )
    chunks = [hit["_source"]["metadata"] for hit in search_response["hits"]["hits"]]

    # 3. Build the prompt with retrieved context
    context_text = "\n\n---\n\n".join(c["text"] for c in chunks)
    prompt = f"""You are an internal knowledge assistant.
Answer the user's question using ONLY the context below.
Cite the source for each claim.

CONTEXT:
{context_text}

QUESTION: {user_query}

ANSWER:"""

    # 4. Generate the answer with Claude
    llm_response = bedrock.invoke_model(
        modelId="anthropic.claude-3-5-sonnet-20240620-v1:0",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )
    answer = json.loads(llm_response["body"].read())["content"][0]["text"]

    return {
        "statusCode": 200,
        "body": json.dumps({
            "answer": answer,
            "sources": [{"source": c["source"], "chunk": c["chunk_index"]} for c in chunks],
        }),
    }
```

The query pipeline is the hot path. Every user question triggers all four steps. Optimizations matter:

- **Cache embeddings** for repeated queries.
- **Filter the vector search** by metadata (tenant, document type, date) before doing k-NN — fewer vectors to compare, faster responses.
- **Re-rank the top-k** with a cross-encoder for higher precision (Cohere Rerank 3 is available on Bedrock).
- **Pre-warm the Lambda** with provisioned concurrency if cold starts are user-visible.

---

### The architecture on one diagram

```
                       ┌────────────────────┐
                       │      User UI       │
                       │ (CloudFront / S3)  │
                       └─────────┬──────────┘
                                 │ HTTPS
                                 ▼
                       ┌────────────────────┐
                       │    API Gateway     │
                       │  + Cognito auth    │
                       └─────────┬──────────┘
                                 │
                                 ▼
                       ┌────────────────────┐
                       │  Lambda: query     │
                       └──┬───────────┬─────┘
                          │           │
            ┌─────────────┘           └─────────────┐
            ▼                                        ▼
   ┌──────────────────┐                    ┌──────────────────┐
   │ Bedrock:         │                    │ Bedrock:         │
   │ Titan Embeddings │                    │ Claude / Llama   │
   │ (embed question) │                    │ (generate)       │
   └────────┬─────────┘                    └──────────────────┘
            │
            ▼
   ┌──────────────────────────────────────────┐
   │  Vector store: OpenSearch Serverless     │
   │  (or Aurora pgvector / MemoryDB)         │
   └──────────────────────────────────────────┘

   ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ingestion path ─ ─ ─ ─ ─ ─ ─ ─

   ┌──────────────────┐
   │   S3 bucket      │  ◄── documents uploaded here
   └────────┬─────────┘
            │ S3 ObjectCreated event
            ▼
   ┌──────────────────┐
   │ Lambda: ingest   │  ──► extract text → chunk → embed
   └────────┬─────────┘
            │
            ▼
   ┌──────────────────────────────────────────┐
   │  Vector store (same as above)            │
   └──────────────────────────────────────────┘
```

Same vector store serves both paths. Everything else is decoupled.

---

### Cost shape for a modest production system

Rough numbers for 1,000 user queries/day, 100 GB of documents:

| Service | Approximate monthly cost |
|---|---|
| S3 (100 GB, standard) | ~$3 |
| Lambda (ingestion, runs on upload) | ~$5 |
| Bedrock Titan Embeddings (queries + ingestion) | ~$30 |
| Bedrock Claude 3.5 Sonnet (1,000 queries/day, ~2k tokens each) | ~$300 |
| OpenSearch Serverless (2 OCUs minimum) | ~$350 |
| API Gateway | ~$5 |
| CloudWatch logs | ~$10 |
| **Total** | **~$700/month** |

The dominant line is Bedrock Claude. Every optimization that reduces context size (better retrieval, tighter prompts, re-ranking) directly reduces the bill.

---

## Use It

### When this architecture is right

| If you need… | This architecture fits because… |
|---|---|
| A RAG app on AWS, fully managed | Every component has a managed AWS service |
| Hybrid search (vector + keyword) | OpenSearch Serverless supports both in one query |
| Multi-tenant with strict data isolation | S3 prefix + IAM + OpenSearch tenant filters |
| Compliance / data residency | AWS regions; Bedrock VPC endpoints |
| Predictable cost at moderate scale | Serverless pricing scales linearly with usage |
| Switching between foundation models | Bedrock exposes Claude, Llama, Mistral, Cohere, AI21 behind one API |

### When to consider alternatives

- **Heavy document volume (>1M pages)** — Lambda timeouts (15 min) become a constraint; switch to ECS or Batch for ingestion.
- **Sub-100ms query latency** — Lambda cold starts matter; consider provisioned concurrency or containers.
- **Cross-cloud portability** — the architecture is AWS-specific; abstracting it costs complexity.
- **Existing heavy investment in another cloud** — keep the same shape but use that cloud's equivalents (Azure AI Search, GCP Vertex AI Search).

### Managed shortcuts

If even the Lambda code feels like too much:

- **Amazon Bedrock Knowledge Bases** — fully managed RAG. Upload documents to S3, point Bedrock at them, get a query API. Handles ingestion, chunking, embedding, retrieval, and citation. No custom Lambda.
- **Amazon Q for Business** — packaged RAG over your enterprise documents (Confluence, SharePoint, S3) with a chat UI.
- **Kendra** — managed enterprise search with built-in connectors, FAQ extraction, and relevance tuning.

These trade flexibility for speed-to-production. Start there if your team has no ML engineers; graduate to the custom architecture when you hit limits.

---

## Common Pitfalls

- **Chunking after embedding.** If you embed large blocks and then realize the chunks are wrong, you re-embed the entire corpus. Decide chunk size and overlap before the first embedding run; tune with a small sample first.

- **No metadata filters.** Pure k-NN over the entire vector store returns chunks from old, irrelevant, or unauthorized documents. Always filter by tenant, document type, date, or source before searching.

- **Cold start in the hot path.** Lambda cold starts (200ms–2s) on the query function are user-visible. Use provisioned concurrency for production.

- **Embedding model drift.** If you change the embedding model (e.g., from Titan v1 to v2), you must re-embed the entire corpus. Mixing embeddings from different models in the same index produces garbage results. Track the embedding model version per index.

- **Skipping OCR.** PDFs of scanned documents contain images, not text. `pypdf` extracts nothing. Use Amazon Textract or a similar OCR step before chunking.

- **No re-ranking.** Embedding similarity ≠ answer relevance. Add a cross-encoder re-ranker (Cohere Rerank 3 on Bedrock) on the top-k results before passing them to the LLM.

- **No evaluation.** Without systematic retrieval recall and answer faithfulness metrics, you cannot tell if your changes are improving or degrading the system. Use RAGAS or a custom eval harness before shipping.

- **Vector store without backups.** OpenSearch Serverless has built-in snapshots; Aurora pgvector does not by default. Configure point-in-time recovery before you go to production.

---

## Exercises

1. **Easy** — Sketch the ingestion and query paths for a RAG app on AWS that reads from an existing S3 bucket. Label each box with the AWS service you would use and one sentence justifying the choice.

2. **Medium** — Your team has 500 GB of documents across PDF, DOCX, and HTML. Half are scanned (image-only). Design the ingestion pipeline: how do you handle the scanned PDFs, what chunk size would you start with, how do you batch embeddings to stay under Lambda's 15-minute timeout, and where would you add OCR.

3. **Hard** — A regulated-industry client wants the RAG system above, with three constraints: (a) all data must stay in a single AWS region, (b) only specific users can query specific document prefixes, (c) every query and retrieval must be audit-logged for 7 years. Design the architecture: which AWS services handle each constraint, where you add VPC endpoints, how you enforce per-user document scoping, and how you wire CloudTrail + S3 object lock for the audit trail.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| RAG | Asking the LLM to search | A two-stage architecture: ingestion (chunks → embeddings → vector store) and querying (embed question → retrieve top-k → inject context → generate answer); the LLM never searches itself |
| Bedrock | A foundation model API | AWS's managed service that exposes multiple foundation models (Claude, Llama, Mistral, Cohere, Titan, AI21) behind one API; switch models without changing application code |
| OpenSearch Serverless | Just a vector database | A managed OpenSearch cluster that supports vector search, BM25 keyword search, and hybrid queries; the most flexible (and priciest) AWS option for RAG |
| Aurora pgvector | Postgres with vectors | A Postgres extension that adds vector columns and similarity search to a database you may already run; cheapest option for moderate scale, but pure vector, no hybrid |
| Titan Embeddings | Amazon's embedding model | The AWS-native embedding model family (v1, v2); pay-per-token, no hosting, supports batch embedding up to 100 chunks per call |
| Lambda | A way to run code | AWS's serverless compute; ideal for the ingestion trigger and the query API; cold starts matter for latency-sensitive query paths |
| Chunking | Splitting documents | Dividing documents into 300–600 token pieces with ~20% overlap before embedding; the most underestimated tuning knob in any RAG system |
| Re-ranking | Sorting results better | A second pass (usually with a cross-encoder model like Cohere Rerank 3) that reorders the top-k retrieved chunks by relevance before they are injected into the prompt; significant precision boost for minimal cost |

---

## Further Reading

- **Amazon Bedrock Knowledge Bases Documentation** — the fully managed RAG option if you do not want to write the Lambda code: https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html
- **"Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"** — the original RAG paper by Lewis et al.: https://arxiv.org/abs/2005.11401
- **OpenSearch Vector Search Documentation** — the canonical reference for k-NN queries, hybrid search, and metadata filtering on OpenSearch Serverless: https://opensearch.org/docs/latest/search-plugins/knn/
- **AWS Architecture Blog: Building a RAG Application on AWS** — a reference architecture with Terraform templates: https://aws.amazon.com/blogs/architecture/
- **RAGAS: Automated Evaluation for RAG Pipelines** — the framework for measuring retrieval recall and answer faithfulness: https://docs.ragas.io