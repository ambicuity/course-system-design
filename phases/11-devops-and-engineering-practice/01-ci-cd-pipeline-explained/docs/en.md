# CI/CD Pipeline Explained

> Ship faster by making every step from commit to production automatic, auditable, and repeatable.

**Type:** Learn
**Prerequisites:** Version Control Basics, System Architecture Overview, Container Fundamentals
**Time:** ~35 minutes

---

## The Problem

Imagine a team of twelve engineers each merging code once a day. Every Friday afternoon, someone manually zips the repository, SSHes into a staging server, copies the build, restarts the process, and prays. Bugs that were introduced on Monday aren't found until Thursday because no one ran the full test suite locally — it takes forty minutes. When something breaks in production, no one knows which of the week's sixty commits caused it. Rolling back means someone diffs directories by hand.

This is the pre-CI/CD world: slow, dangerous, and dependent on tribal knowledge held by the one person who "knows how deployment works." Integration risk compounds with team size. The longer you delay merging and testing, the more divergent branches become, and the more expensive conflicts get — a phenomenon called **integration hell**.

Without a pipeline, your velocity is bounded by human attention. Developers spend hours each week on tasks a machine could do in minutes: running tests, building artifacts, pushing containers, updating manifests. More critically, the feedback loop is broken. A developer commits a bug and doesn't learn about it until the next day, when the context is cold. The CI/CD pipeline collapses that loop to minutes.

---

## The Concept

A CI/CD pipeline is an automated assembly line for software changes. Every commit triggers a defined sequence of stages. Each stage either passes — letting the commit advance — or fails, stopping it and notifying the author immediately.

**CI (Continuous Integration)** is the practice of merging developer changes into a shared branch frequently and verifying each merge with an automated build and test suite. The goal is to surface integration conflicts and bugs as close to the moment they're introduced as possible.

**CD (Continuous Delivery)** extends CI: every change that passes CI is automatically packaged and placed in a state where it *can* be deployed to production with one click (or one approval). **Continuous Deployment** goes further — it removes the manual gate entirely and deploys directly to production.

```
Developer commits
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│                      CI Stage                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │  Source  │→ │  Build   │→ │   Test   │             │
│  │  Fetch   │  │ Compile  │  │  Unit /  │             │
│  │  Lint    │  │ Package  │  │  Integr  │             │
│  └──────────┘  └──────────┘  └──────────┘             │
└───────────────────────┬─────────────────────────────────┘
                        │ artifact (image / JAR / binary)
                        ▼
┌─────────────────────────────────────────────────────────┐
│                      CD Stage                           │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────┐   │
│  │  Deploy  │→ │ Smoke /  │→ │   Production       │   │
│  │ Staging  │  │  E2E     │  │  (manual gate or   │   │
│  └──────────┘  └──────────┘  │   auto-deploy)     │   │
│                               └────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### Pipeline Stages in Detail

| Stage | What Happens | Fail Means |
|---|---|---|
| **Source** | Checkout code, restore cache, install deps | Repo unreachable, broken lock file |
| **Lint / Static Analysis** | Enforce style, run SAST scanners | Style violation, known CVE in dep |
| **Build** | Compile, bundle, containerize | Syntax error, missing import |
| **Unit Tests** | Fast, isolated, no I/O | Business logic regression |
| **Integration Tests** | Real DB/cache, no external APIs | Cross-service contract break |
| **Artifact Publish** | Push image to registry, upload JAR | Registry down, auth failure |
| **Deploy Staging** | Update manifest, rolling restart | Config error, failed health check |
** E2E / Smoke Tests** | Real browser or API call against staging | User-visible regression |
| **Deploy Production** | Same method as staging, with traffic control | Health check fail → auto-rollback |

### The Feedback Loop is the Point

The entire value proposition is **speed of signal**. A pipeline that takes 40 minutes gives you 40-minute feedback. Engineers context-switch away, lose focus, and batch-process failures. A pipeline under 10 minutes keeps engineers in flow. The industry target for a healthy pipeline:

- Lint + build: **< 3 minutes**
- Unit tests: **< 5 minutes**
- Full CI (including integration): **< 10 minutes**
- Deploy to staging: **< 5 minutes after CI green**

### Artifacts, Not Source

A critical design principle: **build once, deploy everywhere**. The build stage produces an immutable, versioned artifact (Docker image, JAR, binary). Every subsequent stage — staging, canary, production — deploys that *exact same artifact*. You never rebuild from source per environment. This ensures what was tested is what runs.

```
git sha → build → image:sha256:abc123
                        │
              ┌─────────┼──────────┐
              ▼         ▼          ▼
           staging   canary   production
```

### Branching Strategy and Pipeline Triggers

| Branch / Event | Pipeline Triggered |
|---|---|
| Feature branch PR | CI only (lint, build, unit tests) |
| Merge to `main` | Full CI + deploy to staging |
| Tag `v1.2.3` | Full CI + deploy to production (with gate) |
| Scheduled (nightly) | Full E2E + security scan |
| Dependency update PR | Full CI including license check |

---

## Build It / In Depth

Let's walk through a realistic GitHub Actions pipeline for a Node.js service deployed as a Docker container to Kubernetes.

### Step 1 — Structure

```
.github/
  workflows/
    ci.yml         # runs on every PR
    cd-staging.yml # runs on merge to main
    cd-prod.yml    # runs on version tags
```

### Step 2 — CI Workflow (ci.yml)

```yaml
name: CI

on:
  pull_request:
    branches: [main]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Lint
        run: npm run lint

      - name: Unit tests
        run: npm test -- --coverage

      - name: Upload coverage
        uses: codecov/codecov-action@v4

  build-image:
    runs-on: ubuntu-latest
    needs: lint-and-test
    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        run: |
          docker build \
            --build-arg GIT_SHA=${{ github.sha }} \
            -t myapp:${{ github.sha }} .

      - name: Trivy security scan
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: myapp:${{ github.sha }}
          exit-code: '1'
          severity: 'CRITICAL'
```

### Step 3 — CD Staging (cd-staging.yml)

```yaml
name: Deploy Staging

on:
  push:
    branches: [main]

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    outputs:
      image-tag: ${{ github.sha }}
    steps:
      - uses: actions/checkout@v4

      - name: Log in to registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          push: true
          tags: ghcr.io/myorg/myapp:${{ github.sha }}

  deploy-staging:
    needs: build-and-push
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - name: Update Kubernetes manifest
        run: |
          kubectl set image deployment/myapp \
            myapp=ghcr.io/myorg/myapp:${{ github.sha }} \
            -n staging

      - name: Wait for rollout
        run: kubectl rollout status deployment/myapp -n staging --timeout=120s

      - name: Smoke test
        run: |
          curl --fail https://staging.myapp.com/health
```

### Step 4 — Production Gate (cd-prod.yml)

```yaml
name: Deploy Production

on:
  push:
    tags:
      - 'v[0-9]+.[0-9]+.[0-9]+'

jobs:
  deploy-production:
    runs-on: ubuntu-latest
    environment: production   # requires manual approval in GitHub
    steps:
      - name: Deploy to production
        run: |
          kubectl set image deployment/myapp \
            myapp=ghcr.io/myorg/myapp:${{ github.ref_name }} \
            -n production

      - name: Verify health
        run: |
          sleep 30
          curl --fail https://myapp.com/health
```

### Key Design Decisions in This Example

- `npm ci` instead of `npm install` — deterministic, reads lock file exactly, fails on mismatch.
- `needs:` creates explicit job ordering; parallel jobs where possible (lint and build could run in parallel if build does not depend on lint).
- The `environment: production` block in GitHub Actions enforces a required reviewer before deployment proceeds.
- The image tag is always the Git SHA — full traceability from production back to source commit.

---

## Use It

### CI/CD Platform Comparison

| Platform | Best For | Key Trait |
|---|---|---|
| **GitHub Actions** | GitHub-hosted repos, OSS | Native integration, marketplace actions |
| **GitLab CI/CD** | Self-hosted, compliance-heavy orgs | All-in-one, built-in container registry |
| **CircleCI** | Speed-focused teams | Fastest caching, resource classes |
| **Jenkins** | Legacy enterprise, full control | Most flexible, highest ops burden |
| **Tekton** | Kubernetes-native pipelines | CRD-based, no vendor lock-in |
| **ArgoCD** | GitOps / Kubernetes CD | Declarative, drift detection |
| **Buildkite** | Large monorepos | Elastic agents, test splitting |
| **AWS CodePipeline** | AWS-native stacks | Tight IAM/ECS/Lambda integration |

### GitOps Variant

In GitOps, the pipeline does not call `kubectl` directly. Instead, it commits a manifest change (image tag bump) to a config repository. A separate operator (ArgoCD, Flux) watches that repo and reconciles the cluster to match.

```
CI pipeline → push image → update values.yaml in config-repo
                                      │
                             ArgoCD detects drift
                                      │
                          kubectl apply (in-cluster)
```

This pattern is preferred in regulated environments because the git history of the config repo is the audit trail for every deployment.

### Deployment Strategies

| Strategy | Mechanism | Risk | Use When |
|---|---|---|---|
| **Recreate** | Kill all, then start new | High downtime | Dev/test only |
| **Rolling** | Replace instances one at a time | Low | Default stateless services |
| **Blue/Green** | Two environments, flip traffic | Low, fast rollback | Critical services |
| **Canary** | Route N% traffic to new version | Very low | High-traffic, data-sensitive |
| **Feature flags** | Deploy dark, enable per user | Near-zero | A/B testing, partial rollouts |

---

## Common Pitfalls

- **Flaky tests that don't fail the pipeline.** Teams add `continue-on-error: true` to noisy tests instead of fixing them. Over time, the pipeline loses all signal value. Every flaky test is a debt item; quarantine it explicitly and schedule a fix.

- **Rebuilding from source per environment.** If staging deploys from source and production deploys from source independently, you can't guarantee they run identical code. Always build once, publish to a registry, promote the same artifact through environments.

- **Secrets in environment variables committed to the pipeline YAML.** Developers hardcode tokens or passwords directly in workflow files. Use your platform's secret store (GitHub Secrets, Vault, AWS SSM) and inject them at runtime. Audit pipeline YAML files the same way you audit application code.

- **A pipeline that takes 45 minutes.** Long pipelines destroy adoption. Engineers stop waiting and merge anyway. Parallelize aggressively: run lint, unit tests, and security scans in parallel jobs. Move slow integration tests to a nightly scheduled run if they can't be made fast.

- **No rollback plan tested in the pipeline.** Teams add a deploy step but never test what happens when the health check fails. Wire an automatic rollback into every deploy stage: if `kubectl rollout status` times out, run `kubectl rollout undo`. Test the rollback path in staging drills.

---

## Exercises

1. **Easy — Map a pipeline:** Take your current team's deploy process (even if it's manual). Write it out as a sequence of named stages in pseudocode or a plain list. Identify which steps are automated today and which are manual. Estimate the time each takes.

2. **Medium — Add a security gate:** Take any open-source project with a GitHub Actions CI file. Fork it and add a Trivy or Snyk scan step that fails on CRITICAL severity CVEs in the Docker image. Observe how image base selection affects the scan results (compare `ubuntu:latest` vs `distroless`).

3. **Hard — Implement a canary deployment:** Design a pipeline (you can use pseudocode or a real config) that: builds and pushes an image on tag, deploys it to 5% of production pods using a Kubernetes Deployment canary pattern (two Deployments behind one Service), waits 10 minutes, checks an error-rate metric via a Prometheus query, and either promotes to 100% or auto-rolls back.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Continuous Integration** | "We use Jenkins, so we do CI" | The *practice* of merging frequently and verifying automatically — the tool is irrelevant without the discipline |
| **Continuous Deployment** | Same as Continuous Delivery | CD with *no manual gate* before production; Continuous Delivery still has a human approval step |
| **Artifact** | A build output file | An immutable, versioned, registry-stored unit (Docker image, JAR) that is promoted unchanged across environments |
| **Pipeline as Code** | Config checked in somewhere | The pipeline definition lives in the same repo as the application, is reviewed via PR, and has full history |
| **Green build** | Tests passed on my machine | Every stage in the pipeline passed against the shared branch — local success is irrelevant |
| **GitOps** | "We use git to store configs" | Declarative desired state in git; an operator continuously reconciles live infra to match — git is the source of truth, not humans running commands |
| **Canary release** | Gradual rollout to users | Routing a small percentage of *production* traffic to the new version, using real observability to gate full promotion |

---

## Further Reading

- **GitHub Actions documentation** — Workflow syntax, reusable workflows, environments with protection rules: https://docs.github.com/en/actions
- **The DevOps Handbook** (Kim, Humble, Debois, Willis) — The foundational text on CI/CD culture, flow, and feedback loops; chapters 10–13 cover pipeline design.
- **Google SRE Book, Chapter 8 — Release Engineering** — How Google manages releases at scale, including hermetic builds and the philosophy of immutable artifacts: https://sre.google/sre-book/release-engineering/
- **ArgoCD documentation — GitOps pipeline patterns**: https://argo-cd.readthedocs.io/en/stable/
- **DORA Metrics (Google Cloud)** — The four key metrics (deployment frequency, lead time, MTTR, change failure rate) that measure pipeline effectiveness: https://cloud.google.com/blog/products/devops-sre/using-the-four-keys-to-measure-your-devops-performance
