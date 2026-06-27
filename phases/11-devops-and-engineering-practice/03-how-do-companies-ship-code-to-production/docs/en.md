# How Do Companies Ship Code to Production?

> Getting code from a developer's laptop to millions of users is an engineering problem, not just a deployment step.

**Type:** Learn
**Prerequisites:** CI/CD Fundamentals, Container Basics (Docker), Version Control with Git
**Time:** ~25 minutes

---

## The Problem

A startup with three engineers can deploy by running a script on a Friday afternoon. A company with 300 engineers cannot. Without a structured shipping process, any one of these will happen routinely: a developer pushes a bug that breaks production for all users, two teams overwrite each other's changes, a "tested" feature in staging fails immediately in production, or a rollback takes 45 minutes while the incident burns.

The deeper issue is coordination. Code is written by many people, touching many services, on many branches, at the same time. Each change needs to be integrated with everyone else's changes, proven safe, packaged reproducibly, and delivered to an environment that mirrors production — all before a human ever clicks "deploy." The process also needs to be repeatable, auditable, and fast enough that engineers actually use it instead of working around it.

Understanding the production shipping pipeline means you can design systems that support continuous delivery, diagnose failures at the right layer, and reason about the trade-offs between speed, safety, and cost.

---

## The Concept

The standard path from developer intent to production runs through three broad phases: **plan → integrate → deliver**. Most companies formalize this as a pipeline that gate-keeps each stage.

```
 PLAN          INTEGRATE                          DELIVER
┌──────┐   ┌─────────────────────────────────┐   ┌─────────────────────────┐
│Jira /│   │  CI Pipeline                    │   │  CD Pipeline            │
│Linear│──▶│  commit → build → test → scan  │──▶│  dev → QA → UAT → prod │
└──────┘   └─────────────────────────────────┘   └─────────────────────────┘
               ▲                                         │
               │  artifact stored in registry            │ same artifact promoted
               └────────────────────────────────────────┘
```

### Phase 1: Planning (Backlog → Sprint)

Work originates as user stories or tickets (Jira, Linear, GitHub Issues). Sprint planning converts a prioritized backlog into a time-boxed commitment. Every piece of work that enters the pipeline starts as a ticket ID, which becomes the branch name, the PR title, and eventually the tag in your audit log.

### Phase 2: Continuous Integration (CI)

Every push to a branch triggers the CI pipeline. The pipeline is the automated enforcer of code quality. A canonical CI run does four things in this order:

| Step | Purpose | Fails if |
|---|---|---|
| **Build** | Compile or bundle the code | Syntax errors, missing deps |
| **Unit/integration tests** | Verify logic in isolation | Test assertions fail |
| **Code quality scan** | Enforce style, coverage, security | Coverage drops below threshold, known CVE found |
| **Artifact packaging** | Produce a deployable image/jar/binary | Build tooling error |

The artifact (Docker image, JAR, tarball) is pushed to a registry (JFrog Artifactory, AWS ECR, GitHub Packages) with an immutable tag — typically the Git SHA or a semantic version. Critically, **the artifact is built once** and promoted through environments. You never rebuild from source for staging vs. production; you promote the same bits.

### Phase 3: Continuous Delivery / Deployment (CD)

Once the artifact exists, the delivery pipeline promotes it through a chain of environments, each with higher fidelity to production:

```
artifact in registry
       │
       ▼
  ┌─────────┐    auto-deploy     ┌────────────┐    auto-deploy     ┌──────────┐    manual gate    ┌──────────┐
  │   Dev   │ ─────────────────▶ │  QA / Test │ ─────────────────▶ │   UAT    │ ─────────────────▶ │   Prod   │
  │ (latest)│                    │(per-team)  │                    │(staging) │                    │          │
  └─────────┘                    └────────────┘                    └──────────┘                    └──────────┘
                                  regression,                       user acceptance                monitoring
                                  perf tests                        sign-off                       alerts
```

**Dev** is for developers — usually auto-deployed on merge to the main branch. Multiple teams often need isolated QA environments, so these are ephemeral: spun up per pull request, destroyed after merge. **UAT** is a production-mirror for business stakeholders to sign off. **Production** is the real thing, deployed on a defined schedule (often with a change window) or via progressive delivery (canary / blue-green).

### The Gatekeeper Model

Each environment transition is a gate. A gate can be:
- **Automated** — tests pass, no severity-1 alerts, coverage threshold met.
- **Manual** — a QA lead marks the ticket resolved, a product owner approves.
- **Time-based** — deploys are batched into a release window.

Most mature orgs use automated gates for dev→QA and QA→UAT, and a manual approval plus time window for UAT→prod.

---

## Build It / In Depth

Walk through a realistic end-to-end pipeline for a Java Spring Boot service using GitHub Actions and Kubernetes.

### 1. Developer Workflow

```bash
# Branch off a ticket
git checkout -b feature/PAY-1234-add-refund-endpoint

# Work, commit
git add src/payments/RefundController.java
git commit -m "feat(payments): add POST /refunds endpoint (PAY-1234)"

# Push — triggers CI
git push origin feature/PAY-1234-add-refund-endpoint
```

### 2. CI Pipeline (`.github/workflows/ci.yml`)

```yaml
name: CI

on:
  push:
    branches: ["feature/**", "main"]
  pull_request:
    branches: ["main"]

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up JDK 21
        uses: actions/setup-java@v4
        with:
          java-version: "21"
          distribution: "temurin"

      - name: Build and test
        run: ./mvnw verify              # compiles, runs unit + integration tests

      - name: SonarQube scan
        run: ./mvnw sonar:sonar
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}

      - name: Build Docker image
        run: |
          IMAGE=payments-service:${{ github.sha }}
          docker build -t $IMAGE .

      - name: Push to registry
        run: |
          echo "${{ secrets.REGISTRY_TOKEN }}" | docker login registry.example.com -u ci --password-stdin
          docker push registry.example.com/payments-service:${{ github.sha }}
```

Key decisions here:
- The image tag is the Git SHA. This makes every image traceable to an exact commit.
- SonarQube runs in the CI job; a quality gate failure blocks the pipeline.
- The artifact is pushed before any deployment step runs.

### 3. Deploy to Dev (on merge to `main`)

```yaml
  deploy-dev:
    needs: build-and-test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - name: Update Kubernetes manifest
        run: |
          kubectl set image deployment/payments-service \
            payments-service=registry.example.com/payments-service:${{ github.sha }} \
            --namespace=dev
```

### 4. QA Promotion — Ephemeral Environments

Many teams use Helm or ArgoCD to spin up isolated namespaces per PR:

```bash
# ArgoCD App-of-Apps creates a namespace per PR number
argocd app create payments-pr-1234 \
  --repo https://github.com/example/payments-service \
  --revision feature/PAY-1234-add-refund-endpoint \
  --dest-namespace qa-pr-1234 \
  --helm-set image.tag=$GIT_SHA
```

The QA team runs regression tests against `https://payments.qa-pr-1234.internal`. On merge, the namespace is deleted.

### 5. UAT and Production Promotion

After QA sign-off, the artifact SHA is promoted:

```bash
# Retag the same SHA as a release candidate
docker pull registry.example.com/payments-service:abc1234
docker tag registry.example.com/payments-service:abc1234 \
            registry.example.com/payments-service:v2.5.0
docker push registry.example.com/payments-service:v2.5.0

# Deploy to UAT
helm upgrade payments-service ./chart \
  --namespace uat \
  --set image.tag=v2.5.0

# After UAT sign-off: promote to prod with a canary
kubectl argo rollouts set image payments-rollout \
  payments-service=registry.example.com/payments-service:v2.5.0
```

### 6. Production Monitoring Gate

Post-deployment, SRE tooling watches key metrics for a burn-in window (typically 10–30 minutes):

```
Prometheus alert rule:
  - alert: PaymentsErrorRateHigh
    expr: rate(http_requests_total{status=~"5..",service="payments"}[5m]) > 0.01
    for: 2m
    annotations:
      summary: "Error rate above 1% — consider rollback"
```

If the alert fires during the burn-in window, automated rollback triggers or an on-call engineer acts on the PagerDuty page.

---

## Use It

### Tools at Each Stage

| Stage | Common Tools | When to reach for each |
|---|---|---|
| Planning | Jira, Linear, GitHub Issues | Jira for large orgs with compliance needs; Linear for speed |
| Source control | GitHub, GitLab, Bitbucket | GitHub dominates; GitLab if you want everything self-hosted |
| CI engine | GitHub Actions, Jenkins, CircleCI, GitLab CI | Actions for GitHub-native; Jenkins for legacy enterprise |
| Quality scan | SonarQube, Semgrep, Snyk | SonarQube for coverage + smells; Snyk for dependency CVEs |
| Artifact registry | JFrog Artifactory, AWS ECR, GHCR | ECR if on AWS; GHCR for GitHub-native; Artifactory in enterprise |
| CD / GitOps | ArgoCD, Flux, Spinnaker | ArgoCD for Kubernetes GitOps; Spinnaker for multi-cloud |
| Progressive delivery | Argo Rollouts, Flagger, LaunchDarkly | Argo Rollouts for canary in k8s; LaunchDarkly for feature flags |
| Monitoring | Prometheus + Grafana, Datadog, ELK | Prometheus for metrics; ELK for logs; Datadog for unified SaaS |

### Deployment Strategies Compared

| Strategy | Risk | Rollback speed | Traffic split |
|---|---|---|---|
| Recreate | High (downtime) | Instant (old version re-deploy) | 0% → 100% |
| Rolling update | Medium | Slow (reverse rolling) | Gradual |
| Blue/Green | Low | Instant (swap LB target) | 0% or 100% |
| Canary | Very low | Instant (remove canary) | 1–10% → 100% |
| Feature flag | Near zero | Instant (flip flag) | Configurable per user |

For stateless web services, blue/green or canary are the industry standard. Feature flags complement these by decoupling deployment from release.

---

## Common Pitfalls

- **Building the artifact multiple times.** Some teams build in CI, rebuild in the QA deploy step, rebuild again for production. The "same" code can produce different binaries across environments (dep versions, compiler flags). Build once, promote the SHA.

- **Skipping the QA environment for "small" changes.** A one-line config change took down a major e-commerce platform's checkout for two hours. Every change, regardless of size, must go through the full pipeline. Small changes fail in boring, unexpected ways.

- **Long-lived feature branches.** Branches that live more than a day or two accumulate merge conflicts and integration risk. The longer the branch, the harder the merge, and the more likely the CI pipeline is testing code that is already out of date with main. Prefer trunk-based development with short-lived branches and feature flags.

- **No rollback plan.** Deploying without a tested rollback path is gambling. Before every production deployment, verify that the rollback procedure is documented, the previous artifact is still in the registry, and at least one engineer knows how to execute it.

- **Treating monitoring as optional post-launch.** Alerts should be configured and tested before the first production deployment, not after the first incident. If you cannot observe the deployment's impact within two minutes, you are flying blind.

---

## Exercises

1. **Easy** — Draw the pipeline stages for a simple REST API from "developer pushes code" to "feature is live in production." Label each gate (automated vs. manual) and identify what artifact passes between stages.

2. **Medium** — A team is running a monolith with a weekly deployment window. They want to move to daily deployments. Identify the three biggest risks in their current process and explain how you would restructure their pipeline to enable daily deploys safely.

3. **Hard** — Design a pipeline for a payments service that must satisfy: (a) zero downtime deployments, (b) a 1% canary with automatic rollback on error rate spike, (c) audit log of every deployment with the approving engineer, (d) compliance requirement that no single engineer can approve their own change to production. Specify the tools, gates, and automation scripts required.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **CI (Continuous Integration)** | "Run tests on push" | Automatically integrating every developer's work into a shared mainline multiple times a day, with an automated pipeline that builds and verifies each integration |
| **CD (Continuous Delivery)** | Same as CI | The automated pipeline that takes a verified artifact from CI and deploys it through environments up to a production-ready state; a human still approves the final push |
| **Continuous Deployment** | What CD stands for | A variant of CD where even the production promotion is automated — no manual approval gate |
| **Artifact** | The source code | An immutable, versioned, deployable package (Docker image, JAR, binary) produced once by CI and promoted through environments unchanged |
| **Environment promotion** | Re-deploying code to a new server | Deploying the exact same artifact (identified by its SHA tag) to a higher-fidelity environment without rebuilding |
| **Feature flag** | A config toggle | A runtime gate that decouples deployment (code is in production) from release (users can see it); enables dark launches and instant rollback without redeployment |
| **UAT (User Acceptance Testing)** | A QA environment with extra steps | A production-mirror environment where business stakeholders verify a feature against real acceptance criteria before it reaches actual users |

---

## Further Reading

- [Google SRE Book — Chapter 8: Release Engineering](https://sre.google/sre-book/release-engineering/) — canonical reference on how Google structures production releases
- [The Twelve-Factor App — Build, Release, Run](https://12factor.net/build-release-run) — foundational principles for separating build from release from runtime
- [Argo Rollouts Documentation](https://argoproj.github.io/argo-rollouts/) — practical reference for canary and blue/green deployments on Kubernetes
- [Accelerate (DORA Research)](https://dora.dev/research/) — data-backed metrics (deployment frequency, lead time, MTTR, change failure rate) that define elite engineering performance
- [Martin Fowler — Continuous Integration](https://martinfowler.com/articles/continuousIntegration.html) — the original, still-relevant definition and rationale for CI practices
