# Types of Virtualization

> Every layer of abstraction you add costs something — the trick is knowing what you're buying.

**Type:** Learn
**Prerequisites:** Linux Fundamentals, Introduction to Cloud Computing, What is a Container
**Time:** ~25 minutes

---

## The Problem

You're running three services on a single physical server: a Python API, a Node.js frontend, and a PostgreSQL database. The database process leaks memory every few days, takes the whole machine down, and the API restarts cold. You fix that by moving to separate servers — but now you're paying for three machines that are each 15% utilized during off-peak hours, and your ops team needs to SSH into each one individually to patch the OS.

You try splitting each server with a hypervisor. Isolation improves dramatically, but each VM needs its own 4 GB Windows Server license, 2 GB of RAM just to idle, and 45 seconds to boot when your auto-scaler needs a new instance. Your cloud bill for RAM alone now exceeds your compute costs.

You switch to containers. Boot time drops to 80 ms, memory overhead per workload falls to a few MB, and you pack 40 containers on the same iron that hosted 4 VMs. But then a container escapes its namespace boundary via a kernel exploit and reads another tenant's memory — because every container shares one kernel.

The right answer isn't a single technology. It is knowing what each virtualization strategy buys and what it costs, so you can layer them deliberately. This lesson gives you the mental model.

---

## The Concept

Virtualization is the practice of creating a logical version of a resource (compute, storage, network) that is decoupled from the underlying physical hardware. Every form of virtualization is really answering the same two questions:

1. **At what boundary do you enforce isolation?** (kernel, hypervisor, hardware)
2. **How much of the hardware does each guest think it owns?** (everything, a partition, just a process tree)

### The Four Execution Models

```
Physical Machine
┌────────────────────────────────────────────────────────────────┐
│                     HARDWARE (CPU/RAM/Disk)                     │
└────────────────────────────────────────────────────────────────┘

(1) BARE METAL               (2) VIRTUAL MACHINES
┌─────────┬─────────┐        ┌──────┬──────┬──────┐
│  App A  │  App B  │        │ VM1  │ VM2  │ VM3  │  ← guest OS per VM
│         │         │        │ OS   │ OS   │ OS   │
├─────────┴─────────┤        ├──────┴──────┴──────┤
│     Host OS       │        │    Hypervisor       │
└───────────────────┘        └─────────────────────┘

(3) CONTAINERS               (4) CONTAINERS ON VMs
┌──────┬──────┬──────┐        ┌─────────────┬─────────────┐
│ Ctr1 │ Ctr2 │ Ctr3 │        │  VM1        │  VM2        │
│      │      │      │        │ ┌──┬──┬──┐  │ ┌──┬──┬──┐  │
├──────┴──────┴──────┤        │ │C1│C2│C3│  │ │C4│C5│C6│  │
│ Container Runtime  │        │ └──┴──┴──┘  │ └──┴──┴──┘  │
│     Host OS        │        │ Container   │ Container   │
└────────────────────┘        │ Runtime+OS  │ Runtime+OS  │
                              ├─────────────┴─────────────┤
                              │         Hypervisor         │
                              └────────────────────────────┘
```

### Model 1 — Bare Metal (No Virtualization)

Applications run directly on the OS, which runs directly on hardware. Processes share the same kernel, same libraries, same network stack. The only isolation is user-space process separation enforced by the OS scheduler and memory management unit.

**What you get:** Maximum performance, zero hypervisor overhead, full access to hardware features (NUMA topology, GPU direct, SR-IOV). High-frequency trading engines, real-time signal processors, and HPC workloads are still deployed bare-metal for this reason.

**What you give up:** A single misconfigured or compromised process can affect all co-tenants. Provisioning a new server takes minutes to hours. Scaling means buying hardware.

### Model 2 — Virtual Machines

A **hypervisor** sits between the hardware and guest OSes and enforces isolation at the hardware boundary. The hypervisor intercepts every privileged instruction the guest OS tries to execute.

**Type 1 (bare-metal) hypervisors** run directly on hardware:
- VMware ESXi, Microsoft Hyper-V, KVM (Linux Kernel Module), Xen

**Type 2 (hosted) hypervisors** run on top of an existing OS:
- VirtualBox, VMware Workstation, Parallels

Modern CPUs expose hardware-assisted virtualization extensions (Intel VT-x, AMD-V) that allow the hypervisor to trap privileged instructions without expensive binary translation. This closes the performance gap to roughly 2–5% overhead versus bare metal for CPU-bound workloads, and near-zero for I/O with para-virtualized drivers (virtio).

**Memory model:** Each VM has an explicit memory allocation. The hypervisor maintains a two-level page table (guest physical → host physical). Techniques like memory ballooning and transparent page sharing (deduplication of identical pages across VMs) help reclaim memory, but each VM still needs RAM for its kernel regardless of workload.

**What you get:** Strong isolation (hardware-enforced MMU boundary), ability to run different OS families on the same host, full snapshot and live-migration support, security boundary enforced at hardware level.

**What you give up:** 2–4 GB of RAM per VM just for the kernel + userland, 30–90 second boot times, OS licensing costs, patching and OS management for every VM.

### Model 3 — Containers

Containers use Linux kernel primitives to partition a single OS kernel into isolated slices:

| Kernel Primitive | What it isolates |
|---|---|
| **namespaces** (pid, net, mnt, uts, ipc, user) | Process tree, network stack, filesystem mounts, hostname, IPC objects, UID/GID mapping |
| **cgroups v2** | CPU shares, memory limits, I/O bandwidth, device access |
| **seccomp** | System call whitelist — blocks calls a container shouldn't need |
| **capabilities** | Restricts root-level capabilities available inside the container |
| **Union filesystem** (overlay2, AUFS) | Layered copy-on-write image format |

A container is a process (or process group) that the kernel treats as if it lives in a different namespace universe. There is no separate kernel instance. The container runtime (`containerd` or `CRI-O`) calls `clone(2)` with the appropriate namespace flags and then `execve(2)` to start the workload.

**What you get:** Sub-100 ms startup, megabytes of overhead rather than gigabytes, identical environment from laptop to production (image portability), dense packing (40–100 containers per host vs. 4–8 VMs), and fast horizontal scaling.

**What you give up:** All containers share one kernel — a kernel vulnerability affects all tenants. Linux-only (Windows containers exist but are niche). Weaker multi-tenant security boundaries.

### Model 4 — Containers on VMs (The Production Standard)

This is what Kubernetes on AWS (EKS), Azure (AKS), and GCP (GKE) actually deploy. Worker nodes are VMs; pods are containers inside those VMs.

```
Cloud Provider Infrastructure
┌─────────────────────────────────────────────────────────────┐
│                      Physical Host                           │
│  ┌──────────────────────┐   ┌──────────────────────────┐   │
│  │  VM: k8s Worker Node │   │  VM: k8s Worker Node     │   │
│  │  ┌────┐ ┌────┐       │   │  ┌────┐ ┌────┐ ┌────┐   │   │
│  │  │Pod │ │Pod │       │   │  │Pod │ │Pod │ │Pod │   │   │
│  │  └────┘ └────┘       │   │  └────┘ └────┘ └────┘   │   │
│  │  containerd + kubelet│   │  containerd + kubelet    │   │
│  │  Guest OS (Linux)    │   │  Guest OS (Linux)        │   │
│  └──────────────────────┘   └──────────────────────────┘   │
│                      Hypervisor                              │
└─────────────────────────────────────────────────────────────┘
```

The hypervisor provides hard multi-tenant isolation between customers. The container engine provides lightweight application isolation within a customer's VM. You get VM-level security with near-container density.

---

## Build It / In Depth

### Tracing a Container From `docker run` to Process

Understanding what happens at the system-call level makes the security model concrete.

```bash
# Run a container and inspect the host's process table
docker run --rm -d --name demo nginx:alpine

# The container's PID inside its namespace
docker exec demo ps aux
# PID 1: nginx: master process

# The same process from the HOST namespace — different PID
ps aux | grep nginx
# PID 38412: nginx: master process  ← host sees a different PID
```

The kernel assigned a new PID namespace when `containerd` called `clone(CLONE_NEWPID | CLONE_NEWNET | ...)`. The process thinks its PID is 1; the host sees it as 38412.

```bash
# Inspect cgroup limits for the container
CGROUP=$(docker inspect demo --format '{{.HostConfig.CgroupParent}}')
cat /sys/fs/cgroup/memory/docker/<container-id>/memory.limit_in_bytes
```

### Comparing Boot Times

```bash
# VM boot on AWS (m5.large via EC2): measured with instance-start time
time aws ec2 start-instances --instance-ids i-0abc123 && \
  aws ec2 wait instance-running --instance-ids i-0abc123
# real: ~35s

# Container start
time docker run --rm alpine echo hello
# real: ~0.08s
```

### Worked Example — Choosing an Isolation Model

Scenario: multi-tenant SaaS where tenants run arbitrary user code (like a Jupyter notebook).

| Requirement | Bare Metal | VM | Container | Container-on-VM |
|---|:---:|:---:|:---:|:---:|
| Tenant isolation from each other | No | Yes | Partial | Yes |
| Sub-second cold start | Yes | No | Yes | Yes |
| Run untrusted kernel modules | N/A | Yes | No | Yes |
| Memory overhead per workload | — | High | Low | Low-Medium |
| Patch blast radius | Whole machine | One VM | One container | One VM |

**Decision:** For arbitrary user code, use container-on-VM or a security-enhanced runtime (gVisor, Kata Containers). For trusted first-party services, containers on shared VMs are sufficient.

### Security-Enhanced Container Runtimes

When you need container density but stronger isolation than standard Linux namespaces provide:

| Runtime | Mechanism | Trade-off |
|---|---|---|
| **gVisor** (Google) | User-space kernel (Go), intercepts syscalls | ~10-15% perf overhead, strong isolation |
| **Kata Containers** | Lightweight VM per container (QEMU/Firecracker) | Near-VM isolation, ~100 ms startup |
| **Firecracker** | microVM, ≤5 MB memory overhead per VM | Used by AWS Lambda, Fargate |

```bash
# Run a container with gVisor runtime
docker run --runtime=runsc --rm -it alpine sh
```

---

## Use It

### Cloud Managed Kubernetes (Containers on VMs)

AWS EKS, GCP GKE, and Azure AKS provision EC2/Compute/Azure VMs as worker nodes. You deploy containers; the cloud provider manages VM lifecycle. This is model 4 in practice. You never directly see the hypervisor.

### Serverless Functions (Containers on microVMs)

AWS Lambda and Google Cloud Functions use Firecracker microVMs. Each function invocation runs in a microVM that boots in ~125 ms, providing per-request isolation with near-container density. Model 4 with a sub-VM granularity.

### Bare-Metal Cloud

AWS EC2 bare-metal instances (e.g., `i3.metal`), Equinix Metal, and OVHcloud bare metal give you direct hardware access. Use for HPC, latency-sensitive databases (RocksDB on NVMe), or workloads that need hardware features (SR-IOV, DPDK, GPU passthrough) that hypervisors can't fully expose.

### Desktop Virtualization (VDI)

VMs deliver full desktop environments to thin clients. Amazon WorkSpaces and Azure Virtual Desktop use VM-per-user or GPU-partitioned VM models. Not relevant to most backend systems design, but the underlying model is the same Type 1 hypervisor.

### Comparison Summary

| Attribute | Bare Metal | VM | Container | Container on VM |
|---|---|---|---|---|
| Isolation boundary | OS process | Hardware MMU | Linux namespace | Hardware MMU + namespace |
| Startup time | Minutes (provision) | 30–90 s | 50–500 ms | 50–500 ms (container) |
| Memory overhead/unit | Near zero | 2–4 GB | 5–50 MB | 5–50 MB |
| Density (per 64 GB host) | 1 | 8–16 VMs | 100–500 containers | 200–400 containers across VMs |
| Security blast radius | Full machine | VM | Host kernel | VM boundary |
| OS diversity | No | Yes | No (Linux) | No (Linux containers) |
| Kernel exploits affect tenants | N/A | No | Yes | No |

---

## Common Pitfalls

- **Conflating "container" with "isolated"**: Containers share the host kernel. A critical kernel CVE (e.g., Dirty COW, runc CVE-2019-5736) can let a container escape and affect the host or other containers. Always run containers on VMs in multi-tenant environments and keep kernels patched.

- **Thinking VMs are slow because of hypervisors**: Modern Type 1 hypervisors with hardware-assisted virtualization (VT-x/AMD-V) add 1–5% CPU overhead. The slowness people encounter is the OS boot time and the memory tax, not the hypervisor itself. Para-virtualized I/O (virtio) closes the I/O gap almost entirely.

- **Over-privileged containers**: Running containers with `--privileged` or mounting the Docker socket inside a container (`-v /var/run/docker.sock`) effectively gives root on the host. The container provides zero additional isolation in this configuration.

- **Ignoring cgroup memory limits**: Without explicit memory limits (`docker run -m 512m`), a single container can exhaust host memory and trigger the OOM killer on unrelated processes. Always set `resources.limits.memory` in Kubernetes pod specs.

- **Assuming Kubernetes nodes are bare metal**: Most production Kubernetes clusters run on cloud provider VMs. This matters for troubleshooting (you can't reboot the hypervisor), for networking (extra NAT layers), and for performance benchmarks (noisy neighbor effects at the VM level exist even when your containers are isolated from each other).

---

## Exercises

1. **Easy — Trace the isolation boundaries:** For each of these workloads, identify which virtualization model (bare metal, VM, container, container-on-VM) is most likely in use: (a) AWS Lambda function, (b) a process on your developer laptop, (c) a Kubernetes pod on GKE, (d) a VirtualBox VM on your laptop. Justify each answer.

2. **Medium — Cost and density calculation:** A physical host has 256 GB RAM, 64 vCPUs, and you need to run 80 microservices averaging 200 MB RAM and 0.5 CPU each. Calculate whether you can fit them as VMs (assume 3 GB RAM overhead per VM) or as containers (assume 30 MB overhead per container, 8 containers per VM for security). Which model needs fewer physical hosts if you require VM-level isolation?

3. **Hard — Security incident response:** A CVE is announced for the Linux kernel (CVSS 9.0) allowing namespace escape. Your environment uses containers on VMs. Write a runbook: which systems are exposed, in what order do you patch (workers vs. control plane vs. node pools), how do you validate that the patch is applied, and what compensating controls can you deploy immediately while rolling the patch? Consider gVisor and Kata Containers as mitigations.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Hypervisor** | A piece of software that "runs" VMs | A thin layer that multiplexes CPU, RAM, and devices across multiple guest OSes; enforces isolation via hardware MMU traps |
| **Container** | A lightweight virtual machine | A group of Linux processes sharing one kernel but isolated via namespaces and restricted via cgroups — no separate kernel |
| **Namespace** | A DNS or Kubernetes concept | A Linux kernel feature that partitions global resources (PIDs, network interfaces, filesystems) so each group of processes sees its own isolated view |
| **cgroup** | A Kubernetes resource limit | A kernel mechanism for hierarchically limiting, accounting for, and isolating resource usage (CPU, memory, I/O, network) of process groups |
| **Type 1 vs. Type 2 Hypervisor** | Product categories | Type 1 runs directly on hardware (ESXi, KVM, Hyper-V); Type 2 runs on a host OS (VirtualBox, Workstation). The meaningful difference is overhead and where the trusted computing base sits |
| **gVisor / Kata Containers** | Fancy container orchestrators | Security-enhanced container runtimes that add an isolation layer (user-space kernel or per-container microVM) between the container and the host kernel |
| **microVM** | A smaller VM | A VM with a stripped-down kernel and no device emulation overhead, designed to boot in <200 ms with <5 MB overhead (Firecracker architecture) |

---

## Further Reading

- [Linux Namespaces — man7.org](https://man7.org/linux/man-pages/man7/namespaces.7.html) — canonical reference for how each namespace type works at the syscall level
- [cgroups v2 documentation — kernel.org](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html) — official documentation on resource control groups used by every container runtime
- [Firecracker: Lightweight Virtualization for Serverless Applications](https://www.usenix.org/conference/nsdi20/presentation/agache) — USENIX NSDI 2020 paper describing how AWS Lambda achieves microVM isolation at container density
- [gVisor: A User-Space Kernel for Containers — Google](https://gvisor.dev/docs/) — architecture guide explaining how gVisor intercepts syscalls to reduce the attack surface of the host kernel
- [Virtual Machine Monitors: Current Technology and Future Trends — Rosenblum & Garfinkel, IEEE Computer 2005](https://doi.org/10.1109/MC.2005.176) — foundational paper on hypervisor design principles still referenced in systems design literature
