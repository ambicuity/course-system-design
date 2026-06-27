# Top Kubernetes Scaling Strategies You Must Know

> Scale the right thing, at the right time, in the right direction — or pay in downtime and wasted cloud spend.

**Type:** Learn
**Prerequisites:** Kubernetes Fundamentals, Pod Resource Requests and Limits, Kubernetes Deployments and ReplicaSets
**Time:** ~30 minutes

## The Problem

Your e-commerce platform sails through Tuesday at 50 req/s with six pods humming along at 30% CPU. Then Black Friday hits. Traffic spikes to 3,000 req/s in under three minutes. Pods start throttling, latency climbs past your SLA, and you are watching money burn while engineers frantically `kubectl scale deployment` by hand. Two hours later, traffic falls back to normal — but you are now running 80 pods and paying for cloud nodes that are doing nothing.

This is not a rare edge case. Every production system with variable load faces the same tension: over-provision and waste money; under-provision and lose users. Kubernetes ships with three built-in primitives for attacking this problem (HPA, VPA, Cluster Autoscaler) and the ecosystem adds more (KEDA, predictive scaling). Each one solves a different slice of the problem, and none of them solves all of it alone.

The goal of this lesson is to give you a precise mental model of what each strategy controls, how it works internally, where it breaks down, and how to combine them correctly in production systems.

---

## The Concept

### The Two Dimensions of Kubernetes Scaling

Every scaling decision in Kubernetes operates on one of two axes:

| Axis | Question | Mechanism |
|---|---|---|
| **Horizontal** | How many replicas? | Add or remove pods |
| **Vertical** | How much CPU/memory per pod? | Resize individual pods |

A third dimension — **node count** — lives one level below pods and is managed by the Cluster Autoscaler or node auto-provisioners. All three dimensions must be coordinated; tuning only one creates headroom in one place while starving another.

### Strategy Overview

```
             Kubernetes Scaling Landscape
             ─────────────────────────────
 ┌─────────────────────────────────────────────────────┐
 │  REACTIVE SCALING (after load arrives)              │
 │                                                     │
 │   HPA (Horizontal Pod Autoscaler)                   │
 │   ├─ Watches: CPU, memory, custom/external metrics  │
 │   └─ Action:  Adjusts pod replica count             │
 │                                                     │
 │   VPA (Vertical Pod Autoscaler)                     │
 │   ├─ Watches: Historical resource usage             │
 │   └─ Action:  Patches resource requests on pods     │
 │                                                     │
 │   Cluster Autoscaler (CA)                           │
 │   ├─ Watches: Pending (unschedulable) pods          │
 │   └─ Action:  Adds/removes nodes via cloud API      │
 └─────────────────────────────────────────────────────┘
 ┌─────────────────────────────────────────────────────┐
 │  EVENT-DRIVEN SCALING                               │
 │                                                     │
 │   KEDA (Kubernetes Event-Driven Autoscaling)        │
 │   ├─ Watches: Queue depth, Kafka lag, cron, etc.   │
 │   └─ Action:  Drives HPA (or scale-to-zero)        │
 └─────────────────────────────────────────────────────┘
 ┌─────────────────────────────────────────────────────┐
 │  PREDICTIVE SCALING                                 │
 │                                                     │
 │   Predictive Autoscaler / KEDA cron trigger         │
 │   ├─ Watches: ML forecasts or historical patterns   │
 │   └─ Action:  Pre-warms replicas before load hits   │
 └─────────────────────────────────────────────────────┘
```

### How HPA Works Internally

HPA queries the Metrics API (backed by metrics-server or a custom adapter) every 15 seconds by default. It computes a desired replica count using:

```
desiredReplicas = ceil(currentReplicas × (currentMetricValue / targetMetricValue))
```

For example: 4 pods running at 80% CPU with a target of 50% → `ceil(4 × 80/50)` = 7 pods.

HPA applies stabilization windows (default: 5 minutes for scale-down, 3 minutes for scale-up) to prevent thrashing when a metric oscillates around the threshold.

### How VPA Works Internally

VPA has three components:
- **Recommender**: Continuously reads historical usage and produces recommended `requests` values.
- **Admission Controller (webhook)**: Injects updated `requests` into new pods at scheduling time.
- **Updater**: Evicts existing pods so the admission controller can recreate them with new limits.

Because eviction is disruptive, VPA is best used in `Off` or `Initial` mode for most production workloads (see Pitfalls).

### How Cluster Autoscaler Works

CA does not watch CPU or memory directly. It watches for **Pending pods** — pods that the scheduler cannot place because no node has enough room. When it sees pending pods, it simulates which node group addition would make them schedulable and provisions it via the cloud provider API. On scale-down, it looks for nodes where all running pods could be packed onto other nodes, cordons the node, drains it, and deletes it.

The critical insight: **CA reacts to pod scheduling pressure, not raw resource utilization**. If your pods have loose resource requests that don't reflect actual usage, CA will never see pending pods and will never add nodes — even if the cluster is CPU-saturated.

---

## Build It / In Depth

### 1. Horizontal Pod Autoscaler (HPA)

```yaml
# hpa-cpu.yaml — basic CPU-based HPA
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
  maxReplicas: 50
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 60   # target 60% of requests
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60   # react fast on load spike
      policies:
        - type: Percent
          value: 100
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300  # conservative scale-down
      policies:
        - type: Pods
          value: 2
          periodSeconds: 60
```

The `behavior` block is mandatory in production. Without it, HPA uses defaults that are often too slow on the way up and too aggressive on the way down.

### 2. Vertical Pod Autoscaler (VPA)

```yaml
# vpa.yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: api-server-vpa
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-server
  updatePolicy:
    updateMode: "Off"   # Only produce recommendations; don't auto-evict
  resourcePolicy:
    containerPolicies:
      - containerName: api-server
        minAllowed:
          cpu: "100m"
          memory: "128Mi"
        maxAllowed:
          cpu: "4"
          memory: "4Gi"
```

Run VPA in `Off` mode first. Check `kubectl describe vpa api-server-vpa` to read recommendations, then manually update your Deployment. Only switch to `Auto` after you've validated the recommendations don't cause disruption.

### 3. Cluster Autoscaler

CA is deployed as a Deployment (one replica) with cloud-provider-specific flags. On AWS EKS:

```bash
# Install via Helm
helm repo add autoscaler https://kubernetes.github.io/autoscaler
helm install cluster-autoscaler autoscaler/cluster-autoscaler \
  --namespace kube-system \
  --set autoDiscovery.clusterName=my-cluster \
  --set awsRegion=us-east-1 \
  --set rbac.serviceAccount.annotations."eks\.amazonaws\.com/role-arn"=arn:aws:iam::123456789:role/cluster-autoscaler-role
```

Annotate node groups for discovery:
```
k8s.io/cluster-autoscaler/enabled: "true"
k8s.io/cluster-autoscaler/my-cluster: "owned"
```

### 4. KEDA — Event-Driven Scale-to-Zero

```yaml
# keda-kafka-scaledobject.yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: kafka-consumer-scaler
spec:
  scaleTargetRef:
    name: kafka-consumer
  minReplicaCount: 0        # true scale-to-zero
  maxReplicaCount: 30
  triggers:
    - type: kafka
      metadata:
        bootstrapServers: kafka:9092
        consumerGroup: my-group
        topic: orders
        lagThreshold: "100"  # add a replica per 100 messages of lag
```

KEDA installs a custom metrics adapter that drives the standard HPA — so HPA still does the actual scaling. This means HPA's behavior policies still apply.

### Combining All Three: The Correct Architecture

```
 Incoming Traffic
       │
       ▼
   [ HPA ] ◄── metrics-server / Prometheus / KEDA
       │  adjusts replica count
       ▼
 [ Pod Pool ]
  (needs more room?)
       │ Pending pods appear
       ▼
 [ Cluster Autoscaler ]
       │  provisions new node
       ▼
 [ New Node ] ── scheduler places pending pods

 [ VPA ] runs in parallel, recommends right-sized requests
         so HPA metrics and CA decisions are accurate
```

---

## Use It

| Strategy | Best For | Avoid When |
|---|---|---|
| **HPA (CPU/memory)** | Stateless services with CPU-correlated load | Stateful workloads, bursty but infrequent traffic |
| **HPA (custom metric)** | Queue consumers, gRPC services with latency SLOs | You don't have a metrics pipeline yet |
| **VPA** | Right-sizing pods with unknown or changing memory requirements | Combined with HPA on the same resource (conflict) |
| **Cluster Autoscaler** | All clusters with variable node-level demand | On-prem with no cloud API; fixed-size clusters |
| **KEDA** | Message queues, cron-driven jobs, scale-to-zero dev environments | Simple CPU-only scaling where HPA alone suffices |
| **Predictive Autoscaling** | Highly regular traffic patterns (business hours, weekly cycles) | Irregular or unpredictable spikes |

**Cloud-specific implementations:**
- AWS: Karpenter (newer, faster than CA) / EKS-managed node groups
- GCP: GKE Autopilot (nodes provisioned per-pod, no CA needed)
- Azure: AKS Cluster Autoscaler with Azure VMSS
- All clouds: KEDA is cloud-agnostic and runs anywhere

---

## Common Pitfalls

- **Using HPA without accurate resource requests.** HPA measures CPU utilization as a percentage of `requests`, not node capacity. If your pod has `requests: 100m` but actually needs 500m, HPA thinks utilization is 500% and thrashes. Set requests to match the 50th-percentile actual usage, then let VPA recommendations validate them.

- **Running VPA in `Auto` mode with HPA on the same resource.** If both are targeting CPU simultaneously, they fight: HPA adds pods while VPA evicts them for resizing. Use VPA `Off` mode to get recommendations, apply them to requests, and let HPA handle the replica count. Alternatively, run VPA on memory and HPA on CPU — they control different resources and coexist safely.

- **Expecting Cluster Autoscaler to scale down quickly.** CA's default scale-down delay is 10 minutes, and a single pod with no `PodDisruptionBudget` can block a node from draining. Always set PodDisruptionBudgets on critical workloads and tune `--scale-down-delay-after-add` for your cost tolerance.

- **Setting `minReplicas: 1` and being surprised by downtime.** A single replica offers zero redundancy. During a node drain, rolling update, or AZ failure, that one pod is unavailable. Set `minReplicas` to at least 2 across at least 2 nodes using pod anti-affinity rules.

- **Ignoring cold-start latency in scale-up paths.** HPA can add pods in seconds, but if your container takes 90 seconds to initialize (JVM warmup, model loading), users see errors during that window. Use `startupProbe` to delay traffic until the pod is genuinely ready, and consider keeping a minimum replica buffer with predictive scaling during known peak periods.

---

## Exercises

1. **Easy** — Deploy a simple Nginx deployment with 2 replicas. Add an HPA targeting 50% CPU utilization with min=2, max=10. Run `kubectl run -it --rm load-generator --image=busybox -- /bin/sh` and use `wget -q -O- http://nginx` in a loop. Watch `kubectl get hpa -w` and explain what you observe in the stabilization window.

2. **Medium** — A batch job consumes messages from an SQS queue. Model what happens with a standard CPU-based HPA: when will it scale up, when will it scale down, and why is this suboptimal? Redesign the scaling strategy using KEDA with the SQS scaler and compare the behavior under a sudden burst of 10,000 messages.

3. **Hard** — You run a machine learning inference service. Each pod loads a 2GB model into memory at startup (takes 60 seconds). The service receives traffic with a sharp weekday 9am–6pm cycle. Design a complete scaling architecture: which metrics drive HPA, how you configure VPA without conflict, what the Cluster Autoscaler needs to work correctly, and how predictive scaling reduces cold-start exposure. Specify `behavior` parameters, `minReplicas`, and the startup/readiness probe strategy.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **CPU Utilization (HPA)** | Percentage of node CPU | Percentage of the pod's CPU *request* value consumed |
| **Cluster Autoscaler** | Scales pods based on CPU | Scales nodes based on unschedulable (Pending) pods only |
| **VPA Auto mode** | Gently adjusts running pods | Evicts and restarts pods to apply new resource values — disruptive |
| **Scale-to-zero** | Built into HPA | Not supported by HPA natively; requires KEDA as a metrics adapter |
| **Stabilization window** | A delay before any scaling | A window over which the max (for scale-down) or min (for scale-up) desired replica count is tracked to prevent thrashing |
| **Resource Request** | A cap on what a pod can use | A scheduling hint and the denominator for HPA utilization math; the actual limit is set separately |
| **Predictive Autoscaling** | Replaces reactive scaling | Supplements reactive scaling by pre-warming capacity ahead of forecasted demand |

---

## Further Reading

- [Kubernetes HPA documentation — autoscaling/v2 API reference](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/)
- [Vertical Pod Autoscaler GitHub repo — architecture and modes](https://github.com/kubernetes/autoscaler/tree/master/vertical-pod-autoscaler)
- [Cluster Autoscaler FAQ — scale-down, node groups, and cloud provider setup](https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/FAQ.md)
- [KEDA documentation — scalers, ScaledObject spec, and cloud integrations](https://keda.sh/docs/latest/scalers/)
- [Karpenter documentation — node provisioning as an alternative to Cluster Autoscaler on AWS](https://karpenter.sh/docs/)
