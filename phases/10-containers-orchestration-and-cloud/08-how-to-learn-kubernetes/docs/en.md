# How to Learn Kubernetes?

> Master Kubernetes layer by layer — from a single Pod to a production-grade cluster — and you'll never fear distributed systems again.

**Type:** Learn
**Prerequisites:** Containers and Docker Basics, Microservices Architecture, Networking Fundamentals (TCP/IP, DNS, Load Balancing)
**Time:** ~35 minutes

---

## The Problem

You've containerized your application with Docker. Locally, everything runs perfectly. Then someone asks: "How does this scale to 500 replicas? How do we roll out a new version without downtime? What happens if a node dies at 3 AM?" You have no answer, because a single `docker run` command can't answer those questions.

Operating containers at scale means answering questions Docker alone cannot: Where does a container land when you have 50 servers? What restarts it if it crashes? How does traffic from the internet reach the right container when containers move around? How do you store secrets without baking them into images? These are **orchestration problems**, and Kubernetes is the industry's standard solution.

Without understanding Kubernetes, you are locked out of the way modern production infrastructure works. Every major cloud provider (AWS EKS, Google GKE, Azure AKS), every GitOps pipeline (ArgoCD, Flux), and nearly every SRE team uses Kubernetes vocabulary as a baseline. This lesson gives you a structured mental map for learning it — not by memorizing YAML, but by understanding why each concept exists.

---

## The Concept

### The Six Learning Layers

Kubernetes has a reputation for complexity, but that complexity is layered. Each layer builds directly on the one before. Learn them in order, and the 80+ resource types in the API stop being random YAML blocks and start making sense.

```
┌─────────────────────────────────────────────────────┐
│  Layer 6: Tools, Observability & Ecosystem          │  kubectl, Helm, CI/CD, GitOps,
│           (Operate and maintain clusters)           │  Prometheus, EKS/GKE/AKS
├─────────────────────────────────────────────────────┤
│  Layer 5: Security & Access Control                 │  RBAC, ServiceAccounts,
│           (Lock down what runs and who can do it)   │  Secrets, Admission Controllers
├─────────────────────────────────────────────────────┤
│  Layer 4: Storage & Configuration                   │  PV, PVC, StorageClass,
│           (Persist data, externalize config)        │  ConfigMap, Secret
├─────────────────────────────────────────────────────┤
│  Layer 3: Networking & Service Management           │  Services, Ingress,
│           (Route traffic to the right Pod)          │  NetworkPolicy, DNS
├─────────────────────────────────────────────────────┤
│  Layer 2: Workloads & Controllers                   │  Deployment, StatefulSet,
│           (Run and manage your app reliably)        │  Job, CronJob, HPA
├─────────────────────────────────────────────────────┤
│  Layer 1: Core Concepts & Architecture              │  Cluster, Node, Pod,
│           (The vocabulary everything else uses)     │  Control Plane, etcd
└─────────────────────────────────────────────────────┘
```

### Layer 1: Core Concepts and Architecture

A Kubernetes **cluster** is a set of machines (nodes) divided into two roles:

**Control Plane** — the brain. It holds the desired state of the cluster.
- `kube-apiserver`: The single entry point. Every `kubectl` call, every controller, every node talks to this.
- `etcd`: Distributed key-value store. The only place where cluster state is persisted. Lose this, lose your cluster.
- `kube-scheduler`: Watches for new Pods with no node assigned, picks a node based on resource requests and constraints.
- `kube-controller-manager`: Runs dozens of control loops (Deployment controller, Node controller, etc.). Each loop watches actual state and drives it toward desired state.

**Worker Nodes** — where your containers actually run.
- `kubelet`: An agent on each node. Talks to the API server; ensures the containers described in PodSpecs are running.
- `kube-proxy`: Manages iptables/IPVS rules on each node for Service networking.
- **Container Runtime**: containerd (or CRI-O). The thing that actually calls the Linux kernel to start containers.

The fundamental schedulable unit is the **Pod** — one or more tightly-coupled containers sharing a network namespace (same IP, same `localhost`) and optional shared volumes. Pods are ephemeral and replaceable; controllers manage them, not you.

```
Control Plane                    Worker Node
┌───────────────────┐            ┌──────────────────────────┐
│  kube-apiserver   │◄──HTTPS────│  kubelet                 │
│  kube-scheduler   │            │  ┌────────────────────┐  │
│  controller-mgr   │            │  │  Pod               │  │
│  etcd             │            │  │  ┌──────┐ ┌──────┐ │  │
└───────────────────┘            │  │  │ C1   │ │ C2   │ │  │
                                 │  │  └──────┘ └──────┘ │  │
                                 │  └────────────────────┘  │
                                 │  kube-proxy              │
                                 └──────────────────────────┘
```

### Layer 2: Workloads and Controllers

You never create naked Pods in production. You describe *what you want*, and controllers continuously reconcile reality to match.

| Controller    | Use Case                                              | Key Behavior                                    |
|---------------|-------------------------------------------------------|-------------------------------------------------|
| **Deployment**| Stateless apps (web servers, APIs)                    | Manages ReplicaSets; rolling updates; rollback  |
| **ReplicaSet**| Maintain N identical Pod replicas                     | Usually managed by Deployment, not directly     |
| **StatefulSet**| Stateful apps (databases, Kafka, ZooKeeper)          | Stable pod names, ordered start/stop, stable PVCs |
| **DaemonSet** | One Pod per node (log shippers, node exporters)       | Auto-added to new nodes                         |
| **Job**       | Run-to-completion tasks (batch processing, migration) | Retries on failure; tracks completion           |
| **CronJob**   | Scheduled Jobs                                        | Creates Jobs on a cron schedule                 |

**Autoscalers** answer "how many replicas?"
- **HPA (Horizontal Pod Autoscaler)**: Scales replica count based on CPU, memory, or custom metrics.
- **VPA (Vertical Pod Autoscaler)**: Adjusts resource requests/limits on existing Pods.
- **Cluster Autoscaler**: Adds/removes nodes when Pods can't be scheduled or nodes are underutilized.

**Labels and Selectors** are the glue. A Deployment finds its Pods via a label selector (e.g., `app: api`). Services find their backend Pods the same way. Everything is loosely coupled through label matching, not hardcoded names.

### Layer 3: Networking and Service Management

Every Pod gets its own IP, but Pods are ephemeral — their IPs change when they restart. A **Service** provides a stable virtual IP (ClusterIP) and DNS name, and load-balances across matching Pods.

| Service Type     | Reachable From          | When to Use                                      |
|------------------|-------------------------|--------------------------------------------------|
| **ClusterIP**    | Inside cluster only     | Internal microservice-to-microservice calls      |
| **NodePort**     | Node IP + port          | Dev/testing; bare-metal without a LB             |
| **LoadBalancer** | Cloud LB external IP    | Exposing a single service externally in the cloud|
| **ExternalName** | DNS CNAME alias         | Routing to external services by DNS name         |

For HTTP(S) traffic, **Ingress** (managed by an Ingress Controller like NGINX or Traefik) gives you host/path-based routing to multiple Services from a single load balancer. This is almost always what you use for web APIs in production.

**NetworkPolicy** resources define which Pods can talk to which other Pods. By default, all Pods can reach all Pods. NetworkPolicies let you enforce that, say, only the `api` namespace can reach the `database` Pod.

### Layer 4: Storage and Configuration

Containers are stateless by default; their filesystem dies with them. Kubernetes storage builds up in levels:

```
StorageClass  ←  defines HOW storage is provisioned (AWS EBS, NFS, etc.)
     ↓
PersistentVolume (PV)  ←  a piece of actual storage, provisioned statically or dynamically
     ↓
PersistentVolumeClaim (PVC)  ←  a request for storage by a Pod ("I need 20 GiB")
     ↓
Volume mount in Pod spec  ←  where inside the container the storage appears
```

For configuration, avoid baking environment-specific values into images:
- **ConfigMap**: Non-sensitive config (feature flags, hostnames). Can be mounted as files or env vars.
- **Secret**: Sensitive config (passwords, TLS certs, API tokens). Base64-encoded at rest in etcd (encrypt etcd at rest in production). Often supplemented by external secret managers (HashiCorp Vault, AWS Secrets Manager).

### Layer 5: Security and Access Control

Security in Kubernetes is multi-layered:

**RBAC (Role-Based Access Control)**: Controls who can do what to which API resources.
- `Role` / `ClusterRole`: A set of allowed verbs (get, list, create, delete) on resources.
- `RoleBinding` / `ClusterRoleBinding`: Binds a Role to a user, group, or ServiceAccount.
- **ServiceAccount**: An identity for Pods. Every Pod runs as a ServiceAccount and can be given minimal permissions via RBAC.

**Admission Controllers**: Webhooks that intercept API requests *after* authentication/authorization but *before* persistence. Used to enforce policies (e.g., "no Pods without resource limits"), inject sidecars (service mesh), or mutate requests. Key built-in controllers: `LimitRanger`, `ResourceQuota`, `PodSecurity`.

**Pod Security**: Kubernetes 1.25+ replaced PodSecurityPolicy with **Pod Security Admission**, which enforces three profiles: `privileged`, `baseline`, and `restricted`.

### Layer 6: Tools, Observability and Ecosystem

- **kubectl**: The CLI. Learn it deeply — `kubectl explain`, `kubectl debug`, `kubectl rollout`, and `kubectl top` are your daily tools.
- **Helm**: Package manager for Kubernetes. A Chart is a templated collection of Kubernetes manifests. Use it to install community software (Prometheus, cert-manager) and to template your own deployments.
- **CI/CD Integration**: Pipelines build images, push to a registry, then update manifests (image tags) — triggering a rollout.
- **GitOps** (ArgoCD, Flux): The Git repo is the source of truth. The GitOps controller syncs the cluster to match what's in Git. Drift detection is automatic.
- **Observability**: Prometheus (metrics scraping + alerting), Grafana (dashboards), Loki (log aggregation), Jaeger/Tempo (distributed tracing). Together called the PLG/LGTM stack.
- **Managed Kubernetes**: AWS EKS, Google GKE, Azure AKS — they manage the control plane for you. Choose based on your cloud provider; the Kubernetes API is identical.

---

## Build It / In Depth

The best way to internalize the layers is to deploy a simple web application and scale it — moving from a raw Pod through a Deployment to an autoscaled, publicly reachable service.

### Step 1: Start a Local Cluster

```bash
# minikube is the simplest local option
brew install minikube
minikube start --cpus=2 --memory=4096

# Verify the cluster is up
kubectl cluster-info
kubectl get nodes
```

### Step 2: Create a Deployment (Layer 2)

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
  labels:
    app: api-server
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api-server
  template:
    metadata:
      labels:
        app: api-server
    spec:
      containers:
        - name: api
          image: hashicorp/http-echo:latest
          args: ["-text=hello from kubernetes"]
          ports:
            - containerPort: 5678
          resources:
            requests:
              cpu: "100m"
              memory: "64Mi"
            limits:
              cpu: "200m"
              memory: "128Mi"
```

```bash
kubectl apply -f deployment.yaml
kubectl get pods          # 3 pods in Running state
kubectl rollout status deployment/api-server
```

### Step 3: Expose It with a Service (Layer 3)

```yaml
# service.yaml
apiVersion: v1
kind: Service
metadata:
  name: api-server-svc
spec:
  selector:
    app: api-server   # matches the Pod labels above
  ports:
    - protocol: TCP
      port: 80
      targetPort: 5678
  type: ClusterIP
```

```bash
kubectl apply -f service.yaml
# From inside the cluster, the service is reachable at api-server-svc:80
# For local testing:
kubectl port-forward svc/api-server-svc 8080:80
curl http://localhost:8080   # → "hello from kubernetes"
```

### Step 4: Add Horizontal Autoscaling (Layer 2 — HPA)

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
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 50
```

```bash
kubectl apply -f hpa.yaml
kubectl get hpa            # watch the TARGETS column
# Generate load:
kubectl run -it load-gen --image=busybox --restart=Never -- \
  /bin/sh -c "while true; do wget -q -O- http://api-server-svc; done"
kubectl get hpa --watch   # observe replica count climb
```

### Step 5: Simulate a Rolling Update

```bash
# Update the image tag — Kubernetes replaces Pods one at a time
kubectl set image deployment/api-server api=hashicorp/http-echo:0.2.3
kubectl rollout status deployment/api-server   # watch it progress

# Something went wrong? Roll back instantly.
kubectl rollout undo deployment/api-server
```

This five-step sequence covers Layers 1–3. Progress to Layers 4–6 by adding a PVC for persistent storage, a ConfigMap for configuration, RBAC to restrict what the Pod's ServiceAccount can do, and finally deploying with a Helm chart.

---

## Use It

### Where Kubernetes Concepts Show Up in Real Systems

| Scenario                             | Key Kubernetes Feature                          |
|--------------------------------------|-------------------------------------------------|
| Zero-downtime deploys                | Deployment rolling update + readiness probes    |
| Traffic spike handling               | HPA + Cluster Autoscaler                        |
| Database with stable identity        | StatefulSet + PVC                               |
| Internal API-to-API calls            | ClusterIP Service + CoreDNS                     |
| HTTPS routing for multiple services  | Ingress + cert-manager (Let's Encrypt TLS)      |
| Secrets injection from Vault         | Vault Agent Injector (MutatingAdmissionWebhook) |
| Batch data pipeline                  | Job or CronJob                                  |
| Node-level log shipping              | DaemonSet (Fluentd/Fluent Bit)                  |
| Multi-tenant isolation               | Namespaces + RBAC + NetworkPolicy               |
| GitOps deployments                   | ArgoCD or Flux watching a Git repo              |

### Managed Kubernetes Comparison

| Feature                      | AWS EKS          | Google GKE              | Azure AKS         |
|------------------------------|------------------|-------------------------|-------------------|
| Control plane managed        | Yes              | Yes (Autopilot too)     | Yes               |
| Node provisioning automation | Karpenter        | Node Auto-provisioning  | Cluster Autoscaler|
| Best-in-class integration    | IAM, ALB, EBS    | Cloud Run, Anthos       | AAD, Azure Disk   |
| Spot/preemptible support     | Spot instances   | Spot VMs                | Spot VMs          |
| Upgrade experience           | Manual or managed| Managed channels        | Managed channels  |

---

## Common Pitfalls

- **Skipping resource requests and limits.** Without `resources.requests`, the scheduler can't make good placement decisions. Without `limits`, one noisy Pod can starve every other Pod on the node. Always set both; use VPA recommendations to tune them.

- **Storing secrets in ConfigMaps.** ConfigMaps are stored in plain text in etcd. Anything sensitive — passwords, API keys, certificates — must go in a Secret with etcd encryption at rest enabled, or better yet, in an external secret manager like Vault or AWS Secrets Manager.

- **Using `latest` image tags in production.** `latest` is mutable. Two Pods on the same Deployment can run different images if a new push happened mid-rollout. Always pin to an immutable digest (`image: myapp@sha256:abc123`) or a semver tag from CI.

- **Ignoring readiness and liveness probes.** Without a `readinessProbe`, Kubernetes sends traffic to a Pod the moment its container starts — before the app has finished warming up. Without a `livenessProbe`, a deadlocked process keeps its Pod in `Running` state forever. Define both for every production container.

- **Treating Pods as VMs.** Pods are cattle, not pets. They get new IPs on restart, they can be evicted at any time (node pressure, drains), and their local disk is ephemeral. Application code must be stateless, or state must live in an external store. Debugging a specific Pod by SSHing in and making changes manually is an anti-pattern.

---

## Exercises

1. **Easy — Core Architecture:** Deploy the NGINX Docker image as a Deployment with 2 replicas. Expose it via a NodePort Service. Use `kubectl describe` to find which node each Pod landed on and explain why the scheduler chose those nodes.

2. **Medium — Workloads + Networking:** Deploy two Deployments — a frontend (NGINX serving a static page) and a backend (the `http-echo` image). Connect them with ClusterIP Services. Configure an Ingress resource so that `/` routes to the frontend and `/api` routes to the backend. Test with `curl` and explain the flow a request takes from the Ingress controller to the Pod.

3. **Hard — Full Stack with Security:** Build a system with a PostgreSQL StatefulSet backed by a PVC. Store the database password in a Kubernetes Secret. Deploy a web app that reads the secret via an environment variable. Create a ServiceAccount for the web app with a Role that only allows reading Secrets in its own namespace — nothing else. Verify the RBAC is enforced by running `kubectl auth can-i` as the ServiceAccount.

---

## Key Terms

| Term                        | What people think                                 | What it actually means                                                                 |
|-----------------------------|---------------------------------------------------|----------------------------------------------------------------------------------------|
| **Pod**                     | A single container                                | One or more co-located containers sharing a network namespace and optional volumes      |
| **Service**                 | A load balancer                                   | A stable virtual IP + DNS name that proxies traffic to matching Pods via label selectors |
| **Deployment**              | A way to run containers                           | A controller that manages ReplicaSets to achieve a desired replica count with rolling updates |
| **Namespace**               | Like a folder for YAML files                      | A virtual cluster providing isolation for names, RBAC, and resource quotas             |
| **ConfigMap**               | A config file stored in Kubernetes                | A non-secret key-value store injected into Pods as env vars or file mounts; not encrypted |
| **Ingress**                 | A reverse proxy                                   | An API object defining routing rules; an Ingress *Controller* is the actual reverse proxy implementing them |
| **StatefulSet**             | A Deployment for databases                        | A controller that provides stable network IDs, ordered startup/shutdown, and stable PVC bindings |

---

## Further Reading

- **Kubernetes Official Documentation** — https://kubernetes.io/docs/home/ (the interactive tutorial at `/docs/tutorials/kubernetes-basics/` is the best starting point)
- **Kubernetes The Hard Way (Kelsey Hightower)** — https://github.com/kelseyhightower/kubernetes-the-hard-way (bootstrap a cluster from scratch to understand every component)
- **Production Kubernetes (O'Reilly)** — https://www.oreilly.com/library/view/production-kubernetes/9781492092292/ (goes deep on operating clusters at scale)
- **CNCF Landscape** — https://landscape.cncf.io/ (maps the entire cloud-native ecosystem around Kubernetes)
- **kubectl Cheat Sheet** — https://kubernetes.io/docs/reference/kubectl/cheatsheet/ (bookmark this; you'll use it daily)
