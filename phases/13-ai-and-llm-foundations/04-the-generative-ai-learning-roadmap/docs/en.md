# The Generative AI Learning Roadmap

> Master the full stack — from probability theory to production agents — in the right order.

**Type:** Learn
**Prerequisites:** Introduction to Large Language Models, How LLMs Work Under the Hood
**Time:** ~25 minutes

## The Problem

The Generative AI ecosystem exploded in eighteen months. Every week a new model, framework, or prompt technique appears. Engineers who try to learn it opportunistically — grabbing YouTube videos and copy-pasting LangChain examples — end up with brittle mental models: they can call an API but cannot explain why a temperature of 0.0 reduces variance, cannot debug a retrieval failure, and cannot decide when fine-tuning is cheaper than prompt engineering.

Consider a concrete failure: a team ships a customer-support chatbot built on GPT-4o. It works in demos. In production it hallucinates policy dates, ignores retrieved documents, and sometimes answers in the wrong language. The team patches symptoms for three months before realizing the root cause is that nobody on the team understood embeddings, retrieval ranking, or context-window management — three foundational concepts skipped in the rush to ship.

The antidote is not more tutorials. It is a structured roadmap that sequences concepts so each layer supports the next. This lesson gives you that map: what to learn, in what order, why each block matters, and where to go deep.

## The Concept

Generative AI is a class of model that learns a probability distribution over training data and then samples from it to produce new outputs — text, images, code, audio, or video. Every system you will ever build sits somewhere on this stack:

```
┌──────────────────────────────────────────────────────┐
│  Layer 7: Applications & Agents                       │
│  (chatbots, copilots, autonomous pipelines)           │
├──────────────────────────────────────────────────────┤
│  Layer 6: Orchestration Frameworks                    │
│  (LangChain, LlamaIndex, DSPy, CrewAI)               │
├──────────────────────────────────────────────────────┤
│  Layer 5: Retrieval & Memory                          │
│  (VectorDBs, embedding models, rerankers)             │
├──────────────────────────────────────────────────────┤
│  Layer 4: Prompt Engineering & Context Management     │
│  (chain-of-thought, few-shot, RAG, tool use)          │
├──────────────────────────────────────────────────────┤
│  Layer 3: Foundation Models & APIs                    │
│  (GPT-4o, Claude 3.5, Gemini, Llama 3, DeepSeek)    │
├──────────────────────────────────────────────────────┤
│  Layer 2: Model Architecture & Training               │
│  (Transformers, RLHF, LoRA, SFT, DPO)                │
├──────────────────────────────────────────────────────┤
│  Layer 1: Math Foundations                            │
│  (Probability, Linear Algebra, Calculus, Statistics)  │
└──────────────────────────────────────────────────────┘
```

You build knowledge bottom-up. You build systems top-down. Both directions exist simultaneously in a good engineer's mental model.

### The Seven Learning Blocks

| Block | Core Topics | Why It Matters |
|-------|-------------|----------------|
| **1. Math Foundations** | Probability distributions, Bayes' theorem, matrix multiplication, gradient descent, cross-entropy loss | Every LLM training objective, every embedding, every sampling strategy is math. Gaps here cause cargo-culting. |
| **2. Foundation Models** | GPT-4o, Claude 3.5 Sonnet, Gemini 1.5, Llama 3.1, DeepSeek-V2, Mistral | Knowing the trade-offs (context length, cost, latency, open vs. closed) determines architecture decisions. |
| **3. Dev Stack** | Python, OpenAI / Anthropic SDK, Hugging Face `transformers`, tokenizers | The toolchain for every experiment and production service. |
| **4. Prompt Engineering** | Zero-shot, few-shot, chain-of-thought, ReAct, structured outputs, system prompts | For 80% of tasks, better prompting outperforms fine-tuning at 1/100th the cost. |
| **5. Retrieval & VectorDB** | Embeddings, cosine similarity, FAISS, Pinecone, pgvector, rerankers | Grounds LLMs in facts and private data without baking knowledge into weights. |
| **6. Fine-tuning & Adaptation** | Supervised fine-tuning (SFT), LoRA / QLoRA, RLHF, DPO, PEFT | When prompting hits a ceiling — domain-specific tasks, style, safety — you reach for this. |
| **7. Agents & Multimodal** | Tool use, planning loops, computer vision (GANs, DALL-E, Flux), multi-agent systems | The frontier: models that act, not just respond. |

### Why the Order Matters

Skipping Layer 1 means you cannot debug a loss spike or explain why your fine-tune overfit. Skipping Layer 4 means you buy expensive fine-tunes for problems solvable with a good system prompt. Skipping Layer 5 means hallucinations from stale weights. Each layer is load-bearing.

## Build It / In Depth

Walk through a concrete learning sequence for an engineer who wants to go from zero to production-capable in twelve weeks.

### Weeks 1-2: Math Bootcamp (Block 1)

You do not need a PhD. You need working intuition for five concepts:

```
Concept             What you need to understand
──────────────────────────────────────────────────
Probability         P(next token | context) is the fundamental LLM objective
Linear Algebra      Embeddings are vectors; attention is dot products + softmax
Calculus            Backprop is the chain rule; gradient descent minimizes loss
Statistics          Mean, variance, entropy — used in sampling & evaluation
Information Theory  Cross-entropy loss = how surprised the model is by the label
```

Study resource: 3Blue1Brown's "Essence of Linear Algebra" + fast.ai's "Practical Deep Learning."

### Weeks 3-4: Foundation Models (Block 2)

Run the same prompt across five models and compare outputs systematically:

```python
import anthropic, openai

def compare_models(prompt: str) -> dict:
    # Claude
    client_anthropic = anthropic.Anthropic()
    claude_response = client_anthropic.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}]
    )

    # GPT-4o
    client_openai = openai.OpenAI()
    gpt_response = client_openai.chat.completions.create(
        model="gpt-4o",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}]
    )

    return {
        "claude": claude_response.content[0].text,
        "gpt4o": gpt_response.choices[0].message.content,
    }

result = compare_models("Explain transformer attention in one paragraph.")
```

Log cost, latency, and quality. Build intuition for the cost-quality frontier.

### Weeks 5-6: Prompt Engineering (Block 4)

Practice the escalation ladder. For any task, try techniques from cheapest to most expensive:

```
1. Zero-shot          →  "Classify this review as positive or negative."
2. Few-shot           →  Provide 3 labeled examples in the prompt.
3. Chain-of-thought   →  "Think step by step before answering."
4. System prompt      →  Give role, tone, constraints, output format.
5. Structured output  →  Ask for JSON with a schema; use response_format.
6. Tool use           →  Give the model a calculator or search function.
7. RAG                →  Inject retrieved documents into context.
8. Fine-tune          →  Only if all above fail at acceptable quality.
```

### Weeks 7-8: Retrieval & VectorDB (Block 5)

Build a minimal RAG pipeline from scratch:

```python
from openai import OpenAI
import numpy as np

client = OpenAI()

def embed(texts: list[str]) -> np.ndarray:
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts
    )
    return np.array([r.embedding for r in response.data])

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

# Index
docs = ["Policy: refunds within 30 days.", "Support hours: 9am-5pm EST."]
doc_embeddings = embed(docs)

# Query
query = "Can I return a product after 3 weeks?"
query_embedding = embed([query])[0]

# Rank
scores = [cosine_similarity(query_embedding, d) for d in doc_embeddings]
best_doc = docs[np.argmax(scores)]

# Generate with grounding
answer = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": f"Answer using only this context:\n{best_doc}"},
        {"role": "user", "content": query}
    ]
)
print(answer.choices[0].message.content)
```

### Weeks 9-10: Fine-tuning (Block 6)

Use LoRA for parameter-efficient fine-tuning on a local model:

```bash
# Install dependencies
pip install transformers peft datasets accelerate bitsandbytes

# Fine-tune Llama 3.1 8B with QLoRA (4-bit quantization + LoRA adapters)
# Requires a GPU with 16 GB+ VRAM or use a cloud instance
python -c "
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from peft import LoraConfig, get_peft_model
from datasets import load_dataset

model_id = 'meta-llama/Meta-Llama-3.1-8B'
lora_config = LoraConfig(r=16, lora_alpha=32, target_modules=['q_proj','v_proj'])
# ... see Hugging Face TRL SFTTrainer for full recipe
"
```

Decision rule: fine-tune only when (a) you have 500+ labeled examples, (b) the task is consistent and well-defined, and (c) prompt engineering with RAG still misses your quality target.

### Weeks 11-12: Agents (Block 7)

Implement a minimal ReAct agent (Reason + Act loop):

```python
import json
from openai import OpenAI

client = OpenAI()
tools = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"]
            }
        }
    }
]

def run_agent(user_message: str) -> str:
    messages = [{"role": "user", "content": user_message}]
    while True:
        response = client.chat.completions.create(
            model="gpt-4o", messages=messages, tools=tools
        )
        choice = response.choices[0]
        if choice.finish_reason == "stop":
            return choice.message.content
        # Handle tool call, append result, loop
        tool_call = choice.message.tool_calls[0]
        args = json.loads(tool_call.function.arguments)
        # ... dispatch to actual function, append result to messages
        break  # simplified; real loop continues until finish_reason == "stop"
```

## Use It

| Scenario | Best Approach | Tooling |
|----------|---------------|---------|
| Q&A over internal docs | RAG pipeline | LlamaIndex + pgvector or Pinecone |
| Customer chatbot with guardrails | Prompt engineering + system prompt + evals | OpenAI / Anthropic API + Braintrust |
| Code generation assistant | Few-shot + structured output | GitHub Copilot API or Claude API |
| Domain-specific classifier | SFT on a small open model | Hugging Face TRL + LoRA |
| Multi-step autonomous task | Agent with tool use | LangGraph or CrewAI |
| Image generation pipeline | Diffusion model API | DALL-E 3, Midjourney API, Flux on Replicate |
| On-premise private deployment | Quantized open model | Ollama + Llama 3.1 or Mistral 7B |

### Model Selection at a Glance

```
High intelligence, complex reasoning  → Claude 3.5 Sonnet, GPT-4o, Gemini 1.5 Pro
Cost-sensitive, high volume           → GPT-4o-mini, Claude Haiku, Gemini Flash
Open-source, on-prem compliance       → Llama 3.1 70B, Mistral Large, DeepSeek-V2
Coding tasks                          → Claude 3.5 Sonnet, DeepSeek Coder
Long context (>128k tokens)           → Gemini 1.5 Pro (1M ctx), Claude 3.5 (200k)
Image understanding                   → GPT-4o, Claude 3 (vision), Gemini 1.5
```

## Common Pitfalls

- **Skipping math and going straight to APIs.** When your model produces nonsense probabilities or fails to follow temperature settings, you have no debugging leverage. Invest two weeks in Block 1; it pays back tenfold.

- **Fine-tuning before prompting.** Fine-tuning costs time, money, and a labeled dataset. Most tasks — including style, tone, and domain vocabulary — are solvable with a well-constructed system prompt and few-shot examples. Always exhaust prompting and RAG first.

- **Treating VectorDB as magic.** Embedding quality, chunk size, overlap, and reranking strategy all dramatically affect retrieval. Teams that dump raw PDFs into Pinecone and expect perfect recall are always disappointed. Evaluate retrieval separately from generation.

- **Ignoring evaluation from day one.** "It looks good to me" does not scale. Build an eval suite — even 50 human-labeled examples — before shipping. Without evals, you cannot tell if a model upgrade helped or hurt.

- **Using a 405B parameter model for a simple classification task.** Every layer of the stack has a cost-quality frontier. A fine-tuned Llama 3.1 8B beats GPT-4o on narrow tasks and costs 50x less per token. Match model size to task complexity.

## Exercises

1. **Easy:** Pick one foundation model (e.g., GPT-4o-mini) and send the same factual question five times with `temperature=0` and five times with `temperature=1.0`. Document the variance in outputs and explain why it differs.

2. **Medium:** Build a RAG system for a 20-page PDF of your choice. Chunk it at 512 tokens with 64-token overlap, embed with `text-embedding-3-small`, and retrieve with cosine similarity. Measure precision@3 on 10 hand-labeled questions. Then tune chunk size and compare.

3. **Hard:** Fine-tune a LoRA adapter on Llama 3.1 8B for a sentiment classification task using the SST-2 dataset. Compare its accuracy and per-inference cost to a zero-shot GPT-4o-mini baseline. Write a one-page decision memo recommending which to use in production and why.

## Key Terms

| Term | What people think | What it actually means |
|------|------------------|------------------------|
| **Foundation Model** | A very large, smart chatbot | A model pre-trained on broad data at scale, usable as a base for downstream tasks via prompting or fine-tuning |
| **Fine-tuning** | Teaching the model new facts | Updating a subset of model weights on task-specific labeled data to shift its behavior; does not reliably inject factual knowledge |
| **RAG** | A smarter prompt | Retrieval-Augmented Generation: retrieving relevant documents and injecting them into context at inference time to ground generation in source material |
| **Embedding** | A black-box vector | A dense numerical representation of text (or other data) where semantic similarity corresponds to geometric proximity |
| **Agent** | An AI that does things autonomously | A model in a loop that can call tools, observe results, and decide next actions — still deterministic given the model and tool outputs |
| **LoRA** | A way to make models smaller | Low-Rank Adaptation: freezing base weights and training small rank-decomposed matrices injected into attention layers — reduces trainable parameters by 99%+ |
| **Temperature** | How creative the model is | A scalar applied before the softmax that controls the sharpness of the token probability distribution; 0 = argmax (greedy), higher = more uniform sampling |

## Further Reading

- [Hugging Face NLP Course](https://huggingface.co/learn/nlp-course) — Hands-on, free, covers tokenizers, transformers, and fine-tuning end-to-end.
- [fast.ai Practical Deep Learning for Coders](https://course.fast.ai/) — Best bottom-up treatment of the math and code simultaneously; goes from notebooks to production.
- [DeepLearning.AI Short Courses](https://www.deeplearning.ai/short-courses/) — Focused 1-2 hour courses on RAG, agents, prompt engineering, and fine-tuning by practitioners.
- [Anthropic Model Card and Usage Policy](https://www.anthropic.com/claude) — Understand capability benchmarks, context windows, and safety characteristics of frontier models.
- [Lilian Weng's Blog — Prompt Engineering](https://lilianweng.github.io/posts/2023-03-15-prompt-engineering/) — Rigorous survey of prompting techniques with references to original papers; invaluable reference for practitioners.
