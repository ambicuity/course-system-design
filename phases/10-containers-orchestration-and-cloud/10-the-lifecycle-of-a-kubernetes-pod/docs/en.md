# The Lifecycle of a Kubernetes Pod

> A Pod is not just a running container — it is a carefully orchestrated sequence of states, each with real consequences for availability and data integrity.

**Type:** Learn
**Prerequisites:** Containers and Docker Basics, Kubernetes Architecture Overview, Health Checks and Probes
**Time:** ~25 minutes

---

## The Problem

You deploy a new version of your service. The rollout appears healthy — `kubectl rollout status` reports success — but a spike of 500s hits your load balancer for roughly 30 seconds before disappearing. Later you discover that traffic was routed to Pods that had not finished initializing their database connection pool. The readiness probe was configured wrong, or not at all.

Or the reverse: you trigger a deployment, old Pods are terminated mid-request, and in-flight writes to your payment service are dropped because the application received SIGKILL with no chance to flush. You assumed containers just "stop cleanly." They don't unless you engineer them to.

These failures share a root cause: engineers treat a Pod as binary — either running or not. In reality, a Pod moves through a precise sequence of phases and conditions. Each transition is an opportunity to protect your users or expose them to breakage. Understanding this lifecycle is not academic; it is the difference between a clean rolling update and a production incident.

---

## The Concept

### The Two-Level View: Phases and Container States

Kubernetes tracks a Pod at two granularities simultaneously.

**Pod Phase** is the high-level summary stored in `status.phase`:

| Phase | Meaning |
|---|---|
| `Pending` | Pod accepted by the cluster; at least one container is not yet running. Includes scheduling and image-pull time. |
| `Running` | Pod is bound to a node; all containers have been created; at least one is still running, starting, or restarting. |
| `Succeeded` | All containers exited with code 0 and will not be restarted. Typical for Jobs. |
| `Failed` | All containers exited; at least one exited non-zero or was killed. |
| `Unknown` | The node hosting the Pod cannot be reached; status cannot be determined. |

**Container State** is per-container, inside `status.containerStatuses[*].state`:

| State | Meaning |
|---|---|
| `Waiting` | Container has not started yet (pulling image, waiting for init containers, etc.). |
| `Running` | Process is executing. `startedAt` timestamp is set. |
| `Terminated` | Process has exited. Both `exitCode` and `reason` are set. |

Pod phase is derived from container states — it is never set directly by a controller.

### The Control Plane Path

From `kubectl apply` to a running process, every Pod traverses this exact path:

```
kubectl apply -f pod.yaml
        │
        ▼
[API Server] ──── validates, authenticates, admits ────► [etcd]
                                                            │
                                                  (watch stream)
                                                            │
                                                            ▼
                                                      [Scheduler]
                                                   filters nodes by:
                                                   - resource requests
                                                   - node selectors / affinity
                                                   - taints & tolerations
                                                   - topology constraints
                                                            │
                                                   writes binding to etcd
                                                            │
                                                  (watch stream: spec.nodeName set)
                                                            │
                                                            ▼
                                                       [kubelet]
                                                   on the assigned node
                                                            │
                              ┌─────────────────────────────────────────────┐
                              │  1. CNI: create network namespace, assign IP │
                              │  2. CSI / kubelet: mount volumes             │
                              │  3. Pull images (ImagePullPolicy)            │
                              │  4. Run init containers (sequential)         │
                              │  5. Run app containers (parallel)            │
                              │  6. Start health probes                      │
                              └─────────────────────────────────────────────┘
```

The kubelet does **not** communicate with the API server to start containers. It watches etcd (via the API server's watch endpoint) and acts independently. This is why a node partition causes `Unknown` phase rather than `Failed` — the control plane simply stops receiving updates.

### Init Containers

Init containers run sequentially before any app container starts. Each must exit with code 0; if one fails, kubelet restarts it according to the Pod's `restartPolicy`. Common uses:

- Waiting for a dependency (e.g., database migration check)
- Seeding a shared volume with config files
- Acquiring a distributed lock

The Pod stays in `Pending` with `status.initContainerStatuses` showing progress until all init containers complete.

### Health Probes: The Traffic Gate

Three probe types control container eligibility and restart behavior:

| Probe | Failure action | Typical use |
|---|---|---|
| `startupProbe` | Restart container | Slow-starting apps; disables liveness until it passes |
| `livenessProbe` | Restart container | Detect deadlock or hung process |
| `readinessProbe` | Remove from Service endpoints | Temporary unavailability (warming up, processing a big batch) |

**Critical distinction:** a failing `readinessProbe` does NOT restart the container. It only removes the Pod's IP from the `Endpoints` object backing a Service. Traffic stops flowing; the process keeps running. This is intentional — you may want a Pod to finish in-flight work while accepting no new connections.

### Pod Conditions

Beyond phase, `status.conditions` provides fine-grained flags:

```
PodScheduled       → True once a node is assigned
Initialized        → True once all init containers complete
ContainersReady    → True when all app containers pass readiness
Ready              → True when both Initialized AND ContainersReady
```

Service endpoint controllers watch the `Ready` condition. A Pod only receives traffic when `Ready=True`.

---

## Build It / In Depth

### Trace a Full Lifecycle with Commands

```bash
# 1. Submit the Pod
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: lifecycle-demo
spec:
  initContainers:
  - name: wait-for-config
    image: busybox:1.36
    command: ["sh", "-c", "echo init done; sleep 2"]
  containers:
  - name: app
    image: nginx:1.25
    ports:
    - containerPort: 80
    readinessProbe:
      httpGet:
        path: /
        port: 80
      initialDelaySeconds: 3
      periodSeconds: 5
    livenessProbe:
      httpGet:
        path: /
        port: 80
      initialDelaySeconds: 10
      periodSeconds: 10
    lifecycle:
      preStop:
        exec:
          command: ["sh", "-c", "sleep 5"]
  terminationGracePeriodSeconds: 30
EOF

# 2. Watch phase transitions in real time
kubectl get pod lifecycle-demo -w

# 3. Inspect container-level state
kubectl get pod lifecycle-demo -o jsonpath='{.status.containerStatuses[*].state}'

# 4. Check all conditions at once
kubectl get pod lifecycle-demo -o jsonpath='{range .status.conditions[*]}{.type}={.status}{"\n"}{end}'
```

Expected output from `-w` over ~15 seconds:

```
NAME             READY   STATUS     RESTARTS   AGE
lifecycle-demo   0/1     Pending    0          0s
lifecycle-demo   0/1     Init:0/1   0          1s
lifecycle-demo   0/1     PodInitializing   0   4s
lifecycle-demo   0/1     Running    0          5s
lifecycle-demo   1/1     Running    0          9s
```

`READY 0/1` while `STATUS Running` means the app container is running but has not yet passed `readinessProbe`.

### Graceful Termination Flow

When you run `kubectl delete pod` or a Deployment replaces a Pod:

```
kubectl delete pod lifecycle-demo
           │
           ▼
[API Server] sets deletionTimestamp on Pod object
           │
     ┌─────┴──────┐
     │            │
[kubelet]     [Endpoints controller]
runs preStop  removes Pod IP from
hook first    Service Endpoints
     │
     ▼
sends SIGTERM to PID 1 of each container
     │
     ▼
waits up to terminationGracePeriodSeconds (default 30s)
     │
     ▼
if still running: sends SIGKILL
     │
     ▼
kubelet reports containers Terminated
     │
     ▼
API Server garbage-collects Pod object from etcd
```

The `preStop` hook runs **before** SIGTERM. It is your last chance to drain connections, flush buffers, or deregister from a service registry. The total budget is `terminationGracePeriodSeconds`; if the `preStop` hook consumes it all, SIGKILL fires immediately when the timer expires regardless of hook completion.

### Probe Configuration That Works in Production

```yaml
startupProbe:
  httpGet:
    path: /healthz
    port: 8080
  failureThreshold: 30       # 30 * 10s = up to 5 minutes to start
  periodSeconds: 10

livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 0     # startupProbe guards this window
  periodSeconds: 15
  failureThreshold: 3        # restart after 3 consecutive failures (~45s)

readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  periodSeconds: 5
  failureThreshold: 2        # remove from endpoints after 2 failures (~10s)
  successThreshold: 1
```

Separating `/healthz` (liveness) from `/ready` (readiness) is not cosmetic. A Pod that is alive but temporarily overloaded should fail readiness, not liveness. Conflating them causes cascading restarts under load.

---

## Use It

### Where Each Probe Fires in the Wild

| Technology / Pattern | Which probe matters most | Why |
|---|---|---|
| JVM services (Spring Boot) | `startupProbe` | JVM warmup can take 30–90 seconds |
| Databases (Postgres sidecar) | `readinessProbe` | Accept traffic only after WAL replay |
| ML inference servers | `startupProbe` + `readinessProbe` | Model loading is slow; inference queue gates traffic |
| Batch Jobs | None (or liveness only) | `Succeeded` phase is the success signal |
| Sidecars (Envoy, Linkerd) | `readinessProbe` | Proxy must be ready before app container receives traffic |

### Deployment Rolling Update Strategy

A Deployment uses Pod phase and conditions to gate rolling updates:

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1        # one extra Pod above desired count during rollout
    maxUnavailable: 0  # never reduce below desired count
```

With `maxUnavailable: 0`, the rollout controller waits for each new Pod's `Ready` condition to be `True` before terminating an old Pod. This makes the readiness probe the single safety gate for every production deployment.

### PodDisruptionBudgets

PDBs enforce a minimum number of ready Pods during voluntary disruptions (node drains, cluster upgrades):

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: app-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: my-service
```

The eviction API checks this budget before draining a node. If terminating a Pod would violate it, the drain blocks. PDBs only work if your readiness probes accurately reflect service health.

---

## Common Pitfalls

- **Setting `initialDelaySeconds` instead of a `startupProbe`.** A fixed delay is a guess. The JVM might start faster on a warm node or slower under load. Use `startupProbe` with a generous `failureThreshold` so the window is elastic. Overlong `initialDelaySeconds` on `livenessProbe` just delays restarts of genuinely stuck processes.

- **Liveness and readiness pointing at the same endpoint.** When a Pod is temporarily overloaded (e.g., GC pause, upstream timeout), you want it removed from the load balancer, not killed and restarted. Conflating the probes causes cascading restarts exactly when the cluster is under stress.

- **Ignoring `preStop` for stateful workloads.** Without a `preStop` hook or a signal handler, SIGTERM arrives and the process has milliseconds to clean up before SIGKILL. Long-lived TCP connections, write-ahead buffers, and distributed locks can all be left in an inconsistent state.

- **Setting `terminationGracePeriodSeconds` too low.** Values under 10–15 seconds are risky for any non-trivial service. SIGKILL is unconditional. If your process needs to flush a write buffer, finish in-flight requests, or deregister from Consul, it needs time. Set the grace period to match your p99 request latency plus your `preStop` hook duration.

- **Forgetting that `Unknown` phase means "the node is gone, not the Pod."** Operators sometimes delete `Unknown` Pods manually, then wonder why data is duplicated. The Pod may still be running on a partitioned node. If you are operating a StatefulSet, understand node eviction policies before manually deleting Unknown Pods.

---

## Exercises

1. **Easy.** Create a Pod with a `readinessProbe` that checks a `/ready` HTTP endpoint. While the Pod is in `Running` state but before it passes the probe, verify with `kubectl describe pod` that it is not yet added to a Service's `Endpoints`. Then confirm it appears once the probe succeeds.

2. **Medium.** Write a Deployment for a Spring Boot application that would typically take 45 seconds to fully start. Configure a `startupProbe` with a 60-second maximum window, a `livenessProbe` that kicks in only after startup, and a `readinessProbe` that removes the Pod from traffic if the `/actuator/health/readiness` endpoint returns non-200. Set `maxUnavailable: 0` on the rolling update strategy and explain why this combination prevents downtime during rollouts.

3. **Hard.** A StatefulSet with 3 replicas has one Pod enter `Unknown` phase because its node lost network connectivity. Design a recovery procedure that: (a) determines whether the Pod is truly dead or still running on the partitioned node, (b) safely evicts or force-deletes the Pod without risking data corruption, and (c) updates a PodDisruptionBudget so that a simultaneous node drain cannot bring the StatefulSet below quorum during the recovery.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Pod phase** | The current running state of the container | A high-level summary (`Pending`, `Running`, etc.) derived from container states; not the same as whether traffic is flowing |
| **Ready condition** | The pod is "up" | All app containers have passed `readinessProbe`; this is the flag that gates Service endpoint inclusion |
| **Liveness probe** | Checks if the app is healthy | Specifically checks whether to **restart** the container; a failure kills and replaces the process |
| **Readiness probe** | Same as liveness | Controls only **traffic routing** (Endpoints inclusion); a failure does NOT restart the container |
| **preStop hook** | A shutdown script | A lifecycle hook that runs *before* SIGTERM is sent; the entire sequence (hook + drain + SIGTERM + wait) must fit within `terminationGracePeriodSeconds` |
| **Init container** | An optional setup step | A required sequential gate; if any init container fails, the Pod stays `Pending` indefinitely (subject to backoff) |
| **Unknown phase** | Pod has crashed | The kubelet on the node stopped reporting; the Pod may still be running on an isolated node |

---

## Further Reading

- [Kubernetes Docs — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/) — the canonical reference for phases, conditions, and container states.
- [Kubernetes Docs — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/) — official probe configuration guide with working examples.
- [Kubernetes Docs — Termination of Pods](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination) — detailed breakdown of the termination sequence including preStop hooks and grace periods.
- [Kubernetes Docs — Pod Disruption Budgets](https://kubernetes.io/docs/tasks/run-application/configure-pdb/) — how to protect availability during voluntary disruptions tied directly to Pod readiness.
- [Production Kubernetes (O'Reilly)](https://www.oreilly.com/library/view/production-kubernetes/9781492092292/) — chapters 4–6 cover probe tuning, graceful termination, and StatefulSet recovery at production depth.
