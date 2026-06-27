# How Large Language Models Work?

> LLMs are next-token predictors trained at civilizational scale — every capability emerges from that one objective.

**Type:** Learn
**Prerequisites:** Transformers and Attention Mechanisms, Tokenization Basics, Neural Network Fundamentals
**Time:** ~35 minutes

---

## The Problem

You're building a product on top of GPT-4 or Claude. A user complains that the model "hallucinated" a legal citation. Your on-call team asks: why did it do that, and can we fix it? Without understanding how LLMs actually produce text — token by token, through learned probability distributions — you have no mental model for debugging, no framework for choosing fine-tuning vs. prompt engineering vs. RAG, and no intuition for why increasing temperature makes the model more "creative" or why a 128k context window costs more than a 4k one.

The same gap hurts at design time. Should you use a base model or an instruction-tuned one? When does LoRA suffice vs. full fine-tuning? Why does quantization to INT8 degrade some tasks but not others? These are everyday engineering decisions that require a working mental model of what the model is doing internally.

This lesson gives you that model — from raw bytes to a deployed chat API — grounded enough to reason through real production problems.

---

## The Concept

### The One-Line Mental Model

An LLM is a function that maps a sequence of tokens to a probability distribution over the next token. Everything else — the apparent "understanding", the multi-step reasoning, the stylistic range — is an emergent consequence of training that function on enough data with enough parameters.

```
P(token_t | token_1, token_2, ..., token_{t-1})
```

### Step 1 — Tokenization

Text is not fed character-by-character or word-by-word. It is split into **tokens** — sub-word units chosen to balance vocabulary size against coverage. The dominant algorithm is **Byte Pair Encoding (BPE)**, used by GPT models. Alternatives include WordPiece (BERT, Gemini) and SentencePiece (LLaMA, T5).

| Algorithm | Splitting unit | Used by |
|-----------|---------------|---------|
| BPE | Frequent byte pairs merged greedily | GPT-4, Claude, LLaMA |
| WordPiece | Maximises likelihood of training data | BERT, Gemini |
| SentencePiece | Language-agnostic, treats text as Unicode bytes | T5, Mistral |

A vocabulary of ~50,000–100,000 tokens is typical. English prose averages ~0.75 tokens per word; code tends to 1–1.5 tokens per word because identifiers and symbols tokenize less efficiently.

**Why it matters for engineers:** Token count drives cost and context-window usage. "How are you?" is 5 tokens in GPT-4, not 4 words.

### Step 2 — Embeddings

Each token ID is mapped to a dense vector — an **embedding** — of dimension `d_model` (typically 512–12,288 depending on model size). Position information is injected via **positional encodings** so the model knows that "bank" in position 3 is different from "bank" in position 20.

```
Input text  →  Token IDs  →  Embedding matrix lookup  →  [seq_len × d_model] tensor
              [8, 543, 2]       E ∈ R^{vocab × d_model}
```

### Step 3 — The Transformer Stack

The embedding tensor passes through `N` identical transformer layers (GPT-3 has 96; GPT-4 is estimated at ~120). Each layer has two sub-components:

```
┌─────────────────────────────────────┐
│         Transformer Layer           │
│                                     │
│  Input x                            │
│    │                                │
│    ▼                                │
│  LayerNorm                          │
│    │                                │
│    ▼                                │
│  Multi-Head Self-Attention  ──┐     │
│    │                          │     │
│    └──── residual add ◄───────┘     │
│    │                                │
│    ▼                                │
│  LayerNorm                          │
│    │                                │
│    ▼                                │
│  Feed-Forward Network  ──────┐      │
│    │                         │      │
│    └──── residual add ◄──────┘      │
│    │                                │
│  Output x'                          │
└─────────────────────────────────────┘
```

#### Self-Attention (the Key Mechanism)

For each token, three vectors are derived via learned weight matrices:
- **Q** (Query): what this token is looking for
- **K** (Key): what this token offers to others
- **V** (Value): the content to propagate if attention is high

Attention scores for a sequence:

```
Attention(Q, K, V) = softmax( QK^T / √d_k ) · V
```

Dividing by `√d_k` prevents the dot products from saturating the softmax at large dimensions. The result is a weighted sum of Value vectors — each token "reads" the entire context and blends information proportionally.

**Multi-head** attention runs this `h` times in parallel (e.g., `h=96` in GPT-3), each head attending to different structural relationships (subject-verb agreement, coreference, long-range dependencies).

#### Feed-Forward Sublayer

After attention, each token passes through an independent 2-layer MLP:

```
FFN(x) = max(0, xW₁ + b₁)W₂ + b₂
```

This is where most of the model's "knowledge" is stored. Research shows individual neurons here fire for specific factual associations (e.g., "Eiffel Tower → Paris").

### Step 4 — Pre-Training

The model is trained on trillions of tokens with a **causal language modeling** objective: given tokens 1..t-1, predict token t. Loss is cross-entropy over the vocabulary:

```
L = -Σ log P(token_t | token_1..t-1)
```

Training a GPT-4-class model requires:
- ~13 trillion tokens of cleaned text
- Thousands of A100/H100 GPUs running for months
- Gradient updates via Adam optimiser with careful learning-rate scheduling

At this scale, the model learns grammar, facts, code, logical structure, and multi-step reasoning — all as a side effect of compressing the training distribution into its parameters.

### Step 5 — Fine-Tuning

A base model is a raw next-token predictor. It will complete "How do I make a bomb?" with whatever text statistically follows on the internet. Fine-tuning aligns it:

| Technique | What it does | Cost | Use when |
|-----------|-------------|------|----------|
| **SFT** (Supervised Fine-Tuning) | Train on curated (prompt, response) pairs | Medium | Changing task format or domain |
| **RLHF** (Reinforcement Learning from Human Feedback) | Reward model ranks outputs; PPO optimises toward high reward | High | Alignment, safety, helpfulness |
| **LoRA** (Low-Rank Adaptation) | Trains small rank-decomposed matrices alongside frozen weights | Very low | Domain adaptation on a budget |
| **DPO** (Direct Preference Optimisation) | Learns preferences directly without a reward model | Medium | Cheaper alternative to RLHF |

LoRA is the dominant production fine-tuning method for teams that don't have Google-scale compute: instead of updating W (which might be 4096×4096 = 16M params), it trains two small matrices A (4096×r) and B (r×4096) where r is 8–64, cutting trainable parameters by 100-1000×.

### Step 6 — Inference and Decoding

At inference, the model runs a forward pass and produces a logit vector of size `vocab_size`. A **sampling strategy** converts logits to the output token:

| Strategy | Description | When to use |
|----------|-------------|-------------|
| Greedy | Always pick highest probability | Deterministic; repetitive on long outputs |
| Temperature sampling | Divide logits by T before softmax; T<1 sharpens, T>1 flattens | Creative tasks at T=0.7–1.2 |
| Top-k | Sample only from k highest-probability tokens | Balanced diversity control |
| Top-p (nucleus) | Sample from smallest set whose cumulative P ≥ p | Better than top-k at adapting to distribution shape |
| Beam search | Maintain k candidate sequences | Translation, summarisation |

The model generates **one token at a time** in an autoregressive loop. A 500-token response requires 500 forward passes. This is why **KV caching** is critical: the Keys and Values for every previous token are cached so each new forward pass only computes attention for the newest token, not the full sequence.

---

## Build It / In Depth

### Worked Example: Tracing a Single Forward Pass

Imagine a tiny model with `d_model=4`, 1 layer, vocabulary of 6 tokens: `["I", "love", "cats", "dogs", ".", "<EOS>"]`.

**Input:** "I love"
**Token IDs:** [0, 1]

**1. Embedding lookup:**
```
token 0 ("I")    →  [0.1, 0.3, -0.2, 0.5]
token 1 ("love") →  [0.4, -0.1, 0.6, 0.2]
```

**2. Self-attention (simplified, 1 head):**
```
Q = X · Wq   # [2 × 4] × [4 × 4] = [2 × 4]
K = X · Wk
V = X · Wv

scores = Q · K^T / √4
       = [[q0·k0, q0·k1],
          [q1·k0, q1·k1]]

# Causal mask: token 1 cannot attend to future tokens,
# so scores[0][1] = -inf

attn_weights = softmax(masked_scores)
output = attn_weights · V
```

**3. FFN + residual → logits over vocabulary [6 values]:**
```
logits = [-1.2, 0.3, 2.1, 0.8, -0.5, -2.0]
# Highest: index 2 ("cats")
```

**4. Sampling (greedy):** Output = "cats"

**5. Next iteration:** Input becomes "I love cats", repeat.

### Minimal Inference in Python (using HuggingFace)

```python
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

model_name = "meta-llama/Meta-Llama-3-8B-Instruct"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name, torch_dtype=torch.float16)

prompt = "Explain transformers in one sentence:"
inputs = tokenizer(prompt, return_tensors="pt")

# Generate up to 50 new tokens
with torch.no_grad():
    output_ids = model.generate(
        **inputs,
        max_new_tokens=50,
        temperature=0.7,
        top_p=0.9,
        do_sample=True,
    )

response = tokenizer.decode(output_ids[0], skip_special_tokens=True)
print(response)
```

### KV-Cache Impact (Numbers)

For a model with `d_model=4096`, `n_heads=32`, `n_layers=32`, and a 4096-token context:

```
KV cache size per token  = 2 × n_layers × d_model × sizeof(float16)
                         = 2 × 32 × 4096 × 2 bytes
                         = 524 KB per token

For 4096 tokens:         = 4096 × 524 KB ≈ 2 GB
```

This explains why serving long-context models is memory-bound and why KV cache eviction policies (sliding window, StreamingLLM) matter.

---

## Use It

| Scenario | Right tool | Why |
|----------|-----------|-----|
| Chat assistant, general tasks | Instruction-tuned model (GPT-4o, Claude Sonnet, Gemini Pro) | RLHF-aligned for helpfulness and safety |
| Domain adaptation with limited GPU | LoRA fine-tune on open model (LLaMA-3, Mistral) | Cheap, keeps base capability |
| Low-latency edge deployment | Quantised model (GGUF/llama.cpp, GPTQ, AWQ) | 4-bit quantisation gives 4× memory reduction, ~10-15% quality loss |
| Factual accuracy over a private corpus | RAG + base or instruction model | Retrieval grounds generation; cheaper than fine-tuning for knowledge |
| Structured output (JSON, SQL) | Constrained decoding (Outlines, Guidance, llama.cpp grammars) | Forces the sampling distribution to only produce valid tokens |
| High throughput batch inference | vLLM with PagedAttention | Continuous batching, KV-cache paging; 20× throughput vs. naive HuggingFace |

**Cloud hosting options:**

- **OpenAI API / Azure OpenAI** — managed, no ops, per-token pricing
- **Amazon Bedrock / Google Vertex** — cloud-native, IAM-integrated
- **Replicate / Together AI / Fireworks AI** — hosted open models, lower cost
- **Self-hosted (vLLM, TGI, Ollama)** — full control, requires GPU ops expertise

---

## Common Pitfalls

- **Confusing token count with word count.** Prompts that seem short can blow past a context window because code, non-English text, and unusual formatting tokenize inefficiently. Always profile token usage in production with the exact tokenizer the model uses.

- **Using temperature=0 for everything.** Greedy decoding eliminates diversity but also makes the model repetitive on long generations and can get it stuck in loops. Temperature 0 is appropriate for code generation or structured extraction; for prose, T=0.6–0.8 is usually better.

- **Fine-tuning when prompt engineering would suffice.** Fine-tuning is irreversible (it degrades base capabilities), expensive to iterate, and often unnecessary. Exhaustively test system prompts, few-shot examples, and RAG before reaching for fine-tuning.

- **Ignoring KV-cache memory when scaling.** Teams profile GPU VRAM for model weights but forget that long-context requests fill the KV cache and cause OOMs. A 70B model at 128k context can require 40+ GB for cache alone — more than the weights.

- **Expecting deterministic outputs by default.** Even at temperature=0, different hardware, batch sizes, and floating-point implementations can produce different results. Build evaluation and safety checks around statistical distributions, not exact string matching.

---

## Exercises

1. **(Easy)** Given a vocabulary of 50,257 tokens and an input of "The quick brown fox", use the `tiktoken` library (OpenAI's tokenizer) to print each token and its ID. How many tokens is the sentence?

2. **(Medium)** Implement a temperature sweep: for the prompt "Once upon a time", generate 20 tokens at temperatures 0.1, 0.5, 1.0, and 1.5 using a HuggingFace model. Observe and explain the qualitative differences in output.

3. **(Hard)** Set up vLLM locally with a 7B model. Write a benchmark script that measures tokens/second at batch sizes 1, 4, 16, and 64. Profile GPU memory at each batch size and identify the point where KV-cache growth becomes the bottleneck. Propose a mitigation strategy.

---

## Key Terms

| Term | What people think | What it actually means |
|------|------------------|----------------------|
| **Token** | A word | A sub-word unit from a fixed vocabulary; "unbelievable" might be 3 tokens |
| **Context window** | Memory the model has | The maximum number of tokens in the combined input+output; the model sees all of them at once via attention |
| **Hallucination** | The model is "lying" or confused | The model predicts a statistically plausible next token that happens to be factually wrong; it has no truth signal |
| **Temperature** | How "smart" the model is | A divisor applied to logits before softmax; higher values flatten the distribution, producing more diverse (and riskier) outputs |
| **Fine-tuning** | Making the model smarter | Updating the model's weights on new examples; can specialise or align but cannot add new facts reliably |
| **Embedding** | A representation of meaning | A learned vector in high-dimensional space where semantic similarity correlates with geometric proximity |
| **KV Cache** | A database the model queries | A memory buffer storing computed Key and Value matrices for past tokens to avoid recomputing attention on every generation step |

---

## Further Reading

- [Attention Is All You Need (Vaswani et al., 2017)](https://arxiv.org/abs/1706.03762) — the original transformer paper; dense but definitive.
- [The Illustrated Transformer — Jay Alammar](https://jalammar.github.io/illustrated-transformer/) — the best visual walkthrough of self-attention available.
- [Language Models are Few-Shot Learners (GPT-3 paper)](https://arxiv.org/abs/2005.14165) — explains emergent in-context learning and scale effects.
- [LoRA: Low-Rank Adaptation of Large Language Models](https://arxiv.org/abs/2106.09685) — the paper behind the dominant production fine-tuning technique.
- [vLLM: Efficient Memory Management for LLM Serving with PagedAttention](https://arxiv.org/abs/2309.06180) — explains KV-cache paging and why it unlocks high-throughput serving.
