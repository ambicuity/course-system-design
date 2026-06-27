# Best Practices in API Design

> A well-designed API is a promise: it tells callers exactly what to expect, today and years from now.

**Type:** Learn
**Prerequisites:** REST vs. GraphQL vs. gRPC, HTTP fundamentals, Authentication & Authorization patterns
**Time:** ~35 minutes

---

## The Problem

Imagine you join a company whose internal services have grown organically over five years. One service returns dates as Unix timestamps. Another returns them as `"YYYY-MM-DD"` strings. A third endpoint named `POST /deleteUser` mutates state but can't safely be retried. Paginating the product catalog requires a different query-param convention on every endpoint. There's no versioning, so any change to a contract silently breaks mobile clients that can't update overnight.

This is the cost of ignoring API design conventions: not a single catastrophic failure, but a thousand small ones. Developers waste hours reading inconsistent docs. Frontend teams build brittle workarounds. On-call engineers debug cascading failures caused by a retry storm on a non-idempotent endpoint. A security audit uncovers that some endpoints return full objects including private fields because nobody agreed on a response envelope.

Good API design is not cosmetic. It is an engineering discipline that determines maintainability, reliability, and how fast other teams can build on top of your system. The practices in this lesson are the minimum bar for any API that will be used by more than one consumer.

---

## The Concept

API design best practices cluster into four themes: **naming and structure**, **data handling**, **reliability**, and **governance**. Each theme has a core principle and concrete rules.

### 1. Naming and URL Structure

REST treats URLs as resource identifiers, not action labels. Follow these conventions:

| Rule | Wrong | Right |
|---|---|---|
| Nouns, not verbs | `GET /getUser` | `GET /users/{id}` |
| Plural collections | `GET /user` | `GET /users` |
| Lowercase, hyphenated | `GET /userProfiles` | `GET /user-profiles` |
| Hierarchy reflects ownership | `GET /getPostsForUser?id=5` | `GET /users/5/posts` |
| Actions as sub-resources | `POST /cancelOrder` | `POST /orders/{id}/cancellations` |

Use HTTP methods to encode intent: `GET` reads, `POST` creates, `PUT` replaces, `PATCH` partially updates, `DELETE` removes. Never use `GET` for a mutating operation — it will be cached.

### 2. Idempotency

An operation is **idempotent** if performing it N times produces the same result as performing it once.

```
GET    → idempotent (read-only)
PUT    → idempotent (replace the whole resource)
DELETE → idempotent (deleting something already gone is still "gone")
POST   → NOT idempotent by default (each call may create a new record)
PATCH  → NOT idempotent by default (depends on the operation)
```

For `POST` operations you want to make safe to retry (payments, order creation), use an **idempotency key** pattern: the client generates a UUID and sends it as a header (`Idempotency-Key: <uuid>`). The server stores the key and result; a duplicate request returns the stored result instead of re-executing.

```
Client                        Server
  │──POST /charges ────────────────────────►│
  │  Idempotency-Key: abc-123               │
  │                                         │──► Creates charge, stores {abc-123 → result}
  │◄─────────────── 201 Created ────────────│
  │                                         │
  │  (network failure, client retries)      │
  │──POST /charges ────────────────────────►│
  │  Idempotency-Key: abc-123               │
  │                                         │──► Key found → return cached result
  │◄─────────────── 201 Created ────────────│  (no second charge created)
```

### 3. Pagination

Never return unbounded collections. An endpoint that returns 100,000 records will eventually OOM the server or time out the client.

**Offset-based pagination** is the simplest but has correctness issues:

```
GET /products?page=3&limit=20
GET /products?offset=40&limit=20
```

If a record is inserted between page 2 and page 3 fetches, the client sees a duplicate. If one is deleted, they skip a record. Works fine for small, slow-changing datasets.

**Cursor-based pagination** is stable under inserts/deletes:

```
GET /products?limit=20
→ { items: [...], next_cursor: "eyJpZCI6IDQyfQ==" }

GET /products?limit=20&cursor=eyJpZCI6IDQyfQ==
→ { items: [...], next_cursor: "eyJpZCI6IDYxfQ==" }
```

The cursor encodes the position (usually the primary key of the last item, base64-encoded). Prefer cursor-based for real-time feeds, activity streams, and large datasets.

**Always include metadata** in paginated responses:

```json
{
  "data": [...],
  "pagination": {
    "next_cursor": "eyJpZCI6IDYxfQ==",
    "has_more": true,
    "total": 4821
  }
}
```

### 4. Sorting and Filtering

Expose these via query parameters, not path segments:

```
GET /orders?status=shipped&created_after=2024-01-01&sort=created_at:desc
GET /products?category=electronics&min_price=100&max_price=500&sort=rating:desc
```

Rules:
- Use `sort=field:asc|desc` or `sort_by=field&order=asc`.
- Accept multiple sort fields: `sort=priority:desc,created_at:asc`.
- Validate the sort and filter field names server-side; reject unknown fields with `400 Bad Request`.
- Document every filter and sort option in your OpenAPI spec.

### 5. Cross-Resource References

When a resource references another, embed either the ID or a hyperlink — not both redundantly.

**Prefer IDs in body, links in `_links` (HAL pattern) or a `links` envelope:**

```json
{
  "id": "order-99",
  "user_id": "user-42",
  "links": {
    "self":  "/orders/order-99",
    "user":  "/users/user-42",
    "items": "/orders/order-99/items"
  }
}
```

Avoid embedding full nested objects unless the consumer always needs them (use query params like `?include=user` for optional expansion). Deep nesting inflates payload size and couples the serialization contract of two different resources.

### 6. Rate Limiting

Rate limiting protects the API from abuse and ensures fair use. Expose the limits in response headers so clients can back off gracefully:

```
HTTP/1.1 200 OK
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 412
X-RateLimit-Reset: 1719360000
Retry-After: 30
```

When a client is throttled, return `429 Too Many Requests`. Common algorithms:

| Algorithm | How it works | Best for |
|---|---|---|
| Token bucket | Tokens refill at a rate; each request consumes one | Bursty traffic, smooth average |
| Sliding window log | Log timestamps of recent requests; reject if count exceeds limit | Accuracy at boundaries |
| Fixed window counter | Count resets every N seconds | Simple, but allows burst at window edge |
| Leaky bucket | Queue requests; drain at fixed rate | Strict output rate control |

Apply different rate limits per tier: unauthenticated < authenticated < premium < internal.

### 7. Versioning

APIs change. Versioning gives you the ability to evolve without breaking existing clients.

**URL versioning** — most common, maximally explicit:

```
/v1/users
/v2/users
```

**Header versioning** — keeps URLs clean:

```
GET /users
Accept: application/vnd.myapi.v2+json
```

**Query param versioning** — easy to test in a browser but easy to forget:

```
GET /users?api_version=2
```

URL versioning wins in practice because it's visible in logs, curl commands, docs, and bookmarks. Adopt a deprecation policy: announce deprecation at least 6–12 months in advance; return `Sunset` and `Deprecation` headers on deprecated endpoints.

```
Deprecation: Sun, 01 Jun 2025 00:00:00 GMT
Sunset: Sun, 01 Dec 2025 00:00:00 GMT
Link: <https://api.example.com/v2/users>; rel="successor-version"
```

### 8. Security

Minimum requirements for any production API:

- **Authentication**: Verify who the caller is. Use API keys for server-to-server, OAuth 2.0 + OIDC for user-delegated access, JWTs for stateless token propagation.
- **Authorization**: Verify what they can do. Enforce at the resource level, not just the route level. Return `403 Forbidden`, never silently return empty data.
- **HTTPS everywhere**: Never accept plaintext HTTP for anything except redirect to HTTPS.
- **Input validation**: Reject malformed, oversized, or unexpected input early. Validate against a schema (OpenAPI, JSON Schema).
- **Sensitive data**: Never return fields the caller is not authorized to see, even if empty. Use field-level projections. Audit log access to sensitive endpoints.
- **CORS**: Restrict allowed origins. `Access-Control-Allow-Origin: *` is not acceptable for authenticated APIs.

### Consistent Error Responses

Pick one error format and use it everywhere. The RFC 7807 "Problem Details" format is widely adopted:

```json
{
  "type": "https://api.example.com/errors/validation",
  "title": "Validation Failed",
  "status": 422,
  "detail": "The 'email' field must be a valid email address.",
  "instance": "/orders",
  "errors": [
    { "field": "email", "message": "Invalid email format" }
  ]
}
```

Never return `200 OK` with `{ "success": false }` — use the correct HTTP status code.

---

## Build It / In Depth

### Worked Example: Designing a `/orders` API from Scratch

**Step 1 — Define resources and methods**

```
POST   /orders                  Create a new order
GET    /orders                  List orders (paginated, filterable)
GET    /orders/{id}             Get a single order
PATCH  /orders/{id}             Update order status or fields
DELETE /orders/{id}             Cancel / soft-delete
POST   /orders/{id}/refunds     Trigger a refund (sub-resource, idempotent via key)
```

**Step 2 — Add idempotency to order creation**

```python
# Flask pseudo-code
@app.route("/orders", methods=["POST"])
def create_order():
    idempotency_key = request.headers.get("Idempotency-Key")
    if idempotency_key:
        cached = redis.get(f"idem:{idempotency_key}")
        if cached:
            return jsonify(json.loads(cached)), 200   # replay stored response

    order = Order.create(request.json)
    response = order.to_dict()

    if idempotency_key:
        redis.setex(f"idem:{idempotency_key}", 86400, json.dumps(response))

    return jsonify(response), 201
```

**Step 3 — Implement cursor pagination**

```python
@app.route("/orders", methods=["GET"])
def list_orders():
    limit = min(int(request.args.get("limit", 20)), 100)
    cursor = request.args.get("cursor")          # base64-encoded last seen id
    status = request.args.get("status")          # optional filter

    query = Order.query.order_by(Order.id.asc())
    if status:
        query = query.filter(Order.status == status)
    if cursor:
        last_id = base64.b64decode(cursor).decode()
        query = query.filter(Order.id > last_id)

    orders = query.limit(limit + 1).all()
    has_more = len(orders) > limit
    if has_more:
        orders = orders[:limit]

    next_cursor = (
        base64.b64encode(str(orders[-1].id).encode()).decode()
        if has_more else None
    )

    return jsonify({
        "data": [o.to_dict() for o in orders],
        "pagination": { "next_cursor": next_cursor, "has_more": has_more }
    })
```

**Step 4 — Version the API via URL prefix**

```python
v1 = Blueprint("v1", __name__, url_prefix="/v1")
v2 = Blueprint("v2", __name__, url_prefix="/v2")

@v1.route("/orders")
def list_orders_v1(): ...   # original shape

@v2.route("/orders")
def list_orders_v2(): ...   # new shape with cursor pagination added
```

**Step 5 — Return rate limit headers in a middleware**

```python
@app.after_request
def add_rate_limit_headers(response):
    user_id = g.get("user_id", "anon")
    key = f"rl:{user_id}"
    remaining = redis.decr(key)
    if remaining < 0:
        return make_response({"error": "rate limit exceeded"}, 429)
    response.headers["X-RateLimit-Remaining"] = max(remaining, 0)
    response.headers["X-RateLimit-Limit"] = RATE_LIMIT
    response.headers["X-RateLimit-Reset"] = int(time.time()) + WINDOW_SECONDS
    return response
```

**Step 6 — OpenAPI spec snippet for documentation**

```yaml
openapi: "3.1.0"
paths:
  /v2/orders:
    get:
      summary: List orders
      parameters:
        - name: cursor
          in: query
          schema: { type: string }
        - name: limit
          in: query
          schema: { type: integer, default: 20, maximum: 100 }
        - name: status
          in: query
          schema:
            type: string
            enum: [pending, shipped, delivered, cancelled]
      responses:
        "200":
          description: Paginated order list
        "429":
          description: Rate limit exceeded
```

---

## Use It

| Technology / Pattern | When to reach for it |
|---|---|
| **OpenAPI / Swagger** | Document and contract-test any HTTP API; generate client SDKs automatically |
| **Stripe API** | Reference implementation for idempotency keys, versioning via `Stripe-Version` header, and structured error envelopes |
| **GitHub REST API** | Reference for cursor pagination with `Link` headers, rate-limit headers, and resource nesting |
| **Kong / AWS API Gateway** | Off-the-shelf rate limiting, auth, and versioning at the gateway layer without code changes |
| **RFC 7807 Problem Details** | Standard error envelope used by Spring Boot, ASP.NET, and many others |
| **HAL / JSON:API / JSON-LD** | Hypermedia formats when discoverability between related resources matters |
| **Spectral (Stoplight)** | Lint your OpenAPI spec for naming, security, and structure violations in CI |

---

## Common Pitfalls

- **Using `POST` for reads.** Some teams use `POST /search` with a body to avoid query-param length limits, which is fine — but mixing this with mutating `POST` endpoints in the same service confuses cacheability semantics. Be explicit in documentation.

- **Ignoring idempotency on money or inventory operations.** A payment endpoint that runs twice causes real financial harm. Any endpoint that charges, deducts stock, or sends an email must be idempotent. Idempotency keys cost almost nothing to implement and prevent catastrophic duplicates.

- **Returning `200 OK` for every response.** Wrapping all errors in `200 OK` with a `success: false` field breaks HTTP clients, monitoring tools, API gateways, and load balancers that rely on status codes for health checks and circuit breaking.

- **Breaking changes without a version bump.** Removing a field, changing a field type, or renaming a key are breaking changes. Additions and new optional fields are generally safe. Establish a written breaking-change policy and enforce it with contract tests.

- **Leaking internal detail in error messages.** Stack traces, SQL errors, and internal service names returned to clients are a security vulnerability. Map internal exceptions to user-safe error messages and log the details server-side.

---

## Exercises

1. **Easy** — Take the endpoint `POST /getUserDataByEmail` and redesign it following REST naming conventions. What method and path would you use? What HTTP status code should it return when the user is not found?

2. **Medium** — Your `GET /reports` endpoint currently returns all 50,000 records at once. Redesign it to support cursor-based pagination. Write the request/response shapes for the first page and the second page. What field in the response tells the client there are more pages?

3. **Hard** — Design a versioning and deprecation strategy for an API that is currently at v1 with 20 client teams depending on it. You need to introduce breaking changes in v2. Write the policy document: how will you announce the v1 sunset, what headers will deprecated v1 endpoints return, and how long will v1 remain live? Include the OpenAPI change needed and the monitoring you would put in place to track v1 usage over time.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Idempotency** | "Only run things once" | Performing the same operation N times produces the same result as performing it once — it's about the *outcome*, not preventing duplicate calls |
| **REST** | "Any HTTP API" | An architectural style with specific constraints: statelessness, uniform interface, resource-based URLs, and use of HTTP semantics correctly |
| **Cursor pagination** | "Just a fancier offset" | A stable pointer into a sorted result set, typically the opaque ID of the last item seen; immune to insert/delete skew that breaks offset pagination |
| **Rate limiting** | "Blocking bad actors" | Controlling the *rate* of requests to protect service capacity and ensure fair use — applies to legitimate clients too, not just abusers |
| **API versioning** | "Adding v2 when v1 is broken" | A forward contract with consumers that allows you to evolve the API without breaking existing integrations; should be planned from v1, not added after the fact |
| **429 Too Many Requests** | "A ban" | A temporary signal to back off and retry after the `Retry-After` interval; clients should handle it gracefully, not treat it as a permanent failure |
| **Breaking change** | "Anything that changes behavior" | Specifically: removing a field, changing a field's type, renaming a field, changing a URL, or changing a status code. Adding new optional fields is non-breaking |

---

## Further Reading

- [Stripe API Reference](https://stripe.com/docs/api) — Industry reference for idempotency keys, versioning, and error envelopes in a production API used at massive scale.
- [GitHub REST API Documentation](https://docs.github.com/en/rest) — Well-documented example of pagination with `Link` headers, rate-limit headers, and resource hierarchy.
- [RFC 7807 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc7807) — The IETF standard for structured error responses; widely implemented in Spring, ASP.NET, and FastAPI.
- [OpenAPI Specification (OAS 3.1)](https://spec.openapis.org/oas/v3.1.0) — The schema language for documenting, validating, and generating code from HTTP APIs.
- [Web API Design: The Missing Link (Apigee)](https://cloud.google.com/files/apigee/apigee-web-api-design-the-missing-link-ebook.pdf) — Practical ebook covering naming, versioning, and error handling with real examples.
