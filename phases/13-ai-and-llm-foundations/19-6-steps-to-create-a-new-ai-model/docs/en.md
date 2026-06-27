# 6 Steps to Create a New AI Model

> Building a model without a process is just expensive guessing.

**Type:** Learn
**Prerequisites:** Introduction to Machine Learning, Data Pipelines, Model Serving Basics
**Time:** ~25 minutes

---

## The Problem

Most teams that fail at ML don't fail because they chose the wrong algorithm. They fail because they skipped the boring parts: they never defined measurable success criteria, they trained on dirty data, or they shipped a model with no monitoring and no rollback plan. The model degrades silently in production and nobody knows why.

Consider a real scenario: a team at an e-commerce company wants to predict which customers will churn in the next 30 days. They download a CSV, throw it into an XGBoost notebook, hit 88% accuracy, and push it to prod. Three months later, churn is up. The model turned out to be predicting historical patterns during a promotion period, the training data was leaking future labels, and the feature pipelines in production were computing features differently than in training. None of this would have surfaced without a disciplined end-to-end process.

The 6-step framework in this lesson is the minimum viable process for building a production-grade AI model. It is not theoretical — each step maps to a class of real failures. Skip a step and you will pay for it later at a cost that dwarfs the time you saved.

---

## The Concept

The pipeline from idea to deployed model has six sequential phases. Each phase has well-defined inputs, outputs, and failure modes.

```
┌─────────────────────────────────────────────────────────────────┐
│   1. Setting     │  2. Data       │  3. Choose      │           │
│   Objectives     │  Preparation   │  Algorithm      │           │
│                  │                │                 │           │
│  Problem → KPIs  │ Raw → Clean    │ Task → Model    │           │
│                  │ Features       │ Framework       │           │
└─────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│   4. Train       │  5. Evaluate   │  6. Deploy      │           │
│   the Model      │  and Test      │  the Model      │           │
│                  │                │                 │           │
│  Fit → Tune      │ Metrics → Bias │ API → Monitor   │           │
│  Hyperparams     │ Holdout Set    │ Rollback        │           │
└─────────────────────────────────────────────────────────────────┘
```

The six phases are not independent. Decisions made in Step 1 constrain Step 3. The features engineered in Step 2 determine what signals are available in Step 4. A mismatch between the training pipeline in Step 2 and the serving pipeline in Step 6 is one of the most common production bugs in ML.

### Phase overview

| Step | Goal | Primary Output |
|------|------|----------------|
| 1. Setting Objectives | Agree on what "good" means | KPIs, feasibility assessment |
| 2. Data Preparation | Produce a clean, versioned dataset | Train / val / test splits |
| 3. Choose the Algorithm | Match model family to the task | Model architecture, framework |
| 4. Train the Model | Fit weights, tune hyperparameters | Trained artifact + training logs |
| 5. Evaluate and Test | Verify on unseen data, check bias | Evaluation report |
| 6. Deploy the Model | Serve predictions reliably | API endpoint, monitoring dashboard |

---

## Build It / In Depth

### Step 1 — Setting Objectives

Before opening a notebook, write down the answers to three questions:

1. **What decision does this model enable?** (e.g., "flag transactions for manual review")
2. **What is the cost of a wrong prediction?** (false positive vs. false negative)
3. **What metric proves the model is working in production?** (precision at k, revenue lift, churn reduction %)

Treat the KPI like a software contract. If you cannot state it numerically, you cannot know when you are done.

Run a **feasibility check** before spending any compute:
- Is there enough labeled data? (Rule of thumb: 10× the number of features for classical ML; millions of examples for deep learning)
- Is the signal strong enough? (If humans cannot predict it from the same inputs, a model probably cannot either)
- Is the latency budget compatible with real-time serving? (A 500 ms inference budget rules out many large models)

```
Feasibility matrix:
                    Data available?
                    YES         NO
Predictable? YES │ PROCEED    │ COLLECT DATA FIRST
             NO  │ RE-SCOPE   │ ABANDON
```

### Step 2 — Data Preparation

Raw data is never ready for training. The pipeline has four sub-steps:

```python
# Pseudocode for a typical data preparation pipeline
raw_df = load_raw_data(source="s3://bucket/raw/events.parquet")

# 1. Clean
clean_df = (
    raw_df
    .drop_duplicates()
    .fillna(strategy="median")          # numeric
    .fillna(strategy="most_frequent")   # categorical
    .clip(lower=p1, upper=p99)          # outlier capping
)

# 2. Feature engineering
clean_df["days_since_last_purchase"] = compute_recency(clean_df)
clean_df["purchase_freq_30d"]        = compute_frequency(clean_df)

# 3. Encode
clean_df = one_hot_encode(clean_df, columns=["country", "device"])

# 4. Split — ALWAYS split before any normalization fit
train, val, test = temporal_split(clean_df, ratios=[0.70, 0.15, 0.15])

# 5. Scale (fit ONLY on train, transform all three)
scaler = StandardScaler().fit(train[numeric_cols])
train[numeric_cols] = scaler.transform(train[numeric_cols])
val[numeric_cols]   = scaler.transform(val[numeric_cols])
test[numeric_cols]  = scaler.transform(test[numeric_cols])
```

**Critical rule:** Fit all preprocessing (scalers, encoders, imputers) only on the training set, then apply the fitted transform to val and test. Fitting on the full dataset is data leakage.

For time-series data, always use a **temporal split** — never random shuffle, which lets future information bleed into training.

### Step 3 — Choose the Algorithm

Map task type to model family first, then pick the framework.

| Task | Small data (<100k rows) | Large data | Unstructured input |
|------|-------------------------|------------|--------------------|
| Binary classification | Logistic Reg, XGBoost | XGBoost, LightGBM | Transformer, CNN |
| Multi-class | Random Forest, XGBoost | LightGBM | Transformer |
| Regression | Ridge, XGBoost | XGBoost, MLP | Transformer |
| Ranking | LambdaMART | LightGBM LAMBDARANK | BERT + linear head |
| Clustering | K-Means, DBSCAN | Mini-batch K-Means | UMAP + HDBSCAN |
| Generation | N/A | GPT-family, T5 | LLM |

**Framework selection:**
- **scikit-learn** — classical ML, quick baselines, built-in pipelines
- **XGBoost / LightGBM** — tabular data, competitions, production gradient boosting
- **PyTorch** — research, custom architectures, dynamic computation graphs
- **TensorFlow / Keras** — production serving (TF Serving), mobile (TFLite)
- **Hugging Face Transformers** — NLP, vision transformers, pre-trained backbones

Start with the simplest model that could plausibly work. A well-tuned logistic regression baseline is your benchmark — everything more complex must beat it to justify the added complexity.

### Step 4 — Train the Model

Training has two nested loops: the gradient descent loop (handled by the framework) and the hyperparameter search loop (your responsibility).

```python
import optuna
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score

def objective(trial):
    params = {
        "n_estimators":   trial.suggest_int("n_estimators", 100, 1000),
        "max_depth":      trial.suggest_int("max_depth", 3, 8),
        "learning_rate":  trial.suggest_float("learning_rate", 1e-3, 0.3, log=True),
        "subsample":      trial.suggest_float("subsample", 0.6, 1.0),
    }
    model = GradientBoostingClassifier(**params)
    model.fit(X_train, y_train)
    return roc_auc_score(y_val, model.predict_proba(X_val)[:, 1])

study = optuna.create_study(direction="maximize")
study.optimize(objective, n_trials=50)
best_params = study.best_params
```

Log every training run. At minimum, track: hyperparameters, training metrics per epoch/iteration, validation metrics, and the git commit hash of the training code. Tools like MLflow or Weights & Biases make this trivial.

**Regularization signals to watch:**
- Large gap between training and validation metric → overfitting → increase regularization or add more data
- Both train and val metrics are poor → underfitting → increase model capacity or improve features

### Step 5 — Evaluate and Test

Never report accuracy on the training set. Report on the **held-out test set** — the data the model has never seen in any form.

```
Evaluation checklist:
□ Primary metric on test set meets the KPI from Step 1
□ Confusion matrix reviewed (not just accuracy)
□ Performance segmented by key subgroups (age, region, product category)
□ Feature importance inspected for data leakage signals
□ Model behavior on edge cases and adversarial inputs checked
□ Bias audit: does performance drop significantly for any protected group?
```

Choose metrics appropriate to class imbalance:

| Situation | Prefer |
|-----------|--------|
| Balanced classes | Accuracy, F1 |
| Imbalanced (rare positive) | Precision-Recall AUC, F1 |
| Ranking quality | NDCG, MAP |
| Regression | RMSE, MAE, MAPE |
| Business impact | Revenue lift, retention delta |

A model that achieves 99% accuracy on a 1% positive rate dataset by predicting "no" every time is worthless. Always check the baseline: how does a naive predictor (always-positive, always-negative, or random) compare?

### Step 6 — Deploy the Model

Deployment has three concerns: **serving**, **packaging**, and **monitoring**.

**Serving options:**

```
Request → Load Balancer
              │
    ┌─────────┴──────────┐
    │                    │
 Batch                Real-time
(cron job,           (REST API,
 Spark job)          gRPC, streaming)
    │                    │
 S3/DB output        Model Server
                    (TF Serving,
                     Triton,
                     FastAPI)
```

**Packaging with Docker:**

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY model_artifacts/ ./model_artifacts/
COPY serve.py .

EXPOSE 8080
CMD ["uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8080"]
```

**Minimal FastAPI serving endpoint:**

```python
from fastapi import FastAPI
from pydantic import BaseModel
import joblib, numpy as np

app   = FastAPI()
model = joblib.load("model_artifacts/model.pkl")
scaler = joblib.load("model_artifacts/scaler.pkl")

class Features(BaseModel):
    days_since_purchase: float
    purchase_freq_30d:   float
    total_spend:         float

@app.post("/predict")
def predict(features: Features):
    X = np.array([[features.days_since_purchase,
                   features.purchase_freq_30d,
                   features.total_spend]])
    X_scaled = scaler.transform(X)
    prob = model.predict_proba(X_scaled)[0, 1]
    return {"churn_probability": round(float(prob), 4)}
```

**Monitor three things in production:**
1. **Data drift** — input feature distributions shifting from training distribution (use KL divergence or Population Stability Index)
2. **Prediction drift** — score distributions shifting without a corresponding label shift
3. **Outcome metrics** — the business KPI you defined in Step 1 (the ground truth, with delay)

---

## Use It

| Scenario | Tooling |
|----------|---------|
| Tabular classification, fast iteration | scikit-learn + XGBoost + MLflow |
| Large-scale training on cloud | SageMaker Training Jobs / Vertex AI Custom Training |
| Experiment tracking | MLflow, Weights & Biases, Neptune |
| Hyperparameter search | Optuna, Ray Tune, SageMaker Automatic Model Tuning |
| Model registry & versioning | MLflow Model Registry, Hugging Face Hub |
| Online serving | FastAPI + Docker, TensorFlow Serving, Triton Inference Server |
| Batch scoring | Apache Spark MLlib, SageMaker Batch Transform |
| Feature store | Feast, Tecton, SageMaker Feature Store |
| Drift monitoring | Evidently AI, WhyLabs, Fiddler |

---

## Common Pitfalls

- **Data leakage through the split.** Fitting a scaler or imputer on the entire dataset before splitting is one of the most common mistakes. It inflates validation metrics and produces a model that cannot generalize. Always split first, fit preprocessing on train only.

- **Optimizing the wrong metric.** Maximizing accuracy on an imbalanced dataset is meaningless. Define the metric in Step 1 and hold to it — do not switch metrics when the numbers look bad.

- **Training–serving skew.** The feature computation in the training pipeline (Step 2) and the serving pipeline (Step 6) diverge over time. Mismatched null handling, different timezone conventions, or slightly different aggregation windows produce silent performance degradation. Use a shared feature store or publish the preprocessing as a versioned artifact that both pipelines consume.

- **No baseline comparison.** Reporting 85% accuracy means nothing without comparing to a trivial baseline (e.g., always-predict-majority: 82%). Always report relative to a naive predictor.

- **Skipping bias evaluation.** A model that performs well on average can perform significantly worse on specific subgroups. Evaluate performance broken down by protected and business-critical segments before shipping. Disparate performance is a legal risk in regulated industries.

---

## Exercises

1. **Easy — Define KPIs for a spam filter.** Given a binary email spam classifier, write down three KPIs (use specific metric names) that would tell you the model is production-ready. Explain why accuracy alone is insufficient.

2. **Medium — Identify the leakage.** You are given a dataset of loan applications. The columns include `loan_status` (the label), `application_date`, `credit_score`, `annual_income`, and `days_to_default`. A teammate builds a model using all five columns and reports 97% AUC. What is wrong and how do you fix it?

3. **Hard — Design a full pipeline.** Sketch the end-to-end ML system (Steps 1–6) for a real-time product recommendation engine serving 10,000 requests per second. Address: feature computation latency, model size constraints, A/B testing strategy, and monitoring. Identify which steps require online vs. offline components.

---

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|------------------------|
| Overfitting | The model is too complex | The model memorizes training data and fails to generalize; training metric >> validation metric |
| Hyperparameter | A parameter the model learns | A setting you choose before training (learning rate, tree depth); not learned from data |
| Data leakage | Accidentally including secret test labels | Any flow of information from the future or from the test set into the training process, inflating validation metrics |
| Model drift | The model gets worse over time | The statistical relationship between inputs and outputs changes in production, reducing prediction quality |
| Feature store | A database of ML features | A centralized repository that computes, stores, and serves features consistently for both training and serving pipelines |
| Recall | How accurate the model is | The fraction of actual positives the model correctly identified; high recall = few false negatives |
| Bias (ML) | The model is racist | Systematic error from flawed assumptions in the learning algorithm OR disparate performance across demographic groups |

---

## Further Reading

- [Google's Rules of Machine Learning](https://developers.google.com/machine-learning/guides/rules-of-ml) — Martin Zinkevich's 43 production rules distilled from Google's ML practice; read before building anything in production.
- [Scikit-learn: Cross-validation and model evaluation](https://scikit-learn.org/stable/modules/cross_validation.html) — authoritative reference for train/val/test splits, cross-validation strategies, and metric selection.
- [MLflow documentation](https://mlflow.org/docs/latest/index.html) — covers experiment tracking, model packaging, model registry, and deployment patterns end to end.
- [Evidently AI documentation](https://docs.evidentlyai.com/) — practical guide for data drift detection and model monitoring in production; includes ready-to-run reports.
- [Chip Huyen, *Designing Machine Learning Systems* (O'Reilly, 2022)](https://www.oreilly.com/library/view/designing-machine-learning/9781098107956/) — the most comprehensive single-source treatment of the full ML lifecycle, from problem framing through production monitoring.
