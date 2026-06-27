# The System Design Topic Map

> System design is not one skill — it is six interconnected domains, and knowing which domain owns your problem is half the solution.

**Type:** Learn
**Prerequisites:** What Is System Design, Non-Functional Requirements (NFRs)
**Time:** ~20 minutes

---

## The Problem

Imagine you are three hours into a system design interview — or worse, three weeks into a production incident — and you realize you have been optimizing the wrong layer. You tuned database indexes for twenty minutes while the real bottleneck was a synchronous HTTP fan-out in your application layer. Or you spent a sprint hardening authentication while an unthrottled endpoint quietly exhausted your downstream services.

This happens because most engineers treat system design as an undifferentiated mass of concepts. Caching, Kubernetes, OAuth, eventual consistency, circuit breakers — they all feel equally relevant all the time. Without a map, every decision is a guess about where to look next.

The System Design Topic Map solves this by partitioning the entire knowledge space into six named domains, each with a clear ownership boundary. Once you internalize the map, you can quickly identify which domain a problem belongs to, what the relevant levers are within that domain, and how cross-domain interactions create the trade-offs you have to manage. The map does not replace depth — it tells you where to go deep.

---

## The Concept

### The Six Domains

```
┌─────────────────────────────────────────────────────────────────────┐
│                     SYSTEM DESIGN TOPIC MAP                         │
│                                                                     │
│  ┌─────────────────────┐        ┌─────────────────────────────┐    │
│  │  1. Application     │        │  2. Network &               │    │
│  │     Layer           │◄──────►│     Communication           │    │
│  │                     │        │                             │    │
│  │  Availability       │        │  HTTP/gRPC/WebSocket        │    │
│  │  Scalability        │        │  REST vs GraphQL            │    │
│  │  Reliability        │        │  Message Queues             │    │
│  │  OOP / DDD          │        │  Event-Driven Arch          │    │
│  │  Microservices      │        │  Service Mesh               │    │
│  │  Clean Architecture │        │                             │    │
│  └─────────┬───────────┘        └──────────────┬──────────────┘    │
│            │                                   │                   │
│            ▼                                   ▼                   │
│  ┌─────────────────────┐        ┌─────────────────────────────┐    │
│  │  3. Data Layer      │        │  4. Scalability &           │    │
│  │                     │◄──────►│     Reliability             │    │
│  │  Schema Design      │        │                             │    │
│  │  Indexing           │        │  Horizontal Scaling         │    │
│  │  SQL vs NoSQL       │        │  Caching Strategies         │    │
│  │  Transactions       │        │  Load Balancing             │    │
│  │  Replication        │        │  Rate Limiting              │    │
│  │  Sharding           │        │  Circuit Breakers           │    │
│  │  Leader Election    │        │                             │    │
│  └─────────┬───────────┘        └──────────────┬──────────────┘    │
│            │                                   │                   │
│            ▼                                   ▼                   │
│  ┌─────────────────────┐        ┌─────────────────────────────┐    │
│  │  5. Security &      │        │  6. Infrastructure &        │    │
│  │     Observability   │        │     Deployments             │    │
│  │                     │        │                             │    │
│  │  OAuth 2.0 / JWT    │        │  CI/CD Pipelines            │    │
│  │  PASETO / Sessions  │        │  Containers / Kubernetes    │    │
│  │  RBAC / ABAC        │        │  Serverless                 │    │
│  │  Threat Modeling    │        │  IaC (Terraform)            │    │
│  │  Monitoring         │        │  Disaster Recovery          │    │
│  │  Tracing / Logging  │        │                             │    │
│  └─────────────────────┘        └─────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### Domain Breakdown

| # | Domain | Core Question | Key Levers |
|---|--------|---------------|------------|
| 1 | **Application Layer** | How does the system behave as a unit? | Architecture style, NFRs, coupling |
| 2 | **Network & Communication** | How do components talk to each other? | Protocol choice, sync vs async, back-pressure |
| 3 | **Data Layer** | How is data stored, retrieved, and kept consistent? | DB type, indexes, replication, sharding |
| 4 | **Scalability & Reliability** | How does the system handle load and failure? | Caching, LB, circuit breakers, partitioning |
| 5 | **Security & Observability** | Can we trust the system and understand it? | AuthN/AuthZ, encryption, metrics, traces |
| 6 | **Infrastructure & Deployments** | How does software go from code to running? | Containers, IaC, CI/CD, DR |

### Why Six Domains, Not More or Fewer?

The domains are not arbitrary. They map onto real organizational boundaries:
- A **platform team** owns domains 4 and 6.
- A **backend team** owns domains 1, 2, and 3.
- A **security/SRE team** owns domain 5, with visibility into all others.

More granular cuts (e.g., splitting caching from load balancing) create friction without clarity. Fewer cuts (e.g., collapsing data + scalability) obscure the conceptual separation between "what your data model looks like" and "how you spread load across nodes."

### How Domains Interact

No system lives in a single domain. The map's real power is in tracing cross-domain cause-and-effect:

```
User request → [Network & Communication: which protocol, sync or async?]
                       │
                       ▼
             [Application Layer: which service handles this? how does it fail?]
                       │
                       ▼
             [Data Layer: which DB? consistent read or eventual?]
                       │
                ┌──────┴──────┐
                ▼             ▼
      [Scalability &    [Security &
       Reliability]      Observability]
      "Can this         "Is this call
       handle 10x?"]     authorized?
                         Can we trace it?"]
```

A decision in one domain constrains options in others. Choosing microservices in domain 1 immediately creates synchronous communication complexity in domain 2, distributed transaction complexity in domain 3, and deployment complexity in domain 6.

---

## Build It / In Depth

### Mapping a Real System: URL Shortener

Walk through the topic map as a diagnostic tool applied to a classic design problem.

**Step 1 — Application Layer**

Decide architectural style and NFRs before anything else.

- Target: 100M redirects/day, 1M new URLs/day
- Availability SLA: 99.99% (52 min/year downtime)
- NFRs: low read latency (<10 ms p99), high write throughput, eventual consistency on analytics is acceptable

Architecture decision: stateless application servers (reads are the hot path, can scale horizontally).

**Step 2 — Network & Communication**

Decide how clients reach the system and how internal components communicate.

```
Client ──HTTP GET /abc123──► Edge CDN ──► API Gateway ──► Redirect Service
                                                              │
                                        async write ──────────► Analytics Queue
```

- External: plain HTTPS (REST), GET-only for redirects — simplest, cache-friendly
- Internal: gRPC between Redirect Service and URL Store for low latency
- Analytics: async via a message queue (Kafka) — domain 3 writes do not block domain 2 latency

**Step 3 — Data Layer**

```
URL Mapping Store:
  Key:   short_code (6 chars, base62)
  Value: original_url, created_at, user_id, expiry

Options:
  ┌──────────────┬─────────────────────────────────────────┐
  │ PostgreSQL   │ Strong ACID, complex queries, sharding  │
  │              │ needed at scale                         │
  ├──────────────┼─────────────────────────────────────────┤
  │ DynamoDB     │ Key-value, horizontal scale by default, │
  │              │ limited query flexibility               │
  ├──────────────┼─────────────────────────────────────────┤
  │ Cassandra    │ Write-optimized, wide-column, eventual  │
  │              │ consistency acceptable for analytics    │
  └──────────────┴─────────────────────────────────────────┘
Decision: DynamoDB for URL mappings (key-value access, auto-sharded).
          PostgreSQL for user/account data (relational, low write volume).
```

**Step 4 — Scalability & Reliability**

```
Read path (hot):
  Client → CDN cache (TTL 24h) → API Gateway → Redirect Service → DynamoDB DAX
                                                          ↑
                                              In-process LRU cache (10k entries)

Write path (cooler):
  Client → API Gateway → URL Generator → DynamoDB (primary write)
                                       → Kafka (analytics)

Reliability:
  - Circuit breaker on DynamoDB calls (Hystrix / Resilience4j)
  - Rate limiting at API Gateway: 100 req/s per user
  - Read replicas in two regions (active-passive failover)
```

**Step 5 — Security & Observability**

```
AuthN: JWT tokens for user-facing write API (create short URL)
AuthZ: ownership check — only the creating user can delete/update
Threats: short URL abuse (spam), analytics data poisoning from bots

Observability:
  Metrics: redirect latency histogram, cache hit ratio, write throughput
  Traces:  OpenTelemetry spans across CDN → Gateway → Service → DB
  Logs:    structured JSON, ship to ELK / CloudWatch
```

**Step 6 — Infrastructure & Deployments**

```
Containers: Docker images, deployed via Kubernetes (EKS)
IaC:        Terraform modules for DynamoDB tables, Kafka topics, IAM roles
CI/CD:      GitHub Actions → build → unit test → integration test → canary deploy
DR:         DynamoDB global tables (multi-region writes), daily snapshots to S3
```

This six-pass diagnostic ensures nothing is overlooked and each decision is made in the right context.

---

## Use It

### Real-World Systems Mapped to Domains

| System | Dominant Domain | Key Complexity |
|--------|-----------------|----------------|
| Netflix streaming | Network & Communication | Adaptive bitrate, CDN, real-time state |
| Google Spanner | Data Layer | Global distributed transactions, TrueTime |
| Uber surge pricing | Application Layer | Domain logic, event-driven price signals |
| Cloudflare DDoS | Scalability & Reliability | Rate limiting at edge, anycast routing |
| AWS IAM | Security & Observability | RBAC, policy evaluation, audit trail |
| GitHub Actions | Infrastructure & Deployments | CI/CD orchestration, runner autoscaling |

### How to Use the Map in Practice

**In an interview:** After restating requirements, explicitly name which domain you are entering before you dive into it. "Moving to the data layer — let me pick the right database type here." This signals structured thinking and prevents you from collapsing six domains into a chaotic stream of buzzwords.

**In incident response:** During an outage, the map is a checklist. Work top-down: Is the application logic misbehaving (domain 1)? Is a network call timing out (domain 2)? Is a DB query unindexed (domain 3)? Is a cache hot (domain 4)? Are auth tokens expired (domain 5)? Did a bad deploy go out (domain 6)?

**In architecture reviews:** Frame each RFC section around one domain. Reviewers immediately know what lenses to apply (e.g., a data-layer reviewer does not need to evaluate the CI/CD section).

---

## Common Pitfalls

- **Jumping to data layer before application layer.** Engineers love picking databases. Resist. The architecture style (microservices vs. modular monolith) and NFRs must be set first — they determine your data access patterns, not the reverse.

- **Treating domain 4 (Scalability & Reliability) as the default answer to every problem.** Adding a cache or a load balancer does not fix a poorly designed schema or an algorithm that is O(n²). Reach for scalability tools only after the lower domains are sound.

- **Conflating security (domain 5) with authentication alone.** AuthN is entry-point 5a. Threat modeling, data encryption at rest, secrets management, audit logging, and network policies are equally part of domain 5. Leaving them out creates a system that is authenticated but not secure.

- **Skipping observability during the design phase.** Teams frequently add monitoring as an afterthought, then lack the instrumentation needed to diagnose their first production incident. Observability should be designed in domain 5 as a first-class concern, not bolted on in domain 6 post-launch.

- **Ignoring cross-domain coupling.** Choosing event-driven architecture in domain 2 (async messaging) introduces ordering and idempotency requirements in domain 3 (data layer). Calling a decision "just a communication choice" while ignoring its data consistency implications is how subtle bugs survive code review.

---

## Exercises

1. **Easy** — Take any system you use daily (e.g., a messaging app, an e-commerce site). Write down two or three specific design concerns that belong to each of the six domains. The goal is to practice recognizing which domain a concern belongs to before trying to solve it.

2. **Medium** — Design a rate limiter for a public REST API. Walk through each of the six domains in order: what does the application layer decide? What protocol is involved? How is state stored (and where)? How does the rate limiter itself scale? How are limits enforced per user (security)? How is the rate limiter deployed? Write a one-paragraph answer per domain.

3. **Hard** — Pick a system you have worked on or know well. Draw a diagram showing at least three cross-domain interactions (e.g., a scalability decision in domain 4 that creates a consistency constraint in domain 3, which in turn affects your choice of architecture in domain 1). Document the trade-off chain and identify the point where you had the most leverage to make a different decision.

---

## Key Terms

| Term | What people think | What it actually means |
|------|------------------|------------------------|
| **Scalability** | Making the system faster | The ability to handle increasing load by adding resources, without redesigning core logic |
| **NFR** | A nice-to-have wish list | A non-functional requirement: a constraint on system behavior (latency, availability, throughput) that shapes every architectural decision |
| **Domain-Driven Design (DDD)** | An OOP pattern | A modeling approach where software structure mirrors business sub-domains and their language, enforced through bounded contexts |
| **Eventual Consistency** | Data might be wrong | A consistency model where all replicas will converge to the same value, given no new writes — reads during propagation may see stale data |
| **Observability** | Just having logs and metrics | The ability to infer internal system state from external outputs (metrics, logs, traces) without needing to redeploy or instrument after the fact |
| **Sharding** | Splitting a database | Horizontal partitioning of data across multiple nodes by a shard key, so each node owns a non-overlapping subset of the total dataset |
| **Bounded Context** | A microservice | A DDD concept: an explicit boundary within which a domain model is defined and applicable; it is not necessarily a deployment unit |

---

## Further Reading

- **Designing Data-Intensive Applications** (Martin Kleppmann) — https://dataintensive.net — The definitive reference for domains 3 and 4; covers replication, partitioning, transactions, and consistency in depth.
- **AWS Well-Architected Framework** — https://aws.amazon.com/architecture/well-architected/ — Six pillars (operational excellence, security, reliability, performance, cost, sustainability) that map closely onto the six topic-map domains.
- **System Design Primer** (GitHub) — https://github.com/donnemartin/system-design-primer — Open-source collection of system design interview topics and worked examples covering all six domains.
- **Google SRE Book** — https://sre.google/sre-book/table-of-contents/ — Free online; covers domains 4, 5, and 6 from the perspective of running production systems at scale.
