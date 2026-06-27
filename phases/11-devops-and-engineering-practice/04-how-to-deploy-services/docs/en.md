# How to Deploy Services

> Every deployment is a controlled bet — the strategy you choose determines how much you're willing to lose if you're wrong.

**Type:** Learn
**Prerequisites:** CI/CD Pipelines, Service Discovery, Load Balancing
**Time:** ~30 minutes

---

## The Problem

You've built a feature, tests pass locally, and CI is green. Now you need to get it into production — where real users, real data, and real traffic live. The naive approach is to stop the old version and start the new one. That works for a personal blog. It fails catastrophically for a payment service with 50,000 concurrent users.

Consider what actually goes wrong: your new binary has a subtle memory leak that only surfaces under production load. Or a database migration you ran first introduced a schema incompatibility the new code wasn't quite ready for. Or the service starts fine but one of its ten downstream dependencies is now receiving a subtly changed request format and starts returning 5xx errors. By the time your monitoring catches it, 10 minutes of traffic have hit a broken path.

The core tension in deployments is **speed vs. safety**. Deploying fast reduces the lag between code merge and user value. Deploying safely limits blast radius when something goes wrong. The deployment strategies in this lesson are different engineering answers to that tension — each making explicit trade-offs about rollout speed, infrastructure cost, rollback complexity, and observability.

---

## The Concept

### The Deployment Taxonomy

Every production deployment strategy is a combination of two orthogonal axes:

| Axis | Options |
|---|---|
| **Traffic split** | All-at-once, gradual (percentage), audience-based |
| **Environment model** | Single env, dual env, per-feature env |

Most named strategies occupy a specific cell in this space.

```
                     TRAFFIC SPLIT
                  All-at-once    Gradual
                +-------------+------------+
  Single env    | Multi-service| Rolling /  |
                |  Deployment  |  Canary    |
ENVIRONMENT  ---+-------------+------------+
  MODEL         |             |            |
  Dual env      | Blue-Green  |  A/B Test  |
                |             |  (variant) |
                +-------------+------------+
```

### Strategy 1: Multi-Service (Big Bang) Deployment

All instances of all affected services are upgraded simultaneously. This is the simplest model to implement because it requires no traffic orchestration — you just replace everything.

```
 BEFORE                 DURING                  AFTER
 -------                ------                  -----
 [v1][v1][v1]  →→→   [v2][v2][v2]    →→→   [v2][v2][v2]
      ↓                    ↓                      ↓
  (serving)          (downtime window)          (serving)
```

**When it makes sense:** Internal tooling, non-critical batch services, or tightly coupled services where running mixed versions causes correctness problems (e.g., a monolith split into microservices that share a database schema version).

**Why it's dangerous at scale:** A bad deploy takes down 100% of capacity instantly. Rollback is another big-bang deploy, meaning you double the exposure window.

### Strategy 2: Rolling Deployment

Instances are updated one at a time (or in small batches). At any given moment, both the old and new version are serving traffic. Most container orchestrators (Kubernetes, ECS) implement this by default.

```
Step 0: [v1][v1][v1][v1]   (4 instances, all old)
Step 1: [v2][v1][v1][v1]   (1 updated, load balancer routes to all)
Step 2: [v2][v2][v1][v1]   (2 updated)
Step 3: [v2][v2][v2][v1]
Step 4: [v2][v2][v2][v2]   (done)
```

**Key requirement:** Old and new versions must be able to run concurrently. This means:
- New code must tolerate old message formats (consumers in a queue)
- Schema migrations must be backward-compatible
- API contracts must be additive, not breaking

### Strategy 3: Blue-Green Deployment

Two complete, production-equivalent environments exist simultaneously. One (green) serves live traffic. The other (blue) receives the new deployment and is tested in isolation. When you're satisfied, a load balancer or DNS cutover routes 100% of traffic to blue. Blue becomes the new production; the old green stands by for instant rollback.

```
                     ┌──────────────────────┐
   Users             │     Load Balancer     │
     │               └─────────┬────────────┘
     │                         │
     │               ┌─────────▼────────────┐
     │               │  [GREEN - v1, LIVE]  │
     │               └──────────────────────┘
     │
     │               ┌──────────────────────┐
     │               │  [BLUE  - v2, IDLE]  │  ← deploy & test here
                     └──────────────────────┘

  After cutover:
     │               ┌──────────────────────┐
     │               │  [GREEN - v1, IDLE]  │  ← warm rollback target
     │               └──────────────────────┘
     │
     │               ┌──────────────────────┐
     └──────────────▶│  [BLUE  - v2, LIVE]  │
                     └──────────────────────┘
```

**Rollback:** Switch the load balancer back. Time to rollback: seconds.

**Cost:** You maintain two full production environments, meaning your infrastructure bill roughly doubles. For stateless services this is manageable; for stateful services (databases, caches) the duplication is more complex.

### Strategy 4: Canary Deployment

Named after the canary-in-a-coal-mine practice. A new version is deployed to a small subset of instances (the "canary"), and a small percentage of real traffic is routed there. If metrics look healthy, traffic gradually shifts until the canary carries 100%.

```
  Traffic Split over time:

  t=0   [v1:100%]
  t=1   [v1:99%]  [v2:1%]    ← canary starts
  t=2   [v1:90%]  [v2:10%]   ← monitoring: error rate, latency, p99
  t=3   [v1:50%]  [v2:50%]
  t=4             [v2:100%]  ← promotion
```

**What to monitor during rollout:**
- Error rate (4xx/5xx) per version
- p99 latency
- Business metrics (conversion, checkout completion)
- Memory/CPU usage

**Rollback:** Route 100% traffic back to v1 and terminate canary pods.

**Key insight:** A canary tests on real production traffic. This catches issues that staging environments never see — real user behavior, real data volumes, real downstream latency.

### Strategy 5: A/B Testing (Feature Experimentation)

A/B testing looks superficially like canary deployment but has a different purpose. In a canary, you're validating that v2 doesn't break things. In an A/B test, you're measuring which version performs *better* on a business metric. Both versions are considered production-worthy; you're comparing outcomes.

| | Canary | A/B Test |
|---|---|---|
| **Goal** | Safety validation | Business metric comparison |
| **Success signal** | No regressions | Statistically significant lift |
| **Duration** | Hours to days | Days to weeks |
| **User assignment** | Traffic % | Cohort segmentation (device, region, account age) |
| **Rollback trigger** | Error spike | Negative effect on metric |

A/B tests require consistent user assignment (the same user always sees the same variant) and statistical rigor — you need enough samples to distinguish signal from noise.

### Feature Flags: The Deployment/Release Decoupling

A powerful pattern orthogonal to all of the above: **deploy code dark, release it separately**. Feature flags let you ship inactive code to production and toggle features on via configuration — without a new deployment.

```
# Service code (already in production)
if feature_flag("new_checkout_flow", user_id):
    return new_checkout(cart)
else:
    return old_checkout(cart)
```

This separates the deployment risk (shipping code) from the release risk (exposing it to users). It also enables instant rollback without a new deploy: flip the flag. Tools like LaunchDarkly, Unleash, and Flipt implement this pattern at scale.

---

## Build It / In Depth

### Implementing a Canary Deployment with Kubernetes

A real canary deployment uses Kubernetes Deployments and a Service selector to split traffic by instance count.

**Step 1: Current stable deployment (v1)**

```yaml
# stable-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-stable
  labels:
    app: api
    track: stable
spec:
  replicas: 9
  selector:
    matchLabels:
      app: api
      track: stable
  template:
    metadata:
      labels:
        app: api
        track: stable
    spec:
      containers:
        - name: api
          image: myregistry/api:v1
```

**Step 2: Deploy the canary alongside it (v2)**

```yaml
# canary-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-canary
  labels:
    app: api
    track: canary
spec:
  replicas: 1        # ~10% of traffic (1 of 10 total pods)
  selector:
    matchLabels:
      app: api
      track: canary
  template:
    metadata:
      labels:
        app: api
        track: canary
    spec:
      containers:
        - name: api
          image: myregistry/api:v2
```

**Step 3: A single Service routes to both by matching only the shared label**

```yaml
# service.yaml
apiVersion: v1
kind: Service
metadata:
  name: api
spec:
  selector:
    app: api          # matches BOTH stable and canary pods
  ports:
    - port: 80
      targetPort: 8080
```

Traffic split = canary_pods / total_pods = 1/10 = 10%.

**Step 4: Monitor and promote**

```bash
# Check error rates during canary
kubectl logs -l app=api,track=canary --tail=100

# Scale up canary and scale down stable
kubectl scale deployment api-canary --replicas=5
kubectl scale deployment api-stable --replicas=5

# Full promotion
kubectl scale deployment api-canary --replicas=10
kubectl scale deployment api-stable --replicas=0

# Cleanup
kubectl delete deployment api-stable
```

**Step 5: Rollback if needed**

```bash
kubectl scale deployment api-stable --replicas=9
kubectl scale deployment api-canary --replicas=0
```

### Decision Flowchart: Choosing a Strategy

```
                      ┌─────────────────────────────┐
                      │  Can v1 and v2 run together? │
                      └───────────┬─────────────────-┘
                        Yes       │        No
              ┌───────────────────┘       └─────────────────────┐
              ▼                                                   ▼
 ┌─────────────────────────┐                        ┌────────────────────────┐
 │  Can you afford 2x infra? │                       │  Multi-service deploy  │
 └──────────┬──────────────┘                        │  (accept downtime or   │
     Yes    │      No                               │  do it at low-traffic) │
      ┌─────┘      └──────┐                         └────────────────────────┘
      ▼                   ▼
 Blue-Green          Canary / Rolling
      │
      └── Need business metric comparison?
               Yes → A/B Test
               No  → Blue-Green
```

---

## Use It

### Cloud & Platform Support

| Platform | Native Strategy | Configuration |
|---|---|---|
| **Kubernetes** | Rolling (default), Canary (manual or via Argo Rollouts) | `strategy.rollingUpdate` in Deployment spec |
| **AWS ECS** | Rolling, Blue-Green (via CodeDeploy) | `deploymentConfiguration` in service def |
| **AWS Lambda** | Canary / Linear traffic shifting | `DeploymentPreference` in SAM / CodeDeploy |
| **Google Cloud Run** | Traffic splitting by revision % | `gcloud run services update-traffic` |
| **Kubernetes + Argo Rollouts** | Canary, Blue-Green with analysis | `Rollout` CRD with `AnalysisTemplate` |
| **Spinnaker** | All strategies via pipeline stages | Declarative pipeline config |
| **Flagger** | Automated canary with Prometheus gates | Operator-based, works with Istio/Envoy |

### When to Reach for Each

- **Rolling:** Default for stateless services where old/new versions are compatible. Zero additional infrastructure cost.
- **Blue-Green:** When you need a staging environment that exactly mirrors production, or when instant rollback is a hard requirement (financial services, healthcare).
- **Canary:** When you want real-traffic validation before full rollout. Best paired with good observability (Datadog, Prometheus + Grafana).
- **A/B Test:** When the question is "which is better?" not "is this safe?". Requires analytics infrastructure and statistical patience.
- **Feature Flags:** Whenever you want to separate code deployment from feature release. Always worth adding for risky or experimental changes.

---

## Common Pitfalls

- **Running incompatible schema migrations before the new code is deployed.** A database column rename will break the old code that's still serving traffic during a rolling deploy. Always apply additive migrations first (add column, backfill), deploy new code, then clean up (remove old column). This is the expand/contract pattern.

- **Treating canary as a staging environment.** A canary is not for manual QA — it's for automated metric observation. If you're clicking around the canary manually, you're not doing canary deployment; you're doing blue-green on a budget.

- **Forgetting stateful dependencies in blue-green.** Switching load balancer traffic is instantaneous, but sessions stored in a cookie or JWT still reference the old environment's signing keys, database connection pool, or in-memory state. Plan for session draining or shared state stores before cutting over.

- **Defining canary success only by error rate.** A new checkout flow might have 0% error rate but a 5% drop in conversion. Always include business metrics in your promotion criteria, not just infrastructure health signals.

- **No automated rollback trigger.** A canary that requires a human to notice and manually intervene defeats much of its purpose. Wire your deployment system to Prometheus alerts or error budget burn rates so rollback fires automatically when thresholds are breached.

---

## Exercises

1. **Easy:** You have a REST API with 3 replicas behind a load balancer. Sketch the sequence of events during a rolling deployment when `maxUnavailable=1` and `maxSurge=1`. How many total pods exist at each step?

2. **Medium:** A payment service needs to deploy a new version that changes how transaction IDs are generated. Old IDs are 8 characters; new ones are 16 characters. The database column is `VARCHAR(8)`. Design a migration and deployment sequence that allows you to use canary deployment without any downtime or data corruption.

3. **Hard:** Your company runs a multi-region service (us-east-1, eu-west-1, ap-southeast-1). Design a deployment strategy that: (a) validates in one region before promoting globally, (b) uses different rollout speeds per region based on traffic volume, (c) automatically halts if p99 latency increases by more than 20% in any region, and (d) doesn't require a human approval step during off-hours. What tooling would you use and what are the failure modes?

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Blue-Green** | A staging-then-production swap | Two identical, always-on environments with traffic switched between them at the load balancer layer |
| **Canary** | A small-scale test deploy | A live traffic split where a minority of real users hit the new version while metrics are actively monitored |
| **Rolling update** | Gradually replacing servers | Replacing instances in batches, requiring old and new code to be simultaneously compatible |
| **Feature flag** | A config switch to enable features | A runtime decision point that decouples code deployment from feature release |
| **A/B test** | Same as canary | A controlled experiment comparing two variants on a business metric, with cohort-consistent assignment |
| **Rollback** | Undoing a deploy | Routing traffic back to the previous known-good version — not necessarily reverting code |
| **Expand/Contract** | A multi-step migration | The pattern of first expanding the schema (backward-compatible), deploying code, then contracting (removing old schema) |

---

## Further Reading

- [Kubernetes Deployment Strategies](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#strategy) — Official docs on `RollingUpdate` and `Recreate` strategies with all configuration fields explained.
- [Argo Rollouts](https://argoproj.github.io/rollouts/) — A Kubernetes controller that adds Blue-Green, Canary, and Analysis-based automated promotion to native Kubernetes.
- [Flagger by Weaveworks](https://flagger.app/) — Progressive delivery operator with Prometheus-gated canary analysis, works with Istio, Linkerd, and AWS App Mesh.
- [Martin Fowler — Feature Toggles](https://martinfowler.com/articles/feature-toggles.html) — The canonical reference on feature flag categories (release toggles, experiment toggles, ops toggles, permission toggles) and their operational implications.
- [Google SRE Book — Release Engineering](https://sre.google/sre-book/release-engineering/) — How Google thinks about safe, reproducible deployments at scale, including hermetic builds and canary analysis.
