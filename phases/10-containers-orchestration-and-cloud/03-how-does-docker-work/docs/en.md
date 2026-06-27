# How does Docker Work?

> Docker does not virtualize hardware — it virtualizes the operating system, packaging just enough Linux to make your process feel like it owns the machine.

**Type:** Learn
**Prerequisites:** Virtual Machines vs Containers, Linux Fundamentals
**Time:** ~25 minutes

---

## The Problem

Picture a team of five engineers working on a Python microservice. One runs macOS 14 with Python 3.11, another uses Ubuntu 22.04 with Python 3.9, and the CI server runs CentOS 7 with Python 3.6. The application works perfectly on the first developer's laptop and fails with a cryptic `ImportError` on every other machine. You spend two days hunting a dependency version mismatch. Then you ship to production, and the OS-level OpenSSL version is different — another failure, this time a silent TLS downgrade.

This is the "works on my machine" problem, and it predates containers by decades. The traditional solution was to write a lengthy setup document and pray everyone followed it. A slightly better solution was full virtual machines — but VMs bring gigabytes of overhead: a complete OS kernel, disk image, and boot time measured in minutes just to run a single process.

Docker solves this by shipping not a virtual machine, but a *packaged environment*: your code plus exactly the filesystem, libraries, and config it needs, using Linux kernel features that have existed since 2008. The resulting unit (a container) starts in milliseconds, weighs megabytes, and behaves identically on every Linux host. Understanding how Docker actually achieves this — down to the kernel primitives — tells you what containers can and cannot do, when they break, and how to design systems that use them well.

---

## The Concept

### The Three-Layer Architecture

Docker exposes a client-server model with three components:

```
┌────────────────────────────────────────────────┐
│                  Docker Client                  │
│  (docker CLI / Docker Desktop / Compose / SDK)  │
└───────────────────┬────────────────────────────┘
                    │  REST API (Unix socket / TCP)
┌───────────────────▼────────────────────────────┐
│               Docker Host                       │
│  ┌──────────────────────────────────────────┐  │
│  │           dockerd (daemon)               │  │
│  │  ┌─────────────┐   ┌──────────────────┐ │  │
│  │  │ containerd  │   │  Image cache     │ │  │
│  │  │  (runtime)  │   │  Volumes/Nets    │ │  │
│  │  └──────┬──────┘   └──────────────────┘ │  │
│  │         │                                │  │
│  │       runc  (OCI runtime, per-container) │  │
│  └─────────────────────────────────────────┘  │
└───────────────────┬────────────────────────────┘
                    │  pull / push
┌───────────────────▼────────────────────────────┐
│               Docker Registry                   │
│        (Docker Hub / ECR / GCR / GHCR)          │
└────────────────────────────────────────────────┘
```

- **Docker Client**: The `docker` binary you type commands into. It speaks a REST API over a Unix socket (`/var/run/docker.sock`) to the daemon. The client itself does no heavy lifting.
- **Docker Daemon (`dockerd`)**: The long-running process that manages images, containers, networks, and volumes. It delegates actual container lifecycle to `containerd`.
- **containerd**: An industry-standard container runtime (CNCF project). It manages the full container lifecycle and delegates the lowest-level fork/exec to `runc`.
- **runc**: A tiny CLI tool that speaks the OCI Runtime Specification. It calls Linux kernel APIs directly to create the isolated process.
- **Registry**: A content-addressed image store. `docker pull` fetches layers from it; `docker push` uploads them.

### What a Container Actually Is

A container is **a process (or group of processes) on the host kernel, isolated using three Linux primitives**:

| Primitive | What it does | Example |
|-----------|-------------|---------|
| **Namespaces** | Hide parts of the global system from a process | PID namespace makes init PID=1 inside the container |
| **cgroups** | Limit and account for resource consumption | Limit a container to 512 MB RAM and 0.5 CPU |
| **Union filesystem** | Stack read-only image layers + a writable top layer | OverlayFS merges base OS + app layers at mount time |

There is no guest kernel. Both the host and all containers share the same kernel. This is why containers are fast and lightweight — and why a container cannot run a Windows kernel process on a Linux host without a VM underneath.

### Namespaces in Detail

Docker uses six Linux namespaces per container:

| Namespace | Kernel flag | Isolates |
|-----------|-------------|---------|
| `pid` | `CLONE_NEWPID` | Process IDs — container sees its own PID tree starting at 1 |
| `net` | `CLONE_NEWNET` | Network interfaces, routing tables, firewall rules |
| `mnt` | `CLONE_NEWNS` | Mount points — container gets its own `/proc`, `/sys`, root |
| `uts` | `CLONE_NEWUTS` | Hostname and domain name |
| `ipc` | `CLONE_NEWIPC` | System V IPC and POSIX message queues |
| `user` | `CLONE_NEWUSER` | UID/GID mappings (rootless Docker) |

When `runc` calls `clone(2)` with these flags, the kernel creates a new process that believes it is the sole occupant of the machine.

### cgroups (Control Groups)

Namespaces provide *visibility* isolation; cgroups provide *resource* isolation. Docker creates a cgroup hierarchy for each container under `/sys/fs/cgroup/`. Kernel accounting tracks CPU time, memory pages, I/O bytes, and network bandwidth per cgroup. Hard limits throw `SIGKILL` (OOM killer) or throttle CPU when a container exceeds its allocation.

### The Layered Filesystem (OverlayFS)

Docker images are stacks of read-only layers. Each `RUN`, `COPY`, or `ADD` instruction in a Dockerfile creates one layer. At runtime, OverlayFS merges them into a single coherent filesystem view and adds a thin writable layer on top.

```
┌─────────────────────────┐  ← writable layer (container-specific)
│  upperdir (writes go here) │
├─────────────────────────┤
│  layer N: RUN pip install  │  ← read-only
├─────────────────────────┤
│  layer N-1: COPY app/      │  ← read-only
├─────────────────────────┤
│  layer 1: FROM python:3.11 │  ← read-only (base image)
└─────────────────────────┘
```

Writes are copy-on-write (CoW): reading a file comes from the highest layer that contains it; writing a file copies it up to the writable layer first. When the container is deleted, the writable layer is discarded — image layers are never modified.

**Why this matters for design**: if ten containers run the same base image, the read-only layers are shared on disk and in the page cache. Ten containers sharing a 200 MB base image cost 200 MB + ten tiny writable layers, not 2 GB.

---

## Build It / In Depth

### Following a `docker run nginx` Call Through the Stack

```bash
docker run -d -p 8080:80 --memory=256m nginx:1.25
```

**Step 1 — Client parses and sends REST request**

```
POST /v1.44/containers/create  →  dockerd via /var/run/docker.sock
```

**Step 2 — dockerd checks the local image cache**

If `nginx:1.25` is absent, dockerd pulls it from Docker Hub: authenticates, fetches the manifest (a JSON list of layer digests), then downloads each compressed layer (`.tar.gz`) in parallel.

**Step 3 — containerd unpacks layers**

Each layer is a tar archive of filesystem diffs. containerd extracts them into content-addressed storage under `/var/lib/containerd/`. OverlayFS mount points are prepared.

**Step 4 — runc creates the container**

`runc` receives an OCI bundle (a `config.json` describing namespaces, cgroups, mounts, and the entrypoint). It calls:
```
clone(CLONE_NEWPID | CLONE_NEWNET | CLONE_NEWNS | CLONE_NEWUTS | CLONE_NEWIPC)
```
then configures the cgroup limits, sets up the OverlayFS mount, pivots the root filesystem, and execs the entrypoint (`nginx -g 'daemon off;'`).

**Step 5 — Networking**

dockerd creates a `veth` pair. One end goes into the container's net namespace; the other is attached to the `docker0` bridge. NAT rules (`iptables DNAT`) map `host:8080 → container_ip:80`.

**Step 6 — Container is running**

The nginx process is now PID 1 inside its namespace, limited to 256 MB, with its own network interface, hostname, and filesystem view. From the host, `ps aux` shows it as an ordinary process with a large PID number.

### Dockerfile Layer Caching

```dockerfile
# Layer 1 — base (cached across almost all builds)
FROM python:3.11-slim

# Layer 2 — dependencies (cached as long as requirements.txt doesn't change)
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Layer 3 — application code (invalidated most often)
COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Copy dependency files *before* source code. Docker cache invalidation is top-down: if layer N changes, all layers N+1 onward are rebuilt. Swapping the `COPY . .` and `RUN pip install` order turns every code change into a full dependency reinstall.

---

## Use It

| Use Case | Tool / Pattern | Notes |
|----------|---------------|-------|
| Local dev environment | `docker-compose.yml` | Database, cache, and app in one `up` command |
| CI build isolation | Docker-in-Docker or Kaniko | Each build gets a clean environment |
| Immutable deployments | Image tag = git SHA | Rollback = pull previous tag |
| Microservice packaging | One container per service | Clear dependency boundary, independent scaling |
| Kubernetes workloads | Pod = one or more containers | Kubernetes orchestrates; Docker (or containerd) executes |
| Serverless runtimes | AWS Lambda container images | Up to 10 GB image, same toolchain |

**Registry choices:**

| Registry | When to use |
|----------|-------------|
| Docker Hub | Open-source images, public projects |
| Amazon ECR | AWS-native workloads, IAM-integrated auth |
| Google Artifact Registry | GKE workloads |
| GitHub Container Registry (GHCR) | GitHub Actions pipelines |
| Self-hosted (Harbor) | Air-gapped or compliance-constrained environments |

---

## Common Pitfalls

- **Ignoring `.dockerignore`**: Without it, `COPY . .` sends your entire repo context (including `node_modules`, `.git`, and test data) to the daemon. A 500 MB context makes every build slow and bloats images with files the app never uses.

- **Running as `root` inside the container**: The default user in most base images is UID 0. If a vulnerability allows container escape, the attacker arrives on the host as root. Always add `USER nonroot` (or a specific UID) at the end of your Dockerfile. Use `--cap-drop ALL` and add back only what's needed.

- **Mutable tags in production**: Tagging images as `latest` or `stable` and deploying by tag means `docker pull` in a rollout can silently fetch a different image than your staging run used. Pin to the digest (`image@sha256:...`) or a git-SHA-based tag in production manifests.

- **Treating the writable layer as durable storage**: Data written inside a container is lost when the container is removed. Mount a named volume (`-v pgdata:/var/lib/postgresql/data`) for anything that must survive restarts. Never put a database inside an image layer.

- **Fat images from un-squashed build artifacts**: Every intermediate file created in a `RUN` layer and not deleted *in the same layer* persists in the image. `RUN apt-get install ... && rm -rf /var/lib/apt/lists/*` must be a single `RUN` instruction, not two separate ones. Use multi-stage builds to keep final images lean.

---

## Exercises

1. **Easy** — Pull the official `alpine:3.19` image and run an interactive shell (`docker run -it alpine sh`). Inside, run `ps aux`. Notice that PID 1 is `sh`, not `systemd`. Explain why.

2. **Medium** — Write a two-stage Dockerfile for a Go HTTP server. Stage 1: `FROM golang:1.22` to compile the binary. Stage 2: `FROM scratch` to copy only the compiled binary. Compare the image sizes (`docker images`). Explain the size difference in terms of layers and the OverlayFS model.

3. **Hard** — Explore namespace isolation from the host side. Start a container in detached mode (`docker run -d nginx`). On the host, find the container's PID with `docker inspect`. Then run `ls -la /proc/<pid>/ns/` and compare the namespace inode numbers to those of a host process (`ls -la /proc/1/ns/`). Identify which namespaces differ and which (if any) are shared.

---

## Key Terms

| Term | What people think | What it actually means |
|------|------------------|----------------------|
| **Container** | A lightweight VM | A process on the host kernel isolated with namespaces and cgroups |
| **Image** | A zip file of source code | An ordered stack of read-only filesystem layers with metadata and an entrypoint |
| **Docker daemon (`dockerd`)** | The thing that runs containers | An API server that delegates to containerd; it manages images, networks, and volumes |
| **Registry** | "Docker Hub" | Any OCI-compliant content-addressed store for image layers and manifests |
| **Layer** | A version of the image | A tar archive of filesystem diffs; cached and shared across images |
| **Namespace** | A Docker concept | A Linux kernel feature (since 2.6.24) that partitions global resources per process |
| **cgroup** | Docker's memory limit | A Linux kernel subsystem that tracks and enforces resource budgets per process group |

---

## Further Reading

- [Docker Architecture — Official Docs](https://docs.docker.com/get-started/overview/#docker-architecture): The canonical reference for the client-daemon-registry model.
- [OCI Runtime Specification](https://github.com/opencontainers/runtime-spec): Defines exactly what `runc` must do — `config.json` schema, lifecycle hooks, and namespace setup.
- [Linux Namespaces — `man 7 namespaces`](https://man7.org/linux/man-pages/man7/namespaces.7.html): The authoritative source on every namespace type and its `clone(2)` flag.
- [Nigel Poulton — *Docker Deep Dive*](https://www.nigelpoulton.com/books/): Short, practical book that follows a container call from CLI to kernel, great companion reading.
- [containerd Architecture](https://containerd.io/docs/getting-started/): Explains how containerd sits between `dockerd` and `runc`, relevant once you work with Kubernetes directly.
