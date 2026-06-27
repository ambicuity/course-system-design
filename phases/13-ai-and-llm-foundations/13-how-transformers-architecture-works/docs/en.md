# How Transformers Architecture Works?

> The same building blocks, recombined — what changes between models, what stays the same, and why.

**Type:** Learn
**Prerequisites:** Everyone talks about Transformers (chapter 12), or equivalent
**Time:** ~20 minutes

---

## The Problem

The previous chapter walked through the canonical transformer end-to-end. That is the right mental model to start with. But it leaves an important question open: if every modern LLM uses the transformer, why do GPT-4, Claude, Gemini, Llama, and DeepSeek feel different? What actually changes between them?

The answer is "more than you might think, less than the marketing suggests." All of them share the same skeleton — tokenize, embed, add positions, run attention many times, project to vocabulary. The differences live in a handful of design choices: how attention is implemented, how positions are encoded, how the FFN is structured, how the model is trained. Those choices compound, and they explain most of the observable differences between models.

This chapter zooms in on the architecture choices that vary between production LLMs, why each choice was made, and what it buys you in capability, cost, or both.

---

## The Concept

### What every transformer shares

Strip away the variations and every transformer has the same skeleton:

```
   Input tokens
        │
        ▼
   Token embedding + positional encoding
        │
        ▼
   ┌──────────────────────┐
   │  N × Transformer Block │
   │  ┌────────────────┐   │
   │  │ Attention      │   │
   │  │   + Residual   │   │
   │  │   + LayerNorm  │   │
   │  └────────────────┘   │
   │  ┌────────────────┐   │
   │  │ Feed-Forward   │   │
   │  │   + Residual   │   │
   │  │   + LayerNorm  │   │
   │  └────────────────┘   │
   └──────────────────────┘
        │
        ▼
   Final norm
        │
        ▼
   Linear projection to vocabulary
        │
        ▼
   Softmax → next token
```

The interesting question is: what changes between models within this skeleton?

---

### Variation 1: Positional encoding

**What it controls:** how the model represents position, which determines how well it generalizes to sequences longer than those seen during training.

| Encoding | How it works | Used by |
|---|---|---|
| **Sinusoidal** (original) | Fixed sine/cosine functions of position | Original transformer (rare now) |
| **Learned absolute** | Trainable embedding per position | BERT, GPT-2 |
| **RoPE (Rotary)** | Rotates query/key vectors by position-dependent angles | Llama, Mistral, DeepSeek, Qwen, GPT-OSS |
| **ALiBi** | Adds linear bias to attention scores | Some early open models |
| **YaRN / NTK-aware** | Extensions of RoPE for longer contexts | Llama 3 (long context) |

**RoPE** has become the de facto standard for modern LLMs because it generalizes well to longer contexts. By rotating Q and K vectors by an angle proportional to their position, RoPE encodes relative distance directly into the attention dot product — and that math extends naturally to positions beyond the training distribution.

**What this means for users:** models trained with RoPE can often extrapolate to longer contexts with minimal fine-tuning. Models trained with absolute positional embeddings hit a hard wall at their training context length.

---

### Variation 2: Attention pattern

**What it controls:** what each token can attend to, which determines both capability and cost.

| Pattern | What each token attends to | Cost | Used by |
|---|---|---|---|
| **Full (causal)** | All previous tokens | O(n²) | GPT-3, Claude, most LLMs |
| **Sliding window** | Last K tokens only | O(n·k) | Mistral (some layers) |
| **Sparse** | Strided or fixed pattern | O(n·√n) | Some research models |
| **Linear attention** | Kernel approximation | O(n) | Research; rarely in production |

Most production LLMs use **full causal attention** — every token attends to every previous token. The cost is O(n²), which is why doubling the context window quadruples the compute. For a 200k-token context, this is a serious bill.

**Sliding window** attention (used in some Mistral layers) keeps cost linear but reduces the model's ability to recall distant context. Modern production models tend to use full attention for capability, with FlashAttention-style memory optimization for cost.

---

### Variation 3: Normalization placement

**What it controls:** training stability, especially at scale.

| Placement | Order | Used by |
|---|---|---|
| **Post-norm** | Sublayer → Add → Norm (original) | Original transformer |
| **Pre-norm** | Norm → Sublayer → Add | GPT-2, GPT-3, Llama, Claude |

**Pre-norm** is the standard for modern LLMs because it is much more stable to train at scale. The residual stream stays clean, gradients flow well, and you do not need careful learning-rate warmup. The original post-norm was elegant but became a training headache at large scales.

---

### Variation 4: Activation function

**What it controls:** the nonlinearity inside the FFN.

| Activation | Formula | Used by |
|---|---|---|
| **ReLU** | `max(0, x)` | Original transformer |
| **GELU** | `x · Φ(x)` | GPT, BERT |
| **SwiGLU** | `x · sigmoid(x) · Wx` | Llama, Mistral, PaLM, most modern LLMs |
| **GeLU** | (variant) | Some models |

**SwiGLU** (a gated linear unit with SiLU/Swish activation) has become the dominant choice for modern LLMs because it consistently improves quality at the same parameter count. It uses three matrices instead of two (an extra "gate" projection), but the quality gain is worth it.

---

### Variation 5: FFN ratio

**What it controls:** how much capacity the FFN has relative to the residual stream.

```
   FFN(x) = activation(x · W1) · W2

   d_model = 4096  (residual stream width)
   d_ff    = 4 × d_model = 16384  (FFN hidden dimension)
```

| Ratio | Used by |
|---|---|
| **4×** | Original transformer, GPT-3 |
| **~2.7×** | PaLM |
| **~2.7× (with SwiGLU)** | Llama, most modern models |

A larger FFN gives more capacity for "knowledge" storage but more compute per token. Modern models often use ~2.7× (with SwiGLU's three matrices) instead of 4× to balance.

---

### Variation 6: Grouped-query attention (GQA)

**What it controls:** memory and cost of inference, especially for long contexts.

| Pattern | How it works | Used by |
|---|---|---|
| **Multi-head** | One K and V per head | Original, GPT-3 |
| **Multi-query (MQA)** | One K and V shared across all heads | Some research |
| **Grouped-query (GQA)** | K and V shared across groups of heads | Llama 2 70B, Llama 3, Mistral |

**GQA** is a clever middle ground: multiple query heads share a smaller number of key/value heads. This dramatically reduces the memory needed to cache K and V during inference (the KV cache is a major memory bottleneck for long contexts) while preserving most of the quality of full multi-head attention.

---

### Variation 7: Mixture of Experts (MoE)

**What it controls:** the model's total parameter count vs. compute per token.

```
   Standard transformer:   every token goes through every parameter
   Mixture of Experts:     each token goes through a subset (2-4 of 64)

   Total parameters:    120B  (across all experts)
   Active per token:    ~5B   (just the 2 selected experts)
```

| Model | Architecture |
|---|---|
| **GPT-OSS 120B** | MoE (router picks 2 of 64 experts) |
| **Mixtral 8x7B** | MoE (router picks 2 of 8 experts) |
| **DeepSeek V3** | MoE (fine-grained, many experts) |
| **GPT-3 175B** | Dense (every token, every parameter) |

**MoE** lets a model have a huge total parameter count (more "knowledge") while keeping compute per token modest (only some parameters fire). The trade-off is increased memory (you need all experts loaded) and more complex serving infrastructure.

---

### Variation 8: Context length and how to extend it

**What it controls:** how much input the model can process at once.

| Model | Native context | Extended |
|---|---|---|
| GPT-3 | 2k | — |
| GPT-4 | 8k | 32k, 128k |
| Claude 3.5 | 200k | — |
| Gemini 1.5 Pro | 1M–2M | — |
| Llama 3 | 128k | — |

**Extending context** beyond training requires special techniques:

- **YaRN** (Yet another RoPE extensioN) — adjusts the rotary frequencies
- **Position interpolation** — scales position indices down
- **LongRoPE** — per-dimension learned scaling
- **Continued pretraining** — actually retrain on longer sequences (most expensive)

Models with native long context (Gemini 1.5, Claude 3.5) are trained on long sequences from the start; others use post-hoc extensions that may degrade slightly at extreme lengths.

---

### What this means in practice

The architecture choices are not just academic. They directly affect:

| Choice | Practical impact |
|---|---|
| **RoPE vs absolute** | Whether the model can be extended to longer contexts |
| **Pre-norm vs post-norm** | Whether you can train the model stably at large scale |
| **GQA vs MHA** | Memory cost of inference, especially for long contexts |
| **MoE vs dense** | Memory cost vs. compute cost per token |
| **SwiGLU vs GELU** | Slight quality improvement, slight compute increase |
| **Full vs sliding window** | Capability vs. cost trade-off for long contexts |

Most of these choices are "settled" — modern LLMs converge on RoPE + pre-norm + GQA + SwiGLU as the default stack, with MoE reserved for the largest models where the memory/compute trade-off makes sense.

---

## Build It / In Depth

### A "modern LLM block" in PyTorch

Combining the choices that have won out in 2024–25:

```python
import torch
import torch.nn as nn
import torch.nn.functional as F

class RMSNorm(nn.Module):
    """RMSNorm - faster and more stable than LayerNorm; used in Llama."""
    def __init__(self, dim, eps=1e-6):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim))

    def forward(self, x):
        norm = x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps)
        return norm * self.weight


class RotaryEmbedding(nn.Module):
    """Rotary positional embedding (RoPE)."""
    def __init__(self, dim, max_seq_len=2048):
        super().__init__()
        inv_freq = 1.0 / (10000 ** (torch.arange(0, dim, 2).float() / dim))
        self.register_buffer("inv_freq", inv_freq)

    def forward(self, x, seq_len):
        t = torch.arange(seq_len, device=x.device).type_as(self.inv_freq)
        freqs = torch.einsum("i,j->ij", t, self.inv_freq)
        return torch.cat((freqs, freqs), dim=-1)


class Attention(nn.Module):
    """Grouped-query attention with RoPE."""
    def __init__(self, d_model, n_heads, n_kv_heads):
        super().__init__()
        self.n_heads = n_heads
        self.n_kv_heads = n_kv_heads
        self.n_rep = n_heads // n_kv_heads
        self.d_k = d_model // n_heads

        self.W_q = nn.Linear(d_model, n_heads * self.d_k, bias=False)
        self.W_k = nn.Linear(d_model, n_kv_heads * self.d_k, bias=False)
        self.W_v = nn.Linear(d_model, n_kv_heads * self.d_k, bias=False)
        self.W_o = nn.Linear(n_heads * self.d_k, d_model, bias=False)

    def forward(self, x, mask):
        B, T, _ = x.shape
        Q = self.W_q(x).view(B, T, self.n_heads, self.d_k).transpose(1, 2)
        K = self.W_k(x).view(B, T, self.n_kv_heads, self.d_k).transpose(1, 2)
        V = self.W_v(x).view(B, T, self.n_kv_heads, self.d_k).transpose(1, 2)
        # ... apply RoPE to Q, K ...
        # ... repeat K, V for grouped-query attention ...
        out = F.scaled_dot_product_attention(Q, K, V, is_causal=True)
        return self.W_o(out.transpose(1, 2).contiguous().view(B, T, -1))


class SwiGLU(nn.Module):
    def __init__(self, d_model, d_ff):
        super().__init__()
        self.W_gate = nn.Linear(d_model, d_ff, bias=False)
        self.W_up   = nn.Linear(d_model, d_ff, bias=False)
        self.W_down = nn.Linear(d_ff, d_model, bias=False)

    def forward(self, x):
        return self.W_down(F.silu(self.W_gate(x)) * self.W_up(x))


class TransformerBlock(nn.Module):
    def __init__(self, d_model, n_heads, n_kv_heads, d_ff):
        super().__init__()
        self.attn = Attention(d_model, n_heads, n_kv_heads)
        self.ffn = SwiGLU(d_model, d_ff)
        self.norm1 = RMSNorm(d_model)
        self.norm2 = RMSNorm(d_model)

    def forward(self, x, mask):
        # Pre-norm + residual (modern LLM style)
        x = x + self.attn(self.norm1(x), mask)
        x = x + self.ffn(self.norm2(x))
        return x
```

This is roughly the structure of Llama 3, Mistral, Qwen 2.5, and most modern open-weight models. The "magic" of GPT-4 or Claude is in the training data and the RLHF, not in radically different architecture.

---

### How to read a model's architecture card

When a model release includes a "config" or technical report, the relevant fields are:

```
   {
     "hidden_size": 4096,           # residual stream width
     "num_attention_heads": 32,     # query heads
     "num_key_value_heads": 8,      # KV heads (GQA: 32/8 = 4 query heads share 1 KV)
     "num_hidden_layers": 32,       # depth
     "intermediate_size": 14336,    # FFN hidden (~3.5x hidden_size)
     "max_position_embeddings": 32768,  # training context length
     "rope_theta": 500000.0,        # RoPE base frequency
     "rms_norm_eps": 1e-5,          # normalization epsilon
     "vocab_size": 128256,          # tokenizer vocab
     "tie_word_embeddings": true    # whether embedding and output share weights
   }
```

From these numbers you can estimate compute, memory, and KV cache size for any deployment scenario.

---

## Use It

### Quick reference: how the leading models are configured

| Model | Hidden | Heads (Q/KV) | Layers | Context | FFN |
|---|---|---|---|---|---|
| Llama 3 8B | 4096 | 32/8 | 32 | 128k | 14336 |
| Llama 3 70B | 8192 | 64/8 | 80 | 128k | 28672 |
| Mistral 7B | 4096 | 32/8 | 32 | 32k+ | 14336 |
| Mixtral 8x7B | 4096 | 32/8 | 32 | 32k | 14336 (×8 experts) |
| Qwen 2.5 72B | 8192 | 64/8 | 80 | 128k | 29568 |
| DeepSeek V3 | 7168 | 128/128 | 61 | 128k | 18432 (MoE) |
| GPT-OSS 120B | — | — | 36 | — | MoE (64 experts) |
| GPT-OSS 20B | — | — | 24 | — | MoE (32 experts) |

The patterns are clear: GQA is universal, RoPE is universal, pre-norm + SwiGLU is universal, and MoE is the way to scale parameters without scaling compute.

---

### What this explains about model behavior

| Observation | Architectural reason |
|---|---|
| Models "lose" details in long contexts | Attention is O(n²) and degrades at extreme lengths |
| Long-context models are expensive | Each new context length step increases memory and compute |
| 70B models feel "smarter" than 7B | More parameters → more capacity for knowledge and reasoning |
| MoE models need lots of memory | All experts must be loaded even if only some run per token |
| Quantization works | Linear layers tolerate lower precision with small quality loss |
| Some models are faster than others at the same size | Architecture choices (GQA, MoE, FFN ratio) affect FLOPs per token |

---

## Common Pitfalls

- **Assuming "transformer" means one specific architecture.** The architecture is a family; the choices at each variation point matter.

- **Comparing models only by parameter count.** A 70B MoE model may use less compute per token than a 70B dense model. Always compare on quality-per-dollar at your workload.

- **Ignoring KV cache size.** For long-context inference, KV cache memory often dominates GPU memory. GQA models use much less.

- **Treating context length as free.** Doubling context roughly quadruples attention compute and doubles KV cache memory. Always price in the actual context you will use.

- **Conflating architecture with capability.** Architecture enables capability; training data and RLHF deliver it. A great architecture trained on poor data produces a poor model.

- **Trying novel architectures without justification.** Production LLMs converge on a few patterns because those patterns work. Novel variants (linear attention, state-space models) need to clear a high bar to displace them.

---

## Exercises

1. **Easy** — Pick two production LLMs from the table above. List three architecture choices that differ between them, and predict one observable consequence for each difference.

2. **Medium** — Implement a single modern transformer block (RoPE + pre-norm + GQA + SwiGLU) in PyTorch. Compare the parameter count to a vanilla transformer block of the same hidden size. Note where the savings or costs appear.

3. **Hard** — Read the technical report for Llama 3 or Qwen 2.5. Identify every architectural choice that differs from the original transformer. For each, explain why the authors made the choice and what evidence they cite for the improvement.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Transformer | One specific architecture | A family of architectures based on self-attention; modern LLMs are a specific subset (decoder-only, pre-norm, RoPE, GQA, SwiGLU) |
| RoPE | One positional encoding | Rotary positional embedding — encodes position by rotating Q and K vectors; the dominant choice for modern LLMs because it generalizes to longer contexts |
| GQA | Just an attention optimization | Grouped-query attention — multiple query heads share fewer key/value heads; reduces KV cache memory by 2–8× with minimal quality loss |
| MoE | A way to make models bigger | Mixture of Experts — each token is routed to a small subset of "expert" FFN blocks; total parameters grow much faster than compute per token |
| Pre-norm | A normalization placement | Applying LayerNorm/RMSNorm before the sublayer instead of after; the modern default because it is more stable to train at scale |
| SwiGLU | Just an activation function | A gated linear unit with SiLU activation that consistently improves quality over GELU/ReLU at the cost of a third projection matrix |
| KV cache | A performance trick | The cached key/value tensors from previous tokens during inference; its memory size is O(layers × heads × seq_len × head_dim) and often dominates long-context serving cost |
| RMSNorm | A replacement for LayerNorm | A simpler normalization (just root-mean-square, no mean-centering) used in Llama and most modern models; slightly faster, comparable quality |

---

## Further Reading

- **"Attention Is All You Need"** — the original transformer paper: https://arxiv.org/abs/1706.03762
- **RoFormer (RoPE)** — the rotary positional embedding paper: https://arxiv.org/abs/2104.09864
- **GQA paper** — "GQA: Training Generalized Multi-Query Transformer Models from Multi-Head Checkpoints": https://arxiv.org/abs/2305.13245
- **Llama 2 / Llama 3 technical reports** — Meta's open documentation of their architecture choices: https://ai.meta.com/llama/
- **FlashAttention paper** — the I/O-aware attention algorithm that makes long contexts feasible: https://arxiv.org/abs/2205.14135
- **The Transformer Family** — Lilian Weng's overview of transformer variants: https://lilianweng.github.io/posts/2023-01-27-the-transformer-family-v2/