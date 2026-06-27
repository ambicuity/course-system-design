# The Evolution of Scaling at Netflix

> Scale is not a feature — it is a sequence of hard decisions made under pressure, each one invalidating the last.

**Type:** Learn
**Prerequisites:** Monolith vs. Microservices, API Gateways, CAP Theorem
**Time:** ~35 minutes

---

## The Problem

Netflix started in 1998 as a DVD-by-mail service. When it launched streaming in 2007 it was a curiosity — a few thousand concurrent streams served from a single data center in Virginia running a monolithic Java application backed by Oracle. Within 18 months, streaming eclipsed DVD in usage. By 2012, Netflix accounted for more than 33% of North American internet traffic during peak evening hours.

The gap between those two numbers — a few thousand streams and one-third of a continent's traffic — is where almost every interesting system-design lesson in the Netflix story lives. A system that works perfectly at one order of magnitude will collapse, stall, or cost ten times too much at the next. The engineers who keep the system alive across that jump cannot simply add more servers; they have to rethink what the system *is*.

The Netflix story is particularly instructive because the pressure was never only about traffic. It was also about engineering velocity. As the product expanded into new countries, new device types, and new content formats (live, downloads, interactive), the rate of change itself became a scaling problem. A monolith that takes three days to deploy is not just slow — it is a business risk. Understanding *how* Netflix separated concerns at each growth stage, and *why* each new abstraction was introduced, gives you a reusable mental model for designing any high-growth system.

---

## The Concept

### The Four Phases

Netflix's public engineering record describes a clear evolutionary arc. Each phase was triggered by a concrete failure or constraint — not by a theoretical roadmap.

```
Phase 1 (2007–2008)
  Client → NCCP (monolith) → Oracle DB
  Single data center. All functionality in one deployable.

Phase 2 (2009–2012)
  Client → NCCP (orchestration shell) → Microservices
                                       → Microservices
                                       → Microservices
  NCCP retained orchestration; features extracted into separate apps.

Phase 3 (2012–2015)
  Client → Zuul Gateway → NCCP (playback) → Microservices
                        → Domain APIs    → Microservices
  Gateway decouples clients from the service topology.

Phase 4 (2015–present)
  Client → Zuul 2 (async) → Edge Services → Domain Microservices
                                           → Cassandra / EVCache / S3
  Full AWS, containerized (Titus), resilience-first engineering.
```

### Phase 1 — The 3-Tier Monolith

The initial architecture was conventional and appropriate for the scale: a thin client tier, an API application called **NCCP (Netflix Content Control Protocol)**, and a relational database backed by Oracle.

NCCP was responsible for authentication, authorization, content licensing checks, device negotiation, stream quality selection, and DRM. Deploying a change to any of those areas meant redeploying the entire application. As the team and feature set grew, deploy risk compounded: a bug in subtitle handling could gate a payment system fix.

The triggering event for rethinking this was a **database corruption incident in August 2008**. A botched upgrade corrupted Netflix's Oracle instance and caused a three-day outage. This was the moment the leadership committed to two long-term bets: (a) move everything to AWS to buy elasticity and redundancy, and (b) decompose the monolith so that no single component could take down the entire product.

### Phase 2 — Microservices Decomposition

"Microservices" in this phase did not mean dozens of tiny services immediately. It meant a deliberate extraction strategy: pull one bounded context out of NCCP, give it its own deployment pipeline, its own data store, and let NCCP call it over an internal HTTP API.

The extraction order followed risk and rate of change. Services that changed frequently (recommendation engine, UI personalization) were extracted first so teams could deploy them independently. Services that were deeply coupled to DRM or licensing were left in NCCP longer because the blast radius of getting extraction wrong was too high.

NCCP became an **orchestration shell** rather than a feature monolith. It still held the request fan-out and response aggregation logic, but the actual business logic lived in downstream services. This pattern — sometimes called the *strangler fig* — let Netflix reach a mostly-microservice architecture without a hard cut-over rewrite.

**Key trade-offs introduced at this phase:**

| Concern | Monolith | Microservices |
|---|---|---|
| Deploy independence | No — everything together | Yes — per-service pipelines |
| Network failure modes | None (in-process calls) | Timeouts, partial failures, cascading outages |
| Data consistency | ACID transactions | Eventual consistency, sagas |
| Observability | Single log stream | Distributed tracing required |
| Team autonomy | Low — shared codebase | High — own repo, own schedule |

Microservices introduced network calls where there had been function calls. This forced Netflix to invest heavily in **resiliency patterns**: circuit breakers (Hystrix), bulkheads, timeouts, and retry budgets. Hystrix became the canonical open-source implementation of the circuit-breaker pattern; Netflix open-sourced it in 2013.

### Phase 3 — The Zuul API Gateway

By 2011, NCCP was talking to dozens of microservices, and so were clients directly in some cases. Two problems emerged:

1. **Client coupling**: Mobile clients hard-coded the addresses of specific services. When services split or merged, clients broke.
2. **Cross-cutting concerns**: Authentication, rate limiting, A/B test routing, and request logging were being reimplemented in every service.

**Zuul** (named after the Ghostbusters villain) was Netflix's answer: a JVM-based edge proxy that acts as the single entry point for all external traffic. Its design is filter-based — analogous to servlet filters — which means new cross-cutting behaviors can be added without touching downstream services.

```
Incoming Request
       │
  ┌────▼─────────────────────────────────────────┐
  │                   Zuul                        │
  │  [Pre-Filters] → [Route Filter] → [Post-Filters] │
  │  - Auth check   - Target service  - Logging      │
  │  - Rate limit   - Load balance    - Metrics       │
  │  - A/B routing  - Retry budget    - CORS          │
  └────────────────────────────┬─────────────────┘
                               │
               ┌───────────────┼───────────────┐
               ▼               ▼               ▼
          NCCP API        Search API      Account API
```

Zuul 1 was synchronous and thread-per-request. At Netflix's traffic levels this became a thread-count ceiling — each blocked thread waiting on a downstream response held an OS thread. In 2016, Netflix shipped **Zuul 2**, a ground-up rewrite using Netty's async I/O model, which dropped the cost per connection from an OS thread (~1 MB stack) to a few KB of event-loop state.

### Phase 4 — Resilience Engineering and the Full Cloud

By 2015, Netflix had completed its migration to AWS and had dismantled its last owned data centers. The architecture by this point had expanded to over 700 microservices. At that scale, the baseline assumption shifts: **something is always broken**. The question is whether a failure in one part propagates to the whole.

Netflix institutionalized this assumption through **Chaos Engineering** — deliberately injecting failures in production to test resilience before real failures occur. The **Chaos Monkey** (open-sourced in 2012) terminates random EC2 instances during business hours. The broader **Simian Army** included:

- **Latency Monkey** — injects artificial network latency
- **Conformity Monkey** — terminates instances not following best-practice configurations
- **Janitor Monkey** — cleans up unused resources

The data layer evolved in parallel. Oracle was replaced by purpose-fit stores:

| Data type | Store | Why |
|---|---|---|
| User viewing history | **Cassandra** | Write-heavy, wide rows, no single point of failure |
| Session / transient state | **EVCache** (Memcached) | Sub-millisecond read latency |
| Movie metadata | **MySQL** on RDS | Relational, infrequently written |
| Billing records | **MySQL** on RDS | ACID required |
| Video assets | **Amazon S3** | Durable blob storage |
| Personalization vectors | In-memory on EC2 | Latency-sensitive, recomputed hourly |

Video delivery itself was moved off third-party CDNs in 2012 when Netflix built **Open Connect**, its own globally distributed CDN. Internet service providers can co-locate Open Connect Appliances (OCAs) inside their networks; Netflix pre-positions content on OCAs so that 95%+ of traffic never traverses the public internet.

---

## Build It / In Depth

### Worked Example: Tracing a Play Request Through the Phases

**Phase 1 (monolith):**
```
Client → POST /play?title=123&device=ios
  NCCP:
    1. Validate session token (internal)
    2. Check license for title 123 (internal)
    3. Select bitrate ladder for iOS device (internal)
    4. Record play event in Oracle (JDBC)
    5. Return manifest URL
```
Everything is a function call. Failure modes: Oracle is down → total outage.

**Phase 2 (microservices, NCCP as orchestrator):**
```
Client → POST /play?title=123&device=ios
  NCCP:
    1. GET auth-service/validate → {userId: 42}      # separate service
    2. GET license-service/check?title=123            # separate service
    3. GET device-service/profile?type=ios            # separate service
    4. POST viewing-history-service/record            # separate service
    5. Return manifest URL
```
Failure modes: any downstream service can timeout independently. NCCP uses Hystrix: if license-service is slow, the circuit opens and NCCP returns a cached or degraded response instead of waiting.

**Phase 3 (with Zuul):**
```
Client → POST /play?title=123&device=ios
  Zuul pre-filters:
    - Validate JWT (no downstream call needed — verified locally)
    - Route to NCCP based on path prefix /play
    - Start request trace ID
  NCCP:
    - Fan out to downstream services (same as Phase 2)
  Zuul post-filters:
    - Attach trace ID to response headers
    - Log latency, status, user segment
```

### Zuul Filter — Minimal Example

Zuul 1 filters are Groovy classes (hot-reloadable at runtime — a significant operational capability):

```groovy
class AuthFilter extends ZuulFilter {
    @Override
    String filterType() { return "pre" }

    @Override
    int filterOrder() { return 1 }

    @Override
    boolean shouldFilter() { return true }

    @Override
    Object run() {
        RequestContext ctx = RequestContext.currentContext()
        HttpServletRequest request = ctx.getRequest()

        String token = request.getHeader("Authorization")
        if (!TokenValidator.isValid(token)) {
            ctx.setSendZuulResponse(false)
            ctx.setResponseStatusCode(401)
            ctx.setResponseBody('{"error":"Unauthorized"}')
        }
        return null
    }
}
```

The filter chain is the key insight: each concern (auth, rate limiting, routing, logging) lives in its own class and is ordered explicitly. Adding a new concern does not require modifying existing filters.

### Circuit Breaker — Hystrix Pattern

```java
@HystrixCommand(
    fallbackMethod = "getCachedLicense",
    commandProperties = {
        @HystrixProperty(name="execution.isolation.thread.timeoutInMilliseconds", value="200"),
        @HystrixProperty(name="circuitBreaker.requestVolumeThreshold", value="20"),
        @HystrixProperty(name="circuitBreaker.errorThresholdPercentage", value="50")
    }
)
public License checkLicense(long titleId) {
    return licenseServiceClient.check(titleId);  // remote call
}

public License getCachedLicense(long titleId) {
    return licenseCache.get(titleId);  // last-known-good value
}
```

If more than 50% of requests in a 10-second window fail or timeout, Hystrix opens the circuit and calls `getCachedLicense` directly for the next 5 seconds. No threads are wasted waiting on a broken downstream.

---

## Use It

### When Each Pattern Applies

| Situation | Pattern to apply | Netflix analog |
|---|---|---|
| Single team, <10 engineers, early product | Monolith | NCCP v1 (2007–2009) |
| Multiple teams, independent deploy velocity needed | Microservices decomposition | NCCP strangler (2009–2012) |
| >5 external client types (mobile, web, TV, partner) | API Gateway | Zuul (2012+) |
| Downstream services with variable latency | Circuit breaker | Hystrix |
| Write-heavy, fault-tolerant storage | Wide-column store | Cassandra |
| Sub-millisecond read latency for hot data | Distributed cache | EVCache |
| Validate system resilience continuously | Chaos engineering | Chaos Monkey / Simian Army |
| Deliver large static assets at scale | Purpose-built CDN | Open Connect |

### Cloud Provider Equivalents

Netflix's homegrown tools have direct equivalents in managed cloud services:

| Netflix tool | AWS managed equivalent | GCP equivalent |
|---|---|---|
| Zuul | API Gateway, ALB | Cloud Endpoints, Apigee |
| Eureka (service discovery) | AWS Cloud Map, ECS service discovery | Cloud DNS + NEGs |
| Hystrix (circuit breaker) | No direct managed equivalent | No direct managed equivalent |
| EVCache | ElastiCache (Memcached) | Memorystore |
| Titus (container platform) | ECS / EKS | GKE |
| Chaos Monkey | AWS Fault Injection Simulator | Chaos Mesh on GKE |

Hystrix is notable: Netflix open-sourced it in 2013, and it became the de-facto JVM circuit-breaker library. Netflix placed it in maintenance mode in 2018 (the Resilience4j library is the modern successor), but the *pattern* it encodes — circuit state machine, fallback, bulkhead — is now a first-class concept in service meshes like Istio and Linkerd.

---

## Common Pitfalls

- **Extracting microservices before you understand boundaries.** Netflix spent 2+ years with NCCP as an orchestration shell before fully committing to independent services. Teams that extract services too early — before the domain model is stable — end up with distributed monoliths: all the network overhead of microservices, none of the deployment independence. Start with a modular monolith; extract when a boundary is proven stable and the team is large enough to own a service.

- **Using an API gateway as business logic.** Zuul filters at Netflix handle auth, rate limiting, routing, and observability — not billing logic or recommendation logic. When teams start encoding product rules in gateway filters, the gateway becomes a new monolith with worse testability. Keep the gateway as the cross-cutting-concerns layer.

- **Ignoring the operational cost of distributed tracing.** Once you have 700 services, a single user request may touch 20 of them. Without distributed trace IDs propagated through every hop, debugging a latency spike is nearly impossible. Netflix built this into Zuul early. The lesson: add trace ID propagation *before* you need it, not after a production incident makes it urgent.

- **Treating circuit breakers as a magic resilience solution.** A circuit breaker prevents cascading failure, but only if the fallback is meaningful. "Return an empty list" is not always an acceptable fallback for a content library. Netflix invested in maintaining last-known-good caches (EVCache) so that fallbacks returned stale-but-real data rather than empty responses that broke the UI.

- **Skipping chaos engineering until after an outage.** Netflix ran Chaos Monkey during business hours, not in the maintenance window. The explicit goal was to ensure on-call engineers were present when failures fired. Testing resilience in a low-traffic window only confirms you can survive low traffic. If your system cannot tolerate instance loss at 8 PM, you will find out — either from Chaos Monkey or from a real failure.

---

## Exercises

1. **Easy — Phase mapping:** Draw the request path for a "search for a title" operation at each of Netflix's four phases. Label which component is responsible for authentication and rate limiting in each phase, and explain what changes and why.

2. **Medium — Strangler fig in practice:** You have a monolithic e-commerce application with six bounded contexts: catalog, cart, checkout, user accounts, recommendations, and fulfillment. Using Netflix's Phase 2 approach (keep the monolith as orchestrator, extract one service at a time), write the extraction sequence you would follow. Justify the order based on change frequency and blast radius. Describe what "done" looks like for each extraction.

3. **Hard — Circuit breaker configuration:** Netflix's Hystrix defaults (20-request volume threshold, 50% error rate, 5-second sleep window) are sensible starting points, but not universal. Consider a hypothetical service where: (a) each request takes ~500 ms, (b) traffic is 2 requests/second at baseline, and (c) the fallback involves an expensive cache miss 10% of the time. Recalculate the Hystrix parameters for this service and explain each choice. Then explain how a service mesh (Istio) would handle this differently and what you lose by delegating circuit breaking to the mesh layer.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **NCCP** | A Netflix-specific acronym with no transferable lesson | The Netflix Content Control Protocol — the original monolithic API that became the template for the strangler-fig decomposition. The orchestration-shell pattern it evolved into is directly applicable to any monolith migration. |
| **API Gateway** | A reverse proxy with authentication bolted on | A dedicated layer for cross-cutting concerns (auth, rate limiting, routing, tracing, A/B) that decouples clients from the service topology. Adding features here has zero downstream service impact. |
| **Circuit Breaker** | A retry mechanism | A state machine (closed / open / half-open) that stops sending requests to a failing downstream so that local threads aren't exhausted waiting, giving the downstream time to recover. Retries and circuit breakers are complementary, not synonymous. |
| **Chaos Engineering** | Random failure injection for testing | The discipline of proactively experimenting on a system in production to build confidence in its ability to withstand turbulent conditions — distinct from fault injection testing because it operates continuously, not in a test window. |
| **Strangler Fig** | A full rewrite done in phases | A migration pattern where new functionality is built as separate services that route around the monolith; over time the monolith is "strangled" as its surface area shrinks. Named after the fig tree that grows around and eventually replaces its host. |
| **EVCache** | Netflix's equivalent of Redis | A Memcached-based distributed cache built on top of Netflix's cloud infrastructure. It is specifically optimized for eventual consistency across regions — not a general-purpose cache, but a pattern for high-read, low-latency, multi-region access. |
| **Open Connect** | A CDN vendor Netflix uses | Netflix's own CDN: physical appliances placed inside ISP networks that serve video bytes without traversing the public internet. The shift from third-party CDN to Open Connect is what made 95%+ local delivery possible at scale. |

---

## Further Reading

- [Netflix TechBlog — Completing the Netflix Cloud Migration](https://netflixtechblog.com/completing-the-netflix-cloud-migration-783e9f8a3f0a) — First-party account of the 7-year AWS migration, with architectural context.
- [Netflix TechBlog — Zuul 2: The Netflix Journey to Asynchronous, Non-Blocking Systems](https://netflixtechblog.com/zuul-2-the-netflix-journey-to-asynchronous-non-blocking-systems-45947377acc9) — The engineering rationale for rewriting Zuul from sync to async; a clear explanation of the thread-pool vs. event-loop trade-off.
- [Netflix TechBlog — Introducing Hystrix for Resilience Engineering](https://netflixtechblog.com/introducing-hystrix-for-resilience-engineering-13531c1ab362) — The original Hystrix introduction; explains the circuit-breaker and bulkhead patterns with real Netflix failure scenarios.
- [Principles of Chaos Engineering](https://principlesofchaos.org) — The canonical definition of chaos engineering, written primarily by Netflix engineers; explains the distinction between chaos experiments and traditional fault injection.
- [Martin Fowler — Strangler Fig Application](https://martinfowler.com/bliki/StranglerFigApplication.html) — The definitive explanation of the migration pattern Netflix used to decompose NCCP, with generalizable guidance on sequencing extractions.
