# A Cheatsheet on REST API Design Best Practices

> A REST API is a public contract — break it and you break every client that depends on it.

**Type:** Learn
**Prerequisites:** HTTP fundamentals, Client-server architecture basics
**Time:** ~25 minutes

---

## The Problem

You're three months into building a product. Your mobile app, web frontend, and two third-party integrations all talk to the same backend API. Then a routine refactor lands: a developer renames `/getUser?id=42` to `/users/42`, changes the error format to include a `code` field, and drops pagination support from a listing endpoint because "nobody was using it."

By Monday morning you have three broken clients, a spike of 5xx errors, and an angry enterprise partner whose integration silently deduped a payment twice because a retry had no idempotency key. None of this was a bug in the logic — it was a failure of API design discipline.

REST APIs don't fail at runtime; they fail through accumulated inconsistency. Clients can tolerate a slow API. They cannot tolerate an unpredictable one. Every deviation from convention — a verb in a path, an undocumented 200 that signals an error, a list endpoint with no size limit — becomes load-bearing tech debt the moment someone writes a client against it. The best practices in this lesson exist not to follow a style guide but to keep that contract stable and safe to evolve.

---

## The Concept

### 1. Resource-Oriented URLs with Correct HTTP Verbs

REST models your API as a set of **resources** (nouns), not operations (verbs). Each resource lives at a stable URL; HTTP methods express the action.

```
# WRONG — RPC-style
GET  /getUsers
POST /createOrder
POST /deleteItem?id=7

# RIGHT — Resource-oriented
GET    /users
POST   /orders
DELETE /items/7
```

**Resource naming rules:**
- Use **plural nouns** for collections: `/users`, `/orders`, `/products`
- Nest to express ownership — keep nesting ≤ 2 levels deep: `/users/{id}/addresses`
- Avoid verbs in paths; let the HTTP method be the verb

**HTTP method semantics:**

| Method  | Semantics                        | Idempotent? | Safe? |
|---------|----------------------------------|-------------|-------|
| GET     | Read a resource or collection    | Yes         | Yes   |
| POST    | Create a new resource            | No          | No    |
| PUT     | Full replace of a resource       | Yes         | No    |
| PATCH   | Partial update of a resource     | No*         | No    |
| DELETE  | Remove a resource                | Yes         | No    |

*PATCH can be made idempotent with a conditional header, but is not by default.

### 2. API Versioning

No API stays the same forever. Versioning lets you introduce breaking changes without breaking existing clients.

**Three strategies:**

```
# Strategy A — URL path (most visible, easiest to test in a browser)
GET /v1/users
GET /v2/users

# Strategy B — Request header (cleaner URLs)
GET /users
Accept: application/vnd.myapi.v2+json

# Strategy C — Query parameter (easy to override per-request, but muddies caching)
GET /users?api_version=2
```

**Default recommendation:** URL-path versioning for public APIs. It is explicit, cache-friendly, and immediately visible in logs. Use header versioning for internal or partner APIs where URL hygiene matters more.

Rule of thumb: bump the major version only for **breaking changes** (removed fields, changed types, altered semantics). Non-breaking additions (new fields, new optional query params) should not require a version bump if you document forwards compatibility.

### 3. Standard HTTP Status Codes

Never return `200 OK` with `{"success": false}` in the body. Use the status code to communicate outcome, the body for detail.

| Range | Meaning       | Common codes                                           |
|-------|---------------|--------------------------------------------------------|
| 2xx   | Success       | 200 OK, 201 Created, 204 No Content                    |
| 3xx   | Redirect      | 301 Moved Permanently, 304 Not Modified                |
| 4xx   | Client error  | 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 409 Conflict, 422 Unprocessable Entity, 429 Too Many Requests |
| 5xx   | Server error  | 500 Internal Server Error, 502 Bad Gateway, 503 Service Unavailable |

Use a consistent **error body format**:

```json
{
  "error": {
    "code": "PAYMENT_DECLINED",
    "message": "The card was declined by the issuer.",
    "details": { "decline_code": "insufficient_funds" },
    "request_id": "req_8f3ab2c1d"
  }
}
```

The `request_id` is essential for support and debugging — log it on the server side linked to the full trace.

### 4. Idempotency

An operation is **idempotent** if calling it once or a hundred times produces the same result on the server.

```
Client         API Server
  |                |
  |-- POST /pay -->|  (network times out)
  |                | ← did it go through?
  |-- POST /pay -->|  (retry — DANGER: double charge?)
```

Without idempotency, retries cause duplicate side effects. The solution is the **Idempotency-Key** header:

```
POST /payments
Idempotency-Key: 7f8d3a9e-4b1c-4f0e-9c6d-2e1f0a3b5c7d
Content-Type: application/json

{ "amount": 5000, "currency": "USD", "card": "tok_visa" }
```

The server stores the key (in Redis or a database) with the outcome. If the same key arrives again within a TTL window, it returns the cached response without re-executing the payment.

**How servers implement idempotency keys:**

```
┌──────────┐      Idempotency-Key: abc123
│  Client  │ ─────────────────────────────────► ┌───────────┐
└──────────┘                                     │   API     │
     ▲                                           │  Server   │
     │                                           └─────┬─────┘
     │                                                 │
     │                              ┌──────────────────▼──────────────────┐
     │                              │  SELECT result FROM idempotency_keys │
     │                              │  WHERE key = 'abc123'                │
     │                              └──────────────────┬──────────────────┘
     │                                                 │
     │                            cached? ─── YES ─────┤
     │  ◄── return cached response ────────────────────┘
     │
     │                            NO ──► execute operation
     │                                  store (key, response) in cache
     │  ◄── return fresh response ─────────────────────────────────────
```

### 5. Pagination

Never return unbounded collections. A `/users` endpoint that returns 2 million rows will bring down your service.

**Three strategies:**

| Strategy       | How it works                                  | Best for                            | Gotchas                               |
|----------------|-----------------------------------------------|-------------------------------------|---------------------------------------|
| Offset-based   | `?page=3&limit=20` → `OFFSET 40 LIMIT 20`    | Simple UIs with page numbers        | Skips/duplicates during inserts       |
| Cursor-based   | `?cursor=eyJpZCI6MTAwfQ==&limit=20`           | Infinite scroll, stable feeds       | Can't jump to arbitrary page          |
| Keyset-based   | `?after_id=100&limit=20` → `WHERE id > 100`  | Large tables, time-ordered data     | Requires sortable, indexed key column |

Return pagination metadata consistently:

```json
{
  "data": [...],
  "pagination": {
    "next_cursor": "eyJpZCI6MTIwfQ==",
    "has_more": true,
    "total": 8432
  }
}
```

Cursor-based is the safe default for most modern APIs — it avoids the expensive `COUNT(*)` and the stale-page problem of offset pagination.

### 6. Security

| Layer            | Mechanism                   | When to use                                                    |
|------------------|-----------------------------|----------------------------------------------------------------|
| Transport        | HTTPS / TLS 1.2+            | Always. Non-negotiable in production.                          |
| Authentication   | API Keys                    | Server-to-server integrations, simple public APIs              |
| Authentication   | JWT (Bearer token)          | Stateless user sessions, microservice auth                     |
| Authentication   | OAuth 2.0                   | Third-party access delegation ("Login with Google")            |
| Authorization    | RBAC / ABAC scopes          | Fine-grained permission checks on individual resources         |
| Rate limiting    | Token bucket / sliding window | Prevent abuse, protect downstream services                   |

Never log raw API keys or JWT payloads. Enforce rate limits per key/user, not just per IP. Include a `Retry-After` header on 429 responses so clients back off gracefully.

---

## Build It / In Depth

Let's design a real-world **Orders API** applying every principle above. Scenario: an e-commerce platform needs an API for creating orders, listing them, and handling payment retries safely.

**Step 1 — Resource model**

```
/orders              # collection
/orders/{order_id}   # single resource
/orders/{order_id}/items  # nested sub-resource (items in an order)
```

**Step 2 — Endpoints with correct verbs and status codes**

```
POST   /v1/orders            → 201 Created  (body: new order object)
GET    /v1/orders            → 200 OK       (body: paginated list)
GET    /v1/orders/{id}       → 200 OK       (body: single order)
PATCH  /v1/orders/{id}       → 200 OK       (body: updated order)
DELETE /v1/orders/{id}       → 204 No Content
```

**Step 3 — Create an order (POST with idempotency key)**

```http
POST /v1/orders HTTP/1.1
Host: api.shop.example
Authorization: Bearer eyJhbGciOiJSUzI1NiJ9...
Idempotency-Key: 3fa85f64-5717-4562-b3fc-2c963f66afa6
Content-Type: application/json

{
  "customer_id": "cust_9Xk2",
  "items": [
    { "sku": "SHOE-42-BLK", "qty": 1, "unit_price_cents": 8999 }
  ],
  "currency": "USD"
}
```

Server response on first call:

```http
HTTP/1.1 201 Created
Location: /v1/orders/ord_7Tj9
Content-Type: application/json

{
  "id": "ord_7Tj9",
  "status": "pending",
  "total_cents": 8999,
  "created_at": "2025-11-14T09:00:00Z"
}
```

On an identical retry (same `Idempotency-Key`):

```http
HTTP/1.1 200 OK          ← Note: 200, not 201. Resource already existed.
Content-Type: application/json

{
  "id": "ord_7Tj9",
  "status": "pending",
  ...
}
```

**Step 4 — List orders with cursor pagination**

```http
GET /v1/orders?limit=20&cursor=eyJpZCI6Im9yZF83VGo5In0= HTTP/1.1
Authorization: Bearer eyJhbGciOiJSUzI1NiJ9...
```

Response:

```json
{
  "data": [
    { "id": "ord_8Aa1", "status": "shipped", "total_cents": 4500 },
    ...
  ],
  "pagination": {
    "next_cursor": "eyJpZCI6Im9yZF84QWExIn0=",
    "has_more": true
  }
}
```

**Step 5 — Standardised error for a bad request**

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request body contains invalid fields.",
    "details": [
      { "field": "items[0].qty", "issue": "must be >= 1" }
    ],
    "request_id": "req_cF9d2a1b"
  }
}
```

**Step 6 — Versioned breaking change**

When you later need to split `customer_id` into `customer.id` + `customer.email`:

```
Old:  GET /v1/orders/{id}  → { "customer_id": "cust_9Xk2" }
New:  GET /v2/orders/{id}  → { "customer": { "id": "cust_9Xk2", "email": "..." } }
```

`v1` continues to work. Clients migrate at their own pace.

---

## Use It

| Tool / Framework           | How it applies REST best practices                                                          |
|----------------------------|---------------------------------------------------------------------------------------------|
| **Stripe API**             | Gold standard: noun-based URLs, idempotency keys on every mutating endpoint, cursor pagination, machine-readable error codes |
| **GitHub REST API**        | `Link` header pagination with cursor tokens, clear HTTP status semantics                    |
| **Express / FastAPI**      | Route-level middleware for auth, rate limiting, and request-ID injection                    |
| **Kong / AWS API Gateway** | API versioning via path prefixes, rate limiting, JWT validation at the gateway layer        |
| **OpenAPI / Swagger**      | Machine-readable contract enforcing naming, status codes, and schema consistency            |
| **Postman / Insomnia**     | Testing pagination, error responses, and idempotency key behaviour during development       |

When building a **public API**: follow Stripe's pattern precisely — idempotency keys, versioned paths, consistent error envelopes.

When building an **internal microservice API**: skip OAuth overhead, use mTLS or shared JWTs, but keep the same URL structure and error format so tooling (logging, tracing) stays uniform.

---

## Common Pitfalls

- **Returning 200 for errors.** Some teams wrap every response in `{"success": false, "data": null}` with HTTP 200. Monitoring, API gateways, and circuit breakers all key off the status code. Hiding errors inside 200 breaks them silently.

- **Putting verbs in URLs.** `/createOrder`, `/fetchUser`, `/doSearch` are RPC, not REST. They force clients to memorise every action name instead of relying on HTTP method semantics. Every new operation spawns a new "verb" with no discoverability.

- **Skipping versioning until it's too late.** Starting without a `/v1/` prefix means your first breaking change either breaks all clients or requires a global find-and-replace across every consumer's codebase. Add the prefix from day one.

- **Unbounded list endpoints.** An endpoint that returns a full table scan is a latency bomb and a DDoS vector. Always enforce a maximum page size (e.g., `limit` cannot exceed 100) and document the default.

- **Missing idempotency keys on POST mutations.** Any POST that has money, inventory, or user-account side effects must support an idempotency key. Clients on mobile networks retry automatically; without a key, they create duplicates. Add idempotency support before you have your first complaint, not after.

---

## Exercises

1. **Easy — Status code audit.** Take any public API you use regularly (GitHub, Stripe, Twilio). Find three endpoints. For each, predict what HTTP status code it returns for: a successful response, a missing resource, and an unauthenticated request. Verify against the documentation. Note any surprises.

2. **Medium — Paginate a real query.** You have a table with 500,000 rows sorted by `created_at DESC`. Implement both offset-based and keyset-based pagination in SQL for the query `GET /articles?limit=20`. Measure the query cost of page 1 versus page 10,000 for each approach. Which one degrades?

3. **Hard — Design an idempotent transfer API.** Design a `POST /v1/transfers` endpoint for a bank that moves money between two accounts. Define: the request schema, the idempotency key storage schema (table or Redis key structure), the TTL, how the server responds when it detects a duplicate, and what happens if the first request is still in-flight when the retry arrives. Write the pseudocode for the server handler.

---

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|------------------------|
| **Idempotent** | "Can be called multiple times safely" | The server state after N identical calls is the same as after 1 call. The responses may differ (e.g., 201 then 200), but the side effect is applied only once. |
| **REST** | "Using HTTP endpoints" | Representational State Transfer — an architectural style with specific constraints: stateless, uniform interface, resource-based addressing, layered system. Most "REST" APIs are actually REST-ish. |
| **Idempotency Key** | "A request ID" | A client-generated unique token that lets the server deduplicate repeated requests with side effects. Different from a request ID, which is server-generated and used for tracing. |
| **Cursor pagination** | "Using a secret offset" | An opaque token encoding a position in the dataset (e.g., `{"id": 420}` base64-encoded). The server decodes it to issue a keyset query, not an OFFSET. |
| **API versioning** | "Changing the URL" | A strategy for managing backward-incompatible API changes so existing clients continue to work without modification. URL path versioning is the most common form. |
| **Rate limiting** | "Blocking abusive users" | A mechanism to enforce throughput quotas per client/key to protect service reliability for all consumers — not just to punish abuse. |
| **422 vs 400** | "Both mean bad input" | 400 (Bad Request) is for malformed syntax (invalid JSON). 422 (Unprocessable Entity) is for valid syntax that fails semantic validation (e.g., `qty: -1`). Use both correctly. |

---

## Further Reading

- [Stripe API Design — HTTP status codes and idempotency keys](https://stripe.com/docs/api) — The de-facto industry reference for production-grade REST API design.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) — The authoritative specification for HTTP methods, status codes, and header semantics.
- [Microsoft REST API Guidelines](https://github.com/microsoft/api-guidelines/blob/vNext/azure/Guidelines.md) — A thorough opinionated guide used across Azure; covers versioning, pagination, errors, and long-running operations.
- [Google AIP — API Improvement Proposals](https://google.aip.dev/) — Google's internal API standards made public; covers resource naming, standard methods, and pagination in depth.
- [Web API Design: The Missing Link (Apigee)](https://cloud.google.com/files/apigee/apigee-web-api-design-the-missing-link-ebook.pdf) — A practical ebook on REST API design decisions with real trade-off analysis.
