# How LLMs See the World

> LLMs don't read words — they compute over integer sequences mapped to high-dimensional vectors.

**Type:** Learn
**Prerequisites:** Neural Network Basics, Transformer Architecture Overview
**Time:** ~35 minutes

---

## The Problem

You integrate an LLM API into your product and immediately hit unexpected behavior: a simple pricing
query burns 3× more tokens than you estimated, your carefully crafted prompt gets silently truncated,
and the model confidently hallucinates a currency conversion because it split "€1,200" across token
boundaries in a way that destroyed the numeric meaning. None of this makes sense if you're thinking
of the model as "a very smart text reader."

The root cause is that you're reasoning about the wrong abstraction. LLMs don't process words,
sentences, or characters. They process *tokens* — compressed subword units encoded as integers —
and they operate entirely in a fixed-size numerical space called the context window. When your mental
model doesn't match the model's actual input representation, you miscount costs, misdesign prompts,
and misread failures.

This lesson closes that gap. Understanding how an LLM ingests and represents text lets you reason
accurately about token budgets, embedding similarity, context limits, and the failure modes unique
to subword tokenization — all of which directly affect the systems you build on top of LLMs.

---

## The Concept

### Step 1 — Preprocessing

Before any model sees your text, a normalizer runs over it:

- Unicode normalization (NFC/NFD/NFKC) collapses visually identical characters to a canonical form.
- Whitespace is standardized; invisible characters, zero-width joiners, and BOM markers are stripped
  or mapped.
- Some tokenizers lowercase everything; others are case-sensitive.

This step is model-specific and not always documented. The takeaway: the string you send is not
necessarily the string the model processes.

### Step 2 — Tokenization

Tokenization converts a normalized string into a list of *tokens*, where each token is a short
chunk of text. Three families exist:

| Strategy       | Example input: `"unhappiness"` | Vocabulary size | Used by          |
|----------------|-------------------------------|-----------------|------------------|
| Character-based | `["u","n","h","a","p","p","i","n","e","s","s"]` | ~256 | Early RNNs |
| Word-based     | `["unhappiness"]`              | 100k–1M         | Classic NLP      |
| Subword-based  | `["un","happiness"]`           | 32k–128k        | All modern LLMs  |

**Why subword wins:** word-based tokenizers explode on rare words, typos, and morphologically rich
languages. Character-based tokenizers need extremely long sequences for any non-trivial text.
Subword tokenizers balance vocabulary size against sequence length and handle unseen words
gracefully by breaking them into known pieces.

**BPE (Byte-Pair Encoding)** is the dominant algorithm. It starts with a character vocabulary and
iteratively merges the most frequent adjacent pair into a new symbol. GPT-2, GPT-4, Claude, and
Gemini all use BPE variants.

```
Initial:  ["u","n","h","a","p","p","i","n","e","s","s"]
Merge "p"+"p" → "pp":   ["u","n","h","a","pp","i","n","e","s","s"]
Merge "n"+"e" → "ne":   ["u","n","h","a","pp","i","ne","s","s"]
Merge "ne"+"s" → "nes": ["u","n","h","a","pp","i","nes","s"]
... (50,000 more merges)
Final: ["un", "happiness"]
```

**WordPiece** (used by BERT) is similar but merges pairs that maximize likelihood of the training
corpus rather than raw frequency.

**SentencePiece / Unigram** (used by LLaMA, T5, Mistral) treats tokenization as a probabilistic
model over character sequences and can operate on raw bytes, which removes the need for a separate
preprocessing step and handles any Unicode natively.

### Step 3 — Token IDs

Each token in the vocabulary is assigned an integer ID. "Hello world" through GPT-4's tokenizer
yields roughly:

```
"Hello"  →  15496
" world" →    995
```

Notice the space before "world" is *part of the token*, not a separate entity. This is one reason
tokenization is surprising: word boundaries, punctuation attachment, and whitespace are baked into
the token boundaries in non-obvious ways.

### Step 4 — Embeddings

Token IDs are not fed into the transformer directly as integers. Each ID is looked up in an
**embedding matrix** — a learned table of shape `(vocab_size, d_model)` — and replaced with a
dense float vector. For GPT-4, `d_model` is reportedly 12,288. For LLaMA 3 70B, it's 8,192.

```
Token ID 15496  →  [0.023, -1.14, 0.87, ..., 0.004]  ← 8192 floats
Token ID 995    →  [-0.31,  0.55, 1.02, ..., -0.77]
```

These vectors are not fixed encodings — they are learned from scratch during pretraining. Tokens
that appear in similar contexts end up geometrically close in this high-dimensional space. "Paris"
and "Berlin" end up near each other; "Paris" and "photosynthesis" do not.

### Step 5 — Positional Encoding

Transformers process all token embeddings in parallel, so they have no inherent sense of position.
A positional encoding is added to each embedding to inject order information.

- **Learned absolute positions** (GPT-2): a separate learned vector for each position index, up to
  the max context length.
- **Rotary Position Embedding — RoPE** (LLaMA, Mistral, GPT-NeoX): encodes relative distances by
  rotating the query/key vectors in the attention computation. Generalizes better to unseen lengths.
- **ALiBi** (MPT, BLOOM): subtracts a linear bias from attention scores based on distance, with no
  additional parameters.

### Step 6 — Attention Over the Context Window

The transformer stacks layers of multi-head self-attention. Each attention head computes, for every
token, a weighted sum of all other tokens' values — where the weights reflect learned relevance:

```
Attention(Q, K, V) = softmax(QK^T / sqrt(d_k)) · V
```

Every token can "look at" every previous token (causal/autoregressive models mask future positions).
The full sequence of embeddings is what we call the **context window**. If a model has a 128k
context window, it can attend over up to 128,000 tokens simultaneously. This is the model's
entire "working memory" — nothing outside the window is visible.

```
Context window (128k tokens):
┌────────────────────────────────────────────────────────┐
│ [system prompt] [history] [retrieved docs] [user msg]  │
│ ←────────────────── 128,000 tokens ──────────────────→ │
└────────────────────────────────────────────────────────┘
      ↑ Everything outside this boundary is invisible
```

### Step 7 — Output: Next-Token Prediction

After all transformer layers, the final hidden state of the last token position is projected through
a linear layer (the "language model head") to produce a logit for every vocabulary token. A softmax
converts these to probabilities. The model samples or argmax-selects the next token, appends it to
the sequence, and repeats.

This is autoregressive generation: each output token becomes part of the input for the next step.

---

## Build It / In Depth

### Concrete walkthrough: tracing "€1,200 total" through GPT tokenization

Let's trace a snippet that regularly causes financial-application bugs.

**Step 1 — Tokenize with tiktoken (GPT-4's tokenizer)**

```python
import tiktoken

enc = tiktoken.encoding_for_model("gpt-4")
text = "€1,200 total"
tokens = enc.encode(text)
token_strings = [enc.decode([t]) for t in tokens]

print(tokens)        # [11396, 16, 11, 1049, 2860]  (approximate)
print(token_strings) # ['€', '1', ',', '200', ' total']
```

The euro sign is one token. The comma is a separate token. "1" and "200" are split. The model
receives *five* separate symbols for what a human reads as a single numeric value. Arithmetic over
this is fragile — the model must mentally re-assemble the pieces before it can operate on the
number.

**Step 2 — Observe the embedding lookup**

```python
# Using a smaller open model for illustration
from transformers import AutoTokenizer, AutoModel
import torch

model_id = "meta-llama/Llama-3.2-1B"
tokenizer = AutoTokenizer.from_pretrained(model_id)
model     = AutoModel.from_pretrained(model_id)

text   = "Hello world"
inputs = tokenizer(text, return_tensors="pt")
# inputs["input_ids"] → tensor([[1, 15043, 3186]])
#  1     = <bos> special token
#  15043 = "Hello"
#  3186  = " world"

with torch.no_grad():
    outputs = model(**inputs)

# outputs.last_hidden_state.shape → [1, 3, 2048]
# 1 sequence, 3 tokens, 2048-dim embedding per token
print(outputs.last_hidden_state.shape)
```

**Step 3 — Token budget math**

Token pricing is per token, not per word or per character. English prose averages ~1.3 tokens per
word. Code is denser (more punctuation, more unique tokens). A page of English text (~500 words) is
roughly 650–700 tokens.

```
Cost estimate for a 10-page report (5,000 words):
  Input tokens  ≈ 5,000 × 1.3  = 6,500
  Output tokens ≈ 500 (summary) = 500
  Total         ≈ 7,000 tokens

At GPT-4o pricing ($5/1M input, $15/1M output):
  Input cost  = 6,500 / 1,000,000 × $5  = $0.0325
  Output cost =   500 / 1,000,000 × $15 = $0.0075
  Total ≈ $0.04 per request
```

**Step 4 — Verify context-window headroom before calling the API**

```python
def fits_in_context(text: str, model: str, max_tokens: int = 128_000) -> bool:
    enc = tiktoken.encoding_for_model(model)
    return len(enc.encode(text)) < max_tokens

# Always check before constructing your prompt
assert fits_in_context(system_prompt + user_message, "gpt-4o")
```

---

## Use It

### Tokenizer libraries by ecosystem

| Library / Tool         | Supported models          | Primary use case                        |
|------------------------|---------------------------|-----------------------------------------|
| `tiktoken` (OpenAI)    | GPT-3.5, GPT-4, GPT-4o   | Token counting, cost estimation         |
| `tokenizers` (HuggingFace) | Most open models      | Training, inference, fine-tuning        |
| `SentencePiece`        | LLaMA, T5, PaLM, Gemma   | Low-level BPE/Unigram tokenization      |
| OpenAI Tokenizer UI    | GPT family                | Quick visual inspection of token splits |
| LangChain `TokenTextSplitter` | Any             | Splitting docs to fit context windows   |

### When tokenization choices affect your architecture

**RAG (Retrieval-Augmented Generation):** You must chunk documents before embedding them. Chunk
boundaries that fall mid-sentence or mid-token create degraded embeddings. Use token-aware splitters
(e.g., LangChain's `RecursiveCharacterTextSplitter` with `length_function=tiktoken_len`), not naive
character-count splits.

**Cost control:** Prompt caching (Anthropic's prompt caching, OpenAI's cached prompts) works at the
token level, not the string level. Structure your prompts so the stable prefix occupies the first
N tokens — the model's KV-cache hit rate depends on this ordering.

**Fine-tuning:** The tokenizer is frozen when you fine-tune. You cannot add new tokens to a
pre-trained vocabulary without also re-initializing the embedding layer and training from scratch.
Plan your vocabulary needs before choosing a base model.

**Multilingual applications:** Latin-script languages tokenize efficiently (1–2 chars/token).
Japanese, Chinese, Arabic, and Thai tokenize at 2–4× the token density of English, which directly
multiplies cost and reduces effective context length. Always benchmark with representative non-English
samples before committing to a token budget.

---

## Common Pitfalls

- **Counting words instead of tokens.** A 4,000-word document is not 4,000 tokens. It's typically
  5,000–6,000 tokens. Always count with the actual tokenizer before estimating cost or checking
  context-window headroom. The mismatch grows worse for code, structured data, and non-Latin scripts.

- **Assuming numbers are single tokens.** Multi-digit numbers, currency amounts, and dates almost
  always split across multiple tokens. Arithmetic and date math over raw token sequences is
  error-prone; format numeric inputs explicitly ("$1200", not "$1,200") and validate numeric outputs
  programmatically.

- **Ignoring special tokens in your count.** Every model prepends `<bos>` and often appends `<eos>`.
  Chat models wrap each turn in role tokens (`<|im_start|>user`, etc.). These consume tokens from
  your budget. A "4k context" model with a heavy system prompt may have fewer than 2k tokens left for
  the user message.

- **Treating the context window as a scrolling buffer.** The model sees the entire window at once,
  with uniform attention across all positions, but empirically performs better on content near the
  beginning and end of the window ("lost in the middle" effect). For long-context RAG, place the
  most critical context either at the top (system prompt) or immediately before the question.

- **Misusing embedding similarity across tokenizers.** Embedding vectors from GPT-4 and LLaMA 3 are
  not interchangeable. Each model has its own learned embedding space. Never mix vectors from
  different models in the same vector store.

---

## Exercises

1. **Easy — Token inspection.** Take five strings that look short to a human (`"$1,200"`,
   `"100%"`, `"don't"`, `"OpenAI"`, `"2024-06-01"`) and tokenize each using `tiktoken` with the
   `gpt-4o` encoding. Record how many tokens each produces and which characters became their own
   tokens. Explain one case where the split could cause a model to mishandle the value.

2. **Medium — Budget-aware RAG chunker.** Write a function `chunk_to_fit(text, max_tokens, model)`
   that splits a long document into a list of chunks, each fitting within `max_tokens`, using the
   model's actual tokenizer (not character count). Validate that every chunk, when tokenized, is
   strictly under the limit. Test it on a 20-page text and verify the chunk boundaries fall on
   sentence endings rather than mid-word.

3. **Hard — Cross-language token cost benchmark.** Build a benchmark that takes the same 500-word
   article translated into English, Spanish, German, Japanese, and Arabic. Tokenize each translation
   with the `meta-llama/Llama-3.1-8B` tokenizer and GPT-4o's `tiktoken`. Produce a table: language,
   character count, token count (each tokenizer), tokens-per-word, cost at current API rates.
   Explain the observed differences in terms of vocabulary design choices and their implications
   for multilingual product pricing.

---

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|------------------------|
| **Token** | A word | A variable-length subword unit; could be part of a word, a whole word, a space, or punctuation |
| **Vocabulary** | A dictionary of words | A fixed set of subword strings (typically 32k–128k) chosen to compress a training corpus efficiently |
| **Embedding** | A synonym for "vector representation" | Specifically, the lookup table row for a token ID; a dense float vector learned during pretraining |
| **Context window** | How much the model "remembers" | The maximum number of tokens in a single forward pass; content outside is completely invisible |
| **BPE** | A compression algorithm (unrelated to ML) | Byte-Pair Encoding; the iterative merge algorithm that builds most modern LLM vocabularies |
| **Token ID** | An internal detail you can ignore | The integer index that maps a token string to its row in the embedding matrix; the actual model input |
| **Lost in the middle** | Marketing for long-context models | Empirical finding that transformer models attend less reliably to content in the middle of very long contexts |

---

## Further Reading

- **OpenAI Tokenizer** — interactive visualization of GPT tokenization:
  https://platform.openai.com/tokenizer

- **Hugging Face NLP Course, Chapter 6 — The Tokenizers Library**:
  https://huggingface.co/learn/nlp-course/chapter6/1

- **"Byte Pair Encoding is Suboptimal for Language Model Pretraining"** (Bostrom & Durrett, 2020) —
  concise critique that sharpens intuition for why tokenizer choice matters:
  https://arxiv.org/abs/2004.03720

- **tiktoken source and benchmarks** (OpenAI):
  https://github.com/openai/tiktoken

- **"Lost in the Middle: How Language Models Use Long Contexts"** (Liu et al., 2023):
  https://arxiv.org/abs/2307.03172
