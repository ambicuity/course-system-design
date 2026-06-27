# The 5 Pillars of API Design

> A well-designed API is a contract — and contracts that break destroy trust faster than bad code ever could.

**Type:** Learn
**Prerequisites:** REST API Basics, HTTP Fundamentals, Client-Server Architecture
**Time:** ~35 minutes

---

## The Problem

You ship a new endpoint at `/api/users`. Three months later, a mobile client is down because you renamed `user_id` to `id` in the response. A partner integration breaks because the rate of requests they send overwhelms your database. Another team can't figure out which version of the API they should be calling. None of this happened because someone wrote bad code — it happened because no one applied principled API design.

APIs are contracts between producers and consumers. Unlike internal code, you cannot refactor an API quietly; every change propagates to every client simultaneously. A poorly designed interface forces clients to work around your assumptions. A missing versioning strategy means you can never safely evolve. No rate limiting means a single misbehaving consumer can take down service for everyone.

The five pillars of API design give you a framework to avoid all of this up front. They don't prescribe one paradigm or one technology — they are the *questions* you must answer for every API surface you expose.

---

## The Concept

The five pillars are: **Interface**, **Paradigm**, **Relationships**, **Versioning**, and **Rate Limiting**. Together they define what your API exposes, how it speaks, how entities relate, how it changes safely over time, and how it defends itself.

### Pillar 1 — The Interface

The interface is the contract itself: what inputs the API accepts and what outputs it returns. Good interface design means:

- **Naming is consistent and domain-driven.** Use nouns for resources (`/orders`, `/invoices`), not verbs (`/getOrders`, `/createInvoice`). HTTP verbs carry the action.
- **HTTP semantics are respected.** `GET` is safe and idempotent. `PUT` is idempotent. `POST` is neither. Violating these guarantees confuses clients and breaks caching.
- **Status codes carry meaning.** `200 OK` for success, `201 Created` after a `POST`, `400 Bad Request` for client errors, `404 Not Found`, `409 Conflict`, `429 Too Many Requests`, `500 Internal Server Error`. Never return `200` with an error body.
- **Payloads are predictable.** Every response has the same envelope shape: a status flag, a data object, and an optional error message.

```json
// Consistent response envelope
{
  "success": true,
  "data": { "id": "u_123", "email": "alice@example.com" },
  "error": null
}
```

### Pillar 2 — API Paradigms

Different problems require different communication styles. The three dominant paradigms are REST, GraphQL, and gRPC.

```
┌─────────────────────────────────────────────────────────────┐
│                    Paradigm Trade-offs                      │
├──────────────┬───────────────────┬───────────────────────── ┤
│  Dimension   │      REST         │   GraphQL   │   gRPC     │
├──────────────┼───────────────────┼─────────────┼────────────┤
│  Transport   │ HTTP/1.1+         │ HTTP/1.1+   │ HTTP/2     │
│  Data format │ JSON (usually)    │ JSON        │ Protobuf   │
│  Fetching    │ Fixed endpoints   │ Flexible    │ Fixed RPCs │
│  Streaming   │ SSE/WebSocket     │ Subscript.  │ Native     │
│  Type safety │ Optional (OpenAPI)│ Schema      │ Proto IDL  │
│  Best for    │ Public APIs       │ Data-heavy  │ Microsvcs  │
│              │ CRUD resources    │ mobile BFFs │ internal   │
└──────────────┴───────────────────┴─────────────┴────────────┘
```

**REST** is the default choice for public-facing APIs. It maps well to HTTP, is easy to cache, and tooling (OpenAPI/Swagger) is mature.

**GraphQL** shines when clients need to fetch deeply nested or highly variable data shapes — think a mobile app that needs user + orders + product details in one round trip.

**gRPC** is the right choice for internal service-to-service communication where performance matters. Binary Protobuf payloads are 3–10× smaller than equivalent JSON, and HTTP/2 multiplexing eliminates head-of-line blocking.

### Pillar 3 — Relationships

Real domains have relationships: a `User` has many `Orders`, an `Order` has many `LineItems`. The API must expose these relationships in a way that feels natural and avoids unnecessary round trips.

Two patterns dominate:

**Nested routes** — encode ownership directly in the URL:
```
GET /users/{userId}/orders
GET /users/{userId}/orders/{orderId}
```
Use this when the child resource only makes sense in the context of the parent (a comment belongs to a post).

**Flat routes with filters** — keep resources at the top level, use query parameters for filtering:
```
GET /orders?userId={userId}
GET /orders/{orderId}
```
Use this when the child resource has independent identity and is accessed in multiple contexts (an order can be fetched by admin, by the user, and by a logistics system).

A common mistake is nesting more than two levels deep. `/users/{id}/orders/{orderId}/lineitems/{itemId}` is hard to read, hard to route, and couples your URL structure to your data model. Flatten at two levels.

### Pillar 4 — Versioning

APIs evolve. Versioning is how you evolve them without breaking existing consumers.

The three main strategies:

| Strategy | Example | Visibility | Ease of Routing |
|---|---|---|---|
| URL path | `/v1/users`, `/v2/users` | High — obvious in logs | Easy — any proxy/gateway |
| Query param | `/users?version=2` | Medium | Medium |
| Request header | `Accept: application/vnd.api+json;version=2` | Low — hidden | Hard — requires header inspection |

**URL path versioning** is the most practical for public APIs. It is instantly visible in logs, easy to route at the gateway layer, and easy to document. The cost is that URLs are slightly less "pretty."

Regardless of strategy, follow this deprecation contract:
1. Announce the new version alongside the old one.
2. Set a sunset date (e.g., 6–12 months).
3. Return a `Deprecation` response header on old endpoints.
4. Remove the old version only after the sunset date passes.

### Pillar 5 — Rate Limiting

Rate limiting protects the API from abuse and from inadvertent overload. Without it, a single client can saturate your database, exhaust connection pools, or cause cascading failures downstream.

The four common algorithms:

```
Fixed Window     Sliding Window    Token Bucket       Leaky Bucket
──────────────   ───────────────   ──────────────     ────────────
[  100 req  ]   Rolling 60s       Tokens refill      Queue drains
[ per minute]   window, smoother  continuously       at fixed rate
Burst at edges  No burst spikes   Allows bursts      Smooths bursts
Simple          More memory       Most common        Strict output
```

**Token bucket** is the most widely used. Each consumer gets a bucket of tokens; each request consumes one token; tokens refill at a fixed rate. Allows controlled bursts while enforcing a sustained limit.

Rate limit responses must be informative:
```http
HTTP/1.1 429 Too Many Requests
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1719432000
Retry-After: 60
```

Rate limits should be applied per dimension: per API key, per user, per IP, and optionally per endpoint (write endpoints typically get stricter limits than read endpoints).

---

## Build It / In Depth

Walk through designing the API surface for a simple e-commerce order service.

**Step 1 — Define the Interface**

```
POST   /v1/orders             → 201 Created, returns order object
GET    /v1/orders/{id}        → 200 OK, returns order object
GET    /v1/orders/{id}/items  → 200 OK, returns list of line items
PATCH  /v1/orders/{id}        → 200 OK, returns updated order
DELETE /v1/orders/{id}        → 204 No Content
```

**Step 2 — Choose a Paradigm**

This is a public-facing, CRUD-heavy resource → REST with OpenAPI spec.

**Step 3 — Map the Relationship**

`Order` contains `LineItems`. Line items never exist outside an order, so nested routes are correct:
```
GET /v1/orders/{orderId}/items
GET /v1/orders/{orderId}/items/{itemId}
```

But `Product` (which a line item references) has independent identity:
```
GET /v1/products/{productId}   ← flat, not nested under orders
```

**Step 4 — Version It**

Ship as `/v1`. In the `Order` response, never expose raw DB column names — expose a stable contract. When you later rename `shipping_addr` to `shipping_address`:

```http
# Old v1 response
{ "shipping_addr": "123 Main St" }

# New v2 response
{ "shipping_address": "123 Main St" }

# v1 endpoint continues to return shipping_addr until sunset
```

**Step 5 — Rate Limit It**

```
Public (unauthenticated):  100 requests / minute  per IP
Authenticated consumers:   1000 requests / minute per API key
Write endpoints (POST/PATCH/DELETE): 50 requests / minute per user
```

Implement at the API gateway (Kong, AWS API Gateway, Nginx) — not in application code.

---

## Use It

| Technology | How It Applies These Pillars |
|---|---|
| **Kong / AWS API Gateway** | Enforce rate limiting, route by version prefix, handle auth |
| **OpenAPI / Swagger** | Document and validate the interface contract |
| **GraphQL (Apollo)** | Schema enforces types; resolvers handle relationship fetching |
| **gRPC + Protobuf** | Interface defined in `.proto` file; versioned via package names |
| **Stripe API** | Textbook example: URL versioning (`/v1/`), envelope responses, per-key rate limits |
| **GitHub REST API** | Rate limit headers (`X-RateLimit-*`), nested resources (`/repos/{owner}/{repo}/issues`) |
| **Twilio** | Stable versioning, explicit deprecation announcements, token-bucket rate limits |

When to use each paradigm in practice:
- **REST** → public developer APIs, CRUD services, anything that benefits from HTTP caching
- **GraphQL** → mobile BFFs, dashboards that aggregate heterogeneous data
- **gRPC** → internal microservice mesh, real-time streaming, latency-critical paths

---

## Common Pitfalls

- **Leaking the data model through the interface.** Returning raw database column names (`created_at_utc_timestamp`) couples clients to your schema. Define a stable DTO layer and map from the DB to it explicitly.

- **Inconsistent error shapes.** Returning `{"error": "not found"}` from one endpoint and `{"message": "User does not exist", "code": 404}` from another forces every client to write bespoke error handling. Standardize on one error envelope.

- **Nesting too deeply.** Routes like `/teams/{teamId}/projects/{projectId}/tasks/{taskId}/comments/{commentId}` are fragile. They break when relationships change and are hard to reason about. Cap nesting at two levels; use flat routes with filter params beyond that.

- **Version-number inflation without a sunset plan.** Shipping `/v1`, `/v2`, `/v3`, `/v4` without retiring old versions forces you to maintain N codepaths indefinitely. Set a sunset date before you ship a new major version.

- **Rate limiting only at the application layer.** Application-layer rate limiting adds latency to every request and cannot protect the service from connection saturation at the network level. Rate limiting belongs at the gateway or load balancer, before traffic reaches your app servers.

---

## Exercises

1. **Easy** — Take a single REST endpoint (`POST /createUser`) that uses a verb in its URL and rewrites it using correct REST conventions. Define the response envelope, the status code on success, and the status code if the email is already taken.

2. **Medium** — A mobile app needs to show a user's profile, their last 5 orders, and the top product image for each order in a single screen load. Compare how you would solve this with REST (how many round trips?), GraphQL (one query?), and a custom BFF endpoint. State which you would choose and why.

3. **Hard** — Design the full rate-limiting strategy for a public API used by three consumer classes: anonymous users, free-tier developers, and paid enterprise clients. Specify the algorithm (and justify it), the limits per tier, the response headers, and where in the stack enforcement lives.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| REST | Any JSON API over HTTP | An architectural style using HTTP semantics: stateless, resource-oriented, uniform interface, layered system |
| Versioning | Just adding `/v2/` to the URL | A full lifecycle contract covering announcement, parallel operation, deprecation headers, and a sunset timeline |
| Rate Limiting | Blocking bad actors | Protecting system capacity for all consumers; most victims are legitimate clients that accidentally loop |
| Idempotent | "Does the same thing twice" | Calling the operation N times produces the same server state as calling it once; crucial for safe retries |
| Resource | A database table | Any named concept the API exposes — can be a document, a computation, a relationship, or an action |
| Nested Route | Organizing endpoints by hierarchy | Encoding ownership in the URL; appropriate when the child has no independent identity outside the parent |
| API Contract | Documentation | The machine-verifiable, versioned agreement between producer and consumer defining inputs, outputs, and behavior |

---

## Further Reading

- [REST API Design Best Practices — Microsoft REST API Guidelines](https://github.com/microsoft/api-guidelines/blob/vNext/Guidelines.md)
- [Google API Design Guide](https://cloud.google.com/apis/design) — resource-oriented design, versioning, and error model used across all Google Cloud APIs
- [Stripe API Reference](https://stripe.com/docs/api) — a real-world example of consistent versioning, envelopes, and rate-limit headers done right
- [GraphQL Best Practices — graphql.org](https://graphql.org/learn/best-practices/) — pagination, versioning philosophy, and nullability in schema design
- [gRPC Design Patterns](https://grpc.io/docs/guides/) — official guide covering service definition, streaming, and deadlines
