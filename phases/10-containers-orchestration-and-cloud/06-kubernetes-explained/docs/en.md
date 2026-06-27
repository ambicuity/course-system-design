# Kubernetes Explained

> Kubernetes is a distributed operating system for containers — it schedules, heals, and scales your workloads so you don't have to babysit servers.

**Type:** Learn
**Prerequisites:** Containers and Docker, CAP Theorem, Load Balancing
**Time:** ~35 minutes

---

## The Problem

You've packaged your service into a Docker image. On your laptop, `docker run` works perfectly. In production, you have 20 containers across 8 VMs. When traffic spikes, you need 40 containers. When a VM reboots, 5 containers die and need restarting. When you ship a new version, you need to roll it out without downtime. When two services need to talk to each other, they need a stable address even though containers come and go. None of this is solved by Docker alone.

The naive solution is a fleet of shell scripts, cron jobs, and custom monitoring daemons. Teams at Google, Twitter, and Netflix built exactly these systems in the 2000s — and all of them reinvented the same concepts independently. Google's internal system, Borg, ran billions of containers per week. In 2014, Google open-sourced a redesigned version of those ideas as Kubernetes (Greek for "helmsman").

Without an orchestrator, you end up owning: bin-packing logic (which container fits on which VM?), health checking and restart loops, rolling update coordination, service discovery, secret distribution, resource quotas, and autoscaling triggers. Kubernetes is the single system that handles all of it through a consistent declarative API.

---

## The Concept

### Declarative vs. Imperative

The mental shift that makes Kubernetes click: **you declare desired state, Kubernetes reconciles reality toward it.**

Instead of: "SSH into VM 3, `docker stop app_v1`, `docker run app_v2`…"
You say: "I want 5 replicas of app, running image v2."

Control loops continuously compare actual state to desired state and make corrective moves. This is the reconciliation loop — the heartbeat of every Kubernetes controller.

### Architecture: Two Planes

```
┌──────────────────────────────────────────────────────────┐
│                     CONTROL PLANE                        │
│                                                          │
│  ┌──────────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │  API Server  │  │ Scheduler │  │ Controller Mgr   │  │
│  │  (kube-       │  │           │  │  - ReplicaSet    │  │
│  │   apiserver) │  │  Watches  │  │  - Deployment    │  │
│  │              │  │  unbound  │  │  - Node          │  │
│  │  Single      │  │  Pods,    │  │  - Endpoint      │  │
│  │  source of   │  │  assigns  │  │  controllers     │  │
│  │  truth for   │  │  Nodes    │  └──────────────────┘  │
│  │  all state   │  └───────────┘                        │
│  └──────┬───────┘                                        │
│         │  reads/writes                                  │
│  ┌──────▼───────┐                                        │
│  │     etcd     │  ← distributed key-value store        │
│  │  (cluster    │    (Raft consensus, 3 or 5 nodes)      │
│  │   state DB)  │                                        │
│  └──────────────┘                                        │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│                   WORKER NODES (many)                    │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Node                                              │  │
│  │                                                    │  │
│  │  ┌──────────┐  ┌──────────┐  ┌─────────────────┐  │  │
│  │  │  kubelet │  │kube-proxy│  │Container Runtime│  │  │
│  │  │          │  │          │  │(containerd/CRI-O│  │  │
│  │  │ Watches  │  │ Programs │  │)                │  │  │
│  │  │ API Svr, │  │ iptables/│  └─────────────────┘  │  │
│  │  │ ensures  │  │ eBPF for │                        │  │
│  │  │ Pods run │  │ svc IPs  │  ┌────────┐ ┌───────┐  │  │
│  │  └──────────┘  └──────────┘  │ Pod A  │ │ Pod B │  │  │
│  │                               └────────┘ └───────┘  │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

### Core Primitives

| Object | What it is | Key field |
|---|---|---|
| **Pod** | One or more containers sharing a network namespace and storage | `spec.containers` |
| **ReplicaSet** | Ensures N copies of a Pod template always run | `spec.replicas` |
| **Deployment** | Manages ReplicaSets; owns rolling updates and rollbacks | `spec.strategy` |
| **Service** | Stable virtual IP + DNS name for a set of Pods | `spec.selector` |
| **ConfigMap** | Non-secret configuration injected as env vars or files | `data` |
| **Secret** | Base64-encoded sensitive config (token, password, cert) | `data` (base64) |
| **Namespace** | Virtual cluster; scopes names and RBAC | `metadata.namespace` |
| **Ingress** | HTTP/HTTPS routing rules pointing at Services | `spec.rules` |
| **PersistentVolume** | A piece of storage provisioned by an admin or StorageClass | `spec.capacity` |

### How the Scheduler Works

When you create a Pod with no Node assigned, it sits in `Pending`. The scheduler watches for unbound Pods and runs two phases:

1. **Filtering** — Eliminate nodes that can't run the Pod (not enough CPU/RAM, taint doesn't tolerate Pod's tolerations, affinity rules not satisfied).
2. **Scoring** — Rank remaining nodes by priority functions (prefer nodes with the image already pulled, spread replicas across zones, least-requested resources first).

The Pod is then bound to the highest-scoring Node by writing `spec.nodeName` back to the API server. The kubelet on that Node sees this and starts the container.

### etcd: The Ground Truth

Everything in the cluster — every Pod spec, every Service endpoint, every Secret — lives in etcd. The API server is stateless; etcd is the database. This is why:
- etcd must be backed up continuously (use `etcdctl snapshot save`).
- Running 3 or 5 etcd members (not 2 or 4) ensures quorum survives one node loss.
- Writes to any Kubernetes resource go through the API server to etcd, never directly.

### Services and kube-proxy

When you create a Service with `type: ClusterIP`, Kubernetes assigns it a virtual IP (VIP) from the cluster CIDR. This IP never changes, even as Pods behind it are replaced. kube-proxy watches the Endpoints object (list of Pod IPs) and programs iptables or eBPF rules so traffic to the VIP gets load-balanced across healthy Pods.

DNS is handled by CoreDNS (a cluster addon): every Service gets a record at `<service>.<namespace>.svc.cluster.local`.

---

## Build It / In Depth

### Step 1 — A minimal Deployment

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api-server
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1   # at most 1 Pod down during rollout
      maxSurge: 1         # at most 1 extra Pod during rollout
  template:
    metadata:
      labels:
        app: api-server
    spec:
      containers:
        - name: api
          image: myregistry/api:v2.4.1
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: "250m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "256Mi"
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 15
            periodSeconds: 20
```

```bash
kubectl apply -f deployment.yaml
kubectl rollout status deployment/api-server
```

### Step 2 — Expose it with a Service

```yaml
# service.yaml
apiVersion: v1
kind: Service
metadata:
  name: api-server-svc
  namespace: production
spec:
  selector:
    app: api-server       # matches Pods with this label
  ports:
    - port: 80
      targetPort: 8080
  type: ClusterIP          # internal only; use LoadBalancer for external
```

```bash
kubectl apply -f service.yaml
kubectl get endpoints api-server-svc   # shows the 3 Pod IPs
```

### Step 3 — Rolling update

```bash
# Update image tag — triggers a rolling update
kubectl set image deployment/api-server api=myregistry/api:v2.5.0

# Watch Pods cycle one at a time (maxUnavailable: 1)
kubectl rollout status deployment/api-server --watch

# If v2.5.0 is broken, roll back instantly
kubectl rollout undo deployment/api-server
```

### Step 4 — Autoscaling

```yaml
# hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-server-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-server
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70   # scale out when avg CPU > 70%
```

```bash
kubectl apply -f hpa.yaml
kubectl get hpa api-server-hpa --watch
```

### What happens when a Node dies

```
Node dies
   │
   ▼
kubelet stops sending heartbeats to API Server
   │
   ▼  (~40s by default: node-monitor-grace-period)
Node Controller marks Node as NotReady
   │
   ▼  (~5min: pod-eviction-timeout)
Pods on the dead Node are marked for deletion
   │
   ▼
ReplicaSet controller sees replica count < desired
   │
   ▼
New Pods scheduled on healthy Nodes
```

---

## Use It

### Managed Kubernetes Services

| Provider | Service | When to choose |
|---|---|---|
| AWS | EKS | Already in AWS, need Fargate serverless nodes |
| Google Cloud | GKE | Best autopilot mode, Anthos for multi-cloud |
| Azure | AKS | Windows containers, Azure AD integration |
| DigitalOcean | DOKS | Simpler billing, smaller teams |
| Self-hosted | kubeadm / k3s | Air-gapped, cost control, edge |

**k3s** (Rancher) is a production-grade Kubernetes distro that runs in ~512 MB RAM — ideal for edge devices, CI runners, and small clusters.

### Key Ecosystem Tools

| Tool | Problem it solves |
|---|---|
| **Helm** | Package manager — bundle K8s manifests into versioned charts |
| **Kustomize** | Template-free config overlay (built into kubectl) |
| **Argo CD** | GitOps: sync cluster state to a Git repo |
| **Istio / Linkerd** | Service mesh: mTLS, traffic shaping, observability |
| **Cert-manager** | Automate TLS certificate issuance and renewal |
| **Prometheus + Grafana** | Metrics scraping and dashboards |
| **Cluster Autoscaler** | Add/remove Nodes based on pending Pod demand |
| **Velero** | Backup and restore cluster resources + volumes |

---

## Common Pitfalls

- **No resource requests or limits.** Without `resources.requests`, the scheduler can't bin-pack safely — Pods land on the same Node until it OOM-kills them. Always set both `requests` (scheduling) and `limits` (enforcement).

- **Skipping readiness probes.** If a Pod doesn't have a `readinessProbe`, the Service sends traffic the moment the container starts, before the app is initialized. This causes 502s during rollouts. A readiness probe gates traffic; a liveness probe gates restart decisions — they serve different purposes.

- **Storing state in Pods.** Pods are ephemeral. Writing to the local filesystem means losing data every restart. Use PersistentVolumeClaims for databases, or use managed cloud storage (S3, Cloud SQL) for anything that must survive.

- **One big namespace for everything.** Namespaces provide RBAC boundaries, network policy scopes, and resource quotas. Separating `production`, `staging`, and `tooling` namespaces prevents accidental cross-environment mutations and enforces least-privilege access.

- **Ignoring etcd backup.** etcd holds all cluster state. If it's lost and you have no backup, the cluster is unrecoverable — you'd have to recreate every Deployment, Service, and Secret by hand. Schedule `etcdctl snapshot save` to durable storage at least hourly.

---

## Exercises

1. **Easy** — Create a Deployment running `nginx:latest` with 2 replicas in a namespace called `sandbox`. Expose it with a ClusterIP Service on port 80. Verify both Pods appear in the Service's Endpoints. Then scale the Deployment to 4 replicas and confirm.

2. **Medium** — Add a `HorizontalPodAutoscaler` to your Deployment targeting 60% average CPU utilization, min 2 replicas, max 10. Use `kubectl run -it --rm load --image=busybox -- /bin/sh` to generate load with a wget loop against the Service IP. Watch the HPA scale out, then let it cool down and scale back in.

3. **Hard** — Deploy a stateful workload using a `StatefulSet` (e.g., a single-node Redis). Attach a `PersistentVolumeClaim` using your cluster's default `StorageClass`. Write a key to Redis, delete the Pod, and confirm the data survives when Kubernetes restarts the Pod on the same PVC. Then configure a `PodDisruptionBudget` to ensure at least one replica is always available during voluntary disruptions.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Pod** | Same as a container | One or more containers sharing a network namespace, IP, and volumes — the atomic scheduling unit |
| **Service** | A running process | A stable virtual IP + DNS name backed by an Endpoints list that routes to healthy Pods |
| **Deployment** | What runs your containers | A controller that manages ReplicaSets, which manage Pods — owns rolling updates and rollback history |
| **Namespace** | Just a folder | A virtual cluster with its own RBAC scope, resource quotas, and network policy boundaries |
| **Node** | A Kubernetes server | A physical or virtual machine running `kubelet` + `kube-proxy` + a container runtime, managed by the control plane |
| **etcd** | Kubernetes's database | A distributed Raft-consensus key-value store that holds every object in the cluster; if lost without backup, the cluster is unrecoverable |
| **Ingress** | A load balancer | A set of L7 routing rules (host/path matching) processed by an Ingress Controller (nginx, Envoy, etc.) installed separately |

---

## Further Reading

- [Kubernetes Official Documentation](https://kubernetes.io/docs/home/) — the authoritative reference for every API object and concept
- [Kubernetes: Up and Running, 3rd ed. — Hightower, Burns, Beda](https://www.oreilly.com/library/view/kubernetes-up-and/9781098110192/) — the canonical practical book by Kubernetes co-creators
- [The Kubernetes Book — Nigel Poulton](https://leanpub.com/thekubernetesbook) — dense, up-to-date, concise reference ideal for engineers already comfortable with containers
- [Production Kubernetes — Rosso & Harris (O'Reilly)](https://www.oreilly.com/library/view/production-kubernetes/9781492092292/) — covers multi-tenancy, security hardening, storage, and running K8s at scale
- [learnk8s.io/troubleshooting-deployments](https://learnk8s.io/troubleshooting-deployments) — flowchart-based guide for diagnosing why Pods are stuck in Pending, CrashLoopBackOff, or ImagePullBackOff
