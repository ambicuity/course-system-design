# The Shopify Tech Stack

> A walkthrough of how Shopify serves 600,000+ merchants at 80,000 requests/second — the languages, infrastructure, and architecture choices behind one of the largest commerce platforms in the world.

**Type:** Reference
**Prerequisites:** Basic web architecture
**Time:** ~15 minutes

---

## The Problem

Shopify is one of the largest commerce platforms in the world. It powers more than 600,000 merchants, serves 80,000 requests per second at peak, and must stay up through the busiest retail moments of the year (Black Friday, Cyber Monday). The technical choices behind that scale are a useful reference for any e-commerce or high-traffic platform.

This lesson walks through Shopify's tech stack — the languages, frameworks, databases, and infrastructure they use. The exact stack evolves, but the underlying patterns are durable lessons in building for scale.

---

## The Concept

### The stack at a glance

```
   Languages & UI     Backend & Servers         Data
   ──────────────     ─────────────────         ────
   Ruby              Ruby on Rails              MySQL
   TypeScript         Nginx                      Redis
   Lua               OpenResty                  Memcached
   React             GraphQL

   DevOps
   ──────
   GitHub
   Docker
   Kubernetes
   GKE
   BuildKite
   ShipIt (open-sourced)
```

Each category is justified by the workload it serves. We walk through each.

---

### Languages & UI

**Ruby** is Shopify's primary backend language. Ruby on Rails has been the foundation of the platform since its founding.

- Rails provides rapid development and a clear structure for monolithic applications
- Ruby is highly productive for CRUD-heavy e-commerce workflows (orders, products, customers)
- Mature ecosystem of gems (Ruby libraries) for payments, shipping, taxation, etc.

**TypeScript** is used for the modern front-end and tooling.

- Strong typing reduces runtime errors
- Plays well with React and the JavaScript ecosystem
- Increasingly used for backend services too

**Lua** powers Shopify's edge layer and high-traffic endpoints.

- Lua scripts run inside Nginx via OpenResty (an enhanced Nginx with Lua scripting)
- Used for request routing, A/B testing, rate limiting at the edge — operations that benefit from being close to the user and avoiding a backend round-trip

**React** powers the merchant admin interface (Shopify admin) and storefront components.

- Component model fits the complex UI of an e-commerce dashboard
- Server-side rendering for SEO on storefronts
- Hydration for interactive features

---

### Backend & Servers

**Ruby on Rails** is the monolith that powers most of Shopify's core.

- **Why a monolith:** for an application with tightly coupled domains (orders, products, customers, payments, fulfillment), the overhead of distributed services outweighs the benefits. A Rails monolith keeps the development velocity high.
- **Modular monolith structure:** internally organized into bounded contexts with clear interfaces, allowing future extraction if needed.

**Nginx** serves as the front-door web server, handling TLS termination and routing.

**OpenResty** extends Nginx with Lua scripting, enabling complex logic at the edge without round-trips to the application.

- Used for: routing decisions, A/B test assignment, geolocation-based content, rate limiting
- Latency savings: 10–50 ms per request compared to doing the same in Rails

**GraphQL** powers the storefront API and the admin GraphQL API.

- Lets clients (storefronts, mobile apps) request exactly the data they need
- One round trip instead of multiple REST calls
- Shopify has invested heavily in GraphQL performance at scale

---

### Data Layer

**MySQL** is the primary transactional database.

- Mature, well-understood, supports the operations Shopify needs
- Extensive use of read replicas for scaling reads
- Sharding by shop_id (merchant) for horizontal scaling

**Redis** is the primary in-memory cache and ephemeral store.

- Session storage
- Page rendering cache
- Rate limit counters
- Pub/sub for some real-time features

**Memcached** is used for object caching.

- Cached rendered page fragments
- Cached query results
- Simpler than Redis for pure caching; faster for some workloads

---

### DevOps

**GitHub** for source control. Shopify is a major open-source contributor; much of their tooling is on GitHub.

**Docker** for containerization. Standard image format for all services.

**Kubernetes** as the orchestration platform. Production workloads run on Kubernetes for auto-scaling, self-healing, and consistent deployment.

**GKE (Google Kubernetes Engine)** as the managed Kubernetes service. Run on GCP.

**BuildKite** for CI/CD. Runs the test suite and builds images.

**ShipIt** — Shopify's deployment tool, now open source.

- Coordinates deployments across the fleet
- Handles canary rollouts
- Provides quick rollback on failure
- Designed for Rails monolith deploys (the unique challenge of shipping a large monolith safely)

---

## Build It / In Depth

### The modular monolith

Shopify's Rails application is a **modular monolith** — a single deployable unit with clear internal module boundaries. Each module owns its data, exposes a public interface, and is tested independently.

```
   Shopify Rails Monolith
   ├── Shop module           (merchant accounts, settings)
   ├── Product module        (catalog, variants, inventory)
   ├── Order module          (carts, checkouts, orders)
   ├── Customer module       (customer accounts, addresses)
   ├── Payment module        (transactions, gateway integrations)
   ├── Fulfillment module    (shipping, inventory sync)
   ├── Theme module          (storefront rendering)
   ├── App module            (embedded apps for merchants)
   └── ...
```

Each module has:
- Its own controllers, models, services
- Its own database tables (with foreign keys to other modules via IDs, not direct joins)
- Its own tests
- A clear public interface for other modules

This structure lets Shopify's large engineering team (1,000+ engineers) work on the same codebase without stepping on each other. It also makes future extraction to microservices possible when warranted.

---

### The edge layer

A modern Shopify request flows through multiple layers:

```
   User request
       │
       ▼
   [Cloudflare] CDN + DDoS protection
       │
       ▼
   [OpenResty] edge layer
       │  - Auth check
       │  - A/B test assignment
       │  - Cache lookup
       │  - Rate limiting
       │  - Geolocation
       │
       ▼ (cache miss or needs app logic)
   [Rails monolith]
       │  - Routes to the appropriate module
       │  - Queries MySQL (with read replicas)
       │  - Reads from Redis cache
       │  - Publishes events to Kafka for async processing
       │
       ▼
   Response
```

The OpenResty edge layer handles a significant portion of traffic without ever reaching the Rails application. This is critical for handling peak events like flash sales or Black Friday.

---

### How Shopify handles peak load

During peak events, traffic can spike 10× normal:

1. **Aggressive caching at the edge.** Most storefront pages are served from CDN or OpenResty cache.
2. **Read replicas for MySQL.** Heavy read traffic (browsing, search) goes to replicas; writes go to the primary.
3. **Queue-based async processing.** Non-critical work (analytics, notifications) goes to queues and is processed asynchronously.
4. **Graceful degradation.** Under load, Shopify deprioritizes non-essential features (recommendations, related products) to keep checkout fast.
5. **Pre-provisioned capacity.** Shopify runs at 60–70% capacity normally so peak spikes fit within headroom.

---

### Why Rails survived

A common question: why does Shopify still use Rails in 2025? Many would argue for rewriting in Go, Rust, or Elixir. Shopify's answer is that **Rails' developer productivity wins** outweigh the theoretical performance gains of a lower-level language.

- **Rails conventions** reduce decision-making overhead
- **The team knows Rails deeply** — they have built their own performance expertise (the Ruby garbage collector tuning, the MySQL query optimizations)
- **Refactoring a monolith** is easier than rewriting from scratch
- **Most performance problems are database or architecture problems**, not language problems

This is the modular-monolith argument in production: keep the monolith until you have a concrete reason to break it apart.

---

### What changed over time

Shopify's stack has evolved significantly:

```
   2010s: Monolithic Rails, MySQL, Memcached, Nginx
   2015+:  GraphQL API added for storefronts
   2018+:  OpenResty/Lua for edge logic
   2020+:  Kubernetes for new services; monolith stays on VMs
   2022+:  ShipIt open-sourced; more TypeScript/React
   2025:   Hybrid — Rails monolith + Kubernetes for new features
```

The monolith remains the core. New features (mobile, AI, real-time) often start as separate services in Kubernetes and may be merged into the monolith if they become core.

---

## Use It

### Lessons from Shopify's stack

| Lesson | Why it matters |
|---|---|
| **Modular monolith first** | Most teams should resist premature microservices; clear internal modules buy most of the benefit |
| **Edge layer for hot paths** | OpenResty/Lua at the edge can absorb significant traffic before reaching the app |
| **Read replicas are mandatory** | Read-heavy workloads (browsing, search) need read scaling separate from writes |
| **Queue for async work** | Anything that does not need to be synchronous should be queued |
| **Graceful degradation under load** | Plan for peak load; deprioritize non-critical features rather than failing |
| **Invest in deployment tooling** | ShipIt, BuildKite, Kubernetes — the deployment story is as important as the application |
| **Match stack to team** | Shopify chose Rails because the team knew Rails; your stack should match your team's strengths |

### When to use a Shopify-like architecture

| Situation | Verdict |
|---|---|
| Single application, complex domain | Modular monolith (Shopify's choice) |
| High traffic e-commerce / SaaS | Aggressive edge caching + read replicas |
| Multi-tenant SaaS | Shard by tenant ID |
| Need real-time updates | GraphQL subscriptions or WebSocket |
| Heavy write throughput | Queue async work; only synchronous what must be |

### When NOT to copy Shopify's stack

| Situation | Different choice |
|---|---|
| Tiny team (1–10 engineers) | Simpler stack — managed services, no Kubernetes |
| Pure serverless application | AWS Lambda or Cloud Functions; not Rails monolith |
| ML-heavy product | Python + GPU; not Ruby |
| Globally distributed with strong data residency | Multi-cloud or multi-region; not single GCP |
| Real-time streaming at very high scale | Kafka + Flink first; not GraphQL |

---

## Common Pitfalls

- **Assuming monoliths cannot scale.** Shopify's monolith serves 80k req/s. The bottleneck is rarely the language or framework.

- **Skipping the edge layer.** A smart edge layer (CDN + OpenResty + caching) absorbs a huge fraction of traffic before it ever reaches the application.

- **Premature microservices extraction.** Most teams break their monolith into services before they have the operational maturity to manage the complexity. Modular monolith first.

- **Treating the deployment as an afterthought.** Shopify's investment in ShipIt paid off in the ability to ship daily to a massive codebase. Deployment is part of the stack.

- **Choosing a stack that does not match the team's skills.** The best stack is the one your team can operate. Shopify chose Rails because they knew Rails.

- **Ignoring observability until something breaks.** Shopify's edge layer, Rails app, and database all generate metrics and traces. Without them, debugging at scale is impossible.

---

## Exercises

1. **Easy** — Pick three technologies from Shopify's stack. For each, describe its role in one sentence and the alternative it replaced.

2. **Medium** — A startup is building an e-commerce platform. Design the stack for the first 100 merchants. Justify each technology choice and the migration path to 100,000 merchants.

3. **Hard** — Shopify handles peak events by aggressive caching, read replicas, and graceful degradation. Design the equivalent system for a different domain (real-time multiplayer gaming, video streaming, financial trading). Specify the layers and the trade-offs you accept.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Modular monolith | An oxymoron | A single deployable unit with clear internal module boundaries; combines the simplicity of a monolith with the structure of microservices |
| OpenResty | A web server | An enhanced Nginx with embedded Lua scripting; used for edge logic that would be too slow in the application |
| Edge layer | The CDN | The layer between the user and the application that handles cross-cutting concerns (auth, caching, routing) before the request reaches the app |
| GraphQL gateway | An API | An API layer that lets clients request exactly the data they need in a single round trip |
| Read replica | A copy | A copy of the primary database that serves reads; scales read throughput independently of writes |
| Graceful degradation | Falling back | Continuing to serve users with reduced functionality when load is high; better than failing outright |
| ShipIt | A deploy tool | Shopify's open-source deployment tool for coordinating safe rollouts of large monoliths |
| Bounded context | A domain term | A domain-driven design concept — a boundary within which a particular model is consistent; Shopify's modules map to bounded contexts |

---

## Further Reading

- **"Shopify Engineering" blog** — official deep dives on architecture decisions: https://shopify.engineering/
- **"Deconstructing the Monolith"** — Shopify's design week talk on modular monoliths: https://shopify.engineering/deconstructing-monolith-designing-data-maximalist-apps-1f9af7ed5748
- **Shopify's Open Source on GitHub** — including ShipIt: https://github.com/Shopify
- **"The Pragmatic Programmer"** — the philosophy behind Shopify's pragmatic stack choices: https://pragprog.com/titles/tpp20/the-pragmatic-programmer-20th-anniversary-edition/
- **OpenResty Documentation** — the edge server Shopify uses: https://openresty.org/en/