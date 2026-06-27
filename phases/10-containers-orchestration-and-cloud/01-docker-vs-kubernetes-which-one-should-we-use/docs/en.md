# Docker vs. Kubernetes. Which one should we use?

> Docker packages your app; Kubernetes runs a thousand copies of it without you thinking about where.

**Type:** Learn
**Prerequisites:** Linux processes and namespaces, Basic networking (TCP/IP, DNS), Monolith-to-microservices decomposition
**Time:** ~25 minutes

---

## The Problem

Your team has just containerized a Node.js API, a Python worker, and a Redis cache using Docker. On a developer laptop, `docker compose up` brings everything up in seconds. Then you push to production — a single EC2 instance — and it works fine for a few weeks.

Traffic doubles. You add a second EC2 instance and manually pull the new image, run `docker run …` with the right flags, and pray the environment variables match. A container crashes at 3 AM; nobody notices until users start complaining. You scale out to five nodes; now you're SSHing into each box to restart things, manually updating nginx configs for load balancing, and managing five different places where secrets must stay in sync.

This is the exact problem Kubernetes was built to solve — but it is also a problem Docker alone is not designed to solve. The dangerous mistake engineers make is treating Docker and Kubernetes as competitors ("which one?"), when they are actually different layers of the same stack. Choosing the wrong tool — or skipping one altogether — leads either to fragile single-node deployments or to prematurely complex cluster infrastructure for a three-container side project.

---

## The Concept

### What each tool actually owns

| Concern | Docker | Kubernetes |
|---|---|---|
| Scope | Single host | Cluster of hosts |
| Unit of work | Container | Pod (1+ containers) |
| Lifecycle managed | One container at a time | All replicas, all nodes |
| Networking | Bridge/host/overlay per host | Cluster-wide virtual network (CNI) |
| Storage | Volumes on the local host | PersistentVolumes across nodes |
| Scaling | Manual (`docker run` again) | `kubectl scale` or HPA |
| Self-healing | No (unless you add Compose `restart`) | Yes — controller loops restart pods |
| Config/secrets | `-e` flags or `.env` files | ConfigMap + Secret objects |

**Docker** is a container runtime plus image build toolchain. Its job is: take an image, start a process in an isolated namespace, give it a virtual network interface and a writable filesystem layer. Nothing more.

**Kubernetes** is a *control plane* that continuously reconciles desired state → actual state across a fleet of nodes. You declare "I want 5 replicas of image X with 512 MB RAM", and Kubernetes' controllers make that true — and keep it true as nodes fail, images update, and traffic shifts.

### The mental model

```
┌─────────────────────────────────────────────────────┐
│                  Kubernetes Cluster                 │
│                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │    Node 1    │  │    Node 2    │  │  Node 3   │ │
│  │              │  │              │  │           │ │
│  │  ┌────────┐  │  │  ┌────────┐  │  │ ┌──────┐ │ │
│  │  │ Docker │  │  │  │ Docker │  │  │ │Docker│ │ │
│  │  │(runtime)│ │  │  │(runtime)│ │  │ │ (rt) │ │ │
│  │  └────────┘  │  │  └────────┘  │  │ └──────┘ │ │
│  │  Pod  Pod    │  │  Pod  Pod    │  │ Pod       │ │
│  └──────────────┘  └──────────────┘  └───────────┘ │
│                                                     │
│  Control Plane: API Server, Scheduler, etcd, ...    │
└─────────────────────────────────────────────────────┘
```

Kubernetes *uses* a container runtime (Docker, containerd, or CRI-O) on every node. As of Kubernetes 1.24, Docker itself was removed as the direct runtime in favor of **containerd** (which Docker also uses under the hood), but Docker-built images work perfectly — the OCI image spec is shared.

### The spectrum of choices

```
Complexity →
──────────────────────────────────────────────────────►
docker run   docker compose   K8s (self-managed)   Managed K8s (EKS/GKE/AKS)
     │               │                │                        │
  1 container    1–10 containers   10–∞ containers         10–∞ containers
  1 host         1 host            multi-host              multi-host
  dev/scripts    dev + small prod  any prod scale          prod at scale
```

The decision is primarily about *scale and operational burden*, not preference.

---

## Build It / In Depth

### Step 1 — The Docker baseline (single host)

```dockerfile
# Dockerfile for a minimal web service
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --production
COPY . .
EXPOSE 3000
CMD ["node", "server.js"]
```

```bash
# Build and run locally
docker build -t myapp:v1 .
docker run -d -p 3000:3000 --name myapp myapp:v1
```

On one host this is complete. Now imagine needing three replicas, rolling updates, and health checks that restart crashed containers.

### Step 2 — Docker Compose (multi-container, single host)

```yaml
# docker-compose.yml
version: "3.9"
services:
  api:
    image: myapp:v1
    ports: ["3000:3000"]
    environment:
      - REDIS_URL=redis://cache:6379
    restart: unless-stopped
    depends_on: [cache]
  cache:
    image: redis:7-alpine
    volumes:
      - redis-data:/data
volumes:
  redis-data:
```

```bash
docker compose up -d
docker compose scale api=3   # still on ONE host, just multiple processes
```

Compose is excellent for local development and small single-host deployments. Its limits: it knows nothing about multiple hosts, it cannot reschedule a crashed container on a healthy node, and it has no native ingress or secret management.

### Step 3 — Kubernetes equivalent (multi-host, production grade)

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
spec:
  replicas: 3
  selector:
    matchLabels:
      app: myapp
  template:
    metadata:
      labels:
        app: myapp
    spec:
      containers:
        - name: api
          image: myapp:v1
          ports:
            - containerPort: 3000
          resources:
            requests: { cpu: "100m", memory: "128Mi" }
            limits:  { cpu: "500m", memory: "256Mi" }
          readinessProbe:
            httpGet: { path: /health, port: 3000 }
            initialDelaySeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: myapp-svc
spec:
  selector:
    app: myapp
  ports:
    - port: 80
      targetPort: 3000
  type: ClusterIP
```

```bash
kubectl apply -f deployment.yaml
kubectl get pods                        # see 3 replicas scheduled across nodes
kubectl rollout status deployment/myapp # watch the rolling update
kubectl scale deployment/myapp --replicas=10
```

What Kubernetes buys you over Compose here:
- Pods spread across nodes automatically (bin-packing by resources)
- The Deployment controller will restart any pod that fails its readiness probe
- Rolling updates replace pods gradually, with automatic rollback on failure
- The Service gives a stable DNS name (`myapp-svc.default.svc.cluster.local`) regardless of which pods are alive

### Decision flowchart

```
Start: do you need to run containers?
         │
         ▼
  Single host only?
     │         │
    Yes        No
     │         │
     ▼         ▼
  Docker/    Multiple hosts or
  Compose    auto-scaling needed?
             │         │
            Yes        No (just spin up
             │         more VMs manually
             ▼         if you must)
      Is team already       
      managing K8s?   
       │        │     
      Yes       No    
       │        │     
       ▼        ▼     
   Self-managed  Use managed:
   K8s           EKS / GKE / AKS
```

---

## Use It

### When Docker alone (or Compose) is the right answer

- **Local development:** Every engineer on the team runs `docker compose up`. No cluster needed.
- **CI pipelines:** Build the image, run tests inside a container, push to a registry.
- **Single-host hobby projects or internal tools** with low traffic and acceptable downtime.
- **Lambda-like batch jobs** where you invoke a container once, it finishes, and you're done.

### When Kubernetes is the right answer

- **Any stateless web service requiring high availability** (3+ replicas, rolling deploys, zero-downtime)
- **Microservices architectures** with 5+ independently deployable services
- **Auto-scaling under variable load** — Kubernetes HPA scales replicas based on CPU/memory or custom metrics
- **Multi-tenant platforms** where namespace isolation, RBAC, and resource quotas matter
- **GitOps pipelines** using ArgoCD or Flux to declaratively sync cluster state from Git

### Managed vs. self-managed Kubernetes

| Option | Ops burden | Good when |
|---|---|---|
| `kind` / `minikube` | Zero (local) | Local development of K8s manifests |
| `kubeadm` (self-managed) | High (you patch etcd, control plane, CNI) | On-prem with strict data residency |
| EKS (AWS) | Low | Already in AWS, need managed nodes |
| GKE (GCP) | Very low | GKE Autopilot handles node pools |
| AKS (Azure) | Low | Already in Azure |

For most product teams: **start with Docker Compose, migrate to a managed Kubernetes service when you genuinely need multi-host orchestration.** Do not introduce Kubernetes to impress interviewers.

---

## Common Pitfalls

- **Running Kubernetes for a single-container app on one host.** K8s adds real operational weight — etcd, control plane, CNI, RBAC. For a personal project or a simple internal tool, Docker Compose is the correct choice. Premature Kubernetes adoption is a known pattern of over-engineering.

- **Forgetting that Docker was removed as the K8s runtime at 1.24.** Teams that hard-code `--container-runtime=docker` in node setup scripts break silently on modern clusters. The image format (OCI) is unchanged; only the socket path changes. Use `containerd` or `CRI-O` directly.

- **Treating `docker compose scale` as production-grade.** Compose can start multiple container instances on one host, but it shares that host's single point of failure. It is not a substitute for multi-node scheduling.

- **Not setting resource `requests` and `limits` in K8s.** Without them, the scheduler cannot bin-pack correctly, and a memory-leaking pod can starve all other pods on the node. Always set both.

- **Using `latest` image tags in Kubernetes Deployments.** Kubernetes caches images per node. If you push a new `:latest` build, nodes that already have the old image may not pull the update. Pin to a content-addressable digest or a versioned tag (`v1.4.2`) and update the tag on each deploy.

---

## Exercises

1. **Easy** — Take a two-service app (a web server + a database) and write a `docker-compose.yml` that starts both, maps the web port to the host, and uses a named volume for the database data directory. Confirm `docker compose up -d` works and the web server can reach the database.

2. **Medium** — Convert the Compose file from Exercise 1 into Kubernetes manifests: a `Deployment` for the web server (3 replicas), a `StatefulSet` for the database, and a `Service` of type `ClusterIP` for each. Deploy to a local `kind` cluster and verify that deleting one web pod causes Kubernetes to recreate it automatically.

3. **Hard** — Add a Kubernetes `HorizontalPodAutoscaler` to the web server Deployment that scales from 2 to 10 replicas based on CPU utilization (target 60%). Use `kubectl run -it --rm load-generator --image=busybox` to generate synthetic load and observe the HPA scaling behavior. Then write a rollout strategy in the Deployment spec that ensures at most 1 pod is unavailable during a rolling update.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Container** | A lightweight VM | A Linux process isolated via namespaces (PID, net, mount, UTS) sharing the host kernel |
| **Image** | A running app | A read-only, layered filesystem snapshot — the blueprint a container is instantiated from |
| **Pod** | A Kubernetes container | The smallest schedulable unit in K8s — 1+ tightly-coupled containers sharing a network namespace and volumes |
| **Orchestration** | "Kubernetes" as a vague buzzword | Automated scheduling, health management, scaling, and networking of containers across multiple hosts |
| **Docker Compose** | A production deployment tool | A developer tool for defining multi-container apps on a **single host** — not designed for multi-node production |
| **containerd** | Docker's replacement | The OCI-compliant container runtime that both Docker and Kubernetes use under the hood to actually start processes |
| **Control Plane** | The master node | The set of K8s components (API server, scheduler, controller-manager, etcd) that maintain desired state |

---

## Further Reading

- [Docker official documentation — Get started](https://docs.docker.com/get-started/)
- [Kubernetes official documentation — Concepts overview](https://kubernetes.io/docs/concepts/)
- [The Twelve-Factor App](https://12factor.net/) — foundational principles for containerizable services
- [Google's original Borg paper (inspiration for K8s)](https://research.google/pubs/pub43438/) — understanding why the design is the way it is
- [kind (Kubernetes IN Docker)](https://kind.sigs.k8s.io/) — run a full K8s cluster locally for testing manifests before touching production
