# Load Balancers vs API Gateways vs Reverse Proxy! And how can they Work Together?

> They all "sit in front of your servers" — but each one solves a fundamentally different problem, and confusing them leads to over-engineered or dangerously under-secured systems.

**Type:** Learn
**Prerequisites:** REST API Design, Microservices Basics, HTTP Fundamentals
**Time:** ~25 minutes

---

## The Problem

You're scaling a ride-sharing backend from one monolith to a dozen microservices. The first obvious step is "put something in front of all these servers." But what? Your infrastructure team says "add a load balancer." Your security team says "you need an API gateway." Your DevOps engineer says "just use nginx as a reverse proxy." Everyone is technically correct — and that's exactly the problem.

Without a clear mental model, you end up with one of two failure modes. Either you bolt every feature onto a single piece of infrastructure (your nginx config becomes a 2,000-line monster handling auth, routing, rate limiting, and SSL), or you deploy all three layers without understanding which responsibility belongs where — adding latency, operational complexity, and cost for zero benefit.

The real question isn't which one to use. It's understanding what each abstraction *is*, what it's optimized for, and how they compose into a production-grade request pipeline.

---

## The Concept

### The Foundational Abstraction: Reverse Proxy

Every piece of infrastructure in this lesson is, at its core, a **reverse proxy**. That term is worth pinning down precisely.

A **forward proxy** sits on the client side. Your corporate firewall that intercepts your outbound requests is a forward proxy — clients know about it, servers don't.

A **reverse proxy** sits on the server side. Clients send requests to it thinking they're reaching the real server. The reverse proxy forwards those requests upstream, gets the response, and sends it back. Clients never see your actual backend addresses.

```
Client ──► Reverse Proxy ──► Backend Server(s)
           (public IP)       (private IPs)
```

A reverse proxy buys you: backend anonymity, SSL termination at one place, response caching, connection pooling, and a single ingress point you can secure and monitor. Every other component in this lesson extends this baseline.

---

### Load Balancer: Traffic Distribution at Scale

A load balancer is a reverse proxy whose *primary* job is to distribute requests across a pool of identical backend instances to avoid overwhelming any single one.

**Layer 4 vs Layer 7 load balancers are architecturally different:**

| Dimension | L4 (Transport Layer) | L7 (Application Layer) |
|---|---|---|
| Sees | TCP/UDP packets | Full HTTP request (headers, URL, body) |
| Routing basis | IP address + port | Path, host, cookie, header, method |
| Speed | Extremely fast, minimal processing | Slower (must parse HTTP), far smarter |
| TLS termination | Pass-through or terminate | Yes — required to inspect HTTP |
| Use case | Raw throughput, non-HTTP protocols | HTTP microservices, A/B routing |
| Examples | AWS NLB, HAProxy (mode tcp) | AWS ALB, nginx upstream, HAProxy (mode http) |

**Common distribution algorithms:**

- **Round robin** — requests rotate sequentially across instances. Simple, assumes equal instance capacity.
- **Least connections** — new request goes to whichever instance currently has fewest active connections. Better for variable request durations (e.g., file uploads).
- **IP hash** — client IP deterministically maps to one backend. Provides sticky sessions without cookies. Breaks if backend count changes.
- **Weighted round robin** — assigns proportional traffic to instances with different capacities (e.g., a beefy instance gets 3× the traffic of a smaller one).
- **Least response time** — combines least connections with latency measurement. Most adaptive, highest bookkeeping cost.

A load balancer also performs **health checks** — polling backends on a configured interval and removing unhealthy instances from the pool without operator intervention.

---

### API Gateway: Policy Enforcement at the Edge

An API gateway is a reverse proxy that adds a rich suite of **cross-cutting concerns** for API traffic. Where a load balancer asks "which backend should handle this request?", an API gateway first asks "should this request be handled at all, and in what shape?"

Responsibilities that belong to an API gateway:

```
Incoming Request
      │
      ▼
┌─────────────────────────────────┐
│         API Gateway             │
│                                 │
│  1. Parameter validation        │ ← Is the request well-formed?
│  2. IP allowlist / denylist     │ ← Is the source trusted?
│  3. Authentication              │ ← Who are you? (JWT, API key, OAuth)
│  4. Authorization               │ ← Are you allowed to do this?
│  5. Rate limiting               │ ← Are you calling too frequently?
│  6. Request transformation      │ ← Header injection, body rewrite
│  7. Response transformation     │ ← Strip sensitive fields, aggregate
│  8. Logging / Tracing           │ ← Correlation IDs, audit trail
│  9. Routing / Load Balancing    │ ← Which upstream service?
│                                 │
└─────────────────────────────────┘
      │
      ▼
  Upstream Services
```

Notice that an API gateway *includes* a load balancer at step 9. It also typically acts as a reverse proxy throughout. The difference isn't capability — it's *purpose and optimization*. An API gateway is built and configured around API semantics (HTTP, REST, gRPC, WebSocket), whereas a load balancer is built around raw connection distribution.

---

### Relationship Summary

```
Reverse Proxy
└── Load Balancer        (specializes in: traffic distribution)
└── API Gateway          (specializes in: policy enforcement + routing)
    └── often contains a built-in Load Balancer for upstream pools
```

A **pure reverse proxy** (like a basic nginx setup) gives you none of these features out of the box — you add what you need.

A **load balancer** gives you distribution + health checks. That's it. No auth, no rate limiting, no request inspection beyond what's needed to route.

An **API gateway** gives you everything — but at a higher latency cost per hop and more operational surface area.

---

## Build It / In Depth

### Production Request Pipeline: End to End

Here's the canonical pattern used in production microservices architectures, from the seed material made precise:

```
Internet
   │
   ▼
┌──────────────────────────────────────┐
│     Edge Load Balancer (L7/L4)       │  ← Single public IP, DDoS protection,
│     e.g. AWS ALB, Cloudflare         │    TLS termination, anycast routing
└──────────────────────────────────────┘
   │
   │  (distributes to API Gateway cluster)
   ▼
┌──────────────────────────────────────┐
│     API Gateway Cluster              │  ← Auth, rate limiting, routing
│     e.g. Kong, AWS API Gateway       │    Parameter validation, logging
│     Apigee, Nginx + Lua              │
└──────────────────────────────────────┘
   │
   │  (routes to correct microservice)
   │
   ├──► /users/*  ──►  ┌──────────────────────┐
   │                    │  Internal LB         │ ← Distributes across
   │                    │  (Users Service x3)  │   service instances
   │                    └──────────────────────┘
   │
   ├──► /orders/* ──►  ┌──────────────────────┐
   │                    │  Internal LB         │
   │                    │  (Orders Service x5) │
   │                    └──────────────────────┘
   │
   └──► /payments/* ►  ┌──────────────────────┐
                        │  Internal LB         │
                        │  (Payments Service)  │
                        └──────────────────────┘
```

**Step-by-step request trace:**

1. **Client → Edge Load Balancer**: The client connects to a single public IP. The LB terminates TLS, checks basic health, and distributes load across the API gateway cluster (so the gateway itself isn't a single point of failure).

2. **Edge LB → API Gateway**: The API gateway receives a plain HTTP/2 request on the internal network. It performs (in order):
   - Schema validation: required fields present? correct types?
   - IP allowlist: is the source IP in a known-good range, or on a blocklist?
   - Authentication: validate JWT signature, check expiry, decode claims.
   - Authorization: does this identity's role permit access to this endpoint?
   - Rate limiting: has this client ID exceeded N requests/second? If yes, return `429 Too Many Requests`.
   - Request transformation: inject `X-User-Id` header so downstream services don't need to re-parse the JWT.

3. **API Gateway → Internal Load Balancer**: The gateway routes `/orders/123` to the Orders service pool. The internal LB selects a healthy instance using least-connections.

4. **Service → Response**: The Orders service processes the request, the response flows back through the same chain. The API gateway may strip internal headers (`X-Internal-Trace-Id`) before returning to the client.

---

### Concrete nginx Config: Reverse Proxy + Upstream Pool

```nginx
# /etc/nginx/nginx.conf

upstream orders_service {
    least_conn;                       # load balancing algorithm
    server 10.0.1.10:8080 weight=3;  # heavier instance gets 3x traffic
    server 10.0.1.11:8080 weight=1;
    server 10.0.1.12:8080 weight=1;
    keepalive 32;                     # persistent upstream connections
}

server {
    listen 443 ssl http2;
    server_name api.example.com;

    # TLS termination (reverse proxy concern)
    ssl_certificate     /etc/ssl/certs/example.crt;
    ssl_certificate_key /etc/ssl/private/example.key;

    location /orders/ {
        # Basic reverse proxy headers
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_pass http://orders_service;
        proxy_connect_timeout 2s;
        proxy_read_timeout    30s;
    }
}
```

This nginx config acts as a **reverse proxy** (hiding backends) and a **load balancer** (upstream block with `least_conn`). It does not do auth or rate limiting — that's a gateway's job.

---

### Rate Limiting in a Gateway: Token Bucket (Conceptual)

```
Client sends request
        │
        ▼
   [ Token Bucket ]
   capacity = 100 tokens
   refill rate = 10 tokens/sec
        │
   Has token? ──YES──► consume token ──► forward to upstream
        │
       NO
        │
        ▼
   Return 429 Too Many Requests
   Retry-After: 1s
```

The API gateway maintains this state per `(client_id, endpoint)` pair, typically in Redis for a horizontally-scaled gateway cluster. The edge load balancer cannot do this because it doesn't parse the JWT to extract `client_id`.

---

## Use It

### When to Use Which

| Situation | What to reach for | Why |
|---|---|---|
| Scale a single service to multiple instances | Load balancer only | No auth needed; pure distribution |
| Expose internal microservices to the internet | API Gateway | Auth, rate limiting, routing in one place |
| Hide backend IPs, terminate SSL | Reverse proxy (nginx/caddy) | Lightweight, fast, well-understood |
| Different rate limits per customer tier | API Gateway | LBs have no concept of identity |
| Route `/v1` to old service, `/v2` to new | API Gateway (L7 routing) | Path-based routing with transformation |
| WebSocket or raw TCP load balancing | L4 Load Balancer | L7 gateways have limited raw TCP support |
| Internal service-to-service traffic | Internal LB (service mesh sidecar) | No need for an API gateway inside the cluster |

### Technology Reference

| Tool | Primary Role | Notable Strength |
|---|---|---|
| **nginx** | Reverse proxy / L7 LB | Battle-tested, minimal overhead, huge ecosystem |
| **HAProxy** | L4 + L7 LB | Highest raw throughput, detailed stats |
| **Kong** | API Gateway (nginx-based) | Plugin ecosystem (auth, rate limit, logging) |
| **AWS ALB** | L7 Load Balancer | Deep AWS integration, weighted target groups |
| **AWS NLB** | L4 Load Balancer | Ultra-low latency, static IP, TCP/UDP |
| **AWS API Gateway** | API Gateway | Serverless, zero ops, pay-per-request |
| **Apigee** | API Gateway | Enterprise analytics, developer portal |
| **Envoy** | Reverse proxy / LB | Service mesh foundation (Istio, Linkerd) |
| **Caddy** | Reverse proxy | Automatic HTTPS, simple config |
| **Cloudflare** | Edge LB + WAF | Global anycast, DDoS protection at scale |

---

## Common Pitfalls

- **Putting auth logic in the load balancer.** Load balancers (especially L4) have no knowledge of JWT tokens, API keys, or OAuth flows. Auth belongs in the API gateway. If you attempt to do it at the LB layer you'll be writing custom Lua/modules and fighting the tool.

- **Single API gateway with no horizontal scaling.** An API gateway is itself a stateless service (rate limit state lives in Redis, not the gateway process). Deploy it as a cluster behind an edge load balancer. A single gateway instance becomes your most critical single point of failure.

- **Skipping the internal load balancer.** Teams often put an API gateway in front but forget to load balance *within* each microservice pool. The gateway routes `/orders/*` to `orders-service`, but if that's a single IP it's back to a SPOF. Every service pool needs its own internal LB.

- **Using IP hash for load balancing when instances auto-scale.** IP hash maps client IP → backend deterministically. When you add or remove instances (during autoscaling), many clients remap to a different backend and lose session state. Use least-connections instead, and handle session state externally (Redis, DB).

- **Letting the API gateway become a business logic layer.** It's tempting to add data transformations, business rules, and fan-out calls in gateway plugins. Resist. The gateway should enforce *policy*, not implement *logic*. Business logic in the gateway couples all your services to a single piece of infrastructure and makes it untestable.

---

## Exercises

1. **Easy** — Draw the request pipeline for a simple SaaS app (one frontend, three microservices: users, billing, content). Label which component is a reverse proxy, which is a load balancer, and which is an API gateway. Identify where TLS terminates and where auth is enforced.

2. **Medium** — You have an API gateway enforcing a rate limit of 100 req/min per user. The gateway is horizontally scaled to 5 instances. Explain why a local in-process counter (per gateway instance) gives incorrect limits. Design a Redis-based solution that gives correct global limits, and sketch what happens to rate limiting if Redis becomes temporarily unavailable (fail-open vs fail-closed tradeoffs).

3. **Hard** — A fintech company runs: Cloudflare (edge), AWS ALB (L7 LB), Kong (API gateway), and 8 microservices each with an internal ALB. Latency from the gateway to a service is 3ms, and the entire request pipeline takes 45ms. Profile where the latency budget is likely spent, identify which layers could be collapsed without sacrificing security or scalability, and write the tradeoffs of each collapse decision.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Reverse Proxy** | A fancy name for nginx | A server that accepts requests on behalf of backends and forwards them upstream; backends remain anonymous to clients |
| **Load Balancer** | Something that "handles traffic" | A reverse proxy specialized in distributing connections across a pool of backends, with health checking and a distribution algorithm |
| **API Gateway** | A load balancer with auth | An application-layer reverse proxy that enforces cross-cutting API policies (auth, rate limiting, routing, transformation) before proxying upstream |
| **L4 Load Balancing** | Old-fashioned / deprecated | Transport-layer balancing (TCP/UDP) — extremely fast, used when you can't or don't need to inspect HTTP (e.g., database proxies, game servers) |
| **L7 Load Balancing** | Same as L4 but slower | Application-layer balancing (HTTP) — content-aware routing based on URL, headers, cookies; required for most microservices |
| **Rate Limiting** | Block bad actors | Constrain *how many requests* a client can make per time window, regardless of intent; protects backend capacity from any client including legitimate ones |
| **SSL Termination** | Decrypting traffic (bad?) | Ending the TLS connection at the proxy layer, forwarding plain HTTP internally; concentrates certificate management and enables HTTP-level inspection |

---

## Further Reading

- [nginx Load Balancing Documentation](https://nginx.org/en/docs/http/load_balancing.html) — Official reference for upstream blocks, algorithms, and health checks.
- [AWS: Choosing between ALB, NLB, and CLB](https://docs.aws.amazon.com/elasticloadbalancing/latest/userguide/how-elastic-load-balancing-works.html) — Authoritative breakdown of when L4 vs L7 matters on AWS.
- [Kong Gateway — Core Concepts](https://docs.konghq.com/gateway/latest/introduction/) — How Kong layers plugins on top of nginx to implement API gateway patterns.
- [Envoy Proxy Architecture Overview](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/intro/overview) — Deep dive into how Envoy implements L7 proxying, service discovery, and observability; foundational for understanding service meshes.
