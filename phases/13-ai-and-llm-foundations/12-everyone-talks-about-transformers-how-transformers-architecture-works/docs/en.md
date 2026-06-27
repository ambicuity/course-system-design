# Everyone talks about Transformers. How Transformers Architecture Works?

> The architecture behind every modern LLM — explained as the sequence of operations, not a black box.

**Type:** Learn
**Prerequisites:** Basic linear algebra (vectors, matrices), Neural networks basics
**Time:** ~30 minutes

---

## The Problem

Every modern large language model — GPT, Claude, Gemini, Llama, DeepSeek, Mistral, Qwen — is built on the **transformer architecture**. You cannot understand how LLMs work, why they hallucinate, why context length matters, or why they are expensive without understanding transformers. And yet most explanations of transformers either drown you in math or skip the mechanics entirely.

The transformer is not magic. It is a sequence of well-defined operations: embed the input, add positional information, run attention many times, project back to vocabulary. Once you see the steps as a pipeline, the rest of LLM behavior — context windows, attention patterns, scaling laws — falls out naturally.

This lesson walks the transformer end-to-end. By the end, you should be able to explain what each component does, why it is there, and what would break if you removed it.

---

## The Concept

### The transformer at a glance

The original transformer (Vaswani et al., 2017, "Attention is All You Need") has two halves: an **encoder** that reads input and a **decoder** that generates output. Most modern LLMs (GPT, Claude, Llama) are decoder-only — they only generate text. Encoder-only models (BERT) and encoder-decoder models (T5) are used for different tasks.

```
   ┌─────────────────────────────────────────────────────────────┐
   │                    ENCODER (N times)                         │
   │                                                             │
   │   Input → Embedding → Positional Encoding                  │
   │                              │                              │
   │                              ▼                              │
   │                     Multi-Head Attention                    │
   │                              │                              │
   │                              ▼                              │
   │                       Add & Normalize                       │
   │                              │                              │
   │                              ▼                              │
   │                       Feed Forward                          │
   │                              │                              │
   │                              ▼                              │
   │                       Add & Normalize                       │
   │                              │                              │
   │                              ▼                              │
   │                       (repeat N times)                      │
   └─────────────────────────────────────────────────────────────┘

   ┌─────────────────────────────────────────────────────────────┐
   │                    DECODER (N times)                         │
   │                                                             │
   │   Output so far → Embedding → Positional Encoding           │
   │                              │                              │
   │                              ▼                              │
   │                  Masked Multi-Head Attention                 │
   │                              │                              │
   │                              ▼                              │
   │                  Cross-Attention with Encoder               │
   │                              │                              │
   │                              ▼                              │
   │                       Add & Normalize                       │
   │                              │                              │
   │                              ▼                              │
   │                       Feed Forward                          │
   │                              │                              │
   │                              ▼                              │
   │                       Add & Normalize                       │
   │                              │                              │
   │                              ▼                              │
   │                       (repeat N times)                      │
   │                              │                              │
   │                              ▼                              │
   │                       Linear → Softmax                      │
   │                              │                              │
   │                              ▼                              │
   │                     Next token (probability)                │
   └─────────────────────────────────────────────────────────────┘
```

For a decoder-only LLM (which is what most people mean by "transformer" today), only the right half runs, and it loops, generating one token at a time.

---

### Step 1: Input Embedding

The transformer operates on vectors, not words. The first step is to convert each token into a dense vector.

```
   "The cat sat" → [tokenize] → [34, 12, 5678, 99, ...]
                                       │
                                       ▼
                                 [embed each]
                                       │
                                       ▼
                  [
                    [0.12, -0.34, 0.78, ...],   # "The"
                    [0.45,  0.22, -0.11, ...],  # "cat"
                    [-0.67, 0.89, 0.33, ...],   # "sat"
                    ...
                  ]
                  shape: (sequence_length, embedding_dim)
```

Each token maps to a fixed-size vector (e.g., 4096 dimensions in a 7B model). The vector is *learned* during training — the model learns that semantically similar tokens should have similar vectors. The embedding table is a matrix of shape `(vocabulary_size, embedding_dim)` and is part of the model's learned parameters.

---

### Step 2: Positional Encoding

Self-attention is **permutation-invariant** — it does not know that "the cat sat" is different from "sat the cat." Without positional information, the model would treat these as the same sentence.

```
   Without positional encoding:
   "the cat ate the fish"  ≈  "fish the ate cat the"

   With positional encoding:
   Position 0 → [sin(0), cos(0), sin(0/100), ...]  # unique to position 0
   Position 1 → [sin(1), cos(1), sin(1/100), ...]  # unique to position 1
   ...
```

Positional encoding is a vector added to each token's embedding that encodes its position in the sequence. The original transformer used sinusoidal functions; modern LLMs often use **rotary positional embeddings (RoPE)** or **ALiBi**, which generalize better to longer sequences.

**What this gives the model:** the ability to reason about word order, which is essential for grammar, narrative, and most language tasks.

---

### Step 3: Multi-Head Attention

This is the heart of the transformer. It is the only operation that lets information flow between positions — every other operation is applied independently to each position.

**The mechanism:**

```
   For each token's vector x:
       1. Project to three vectors: Q (query), K (key), V (value)
            Q = x · W_Q
            K = x · W_K
            V = x · W_V

       2. Compute attention scores: how much should token i attend to token j?
            score(i, j) = Q_i · K_j  /  sqrt(d_k)

       3. Softmax to get attention weights (probabilities):
            weights(i, j) = softmax(score(i, .))

       4. Weighted sum of values:
            output_i = sum_j  weights(i, j) · V_j
```

**In plain English:** each token asks "which other tokens should I pay attention to?" by comparing its query to every other token's key, then reads off a weighted mixture of their values.

**Multi-head** means running this several times in parallel with different learned projections, then concatenating the results. Different heads learn to attend to different things — one might track syntax, another might track coreference, another might track long-range dependencies.

---

### Step 4: Add & Normalize

After each major sublayer (attention, feed-forward), the transformer adds the input back and normalizes:

```
   output = LayerNorm(x + Sublayer(x))
```

This is called a **residual connection**. It solves two problems:

1. **Vanishing gradients.** Deep networks are hard to train because gradients shrink as they backpropagate. Residual connections provide a "highway" for gradients to flow.
2. **Information preservation.** The sublayer adds information to the input rather than replacing it.

LayerNorm (Layer Normalization) keeps the activations well-scaled, which stabilizes training. Without it, activations can explode or vanish.

---

### Step 5: Feed-Forward Network

Each position independently passes through a two-layer fully connected network:

```
   FFN(x) = max(0, x · W1 + b1) · W2 + b2
```

(With modern activations like GELU or SwiGLU instead of ReLU.)

The FFN is where the model stores "knowledge" — facts it has learned. Attention mixes information between positions; the FFN processes each position's information independently and adds depth.

In a 7B model, the FFN hidden dimension is around 11000 — much larger than the model's 4096-dimensional residual stream. This expansion-then-contraction pattern is repeated in every transformer layer.

---

### Step 6: Stacking layers

The transformer repeats the entire block (attention + FFN + residuals) many times:

```
   GPT-3 small:     12 layers
   GPT-3 175B:      96 layers
   Llama 3 70B:     80 layers
   Claude 3.5:      ~80 layers (estimated)
```

Each layer refines the representation a little more. Early layers tend to capture surface features (syntax, word identity). Middle layers capture more abstract patterns (semantic roles, entity relationships). Late layers capture task-specific reasoning.

---

### Step 7: The decoder's extra trick — masking

Decoder-only models generate text one token at a time. During training, they see the full target sequence at once but must not "cheat" by looking at future tokens.

```
   Mask matrix (lower triangular):
   ┌───────────────────────┐
   │ 1  0  0  0  0  0  0  0 │  position 0 attends only to itself
   │ 1  1  0  0  0  0  0  0 │  position 1 attends to 0, 1
   │ 1  1  1  0  0  0  0  0 │  position 2 attends to 0, 1, 2
   │ 1  1  1  1  0  0  0  0 │  ...
   │ 1  1  1  1  1  0  0  0 │
   │ 1  1  1  1  1  1  0  0 │
   │ 1  1  1  1  1  1  1  0 │
   │ 1  1  1  1  1  1  1  1 │
   └───────────────────────┘
```

This **causal mask** ensures that position i only attends to positions ≤ i. The model learns to predict the next token using only previous tokens — exactly what it must do at inference time.

---

### Step 8: Linear → Softmax → Next token

After all the layers, the final vector for each position is projected back to vocabulary size and turned into probabilities:

```
   final_vector  ──×──  W_vocab  ──►  scores for each of 50,000 tokens
                                          │
                                          ▼
                                       softmax
                                          │
                                          ▼
                              [0.01, 0.04, 0.82, ...]   # probability per token
                                          │
                                          ▼
                                       sample / argmax
                                          │
                                          ▼
                                      next token
```

At inference, the model picks the next token (greedy, sampling, beam search, or top-p) and appends it to the sequence, then loops.

---

### The full pipeline

```
   "The cat"
       │
       ▼
   Tokenize: ["The", "cat"] → [34, 5678]
       │
       ▼
   Embed: each token → vector (shape: 2 × 4096)
       │
       ▼
   Add positional encoding
       │
       ▼
   ┌─────────────────────────────────────────┐
   │  Repeat 80 times:                        │
   │                                         │
   │    Multi-Head Self-Attention            │
   │           │                             │
   │           ▼                             │
   │    Add & Norm                           │
   │           │                             │
   │           ▼                             │
   │    Feed-Forward Network                 │
   │           │                             │
   │           ▼                             │
   │    Add & Norm                           │
   │                                         │
   └─────────────────────────────────────────┘
       │
       ▼
   Linear projection to vocabulary size
       │
       ▼
   Softmax → probabilities
       │
       ▼
   Sample next token: "sat"
       │
       ▼
   Append "sat" → "The cat sat" → loop again
```

Every modern LLM does this. The differences between models (GPT vs Claude vs Llama) are in details: how attention is implemented, what positional encoding they use, how the FFN is structured, how many layers, how wide, how trained.

---

## Build It / In Depth

### A minimal attention block in PyTorch

```python
import torch
import torch.nn as nn
import torch.nn.functional as F

class MultiHeadAttention(nn.Module):
    def __init__(self, d_model, n_heads):
        super().__init__()
        self.n_heads = n_heads
        self.d_k = d_model // n_heads

        self.W_q = nn.Linear(d_model, d_model)
        self.W_k = nn.Linear(d_model, d_model)
        self.W_v = nn.Linear(d_model, d_model)
        self.W_o = nn.Linear(d_model, d_model)

    def forward(self, x, mask=None):
        B, T, D = x.shape

        # Project to Q, K, V
        Q = self.W_q(x).view(B, T, self.n_heads, self.d_k).transpose(1, 2)
        K = self.W_k(x).view(B, T, self.n_heads, self.d_k).transpose(1, 2)
        V = self.W_v(x).view(B, T, self.n_heads, self.d_k).transpose(1, 2)

        # Scaled dot-product attention
        scores = (Q @ K.transpose(-2, -1)) / (self.d_k ** 0.5)
        if mask is not None:
            scores = scores.masked_fill(mask == 0, float('-inf'))
        weights = F.softmax(scores, dim=-1)

        # Weighted sum
        out = weights @ V
        out = out.transpose(1, 2).contiguous().view(B, T, D)
        return self.W_o(out)


class TransformerBlock(nn.Module):
    def __init__(self, d_model, n_heads, d_ff):
        super().__init__()
        self.attn = MultiHeadAttention(d_model, n_heads)
        self.ffn = nn.Sequential(
            nn.Linear(d_model, d_ff),
            nn.GELU(),
            nn.Linear(d_ff, d_model),
        )
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)

    def forward(self, x, mask=None):
        x = x + self.attn(self.norm1(x), mask)   # residual
        x = x + self.ffn(self.norm2(x))         # residual
        return x
```

This is roughly what every transformer-based LLM contains. The differences between models are subtle variations on this structure.

---

### Key design choices that vary between models

| Choice | What it controls | Example variations |
|---|---|---|
| **Positional encoding** | How position is represented | Sinusoidal, RoPE, ALiBi |
| **Attention pattern** | What each token attends to | Full, sliding window, sparse |
| **Normalization** | Where norms go | Pre-norm (GPT, Llama), post-norm (original) |
| **Activation** | The nonlinearity in FFN | ReLU, GELU, SwiGLU |
| **FFN ratio** | FFN hidden size / model dim | 4× (most), 2.7× (PaLM) |
| **Number of heads** | Parallel attention patterns | 32 (GPT-3 175B), 64 (Llama 70B) |
| **Tying** | Whether embeddings are shared | Often tied for small models |

Most of these are minor. The architecture is fundamentally the same everywhere.

---

## Use It

### What this explains about LLMs

| Behavior | Why it happens |
|---|---|
| **Hallucinations** | The model predicts plausible next tokens, not true statements |
| **Context window limits** | Attention is O(n²) in sequence length; very long contexts are expensive |
| **Lost-in-the-middle** | Attention is weaker to the middle of long contexts |
| **Cost scales with output length** | Every output token requires a full forward pass through all layers |
| **Fine-tuning works** | Adjusting the FFN weights changes stored "knowledge" |
| **Quantization works** | The linear layers tolerate lower precision with modest quality loss |

Understanding the architecture turns "LLMs do magic" into "LLMs do well-defined math."

---

### Key papers to know

| Paper | Year | Contribution |
|---|---|---|
| **Attention Is All You Need** | 2017 | The original transformer |
| **BERT** | 2018 | Encoder-only model for understanding |
| **GPT-2 / GPT-3** | 2019–20 | Decoder-only scaling, in-context learning |
| **T5** | 2019 | Unified text-to-text framework |
| **RoFormer (RoPE)** | 2021 | Rotary positional embeddings |
| **FlashAttention** | 2022 | Memory-efficient attention |
| **Llama / Llama 2 / Llama 3** | 2023–24 | Open-weight models that closed the gap with closed models |
| **Mixtral of Experts** | 2023 | Sparse Mixture-of-Experts |

---

## Common Pitfalls

- **Treating attention as magic.** Attention is just a learned weighted average. The "magic" is in the learning, not the operation.

- **Ignoring the cost.** Self-attention is O(n²) in sequence length. Doubling the context window quadruples the attention compute. This is why context length matters for both cost and latency.

- **Conflating "transformer" with "GPT."** The transformer is the architecture. GPT, Claude, Llama, etc. are specific implementations. There are encoder-only, decoder-only, and encoder-decoder variants.

- **Forgetting positional encoding.** Without it, the model is permutation-invariant — it cannot distinguish "dog bites man" from "man bites dog."

- **Assuming larger is always better.** Architecture choices matter as much as size. A well-designed small model often beats a poorly-designed large one.

- **Treating layer count as the only scaling axis.** Width (hidden dim), depth (layers), and head count all scale differently. Modern models trade depth for width or vice versa depending on the use case.

---

## Exercises

1. **Easy** — Draw the transformer pipeline from input to output. Label each component (embedding, positional encoding, attention, FFN, etc.) and one sentence per component on what it does.

2. **Medium** — Implement a single transformer block in PyTorch or your framework of choice. Verify that it can process a small batch of token IDs and produce output of the expected shape.

3. **Hard** — Pick an architectural innovation (RoPE, FlashAttention, sparse attention, MoE). Read the original paper. Write a one-page summary of what problem it solves, how it works, and which production models use it.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Transformer | A type of AI | A neural network architecture based on self-attention; the foundation of every modern LLM (GPT, Claude, Llama) |
| Self-attention | The model understanding context | A weighted average over the input sequence, where the weights are learned; the only operation that lets information flow between positions |
| Multi-head attention | Many attentions in parallel | Running self-attention multiple times in parallel with different learned projections; lets the model attend to different aspects simultaneously |
| Positional encoding | The model knowing word order | A vector added to each token's embedding that encodes its position; without it, the model is permutation-invariant |
| Residual connection | A skip connection | Adding the input of a layer to its output; lets gradients flow through deep networks and preserves information |
| Feed-forward network | A standard neural network layer | A two-layer fully-connected network applied independently at each position; where the model stores "knowledge" |
| Causal mask | The model predicting one token at a time | A triangular mask that prevents each position from attending to future positions during training |
| Token | A word | A discrete unit of text produced by a tokenizer (BPE, SentencePiece); the smallest unit the model processes — not always a full word |

---

## Further Reading

- **"Attention Is All You Need"** — the original transformer paper by Vaswani et al.: https://arxiv.org/abs/1706.03762
- **Andrej Karpathy's "Let's build GPT: from scratch, in code, spelled out"** — a hands-on video implementing a transformer from scratch: https://www.youtube.com/watch?v=kCc8FmEb1nY
- **3Blue1Brown's transformer series** — visual, intuitive explanations of attention and transformers: https://www.3blue1brown.com/topics/neural-networks
- **The Illustrated Transformer** — Jay Alammar's classic visual walkthrough: https://jalammar.github.io/illustrated-transformer/
- **Lil'Log** — Lilian Weng's technical blog, with deep dives on transformer variants: https://lilianweng.github.io/