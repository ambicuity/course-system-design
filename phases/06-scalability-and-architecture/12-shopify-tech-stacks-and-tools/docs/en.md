# Shopify Tech Stacks and Tools

> Boring choices at the core, sharp architecture at the edges — that is how Shopify runs at Black Friday scale without rewriting everything.

**Type:** Learn
**Prerequisites:** Scalability Fundamentals, Database Sharding, Event-Driven Architecture
**Time:** ~35 minutes

---

## The Problem

On Black Friday 2024, Shopify processed 173 billion requests, peaked at 284 million requests per minute, and pushed 12 terabytes of data per minute through its edge network. These are not burst anomalies that engineers hope survive—they are planned targets the system is designed to sustain for an entire day, across hundreds of thousands of merchants with wildly different traffic profiles.

Most e-commerce platforms solve this with a micro-services decomposition: split every domain into its own service, give it its own database, and scale them independently. Shopify rejected that path. The core platform still runs as a single Ruby on Rails application—one of the largest Rails codebases on the planet. That choice sounds reckless until you understand what surrounds it: a pod isolation model, aggressive edge caching via Fastly, MySQL sharding at the tenant level, Kafka for async decoupling, and years of investment in deployment tooling that lets hundreds of engineers ship safely every day.

Without understanding why Shopify made each of these decisions and what they trade away, you will either cargo-cult "just use microservices" or dismiss the monolith as technical debt. Neither is right. The lesson here is how a mature engineering organization layers proven boring tools into a system that achieves outcomes most greenfield microservice architectures cannot.

---

## The Concept

### The Modular Monolith at the Core

Shopify's primary backend is a Rails application called **Shopify Core**. It is not a distributed system in the services sense—all merchant-facing business logic (orders, products, checkouts, payments, fulfillment) lives in one deployable artifact. But it is not an unstructured "big ball of mud" either. It is a **modular monolith**: the codebase is divided into bounded modules that own their database tables, enforce their own API contracts, and cannot call each other's internal implementations directly.

```
Shopify Core (Rails Monolith)
┌─────────────────────────────────────────────────────┐
│  ┌────────────┐  ┌────────────┐  ┌────────────────┐ │
│  │  Orders    │  │ Inventory  │  │   Checkout     │ │
│  │  Module    │  │  Module    │  │   Module       │ │
│  └──────┬─────┘  └──────┬─────┘  └───────┬────────┘ │
│         │               │                │           │
│  ┌──────▼───────────────▼────────────────▼────────┐  │
│  │             Internal Event Bus / Domain APIs    │  │
│  └─────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

The module boundary is enforced in Ruby via Packwerk—a static analysis tool that detects cross-module constant references and rejects them at CI time. This gives the organization most of the isolation benefit of microservices (clear ownership, independent test suites, enforced contracts) while keeping deployment simple (one artifact to test, release, and roll back) and operations cheap (one call stack to trace, one process to profile).

### The Pod Model for Tenant Isolation

Shopify serves hundreds of thousands of merchants. If one merchant's spike takes down a database or a background job queue, every other merchant on that host suffers. The solution is the **pod**: a self-contained slice of the infrastructure assigned to a cohort of shops.

```
                     ┌────────────────────────────────────┐
                     │           Global Load Balancer      │
                     └──────────┬──────────┬──────────────┘
                                │          │
              ┌─────────────────▼──┐  ┌────▼───────────────────┐
              │       Pod A        │  │        Pod B            │
              │                    │  │                         │
              │  Rails + Workers   │  │  Rails + Workers        │
              │  MySQL Shard 1-N   │  │  MySQL Shard N+1-M      │
              │  Redis (session)   │  │  Redis (session)        │
              │  Kafka partition   │  │  Kafka partition        │
              └────────────────────┘  └─────────────────────────┘
```

Each pod has its own MySQL shard set, its own Redis cluster, and its own Kafka partition group. A catastrophic incident in Pod A—a runaway query, an OOM, a corrupt deployment—cannot cascade into Pod B. The routing layer resolves a shop's `shop_id` to a pod assignment at the edge and pins that request for its lifetime. Shop migrations between pods happen via a controlled data-copy process, not live routing changes.

### The Data Layer

**MySQL** is Shopify's primary data store, chosen for ACID semantics and deep ecosystem tooling. Tenancy is implemented via **shop_id** on every table—not a separate schema or database per shop, but a logical partition using a column. Physical sharding splits the MySQL cluster by ranges of `shop_id` so a single machine does not hold every merchant's data.

**Redis** plays two roles: session storage (stateless Rails processes need session affinity via Redis) and a low-latency cache for hot storefront data. Shopify uses a layered caching strategy where Redis sits in front of MySQL for read-heavy paths like product catalog queries.

**Elasticsearch** backs search across products, orders, and admin interfaces. Full-text search semantics are complex enough that it is not worth pushing into MySQL.

### The Async Layer: Kafka and Background Jobs

Shopify processes enormous volumes of async work: webhook delivery, inventory recalculation, email/SMS triggers, fraud analysis. This is handled through **Kafka** for durable event streaming and **Sidekiq** (Redis-backed) for in-process background jobs.

The distinction matters: Kafka is used when events must be consumed by multiple subscribers or must survive process restarts with guaranteed delivery. Sidekiq is used for simpler task queues where fire-and-forget is acceptable. Over time Shopify has migrated more critical async paths from Sidekiq to Kafka as reliability requirements increased.

### The Edge Layer: Fastly and Liquid

**Fastly** is Shopify's CDN and edge network. Storefront HTML, assets, and API responses are cached aggressively at the edge. On Black Friday, the majority of storefront reads never reach the Rails application—Fastly serves a cached HTML response within milliseconds from a PoP near the buyer.

Storefront templates are written in **Liquid**, Shopify's own templating language (open source, originally extracted from Rails). Liquid was designed to run safely in a multi-tenant context: it has no file I/O, no network access, and strict resource limits. Merchants and theme developers can write Liquid without being able to affect other merchants or escape the sandbox.

**Hydrogen** is Shopify's React-based headless storefront framework for merchants who need custom frontend experiences beyond what Liquid allows. Hydrogen apps run on **Oxygen**, Shopify's own edge hosting platform built on Cloudflare Workers.

### GraphQL as the API Surface

Both the Storefront API and the Admin API are GraphQL. This is not a microservices API gateway—the Rails monolith exposes GraphQL endpoints directly. GraphQL was chosen because it composes naturally with Shopify's module structure: each module registers its types and resolvers, and the schema is assembled at boot time. It also lets merchant apps and Shopify-internal services request only the fields they need, reducing payload sizes and database query fan-out.

### Kubernetes and Deployment

Shopify runs on **Google Cloud Platform** (GCP), containerized with Docker and orchestrated by **Kubernetes**. CI/CD is handled via an internal tool called **Shipit**, which implements progressive rollouts: a new version of Shopify Core is deployed to a small percentage of pods, health checks are run, and the rollout is automatically promoted or rolled back. This makes it safe to ship hundreds of times a day across a codebase that handles global production traffic.

---

## Build It / In Depth

### Tracing a Checkout Request End to End

Understanding the stack is easier when you follow one request through it.

```
Browser
  │
  │  HTTPS
  ▼
Fastly Edge (CDN/WAF)
  │  Cache miss → forward to origin
  │
  ▼
GCP Load Balancer (regional)
  │  Routes by shop_id → pod assignment
  ▼
Kubernetes Pod (Rails unicorn/puma workers)
  │
  ├──► Redis         (session lookup)
  ├──► MySQL Shard   (cart, product, pricing reads)
  │      └── Replica reads for non-critical paths
  │
  │  [Checkout submitted]
  │
  ├──► MySQL Shard   (order write, ACID transaction)
  ├──► Kafka         (OrderCreated event published)
  │
  ▼
Response returned to browser

Kafka consumers (async, out of request path):
  ├── Webhook delivery service
  ├── Fraud analysis
  ├── Inventory reservation
  └── Email/SMS trigger
```

The request path keeps synchronous work to a minimum—only what must be committed in the same transaction (the order row) is in the hot path. Everything else is an event consumed asynchronously, which is why checkout latency stays low even when downstream systems are under pressure.

### MySQL Sharding by shop_id

```sql
-- Every table includes shop_id as the first column in its composite primary key
CREATE TABLE orders (
  shop_id    BIGINT      NOT NULL,
  id         BIGINT      NOT NULL AUTO_INCREMENT,
  state      VARCHAR(32) NOT NULL,
  created_at DATETIME    NOT NULL,
  -- ...
  PRIMARY KEY (shop_id, id),
  INDEX idx_orders_created (shop_id, created_at)
);
```

All queries are scoped to a `shop_id`:

```ruby
# In Rails, every query automatically includes the shop scope
Order.where(shop_id: current_shop.id, state: "pending")
```

The shard router maps `shop_id` → database host at connection time. Cross-shard queries do not exist in the critical path—each shop's data lives entirely within one shard set.

### Packwerk Module Boundary Enforcement

```ruby
# packwerk.yml at module root
# app/components/orders/package.yml
enforce_dependencies: true
enforce_privacy: true
public_path: app/components/orders/public/
```

If `Checkout::Service` tries to call `Orders::InternalHelper` (a private constant), Packwerk raises a violation at CI time:

```
orders/app/components/checkout/service.rb
  Dependency violation: ::Orders::InternalHelper is private to 'orders'
  Use the public API: Orders::PublicApi.find(...)
```

This is the mechanical enforcement that keeps the monolith from rotting into a dependency spaghetti even as the team grows to hundreds of engineers.

---

## Use It

| Layer | Tool | Why Shopify Uses It | When You Should Use It |
|-------|------|---------------------|------------------------|
| Core backend | Ruby on Rails | Battle-tested, huge talent pool, ActiveRecord reduces query boilerplate | Mid-to-large teams where developer velocity > raw throughput |
| Tenant isolation | Pod model | Limits blast radius without full microservices overhead | Multi-tenant SaaS with noisy-neighbor risk |
| Primary database | MySQL (InnoDB) | ACID, mature tooling, Vitess compatibility | Any transactional workload requiring consistency |
| Caching | Redis | Sub-millisecond latency, rich data structures, Lua scripting | Session storage, hot read caches, distributed locks |
| Event streaming | Kafka | Durable, replayable, fan-out to multiple consumers | Audit logs, webhooks, cross-module async communication |
| Background jobs | Sidekiq | Simple, Redis-backed, integrates natively with Rails | Fire-and-forget tasks that don't need Kafka durability |
| CDN / Edge | Fastly | Programmable with VCL/Compute@Edge, sub-10ms cache hits | Storefront caching, DDoS mitigation, A/B at the edge |
| Storefront templates | Liquid | Safe sandbox, no execution escape in multi-tenant context | Any multi-tenant context where merchants write templates |
| Headless storefronts | Hydrogen + Oxygen | React DX, edge-rendered, tight Shopify API integration | Custom merchant frontends needing React flexibility |
| Search | Elasticsearch | Full-text + faceted search, kibana for observability | Product/order search, admin search, analytics |
| Container orchestration | Kubernetes on GCP | Autoscaling, pod-level health checks, rolling deploys | Any containerized workload at scale |
| Static analysis / modules | Packwerk | Enforces module contracts without runtime overhead | Large Rails monorepos where boundaries must be maintained |

---

## Common Pitfalls

- **Treating the modular monolith as a stepping stone, not a destination.** Many teams plan to "start monolith, then extract microservices." Shopify has deliberately kept the monolith for core commerce logic even at massive scale. If you extract too early, you pay the distributed systems tax (network latency, partial failures, distributed transactions) before your load justifies it.

- **Confusing tenant isolation with database-per-tenant.** Shopify uses a single schema with `shop_id` on every table, not a separate database per merchant. Database-per-tenant sounds safe but becomes an operational nightmare at tens of thousands of tenants. `shop_id`-scoped rows with proper indexing and shard routing achieves the same isolation at a fraction of the operational cost.

- **Using Kafka for everything async.** Kafka has operational overhead (broker management, partition sizing, consumer group lag monitoring). Sidekiq on Redis is often sufficient for simple task queues. Reach for Kafka only when you need multiple independent consumers, guaranteed delivery with replay, or cross-service event buses.

- **Caching at the wrong layer.** Shopify pushes caching as close to the user as possible (Fastly at the edge) before considering Redis, and Redis before MySQL replicas. Engineers who add Redis caches for queries that Fastly could serve are solving the problem one layer too deep and increasing application complexity unnecessarily.

- **Ignoring module boundary enforcement over time.** Packwerk exists because Rails makes it trivially easy to reach across package boundaries at the cost of long-term coupling. Without tooling that enforces boundaries at CI, even a well-intentioned modular monolith degrades within a year as team size grows. Automate the enforcement; do not rely on code review alone.

---

## Exercises

1. **Easy — Understand the Pod Model.** Draw a diagram of a two-pod Shopify-like system. Label: load balancer, pod routing logic, Rails workers, MySQL shard, Redis, and Kafka partition. Explain in one sentence what happens when Pod A's MySQL shard becomes unavailable.

2. **Medium — Design Tenant Sharding.** You are building a SaaS analytics platform for 50,000 customers. Each customer generates approximately 10,000 events per day. Design the sharding strategy: what column is your shard key, how many shards do you start with, how do you route queries, and what happens when a single customer's traffic spikes 100x on a given day? Identify which of Shopify's patterns directly apply.

3. **Hard — Evaluate the Monolith vs. Microservices Trade-off.** Shopify's checkout processes millions of transactions per minute from a monolith. A startup you advise processes 10,000 transactions per day and is considering extracting their payments service into a microservice. Write a structured analysis: what specific benefits does extraction provide at 10K/day, what costs does it impose, and at what scale threshold does the trade-off flip? Reference the Shopify pod architecture and Packwerk approach as alternatives to full extraction.

---

## Key Terms

| Term | What People Think | What It Actually Means |
|------|-------------------|------------------------|
| Modular Monolith | Just a big messy application with no structure | A single deployable unit whose internal components are organized into modules with enforced API boundaries — combines deployment simplicity with organizational clarity |
| Pod (Shopify) | A Kubernetes pod (container group) | A self-contained unit of infrastructure (app servers + database shards + cache + queue) assigned to a cohort of shops to limit blast radius |
| Liquid | A general-purpose templating language | A sandboxed, intentionally limited templating DSL designed to run safely in multi-tenant merchant-controlled contexts — no I/O, no escape |
| Packwerk | A code formatter or linter | A static analysis tool that enforces package-level privacy and dependency rules in Ruby/Rails monorepos at CI time |
| Shop Scope | A Rails `default_scope` | The architectural requirement that every database query includes `shop_id` in its WHERE clause, enforced both by convention and, in some paths, by Packwerk |
| Hydrogen | Shopify's React library | An opinionated React metaframework for building headless storefronts against Shopify's Storefront API, designed to run on Oxygen (Cloudflare Workers) |
| Oxygen | A cloud hosting product | Shopify's edge hosting platform for Hydrogen storefronts, built on Cloudflare Workers — provides low-latency SSR globally without merchants managing infrastructure |

---

## Further Reading

- **Shopify Engineering Blog** — primary source for architectural decisions directly from the team: https://shopify.engineering
- **Packwerk GitHub Repository** — source, documentation, and examples for Rails module enforcement: https://github.com/Shopify/packwerk
- **"Deconstructing the Monolith" (Shopify Engineering)** — the original post explaining why Shopify moved toward a modular monolith rather than microservices: https://shopify.engineering/deconstructing-monolith-designing-software-maximizes-developer-productivity
- **Vitess Documentation** — MySQL sharding layer used by Shopify and others for horizontal scaling: https://vitess.io/docs
- **Hydrogen Documentation** — official docs for the React-based headless storefront framework: https://shopify.dev/docs/storefronts/headless/hydrogen
