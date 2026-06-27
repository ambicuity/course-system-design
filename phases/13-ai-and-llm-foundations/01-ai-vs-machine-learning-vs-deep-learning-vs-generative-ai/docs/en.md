# AI vs Machine Learning vs Deep Learning vs Generative AI

> Four nested terms — every Generative AI is a Deep Learning system, every Deep Learning is Machine Learning, every Machine Learning is AI. Knowing the boundaries keeps the conversation precise.

**Type:** Learn
**Prerequisites:** None
**Time:** ~20 minutes

---

## The Problem

The terms are used interchangeably by people who should know better. Marketing copy says "AI" when it means "a logistic regression model." Press articles say "machine learning" when describing a generative model. Job postings ask for "AI engineers" but interview for "LLM prompt tuning." The vocabulary drift makes it hard to discuss technology precisely — and to know which skills, tools, and limits apply to which system.

The four terms — AI, Machine Learning, Deep Learning, Generative AI — are nested categories, not synonyms. Each one is a strict subset of the previous. Generative AI is the smallest, most specific category. AI is the broadest, most general. Confusing them leads to over-promising ("our AI is creative") and under-delivering ("our AI is just statistics").

This lesson draws the boundaries. You will leave with a clear mental model of what each term covers, what techniques belong to each, and how to talk about them without ambiguity.

---

## The Concept

### The nested hierarchy

```
   ┌─────────────────────────────────────────────────────────────┐
   │                                                             │
   │   ARTIFICIAL INTELLIGENCE (AI)                              │
   │   "Systems that perform tasks requiring human intelligence" │
   │                                                             │
   │   ┌─────────────────────────────────────────────────────┐   │
   │   │                                                     │   │
   │   │   MACHINE LEARNING (ML)                             │   │
   │   │   "Systems that learn from data"                    │   │
   │   │                                                     │   │
   │   │   ┌─────────────────────────────────────────────┐   │   │
   │   │   │                                             │   │   │
   │   │   │   DEEP LEARNING (DL)                        │   │   │
   │   │   │   "Neural networks with many layers"        │   │   │
   │   │   │                                             │   │   │
   │   │   │   ┌─────────────────────────────────────┐   │   │   │
   │   │   │   │                                     │   │   │   │
   │   │   │   │   GENERATIVE AI (GenAI)             │   │   │   │
   │   │   │   │   "Models that create new content"   │   │   │   │
   │   │   │   │                                     │   │   │   │
   │   │   │   └─────────────────────────────────────┘   │   │   │
   │   │   │                                             │   │   │
   │   │   └─────────────────────────────────────────────┘   │   │
   │   │                                                     │   │
   │   └─────────────────────────────────────────────────────┘   │
   │                                                             │
   └─────────────────────────────────────────────────────────────┘
```

Every Generative AI system is a Deep Learning system. Every Deep Learning system is a Machine Learning system. Every Machine Learning system is an AI system. But the reverse is not true: most AI is not Generative AI; most ML is not Deep Learning; most DL is not Generative.

---

### Artificial Intelligence (the outermost ring)

**Definition:** the broad field of computer science focused on creating systems that perform tasks typically requiring human intelligence — reasoning, learning, perception, planning, language understanding.

**What counts as AI:**

- Rule-based expert systems (MYCIN, 1970s — diagnose bacterial infections)
- Search algorithms (Deep Blue, 1997 — chess)
- Classical planning (STRIPS, Shakey the robot, 1960s–70s)
- Machine learning systems (any of the below)
- Robotics, computer vision, NLP, speech recognition
- Modern LLMs and multimodal models

**What does not count as AI:**

- Standard deterministic software (a calculator is not AI)
- Pure statistical models without any learning component (a lookup table is not AI)
- Human intelligence itself (we are studying the field, not part of it)

AI is the umbrella term. When someone says "AI," they could mean any of the above — so the term is usually too vague to be useful in technical conversations without further qualification.

---

### Machine Learning (a subset of AI)

**Definition:** a subset of AI focused on algorithms that learn patterns from data instead of being explicitly programmed.

**The shift in mindset:**

```
   Traditional programming:
   Input + Program → Output

   Machine learning:
   Input + Output → Program (learned model)
```

In traditional programming, a human writes the rules. In machine learning, the human provides examples and the system discovers the rules.

**Examples of ML (not deep learning):**

- Linear regression, logistic regression
- Decision trees, random forests, gradient-boosted trees (XGBoost, LightGBM)
- Support vector machines
- K-nearest neighbors
- Naive Bayes
- Simple clustering (k-means)

**Where ML is used:**

- Spam detection
- Recommendation systems
- Fraud detection
- Customer churn prediction
- Credit scoring
- Demand forecasting

Most production ML systems today are *not* deep learning. They are gradient-boosted trees and logistic regression running on structured (tabular) data.

---

### Deep Learning (a subset of ML)

**Definition:** a specialized subset of ML that uses neural networks with many layers to model complex patterns in data.

**What makes it "deep":**

The word refers to the number of layers in the neural network. A "shallow" network might have 1–3 layers. A "deep" network might have 12, 24, 96, or even hundreds of layers. Depth lets the network learn hierarchical representations — simple features in early layers, complex features in later layers.

```
   Input:    "Image of a cat"
                │
                ▼
   Layer 1:  edges, gradients
                │
                ▼
   Layer 5:  textures, corners
                │
                ▼
   Layer 10: parts (eyes, ears)
                │
                ▼
   Layer 20: objects (face, body)
                │
                ▼
   Output:   "cat" (0.97)
```

**Types of deep learning:**

- **CNNs (Convolutional Neural Networks)** — image and video processing
- **RNNs / LSTMs** — sequential data (mostly superseded by transformers)
- **Transformers** — language, and now images, audio, video, code, proteins
- **GANs (Generative Adversarial Networks)** — image generation (largely superseded by diffusion)
- **Diffusion models** — image / audio generation
- **Reinforcement learning networks** — game playing, robotics

**Where deep learning is used:**

- Image classification, object detection, segmentation
- Speech recognition, speech synthesis
- Machine translation, summarization, question answering
- Protein structure prediction (AlphaFold)
- Game playing (AlphaGo, OpenAI Five)
- Code generation, scientific reasoning

---

### Generative AI (a subset of Deep Learning)

**Definition:** AI systems that generate new content — text, images, code, audio, video, 3D models — that resembles the data they were trained on.

**What separates GenAI from other DL:**

Most deep learning is *discriminative* — given an input, classify it or predict a label. Generative AI is *generative* — given a prompt, produce a new output that did not exist before.

```
   Discriminative:   Image → "cat"
   Generative:       "cat" → Image
```

**Types of generative models:**

| Type | What it generates | Examples |
|---|---|---|
| **Large Language Models (LLMs)** | Text | GPT-4o, Claude, Gemini, Llama, DeepSeek |
| **Image generators** | Images | DALL-E, Midjourney, Stable Diffusion, Flux |
| **Video generators** | Video | Sora, Runway Gen-3, Veo |
| **Audio generators** | Speech, music | ElevenLabs, Suno, Udio |
| **Code generators** | Code | Copilot, Cursor, Codex |
| **Multimodal generators** | Mixed modalities | GPT-4o, Gemini, Claude (with vision) |
| **3D generators** | 3D models | Meshy, Tripo, CSM |

**Where GenAI is used:**

- Customer support chatbots and agents
- Code generation and review
- Content creation (articles, images, videos)
- Search and question answering
- Drug discovery (protein design)
- Synthetic data generation
- Creative tools (design, music, writing)

---

### What each term implies technically

| Term | Typical techniques | Typical data | Typical compute |
|---|---|---|---|
| AI | Anything | Anything | Anything |
| ML | Statistical learning on data | Structured, text, images | CPU, modest GPU |
| DL | Neural networks with many layers | Large datasets, often unstructured | Heavy GPU / TPU |
| GenAI | Large transformer / diffusion models | Massive corpora | Massive GPU clusters |

The compute column is the sharpest discriminator. A linear regression model runs on a laptop in milliseconds. GPT-4o's training run consumed gigawatt-hours. The cost and infrastructure difference is what makes GenAI a separate field, not just a clever application of ML.

---

### When to use which term

```
   Are you describing the entire field of computer science
   that builds intelligent systems?
   → "AI"

   Are you describing any system that learns from data?
   → "Machine Learning" (or just "ML")

   Are you describing neural networks with many layers?
   → "Deep Learning"

   Are you describing models that generate new content?
   → "Generative AI" (or "GenAI")

   Specifically text generation?
   → "Large Language Models" (or "LLMs")

   Specifically image generation?
   → "Diffusion models" or "image generators"
```

Being precise matters in design reviews, job descriptions, and technical writing. "We use AI for fraud detection" is uninformative. "We use a gradient-boosted tree model trained on 18 months of transaction data to score the probability of fraud" is precise.

---

## Build It / In Depth

### The same problem, four approaches

**Task:** detect spam emails.

**AI approach (rule-based):**
```python
def is_spam(email):
    if "free money" in email.subject.lower():
        return True
    if "viagra" in email.body.lower():
        return True
    if email.sender.endswith("@shady-domain.com"):
        return True
    return False
```
No learning. Pure rules. This is AI but not ML.

**ML approach (logistic regression):**
```python
from sklearn.linear_model import LogisticRegression
from sklearn.feature_extraction.text import TfidfVectorizer

X = vectorizer.fit_transform(emails)        # bag-of-words features
y = [1 if is_spam else 0 for is_spam in labels]
model = LogisticRegression().fit(X, y)
```
Learns from labeled data. Statistical. Shallow. This is ML but not DL.

**DL approach (small neural network):**
```python
import torch.nn as nn

class SpamClassifier(nn.Module):
    def __init__(self, vocab_size, hidden=64):
        super().__init__()
        self.embed = nn.Embedding(vocab_size, hidden)
        self.fc = nn.Linear(hidden, 1)

    def forward(self, x):
        return self.fc(self.embed(x).mean(dim=1))
```
Neural network with embeddings. This is DL but not GenAI.

**GenAI approach (LLM-based):**
```python
def is_spam(email):
    prompt = f"""Classify this email as spam or not.
    Email: {email.subject} - {email.body[:500]}
    Answer with just 'spam' or 'not spam'."""
    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    ).choices[0].message.content
    return "spam" in response.lower()
```
Uses a generative model to produce a classification. This is GenAI applied to a discriminative task — and usually overkill.

The point: the four terms describe overlapping techniques, and the right choice depends on the problem. A logistic regression will outperform GPT-4o on spam detection, run in 1ms, cost nothing, and be auditable.

---

### Decision tree: which technique for which problem

```
   Do you have a clear, narrow task with structured data?
   (spam, churn, fraud, recommendation)
       │
       ▼
   Use classical ML: gradient-boosted trees, logistic regression.
   Cheap, fast, interpretable, well-understood.

   Do you have unstructured data (images, audio, video)?
       │
       ▼
   Use deep learning: CNNs, transformers for vision/audio.
   Necessary because classical ML cannot model raw pixels.

   Do you need to generate content (text, code, images, video)?
       │
       ▼
   Use Generative AI: LLMs, diffusion models.
   Expensive but uniquely capable at generation.

   Do you need to understand or transform text?
       │
       ▼
   Use either: classical NLP (for narrow tasks) or LLMs (for broad tasks).
```

---

## Use It

### When to use which layer

| Problem shape | Use | Why |
|---|---|---|
| Tabular data, narrow task, high interpretability | Classical ML | Cheap, fast, explainable |
| Image / video classification | Deep learning (CNN, ViT) | State-of-the-art accuracy |
| Speech recognition / synthesis | Deep learning | Best-in-class |
| Text classification / NER | Classical NLP or fine-tuned BERT | Cheap and accurate |
| Text generation, summarization, Q&A | LLM | Best-in-class |
| Code generation | LLM | State-of-the-art |
| Image generation | Diffusion model | Best-in-class |
| Multi-step reasoning | LLM agent | Tool use + planning |
| Scientific discovery (proteins, materials) | Specialized DL | AlphaFold-style models |

---

### Common confusions to avoid

| Confused as… | Actually… |
|---|---|
| "AI" (in marketing) | Usually classical ML, not GenAI |
| "Deep learning" (in headlines) | Usually means LLMs, not the broader DL field |
| "Machine learning" (in job titles) | Often means LLM engineering, which is a subfield |
| "Generative AI" (in demos) | Sometimes just a fancy front-end over a classifier |

---

## Common Pitfalls

- **Calling every LLM application "AI."** It is AI, but it is also ML, also DL, also GenAI. Use the most specific accurate term. Saying "our GenAI agent" is more informative than "our AI."

- **Calling logistic regression "AI."** It is AI in the broadest sense, but in a technical conversation, "ML model" is more precise and sets accurate expectations.

- **Assuming "deep" means "better."** Deep learning is not always better than classical ML. For tabular data, gradient-boosted trees routinely beat deep networks. Use DL when the data modality demands it.

- **Treating GenAI as a hammer.** Not every problem is a generation problem. Classification, ranking, and regression problems usually have better non-GenAI solutions.

- **Ignoring the compute difference.** A classical ML model trains on a laptop in seconds. A GenAI model trains on a supercomputer for months. The cost gap is 6–8 orders of magnitude. Pick the technique whose cost matches the value of the problem.

- **Confusing "AI" with "AGI."** AI is the field. AGI (Artificial General Intelligence) is a hypothetical future system with human-level general reasoning. They are not the same; most AI is not AGI; most GenAI is far from AGI.

---

## Exercises

1. **Easy** — Pick four real products or systems (one AI, one ML, one DL, one GenAI). For each, identify which technique within the category it uses, and what data it operates on.

2. **Medium** — Take a problem you have worked on (or a hypothetical one). Walk through the decision tree and identify which category fits. Justify why you would or would not use a more advanced technique.

3. **Hard** — A company claims "our AI does X" where X is one of: detecting fraud, generating marketing copy, recognizing faces, predicting customer churn. For each, identify the most specific category (ML, DL, GenAI), the most likely technique, the data requirements, and a realistic cost / performance estimate.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| AI | Any computer program | The broad field of building systems that perform tasks requiring human intelligence; includes rule-based systems, classical AI, ML, DL, and GenAI |
| Machine Learning | AI that learns | A subset of AI focused on algorithms that learn from data instead of being explicitly programmed; includes linear models, tree models, and neural networks |
| Deep Learning | ML with neural networks | A subset of ML using neural networks with many layers; the only family that can handle raw pixels, audio, and text at scale |
| Generative AI | AI that creates | A subset of DL focused on models that produce new content (text, images, code, video); dominated by transformers for text and diffusion for images |
| Discriminative model | Any ML model | A model that learns a decision boundary between classes — given an input, predict a label; the dominant form of ML in production |
| Generative model | An AI that creates | A model that learns the distribution of training data — given a prompt, produce a new sample; the basis of all GenAI |
| Foundation model | A pretrained model | A large model trained on broad data that can be adapted to many downstream tasks; usually refers to LLMs, but also image and multimodal models |
| AGI | AI that thinks like humans | A hypothetical AI with human-level general intelligence across all domains; does not exist today and is not the same as AI, ML, DL, or GenAI |

---

## Further Reading

- **"Artificial Intelligence: A Modern Approach"** — Russell & Norvig's textbook, the canonical reference for the AI field: https://aima.cs.berkeley.edu/
- **"Deep Learning"** — Goodfellow, Bengio, and Courville's free textbook, the canonical reference for deep learning: https://www.deeplearningbook.org/
- **"The Bitter Lesson"** — Rich Sutton's influential essay on why general methods (compute + learning) win over hand-engineered approaches: http://www.incompleteideas.net/IncompleteIdeas/bitterlesson.html
- **Hugging Face Course** — a free, hands-on introduction to modern NLP and generative AI: https://huggingface.co/learn
- **Andrej Karpathy's "Intro to Large Language Models"** — a one-hour video that explains LLMs as the convergence of the four layers: https://www.youtube.com/watch?v=zjkBMFhNj_g