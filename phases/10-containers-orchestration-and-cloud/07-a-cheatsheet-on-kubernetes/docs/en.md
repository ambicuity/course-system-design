# A Cheatsheet on Kubernetes

> Kubernetes doesn't run your containers — it continuously reconciles the world you described with the world that exists.

**Type:** Learn
**Prerequisites:** Containers and Docker basics, Microservices architecture, Load balancing
**Time:** ~25 minutes

---

## The Problem

You've containerized your application. Now what? On one machine, `docker run` works fine. But your traffic grows, one instance isn't enough, and hardware fails. You need to run 20 replicas of your API across 10 machines, replace crashed containers automatically, route traffic only to healthy instances, roll out a new version without downtime, and scale down at 2 AM when load drops. None of that is built into Docker itself.

You could write shell scripts. Dozens of them. Scripts that check process health, restart dead containers, rebalance traffic after node failure, and handle deploys. Teams have done exactly this — and every team reinvents the same fragile, untested, undocumented operations infrastructure. On-call engineers carry pagers for the shell scripts.

Kubernetes (K8s) is the answer the industry converged on. Originally developed at Google (descended from their internal Borg/Omega systems), it's now maintained by the CNCF and runs the majority of production container workloads. The core idea: you declare *desired state* in YAML manifests, and K8s runs a continuous reconciliation loop that drives the cluster toward that state — forever. You never say "start container X on node Y." You say "I want 5 replicas of this image, each needing 500m CPU," and K8s figures out where to put them, restarts any that die, and reschedules any whose node goes offline.

---

## The Concept

### The Two Halves: Control Plane and Data Plane

```
┌──────────────────────────────────────────────────────────┐
│                      CONTROL PLANE                       │
│  ┌──────────────┐  ┌────────┐  ┌──────────────────────┐ │
│  │  API Server  │  │  Etcd  │  │  Controller Manager  │ │
│  │  (kube-api)  │  │        │  │  (reconcile loops)   │ │
│  └──────┬───────┘  └────────┘  └──────────────────────┘ │
│         │                ┌─────────────────────────────┐ │
│         │                │       Scheduler             │ │
│         │                │  (which node gets the pod?) │ │
│         │                └─────────────────────────────┘ │
└─────────┼────────────────────────────────────────────────┘
          │ watch / list
┌─────────┼────────────────────────────────────────────────┐
│         │              DATA PLANE (Nodes)                 │
│  ┌──────▼──────┐   ┌──────────┐   ┌──────────────────┐  │
│  │   Kubelet   │   │Kube-proxy│   │  Container Runtime│  │
│  │(node agent) │   │(iptables/│   │  (containerd /   │  │
│  │             │   │ ipvs)    │   │   CRI-O)         │  │
│  └─────────────┘   └──────────┘   └──────────────────┘  │
│         Node 1           Node 2           Node 3          │
└──────────────────────────────────────────────────────────┘
```

**Control Plane components:**

| Component | Role |
|---|---|
| **API Server** | The single entry point for all cluster operations. Every `kubectl` command, every controller, every Kubelet talks to the API Server over HTTPS. Stateless — persists nothing itself. |
| **Etcd** | Distributed key-value store. Holds the entire cluster state. If etcd is lost, the cluster state is gone. Always run etcd with 3 or 5 members (quorum). |
| **Controller Manager** | Runs dozens of controllers as goroutines (Deployment controller, ReplicaSet controller, Node controller, etc.). Each controller watches its resource type and reconciles actual → desired state. |
| **Scheduler** | Watches for unscheduled Pods and assigns each to a Node using scoring functions: resource requests/limits, taints/tolerations, affinity rules, topology spread. |

**Node components:**

| Component | Role |
|---|---|
| **Kubelet** | The node agent. Watches the API Server for Pods assigned to its node, tells the container runtime to start/stop them, reports back health. |
| **Kube-proxy** | Implements Service networking — programs iptables or IPVS rules so that cluster-internal traffic to a Service VIP reaches the right Pod(s). |
| **Container Runtime** | The thing that actually runs containers (containerd, CRI-O). Kubernetes talks to it via the CRI (Container Runtime Interface). Docker was replaced here in K8s 1.24+. |

### The Core Resources

**Pod** — The smallest deployable unit. A Pod wraps one or more containers that share a network namespace (same IP) and can share volumes. You almost never create Pods directly — higher-level controllers do it for you.

**Deployment** — Declares "I want N replicas of this Pod spec." Manages a ReplicaSet, which manages the actual Pods. Handles rolling updates, rollbacks, and scaling. The workhorse for stateless apps.

**Service** — Gives a stable DNS name and virtual IP to a dynamic set of Pods selected by label. Traffic to the Service VIP is load-balanced across matching Pods. Four types:
- `ClusterIP` — internal only (default)
- `NodePort` — exposes on each node's IP at a static port
- `LoadBalancer` — provisions a cloud load balancer
- `ExternalName` — maps to a DNS name

**ConfigMap / Secret** — Decouple configuration from image. Secrets are base64-encoded (not encrypted by default — use encryption at rest or an external secrets manager in production).

**PersistentVolume / PersistentVolumeClaim** — Abstract storage from the node. A PVC is a request for storage; a PV is the actual storage resource. StorageClasses enable dynamic provisioning.

**Namespace** — Virtual cluster within a cluster. Use it for team/environment isolation, resource quota enforcement, and RBAC scoping.

### The Reconciliation Loop (How It Actually Works)

Every controller in K8s runs the same loop:

```
1. Watch: observe the current state via API Server
2. Diff:  compare current state to desired state
3. Act:   call APIs to bring current → desired
4. Sleep: go back to step 1
```

This is why K8s is *eventually consistent* and self-healing. If you manually kill a Pod, the ReplicaSet controller notices the diff within seconds and creates a replacement. The system doesn't need you to issue a "restart" command — it just corrects itself.

---

## Build It / In Depth

### Step 1 — Write a Deployment manifest

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
      maxSurge: 1         # create 1 extra pod before killing old ones
      maxUnavailable: 0   # never go below desired replica count
  template:
    metadata:
      labels:
        app: api-server
    spec:
      containers:
        - name: api
          image: myrepo/api-server:v2.3.1
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
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
    app: api-server        # matches Pods with this label
  ports:
    - protocol: TCP
      port: 80             # Service listens here
      targetPort: 8080     # forwards to container port
  type: ClusterIP
```

### Step 3 — Apply and verify

```bash
kubectl apply -f deployment.yaml -f service.yaml

# watch rollout progress
kubectl rollout status deployment/api-server -n production

# see pods and which node they landed on
kubectl get pods -n production -o wide

# describe a pod for events/probe failures
kubectl describe pod <pod-name> -n production

# check logs
kubectl logs -n production -l app=api-server --tail=100 -f
```

### Step 4 — Add autoscaling

```yaml
# hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-server-hpa
  namespace: production
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
          averageUtilization: 60   # scale up if avg CPU > 60%
```

The HPA polls metrics every 15 seconds (default) and adjusts replica count. It requires the Metrics Server to be installed in the cluster to read CPU/memory from Kubelet.

### Rolling Update Flow

```
Before:  [v1] [v1] [v1]           3 old pods
Step 1:  [v1] [v1] [v1] [v2]     surge=1, create new pod
Step 2:  [v1] [v1] [v2]          new pod ready, kill one old
Step 3:  [v1] [v2] [v2]          repeat
Step 4:  [v2] [v2] [v2]          done, zero downtime
```

Rollback is one command: `kubectl rollout undo deployment/api-server -n production`

---

## Use It

| Scenario | Recommended K8s resource |
|---|---|
| Stateless API or web app | Deployment + Service + HPA |
| Stateful database / message broker | StatefulSet (stable network IDs + ordered starts) |
| Node-level agent (log collector, monitoring) | DaemonSet (one Pod per node) |
| One-off batch job | Job |
| Periodic scheduled task (cron) | CronJob |
| Shared config across Pods | ConfigMap |
| Credentials (DB passwords, API keys) | Secret + external secrets manager |
| Dynamic persistent storage (EBS, GCP PD) | StorageClass + PVC |
| Ingress routing / TLS termination | Ingress + Ingress controller (NGINX, Traefik, AWS ALB) |
| Traffic management, retries, canary | Service Mesh (Istio, Linkerd) |

**Cloud-managed K8s (recommended for most teams):**
- AWS EKS — control plane managed, integrate with IAM, ALB, EBS
- GCP GKE — autopilot mode fully manages node pools
- Azure AKS — tight Azure AD / ACR integration

Managed K8s offloads etcd backups, control-plane upgrades, and node patching. Unless you have a specific reason to self-host, use managed.

---

## Common Pitfalls

- **No resource requests set.** Without `resources.requests`, the Scheduler can't make good placement decisions, and nodes can be OOM-killed unexpectedly. Always set both `requests` (for scheduling) and `limits` (for enforcement). A common start: requests = 50% of limits.

- **No readiness/liveness probes.** Without a readiness probe, a newly started Pod receives traffic before it's ready. Without a liveness probe, a deadlocked app never gets restarted. Both are essential in production.

- **Storing sensitive data in ConfigMaps.** ConfigMaps are plaintext. Secrets are base64 — not encrypted unless you enable `EncryptionConfiguration` on the API Server or use a solution like Sealed Secrets, AWS Secrets Manager, or HashiCorp Vault.

- **Using `latest` image tag.** This makes rollbacks impossible (you can't tell which image is "the one before this"), breaks reproducibility, and can silently pull a broken image on the next pod restart. Always tag images with a commit SHA or semantic version.

- **Ignoring Pod Disruption Budgets (PDBs) during upgrades.** When nodes are drained for upgrades, K8s can evict all replicas of a Deployment at once unless you define a PDB. Set `minAvailable: 1` (or `maxUnavailable: 1`) to guarantee at least one replica stays up during voluntary disruptions.

---

## Exercises

1. **Easy** — Write a Deployment manifest for an Nginx container with 2 replicas. Add a ClusterIP Service that routes port 80 to the container's port 80. Apply it to a local cluster (minikube or kind) and verify with `kubectl get all`.

2. **Medium** — Deploy the same Nginx Deployment with a rolling update strategy (`maxUnavailable: 0`, `maxSurge: 1`). Update the image to a newer Nginx version, watch the rollout, then immediately roll back and observe what happened to ReplicaSets.

3. **Hard** — Add an HPA to the Deployment targeting 50% CPU utilization. Use a load generator (e.g., `kubectl run -it load --image=busybox -- /bin/sh` + `wget` loop) to push CPU above the threshold. Observe the HPA scale up. Remove the load and observe scale-down (note the stabilization window — why is scale-down slower than scale-up?).

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Pod** | A container | A group of one or more containers sharing a network namespace and optional volumes; the smallest schedulable unit |
| **Deployment** | Runs containers | A controller that manages ReplicaSets, which manage Pods — handles rolling updates and declarative scaling |
| **Service** | A load balancer | A stable virtual IP + DNS name that proxies traffic to a matching set of Pods via iptables/IPVS rules |
| **Namespace** | An environment (dev/prod) | A virtual partition within a cluster for access control, resource quotas, and name scoping — not a security boundary |
| **Etcd** | A K8s database | A distributed consensus key-value store (Raft protocol) that is the single source of truth for all cluster state |
| **HPA** | Auto-scaling | The Horizontal Pod Autoscaler — adjusts replica count in response to metrics; does not resize individual containers (that's VPA) |
| **Rolling Update** | Zero-downtime deploy | A controlled replacement of old Pods with new ones, governed by `maxSurge` and `maxUnavailable` parameters |

---

## Further Reading

- [Kubernetes Official Documentation](https://kubernetes.io/docs/home/) — the reference; the Concepts section explains the mental models
- [The Illustrated Children's Guide to Kubernetes](https://www.cncf.io/phippy/) — CNCF's visual explainer; surprisingly effective for building the core mental model
- [Kubernetes Patterns (book) — Bilgin Ibryam & Roland Huß, O'Reilly](https://www.oreilly.com/library/view/kubernetes-patterns/9781492050278/) — catalog of production-grade patterns: sidecar, ambassador, adapter, etc.
- [Production Kubernetes (book) — Josh Rosso et al., O'Reilly](https://www.oreilly.com/library/view/production-kubernetes/9781492092292/) — covers what the official docs skip: multi-tenancy, networking deep dives, and upgrade strategies
- [kubectl Cheat Sheet](https://kubernetes.io/docs/reference/kubectl/cheatsheet/) — the official quick reference for the commands you'll use daily
