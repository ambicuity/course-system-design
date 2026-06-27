# Top 20 AI Concepts You Should Know

> You don't need to build neural networks from scratch — but you do need to know what every layer of the stack does and why it matters.

**Type:** Learn
**Prerequisites:** Introduction to System Design, Scalability Fundamentals
**Time:** ~35 minutes

---

## The Problem

A senior backend engineer joins an AI-first company and is asked to review the architecture for a new document-search product. The system uses "embeddings" and a "vector database" for search, a "fine-tuned LLM" for summarization, and "prompt engineering" for the UI. He nods along. He's heard all these terms, but can't explain the difference between a fine-tuned model and a prompted one, doesn't know when a vector search beats a keyword search, and can't estimate what the inference infrastructure will cost. He approves the design anyway. Six months later the product is slow, expensive, and hard to maintain — but nobody can say exactly why.

This is the AI knowledge gap. The vocabulary exists everywhere, but the mental models are missing. Without them, engineers can't make the right architectural trade-offs: when to train versus prompt, how to measure quality, what kind of GPU cluster you actually need, why the retrieval is returning nonsense.

This lesson closes that gap. It gives you a precise one-screen definition and a concrete mental model for each of the 20 most important AI concepts you will encounter in modern system design — from the foundational math abstractions (supervised learning, feature engineering) through the application layer (LLMs, agents, multimodal models) to the operational layer (evaluation, infrastructure). Read it once, use it as a reference whenever one of these terms surfaces in an architecture discussion.

---

## The Concept

The 20 concepts fall into five natural groups. Knowing the group helps you know where a tool fits.

```
┌─────────────────────────────────────────────────────────────────┐
│  GROUP 1 — Foundations      │  GROUP 2 — Data & Representation  │
│  ┌──────────────────────┐   │  ┌──────────────────────────────┐ │
│  │ Machine Learning     │   │  │ Feature Engineering          │ │
│  │ Deep Learning        │   │  │ Embeddings                   │ │
│  │ Neural Networks      │   │  │ Vector Search                │ │
│  │ Supervised Learning  │   └──────────────────────────────────┘ │
│  │ Bayesian Learning    │                                        │
│  └──────────────────────┘   GROUP 3 — Model Families            │
│                             ┌──────────────────────────────────┐ │
│  GROUP 4 — Apply & Adapt    │ NLP                              │ │
│  ┌──────────────────────┐   │ Computer Vision                  │ │
│  │ Prompt Engineering   │   │ Reinforcement Learning           │ │
│  │ Fine-Tuning Models   │   │ Generative Models                │ │
│  │ AI Agents            │   │ LLM                              │ │
│  │ Multimodal Models    │   │ Transformers                     │ │
│  └──────────────────────┘   └──────────────────────────────────┘ │
│                                                                  │
│  GROUP 5 — Operations                                           │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Model Evaluation                  AI Infrastructure        │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Group 1 — Foundations

**1. Machine Learning**
The field where systems improve at a task by learning from data rather than being explicitly programmed. The core loop: define a loss function, feed examples, adjust parameters to minimize loss, repeat. Every subsequent concept in this list lives on top of this loop.

**2. Supervised Learning**
A subtype of ML where every training example carries a label (correct answer). The model learns a mapping from input X → output Y. A classifier predicting spam/not-spam, a regressor predicting house price — both supervised. The practical bottleneck is always labeling cost.

**3. Deep Learning**
Supervised (and unsupervised) learning using neural networks with many layers. "Deep" means the layers are stacked, building hierarchical representations: raw pixels → edges → shapes → objects. The key insight is that *representation learning* happens automatically; you don't handcraft features.

**4. Neural Networks**
The computational substrate of deep learning. Layers of simple units (neurons) — each computes a weighted sum of its inputs then applies a nonlinear activation function (ReLU, sigmoid). Stacked layers transform inputs into increasingly abstract representations. Weight updates happen via backpropagation + gradient descent.

```
Input  →  [Dense Layer]  →  [Dense Layer]  →  Output
          (ReLU)            (ReLU)            (Softmax)
```

**5. Bayesian Learning**
Rather than outputting a single prediction, Bayesian models maintain a probability distribution over predictions — quantifying uncertainty. Useful when you need to know *how confident* a model is, not just what it predicts. Practical form: calibrated confidence scores, dropout-as-Bayesian-approximation.

---

### Group 2 — Data & Representation

**6. Feature Engineering**
Transforming raw data into inputs a model can use effectively. In classical ML this is manual and domain-driven (e.g., "days since last purchase"). In deep learning, the network learns features automatically — but feature engineering still matters at the data pipeline level (normalization, bucketing, handling nulls, time-series lags).

**7. Embeddings**
Dense, low-dimensional vector representations that encode meaning. A word, sentence, image, or user can all be mapped to a vector in a shared geometric space. Semantically similar items land near each other. Embeddings are the lingua franca connecting retrieval systems, recommendation engines, and language models.

```
"cat"  →  [0.21, -0.43,  0.88, ...]   # 1536-dim vector
"dog"  →  [0.19, -0.40,  0.85, ...]   # nearby: similar concept
"car"  →  [-0.72, 0.34, -0.11, ...]   # far away
```

**8. Vector Search**
Finding the *k* nearest neighbors to a query vector in a large corpus of embeddings. Exact nearest-neighbor search is O(n·d) — too slow at scale. Approximate Nearest Neighbor (ANN) algorithms (HNSW, IVF, PQ) trade a small recall loss for 100–1000× speed improvement. This is the retrieval engine behind semantic search and RAG.

---

### Group 3 — Model Families

**9. NLP (Natural Language Processing)**
The subdomain concerned with text: tokenization, parsing, sentiment analysis, named-entity recognition, translation, summarization, question-answering. Modern NLP is entirely dominated by transformer-based models; the classical pipeline (TF-IDF, CRF, rule-based) is now largely legacy.

**10. Computer Vision**
The subdomain concerned with images and video: classification, object detection, segmentation, optical character recognition. The dominant architecture shifted from CNNs (convolutional neural networks) to Vision Transformers (ViT) after 2020. Key datasets: ImageNet, COCO.

**11. Reinforcement Learning (RL)**
A learning paradigm where an agent takes actions in an environment, receives rewards or penalties, and learns a policy that maximizes cumulative reward. Unlike supervised learning, there are no labeled examples — the signal comes from outcomes. Used in robotics, game-playing (AlphaGo), recommendation ranking, and RLHF for LLM alignment.

```
Agent → Action → Environment → Reward + Next State → Agent (loop)
```

**12. Generative Models**
Models that learn the underlying distribution of training data and can *sample* new examples from it. Key types:
- **GANs** — generator vs. discriminator adversarial training
- **VAEs** — encode to a latent distribution, decode back
- **Diffusion models** — add noise then learn to denoise (Stable Diffusion, DALL·E)
- **Autoregressive models** — generate token-by-token (GPT family)

**13. Transformers**
The architecture underlying virtually all modern AI: a stack of self-attention layers and feed-forward networks. Self-attention lets every position in the input attend to every other position in O(n²) — enabling rich long-range dependencies. The encoder-decoder form powers translation; the decoder-only form (GPT) powers generation; the encoder-only form (BERT) powers classification/retrieval.

```
Input tokens
    │
    ▼
[Multi-Head Self-Attention] ──► add & norm
    │
    ▼
[Feed-Forward Network]      ──► add & norm
    │
    ▼ (× N layers)
Output representations
```

**14. LLM (Large Language Model)**
A transformer-based language model trained at massive scale (billions of parameters, trillions of tokens) to predict the next token. Scale unlocks emergent capabilities: in-context learning, chain-of-thought reasoning, instruction following — none of which were explicitly trained. GPT-4, Claude, Gemini, Llama, Mistral are all LLMs.

---

### Group 4 — Apply & Adapt

**15. Prompt Engineering**
Structuring the text input to an LLM to produce the desired output. Techniques include: zero-shot (just ask), few-shot (include examples), chain-of-thought (ask the model to reason step-by-step), role assignment, output format constraints. Effective prompting is often the fastest path from "model exists" to "product works."

**16. Fine-Tuning Models**
Continuing training of a pre-trained model on a smaller, task-specific dataset to adjust its weights for a particular domain or behavior. Full fine-tuning is expensive; parameter-efficient methods (LoRA, QLoRA, prefix tuning) update < 1% of weights and run on a single GPU. Fine-tuning is appropriate when prompting is insufficient, you have labeled task data, and you can afford the compute + inference cost of a separate model.

**17. AI Agents**
Systems that use an LLM (or other model) as a reasoning engine to autonomously plan, call tools, observe results, and iterate toward a goal. The ReAct pattern (Reason + Act) is the standard loop. Agents can browse the web, query databases, write and execute code, and chain multiple steps without human intervention. Current limitation: reliability degrades quickly beyond 5–10 reasoning steps.

```
Goal → [LLM: Plan] → Tool Call → Observation → [LLM: Reason] → ... → Answer
```

**18. Multimodal Models**
Models that process and generate across more than one modality — text, images, audio, video, code. GPT-4o, Gemini 1.5, Claude 3 are all multimodal. The architecture typically encodes each modality into a shared embedding space before the transformer processes them jointly. Enables: image captioning, visual QA, audio transcription + summarization in one pass.

---

### Group 5 — Operations

**19. Model Evaluation**
Systematic measurement of model quality before and after deployment. Offline metrics depend on task:

| Task | Metric |
|---|---|
| Classification | Accuracy, Precision, Recall, F1, AUC-ROC |
| Generation | BLEU, ROUGE, BERTScore, human eval |
| Retrieval | Precision@K, Recall@K, MRR, NDCG |
| Ranking | nDCG, MAP |

Offline metrics are necessary but not sufficient. A/B tests and online guardrails (latency, user engagement, error rate) are needed to verify real-world impact.

**20. AI Infrastructure**
The hardware, software, and operational systems that train, serve, and monitor models at scale:
- **Training**: GPU/TPU clusters, distributed frameworks (PyTorch DDP, Megatron-LM), mixed-precision, gradient checkpointing
- **Serving**: model servers (Triton, vLLM, TGI), batching, quantization (INT8/INT4), KV-cache management
- **Orchestration**: Kubernetes, Ray, Slurm
- **Observability**: request tracing, token usage, drift detection, output monitoring

---

## Build It / In Depth

The following concrete example walks through building a minimal semantic search pipeline — touching embeddings, vector search, prompt engineering, and evaluation all in one pass.

**Scenario**: You have 10,000 customer support tickets. You want users to query them in natural language and get the most relevant tickets back, with a one-paragraph summary.

### Step 1 — Generate Embeddings

```python
import openai

def embed(texts: list[str]) -> list[list[float]]:
    response = openai.embeddings.create(
        model="text-embedding-3-small",   # 1536 dims, $0.02/1M tokens
        input=texts
    )
    return [item.embedding for item in response.data]

# Batch your 10k tickets in chunks of 2048 for throughput
tickets = load_tickets()  # list of strings
vectors = []
for batch in chunked(tickets, 2048):
    vectors.extend(embed(batch))
```

### Step 2 — Index in a Vector Database

```python
import chromadb

client = chromadb.Client()
collection = client.create_collection("support_tickets")

collection.add(
    documents=tickets,
    embeddings=vectors,
    ids=[str(i) for i in range(len(tickets))]
)
```

### Step 3 — Query with Semantic Search

```python
def search(query: str, top_k: int = 5) -> list[str]:
    q_vec = embed([query])[0]
    results = collection.query(query_embeddings=[q_vec], n_results=top_k)
    return results["documents"][0]
```

### Step 4 — Summarize with Prompt Engineering

```python
def summarize(query: str, retrieved: list[str]) -> str:
    context = "\n---\n".join(retrieved)
    prompt = f"""You are a support analyst. A customer asked: "{query}"

Here are the {len(retrieved)} most relevant past tickets:
{context}

In 2-3 sentences, summarize the common theme and resolution pattern."""

    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    return response.choices[0].message.content
```

### Step 5 — Evaluate

```python
# Offline: measure retrieval quality on a labeled eval set
from sklearn.metrics import precision_score

def precision_at_k(query: str, expected_ids: list[str], k: int = 5) -> float:
    results = search(query, top_k=k)
    retrieved_ids = [r["id"] for r in results]
    hits = sum(1 for rid in retrieved_ids if rid in expected_ids)
    return hits / k

# Run across 200 labeled queries; aim for P@5 > 0.7 before deploying
```

This pipeline touches concepts 7, 8, 13 (transformer model underneath embeddings), 15, and 19 — five of the twenty, working together.

---

## Use It

| Concept | Tools / Services | When to reach for each |
|---|---|---|
| Embeddings | OpenAI `text-embedding-3`, Cohere Embed, `sentence-transformers` | Any semantic similarity task |
| Vector Search | Pinecone, Weaviate, pgvector, Chroma, Qdrant | RAG, semantic search, dedup |
| LLM | GPT-4o, Claude 3.5 Sonnet, Gemini 1.5, Llama 3 | Generation, reasoning, summarization |
| Fine-Tuning | OpenAI fine-tune API, Hugging Face PEFT/LoRA | Domain adaptation, consistent formatting |
| Prompt Engineering | Any LLM + structured prompts | Fastest path to working feature |
| AI Agents | LangChain, LlamaIndex, Autogen, CrewAI | Multi-step automation with tools |
| ML Training | PyTorch, TensorFlow, JAX | Custom model training |
| Computer Vision | Torchvision, Detectron2, Roboflow, AWS Rekognition | Image/video classification, OCR |
| NLP Pipeline | spaCy, Hugging Face `transformers`, AWS Comprehend | Classification, NER, text parsing |
| AI Infrastructure | AWS SageMaker, GCP Vertex AI, Azure ML, vLLM, Triton | Serving models at production scale |

---

## Common Pitfalls

- **Confusing fine-tuning with prompt engineering.** Fine-tuning changes the model weights — it's expensive, requires labeled data, and creates a new model to maintain. Prompt engineering costs nothing to try. Always exhaust prompting first; only fine-tune when you have > 100 high-quality labeled examples and prompting has a documented ceiling.

- **Treating embedding similarity as ground truth.** Cosine similarity measures geometric closeness, not relevance to your task. A retrieval system with P@5 = 0.4 can look functional during demos (it returns *something*) while silently failing users. Build an eval set from day one.

- **Ignoring inference latency and cost.** A 70B-parameter model at 32-bit precision requires ~140 GB of GPU VRAM. Quantizing to INT4 cuts that to ~35 GB with < 5% quality loss. Engineers who don't understand AI infrastructure approve architectures that cost 10× what they need to.

- **Applying RL when supervised learning would work.** RL is the right tool when the environment is interactive and rewards are delayed. It's the wrong tool when you have labeled data — it's much harder to train, debug, and reproduce. Most recommendation and ranking problems are better solved with supervised learning on logged feedback.

- **Ignoring data distribution shift.** A model trained on last year's data degrades silently as the real-world distribution changes. Model evaluation is not a one-time activity at launch — build continuous evaluation pipelines with freshness checks and drift alerts.

---

## Exercises

1. **Easy** — For each of the five concept groups (Foundations, Data & Representation, Model Families, Apply & Adapt, Operations), name one real product or feature you use daily and identify which concept(s) from that group it relies on most heavily.

2. **Medium** — Take the semantic search pipeline from "Build It / In Depth" and extend it with a re-ranking step: after retrieving the top 20 results with ANN search, use a cross-encoder model (e.g., `cross-encoder/ms-marco-MiniLM-L-6-v2` from Hugging Face) to rerank them and return only the top 5. Measure whether P@5 improves on your eval set.

3. **Hard** — Design an AI agent for a customer support use case: it receives a user question, retrieves relevant tickets from the vector store, checks a live CRM API for the user's account status, decides whether to escalate or auto-resolve, and drafts a reply. Define the tool schema, the system prompt, the loop termination condition, and describe where failures most likely occur and how you would monitor for them.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Fine-tuning** | Training the model from scratch on your data | Continuing training of an already-trained model on new data to shift its behavior; weights are updated but not randomly initialized |
| **Embedding** | A compressed summary of text | A dense real-valued vector in a high-dimensional space where semantic similarity corresponds to geometric proximity |
| **Hallucination** | The model lying | The model generating fluent, confident text that is factually incorrect because it is predicting likely next tokens, not retrieving facts |
| **Prompt Engineering** | Just asking nicely | Systematic design of the input structure — examples, role, format constraints, chain-of-thought instructions — to steer model output toward the desired behavior |
| **Transformer** | Another name for an LLM | The specific neural network architecture (self-attention + feed-forward layers) that underpins LLMs, but also BERT, ViT, Whisper, and many non-language models |
| **Agent** | An AI that does things autonomously | An LLM-driven loop where the model reasons about which tool to call, observes the result, and iterates — reliability drops sharply with loop depth |
| **Vector Search** | Full-text search with AI | Approximate nearest-neighbor retrieval in embedding space; fundamentally different from keyword matching — it finds semantically similar items, not textually matching ones |

---

## Further Reading

- [Attention Is All You Need (Vaswani et al., 2017)](https://arxiv.org/abs/1706.03762) — the original transformer paper; surprisingly readable; defines the architecture underlying almost everything in modern AI.
- [Hugging Face NLP Course](https://huggingface.co/learn/nlp-course) — free, hands-on, covers tokenizers → fine-tuning → deployment; the best practical intro to transformer-based NLP.
- [Chip Huyen — Designing Machine Learning Systems (O'Reilly, 2022)](https://www.oreilly.com/library/view/designing-machine-learning/9781098107956/) — production-focused; covers feature engineering, evaluation, infrastructure, and monitoring with real system examples.
- [Lilian Weng's Blog — Prompt Engineering](https://lilianweng.github.io/posts/2023-03-15-prompt-engineering/) — comprehensive, rigorous survey of prompting techniques with empirical grounding.
- [vLLM Documentation](https://docs.vllm.ai) — reference for high-throughput LLM serving; explains KV-cache, continuous batching, and quantization from an engineering perspective.
