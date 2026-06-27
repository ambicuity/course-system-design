# CI/CD Simplified Visual Guide

> Ship faster by making deployment so routine it becomes boring.

**Type:** Learn
**Prerequisites:** Version Control Basics, System Design Fundamentals, Microservices Overview
**Time:** ~30 minutes

---

## The Problem

Imagine a team of twelve engineers all pushing code to a monolithic e-commerce service. On release day, someone merges a feature branch that has been sitting for three weeks. Integration takes four hours of manual conflict resolution. The deploy runs at midnight because everyone is afraid of daytime outages. Half the time something breaks in production that worked fine on a laptop. The team spends more energy managing deployments than building features.

This is the pre-CI/CD world. Without automation, integration is an event — painful, infrequent, and risky. The longer you wait between integrations, the larger the delta, the harder the debugging, and the worse the blast radius when something goes wrong. Human-operated deployment checklists introduce inconsistency: one engineer skips a migration step, another deploys the wrong tag, a third forgets to warm the cache.

CI/CD fixes this by turning integration and deployment into a continuous, automated, auditable process. Instead of deploying once a week in a war-room ceremony, teams deploying with mature CI/CD push dozens of times a day with confidence, because each change is small, automatically verified, and reversible.

---

## The Concept

### Continuous Integration vs. Continuous Delivery vs. Continuous Deployment

All three terms share the "CD" abbreviation but mean different things:

| Term | What it means | Human gate? |
|---|---|---|
| **Continuous Integration (CI)** | Merge code frequently; run automated tests on every push | No gate on integration |
| **Continuous Delivery (CD)** | Every passing build is *releasable* to production at any moment | Manual approval before production |
| **Continuous Deployment (CD)** | Every passing build is *automatically released* to production | No gate — fully automated |

Most companies live between Continuous Delivery and Continuous Deployment. They automate everything up to production, but a human clicks "approve" before the final push. Startups and mature platform teams often go all the way to Continuous Deployment.

### The Pipeline Mental Model

A CI/CD pipeline is a directed graph of stages. Each stage transforms an artifact (source code → container image → deployed workload) and gates the next stage on success.

```
Developer pushes to Git
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│  CI PHASE                                                 │
│                                                           │
│  [Source] → [Build] → [Unit Tests] → [Integration Tests]  │
│                              │                            │
│                         (fail fast)                       │
└───────────────────┬───────────────────────────────────────┘
                    │ Artifact (container image, JAR, etc.)
                    ▼
┌───────────────────────────────────────────────────────────┐
│  CD PHASE                                                 │
│                                                           │
│  [Staging Deploy] → [Smoke/E2E Tests] → [Approval Gate?]  │
│                                               │           │
│                                         [Production]      │
└───────────────────────────────────────────────────────────┘
```

### The Four Key Principles

**1. Build once, deploy everywhere.** Compile or package the artifact once at CI time. Promote that exact binary through staging and into production. Never rebuild from source for production. Rebuilding introduces non-determinism (dependency drift, environment differences).

**2. Fail fast.** Put the cheapest, fastest checks first. Unit tests run in seconds; integration tests take minutes; E2E tests can take an hour. Order them cheapest → most expensive. A pipeline that spends 20 minutes before running unit tests wastes engineering time.

**3. Everything is code.** Pipeline definitions, deployment manifests, environment configs — all live in version control alongside application code. This is called *pipeline as code* (GitHub Actions YAML, Jenkinsfile, GitLab CI YAML). It makes pipelines auditable, reviewable, and reproducible.

**4. Short-lived branches.** CI only works if developers integrate frequently. Feature flags let you merge incomplete code without exposing it. Trunk-based development (all commits to `main` or short-lived branches merged within a day or two) is the natural complement to CI.

### Artifact Promotion Flow

```
Code commit
    │
    ▼
Build image → tag: sha-abc123
    │
    ▼
Push to registry (dev tag)
    │
    ▼
Deploy to DEV env → automated tests pass
    │
    ▼
Promote same image → retag: staging-abc123
    │
    ▼
Deploy to STAGING → smoke tests + QA approval
    │
    ▼
Promote same image → retag: prod-abc123 / v1.4.2
    │
    ▼
Deploy to PRODUCTION → canary → 100% traffic
```

The image never changes — only the tag (alias) changes. This is the guarantee that what you tested is what you shipped.

---

## Build It / In Depth

### A Minimal GitHub Actions Pipeline

The following pipeline runs on every push to `main`. It builds a Docker image, runs tests, and pushes to a registry. This is production-usable as a starting point.

```yaml
# .github/workflows/ci-cd.yml
name: CI/CD Pipeline

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run unit tests
        run: pytest tests/unit -v --tb=short

      - name: Run integration tests
        run: pytest tests/integration -v --tb=short

  build-and-push:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'  # Only on main, not PRs
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - name: Log in to registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest

  deploy-staging:
    needs: build-and-push
    runs-on: ubuntu-latest
    environment: staging  # Requires environment protection rules in GitHub

    steps:
      - name: Deploy to staging
        run: |
          # Example: update a Kubernetes deployment
          kubectl set image deployment/app \
            app=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
        env:
          KUBECONFIG: ${{ secrets.STAGING_KUBECONFIG }}

  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment: production  # Requires manual approval in GitHub Environments

    steps:
      - name: Deploy to production
        run: |
          kubectl set image deployment/app \
            app=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
        env:
          KUBECONFIG: ${{ secrets.PROD_KUBECONFIG }}
```

### Stage Breakdown

```
┌──────────────┬───────────────┬────────────────────────────────────────┐
│ Stage        │ Typical time  │ What it gates                          │
├──────────────┼───────────────┼────────────────────────────────────────┤
│ Lint         │ 10-30 sec     │ Style, static analysis, secret scanning│
│ Unit tests   │ 30 sec - 2 min│ Pure logic, no I/O                     │
│ Build        │ 1-5 min       │ Compilable, image buildable            │
│ Integration  │ 2-10 min      │ DB, queue, network contract            │
│ Security scan│ 1-3 min       │ CVE check on dependencies + image      │
│ E2E / smoke  │ 5-20 min      │ Critical user paths work               │
│ Staging gate │ Manual/auto   │ Functional correctness in prod-like env│
│ Production   │ 2-10 min      │ Rolling deploy + health checks         │
└──────────────┴───────────────┴────────────────────────────────────────┘
```

### Canary Deployment Pattern

Rather than shipping to 100% of traffic at once, a canary routes a small slice to the new version first:

```
Traffic split during canary:

 Users ───► Load Balancer
                 │
         ┌───── ┴ ──────┐
         │ 95%           │ 5%
         ▼               ▼
    [v1.4.1 pods]   [v1.4.2 pods]  ← watch error rate, latency
         │               │
         │   If OK after N minutes:
         │               │
         ▼               ▼
    [drain]         [100% traffic]
```

If error rate or latency spikes in the canary slice, the pipeline automatically rolls back by shifting traffic back to v1.4.1.

---

## Use It

### CI/CD Tools and When to Reach for Each

| Tool | Best for | Hosted / Self-hosted | Key strength |
|---|---|---|---|
| **GitHub Actions** | Teams already on GitHub | Hosted (GitHub runners) | Tight git integration, large marketplace |
| **GitLab CI/CD** | GitLab monorepos, compliance-heavy orgs | Both | Auto DevOps, built-in security scanning |
| **Jenkins** | Legacy enterprise, heavy customization | Self-hosted | Massive plugin ecosystem, full control |
| **CircleCI** | Fast feedback loops, Docker-heavy workloads | Hosted + self-hosted | Parallelism, caching primitives |
| **Tekton** | Kubernetes-native pipelines | Self-hosted (K8s) | Cloud-native, pipeline as CRDs |
| **ArgoCD** | GitOps continuous delivery on Kubernetes | Self-hosted | Declarative sync, drift detection |
| **Spinnaker** | Multi-cloud, large-scale CD | Self-hosted | Sophisticated deployment strategies |

**Rule of thumb:**
- Starting out on GitHub → **GitHub Actions**, period.
- Need GitOps on Kubernetes → **ArgoCD** for CD, any CI tool upstream.
- Regulated industry needing on-prem → **GitLab CI** self-managed or **Jenkins**.
- Already deep in AWS → **AWS CodePipeline + CodeBuild** to stay in the ecosystem.

### Feature Flags as a CI/CD Complement

Feature flags decouple deployment from release. You deploy code to 100% of users but the feature is toggled off. Turn it on gradually:

```
Deploy → 0% users see feature → 1% → 10% → 50% → 100%
                                  ↑
                          monitor metrics, rollback flag if issues
```

Tools: **LaunchDarkly**, **Flagsmith** (open-source), **Unleash**, or a simple Redis-backed flag service.

---

## Common Pitfalls

- **Testing in CI but not in an environment that mirrors production.** Unit tests pass but integration tests run against an in-memory SQLite while production uses PostgreSQL 15 with specific extensions. Keep environments parity-close using Docker Compose or Testcontainers.

- **Building the artifact multiple times.** Teams rebuild from source for staging and again for production. Two builds from the same commit can produce different binaries if dependencies float (no lockfile) or if build machines differ. Build once, tag and promote the same image.

- **Long-lived branches invalidating "Continuous" in CI.** A branch that lives for two weeks before merging has already defeated the purpose of continuous integration. The merge itself becomes a high-risk integration event. Enforce short-lived branches and use feature flags to ship incomplete features safely.

- **Secrets in pipeline YAML or environment variables logged to stdout.** A `echo $DATABASE_PASSWORD` during debugging gets committed and printed in CI logs. Use a secrets manager (Vault, AWS Secrets Manager, GitHub Actions Secrets) and mask values at the runner level.

- **No rollback strategy.** Deploying to production without a tested rollback path means any bad deploy requires a hotfix commit, another CI run, and another deploy cycle — sometimes 30-60 minutes of downtime. Build rollback into the pipeline: either a previous-image repoint in Kubernetes or a blue/green swap.

---

## Exercises

1. **Easy — Draw the pipeline.** Take a project you know (even a personal side project). Sketch the CI/CD pipeline on paper or in a text diagram: what stages would run, in what order, and which environment does each stage deploy to? Identify which stages run on pull requests vs. only on merges to `main`.

2. **Medium — Add a security gate.** Extend the GitHub Actions pipeline from the Build It section to include a Trivy container scan step that runs after the image is built and fails the pipeline if any CRITICAL CVEs are found. Research the `aquasecurity/trivy-action` marketplace action.

3. **Hard — Design a zero-downtime deployment strategy.** A monolithic Rails app runs on three EC2 instances behind an ALB. You need to deploy new code with zero downtime and a tested rollback path. Design the full pipeline: CI stages, artifact type, deployment strategy (rolling / blue-green / canary), health check definition, rollback trigger, and how you would verify rollback actually works. Write the design as a short technical doc with a diagram.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Continuous Integration** | Running tests automatically | Merging code to a shared branch *frequently* (multiple times per day) with automated checks to detect conflicts early |
| **Continuous Deployment** | Just automating deploys | Every commit that passes all automated gates is shipped to production *without human approval* |
| **Pipeline** | A sequence of steps | A directed acyclic graph of stages where each stage gates the next; parallel stages are common and desirable |
| **Artifact** | Any build output | The single, immutable, versioned output (image, JAR, binary) built once and promoted through environments without rebuilding |
| **Canary release** | A risky beta test | A controlled traffic split that exposes a small percentage of real users to the new version while monitoring for regressions |
| **Feature flag** | A configuration option | A runtime toggle that decouples *deployment* (code is in production) from *release* (users can see the feature) |
| **Trunk-based development** | Everyone pushes to main | A branching strategy where all developers integrate to a single shared branch frequently, enabling true CI |

---

## Further Reading

- [GitHub Actions Official Documentation](https://docs.github.com/en/actions) — The authoritative reference for workflow syntax, runner environments, secrets, and environment protection rules.
- [Google's SRE Book — Chapter on Release Engineering](https://sre.google/sre-book/release-engineering/) — How Google approaches build systems, deployment automation, and the philosophy behind treating release engineering as a first-class discipline.
- [Continuous Delivery by Jez Humble and David Farley](https://continuousdelivery.com/) — The canonical book on CD practices; the companion website hosts key concepts and patterns.
- [ArgoCD Documentation — GitOps Guide](https://argo-cd.readthedocs.io/en/stable/) — Best reference for Kubernetes-native GitOps delivery, including sync strategies, health checks, and rollback.
- [DORA Metrics — DevOps Research and Assessment](https://dora.dev/guides/dora-metrics-four-keys/) — The four key metrics (deployment frequency, lead time for changes, change failure rate, time to restore service) that quantify CI/CD maturity and predict organizational performance.
