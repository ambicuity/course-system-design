# How Kubernetes Works?

> Kubernetes turns a fleet of machines into a single programmable computer that keeps your containers alive and correctly placed — forever.

**Type:** Learn
**Prerequisites:** Containers & Docker, Microservices Architecture, Load Balancing
**Time:** ~35 minutes

---

## The Problem

Imagine you ship a payment service as a Docker container. On a single VM this works fine — you run `docker run payment-service` and you're done. Now your load grows and you need 20 replicas spread across 8 VMs, each in a different availability zone. You need the replicas to restart if a VM goes down, bin-pack them efficiently so you don't waste RAM, route traffic only to healthy ones, roll out a new image version without downtime, and pull secrets from a vault instead of baking them into the image. Doing all of this by hand with shell scripts is how Site Reliability teams lose sleep and weekends.

The deeper issue is state drift. A VM silently loses a disk, a container OOMs and dies, a node gets kernel-upgraded and reboots — the world keeps diverging from what you intended. Without a continuous reconciliation loop, every drift is a manual incident.

Kubernetes solves this with a single principle: **you declare what you want; the system continuously enforces it.** You never tell Kubernetes _how_ to run a container; you tell it _what_ should be running. The control plane figures out the rest — placement, restarts, networking, rolling updates — all the time, forever.

---

## The Concept

### The Two Layers: Control Plane and Data Plane

A Kubernetes cluster has two logical layers:

```
┌─────────────────────────────────────────────────────────┐
│                     CONTROL PLANE                       │
│  ┌──────────────┐  ┌──────────┐  ┌───────────────────┐ │
│  │  API Server  │  │ etcd     │  │ Controller Manager│ │
│  │  (kube-      │  │ (source  │  │ (reconciliation   │ │
│  │  apiserver)  │  │ of truth)│  │  loops)           │ │
│  └──────┬───────┘  └──────────┘  └───────────────────┘ │
│         │          ┌──────────┐  ┌───────────────────┐ │
│         │          │Scheduler │  │Cloud Controller   │ │
│         │          │(kube-    │  │Manager (CCM)      │ │
│         │          │scheduler)│  └───────────────────┘ │
│         │          └──────────┘                        │
└─────────┼───────────────────────────────────────────────┘
          │  (HTTPS / watch)
┌─────────┼───────────────────────────────────────────────┐
│         │           DATA PLANE (Worker Nodes)            │
│  ┌──────┴──────────────────────────────────────────┐    │
│  │  Node A                Node B              Node C│    │
│  │  ┌──────────┐          ┌──────────┐             │    │
│  │  │ kubelet  │          │ kubelet  │  ...        │    │
│  │  │ kube-    │          │ kube-    │             │    │
│  │  │ proxy    │          │ proxy    │             │    │
│  │  │ runtime  │          │ runtime  │             │    │
│  │  │ [Pod][Pod│          │ [Pod]    │             │    │
│  │  └──────────┘          └──────────┘             │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### Control Plane Components

| Component | Role | What happens if it dies |
|---|---|---|
| **kube-apiserver** | The only component that reads/writes etcd. All other components talk _only_ to the API server. | No new scheduling or state changes — existing Pods keep running |
| **etcd** | Distributed key-value store. Single source of truth for every object (Pods, Deployments, Services…). | Cluster brain-dead — no state changes possible |
| **kube-scheduler** | Watches for unscheduled Pods (pods with no `nodeName`) and picks the best node. Runs filters (predicates) then ranks (priorities). | Pending Pods stay pending — existing Pods unaffected |
| **kube-controller-manager** | Runs dozens of control loops (ReplicaSet controller, Node controller, Endpoints controller…) as goroutines in a single binary. | Drift not corrected — Pods that die are not replaced |
| **cloud-controller-manager** | Manages cloud-provider resources (LoadBalancer, NodeIP, Volume). | Cloud resources (LBs, IPs) not provisioned or cleaned up |

### Worker Node Components

| Component | Role |
|---|---|
| **kubelet** | Agent on every node. Watches the API server for Pods assigned to its node. Calls the container runtime to start/stop containers, reports status back. |
| **kube-proxy** | Programs `iptables` or `ipvs` rules for `Service` virtual IPs. It's a network rules manager, not a real proxy. |
| **Container Runtime** | The thing that actually runs containers — `containerd`, `CRI-O`. Kubernetes talks to it via the Container Runtime Interface (CRI). |

### The Watch Mechanism — How Everything Connects

The API server exposes a **watch stream** (HTTP long-poll or HTTP/2 server-push). Every controller and the kubelet open a persistent watch on the object types they care about. When you write a Deployment, etcd fires an event, the API server fans it out to all watchers, and the relevant controller reacts.

```
kubectl apply -f deployment.yaml
         │
         ▼
   kube-apiserver ──► etcd (stores Deployment object)
         │
         ├──► ReplicaSet controller wakes up
         │        └─ creates ReplicaSet object in etcd
         │                 │
         │         Pod controller wakes up
         │              └─ creates 3 Pod objects (status: Pending)
         │                        │
         ├──► kube-scheduler wakes up
         │        └─ selects nodes for each Pod
         │           └─ patches Pod.spec.nodeName
         │                        │
         └──► kubelet on assigned node wakes up
                  └─ pulls image, starts container
                  └─ updates Pod status → Running
```

Nothing polls. Every hop is event-driven via the watch stream.

### The Reconciliation Loop

Every controller in Kubernetes runs the same simple loop:

```
for {
    desired  = read desired state from API server
    actual   = observe the real world
    if desired != actual {
        act to move actual toward desired
    }
    sleep(jitter)
}
```

This is called a **level-triggered control loop** (not edge-triggered). Controllers don't rely on receiving every event in order — they compare current desired vs. current actual. This makes the system self-healing even after network partitions or restarts.

### Core Abstractions

```
Deployment          (declares desired replica count + rollout strategy)
   └── ReplicaSet   (owns a stable set of Pod replicas)
          └── Pod   (smallest schedulable unit; 1+ tightly coupled containers)
                └── Container (image + resource requests/limits)

Service             (stable virtual IP + DNS name → selects Pods by label)
ConfigMap / Secret  (inject configuration into Pods)
PersistentVolume    (storage abstraction independent of Pod lifecycle)
Namespace           (soft multi-tenancy boundary)
```

A **Pod** is not a container. It is a group of containers that share a network namespace (same IP, same loopback) and can share volumes. The sidecar pattern (logging agents, service-mesh proxies) relies on this.

---

## Build It / In Depth

### Full Walkthrough: From YAML to Running Container

**Step 1 — Write the Deployment manifest**

```yaml
# payment-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment
  namespace: prod
spec:
  replicas: 3
  selector:
    matchLabels:
      app: payment
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0        # zero-downtime rollout
  template:
    metadata:
      labels:
        app: payment
    spec:
      containers:
        - name: payment
          image: myorg/payment:v2.3.1
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
              path: /health
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 5
```

**Step 2 — Apply and watch the rollout**

```bash
kubectl apply -f payment-deployment.yaml

# Watch the reconciliation live
kubectl rollout status deployment/payment -n prod

# Inspect what the scheduler decided
kubectl get pods -n prod -o wide
# NAME                       READY   STATUS    NODE
# payment-5d8bc9f9b-2kxlm    1/1     Running   node-2
# payment-5d8bc9f9b-7jrpn    1/1     Running   node-1
# payment-5d8bc9f9b-q8mrt    1/1     Running   node-3
```

**Step 3 — Expose with a Service**

```yaml
# payment-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: payment
  namespace: prod
spec:
  selector:
    app: payment        # matches Pod labels
  ports:
    - port: 80
      targetPort: 8080
  type: ClusterIP       # internal DNS: payment.prod.svc.cluster.local
```

```bash
kubectl apply -f payment-service.yaml
kubectl get endpoints payment -n prod
# NAME      ENDPOINTS
# payment   10.244.1.4:8080,10.244.2.7:8080,10.244.3.2:8080
```

kube-proxy on every node programs `iptables` rules so that traffic to the Service VIP (`10.96.x.x:80`) is DNAT-ed to one of the healthy endpoints at random.

**Step 4 — Simulate a node failure**

```bash
# Kill a node
kubectl drain node-2 --ignore-daemonsets --delete-emptydir-data

# ReplicaSet controller notices: actual replicas = 2, desired = 3
# It creates a new Pod; scheduler places it on node-1 or node-3
kubectl get pods -n prod -o wide
# payment-5d8bc9f9b-2kxlm    Terminating   node-2
# payment-5d8bc9f9b-7jrpn    Running       node-1
# payment-5d8bc9f9b-q8mrt    Running       node-3
# payment-5d8bc9f9b-nvwzq    Running       node-1   <-- new
```

The self-healing loop kicked in automatically within ~5 seconds (node heartbeat timeout + controller loop latency).

**Step 5 — Roll out a new image**

```bash
kubectl set image deployment/payment payment=myorg/payment:v2.4.0 -n prod
kubectl rollout status deployment/payment -n prod
# Waiting for deployment "payment" rollout to finish: 1 out of 3 new replicas have been updated...
# Waiting for deployment "payment" rollout to finish: 2 out of 3 new replicas...
# deployment "payment" successfully rolled out

# Rollback if v2.4.0 breaks production
kubectl rollout undo deployment/payment -n prod
```

The Deployment controller creates a new ReplicaSet for `v2.4.0` and gradually scales it up while scaling down the `v2.3.1` ReplicaSet — respecting `maxSurge` and `maxUnavailable`.

---

## Use It

### When to use which workload type

| Workload | Object | Use case |
|---|---|---|
| Stateless HTTP service | `Deployment` | Web servers, APIs, ML inference |
| Stateful service needing stable identity | `StatefulSet` | Databases (Postgres, Kafka, ZooKeeper) |
| One copy per node | `DaemonSet` | Log collectors, node-level monitoring (Fluent Bit, node-exporter) |
| Run to completion (batch) | `Job` / `CronJob` | Data pipelines, nightly reports |

### Managed Kubernetes in the cloud

| Platform | Notes |
|---|---|
| **EKS** (AWS) | Control plane fully managed; integrate with ALB Ingress Controller and IRSA for IAM |
| **GKE** (GCP) | Autopilot mode removes node management entirely; excellent Dataplane V2 (eBPF) networking |
| **AKS** (Azure) | Deep AD integration; good for Windows Server containers |
| **Self-managed** (kubeadm, k3s) | Edge/on-prem; you own etcd backups and control-plane HA |

### Kubernetes vs. alternatives

| Tool | Best for | Not suited for |
|---|---|---|
| **Kubernetes** | Large, complex, multi-team microservice platforms | Simple single-service deploys |
| **Docker Swarm** | Small teams wanting simpler orchestration | Advanced scheduling, ecosystem breadth |
| **Nomad** | Multi-workload (VMs, binaries, containers) | Kubernetes-native ecosystem tools |
| **ECS** (AWS) | AWS-only, simpler ops model | Multi-cloud, complex scheduling |

---

## Common Pitfalls

- **Not setting resource requests/limits.** The scheduler makes placement decisions based on `requests`. Without them, the scheduler treats each Pod as needing zero resources, which causes nodes to be overcommitted. When memory pressure hits, the kernel OOM-kills containers at random. Always set both `requests` (for scheduling) and `limits` (for isolation).

- **Ignoring readiness probes.** A Pod without a `readinessProbe` is added to Service endpoints the moment it starts, before the application is ready to serve traffic. This causes a burst of 502/503 errors on every deploy. `readinessProbe` gates traffic; `livenessProbe` gates restarts — use both.

- **One big Deployment per environment instead of namespaces.** Dumping everything into `default` gives you no isolation, no RBAC boundaries, and `kubectl get pods` returns hundreds of results. Use namespaces (`prod`, `staging`, `infra`) with LimitRanges and ResourceQuotas.

- **Storing secrets in ConfigMaps or environment variables in plain text.** `Secret` objects are base64-encoded, not encrypted at rest by default. Use etcd encryption at rest plus an external secrets manager (HashiCorp Vault, AWS Secrets Manager via External Secrets Operator) for production credentials.

- **Rolling back with `kubectl delete pod`.** Deleting a Pod managed by a ReplicaSet immediately creates a new identical Pod — it does not roll back the image. Use `kubectl rollout undo` to roll back a Deployment, or `kubectl set image` to pin a specific tag.

---

## Exercises

1. **Easy — Inspect the reconciliation loop.** Create a Deployment with `replicas: 2`. Manually delete one Pod with `kubectl delete pod <name>`. Watch what happens to the Pod count using `kubectl get pods -w`. Explain which component detected the drift and which component created the replacement.

2. **Medium — Zero-downtime rolling update with health checks.** Add a `readinessProbe` and `livenessProbe` to the payment Deployment above. Deploy a broken image (`myorg/payment:broken`) and observe: does the rollout pause automatically? Use `kubectl rollout status` and `kubectl describe deployment payment` to explain why it pauses. Then roll back.

3. **Hard — Simulate etcd unavailability.** On a local cluster (kind or minikube with a custom etcd), stop the etcd process. Show that existing Pods continue running. Attempt to apply a new manifest — what happens? Attempt to delete a Pod — what happens? Write a one-page post-mortem explaining why the data plane is decoupled from the control plane and what `--grace-period` means in this context.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Pod** | A container | A group of one or more containers sharing a network namespace and volume mounts; the atomic unit of scheduling |
| **Service** | A load balancer | A stable virtual IP + DNS name backed by iptables/ipvs rules on every node; load balancing is just a side effect |
| **Deployment** | Runs containers | Declares desired replica count and rollout strategy; manages ReplicaSets, not Pods directly |
| **etcd** | A config file | A distributed, strongly-consistent key-value store that is the single source of truth for all cluster state |
| **kubelet** | Kubernetes itself | An agent on each node that bridges the API server and the container runtime; it is not in the control plane |
| **Namespace** | Like a VM or network segment | A soft multi-tenancy boundary for RBAC and quotas; all namespaces share the same network unless a NetworkPolicy is applied |
| **Rolling Update** | Replaces all Pods at once | Incrementally creates new Pods and terminates old ones according to `maxSurge` and `maxUnavailable` — existing Pods serve traffic throughout |

---

## Further Reading

- [Kubernetes Official Documentation — Concepts](https://kubernetes.io/docs/concepts/) — the authoritative source for every object and component described here.
- [Kubernetes the Hard Way — Kelsey Hightower](https://github.com/kelseyhightower/kubernetes-the-hard-way) — bootstrapping a cluster from scratch; the fastest way to understand what every component actually does.
- [The Kubernetes Book — Nigel Poulton](https://nigelpoulton.com/books/) — the clearest narrative introduction to the control plane and data plane split.
- [CNCF Interactive Landscape](https://landscape.cncf.io/) — maps every tool in the Kubernetes ecosystem (networking, storage, observability, security) so you know what to reach for next.
- [etcd Documentation — Raft Consensus](https://etcd.io/docs/v3.5/learning/design-learner/) — explains why etcd needs an odd number of nodes and what happens during leader elections.
