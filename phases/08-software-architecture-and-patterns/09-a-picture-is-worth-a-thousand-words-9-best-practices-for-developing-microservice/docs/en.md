# A picture is worth a thousand words: 9 best practices for developing microservices

> Nine rules that separate microservices that work from microservices that produce a distributed monolith — distilled from the patterns used by teams that have done it well.

**Type:** Learn
**Prerequisites:** Microservices basics, distributed systems familiarity
**Time:** ~25 minutes

---

## The Problem

Microservices solve real problems — independent scaling, independent deploys, team autonomy — but they also create new ones: network failures, distributed transactions, observability across services, data consistency. Teams that adopt microservices without understanding the trade-offs often end up with a **distributed monolith**: all the operational cost of microservices, none of the benefits.

The practices that follow are the ones that distinguish successful microservice architectures from failed ones. They are not optional. They are what makes microservices worth the complexity. Skip them and you will rebuild a monolith with extra steps.

This lesson walks through nine best practices — each with a clear problem it solves and a concrete way to apply it.

---

## The Concept

### The nine best practices

```
   1. Separate data storage per service
   2. Single responsibility per service
   3. Stateless services
   4. Container-based deployment
   5. Container orchestration
   6. Domain-Driven Design (DDD) for boundaries
   7. Independent build per service
   8. Code maturity uniformity
   9. Micro frontend for the UI layer
```

Each addresses a specific failure mode. Together, they form the operational discipline that microservices require.

---

### 1. Separate data storage for each service

**The rule:** each service owns its data. Other services access it only through the owning service's API.

```
   ┌──────────┐                  ┌──────────┐
   │  Users   │                  │ Billing  │
   │  Service │ ──── API call ──►│ Service  │
   └────┬─────┘                  └────┬─────┘
        │                             │
        ▼                             ▼
   ┌──────────┐                  ┌──────────┐
   │  users   │                  │ invoices │
   │ database │                  │ database │
   └──────────┘                  └──────────┘
       NO direct database access between services
```

**Why this matters:**

- **No tight coupling.** If service A reaches into service B's database, they are coupled at the schema level. Changing B's schema breaks A.
- **Independent evolution.** Service B can change its data model without coordinating with A.
- **Failure isolation.** A runaway query on B's data does not affect A's data.

**The trap:** "let me just query their database directly — it's faster than calling the API." That is how distributed monoliths are born. The performance gain is temporary; the coupling is permanent.

**Pragmatic exception:** for read-only access to reference data, some teams allow direct queries to a published view (a separate read replica or a published table). This is acceptable if it is explicitly designed, not a shortcut.

---

### 2. Single responsibility per service

**The rule:** each service does one thing well. The "micro" in microservices refers to the scope of the service, not the size of its codebase.

**Good service boundaries:**

- User management
- Billing
- Search
- Notifications
- Recommendations

**Bad service boundaries:**

- "Database service" (too infrastructure-y)
- "Business logic service" (too vague)
- "Everything service" (just a monolith with extra steps)

**The diagnostic test:** if you cannot describe the service in one sentence without using "and," it does too much.

> "The user service manages user accounts, profiles, and authentication." ✓
> "The user service manages users and handles billing and sends notifications." ✗

The boundary should align with a **bounded context** from domain-driven design.

---

### 3. Stateless services

**The rule:** any service instance can handle any request. No per-instance state, no per-instance storage of session data.

```
   Stateless service:
   ┌──────────┐
   │ Instance │ ─── handles request ───┐
   └──────────┘                          │
   ┌──────────┐                          │
   │ Instance │ ─── handles request ───┐│
   └──────────┘                         ││
                                        ▼▼
                              ┌────────────────────┐
                              │ External storage   │
                              │ (DB, cache, queue) │
                              └────────────────────┘
```

**Why stateless matters:**

- **Horizontal scaling.** Add instances to handle more load. Remove them when load drops. No rebalancing required.
- **Failure recovery.** When an instance dies, the load balancer sends the next request to another instance. No state to recover.
- **Deployments.** Deploy a new version by killing old instances and starting new ones. No state migration.

**What "stateless" does not mean:**

- No persistence — services can have databases (the database is shared state, not instance state).
- No memory cache — caching is fine, but treat the cache as recoverable, not authoritative.
- No configuration — services have config, but config is loaded from external sources, not hardcoded per instance.

**What to externalize:**

- Session state → Redis or a session service
- File uploads → object storage (S3)
- Cached computations → Redis or Memcached
- Scheduled jobs → a job queue (SQS, RabbitMQ, Celery)

---

### 4. Container-based deployment

**The rule:** services ship as containers (Docker images). The container is the unit of deployment.

```
   ┌─────────────────────┐
   │  Container image    │
   │  ────────────────   │
   │  - Code             │
   │  - Runtime          │
   │  - Dependencies     │
   │  - Configuration    │
   │  - Health checks    │
   └──────────┬──────────┘
              │  deployed to:
              ▼
   ┌─────────────────────┐
   │  Kubernetes /       │
   │  ECS / Nomad / etc  │
   └─────────────────────┘
```

**Why containers:**

- **Consistency.** Same image runs locally, in CI, in staging, in production. No "works on my machine."
- **Isolation.** Each service has its own dependencies; no conflicts.
- **Reproducibility.** The image is a precise artifact; rebuilding it produces the same bytes.
- **Efficiency.** Containers share the host kernel; less overhead than VMs.

**Container essentials for production:**

- Minimal base image (Alpine, distroless)
- Multi-stage build (build artifacts separated from runtime)
- Non-root user inside the container
- Health check endpoint (`HEALTHCHECK` in Dockerfile)
- Resource limits (CPU, memory)
- Restart policy

---

### 5. Container orchestration

**The rule:** use an orchestrator (Kubernetes, ECS, Nomad, Cloud Run) to manage containers in production.

```
   ┌──────────────────────────────────────────────────┐
   │  Orchestrator (Kubernetes)                       │
   │  ──────────────────────────                      │
   │  - Schedule containers on nodes                  │
   │  - Scale horizontally based on load              │
   │  - Self-heal (restart failed containers)         │
   │  - Rolling updates with rollback                 │
   │  - Service discovery (DNS)                       │
   │  - Secret management                             │
   │  - Network policies                              │
   └──────────────────────────────────────────────────┘
```

**What the orchestrator handles so you do not have to:**

- **Deployment.** Rolling updates, blue/green, canary — all declarative
- **Scaling.** HPA (horizontal pod autoscaler) adds instances when CPU or memory crosses a threshold
- **Self-healing.** Restart on failure, replace on liveness check failure
- **Service discovery.** Pods get DNS names; service discovery is automatic
- **Resource isolation.** CPU/memory requests and limits per container
- **Secrets.** Inject credentials without putting them in images

**When you do not need an orchestrator:** if you have 2–5 services and a single server, a simple Docker Compose setup may be enough. Add an orchestrator when you need any of: auto-scaling, multi-host deployment, sophisticated deployment strategies.

---

### 6. Domain-Driven Design (DDD) for service boundaries

**The rule:** use DDD's bounded context concept to identify where one service ends and another begins.

**The core idea:**

Each part of the business has its own *ubiquitous language* — its own vocabulary and model. The same word means different things in different contexts:

```
   "Customer" in the Sales context:
     - name, address, billing info, sales rep
     - lifecycle: lead → prospect → customer → churned

   "Customer" in the Support context:
     - name, contact info, ticket history, sentiment
     - lifecycle: new → active → escalated → resolved

   "Customer" in the Shipping context:
     - name, address, delivery preferences, tracking history
     - lifecycle: pending → in transit → delivered
```

These are different models. They live in different bounded contexts. They become different services.

**The DDD workflow:**

1. **Event storming** — a workshop where domain experts and engineers map out the business events. The clusters that emerge are candidate bounded contexts.
2. **Bounded context identification** — group related events, commands, and aggregates into contexts. Each context becomes a service.
3. **Context mapping** — define how contexts interact (synchronous API, async events, shared kernel, etc.).

**Why DDD boundaries are better than technical boundaries:**

- They reflect the business, not the code structure
- They survive team changes
- They tell you where to make trade-offs (consistency within a context, eventual consistency across)

---

### 7. Independent build per service

**The rule:** each service has its own build pipeline, version, and release cadence.

```
   Service A repo             Service B repo
   ┌──────────────┐            ┌──────────────┐
   │  src/        │            │  src/        │
   │  Dockerfile  │            │  Dockerfile  │
   │  tests/      │            │  tests/      │
   └──────┬───────┘            └──────┬───────┘
          │                           │
          ▼                           ▼
   ┌──────────────┐            ┌──────────────┐
   │  CI builds   │            │  CI builds   │
   │  Service A   │            │  Service B   │
   │  v1.4.2      │            │  v2.1.0      │
   └──────┬───────┘            └──────┬───────┘
          │                           │
          ▼                           ▼
   ┌──────────────┐            ┌──────────────┐
   │  Registry:   │            │  Registry:   │
   │  service-a   │            │  service-b   │
   │  :1.4.2      │            │  :2.1.0      │
   └──────────────┘            └──────────────┘
```

**Why independent builds:**

- **Deploy when ready.** Service A can ship three times a day while Service B ships weekly.
- **No version coupling.** Service A's v1.4.2 and Service B's v2.1.0 can coexist.
- **Faster CI.** A small change to one service triggers a build of just that service, not the whole system.

**Implementation:**

- **One repo per service.** Polyrepo is the most common pattern; monorepo with per-service build configs also works.
- **Semantic versioning.** Each service has its own version line.
- **Own CI pipeline.** Each service builds, tests, and publishes its own image.
- **Independent deployment.** Pushing a new version of Service A does not affect Service B.

---

### 8. Code maturity uniformity

**The rule:** code within a service should be at a similar level of quality. Avoid the "big ball of mud" inside an otherwise clean architecture.

**The problem:**

```
   Service A:
   ┌─────────────────────────────┐
   │  80% well-tested, clean    │
   │                             │
   │  Legacy module (untouched)  │  ← hidden rot
   │  - No tests                 │
   │  - Spaghetti code           │
   │  - Three different authors  │
   └─────────────────────────────┘
```

The legacy module is the part that breaks. The clean code around it provides no protection because the boundaries between the modules are leaky.

**The discipline:**

- When you touch a module, leave it slightly better than you found it (the boy scout rule).
- New code meets current standards; old code is brought up to standard incrementally.
- Tests are required for new code; adding tests to old code is encouraged but not gated.
- Refactoring tasks are valued, not deprioritized.

**The goal:** no service should have "that one place nobody wants to touch."

---

### 9. Micro frontend for the UI layer

**The rule:** the frontend mirrors the backend's service boundaries. Each service owns a piece of the UI; the pieces compose into the full application.

```
   ┌──────────────────────────────────────────┐
   │  Shell (top-level layout, navigation)    │
   │  ─────────────────────────────────       │
   │  ┌────────────┐  ┌────────────┐          │
   │  │  User      │  │  Billing   │          │
   │  │  frontend  │  │  frontend  │          │
   │  │  (React)   │  │  (Vue)     │          │
   │  └────────────┘  └────────────┘          │
   │  ┌────────────┐  ┌────────────┐          │
   │  │  Search    │  │  Profile   │          │
   │  │  frontend  │  │  frontend  │          │
   │  └────────────┘  └────────────┘          │
   └──────────────────────────────────────────┘
```

**Why micro frontends:**

- **Independent deployment.** The billing team can ship their UI without touching the user team's UI.
- **Technology flexibility.** Different parts of the UI can use different frameworks if appropriate.
- **Team autonomy.** Each team owns their UI end-to-end (UI, business logic, deployment).

**Implementation patterns:**

- **Module federation** (Webpack 5) — separate builds compose at runtime
- **Web components** — framework-agnostic custom elements
- **iframe composition** — simple but heavy
- **Single-spa** — micro frontend orchestrator
- **Edge-side composition** — server stitches fragments together

**The trade-off:** cross-team coordination on shared UI (navigation, authentication) becomes harder. Use a clear "shell" component owned by a platform team.

---

## Build It / In Depth

### The reference architecture

```
   ┌─────────────────────────────────────────────────────────────┐
   │                                                             │
   │   User Service        Billing Service        Search Service│
   │   ─────────────       ───────────────        ──────────────│
   │   [users DB]          [billing DB]           [search index]│
   │                                                             │
   │   ┌──────────────────────────────────────────────────┐     │
   │   │  API Gateway (auth, rate limit, routing)          │     │
   │   └──────────────────────────────────────────────────┘     │
   │                                                             │
   │   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
   │   │ Event Bus    │  │ Observability│  │ Service      │    │
   │   │ (Kafka / SQS)│  │ (tracing,    │  │ Discovery    │    │
   │   │              │  │  metrics)    │  │ (Consul,     │    │
   │   │              │  │              │  │  K8s DNS)    │    │
   │   └──────────────┘  └──────────────┘  └──────────────┘    │
   │                                                             │
   └─────────────────────────────────────────────────────────────┘
```

Every service:

1. Owns its data (no shared databases)
2. Has a single responsibility
3. Is stateless (all state in external systems)
4. Runs in a container
5. Is deployed via an orchestrator
6. Aligns with a bounded context
7. Has its own build pipeline
8. Maintains internal code quality
9. Has a corresponding micro frontend

---

### Common cross-cutting concerns

Microservices share concerns that need shared solutions:

| Concern | Solution |
|---|---|
| **Authentication** | Centralized identity provider (Auth0, Keycloak); tokens validated at the API gateway |
| **Service-to-service auth** | mTLS, JWT, service mesh (Istio, Linkerd) |
| **Tracing** | OpenTelemetry, Jaeger, Zipkin |
| **Metrics** | Prometheus + Grafana, Datadog |
| **Logging** | Centralized logging (ELK, Loki, CloudWatch) |
| **Configuration** | Vault, AWS Secrets Manager, K8s ConfigMaps/Secrets |
| **Service discovery** | K8s DNS, Consul, AWS Cloud Map |
| **Schema management** | Schema registry (Confluent, Apicurio) |
| **API contracts** | OpenAPI specs, contract tests (Pact) |

---

## Use It

### When to adopt microservices

| Situation | Verdict |
|---|---|
| Greenfield, small team, unclear domain | Start with a modular monolith; promote when pressure appears |
| Existing monolith, growing pains | Refactor to modular monolith first; extract hot modules into services |
| Multiple teams, independent deploy cadence | Microservices with clear DDD boundaries |
| Different scaling per feature | Microservices (or scale within a modular monolith with sharding) |
| Strong fault isolation required | Microservices with proper bulkheads |

### When NOT to adopt microservices

| Situation | Better choice |
|---|---|
| Single team, single domain | Modular monolith |
| Low traffic that fits on one server | Modular monolith |
| Domain not well understood | Modular monolith |
| No operational maturity (no observability, no CI/CD) | Build operational maturity first; modular monolith in the meantime |

---

## Common Pitfalls

- **Distributed monolith.** Services share databases, make synchronous calls in tight loops, and require coordinated deployments. You have the operational cost of microservices without the benefits.

- **Chatty services.** Service A calls B, B calls C, C calls D — for every request. Latency compounds; failures cascade. Fix by aggregating at the edge or using async events.

- **No observability.** Without distributed tracing, you cannot debug cross-service requests. Wire OpenTelemetry from day one.

- **Premature decomposition.** Splitting the monolith into 30 microservices before the boundaries are clear produces a tangled mess. Start with 3–5 services aligned to clear bounded contexts.

- **Shared libraries that grow too big.** A "common" library imported by every service couples them at the code level. Keep shared libraries small and version them carefully.

- **No API contracts.** Services must agree on request/response shapes. Use OpenAPI specs, protobuf, or Avro schemas, validated by contract tests in CI.

- **Eventual consistency confusion.** "I just wrote a record, why can't I read it from the other service?" Because cross-service consistency is eventual, not strong. Design for it; document it.

- **Ignoring Conway's law.** The service boundaries should match the team's communication structure. If two teams must constantly coordinate, they are probably one team.

---

## Exercises

1. **Easy** — Pick three of the nine practices. For each, describe a real situation where skipping it would cause a specific failure.

2. **Medium** — You are designing a microservices architecture for an e-commerce platform. Identify five services, their bounded contexts, their data ownership, and their public APIs. For each, justify the boundary.

3. **Hard** — A team has 12 microservices with 8 different databases, 5 frameworks, and 3 deployment systems. Performance is degrading; incidents are taking hours to resolve. Design a stabilization plan: what to consolidate, in what order, and how to do it without disrupting the business.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Microservice | A small service | A service with a single responsibility, its own data, deployed independently, communicating over the network |
| Distributed monolith | Microservices in trouble | Services that require coordinated deployments or share databases — the worst of both worlds |
| Bounded context | A module | A DDD concept — a boundary within which a particular model is consistent; the natural service boundary |
| Stateless service | A service with no state | A service where any instance can handle any request; all state lives in external systems (DB, cache, queue) |
| Container | A lightweight VM | An OS-level virtualization unit that packages code, runtime, and dependencies; the standard deployment artifact for microservices |
| Orchestrator | A scheduler | Software (Kubernetes, ECS) that schedules, scales, heals, and updates containers in production |
| Polyrepo | One repo per service | Each microservice has its own Git repository, build pipeline, and version line |
| Micro frontend | A small UI | A piece of the UI that mirrors a backend service; independent deployment and technology choice |

---

## Further Reading

- **"Building Microservices"** — Sam Newman's book, the canonical reference: https://samnewman.io/books/building_microservices/
- **"Microservices Patterns"** — Chris Richardson's book on patterns for microservices: https://microservices.io/book/
- **"Domain-Driven Design"** — Eric Evans; the source of the bounded-context concept: https://domainlanguage.com/ddd/
- **"Monolith First"** — Martin Fowler on starting with a monolith: https://martinfowler.com/bliki/MonolithFirst.html
- **12-Factor App** — the methodology that underpins cloud-native microservices: https://12factor.net/
- **Kubernetes Documentation** — the standard orchestrator: https://kubernetes.io/docs/