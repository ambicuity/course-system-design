# Docker vs Kubernetes

> Docker packages your app; Kubernetes runs it at scale — they solve fundamentally different problems.

**Type:** Learn
**Prerequisites:** Virtualization vs Containers, Microservices Architecture
**Time:** ~25 minutes

---

## The Problem

You've containerized your Node.js API with Docker. It runs perfectly on your laptop. You push the image to a registry and SSH into a single production VM to run `docker run -p 80:80 my-api`. Everything works — until it doesn't. Traffic spikes and you need three more instances. You SSH in again and run three more `docker run` commands, manually tracking which ports are used. One container crashes at 2 AM. Nobody notices for four hours. You need to update the image, so you `docker stop` and `docker run` each container in sequence, creating a window of reduced capacity.

This is the scaling and resilience wall. Managing containers across more than one machine, keeping them healthy, routing traffic, rolling out updates without downtime, and handling node failures — none of this is part of Docker's scope. Docker's job ends when the container starts.

Kubernetes exists precisely for this gap. It treats your containers as workloads to be scheduled, supervised, networked, and scaled across a fleet of machines. Understanding what each tool does — and more critically, what each tool does *not* do — is the foundation for any production container strategy.

---

## The Concept

### What Docker Actually Is

Docker is a toolchain for building and running containers on a single host. Its core abstractions are:

- **Image**: A read-only, layered filesystem snapshot. Built from a `Dockerfile`. Portable across any OCI-compliant runtime.
- **Container**: A running instance of an image, isolated via Linux namespaces (PID, network, mount, UTS, IPC) and resource-bounded via cgroups.
- **Registry**: A content-addressable store for images (Docker Hub, ECR, GCR, GHCR).
- **Docker Engine**: The daemon that manages the container lifecycle on one host.

```
Dockerfile
    │
    ▼
docker build ──► Image (layers in /var/lib/docker)
                     │
                     ▼
               docker run ──► Container (running process)
                                   │
                                   ▼
                              Host Network / Volumes
```

Docker answers: *"How do I run this process in a reproducible, isolated environment?"*

### What Kubernetes Actually Is

Kubernetes (k8s) is a container orchestration system. It does not build images — it consumes them. Its job is to declare *what* should run and ensure the cluster converges to that state, regardless of machine failures or load changes.

Core Kubernetes abstractions:

- **Pod**: The smallest schedulable unit. One or more tightly coupled containers sharing a network namespace and storage volumes. Think of it as a "logical host" for your containers.
- **Node**: A physical or virtual machine that runs Pods. Has a kubelet (agent) and kube-proxy (network rules).
- **Control Plane**: The brain of the cluster — API server, etcd (distributed state store), scheduler, and controller manager.
- **Deployment**: Declares the desired state (e.g., "run 3 replicas of image X"). The controller reconciles actual vs desired continuously.
- **Service**: A stable virtual IP + DNS name that load-balances traffic across a set of Pods.

```
┌─────────────────────────────────────────────┐
│              CONTROL PLANE                  │
│  ┌──────────┐ ┌──────┐ ┌─────────────────┐ │
│  │ API      │ │ etcd │ │ Controller Mgr  │ │
│  │ Server   │ │      │ │ + Scheduler     │ │
│  └──────────┘ └──────┘ └─────────────────┘ │
└────────────────────┬────────────────────────┘
                     │ watches / instructs
        ┌────────────┼────────────┐
        ▼            ▼            ▼
  ┌──────────┐ ┌──────────┐ ┌──────────┐
  │  Node 1  │ │  Node 2  │ │  Node 3  │
  │ ┌──────┐ │ │ ┌──────┐ │ │ ┌──────┐ │
  │ │ Pod  │ │ │ │ Pod  │ │ │ │ Pod  │ │
  │ └──────┘ │ │ └──────┘ │ │ └──────┘ │
  │ kubelet  │ │ kubelet  │ │ kubelet  │
  └──────────┘ └──────────┘ └──────────┘
```

Kubernetes answers: *"How do I keep the right containers running on the right machines, at the right scale, without manual intervention?"*

### Side-by-Side Comparison

| Dimension | Docker (standalone) | Kubernetes |
|---|---|---|
| **Scope** | Single host | Cluster of hosts |
| **Unit of work** | Container | Pod |
| **State management** | Manual (`docker run/stop`) | Declarative (YAML manifests) |
| **Self-healing** | None — crashed containers stay down | Restarts, reschedules Pods automatically |
| **Scaling** | Manual (`docker run` N times) | `kubectl scale` or Horizontal Pod Autoscaler |
| **Rolling updates** | Manual stop/start each instance | Built-in rollout with configurable strategy |
| **Service discovery** | Manual / compose networks | DNS-based, built-in via Services |
| **Load balancing** | Not built-in | kube-proxy + Ingress controllers |
| **Secret management** | env vars or bind mounts | Kubernetes Secrets (with encryption at rest) |
| **Multi-tenancy** | Namespaces via Compose projects | Namespaces, RBAC, NetworkPolicies |
| **Learning curve** | Low | Steep |
| **Operational overhead** | Minimal | Significant (control plane, etcd, upgrades) |

### The Reconciliation Loop — Kubernetes' Core Idea

Kubernetes is built on a single mental model: **desired state vs actual state**. Every controller runs a loop:

```
observe actual state
  if actual != desired:
    take action to close the gap
```

A Deployment controller watches etcd for the desired replica count. If a Pod crashes, actual < desired. The controller creates a new Pod. The scheduler finds a node with enough CPU/memory. The kubelet on that node pulls the image and starts the container. This entire chain happens automatically, typically in under 30 seconds.

This declarative model means you never directly manipulate running containers in production — you change the manifest, and the cluster self-corrects.

---

## Build It / In Depth

### Step 1 — Build and Push an Image (Docker's Domain)

```dockerfile
# Dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY src/ ./src/
EXPOSE 3000
CMD ["node", "src/index.js"]
```

```bash
docker build -t my-registry.io/my-api:v1.2.0 .
docker push my-registry.io/my-api:v1.2.0
```

This is the last Docker-specific step. Everything from here is Kubernetes.

### Step 2 — Declare a Deployment

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-api
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: my-api
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
  template:
    metadata:
      labels:
        app: my-api
    spec:
      containers:
        - name: api
          image: my-registry.io/my-api:v1.2.0
          ports:
            - containerPort: 3000
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "256Mi"
          readinessProbe:
            httpGet:
              path: /health
              port: 3000
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /health
              port: 3000
            failureThreshold: 3
            periodSeconds: 30
```

```bash
kubectl apply -f deployment.yaml
kubectl rollout status deployment/my-api -n production
```

The `RollingUpdate` strategy ensures at most 1 Pod is unavailable during the update. Kubernetes cycles through old Pods as new ones pass their `readinessProbe`.

### Step 3 — Expose It with a Service

```yaml
# service.yaml
apiVersion: v1
kind: Service
metadata:
  name: my-api-svc
  namespace: production
spec:
  selector:
    app: my-api
  ports:
    - port: 80
      targetPort: 3000
  type: ClusterIP  # internal; pair with an Ingress for external traffic
```

```bash
kubectl apply -f service.yaml
# Verify Pods behind the service
kubectl get endpoints my-api-svc -n production
```

### Step 4 — Autoscale

```bash
# Scale to 5 replicas manually
kubectl scale deployment/my-api --replicas=5 -n production

# Or configure HorizontalPodAutoscaler
kubectl autoscale deployment my-api \
  --cpu-percent=60 \
  --min=3 \
  --max=10 \
  -n production
```

---

## Use It

### When Docker Standalone Is Enough

| Scenario | Why Docker Alone Works |
|---|---|
| Local development | Single-machine, no HA needed |
| CI build/test pipeline | Short-lived, scripted — no orchestration |
| Single-host small app | < 2 containers, predictable load |
| Side projects / prototypes | Overhead of k8s is not justified |

Use Docker Compose for multi-container local dev (`docker compose up`). It is not a production orchestrator.

### When You Need Kubernetes

| Scenario | What Kubernetes Adds |
|---|---|
| Multi-service production system | Scheduling, placement, health management |
| Traffic spikes / variable load | HPA scales replicas in seconds |
| Zero-downtime deployments | Rolling updates, canary via Argo Rollouts |
| Multi-region / multi-zone | Pod anti-affinity, topology spread constraints |
| Team isolation | Namespaces + RBAC per team |
| GPU workloads (ML training) | Node taints and tolerations route jobs to GPU nodes |

### Managed Kubernetes Options

| Provider | Service | When to Reach For It |
|---|---|---|
| AWS | EKS | Tight integration with IAM, ALB, EBS |
| GCP | GKE | Autopilot mode for hands-off node management |
| Azure | AKS | Windows container support, AAD integration |
| Self-hosted | k3s / kubeadm | On-prem or resource-constrained edge |
| Minimal k8s | k3s | Raspberry Pi clusters, IoT edge |

Docker Compose is sometimes combined with tools like **Portainer** or **Dokku** as a lighter-weight alternative to k8s for small production deployments. Valid choice for teams where k8s operational overhead exceeds the benefit.

---

## Common Pitfalls

- **Running Docker in production without orchestration.** `docker run --restart=always` is not self-healing. It restarts on the same node — if the node goes down, your app goes down. You need Kubernetes (or at minimum Docker Swarm) for cross-node resilience.

- **Conflating the image build pipeline with deployment.** Docker builds the image; Kubernetes deploys it. Teams sometimes try to `docker build` inside Kubernetes pods during deployment, coupling the build and runtime environments. Use a separate CI system (GitHub Actions, Buildkite) to build and push; Kubernetes only pulls.

- **Ignoring resource `requests` and `limits`.** Without these, the Kubernetes scheduler cannot make placement decisions, and one noisy Pod can starve its neighbors. Always set both. `requests` determines scheduling; `limits` triggers OOM kills.

- **Skipping readiness probes.** Without a `readinessProbe`, Kubernetes routes traffic to a Pod as soon as the container process starts — before your app is actually ready. During a rolling update, this means requests hit a half-started instance. Add a `/health` endpoint and always configure `readinessProbe`.

- **Using `latest` tag in production.** Kubernetes caches images per `imagePullPolicy`. `latest` with `IfNotPresent` (the default) means nodes may run stale images after a push. Always use immutable, versioned tags (`v1.2.0`, git SHA) in production manifests.

---

## Exercises

1. **Easy — Build and run locally.** Write a `Dockerfile` for any simple HTTP server (pick a language). Build the image, run a container, verify it responds on `localhost:8080`. Then write a `docker-compose.yml` that runs it alongside a Redis container and confirm the app can connect to Redis by hostname.

2. **Medium — Deploy to a local cluster.** Install `minikube` or `kind`. Write a Deployment manifest for the same app with 3 replicas and a liveness probe. Apply it, then manually `kubectl delete pod <one-pod>` and observe Kubernetes recreate it. Write a Service manifest and verify you can reach the app through the ClusterIP from another Pod in the cluster.

3. **Hard — Zero-downtime rolling update.** Using your local cluster from Exercise 2, configure a `RollingUpdate` strategy with `maxUnavailable: 0` and `maxSurge: 1`. In one terminal, run a loop that continuously `curl`s the app's `/version` endpoint. In another terminal, update the Deployment to a new image tag. Observe: does the rolling update produce any errors? Now introduce a bad image tag and observe how `maxUnavailable: 0` plus a misconfigured `readinessProbe` interacts with the rollout — does it halt or complete?

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Container** | A lightweight VM | A process isolated via Linux namespaces and bounded by cgroups — shares the host kernel |
| **Image** | A running thing | A static, layered filesystem snapshot; it doesn't "run" until instantiated as a container |
| **Pod** | A Kubernetes container | One or more containers that share a network namespace and lifecycle; the smallest schedulable unit |
| **Orchestration** | Kubernetes is just "running containers" | Desired-state reconciliation: scheduling, health management, scaling, networking, and rollout automation |
| **kubectl apply** | Pushes a config to the cluster | Sends a manifest to the API server; controllers then reconcile actual state toward desired state |
| **Service** | A load balancer | A stable virtual IP + DNS name backed by kube-proxy rules — it selects Pods via label selectors |
| **etcd** | A database for configs | A distributed, strongly-consistent key-value store that is the *sole* source of truth for all cluster state |

---

## Further Reading

- [Docker Official Docs — Dockerfile reference](https://docs.docker.com/engine/reference/builder/)
- [Kubernetes Official Docs — Concepts overview](https://kubernetes.io/docs/concepts/)
- [Kubernetes — Deployments and rolling updates](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Google SRE Book — Chapter 7: The Evolution of Automation at Google](https://sre.google/sre-book/the-evolution-of-automation/) — context for why declarative orchestration matters
- [Brendan Burns et al., "Borg, Omega, and Kubernetes" (ACM Queue, 2016)](https://queue.acm.org/detail.cfm?id=2898444) — the lineage and design rationale behind Kubernetes from its creators
