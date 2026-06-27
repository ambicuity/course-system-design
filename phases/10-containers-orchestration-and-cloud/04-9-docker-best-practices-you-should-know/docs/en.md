# 9 Docker Best Practices You Should Know

> A container is only as solid as the Dockerfile that built it.

**Type:** Learn
**Prerequisites:** Introduction to Containers, Docker Fundamentals, Container Registries
**Time:** ~25 minutes

---

## The Problem

You push a container to production and it works fine — until it doesn't. A teammate pins the same image by the `latest` tag, rebuilds two weeks later, and gets a different base OS version with a broken dependency. Another engineer ships a 1.4 GB image for a 12 MB Go binary because the full build toolchain rode along for the journey. A security audit flags 47 CVEs baked into your base image from 2021 that nobody scanned.

These are not theoretical failures. They are the default outcome when teams treat Dockerfiles as throwaway scripts rather than first-class infrastructure code. The container boundary gives you process isolation, but it does nothing to protect you from your own Dockerfile decisions.

Understanding these nine practices is the difference between a container that is reproducible, secure, and cache-friendly versus one that causes surprise incidents at 2 AM. Each practice addresses a distinct failure mode that shows up in real production environments.

---

## The Concept

Docker images are built in **layers**. Each instruction in a Dockerfile (`FROM`, `RUN`, `COPY`, `ENV`, ...) produces an immutable filesystem layer that is stacked on top of the previous one. The final image is the union of all those layers. This layer model is what makes caching, sharing, and scanning possible — and also what makes ordering, size, and provenance matter so much.

```
  ┌─────────────────────────────┐
  │  Layer N   COPY app/ .      │  ← changes frequently
  ├─────────────────────────────┤
  │  Layer N-1 RUN pip install  │  ← changes when requirements change
  ├─────────────────────────────┤
  │  Layer N-2 COPY requirements│  ← anchor for pip cache
  ├─────────────────────────────┤
  │  Layer 1   FROM python:3.12 │  ← base, pulled once
  └─────────────────────────────┘
```

When Docker rebuilds an image, it walks layers top-to-bottom and reuses every cached layer up to — but not including — the first layer that changed. Everything above that point is rebuilt from scratch. This is why order is not cosmetic.

The nine practices below map to three concerns: **reproducibility** (1, 2, 6, 8), **size and performance** (3, 4, 7), and **security** (5, 9).

---

## Build It / In Depth

### 1. Use Official Images

The Docker Hub `library/` namespace (e.g., `python`, `node`, `postgres`) is maintained by Docker and the upstream software vendors. These images receive timely CVE patches, follow documented hardening guidelines, and have a known, audited supply chain.

```dockerfile
# Bad: random third-party image — unknown provenance
FROM someuser/python-app:latest

# Good: official, vendor-maintained base
FROM python:3.12-slim
```

For production, prefer the `-slim` or `-alpine` variants to reduce attack surface. The full image (e.g., `python:3.12`) bundles compilers and dev tools you do not need at runtime.

---

### 2. Use a Specific Image Version

`latest` is a moving target. It resolves to a different digest on every pull. When you rebuild tomorrow, your image may incorporate a breaking upstream change.

```dockerfile
# Bad: unpredictable, changes without notice
FROM node:latest

# Good: pinned to a minor version (common for teams)
FROM node:20.14-alpine3.20

# Best: pinned to an immutable digest (CI/CD pipelines)
FROM node:20.14-alpine3.20@sha256:a1b2c3d4...
```

Digest pinning (`@sha256:...`) guarantees bit-for-bit identity. Use it in production pipelines. Accept minor-version pins in dev environments where you want patch updates.

---

### 3. Multi-Stage Builds

The build environment and the runtime environment have different requirements. Multi-stage builds let you use one image to compile and a separate, minimal image to ship.

```dockerfile
# Stage 1: builder
FROM golang:1.22-alpine AS builder
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /app ./cmd/server

# Stage 2: runtime — only the binary, nothing else
FROM scratch
COPY --from=builder /app /app
ENTRYPOINT ["/app"]
```

The final image here contains a single statically linked binary. No Go toolchain, no module cache, no shell. A typical Go service goes from 800 MB (builder) to under 15 MB (runtime image).

```
  Before multi-stage:          After multi-stage:
  ┌───────────────────┐        ┌──────────────┐
  │ go toolchain ~500 │        │ binary ~12MB │
  │ module cache ~200 │   →    └──────────────┘
  │ source files      │
  │ binary ~12MB      │
  └───────────────────┘
     ~800 MB                     ~12 MB
```

---

### 4. Use a .dockerignore File

When you run `docker build`, Docker sends the entire **build context** (the directory you point at) to the daemon over a socket. Without a `.dockerignore`, that means `.git/`, `node_modules/`, test data, and local secrets all travel across that socket and can end up in intermediate layers.

```
# .dockerignore
.git
node_modules
.env
*.log
coverage/
__pycache__
.pytest_cache
*.test
```

This has two effects: it speeds up the build (less data sent to the daemon) and it prevents accidental baking of secrets or large unneeded files into image layers that are then pushed to a registry.

---

### 5. Use the Least Privileged User

By default, processes inside a container run as **root (UID 0)**. If an attacker exploits your application, they get root inside the container — and depending on your host configuration and seccomp/AppArmor policies, that can translate to host compromise.

```dockerfile
FROM node:20-alpine

WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev

COPY . .

# Create a non-root user and switch to it
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
USER appuser

CMD ["node", "server.js"]
```

Many official images already provide a non-root user (e.g., `node` user in `node:alpine`). Use `USER node` to activate it. Pair this with `--read-only` filesystem mounts and `--cap-drop ALL` at runtime for defense in depth.

---

### 6. Use Environment Variables (Not Hardcoded Values)

Configuration that varies by environment — database URLs, feature flags, log levels — must not be baked into the image. Use `ENV` for runtime defaults and `ARG` for build-time parameters. Never store secrets in either; inject those from a secrets manager at runtime.

```dockerfile
# ARG is only available at build time
ARG BUILD_VERSION=dev

# ENV is available at runtime
ENV LOG_LEVEL=info \
    PORT=8080 \
    APP_VERSION=$BUILD_VERSION

# At runtime, override via docker run or Kubernetes:
# docker run -e LOG_LEVEL=debug -e PORT=9090 myapp
```

| Instruction | Available at build time | Available at runtime | Appears in image layer |
|-------------|------------------------|----------------------|------------------------|
| `ARG`       | Yes                    | No                   | No (except in RUN)     |
| `ENV`       | Yes                    | Yes                  | Yes                    |

**Never do this:**
```dockerfile
ENV DATABASE_PASSWORD=supersecret   # baked into the image, visible in `docker inspect`
```

---

### 7. Order Instructions for Cache Efficiency

Docker's layer cache is invalidated from the first changed instruction downward. Structure your Dockerfile so the most stable instructions come first and the most volatile last.

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Step 1: copy dependency manifests only (changes rarely)
COPY requirements.txt .

# Step 2: install deps (cached until requirements.txt changes)
RUN pip install --no-cache-dir -r requirements.txt

# Step 3: copy source code (changes on every commit)
COPY . .

CMD ["python", "main.py"]
```

The anti-pattern is `COPY . .` followed by `pip install`. Every source file change invalidates the pip layer, forcing a full dependency reinstall even when `requirements.txt` has not changed. This can add minutes to CI build times at scale.

---

### 8. Label Your Images

OCI image annotations give you a structured, machine-readable audit trail embedded directly in the image manifest. Labels are queryable via `docker inspect` and propagate through registries.

```dockerfile
LABEL org.opencontainers.image.title="payment-service" \
      org.opencontainers.image.version="2.4.1" \
      org.opencontainers.image.source="https://github.com/acme/payment-service" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.vendor="Acme Corp" \
      maintainer="platform-team@acme.com"
```

Use standardized OCI keys (`org.opencontainers.image.*`) so tooling like container security platforms, registries, and orchestrators can parse them automatically. Inject `GIT_SHA` and `BUILD_DATE` as `ARG` values from your CI pipeline.

---

### 9. Scan Images for Vulnerabilities

Every base image carries a set of OS packages with known CVEs. Your dependencies add more. Scanning at build time or in the registry catches these before they reach production.

```bash
# Trivy (open source, fast)
trivy image python:3.12-slim

# Docker Scout (integrated into Docker CLI)
docker scout cves myapp:2.4.1

# Grype (Anchore, open source)
grype myapp:2.4.1
```

Integrate scanning into CI as a gate:

```yaml
# GitHub Actions example
- name: Scan image
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: myapp:${{ github.sha }}
    exit-code: '1'          # fail the build on HIGH/CRITICAL CVEs
    severity: 'HIGH,CRITICAL'
```

Scanning is not a one-time event. Re-scan images already in your registry on a schedule — new CVEs are published daily against packages frozen in images you built six months ago.

---

## Use It

| Practice | Where it matters most | Key tooling |
|---|---|---|
| Official images | All production workloads | Docker Hub `library/` namespace |
| Pinned versions | CI/CD reproducibility | Digest pinning (`@sha256:`) |
| Multi-stage builds | Compiled languages (Go, Java, Rust, C++) | Docker `AS builder` syntax |
| .dockerignore | Monorepos, JS projects with `node_modules` | `.dockerignore` file |
| Non-root user | PCI-DSS, SOC 2 environments | `USER`, `adduser`/`useradd` |
| ENV / ARG | 12-factor apps, Kubernetes deployments | `ENV`, `ARG`, K8s `ConfigMap`/`Secret` |
| Layer ordering | Any team with more than 1 developer | Dockerfile structure |
| Labels | Container registries, SBOM tooling | OCI annotations, Syft |
| Image scanning | Security-sensitive workloads, compliance | Trivy, Docker Scout, Grype, Snyk |

In Kubernetes environments, complement these Dockerfile practices with Pod Security Standards (`runAsNonRoot: true`, `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`) to enforce them at the orchestrator level regardless of what the image declares.

---

## Common Pitfalls

- **Treating `latest` as a stable tag.** `latest` is the default pushed when no tag is specified. It changes silently. CI builds that pin `latest` will produce different binaries on different days, making incidents nearly impossible to reproduce.

- **Copying secrets into the image accidentally.** A `.env` file or `~/.aws/credentials` in the build context gets included in a `COPY . .` instruction and lives permanently in an intermediate layer — even if you `RUN rm .env` afterward. The layer below still contains it. Use `.dockerignore` and inject secrets at runtime.

- **Running `apt-get update` and `apt-get install` in separate `RUN` instructions.** Docker caches each layer independently. If `apt-get update` is cached but `apt-get install` reruns, you install packages from a stale index. Always combine them: `RUN apt-get update && apt-get install -y --no-install-recommends <pkg> && rm -rf /var/lib/apt/lists/*`.

- **Ignoring the `no-cache` flag for package managers.** `pip install` and `npm ci` leave caches in the image layer. Use `pip install --no-cache-dir` and `npm ci --omit=dev` to avoid bloating images with package manager caches that serve no runtime purpose.

- **Scanning once and forgetting.** CVEs are published continuously. An image clean at build time may have a CRITICAL vulnerability reported two weeks later. Schedule nightly registry scans and alert on new findings against already-deployed images.

---

## Exercises

1. **Easy:** Take an existing Dockerfile that uses `FROM ubuntu:latest` and `python` installed via `apt`. Rewrite it to use `FROM python:3.12-slim` pinned to a specific digest. Measure the image size difference with `docker image ls`.

2. **Medium:** Take a Node.js application Dockerfile that currently does `COPY . . && npm install`. Restructure it using proper layer ordering and a `.dockerignore` file. Benchmark build time before and after by touching only a source file (not `package.json`) and rebuilding.

3. **Hard:** Convert a Java Spring Boot application from a single-stage build (using `maven:3.9` to both build and run) to a multi-stage build that produces a runtime image based on `eclipse-temurin:21-jre-alpine`. Add OCI labels populated from CI environment variables, run the container as a non-root user, and integrate a Trivy scan as a CI pipeline gate that fails on CRITICAL severity.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| `latest` tag | The most recent stable release | An arbitrary mutable pointer — usually whatever was last pushed without an explicit tag |
| Build context | The Dockerfile itself | The entire directory tree sent to the Docker daemon before a single instruction runs |
| Image layer | A file in the image | An immutable filesystem diff stored as a tar archive; shared across images via content-addressed IDs |
| Multi-stage build | Just for compiled languages | A Dockerfile with multiple `FROM` statements; useful for any language where build and runtime deps differ |
| `ARG` vs `ENV` | Both are environment variables | `ARG` exists only during the build; `ENV` is baked into the image and visible at runtime and in `docker inspect` |
| Non-root user | Optional hardening, rarely needed | A mandatory baseline for any compliance framework (PCI-DSS, SOC 2, CIS Benchmark) |
| Image scan | A one-time gate at build | A continuous process — re-scan already-deployed images as new CVEs are published daily |

---

## Further Reading

- [Docker Official Dockerfile Best Practices](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/) — the canonical reference from Docker, covers all instructions in depth.
- [OCI Image Spec — Annotations](https://github.com/opencontainers/image-spec/blob/main/annotations.md) — specification for standard label keys (`org.opencontainers.image.*`).
- [Trivy Documentation](https://aquasecurity.github.io/trivy/) — open-source vulnerability scanner with registry, filesystem, and CI integration modes.
- [Google Distroless Images](https://github.com/GoogleContainerTools/distroless) — minimal base images containing only application runtimes, no shell or package manager, ideal as the final stage in multi-stage builds.
- [CIS Docker Benchmark](https://www.cisecurity.org/benchmark/docker) — comprehensive security hardening checklist covering Dockerfile practices, daemon configuration, and runtime settings.
