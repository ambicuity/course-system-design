# Full Fine-Tuning vs LoRA vs RAG

> Teach the model new behavior, teach it new facts, or hand it a cheat sheet — these are fundamentally different operations.

**Type:** Learn
**Prerequisites:** Transformer Architecture Basics, Embeddings and Vector Search, Prompt Engineering
**Time:** ~35 minutes

---

## The Problem

Your company has a 70 B-parameter open-source LLM. Out of the box it writes generic business prose. You need it to write in your legal team's citation style, stay current with contracts signed last week, and never hallucinate jurisdiction-specific statutes. You've heard "fine-tune it" and "add RAG" in the same meeting, and no one could agree which to do first.

The confusion is understandable: all three techniques — full fine-tuning, LoRA, and RAG — ultimately make a model more useful for a specific purpose. But they operate on completely different levers. Full fine-tuning and LoRA change the model's *weights* (how it thinks). RAG changes the model's *context* (what it reads before answering). Confusing the two leads to expensive GPU runs that don't fix knowledge-staleness, or RAG pipelines bolted onto a model that still writes in the wrong tone.

The goal of this lesson is a precise mental model of what each technique actually does so you can make the right architectural call the first time.

---

## The Concept

### The three levers at a glance

```
          ┌──────────────────────────────────────────────────┐
          │               Knowledge sources                  │
          │                                                  │
          │  Pre-training data     Domain data    Live docs  │
          │  (frozen weights)      (fine-tune)   (retrieval) │
          └───────────────┬───────────────┬──────────┬───────┘
                          │               │          │
                          ▼               ▼          ▼
                    [Base LLM]     [Fine-tuned]  [Base LLM]
                                    [LLM]       +[Retriever]
                                                +[Context]
                       RAG changes this arrow ──────────┘
                Fine-tuning changes this arrow ──────────┘
```

### Full Fine-Tuning

Every weight in the model is unfrozen and updated via gradient descent on your labeled dataset. A 7 B-parameter model has 7 billion floats to update every step. In practice this requires:

- Multi-GPU nodes (A100/H100 class) with 40–80 GB VRAM each
- Hours to days of training depending on dataset size
- A full-sized checkpoint on disk (same bytes as the original model)
- A custom optimizer state that can be 2–4× the model size in memory during training

**What actually changes:** the model's internals shift to encode new *behavioral patterns* — what style to output, what label to predict, what schema to follow. It is not a good mechanism for injecting facts. If you train on a document that says "our CEO is Alice", the model may or may not reliably retrieve that fact; it's baked into weights in a lossy way that doesn't generalize like a database lookup.

**Risk — catastrophic forgetting:** when you update all weights aggressively on a narrow dataset the model can lose general capabilities. Weight regularization (L2) or techniques like Elastic Weight Consolidation partially mitigate this.

### LoRA (Low-Rank Adaptation)

LoRA's insight: the weight updates needed to adapt a model to a new task lie in a very low-dimensional subspace. Instead of updating the full weight matrix W ∈ ℝ^(d×k), you freeze W and learn two small matrices:

```
W_adapted = W + B·A
            ───────
            frozen  (d×r)(r×k), r << min(d,k)
```

A common rank is r = 8 or r = 16. For a layer where d = k = 4096, the full matrix has 16 M parameters. LoRA with r = 8 adds only 65 K — a 250× reduction per layer. Across a 7 B model, total LoRA parameters are typically 1–30 M versus 7 000 M.

**Training implications:**
- Runs on a single 24 GB consumer GPU for a 7 B model (with 4-bit quantization — QLoRA)
- Adapter checkpoint is tiny (a few hundred MB vs. 14 GB for the base model)
- Multiple adapters can be swapped at runtime over the same frozen base
- Adapters can be *merged* back into W at inference time to add zero overhead

**QLoRA** stacks quantization on top: the frozen base weights are loaded in 4-bit NF4 format (~4 GB for a 7 B model) while the LoRA adapters remain in bf16. This is the dominant approach for fine-tuning on a single GPU today.

LoRA is applied to specific weight matrices — usually the attention projection matrices (Q, K, V, O) and sometimes the MLP layers. Choosing which matrices to target is a tunable hyperparameter.

### RAG (Retrieval-Augmented Generation)

RAG does not touch weights. At inference time it:

1. Embeds the user's query into a vector
2. Performs approximate nearest-neighbor search against a pre-indexed vector store
3. Fetches the top-k most relevant document chunks
4. Prepends those chunks to the prompt as context
5. Sends the augmented prompt to the LLM

```
User query
    │
    ▼
[Embedding Model]──→ query vector
                          │
                          ▼
                  [Vector Database]
                  (millions of chunks)
                          │ top-k chunks
                          ▼
         ┌─────────────────────────────────┐
         │  SYSTEM: Answer from context.   │
         │  CONTEXT: <chunk1> <chunk2> … │
         │  USER: <original query>         │
         └─────────────────────────────────┘
                          │
                          ▼
                        [LLM]
                          │
                          ▼
                       Answer
```

The knowledge lives in the vector store, not in the model. Updating knowledge means re-chunking and re-embedding documents — no GPU training required.

### Side-by-side comparison

| Dimension | Full Fine-Tuning | LoRA | RAG |
|---|---|---|---|
| What changes | All model weights | Small adapter matrices | Inference context only |
| GPU training needed | Yes — large cluster | Yes — single GPU feasible | No |
| Typical training time | Hours–days | Minutes–hours | None |
| Knowledge update cost | Full retrain | Adapter retrain | Re-embed documents |
| Knowledge freshness | Frozen at train time | Frozen at train time | Real-time |
| Inference latency | Baseline | Same as merged model | +50–200 ms (retrieval) |
| Hallucination control | Poor | Poor | Better (grounded in chunks) |
| Best for | Behavior / style / format | Behavior / style (cheaper) | Factual / up-to-date knowledge |
| Disk footprint | Full model copy | Small adapter (~0.1–1% of base) | Vector index + base model |

---

## Build It / In Depth

### Choosing the right technique — a decision tree

```
Is your problem about BEHAVIOR or KNOWLEDGE?
├── BEHAVIOR (style, format, task type, tone, output schema)
│   ├── Do you have >10 000 high-quality labeled examples?
│   │   ├── YES → Full fine-tuning (if compute budget allows)
│   │   └── NO  → LoRA (or QLoRA for single-GPU)
│   └── Do you need multiple specialized variants of the same base?
│       └── YES → LoRA adapters (one per variant, share the base)
└── KNOWLEDGE (facts, documents, current events, proprietary data)
    ├── Is the knowledge large (>100 MB) or updated frequently?
    │   └── YES → RAG
    └── Is the knowledge small, stable, and fits in context?
        └── Consider few-shot prompting first (no infrastructure needed)
```

### LoRA fine-tuning with Hugging Face PEFT

```python
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from peft import LoraConfig, get_peft_model, TaskType
from trl import SFTTrainer
import torch

model_id = "meta-llama/Llama-3-8b"

# Load base model in 4-bit (QLoRA)
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    load_in_4bit=True,
    torch_dtype=torch.bfloat16,
    device_map="auto",
)
tokenizer = AutoTokenizer.from_pretrained(model_id)

# Define LoRA config
lora_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=16,               # rank — higher = more capacity, more params
    lora_alpha=32,      # scaling factor; effective lr = alpha/r
    target_modules=["q_proj", "v_proj"],  # which attention matrices
    lora_dropout=0.05,
    bias="none",
)

model = get_peft_model(model, lora_config)
model.print_trainable_parameters()
# Output: trainable params: 4,194,304 || all params: 8,033,669,120 (0.052%)

training_args = TrainingArguments(
    output_dir="./lora-adapter",
    num_train_epochs=3,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,
    learning_rate=2e-4,
    fp16=False,
    bf16=True,
    logging_steps=10,
)

trainer = SFTTrainer(
    model=model,
    train_dataset=dataset,          # your HuggingFace Dataset
    dataset_text_field="text",
    tokenizer=tokenizer,
    args=training_args,
    max_seq_length=2048,
)

trainer.train()
# Save only the adapter (small)
model.save_pretrained("./lora-adapter")
```

To merge the adapter back into the base weights for zero-overhead inference:

```python
from peft import PeftModel

base = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=torch.bfloat16)
merged = PeftModel.from_pretrained(base, "./lora-adapter")
merged = merged.merge_and_unload()
merged.save_pretrained("./merged-model")
```

### Minimal RAG pipeline (LangChain + Chroma)

```python
from langchain_community.document_loaders import DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.chains import RetrievalQA
from langchain_community.llms import HuggingFacePipeline

# 1. Load and chunk documents
loader = DirectoryLoader("./contracts", glob="**/*.pdf")
docs = loader.load()

splitter = RecursiveCharacterTextSplitter(
    chunk_size=512,      # tokens, roughly
    chunk_overlap=64,    # overlap prevents context loss at boundaries
)
chunks = splitter.split_documents(docs)

# 2. Embed and index
embed_model = HuggingFaceEmbeddings(model_name="BAAI/bge-base-en-v1.5")
vectorstore = Chroma.from_documents(chunks, embed_model, persist_directory="./chroma_db")

# 3. Build RAG chain
retriever = vectorstore.as_retriever(search_kwargs={"k": 4})
llm = HuggingFacePipeline.from_model_id("mistralai/Mistral-7B-Instruct-v0.2", ...)
chain = RetrievalQA.from_chain_type(llm=llm, retriever=retriever, return_source_documents=True)

result = chain.invoke({"query": "What is the termination clause in contract #2024-089?"})
print(result["result"])
print(result["source_documents"])  # grounding evidence
```

### Real numbers: parameter count for a 7B model

| Approach | Trainable params | GPU RAM (training) | Checkpoint size |
|---|---|---|---|
| Full fine-tuning | 7 000 M (100%) | 80–160 GB | ~14 GB (bf16) |
| LoRA r=8 | ~4 M (0.06%) | 6–10 GB (with QLoRA) | ~32 MB |
| LoRA r=64 | ~33 M (0.47%) | 14–18 GB (with QLoRA) | ~256 MB |
| RAG | 0 (no training) | Not applicable | Vector index |

---

## Use It

### When specific tools and cloud services apply

**Full fine-tuning**
- Use when you are building a specialized model to deploy at massive scale where inference cost matters enough to justify the training cost
- AWS SageMaker HyperPod, Google Cloud TPU pods, Azure ML GPU clusters
- Datasets: typically 10 K–1 M+ examples; format them as instruction–completion pairs (Alpaca, ShareGPT, ChatML formats)

**LoRA / QLoRA**
- The default choice for most application teams doing behavior adaptation
- Hugging Face PEFT library (open source, de facto standard)
- Axolotl, LLaMA-Factory, Unsloth (training speed optimizations)
- Modal, RunPod, Lambda Labs (cheap on-demand GPU rental for adapter training)
- Replicate, Together AI (serve the merged adapter without managing infrastructure)

**RAG**
- Correct choice when knowledge must stay fresh or is too large to fine-tune in
- LlamaIndex and LangChain are the most common orchestration frameworks
- Vector databases: Pinecone (managed), Weaviate (self-hosted or cloud), Qdrant (Rust-based, fast), pgvector (if you're already on Postgres), ChromaDB (local dev)
- Embedding models: OpenAI `text-embedding-3-small`, `BAAI/bge-m3` (multilingual), `Cohere embed-v3`

**Combining techniques** — not mutually exclusive:
- LoRA to fix behavior + RAG to supply knowledge is a common production stack
- Fine-tune a model to follow your output schema reliably, then RAG-inject the factual content at inference time

---

## Common Pitfalls

- **Fine-tuning to inject facts.** Weights encode patterns, not lookup tables. If you train on a fact it may appear in training loss but fail to surface reliably at inference. For "the policy document says X" type knowledge, use RAG.

- **Chunking too coarsely (or too finely) in RAG.** Chunks of 2 000+ tokens overwhelm the model's attention on the relevant sentence. Chunks of 50 tokens lose surrounding context needed for comprehension. Experiment around 256–512 tokens with 10–15% overlap as a starting point.

- **Skipping the embedding model evaluation.** The retrieval quality is bounded by the embedding model. Do not assume the cheapest embedding model is good enough. Evaluate NDCG@k or recall@k on your actual queries before building the full pipeline.

- **Forgetting the rank–alpha relationship in LoRA.** `lora_alpha` is a scaling multiplier: the effective update magnitude is `alpha / r`. If you increase r to gain capacity but forget to increase alpha proportionally, you effectively reduce the learning rate. A common default: set `alpha = 2 * r`.

- **Not evaluating catastrophic forgetting after full fine-tuning.** Always run the base model's benchmark suite (MMLU, HellaSwag, etc.) on your fine-tuned checkpoint. A domain fine-tune that drops general reasoning by 20% is often not worth the accuracy gain on the narrow task.

---

## Exercises

1. **Easy — Classify the technique.** For each scenario, state which technique you would use and why: (a) A customer-service bot needs to answer questions about your product catalog that updates weekly. (b) A code assistant needs to output only valid JSON with a specific schema. (c) A medical transcription tool needs to learn clinical abbreviations and adapt to an ER department's note style.

2. **Medium — Adapter arithmetic.** A Llama 3 8B model has attention projection matrices of shape (4096, 4096). You apply LoRA with r = 16 to Q, K, V, and O projections across all 32 layers. Calculate the total number of trainable LoRA parameters and express it as a percentage of the 8 B base model.

3. **Hard — Architecture decision.** You are building a legal research assistant. The model must: (1) write in a formal legal style, (2) cite clauses from 200 000 contract PDFs, and (3) refuse to speculate when the answer is not in the documents. Design a full system: which models to use, where LoRA fits, how the RAG pipeline is structured, and how you enforce the refusal behavior. Identify at least two failure modes and how you mitigate them.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Fine-tuning | Retraining a model from scratch on your data | Continuing training of a pre-trained model on new data; only updates are new, the base knowledge is preserved to varying degrees |
| LoRA adapter | A plugin that replaces the model | A pair of small matrices (B, A) whose product is *added* to existing frozen weight matrices — the base weights never change |
| Catastrophic forgetting | A rare edge case in fine-tuning | The well-documented tendency for aggressive weight updates on a narrow dataset to degrade general capabilities encoded in earlier training |
| RAG hallucination | RAG eliminates hallucination | RAG reduces unsupported claims by grounding the model in retrieved context, but the LLM can still misinterpret, paraphrase incorrectly, or ignore chunks |
| Rank (r) in LoRA | Bigger rank = always better | Higher rank adds expressivity and parameter count; beyond a task-specific threshold it adds parameters with no accuracy benefit and increases memory cost |
| Embedding model | Interchangeable with the generation model | A separate encoder-only or bi-encoder model tuned for semantic similarity; swapping it changes retrieval quality independently of the LLM |
| QLoRA | Quantization that replaces LoRA | Quantization applied to the *frozen base model* to reduce memory; LoRA adapters still train in full precision (bf16) on top |

---

## Further Reading

- **LoRA original paper** — Hu et al. (2021): https://arxiv.org/abs/2106.09685 — the derivation of the low-rank hypothesis and all core hyperparameter guidance
- **QLoRA paper** — Dettmers et al. (2023): https://arxiv.org/abs/2305.14314 — how 4-bit NF4 quantization + double quantization + paged optimizers enable single-GPU fine-tuning of 65 B models
- **RAG original paper** — Lewis et al. (2020): https://arxiv.org/abs/2005.11401 — the Facebook AI paper that named and formalized retrieval-augmented generation
- **Hugging Face PEFT documentation**: https://huggingface.co/docs/peft — practical reference for LoRA, QLoRA, and other parameter-efficient fine-tuning methods
- **LlamaIndex RAG tutorial**: https://docs.llamaindex.ai/en/stable/getting_started/concepts/ — production-oriented guide covering chunking strategy, retriever types, and evaluation metrics
