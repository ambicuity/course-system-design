# How OpenAI's GPT-OSS 120B and 20B Models Work

> OpenAI's first open-weight models since GPT-2 — a Mixture-of-Experts architecture tuned for cost-efficient real-world deployment.

**Type:** Learn
**Prerequisites:** How Transformers Architecture Works?, Mixture-of-Experts concepts
**Time:** ~20 minutes

---

## The Problem

OpenAI released GPT-OSS 120B and GPT-OSS 20B as open-weight models under the Apache 2.0 license — their first open releases since GPT-2 in 2019. The models aim to deliver frontier-level performance at a fraction of the deployment cost by using a Mixture-of-Experts (MoE) architecture that activates only a small fraction of parameters per token.

For anyone building production AI, these models matter because:

1. They are the first time a frontier lab has open-sourced a model with this capability profile.
2. The Apache 2.0 license allows unrestricted commercial use.
3. The MoE architecture is the direction the field is moving for cost-efficient serving.
4. The model cards reveal concrete details about how modern MoE LLMs are designed.

This lesson walks through how GPT-OSS 120B and 20B actually work, what makes them different from typical dense LLMs, and when to consider using them in production.

---

## The Concept

### The two models at a glance

| Property | GPT-OSS 20B | GPT-OSS 120B |
|---|---|---|
| Total parameters | ~21B | ~117B |
| Active per token | ~3.6B | ~5.1B |
| Number of experts | 32 | 128 |
| Experts active per token | 4 | 4 |
| Transformer layers | 24 | 36 |
| Context length | 128k | 128k |
| License | Apache 2.0 | Apache 2.0 |

Both models are **MoE transformers** — at every layer, a router selects a small subset of expert FFN blocks to process each token. The total parameter count is large (giving the model capacity for knowledge and reasoning), but the active parameter count per token is small (giving it low latency and cost).

---

### The full inference pipeline

```
   User prompt: "Explain quantum mechanics in a simple manner"
        │
        ▼
   ┌─────────────────────────────────────────┐
   │  1. TOKENIZATION                        │
   │  Raw text → Byte-Pair Encoding (BPE)    │
   │  Handles any input: text, code, emojis  │
   └─────────────────────────────────────────┘
        │  [list of token IDs]
        ▼
   ┌─────────────────────────────────────────┐
   │  2. EMBEDDING                           │
   │  Each token → dense vector              │
   │  via learned embedding table            │
   └─────────────────────────────────────────┘
        │  shape: (sequence_length, hidden_dim)
        ▼
   ┌─────────────────────────────────────────┐
   │  3. TRANSFORMER LAYERS (24 or 36)       │
   │  ┌─────────────────────────────────┐    │
   │  │  Self-Attention                 │    │
   │  │  (which tokens relate)          │    │
   │  └─────────────────────────────────┘    │
   │  ┌─────────────────────────────────┐    │
   │  │  Router (which experts to use)  │    │
   │  │       ▼                         │    │
   │  │  Picks 4 of 32 or 4 of 128      │    │
   │  └─────────────────────────────────┘    │
   │  ┌─────────────────────────────────┐    │
   │  │  Selected Expert FFNs           │    │
   │  │  (process the token)            │    │
   │  └─────────────────────────────────┘    │
   └─────────────────────────────────────────┘
        │
        ▼
   ┌─────────────────────────────────────────┐
   │  4. PROJECTION                          │
   │  Hidden state → vocabulary scores       │
   └─────────────────────────────────────────┘
        │
        ▼
   ┌─────────────────────────────────────────┐
   │  5. SOFTMAX + SAMPLING                  │
   │  Probability distribution → next token  │
   └─────────────────────────────────────────┘
        │
        ▼
   ┌─────────────────────────────────────────┐
   │  6. POST-PROCESSING                     │
   │  SFT + RLHF make raw model helpful      │
   └─────────────────────────────────────────┘
        │
        ▼
   Response
```

Step 6 is what separates "a raw pretrained model" from "a useful assistant." Both models went through supervised fine-tuning (SFT) on instruction-following data and reinforcement learning from human feedback (RLHF) to align them with user intent.

---

### Step 1: Tokenization with BPE

The model does not see characters or words — it sees token IDs. The tokenizer is **Byte-Pair Encoding (BPE)**, the same family used by GPT-2, GPT-3, and most modern LLMs.

```
   "Quantum mechanics is fascinating."
        │
        ▼  BPE merges frequent subword pairs
        │
   ["Quant", "um", " mech", "anics", " is", " fasc", "inat", "ing", "."]
        │
        ▼  Each → ID
        │
   [23451, 286, 26162, 1580, 318, 32034, 1680, 290, 13]
```

BPE works at the byte level, so it can encode any string — including emoji, code, and non-Latin scripts — without an "unknown token" escape hatch. The vocabulary size is typically 100k–200k tokens; GPT-OSS uses 200k.

**Why subword tokens:** smaller vocabulary than character-level, smaller sequences than word-level, and the model can compose any word from subwords even if it has never seen that exact word.

---

### Step 2: Embedding

Each token ID is mapped to a dense vector via a learned embedding table.

```
   token_id: 23451 ("Quant")
        │
        ▼  lookup in matrix (vocab_size × hidden_dim)
        │
   embedding: [0.12, -0.34, 0.78, 0.56, ..., 0.91]   (length: hidden_dim)
```

For GPT-OSS 120B, hidden_dim is 2880 (estimated based on the parameter count and architecture). The embedding table is part of the trained parameters and accounts for a non-trivial fraction of memory (~200k × 2880 = ~580M parameters just for the table).

---

### Step 3: Transformer layers — the MoE twist

This is where GPT-OSS diverges from a vanilla transformer. Each layer has:

```
   ┌─────────────────────────────────────────────┐
   │  Self-Attention block                       │
   │  (same as any transformer)                  │
   └─────────────────────┬───────────────────────┘
                         │
                         ▼
   ┌─────────────────────────────────────────────┐
   │  Router: small linear layer that scores    │
   │  each expert for the current token         │
   │  → picks top-K experts (K=4)               │
   └─────────────────────┬───────────────────────┘
                         │
                         ▼
   ┌─────────────────────────────────────────────┐
   │  Selected K experts' FFNs run in parallel   │
   │  (each is a SwiGLU FFN)                    │
   │  Their outputs are combined (weighted sum) │
   └─────────────────────────────────────────────┘
```

**What the router does:**

The router is a learned linear layer that maps each token's hidden state to a score for each expert. It selects the top-K experts (K=4 for GPT-OSS) per token. Each expert is a standard SwiGLU FFN.

```
   hidden_state (2880-dim)
        │
        ▼  router: Linear(2880 → 32)  [for the 20B model]
        │
   scores: [0.3, -1.2, 4.5, ..., 2.1]   (one per expert)
        │
        ▼  top-K selection (K=4)
        │
   active experts: #2, #7, #14, #29
        │
        ▼  run those 4 FFNs, weight by softmax scores
        │
   combined output
```

**Why MoE:** total parameters are huge (giving the model capacity for many specialized "skills"), but compute per token is small (only K experts run per token). The 120B model has ~117B total parameters but uses only ~5.1B per token — making it roughly 20× cheaper to serve than a 117B dense model at the same quality.

**The training challenge:** without auxiliary losses, the router tends to send most tokens to a few "favorite" experts, wasting the rest. GPT-OSS uses load-balancing losses that encourage even expert utilization, similar to Mixtral and DeepSeek.

---

### Step 4: Output projection

After all 24 (20B) or 36 (120B) layers, the final hidden state is projected to vocabulary size:

```
   final_hidden_state (2880-dim)
        │
        ▼  Linear(2880 → 200,000)  [vocab size]
        │
   scores: one per token in vocabulary
        │
        ▼  softmax
        │
   probabilities
```

---

### Step 5: Sampling

The probability distribution is converted into a single token via sampling. Different sampling strategies:

- **Greedy** — pick the highest-probability token. Deterministic, often repetitive.
- **Temperature** — scale the logits before softmax. Low = more focused; high = more random.
- **Top-p (nucleus)** — sample from the smallest set of tokens whose cumulative probability exceeds p. Most common in production.
- **Top-k** — sample from the top k tokens. Simpler than top-p, comparable results.

GPT-OSS supports the standard sampling controls via the API.

---

### Step 6: Post-training (SFT + RLHF)

The base pretrained model is a "completion engine" — given a prompt, it continues the text. To make it a useful assistant, OpenAI applied:

1. **Supervised fine-tuning (SFT)** on curated (prompt, ideal_response) pairs — typically tens of thousands of examples written by humans or generated by stronger models.
2. **Reinforcement learning from human feedback (RLHF)** — human raters compare two model outputs and the model is trained to prefer the better one.
3. **Constitutional AI or RLAIF** — let the model itself generate critiques, reducing the human-rater bottleneck.
4. **Safety fine-tuning** — additional training to refuse harmful requests, avoid producing dangerous content, etc.

The result is a model that follows instructions, refuses harmful requests, and produces output in the style users expect.

---

### Why MoE matters for production

The MoE design has direct production consequences:

| Aspect | Dense model | MoE model |
|---|---|---|
| Total parameters | N | N (same) |
| Active per token | N | N / (num_experts / top_K) |
| Memory at rest | N × bytes | N × bytes (all experts loaded) |
| Compute per token | N × FLOPs | (N / E) × K × FLOPs |
| Latency | Higher | Lower (less compute) |
| Throughput | Lower | Higher |
| Cost per token | Higher | Lower |

**Memory is the catch:** you must load all experts into GPU memory, even if only some run per token. GPT-OSS 120B needs ~234 GB at fp16. That fits on two H100 GPUs (80 GB each) or one H200 (141 GB). GPT-OSS 20B needs ~40 GB — one A100 or one RTX 4090 with quantization.

**Serving MoE is harder than dense models:** the routing logic adds latency variance (different tokens take different paths), and GPU utilization is harder to optimize. Frameworks like vLLM, SGLang, and TensorRT-LLM have specific MoE support.

---

## Build It / In Depth

### A minimal MoE layer in PyTorch

```python
import torch
import torch.nn as nn
import torch.nn.functional as F

class Expert(nn.Module):
    """A single expert: a SwiGLU FFN."""
    def __init__(self, d_model, d_ff):
        super().__init__()
        self.W_gate = nn.Linear(d_model, d_ff, bias=False)
        self.W_up   = nn.Linear(d_model, d_ff, bias=False)
        self.W_down = nn.Linear(d_ff, d_model, bias=False)

    def forward(self, x):
        return self.W_down(F.silu(self.W_gate(x)) * self.W_up(x))


class MoELayer(nn.Module):
    """Mixture-of-Experts layer with top-K routing."""
    def __init__(self, d_model, d_ff, n_experts=32, top_k=4):
        super().__init__()
        self.n_experts = n_experts
        self.top_k = top_k
        self.router = nn.Linear(d_model, n_experts, bias=False)
        self.experts = nn.ModuleList([Expert(d_model, d_ff) for _ in range(n_experts)])

    def forward(self, x):
        B, T, D = x.shape
        x_flat = x.view(-1, D)              # (B*T, D)
        n_tokens = x_flat.shape[0]

        # Route each token to top-K experts
        router_logits = self.router(x_flat)              # (B*T, n_experts)
        routing_weights = F.softmax(router_logits, dim=-1)
        top_k_weights, top_k_indices = routing_weights.topk(self.top_k, dim=-1)

        # Normalize the top-K weights so they sum to 1
        top_k_weights = top_k_weights / top_k_weights.sum(dim=-1, keepdim=True)

        # Compute the output for each token by combining its top-K experts
        output = torch.zeros_like(x_flat)
        for k in range(self.top_k):
            expert_idx = top_k_indices[:, k]                    # which expert for each token
            expert_weight = top_k_weights[:, k].unsqueeze(-1)  # weight for that expert

            # Apply the selected expert to each token
            for e in range(self.n_experts):
                mask = (expert_idx == e)
                if mask.any():
                    expert_input = x_flat[mask]
                    expert_output = self.experts[e](expert_input)
                    output[mask] += expert_weight[mask] * expert_output

        return output.view(B, T, D)
```

This is a simplified, inefficient version of MoE. Production implementations (in vLLM, Megatron, etc.) use expert-parallelism, fused kernels, and load-balancing tricks to make MoE fast and stable.

---

### The auxiliary load-balancing loss

Without intervention, the router learns to send most tokens to one or two "favorite" experts. The other experts atrophy and the model's effective capacity collapses. The fix is an auxiliary loss that penalizes imbalanced routing:

```python
def load_balancing_loss(router_logits, n_experts, top_k):
    """Encourage even expert utilization."""
    routing_weights = F.softmax(router_logits, dim=-1)
    # fraction of tokens routed to each expert
    _, selected_experts = routing_weights.topk(top_k, dim=-1)
    expert_mask = F.one_hot(selected_experts, num_classes=n_experts).float()
    expert_mask = expert_mask.sum(dim=1)  # tokens per expert

    tokens_per_expert = expert_mask.mean(dim=0)
    router_prob_per_expert = routing_weights.mean(dim=0)

    # Loss = sum(N_experts × fraction_tokens × fraction_routing_prob)
    loss = n_experts * (tokens_per_expert * router_prob_per_expert).sum()
    return loss
```

This loss is added to the main training loss with a small coefficient. It pushes the router to spread tokens more evenly across all experts.

---

## Use It

### When to use GPT-OSS 20B vs 120B vs closed alternatives

| Situation | Best choice |
|---|---|
| Need the highest quality, cost is no object | GPT-4o, Claude Opus, Gemini Ultra |
| Need strong quality at moderate cost | GPT-OSS 120B, Claude Sonnet, Llama 3.3 70B |
| Need good quality on a single GPU | GPT-OSS 20B (with quantization), Llama 3.1 8B |
| Need on-prem / air-gapped deployment | GPT-OSS 20B / 120B (Apache 2.0, no API calls) |
| Need absolute lowest latency | Smaller dense models (Llama 3.2 1B, Phi-4) |
| Need a fine-tuned domain model | GPT-OSS (open weights allow fine-tuning) |

### The Apache 2.0 advantage

GPT-OSS is licensed under **Apache 2.0**, which means:

- ✅ Commercial use without restriction
- ✅ Modification and derivative works
- ✅ Redistribution
- ✅ Patent grant
- ❌ No trademark grant (cannot use "GPT-OSS" branding)
- ❌ No warranty

Compare to Llama's community license (commercial use allowed with restrictions for very large users) or Mistral's research-only licenses for some models. Apache 2.0 is the most permissive and is the standard for true open-source distribution.

---

### How to deploy GPT-OSS

```bash
# Option 1: Ollama (simplest, local dev)
ollama run gpt-oss:20b
ollama run gpt-oss:120b

# Option 2: vLLM (production-grade serving)
vllm serve gpt-oss-120b --tensor-parallel-size 2

# Option 3: Hugging Face Transformers (Python)
from transformers import pipeline
pipe = pipeline("text-generation", model="openai/gpt-oss-120b")
```

For production deployments, vLLM is the recommended path — it supports MoE routing efficiently, has continuous batching, and exposes an OpenAI-compatible API.

---

## Common Pitfalls

- **Confusing total and active parameters.** GPT-OSS 120B has 117B total parameters but uses ~5B per token. Memory is determined by total parameters; latency and cost are determined by active parameters.

- **Underestimating serving memory.** The MoE model's memory footprint is set by *all* experts being loaded. 120B at fp16 = ~234 GB. Plan your GPU budget accordingly.

- **Treating MoE like dense for capacity planning.** MoE models have higher throughput per GPU but require more sophisticated batching to keep all experts busy. Naive batching leaves experts idle.

- **Ignoring the license comparison.** Apache 2.0 is permissive, but other open-weight models have usage restrictions. Always check before shipping.

- **Assuming "open" means "no API cost."** Self-hosting GPT-OSS 120B on two H100s costs roughly $4–8/hour depending on provider. At low traffic, the closed API may still be cheaper.

- **Skipping evaluation on your workload.** The published benchmarks are averages over standard tasks. Always evaluate on your own data before committing.

---

## Exercises

1. **Easy** — In one sentence each, describe total parameters, active parameters, and how the router decides which experts to use in GPT-OSS 120B.

2. **Medium** — Estimate the GPU memory needed to serve GPT-OSS 120B and GPT-OSS 20B at fp16, fp8, and int4 quantization. Match each to a concrete GPU (A100, H100, H200, RTX 4090) and explain the trade-off.

3. **Hard** — Design a production deployment for a customer support agent using GPT-OSS 120B. Specify: GPU choice, serving framework, batching strategy, latency and throughput targets, cost per 1,000 conversations, and observability tooling. Justify each choice.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| GPT-OSS | A new model | OpenAI's first open-weight models since GPT-2, released under Apache 2.0; 20B and 120B variants, both MoE transformers |
| Mixture of Experts (MoE) | A way to make models bigger | A transformer where each layer has many "expert" FFN blocks; a router selects the top-K per token, so total parameters are large but active parameters are small |
| Router | Part of the model | A small learned linear layer that scores each expert for the current token and selects the top-K; trained jointly with the rest of the model |
| Load-balancing loss | A training trick | An auxiliary loss added during training that encourages even expert utilization; without it, the router collapses to using only a few experts |
| Active parameters | Total parameters | The number of parameters that actually fire for a single token — the relevant number for compute and latency, while total parameters determine memory |
| BPE | The tokenizer | Byte-Pair Encoding — a subword tokenization scheme that operates at the byte level, so it can encode any string without an "unknown token" |
| RLHF | The fine-tuning | Reinforcement Learning from Human Feedback — a post-training step where human raters compare model outputs and the model is trained to prefer better ones |
| Apache 2.0 | An open-source license | The most permissive standard open-source license; allows unrestricted commercial use, modification, and redistribution |

---

## Further Reading

- **OpenAI GPT-OSS Model Card** — the official documentation of the models: https://openai.com/index/introducing-gpt-oss/
- **"Mixtral of Experts"** — the Mistral paper that established the modern MoE pattern GPT-OSS follows: https://arxiv.org/abs/2401.04088
- **"DeepSeekMoE"** — DeepSeek's MoE paper with finer-grained expert routing: https://arxiv.org/abs/2401.06066
- **vLLM MoE Documentation** — production serving of MoE models: https://docs.vllm.ai/en/latest/models/supported_models.html
- **"A Survey on Mixture of Experts"** — comprehensive academic survey of MoE architectures: https://arxiv.org/abs/2407.06204