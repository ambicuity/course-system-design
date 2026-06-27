# 8 System Design Concepts Explained in 1 Diagram

> Eight non-functional requirements and the architectural patterns that deliver them — the framework behind every reliable distributed system.

**Type:** Learn
**Prerequisites:** Basic distributed systems, networking
**Time:** ~25 minutes

---

## The Problem

Functional requirements are what the system *does* — search, checkout, send a message. Non-functional requirements (NFRs) are how well it does them — fast, always available, never loses data. Every system design conversation eventually comes down to NFRs: *how available? how fast? how consistent? how durable?*

Most engineers learn the patterns (load balancers, CDNs, message queues) without seeing them mapped to the qualities they actually deliver. This lesson draws that mapping explicitly. Eight NFRs, eight architectural patterns, one diagram showing how they fit together.

Knowing this mapping lets you reason backwards from a quality requirement to the pattern that delivers it. "We need 99.99% availability" → "we need redundant instances behind a load balancer." "We need to survive disk failures" → "we need a transaction log and replication."

---

## The Concept

### The eight NFR / pattern pairs

```
   ┌──────────────────────────────────────────────────────────────┐
   │                                                              │
   │   NFR (quality attribute)         Architectural pattern      │
   │   ──────────────────────────     ──────────────────────      │
   │   1. Availability                 Load Balancers              │
   │   2. Latency                      CDN                         │
   │   3. Scalability                  Replication                 │
   │   4. Durability                   Transaction Log             │
   │   5. Consistency                  Eventual Consistency         │
   │   6. Modularity                   Loose Coupling + Cohesion   │
   │   7. Configurability              Configuration as Code       │
   │   8. Resiliency                   Message Queues              │
   │                                                              │
   └──────────────────────────────────────────────────────────────┘
```

Each NFR is delivered by a specific architectural pattern. Some patterns deliver multiple NFRs; some NFRs require multiple patterns.

---

### 1. Availability ← Load Balancers

**NFR:** the system remains operational and accessible to users at all times.

**Pattern:** **load balancers** distribute traffic across multiple service instances to eliminate single points of failure.

```
                   ┌─────────────┐
                   │   Client    │
                   └──────┬──────┘
                          │
                          ▼
                ┌───────────────────┐
                │  Load Balancer    │
                │  (round-robin,    │
                │   least-conns)    │
                └────┬─────┬────┬───┘
                     │     │    │
                     ▼     ▼    ▼
                ┌──────┐ ┌──────┐ ┌──────┐
                │ Svc A│ │ Svc A│ │ Svc A│
                └──────┘ └──────┘ └──────┘

   Availability = uptime when one instance fails
                 (others continue serving)
```

**How it delivers availability:**

- Multiple instances serve the same function
- If one fails, the load balancer routes to the others
- Combined with health checks, failures are detected and traffic shifted

**Availability targets:**

- 99% ("two nines") = 3.65 days downtime per year
- 99.9% ("three nines") = 8.77 hours per year
- 99.99% ("four nines") = 52.6 minutes per year
- 99.999% ("five nines") = 5.26 minutes per year

---

### 2. Latency ← CDN

**NFR:** the time delay experienced in a system between a request and its response.

**Pattern:** **Content Delivery Networks (CDNs)** cache content at edge servers around the world, reducing the physical distance data must travel.

```
   User in Tokyo                User in London
        │                              │
        ▼                              ▼
   ┌──────────┐                  ┌──────────┐
   │ CDN Edge │                  │ CDN Edge │
   │  Tokyo   │                  │  London  │
   └────┬─────┘                  └────┬─────┘
        │                              │
        └──────────────┐  ┌───────────┘
                       │  │
                       ▼  ▼
                  ┌──────────┐
                  │  Origin  │
                  │  Server  │
                  └──────────┘

   Latency = physical distance × network speed
   CDN cuts the long-haul leg
```

**How CDN delivers low latency:**

- Edge servers are physically closer to users (5–50 ms instead of 100–300 ms)
- Static assets (images, CSS, JS) are cached at the edge
- Dynamic content uses edge compute (Cloudflare Workers, Lambda@Edge)
- TLS termination happens at the edge (faster handshake)

**Other latency techniques:**

- Compression (gzip, brotli)
- HTTP/2 or HTTP/3 multiplexing
- Caching at multiple layers
- Database query optimization

---

### 3. Scalability ← Replication

**NFR:** the system's ability to handle increased load by adding resources.

**Pattern:** **replication** distributes data across multiple nodes, enabling higher throughput and workload.

```
   ┌────────────────────┐         ┌────────────────────┐
   │   Primary DB       │────────►│   Replica DB       │  reads
   │   (writes)         │  async  │   (reads)          │  ←──
   └────────────────────┘         └────────────────────┘

   ┌────────────────────┐         ┌────────────────────┐
   │   Primary DB       │────────►│   Replica DB       │
   │   (writes)         │  sync   │   (reads + DR)     │
   └────────────────────┘         └────────────────────┘
```

**How replication delivers scalability:**

- Reads scale horizontally (add replicas)
- Writes either stay on the primary (with read replicas) or are sharded
- Throughput grows linearly with the number of replicas (mostly)

**Replication is not free:**

- Synchronous replication adds write latency
- Asynchronous replication has lag (replicas may be stale)
- Replication conflicts in multi-primary setups

---

### 4. Durability ← Transaction Log

**NFR:** data, once committed, remains safe even in the event of failure.

**Pattern:** the **transaction log (WAL)** persists every operation before applying it to the main data store, allowing the system to reconstruct state after a crash.

```
   Client commit
        │
        ▼
   ┌─────────────────────────────────┐
   │  1. Write to WAL (durable)       │   ← durability point
   │  2. Modify data pages (in mem)   │
   │  3. Confirm to client            │
   └─────────────────────────────────┘

   On crash:
   ┌─────────────────────────────────┐
   │  1. Read WAL                    │
   │  2. Replay uncommitted ops       │
   │  3. Restore consistent state     │
   └─────────────────────────────────┘
```

**How the WAL delivers durability:**

- Every change is recorded on disk before being applied
- On crash, the WAL is replayed to recover committed-but-not-flushed changes
- Combined with backups, the WAL enables point-in-time recovery

**Durability targets:**

- AWS S3: 99.999999999% (eleven nines)
- Typical cloud databases: 99.99%
- Local disks with no replication: 99.9%

---

### 5. Consistency ← Eventual Consistency

**NFR:** all users see the same data at the same time.

**Pattern:** **eventual consistency** allows temporary differences between replicas but synchronizes them over time.

```
   Write to replica A
        │
        ▼
   ┌──────────┐
   │  Replica A│  ←── reads see new value immediately
   └─────┬────┘
         │ async replication
         ▼
   ┌──────────┐
   │  Replica B│  ←── reads see new value after lag
   └──────────┘
```

**The consistency spectrum:**

| Level | Behavior |
|---|---|
| **Strong consistency** | All reads see the latest write; high latency, lower availability |
| **Causal consistency** | Writes that may have caused each other are seen in order |
| **Read-your-writes** | After your write, you always see it; others may not |
| **Eventual consistency** | All replicas converge given enough time without new writes |

**The CAP trade-off:** in a distributed system with network partitions, you choose between consistency and availability. Strong consistency requires rejecting writes during a partition; eventual consistency accepts writes and reconciles.

**Choosing the level:** banking and inventory often need strong consistency; social feeds and analytics can tolerate eventual consistency.

---

### 6. Modularity ← Loose Coupling + High Cohesion

**NFR:** the system is built from well-separated, self-contained components that can be understood, modified, and replaced independently.

**Pattern:** **loose coupling** (components depend on each other as little as possible) and **high cohesion** (each component groups related functionality together).

```
   Loosely coupled, high cohesion:

   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
   │   Billing    │    │   Users      │    │   Search     │
   │   Module     │    │   Module     │    │   Module     │
   │              │    │              │    │              │
   │  - charges   │    │  - profiles  │    │  - indexing  │
   │  - invoices  │    │  - auth      │    │  - ranking   │
   │  - payments  │    │  - prefs     │    │  - facets    │
   └──────────────┘    └──────────────┘    └──────────────┘
      ▲                                    ▲
      │                                    │
      └────── interact via ────────┘
            public interfaces only
```

**What loose coupling looks like:**

- Modules communicate through well-defined interfaces
- Internal state is private to the module
- Replacing one module does not require changing others
- Async messaging (events) for cross-module communication

**What high cohesion looks like:**

- A module's responsibilities are related
- A single reason to change
- A single team can own it

---

### 7. Configurability ← Configuration as Code

**NFR:** the system can be adjusted or modified without altering core logic.

**Pattern:** **Configuration as Code (CaC)** manages infrastructure and application settings via version-controlled files.

```
   ┌──────────────────┐
   │   Git Repo       │
   │  ──────────      │
   │  ├── main.tf     │  Terraform
   │  ├── k8s/        │  Kubernetes manifests
   │  │   └── api.yaml│
   │  ├── app/        │  App config
   │  │   └── config.yaml
   │  └── secrets/    │  Vault or sealed secrets
   └──────────────────┘
        │
        │ CI/CD applies to environments
        ▼
   ┌──────┐  ┌──────┐  ┌──────┐
   │ dev  │  │stage │  │ prod │
   └──────┘  └──────┘  └──────┘
```

**Why CaC:**

- **Reproducibility.** The same config can be applied to dev, staging, prod.
- **Versioning.** Config changes are reviewable, revertable, auditable.
- **DR.** Re-create an environment from config alone.
- **Consistency.** No snowflake servers.

**Tools:**

- **Terraform / Pulumi** — infrastructure
- **Helm / Kustomize** — Kubernetes
- **Ansible / Chef / Puppet** — configuration management
- **Vault / AWS Secrets Manager** — secrets

---

### 8. Resiliency ← Message Queues

**NFR:** the system's ability to recover from failures and continue operating smoothly.

**Pattern:** **message queues** decouple components and buffer tasks, enabling retries, backpressure, and graceful degradation.

```
   ┌──────────┐         ┌──────────┐         ┌──────────┐
   │ Producer │────────►│  Queue   │────────►│ Consumer │
   └──────────┘         └──────────┘         └──────────┘
                            │
                       (buffer)
                            │
                       retry on failure
                       backpressure on overflow
```

**How queues deliver resiliency:**

- **Buffering.** Slow consumers do not back-pressure producers.
- **Retries.** Failed messages are retried with exponential backoff.
- **Dead-letter queues.** Messages that cannot be processed go to a DLQ for inspection.
- **Isolation.** A consumer crash does not affect the producer; messages wait in the queue.
- **Backpressure.** When consumers are overwhelmed, the queue fills; producers can slow down.

**Other resiliency patterns:**

- Circuit breakers (stop calling a failing service)
- Bulkheads (isolate failures)
- Timeouts (every call has a deadline)
- Health checks (detect and replace failed instances)

---

## Build It / In Depth

### The full picture on one diagram

```
                          ┌─────────────┐
                          │   Client    │
                          └──────┬──────┘
                                 │
                                 ▼
                          ┌─────────────┐
                          │    CDN      │ ← Latency
                          └──────┬──────┘
                                 │
                                 ▼
                          ┌─────────────┐
                          │ API Gateway │ ← Auth, Rate Limit
                          └──────┬──────┘
                                 │
                                 ▼
                          ┌─────────────┐
                          │Load Balancer│ ← Availability
                          └──────┬──────┘
                                 │
                ┌────────────────┼────────────────┐
                ▼                ▼                ▼
         ┌──────────┐     ┌──────────┐     ┌──────────┐
         │ Service A│     │ Service B│     │ Service C│
         │ (Billing)│     │ (Users)  │     │ (Search) │
         └─────┬────┘     └─────┬────┘     └─────┬────┘
               │                │                │
               ▼                ▼                ▼
         ┌──────────┐     ┌──────────┐     ┌──────────┐
         │  Cache   │     │  Cache   │     │  Cache   │ ← Latency
         └─────┬────┘     └─────┬────┘     └─────┬────┘
               │                │                │
               ▼                ▼                ▼
         ┌──────────┐     ┌──────────┐     ┌──────────┐
         │ Primary  │     │ Primary  │     │ Primary  │
         │   DB     │────►│   DB     │────►│   DB     │
         └─────┬────┘ Repl└─────┬────┘ Repl└─────┬────┘
               │                │                │
               ▼                ▼                ▼
         ┌──────────┐     ┌──────────┐     ┌──────────┐
         │ Replica  │     │ Replica  │     │ Replica  │ ← Scalability
         └──────────┘     └──────────┘     └──────────┘

   ┌─────────────────────────────────────────────────┐
   │  WAL (write-ahead log on every primary)         │ ← Durability
   └─────────────────────────────────────────────────┘

   ┌─────────────────────────────────────────────────┐
   │  Eventual consistency across replicas (async)    │ ← Consistency
   └─────────────────────────────────────────────────┘

   ┌─────────────────────────────────────────────────┐
   │  Message queue for async work + retries         │ ← Resiliency
   └─────────────────────────────────────────────────┘

   ┌─────────────────────────────────────────────────┐
   │  Configuration as code (Terraform, Helm, Vault) │ ← Configurability
   └─────────────────────────────────────────────────┘
```

Every NFR is delivered by a specific layer. Most production systems use all eight.

---

### Mapping NFRs to concrete patterns

| NFR | Question it answers | Pattern(s) |
|---|---|---|
| **Availability** | Will it be up? | Load balancer, multiple instances, health checks |
| **Latency** | Is it fast? | CDN, cache, optimized queries, edge compute |
| **Scalability** | Can it grow? | Replication, sharding, stateless services |
| **Durability** | Is data safe? | WAL, backups, multi-AZ replication |
| **Consistency** | Do users see the same data? | Replication + eventual consistency + read-your-writes handling |
| **Modularity** | Can parts change independently? | Loose coupling, high cohesion, clear interfaces |
| **Configurability** | Can we adjust without rebuilding? | Configuration as code, environment variables, feature flags |
| **Resiliency** | Does it recover from failures? | Message queues, retries, circuit breakers, health checks |

---

## Use It

### When designing a system, start with the NFRs

```
   Functional requirements:  what the system does
   Non-functional:           how well it does it

   Step 1: List the NFRs explicitly.
     - "The system must respond within 200 ms at p99"
     - "The system must be available 99.95% of the time"
     - "The system must not lose data once written"
     - "The system must scale to 1M users"

   Step 2: For each NFR, identify the pattern(s).
     - 200 ms latency → CDN, caching, optimized DB
     - 99.95% availability → load balancer, multiple instances, health checks
     - No data loss → WAL, replication, backups
     - Scale → stateless services, replication, sharding

   Step 3: Compose the patterns into an architecture.
```

This is the heart of system design interviews: starting from NFRs and reasoning to patterns.

---

### Common mistakes when reasoning about NFRs

| Mistake | Why it hurts |
|---|---|
| Specifying NFRs without numbers | "Fast" means nothing; "p99 < 200 ms" is testable |
| Hitting every NFR at maximum level | Trade-offs are real; choosing all "five nines" is unaffordable |
| Confusing durability with availability | Data not lost ≠ system responds; both matter, separately |
| Adding patterns without measuring need | A CDN for a single-region app adds latency, not removes it |
| Ignoring cost as an NFR | Reliability at any price is unsustainable |
| Believing CAP is a choice you opt into | CAP applies to every distributed system; you make the choice, even implicitly |

---

## Common Pitfalls

- **Treating NFRs as a checklist.** They interact; choosing one often trades against another. Reason about them together.

- **Optimizing for the wrong NFR.** Building for 99.999% availability when the requirement is 99.9% wastes money. Specifying p99 < 50 ms when p99 < 500 ms is acceptable wastes engineering.

- **Confusing latency with throughput.** Latency is per-request time. Throughput is requests-per-second. They are independent; you can have low latency and low throughput, or high latency and high throughput.

- **Believing a CDN always helps.** If your content is dynamic and personalized, a CDN adds complexity without latency benefit.

- **Ignoring operational NFRs.** "It must be deployable in 5 minutes" is an NFR. "On-call must be sustainable" is an NFR. Treat them with the same rigor as latency and availability.

- **No monitoring for the NFRs.** If you cannot measure p99 latency, you cannot tell whether you are meeting your NFR.

---

## Exercises

1. **Easy** — Pick three NFRs from the eight. For each, describe the pattern that delivers it in one sentence and one example of a system that uses it.

2. **Medium** — Take a real system (a web app, a mobile app, a backend service). Identify which of the eight NFRs are explicitly addressed, which are implicit, and which are missing. Propose patterns to address the missing ones.

3. **Hard** — Design a system for a new real-time collaboration tool (think Figma or Notion). Write down the NFRs explicitly with numbers (e.g., "p99 latency < 100 ms for cursor updates"). For each NFR, choose the pattern. Justify each choice with the trade-off you accepted.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Non-functional requirement | A soft requirement | A quality attribute of a system — availability, latency, durability, consistency, scalability — that determines how well functional requirements are met |
| Load balancer | A router | A component that distributes traffic across multiple instances to improve availability and throughput |
| CDN | A cache | A geographically distributed network of edge servers that serve content close to users |
| Replication | Backup | Copying data across multiple instances for availability, fault tolerance, and read scaling |
| Transaction log (WAL) | A log file | A durable append-only record of every change that allows recovery after crashes |
| Eventual consistency | Weak consistency | A consistency model where replicas converge over time; allows temporary divergence in exchange for availability and performance |
| Loose coupling | Decoupling | An architectural property where components depend on each other as little as possible, communicating through well-defined interfaces |
| Configuration as code | Infrastructure as code | Managing infrastructure and application settings via version-controlled files, applied consistently across environments |

---

## Further Reading

- **"Designing Data-Intensive Applications"** — Martin Kleppmann's book; the canonical reference for distributed systems: https://dataintensive.net/
- **"Software Engineering at Google"** — lessons on NFRs and SRE practices: https://abseil.io/resources/swe-book
- **AWS Well-Architected Framework** — five pillars (operational excellence, security, reliability, performance, cost) with concrete recommendations: https://aws.amazon.com/architecture/well-architected/
- **Google SRE Book** — the source of SLOs, error budgets, and the discipline of NFR-driven operations: https://sre.google/sre-book/table-of-contents/
- **Microsoft Azure Architecture Center** — practical patterns and trade-offs: https://learn.microsoft.com/en-us/azure/architecture/