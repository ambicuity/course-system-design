# Virtualization vs Containerization

> Isolation is the goal — the question is how much kernel you want to share.

**Type:** Learn
**Prerequisites:** Linux fundamentals, basic networking concepts
**Time:** ~30 minutes

---

## The Problem

Imagine you run a SaaS platform with three services: a Node.js API, a Python ML worker, and a legacy PHP application. All three have conflicting system library requirements. The API needs `libssl 1.1`, the ML worker needs CUDA and a newer `libssl 3.x`, and the PHP app was frozen at PHP 7.4 years ago. Running all three on the same bare-metal host means dependency hell — one upgrade breaks another service.

The naive fix is to buy three separate servers. That works, but now each server sits at 10–15% CPU utilization while you pay for 100% of the hardware. Capital expenditure balloons, provisioning new capacity takes days, and reproducing a production bug locally is nearly impossible.

Both virtualization and containerization solve this isolation problem, but they make fundamentally different trade-offs around where the boundary between isolated environments is drawn. Understanding that boundary — and what crosses it — determines cost, startup time, portability, and security posture. Getting this wrong leads to either wasted cloud spend (over-provisioning VMs) or security incidents (insufficiently isolated containers running multi-tenant workloads).

---

## The Concept

### The Isolation Stack: Four Levels

```
┌─────────────────────────────────────────────────────────────────┐
│                    BARE METAL                                   │
│  App A │ App B │ App C — all share one OS, one kernel          │
│                    OS / Kernel                                  │
│                    Physical Hardware                            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    VIRTUALIZED                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│  │  App A   │  │  App B   │  │  App C   │                      │
│  │ Guest OS │  │ Guest OS │  │ Guest OS │  ← full OS per VM    │
│  └──────────┘  └──────────┘  └──────────┘                      │
│                   Hypervisor                                    │
│                   Host OS (optional)                            │
│                   Physical Hardware                             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    CONTAINERIZED                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│  │  App A   │  │  App B   │  │  App C   │                      │
│  │  libs    │  │  libs    │  │  libs    │  ← user-space only   │
│  └──────────┘  └──────────┘  └──────────┘                      │
│                Container Runtime (Docker / containerd)          │
│                   Shared Host OS Kernel                         │
│                   Physical Hardware                             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│             CONTAINERIZED ON VIRTUALIZED (most common in cloud) │
│  ┌────────────────────────────┐  ┌────────────────────────────┐ │
│  │  Container A │ Container B │  │  Container C │ Container D │ │
│  │     libs     │   libs      │  │    libs      │    libs     │ │
│  │        Container Runtime   │  │       Container Runtime    │ │
│  │          Guest OS          │  │         Guest OS           │ │
│  └────────────────────────────┘  └────────────────────────────┘ │
│                        Hypervisor                               │
│                        Physical Hardware                        │
└─────────────────────────────────────────────────────────────────┘
```

### How Virtualization Works Under the Hood

A **hypervisor** intercepts privileged CPU instructions that a guest OS would otherwise run directly on hardware. There are two types:

- **Type 1 (bare-metal):** Runs directly on hardware. The hypervisor *is* the OS. Examples: VMware ESXi, Microsoft Hyper-V, KVM (Linux kernel module).
- **Type 2 (hosted):** Runs as a process inside a host OS. Examples: VirtualBox, VMware Workstation.

Each VM gets a virtualized version of CPU, memory, disk, and NIC. The guest OS believes it owns real hardware. This complete simulation is what makes VMs strongly isolated but expensive — a 1 GB Ubuntu VM ships ~200 MB of userland plus the kernel, plus a virtualized device driver stack.

**Boot time:** 30–60 seconds (kernel boot + init system + services).
**Disk footprint:** 2–20 GB per VM image.
**Memory overhead:** Guest OS kernel + system daemons consume 100–300 MB before your app runs.

### How Containerization Works Under the Hood

Containers are not a new abstraction — they are a thin composition of three existing Linux kernel features:

| Kernel Feature | What it does |
|---|---|
| **Namespaces** | Isolate the view of system resources (PID tree, network interfaces, mount points, user IDs, hostname) |
| **cgroups (v1/v2)** | Enforce resource *limits* — CPU shares, memory ceiling, I/O bandwidth |
| **Union Filesystems** (OverlayFS) | Layer read-only image layers under a writable container layer; enables image sharing |

When you run `docker run nginx`, the container runtime:
1. Pulls image layers and stacks them via OverlayFS
2. Forks a new process with a new set of Linux namespaces (isolated PID, net, mnt, uts)
3. Assigns the process to a cgroup with your resource limits
4. Exec's the entrypoint inside the isolated namespace

The critical insight: **there is no second kernel**. The container process runs on the host kernel. `strace` from the host can see container syscalls. This is why containers start in milliseconds — there is no kernel to boot.

### Side-by-Side Comparison

| Dimension | Virtual Machine | Container |
|---|---|---|
| Isolation unit | Full OS + kernel | Process namespace |
| Kernel | Separate guest kernel per VM | Shared host kernel |
| Startup time | 30–90 seconds | < 1 second |
| Image size | 2–20 GB | 5–500 MB |
| Memory overhead | 100–300 MB (OS baseline) | < 10 MB (process + libs) |
| Security boundary | Hypervisor (hardware-level) | Kernel namespaces (software) |
| Multi-tenant safety | Strong (separate kernels) | Weaker (shared kernel) |
| Portability | Image tied to hypervisor type | Run on any Linux host with same kernel |
| Live migration | Supported (vMotion, etc.) | Limited without orchestration |
| Suitable for | Legacy apps, OS-level testing, strong isolation | Microservices, CI/CD, stateless workloads |

---

## Build It / In Depth

### Exploring Isolation Primitives Directly

You do not need Docker to understand containers — you can recreate the core isolation with basic Linux commands.

**Step 1 — Namespace isolation (new PID and hostname namespace):**

```bash
# Start an isolated shell — it cannot see host PIDs
sudo unshare --pid --fork --mount-proc --uts bash

# Inside the new shell
hostname container-demo
ps aux          # Only sees processes inside its own PID namespace
hostname        # Shows "container-demo", not the host name
exit
```

**Step 2 — cgroup resource limit (cap memory to 64 MB):**

```bash
# Create a cgroup (cgroup v2 path on modern Linux)
sudo mkdir /sys/fs/cgroup/demo
echo "67108864" | sudo tee /sys/fs/cgroup/demo/memory.max   # 64 MB

# Launch a process into the cgroup
sudo bash -c 'echo $$ > /sys/fs/cgroup/demo/cgroup.procs && exec sleep 300'
```

**Step 3 — See what Docker actually does:**

```bash
# Run an nginx container
docker run -d --name web --memory="64m" --cpus="0.5" nginx

# Inspect the kernel structures Docker created
docker inspect web | grep -A5 '"Pid"'
# Find the actual host PID, then inspect its namespaces:
ls -la /proc/<PID>/ns/

# Confirm the cgroup limit
cat /sys/fs/cgroup/system.slice/docker-<CONTAINER_ID>.scope/memory.max
```

**Step 4 — VM vs container image size comparison:**

```bash
# Pull a minimal container image
docker pull alpine
docker images alpine    # ~7 MB

# Compare: a minimal Ubuntu 22.04 cloud VM image
# (for reference — you'd download it separately)
# ubuntu-22.04-server-cloudimg-amd64.img  →  ~600 MB compressed
# Expanded with OS disk: 2–5 GB
```

### Layered Filesystem in Action

```bash
# Build a two-layer image to see OverlayFS
cat > Dockerfile <<'EOF'
FROM alpine:3.19
RUN echo "layer1" > /data.txt
RUN echo "layer2" >> /data.txt
EOF

docker build -t overlay-demo .
docker history overlay-demo   # Shows each layer and its size

# Inspect actual OverlayFS mounts for a running container
docker run -d --name demo overlay-demo sleep 300
docker inspect demo | python3 -c \
  "import sys,json; m=json.load(sys.stdin)[0]['GraphDriver']['Data']; \
   [print(k,v) for k,v in m.items()]"
# LowerDir, UpperDir, WorkDir, MergedDir — the OverlayFS mount args
```

---

## Use It

### When to Choose Each

| Scenario | Best Choice | Reason |
|---|---|---|
| Multi-tenant SaaS (untrusted code) | VM or gVisor containers | Kernel separation prevents tenant escape |
| Microservices on your own infra | Containers (Kubernetes) | Fast scale-out, low overhead per pod |
| Legacy Windows .NET app | VM (Windows guest) | Containers share the host kernel; Windows app needs Windows kernel |
| CI/CD build pipelines | Containers | Ephemeral, fast startup, reproducible environments |
| GPU workloads (ML training) | VMs or containers with GPU passthrough | GPU drivers must match; containers need NVIDIA Container Toolkit |
| Bare-metal performance critical (HFT, game servers) | Bare metal | Zero hypervisor or container overhead |
| Cloud Kubernetes (EKS, GKE, AKS) | Containers on VMs | Node = VM; pod = container inside that VM |

### Key Technologies

- **Type 1 Hypervisors:** VMware ESXi, Microsoft Hyper-V, KVM/QEMU, Xen (AWS Nitro is KVM-based)
- **Type 2 Hypervisors:** VirtualBox, VMware Workstation, Parallels
- **Container Runtimes:** containerd (default in Kubernetes), CRI-O, Docker Engine (wraps containerd)
- **Sandboxed Containers (middle ground):** gVisor (Google) — intercepts syscalls in user-space; Kata Containers — each pod runs in a lightweight VM
- **Cloud:** AWS EC2 = VMs; AWS Fargate / ECS = containers; GKE Autopilot = containers on managed VMs

### The "Containers on VMs" Pattern (Most Common in Production)

Every major cloud Kubernetes offering runs containers inside VMs. This is not redundancy for its own sake:

1. **VM = node boundary** — cgroups and namespaces provide workload isolation; the VM provides a security boundary between cloud tenants.
2. **VM autoscaling** — you scale VM fleet to add/remove container capacity (node autoscaler).
3. **Container scheduling** — Kubernetes packs containers onto VMs at high density (bin-packing).

---

## Common Pitfalls

- **"Containers are secure because they're isolated."** A misconfigured container running as root with the Docker socket mounted can escape to the host. Always run containers as non-root (`USER 1000`), drop capabilities (`--cap-drop=ALL`), and never mount `/var/run/docker.sock` in production containers.

- **Assuming containers are VMs for licensing.** Some software licenses count per-OS or per-VM. Running 50 containers on one VM may still count as one license seat — or it may not, depending on the EULA. Virtualization-based software counts can differ entirely.

- **Ignoring kernel version compatibility.** Containers share the host kernel. An image built against kernel 6.x features (io_uring, eBPF programs, specific syscalls) will fail on an old kernel. VMs sidestep this because each VM boots its own kernel.

- **Bloated VM images from lack of snapshot hygiene.** Teams often take VM snapshots "just in case" and never delete them. Snapshots chain and inflate storage; disk I/O performance degrades as chains grow. Enforce a snapshot retention policy and use immutable VM images instead.

- **Using VMs for everything in Kubernetes nodes.** Over-provisioning each VM node to run just 2–3 containers wastes capacity. Right-size your node instance types and let the Kubernetes scheduler bin-pack pods. Use node auto-provisioning to let the cluster choose instance types dynamically.

---

## Exercises

1. **Easy:** On any Linux machine (or Docker Desktop on Mac/Windows), run `docker run --rm alpine ps aux` and compare the PID list inside the container vs `ps aux` on the host. Explain why they differ in terms of PID namespaces.

2. **Medium:** Create two Docker containers: one limited to 128 MB RAM (`--memory=128m`) and one with no limit. Inside each, run a Python script that allocates memory in a loop (`bytearray(1024*1024)`) until it fails. Observe what happens at the limit and explain the role of cgroups in enforcing it.

3. **Hard:** Deploy a Kubernetes cluster locally with `kind` (Kubernetes in Docker). Notice that each "node" is itself a Docker container. Exec into a node container and list the processes — you will see the container runtime and all pod processes. Draw an annotated diagram of the full isolation stack: physical host → Docker (for `kind`) → node container → pod container. Identify which layer uses namespaces, which uses cgroups, and which uses hypervisor isolation. Discuss what security guarantees are present and absent in this setup.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Container** | A lightweight VM | A Linux process with namespaces and cgroup limits; shares the host kernel |
| **Hypervisor** | "The thing that runs VMs" | Software (or hardware-assisted firmware) that intercepts privileged CPU instructions and multiplexes hardware across guest OSes |
| **Namespace** | A container concept | A Linux kernel feature (since 2002) that scopes the view of system resources for a process tree — predates Docker by a decade |
| **cgroup** | A Docker resource setting | A Linux kernel mechanism that enforces resource accounting and limits; cgroup v2 unified hierarchy became default in kernel 5.10 |
| **OverlayFS** | An implementation detail | A union filesystem that stacks read-only image layers and a writable layer; enables sub-second container startup and efficient image sharing |
| **Type 1 vs Type 2 Hypervisor** | Just a product classification | Structural distinction: Type 1 runs on bare metal (no host OS); Type 2 runs as an application inside a host OS |
| **Kata Containers** | Exotic / niche | OCI-compatible container runtime that starts each container in a micro-VM; bridges the gap between container density and VM security |

---

## Further Reading

- [Linux Namespaces — kernel.org documentation](https://www.kernel.org/doc/html/latest/admin-guide/namespaces/index.html)
- [cgroups v2 — Red Hat documentation](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/managing_monitoring_and_updating_the_kernel/setting-limits-for-applications_managing-monitoring-and-updating-the-kernel)
- [OCI Runtime Specification](https://github.com/opencontainers/runtime-spec/blob/main/spec.md) — the standard all container runtimes implement
- [gVisor: Container Security Through Kernel Isolation](https://gvisor.dev/docs/) — Google's approach to sandboxed containers
- [Brendan Gregg — Linux Performance and Containers](https://www.brendangregg.com/blog/2017-11-29/aws-lambda-vs-ec2.html) — practical performance analysis of isolation layers
