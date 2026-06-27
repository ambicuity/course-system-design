# DeepSeek 1-Pager

> Train a reasoning frontier model for a fraction of the cost by rethinking what parameters actually need to fire.

**Type:** Learn
**Prerequisites:** Large Language Model Basics, Transformer Architecture, Reinforcement Learning from Human Feedback (RLHF)
**Time:** ~25 minutes

---

## The Problem

Training a frontier-class large language model has historically been an exercise in raw compute. OpenAI's GPT-4 reportedly used approximately 25,000 NVIDIA A100 GPUs over 90–100 days. The capital expenditure alone puts frontier model development out of reach for most organizations — and even for well-funded labs, it creates a tightrope between iteration speed and cost. Every experiment costs millions of dollars, so teams must bet big and iterate slowly.

Beyond the cost problem, there is a qualitative ceiling. Supervised fine-tuning (SFT) — the dominant post-pretraining technique — teaches a model to imitate human annotations. The model learns to produce outputs that look like what a human labeled "correct", but it never develops a robust internal reasoning process. It is pattern-matching expert annotators, not thinking. This produces models that are fluent but brittle: they fail on novel reasoning chains, especially in mathematics, formal logic, and multi-step coding problems, because no annotated example covered exactly that reasoning path.

DeepSeek R1, released in January 2025, attacked both problems simultaneously. By combining a Mixture-of-Experts (MoE) architecture with a reinforcement learning training algorithm called Group Relative Policy Optimization (GRPO), DeepSeek's team trained a 671-billion-parameter model that activates only 37 billion parameters per forward pass — using 2,000 NVIDIA GPUs and spending approximately $6 million on the final training run. The resulting model matches or outperforms GPT-4 on mathematical reasoning, competitive programming, and multi-step logic benchmarks, and was released open-source under the MIT license. This lesson is a technical 1-pager on how that happened and what it means for system design.

---

## The Concept

### Architecture: Mixture of Experts (MoE)

A standard "dense" transformer activates every parameter on every token. A 671B dense model fires all 671B weights for every word it processes. That is thermodynamically expensive and computationally redundant — not all knowledge is relevant to every token.

MoE replaces the standard feed-forward layers with a set of parallel "expert" sub-networks and a learned router. For each token, the router selects a small subset of experts to activate. All other experts sit idle for that token.

```
                    INPUT TOKEN
                        |
                   [Router Layer]
                  /    |    |    \
           Exp-1  Exp-2  Exp-3  ... Exp-N     ← 671B params spread across N experts
             ↓              ↓
         (active)        (active)              ← only k experts fire per token
           \               /
            [Weighted Sum]
                  |
               OUTPUT
```

DeepSeek R1 has 671 billion **total** parameters across all experts, but only **37 billion** activate per token. The savings:

| Metric | Dense 671B | MoE 671B / 37B active |
|---|---|---|
| Params per forward pass | 671B | 37B |
| Memory for inference | ~1.3 TB FP16 | ~74 GB FP16 (active only) |
| Relative compute per token | 18× higher | 1× baseline |
| Training GPU-hours (relative) | Very high | Significantly reduced |

The router itself is a lightweight learned linear layer with a softmax. It outputs a probability distribution over experts, and the top-k experts (typically k=2 or k=4 in MoE designs) are selected. The outputs of the selected experts are combined by their router weights.

An important design challenge with MoE is **load balancing**: if the router always sends tokens to the same two experts, those experts overfit while the rest are wasted capacity. DeepSeek addresses this with an auxiliary load-balancing loss term during training that penalizes expert utilization skew.

### Training: Group Relative Policy Optimization (GRPO)

Standard RLHF uses a reward model trained on human preference data, then runs Proximal Policy Optimization (PPO) to push the language model toward higher-reward outputs. This works but has a key cost: PPO requires maintaining a separate **critic network** (the value function baseline) that is roughly the same size as the model being trained. For a model of this scale, that doubles memory and compute requirements.

GRPO eliminates the critic. Instead of learning a value function, it estimates the baseline by comparing multiple sampled outputs **within the same group** for the same input prompt.

```
Prompt: "Solve: ∫x·sin(x)dx"

Sample group (8 outputs):
  Output 1: "-x·cos(x) + sin(x) + C"   → CORRECT  → reward = +1.0
  Output 2: "-x·cos(x) - sin(x) + C"   → WRONG    → reward = -1.0
  Output 3: "x·cos(x) + sin(x) + C"    → WRONG    → reward = -1.0
  Output 4: "-x·cos(x) + sin(x) + C"   → CORRECT  → reward = +1.0
  ...

GRPO baseline = mean(rewards within group) = 0.0 (in this example)
Advantage for output 1 = reward(1) - baseline = +1.0 - 0.0 = +1.0
Advantage for output 2 = reward(2) - baseline = -1.0 - 0.0 = -1.0

Policy gradient update: reinforce outputs with positive advantage,
suppress outputs with negative advantage.
```

This is computationally elegant: the reward signal is entirely **rule-based** for well-defined domains (math, code). A correct math answer can be verified against a known solution without a human annotator or a learned reward model. GRPO therefore requires:

1. A group of sampled completions from the current policy
2. A verifiable reward function (symbolic math checker, code execution sandbox)
3. Group-relative advantage estimation (no separate critic needed)
4. A PPO-style clipped policy gradient update

The training pipeline for DeepSeek R1 also included an initial **cold-start SFT phase** with a small set of long chain-of-thought examples, followed by GRPO reinforcement learning, followed by a final SFT fine-tuning pass on the best RL-generated outputs. This staged approach bootstrapped the model's ability to produce readable reasoning chains before the RL phase shaped them for correctness.

### Why This Matters Architecturally

MoE + GRPO creates a compounding efficiency advantage:
- **MoE** reduces the active compute per token at inference and training time
- **GRPO** removes the critic model, cutting training memory roughly in half compared to PPO
- **Rule-based rewards** remove the cost of training and maintaining a reward model
- **Open weights (MIT)** allow inference on commodity hardware via quantization

The net result is a model that achieves frontier reasoning capability at roughly 1/12th the training GPU count reported for GPT-4.

---

## Build It / In Depth

### Tracing a Single Inference Pass Through DeepSeek R1

Let's walk through what happens when a user submits a hard coding problem.

**Step 1 — Tokenization**

```
Input: "Write a Python function that finds the kth smallest element in a BST."
Tokens: ["Write", " a", " Python", " function", " that", " finds", " the", " kth", ...]
```

**Step 2 — MoE Routing Decision (per transformer layer)**

For each token at each MoE layer, the router fires:

```python
# Pseudocode — actual implementation uses optimized CUDA kernels
router_logits = token_hidden_state @ router_weight_matrix  # shape: [n_experts]
router_probs  = softmax(router_logits)
top_k_indices = argtopk(router_probs, k=2)                 # select 2 experts
top_k_weights = router_probs[top_k_indices]                 # normalized weights
top_k_weights = top_k_weights / top_k_weights.sum()        # re-normalize

expert_outputs = [experts[i](token_hidden_state) for i in top_k_indices]
combined = sum(w * out for w, out in zip(top_k_weights, expert_outputs))
```

This happens at every MoE layer, every token, every forward pass. The router learns which experts specialize in which linguistic or semantic patterns.

**Step 3 — Reasoning Token Generation (chain of thought)**

DeepSeek R1 generates an internal reasoning trace before the final answer:

```
<think>
The problem asks for kth smallest in a BST. The kth smallest
element in a BST can be found using in-order traversal since
in-order traversal of a BST visits nodes in sorted order.
I need to count nodes during traversal and return when I reach
the kth node.

Edge cases: k=1 (smallest), k=n (largest), empty tree.

Algorithm:
  - In-order traversal (left, root, right)
  - Maintain a counter
  - When counter == k, return current node value
</think>

def kth_smallest(root, k):
    stack = []
    count = 0
    current = root
    while stack or current:
        while current:
            stack.append(current)
            current = current.left
        current = stack.pop()
        count += 1
        if count == k:
            return current.val
        current = current.right
    return -1
```

The `<think>` block is where the RL training has the most visible effect. The model learned that verbosely working through the problem before committing to code significantly improves correctness on hard problems.

**Step 4 — Reward Signal (during GRPO training)**

During training, for coding tasks, the code block is extracted and executed in a sandboxed Python environment against test cases:

```python
# Reward function for code generation
def compute_reward(generated_code: str, test_cases: list[dict]) -> float:
    passed = 0
    for tc in test_cases:
        try:
            result = execute_in_sandbox(generated_code, tc["input"], timeout=5)
            if result == tc["expected_output"]:
                passed += 1
        except Exception:
            pass
    return passed / len(test_cases)  # 0.0 to 1.0
```

For math, a symbolic math checker (e.g., SymPy-based equivalence check) serves the same role. Neither requires human annotation at scale.

### Quantized Local Deployment

Because the weights are MIT-licensed, you can run DeepSeek R1 locally via:

```bash
# Using Ollama (handles quantization and serving)
ollama pull deepseek-r1:7b      # 7B distilled version, ~4 GB
ollama pull deepseek-r1:70b     # 70B distilled version, ~40 GB
ollama run deepseek-r1:7b

# Or via llama.cpp for raw GGUF inference
./llama-cli -m deepseek-r1-7b-q4_k_m.gguf \
  --ctx-size 8192 \
  --threads 8 \
  --prompt "<｜User｜>Explain MoE architecture<｜Assistant｜>"
```

For the full 671B model, you need multi-GPU or distributed inference (vLLM supports tensor parallelism):

```bash
python -m vllm.entrypoints.openai.api_server \
  --model deepseek-ai/DeepSeek-R1 \
  --tensor-parallel-size 8 \          # spread across 8 GPUs
  --max-model-len 32768 \
  --trust-remote-code
```

---

## Use It

### When to Reach for DeepSeek R1 vs Alternatives

| Use Case | DeepSeek R1 | GPT-4o | Claude 3.5 Sonnet | Llama 3.3 70B |
|---|---|---|---|---|
| Hard math / competition problems | Best-in-class | Strong | Strong | Decent |
| Competitive programming | Best-in-class | Strong | Strong | Decent |
| Multi-step logical reasoning | Best-in-class | Strong | Strong | Decent |
| Open weights / on-prem | Yes (MIT) | No | No | Yes (custom license) |
| Cost per million tokens (API) | ~$0.14 input | ~$2.50 input | ~$3.00 input | ~$0.36 input |
| Context window | 128K | 128K | 200K | 128K |
| Multilingual (52 languages) | Yes | Yes | Yes | Yes |
| Creative writing / instruction | Good | Excellent | Excellent | Good |

**Reach for DeepSeek R1 when:**
- The task involves verifiable correctness (math, code, formal logic)
- You need open weights for compliance, latency, or cost reasons
- You are building an agent loop that self-verifies outputs
- You want to fine-tune on your own reasoning datasets

**Reach for GPT-4o / Claude when:**
- The task is instruction-following, creative, or heavily multimodal
- You need strong tool use and function-calling reliability
- Human preference alignment (politeness, safety) is the top priority

### Distilled Variants for Practical Deployment

DeepSeek released smaller "distilled" models trained to mimic R1's reasoning traces:

```
DeepSeek-R1-Distill-Qwen-1.5B   → edge / mobile inference
DeepSeek-R1-Distill-Qwen-7B     → single GPU, 4–8 GB VRAM
DeepSeek-R1-Distill-Llama-8B    → single GPU, compatible with Llama tooling
DeepSeek-R1-Distill-Qwen-14B    → prosumer GPU (16 GB VRAM)
DeepSeek-R1-Distill-Qwen-32B    → workstation / small cluster
DeepSeek-R1-Distill-Llama-70B   → data center, best distilled quality
```

These distilled models achieve competitive reasoning quality by training on synthetic chain-of-thought data generated by the full R1 model — a form of knowledge distillation through behavior cloning.

---

## Common Pitfalls

- **Treating the `<think>` block as usable output.** The reasoning trace is verbose and unpolished by design. Parse only the content after `</think>` for the final answer in production pipelines. Sending the entire raw output to users looks broken.

- **Ignoring load balancing when deploying MoE models.** With tensor parallelism, expert routing can cause GPU communication imbalances. If all tokens in a batch route to the same experts on the same GPU, other GPUs sit idle. Use vLLM or TGI's MoE-aware batching rather than naive parallelism.

- **Assuming open weights means free inference at full size.** The full 671B model requires approximately 8 × 80 GB H100 GPUs at FP8 precision. Budget accordingly or use a distilled variant. "Open source" does not mean "runs on a laptop."

- **Misinterpreting the $6M training cost.** That figure covers the *final* training run only. Total R&D costs including failed experiments, data curation, infrastructure, and engineering salaries are substantially higher. Do not plan a competing model budget around $6M.

- **Using DeepSeek R1 for tasks where reasoning traces hurt latency.** The model generates long internal monologues before answering. For low-latency applications (sub-100ms response), use a dense distilled variant with `max_new_tokens` constraints, or route to a smaller fast model and only escalate to R1 for hard cases.

---

## Exercises

1. **Easy** — Take any calculus integration problem (e.g., ∫x²·eˣdx) and trace through how GRPO would compute the group-relative advantage for a batch of 4 sampled outputs where 2 are correct and 2 are wrong. Write out the reward values, the baseline, and the advantage for each output.

2. **Medium** — Design a simple MoE feed-forward layer for a toy transformer with 4 experts and k=1 routing. Implement the router, expert selection, and weighted output combination in Python using only NumPy. Test it with a random hidden state vector and verify that only 1 expert fires.

3. **Hard** — Design an agentic coding assistant system that uses a small fast model (e.g., DeepSeek-R1-Distill-7B) as a first-pass code generator and the full DeepSeek-R1 as a reviewer/debugger. Define the routing logic: when does the agent escalate from the 7B to the 671B? What reward signal or heuristic decides escalation? Draw the system architecture and estimate the cost per 1,000 user queries under different escalation rates.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Mixture of Experts (MoE) | A fancy ensemble of different specialized models | A single model with parallel feed-forward sub-networks; a learned router selects a subset (top-k) to activate per token, keeping total compute low while total capacity high |
| GRPO | Just another name for PPO | A PPO variant that removes the critic network by using within-group reward averaging as a baseline, cutting memory and removing the need for a separate value model |
| Active Parameters | The total parameter count (671B) | The parameters that actually compute during a single forward pass — for MoE models this is the routed subset (37B), which determines inference cost |
| Chain-of-Thought (CoT) | A prompting trick you add at inference time | Here, an emergent training artifact: GRPO reinforcement learning caused the model to spontaneously develop verbose internal reasoning traces that improve final answer accuracy |
| Open Source (MIT) | Free to use in any context | The model weights are publicly released under MIT, meaning you can run, modify, and commercialize without restriction — but the training data and exact training code are not fully public |
| Distillation | Always requires the teacher model at inference time | A one-time training process: a smaller student model is trained on outputs from a larger teacher; only the student is needed at inference time |
| Load Balancing Loss | A minor regularization trick | A critical auxiliary training objective in MoE models that prevents expert collapse — without it, the router ignores most experts and the model degrades to a dense sub-network |

---

## Further Reading

- **DeepSeek-R1 Technical Report** — The primary source. Covers the GRPO formulation, MoE architecture details, training stages, and benchmark results in full.
  https://arxiv.org/abs/2501.12948

- **Mixture of Experts (Mistral / Switch Transformer papers)** — Google's Switch Transformer paper is the clearest academic treatment of sparse MoE scaling laws and load balancing.
  https://arxiv.org/abs/2101.03961

- **Group Relative Policy Optimization (GRPO original paper)** — DeepSeek's earlier math-focused paper (DeepSeekMath) where GRPO was first introduced; explains the derivation from PPO.
  https://arxiv.org/abs/2402.03300

- **vLLM Documentation — MoE Inference** — Practical guide to deploying MoE models with tensor parallelism, expert parallelism, and quantization in production.
  https://docs.vllm.ai/en/latest/models/supported_models.html

- **DeepSeek GitHub (open weights and inference code)**
  https://github.com/deepseek-ai/DeepSeek-R1
