# How to Design Good APIs

> A great API feels inevitable — every endpoint does exactly what its name promises, every error tells you what went wrong, and every caller can recover gracefully.

**Type:** Learn
**Prerequisites:** REST vs. GraphQL vs. gRPC, HTTP fundamentals, Authentication & Authorization patterns
**Time:** ~35 minutes

---

## The Problem

Imagine your mobile team ships a new feature. They call `POST /api/placeOrder` twice because the network timed out on the first request. The result: the customer is charged twice. The server never told the client the first request succeeded; there was no idempotency key. Six weeks later the backend team renames the endpoint to `/api/orders/create` for "consistency" — and silently breaks every integration partner. Now those partners must scramble to patch production.

APIs are contracts. Unlike internal code you can refactor at will, an API's consumers span mobile apps, third-party integrations, internal microservices, and SDKs you no longer control. A bad design decision baked into v1 can haunt you for years. Even giants like Twitter and Stripe have made painful public API migrations that broke clients and eroded trust.

The stakes are high precisely because API design is deceptively easy to get wrong. The surface-level decisions — naming, versioning, HTTP method choice — seem trivial until production traffic hits and you realize your choices made a class of bugs nearly impossible to prevent, or made a class of clients nearly impossible to build. This lesson gives you the mental model and concrete rules to get those choices right the first time.

---

## The Concept

Good API design rests on five pillars: **consistency**, **idempotency**, **security**, **discoverability**, and **evolvability**. Miss any one of them and you pay in operational pain later.

### 1. Resource-Oriented Naming

HTTP is a resource protocol. Your URLs should name things (nouns), not actions (verbs). The HTTP method carries the action.

| Wrong (verb-based)            | Right (noun-based)           |
|-------------------------------|------------------------------|
| `GET /api/getUser`            | `GET /api/users/{id}`        |
| `POST /api/createOrder`       | `POST /api/orders`           |
| `POST /api/deleteProduct`     | `DELETE /api/products/{id}`  |
| `GET /api/fetchUserOrders`    | `GET /api/users/{id}/orders` |

Rules:
- Collections are plural: `/orders`, `/products`, `/users`
- Nested resources express ownership: `/users/{id}/orders`
- Use lowercase, hyphens for multi-word segments: `/shipping-addresses`
- Never expose internal IDs (auto-increment integers) directly; use opaque UUIDs or slugs

### 2. Idempotency

An operation is **idempotent** if calling it N times produces the same result as calling it once.

```
GET  /orders/123     →  idempotent (read only)
PUT  /orders/123     →  idempotent (full replace, same result each time)
DELETE /orders/123   →  idempotent (first call deletes, subsequent calls get 404 — state is stable)
POST /orders         →  NOT idempotent by default (each call may create a new resource)
PATCH /orders/123    →  NOT idempotent by default (depends on operation)
```

Why it matters: networks fail. Clients retry. Without idempotency guarantees, retries cause duplicate charges, duplicate shipments, and corrupted state.

**Idempotency keys** solve POST's non-idempotency problem:
1. Client generates a UUID (`Idempotency-Key: a7f3c9d0-...`) and stores it locally.
2. Client sends the key in every request attempt for this operation.
3. Server stores `(key → response)` in Redis or a DB table on first success.
4. On retry, server recognizes the key and returns the stored response — no re-processing.
5. Keys expire after a safe window (24–72 hours).

```
Client                           Server
  |                                |
  |-- POST /payments               |
  |   Idempotency-Key: k-abc123    |
  |   { amount: 50 }              --->  First call: charge card, store (k-abc123 → 200 OK)
  |                                |
  |   [network timeout]            |
  |                                |
  |-- POST /payments               |
  |   Idempotency-Key: k-abc123    |
  |   { amount: 50 }              --->  Key found: return stored response, no second charge
  |<-- 200 OK (same response)      |
```

### 3. Versioning

APIs evolve. The question is not *if* you will need to version, but *how*.

| Strategy            | Example                              | Trade-offs                                                          |
|---------------------|--------------------------------------|---------------------------------------------------------------------|
| URL path versioning | `/v1/orders`, `/v2/orders`           | Simple, highly visible, cache-friendly. Proliferates URL namespaces.|
| Query string        | `/orders?version=2`                  | Easy to implement. Hard to route at the infrastructure layer.       |
| Header versioning   | `Accept: application/vnd.api+json;version=2` | Clean URLs. Harder to test in a browser. Requires documentation.  |
| Content negotiation | `Accept: application/vnd.myapi.v2+json` | Most RESTfully correct. Least discoverable.                       |

**URL path versioning is the industry default** (Stripe, GitHub, Twilio all use it). It is cache-friendly, browser-testable, and immediately obvious in logs and dashboards.

Breaking vs. non-breaking changes:
- **Breaking:** removing a field, changing a field's type, removing an endpoint, changing required parameters
- **Non-breaking:** adding new optional fields, adding new endpoints, adding new optional query params

Never make breaking changes within a version. When you must, increment the version and support the old version for a defined sunset period.

### 4. Pagination

Never return unbounded result sets. A single call that returns 10,000 rows is a DDoS waiting to happen.

**Offset/Limit (simple, but has gaps):**
```
GET /orders?limit=20&offset=40
```
- Easy to implement and understand
- Skips work if items are inserted/deleted between pages (page drift)
- Performance degrades at large offsets (DB must scan all preceding rows)

**Cursor-based (preferred for large, mutable datasets):**
```
GET /orders?limit=20&after=cursor_eyJpZCI6MTIzfQ==
```
- Cursor encodes the position (e.g., base64-encoded last-item ID or timestamp)
- Stable — no drift when items are inserted between pages
- Cannot jump to arbitrary pages
- Used by Twitter, Facebook, Stripe

**Response envelope for paginated APIs:**
```json
{
  "data": [...],
  "pagination": {
    "next_cursor": "cursor_eyJpZCI6MTQzfQ==",
    "has_more": true,
    "total": 843
  }
}
```

### 5. Security

Every endpoint is a potential attack surface.

- **Always HTTPS.** No exceptions. Terminate TLS at the load balancer or API gateway; never serve API traffic over plain HTTP.
- **Authenticate every request.** Use Bearer tokens (JWT or opaque) in the `Authorization` header. Never pass credentials in query strings — they appear in logs.
- **Validate the JWT on every call.** Check the signature, `exp` claim, `iss` claim, and `aud` claim. Treat the payload as untrusted until the signature verifies.
- **Authorize by resource ownership.** Authenticating who someone is is not enough; verify they own the resource they are accessing. `GET /orders/123` should reject user B trying to read user A's order.
- **Rate limit.** Protect against abuse and runaway clients. Return `429 Too Many Requests` with a `Retry-After` header when limits are hit.
- **Never return internal details in errors.** Stack traces, SQL errors, and file paths in error responses are information leaks.

### 6. Consistent Error Responses

Your error body is part of your API contract. Define it once and never deviate.

```json
{
  "error": {
    "code": "ORDER_NOT_FOUND",
    "message": "No order with id 'ord_abc123' exists for this account.",
    "request_id": "req_9f3c2d",
    "documentation_url": "https://docs.example.com/errors/ORDER_NOT_FOUND"
  }
}
```

| HTTP Status | When to use                                                     |
|-------------|------------------------------------------------------------------|
| 200 OK      | Successful GET, PUT, PATCH                                       |
| 201 Created | Successful POST that created a resource                          |
| 204 No Content | Successful DELETE (no body to return)                        |
| 400 Bad Request | Invalid input, malformed JSON, failed validation            |
| 401 Unauthorized | Missing or invalid credentials                            |
| 403 Forbidden | Authenticated but not authorized                             |
| 404 Not Found | Resource does not exist (or you choose not to reveal it)    |
| 409 Conflict | Duplicate resource, state machine conflict                    |
| 422 Unprocessable Entity | Syntactically valid but semantically wrong          |
| 429 Too Many Requests | Rate limit exceeded                                    |
| 500 Internal Server Error | Something unexpected broke on the server           |

---

## Build It / In Depth

### Worked Example: Designing the Orders API

**Step 1: Define your resources and their relationships**

```
User  1───* Order  1───* OrderItem
                  │
                  └──* ShipmentEvent
```

**Step 2: Map CRUD operations to HTTP methods**

```
POST   /orders                  → create order
GET    /orders                  → list orders (paginated)
GET    /orders/{id}             → fetch single order
PATCH  /orders/{id}             → partial update (e.g., change address before shipment)
DELETE /orders/{id}             → cancel order (soft delete)
GET    /orders/{id}/items       → list items in an order
POST   /orders/{id}/refund      → trigger refund (action endpoint — acceptable for non-CRUD operations)
```

**Step 3: Design the request/response contract**

```http
POST /v1/orders
Authorization: Bearer eyJhbGci...
Idempotency-Key: idk_7a3f91bc
Content-Type: application/json

{
  "items": [
    { "product_id": "prod_abc", "quantity": 2 }
  ],
  "shipping_address_id": "addr_xyz",
  "coupon_code": "SAVE10"
}
```

```http
HTTP/1.1 201 Created
Location: /v1/orders/ord_9f3c2d1a

{
  "id": "ord_9f3c2d1a",
  "status": "pending",
  "total_cents": 4590,
  "currency": "USD",
  "items": [...],
  "created_at": "2025-11-14T09:32:00Z"
}
```

**Step 4: Handle partial updates cleanly with PATCH**

Use JSON Merge Patch (RFC 7396) for simple partial updates:

```http
PATCH /v1/orders/ord_9f3c2d1a
Content-Type: application/merge-patch+json

{
  "shipping_address_id": "addr_new"
}
```

Only the field provided changes. Fields omitted are untouched. Fields explicitly set to `null` are cleared.

**Step 5: Wire up rate limiting headers**

Inform clients of their quota so they can back off intelligently:

```http
HTTP/1.1 200 OK
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 842
X-RateLimit-Reset: 1731586800
```

When the limit is breached:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 37
Content-Type: application/json

{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "You have exceeded 1000 requests per hour.",
    "retry_after_seconds": 37
  }
}
```

---

## Use It

| Technology / Pattern     | When to reach for it                                                                 |
|--------------------------|--------------------------------------------------------------------------------------|
| **Stripe API**           | Gold standard for idempotency keys, versioning, and error design. Study it first.    |
| **OpenAPI / Swagger**    | Define your API contract before writing code. Generate docs and client SDKs from it. |
| **Kong / AWS API Gateway** | Enforce rate limiting, authentication, and versioning at the gateway layer.        |
| **Postman / Insomnia**   | Build and share collections; run contract tests in CI.                               |
| **Prism (Stoplight)**    | Mock server from OpenAPI spec; lets frontend teams work before backend is ready.     |
| **RFC 7807 Problem Details** | Standardized error response format — use when building interoperable APIs.       |
| **HTTP/2**               | Multiplexing reduces latency for API-heavy clients with many parallel requests.       |
| **Cursor pagination**    | Use whenever the dataset can grow large or is frequently written to (feeds, events). |

---

## Common Pitfalls

- **Verbs in URL paths.** `/api/getUser` is an RPC style leaking into REST. The HTTP method is the verb. Keep URLs as pure nouns. Once a verb-based URL reaches production, you cannot easily rename it without breaking callers.

- **Ignoring idempotency on POST.** Assuming every client will send exactly one request per user intent is wrong at scale. Networks fail, clients timeout, users click twice. Implement idempotency keys for any POST that creates a resource or triggers a financial operation.

- **Silent breaking changes.** Removing a field or changing its type inside an existing version (`/v1/...`) is a silent contract violation. Callers will crash with cryptic errors. Add a formal deprecation header (`Deprecation: true`, `Sunset: Sat, 01 Mar 2025 00:00:00 GMT`) and give consumers a migration window before removing anything.

- **401 vs. 403 confusion.** `401 Unauthorized` means "I don't know who you are — authenticate first." `403 Forbidden` means "I know who you are, and you don't have permission." Using 403 for unauthenticated requests leaks that a resource exists.

- **Unbounded list endpoints.** `GET /events` that returns millions of rows with no `limit` default is a denial-of-service vector and a memory bomb for your server. Always enforce a server-side maximum page size (e.g., 100) and default to a safe value (e.g., 20) when the client omits `limit`.

---

## Exercises

1. **Easy:** Take the following verb-based URL list and rewrite each as a proper resource-oriented URL with the correct HTTP method:
   - `POST /api/createUser`
   - `GET /api/getUserOrders?userId=5`
   - `POST /api/deleteProduct?id=42`
   - `GET /api/listActiveSubscriptions`

2. **Medium:** Design the complete URL structure, HTTP methods, status codes, and request/response JSON for a "Comments" sub-resource on a blog post API. Consider how you would paginate comments (offset vs. cursor — justify your choice) and how you would handle attempts to comment on a post that has been locked by a moderator.

3. **Hard:** A payment API is experiencing duplicate charges because some clients do not implement idempotency keys and the mobile app retries on network timeout. Design the full idempotency key system: the client contract (which header, UUID generation), the server storage schema (table/Redis key structure), the deduplication window, the edge cases (what if the first request fails mid-transaction?), and a migration plan that adds idempotency support without breaking existing callers that do not send keys.

---

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|------------------------|
| **Idempotent** | "The server does nothing the second time" | The end state is the same regardless of how many identical requests are sent. A DELETE may return 404 on the second call but the resource is still gone — that is idempotent. |
| **REST** | "Any JSON API over HTTP" | A set of architectural constraints: stateless client-server interaction, uniform interface, resource identification via URI, and hypermedia as the engine of application state. Most "REST" APIs are actually REST-adjacent. |
| **Idempotency Key** | "A cache key that prevents duplicate rows" | A client-generated unique token that lets the server detect retries and return the original response, decoupling network-level retry from business-logic re-execution. |
| **Pagination cursor** | "A page number" | An opaque pointer to a position in a result set — typically a base64-encoded last-seen ID or timestamp. It guarantees stable iteration even when the underlying dataset changes between pages. |
| **401 vs. 403** | "Both mean 'you can't do that'" | 401 = unauthenticated (no valid credentials). 403 = authenticated but unauthorized (you are known, but denied). Confusing them leaks information about resource existence. |
| **API versioning** | "Incrementing a number when things change" | A commitment mechanism that isolates breaking changes to a new version while preserving backward compatibility for existing callers for a defined period. Versioning is a promise, not just a number. |
| **Sunset header** | "An HTTP header I've never seen" | `Sunset: <HTTP-date>` (RFC 8594) signals when a deprecated API version will be decommissioned. Allows automated tooling and developers to track and respond to API lifecycle changes. |

---

## Further Reading

- [Stripe API Reference](https://stripe.com/docs/api) — The most carefully designed public REST API available. Study the error format, idempotency key documentation, and versioning model.
- [Google Cloud API Design Guide](https://cloud.google.com/apis/design) — Covers resource naming, standard methods, errors, and common patterns for large-scale API design.
- [RFC 7807 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc7807) — The standard for machine-readable error responses. Widely adopted in modern REST and HTTP APIs.
- [RFC 8594 — The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594) — Defines the `Sunset` header for signaling API deprecation timelines to clients.
- [Designing Web APIs — Brenda Jin, Saurabh Sahni, Amir Shevat (O'Reilly)](https://www.oreilly.com/library/view/designing-web-apis/9781492026914/) — Comprehensive book covering REST, GraphQL, and Webhooks with real-world design case studies.
