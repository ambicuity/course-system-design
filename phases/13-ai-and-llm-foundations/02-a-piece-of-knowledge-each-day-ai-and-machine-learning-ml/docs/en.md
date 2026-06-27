# AI and Machine Learning (ML) Fundamentals

> ML is the engine of the AI revolution — and confusing the two costs you in architecture decisions.

**Type:** Learn
**Prerequisites:** Introduction to System Design, Data Modeling Basics
**Time:** ~35 minutes

---

## The Problem

You are building a product recommendation feature. Your PM says "add some AI to this." You nod. Then you open a browser and immediately face a wall of overlapping terms: AI, ML, deep learning, neural networks, supervised learning, reinforcement learning. You copy-paste a scikit-learn tutorial, tune nothing, ship it, and watch conversion rates drop.

This happens because "AI" is a marketing umbrella and "ML" is an engineering discipline. The moment you treat them as synonyms you make two categories of bad decisions: you over-scope ("we need a neural network!") when a logistic regression would beat baseline by 8%, or you under-scope ("that's just a filter, not AI") when a trained model would handle edge cases that ten thousand `if` statements cannot.

Understanding where AI ends, where ML begins, and what the sub-disciplines of ML actually mean lets you pick the right tool. It also helps you talk credibly to data scientists, set realistic data and compute requirements, and reason about the failure modes of your system before you build it.

---

## The Concept

### The Hierarchy

AI, ML, and deep learning are nested — each is a proper subset of the one above it.

```
┌──────────────────────────────────────────────────────┐
│  AI (Artificial Intelligence)                        │
│  Any system that mimics human cognitive functions    │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │  ML (Machine Learning)                         │  │
│  │  Algorithms that learn patterns from data      │  │
│  │                                                │  │
│  │  ┌──────────────────────────────────────────┐  │  │
│  │  │  Deep Learning                           │  │  │
│  │  │  ML via multi-layer neural networks      │  │  │
│  │  │                                          │  │  │
│  │  │  ┌────────────────────────────────────┐  │  │  │
│  │  │  │  LLMs / Foundation Models          │  │  │  │
│  │  │  │  Transformer-based, massive scale  │  │  │  │
│  │  │  └────────────────────────────────────┘  │  │  │
│  │  └──────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

**AI (Artificial Intelligence)** — the field. Any program that senses, reasons, acts, or adapts in ways we associate with human intelligence qualifies. This includes rule-based expert systems from the 1980s that contain zero statistics.

**ML (Machine Learning)** — a sub-field of AI. Instead of hand-coding rules, you feed labeled examples to an algorithm that extracts the rules itself. The distinguishing property: *performance improves as it sees more data*.

**Deep Learning** — a sub-field of ML using artificial neural networks with many layers. It excels when the input is unstructured (images, audio, text) and feature engineering by hand would be intractable.

**Foundation Models / LLMs** — a sub-field of deep learning. Models pre-trained on internet-scale data and then fine-tuned or prompted for specific tasks. GPT-4, Claude, Gemini, Llama all belong here.

### How ML Actually Works

Every ML problem reduces to the same four-step loop:

```
 Data ──► Feature Engineering ──► Model Training ──► Evaluation
   ▲                                                       │
   └──────────────── Iterate until metrics pass ───────────┘
```

1. **Data** — labeled examples (supervised) or raw examples (unsupervised). Quality matters more than quantity.
2. **Feature Engineering** — transforming raw data into numeric representations the algorithm can use. Classic ML requires explicit features (age, click-rate); deep learning learns features from raw input.
3. **Training** — the algorithm adjusts its internal parameters to minimize a loss function on the training set.
4. **Evaluation** — test on held-out data. If accuracy/precision/recall meet the bar, deploy. Otherwise iterate.

### The Three Learning Paradigms

| Paradigm | What you provide | Algorithm learns | Example use case |
|---|---|---|---|
| **Supervised** | Input + correct label | A mapping from input → label | Spam classifier, price prediction |
| **Unsupervised** | Input only (no labels) | Structure/clusters in the data | Customer segmentation, anomaly detection |
| **Reinforcement** | Environment + reward signal | A policy to maximize reward | Game agents, robotics, RLHF fine-tuning |

Most production ML is supervised. You have logs, you label them (or they are self-labeled by user actions), and you train a model to predict the label for new inputs.

### The Bias-Variance Trade-off

Every model sits on a spectrum between two failure modes:

```
High Bias (underfitting)           High Variance (overfitting)
   Model too simple                   Model memorizes training data
   Misses real patterns               Fails on unseen data
         │                                    │
         └──────────────┬─────────────────────┘
                   Sweet spot
              (generalizes well)
```

- **High bias**: your linear model predicting house prices ignores the neighborhood feature. Training error and test error are both high.
- **High variance**: a decision tree with unlimited depth memorizes every training record. Training error is near zero; test error is terrible.

The fix: regularization (L1/L2), cross-validation, more training data, or a simpler model family.

### How a Model Learns: Gradient Descent

Parameters are adjusted by computing the gradient of the loss with respect to each parameter and moving in the direction that reduces the loss:

```
w ← w − α · ∇L(w)
```

- `w` = model weights (parameters)
- `α` = learning rate (step size)
- `∇L(w)` = gradient of the loss function

In practice, you use **stochastic gradient descent (SGD)** or Adam, which estimate the gradient over mini-batches instead of the full dataset — this is why GPU parallelism is valuable.

---

## Build It / In Depth

### A Concrete Supervised Learning Example

**Problem**: Predict whether a user will churn (cancel subscription) within 30 days.

**Step 1 — Collect and label data**

```python
import pandas as pd

# Each row is one user observed at a point in time
# Label: did they churn within 30 days?
df = pd.read_csv("user_events.csv")
# Columns: user_id, days_since_last_login, num_sessions_last_30d,
#          support_tickets_open, plan_tier, churned (0/1)
print(df.head())
```

**Step 2 — Feature engineering and split**

```python
from sklearn.model_selection import train_test_split

FEATURES = ["days_since_last_login", "num_sessions_last_30d",
            "support_tickets_open", "plan_tier_encoded"]
TARGET = "churned"

X = df[FEATURES]
y = df[TARGET]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
```

**Step 3 — Train a simple model**

```python
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

pipeline = Pipeline([
    ("scaler", StandardScaler()),
    ("clf", GradientBoostingClassifier(n_estimators=100, max_depth=4)),
])

pipeline.fit(X_train, y_train)
```

**Step 4 — Evaluate**

```python
from sklearn.metrics import classification_report, roc_auc_score

y_pred = pipeline.predict(X_test)
y_prob = pipeline.predict_proba(X_test)[:, 1]

print(classification_report(y_test, y_pred))
print(f"AUC-ROC: {roc_auc_score(y_test, y_prob):.3f}")
```

A healthy churn model typically reaches AUC-ROC > 0.80. Below 0.70, your feature set is weak or your labels are noisy. AUC measures the model's ability to rank a churner above a non-churner — relevant when the classes are imbalanced (they always are in churn).

**Step 5 — Serve predictions**

```python
# At inference time (e.g., a nightly batch job or a real-time API)
import joblib

joblib.dump(pipeline, "churn_model.pkl")

# In your service:
model = joblib.load("churn_model.pkl")
user_features = [[14, 3, 2, 1]]   # days_since_login, sessions, tickets, tier
proba = model.predict_proba(user_features)[0][1]
# proba = 0.73 → high churn risk, trigger retention campaign
```

### Decision Flowchart: Which ML Approach?

```
Do you have labeled training data?
    │
    ├─ YES ──► Supervised Learning
    │              │
    │              ├─ Output is a category?  ──► Classification
    │              └─ Output is a number?    ──► Regression
    │
    └─ NO  ──► Do you have a reward signal you can simulate?
                   │
                   ├─ YES ──► Reinforcement Learning
                   └─ NO  ──► Unsupervised Learning
                                  │
                                  ├─ Find groups?    ──► Clustering (K-Means, DBSCAN)
                                  └─ Find outliers?  ──► Anomaly Detection
```

---

## Use It

### When to reach for each tool

| Scenario | Recommended approach | Why |
|---|---|---|
| Spam / fraud detection (binary) | Gradient Boosting (XGBoost, LightGBM) | Tabular data, fast to iterate, interpretable |
| Image classification | CNN / Vision Transformer | Feature extraction from pixels is intractable by hand |
| Recommendation engine (collaborative) | Matrix Factorization, Two-Tower Neural Net | Learns latent user-item affinity |
| Text sentiment / classification | Fine-tuned BERT or LLM API | Pre-trained language understanding |
| Anomaly detection without labels | Isolation Forest, Autoencoder | No labeled anomalies available |
| Sequential decisions (game, pricing) | Reinforcement Learning (PPO, SAC) | Reward signal replaces labels |
| Time-series forecasting | ARIMA, LightGBM, Temporal Fusion Transformer | Depends on data volume and horizon |

### Production tooling

| Layer | Popular options |
|---|---|
| Training frameworks | scikit-learn (tabular), PyTorch / TensorFlow (neural nets) |
| Feature stores | Feast, Tecton, Databricks Feature Store |
| Model registry | MLflow, Weights & Biases, SageMaker Model Registry |
| Serving | BentoML, TorchServe, SageMaker Endpoints, Vertex AI |
| Monitoring | Evidently AI, WhyLabs, Arize |
| Orchestration | Kubeflow, Metaflow, Airflow + custom steps |

---

## Common Pitfalls

- **Training-serving skew** — your training pipeline computes features one way; your serving pipeline computes them slightly differently (e.g., timezone mismatch in recency features). The model's real-world performance drops 10–20% and the bug is invisible in offline metrics. Use a feature store so both pipelines share the same transformation logic.

- **Data leakage** — accidentally including information in your training features that is not available at prediction time (e.g., using `support_tickets_resolved` which is only set after the user calls support post-churn). AUC looks great offline; production performance is near random. Always timestamp your feature join carefully.

- **Label imbalance ignored** — a churn dataset might be 2% positive. A naive model that always predicts "no churn" gets 98% accuracy. Use AUC-ROC, F1, or precision/recall, not accuracy. Set `class_weight="balanced"` or oversample.

- **Conflating AI with ML** — deploying a rule engine is not ML, and that is fine. Conversely, assuming every ML model needs a neural network when a decision tree with five features solves the problem is expensive. Match the tool to the problem.

- **No monitoring after deployment** — ML models decay. User behavior shifts, data distributions change, upstream schema changes silently alter features. Add distribution monitoring (input drift, prediction drift) from day one. A model with no monitoring is a time bomb.

---

## Exercises

1. **(Easy)** Given a dataset of apartment listings (square footage, number of rooms, neighborhood, price), identify: is this supervised or unsupervised? Is it classification or regression? What would a reasonable baseline model be before trying a neural network?

2. **(Medium)** You are building a content moderation system. Your labeled dataset has 1,000 toxic posts and 50,000 clean posts. Design the evaluation strategy: which metric do you optimize, how do you handle the imbalance, and what does a false negative cost vs. a false positive?

3. **(Hard)** A recommendation system is performing well offline (NDCG@10 = 0.42) but click-through rate in production is flat. List three architectural reasons this gap can occur and how you would diagnose each one. Your answer should reference training data generation, feature leakage, and feedback loop effects.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **AI** | Anything smart a computer does | The broad field of building systems that mimic human intelligence — includes rule-based systems with no statistics |
| **ML** | Synonymous with AI | A sub-field of AI: algorithms that improve their performance on a task by learning from data |
| **Deep Learning** | Just a fancy neural net | ML using networks with many layers; enables learning representations directly from raw, unstructured inputs |
| **Training** | "Running the AI" | The optimization process that adjusts model parameters to minimize loss on labeled examples |
| **Overfitting** | A model that is too accurate | A model that has memorized training data and generalizes poorly to new data |
| **Feature** | A column in a table | A measurable, numeric representation of an attribute used as input to a model |
| **AUC-ROC** | A score between 0 and 1 | Area Under the Receiver Operating Characteristic curve — the probability that the model ranks a positive example above a negative one |

---

## Further Reading

- [Google's Machine Learning Crash Course](https://developers.google.com/machine-learning/crash-course) — free, structured, and grounded in TensorFlow; covers fundamentals through deployment.
- [Scikit-learn User Guide](https://scikit-learn.org/stable/user_guide.html) — the reference for classical ML algorithms, preprocessing, and model evaluation in Python.
- [*The Elements of Statistical Learning* — Hastie, Tibshirani, Friedman (free PDF)](https://web.stanford.edu/~hastie/ElemStatLearn/) — the mathematical foundation; chapters 2–4 cover bias-variance, linear models, and regularization.
- [Chip Huyen, *Designing Machine Learning Systems* (O'Reilly, 2022)](https://www.oreilly.com/library/view/designing-machine-learning/9781098107956/) — practical coverage of the full ML lifecycle in production, from framing to monitoring.
- [Made With ML — MLOps curriculum](https://madewithml.com/) — end-to-end walkthrough from data through CI/CD for ML systems, with code.
