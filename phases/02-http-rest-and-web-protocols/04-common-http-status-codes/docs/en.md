# Common HTTP Status Codes

> A status code is a contract: it tells the caller exactly what happened so they can react intelligently without parsing the body.

**Type:** Learn
**Prerequisites:** HTTP & REST Fundamentals, Anatomy of an HTTP Request/Response
**Time:** ~25 minutes

---

## The Problem

You ship a REST API. A mobile client calls `POST /orders` and gets back a response. The body says `{"error": "payment failed"}` — but the HTTP status is `200 OK`. The client SDK logs "success", the retry logic does nothing, and the user is charged twice on a second manual attempt. This class of bug is pervasive and entirely preventable.

Without a shared vocabulary of status codes, every client must parse every body just to know whether anything worked. Caches cannot reason about cacheable responses. Load balancers cannot distinguish transient server errors from permanent failures. Monitoring systems cannot separate user mistakes from infrastructure outages.

Status codes exist so that every layer in a distributed system — client libraries, proxies, CDNs, gateways, alerting tools — can act correctly without understanding your application's domain. Getting them right is not cosmetic; it is a correctness requirement.

---

## The Concept

HTTP status codes are three-digit integers grouped into five classes by their leading digit. The class alone is enough for a client to decide its default behavior; the specific code adds detail.

```
1xx  Informational    Request received, continue processing
2xx  Success          Request was received, understood, and accepted
3xx  Redirection      Further action needed to complete the request
4xx  Client Error     Request contains bad syntax or cannot be fulfilled
5xx  Server Error     Server failed to fulfill an apparently valid request
```

### 1xx — Informational

Rarely seen in application code. The most useful is:

| Code | Name | When to use |
|------|------|-------------|
| 100 | Continue | Client asked if it can send a large body (via `Expect: 100-continue`). Server says yes. |
| 101 | Switching Protocols | Server accepts an upgrade, e.g., HTTP → WebSocket. |

### 2xx — Success

These tell the client the operation completed. The specific code signals *what kind* of completion.

| Code | Name | When to use |
|------|------|-------------|
| 200 | OK | Generic success. GET, PUT, PATCH responses with a body. |
| 201 | Created | A new resource was created. Always include `Location` header pointing to it. |
| 202 | Accepted | Request accepted for async processing; work is not done yet. |
| 204 | No Content | Success, but there is no body to return. Common for DELETE and some PUT. |
| 206 | Partial Content | Response is a range (used with video streaming, resumable downloads). |

**Mental model:** 200 is the catch-all; prefer a more specific 2xx when semantics match.

### 3xx — Redirection

Tell the client to look elsewhere. The key axis is **temporary vs. permanent** and **method preservation**.

| Code | Name | Permanent? | Preserves POST? |
|------|------|-----------:|----------------:|
| 301 | Moved Permanently | Yes | No (may change to GET) |
| 302 | Found | No | No (may change to GET) |
| 303 | See Other | No | No (always GET) |
| 307 | Temporary Redirect | No | Yes |
| 308 | Permanent Redirect | Yes | Yes |

**The 303 pattern:** After a `POST` that creates a resource, respond `303 See Other` with a `Location` to the resource. The client GETs it. This prevents resubmission on browser refresh — the classic Post/Redirect/Get (PRG) pattern.

**SEO implication:** Search crawlers treat 301/308 as signals to update their index. Use 301 when moving a URL permanently; use 302/307 for A/B tests or maintenance pages.

### 4xx — Client Error

The client did something wrong. The server should not retry. Always include a body explaining the error.

| Code | Name | When to use |
|------|------|-------------|
| 400 | Bad Request | Malformed syntax, invalid JSON, failed schema validation. |
| 401 | Unauthorized | No valid credentials supplied. (Despite the name, it means unauthenticated.) |
| 403 | Forbidden | Credentials are valid but the caller lacks permission. |
| 404 | Not Found | Resource does not exist. Also usable to hide existence of forbidden resources. |
| 405 | Method Not Allowed | The HTTP verb is not supported on this endpoint. Include `Allow` header. |
| 409 | Conflict | State conflict — e.g., duplicate key, optimistic locking failure. |
| 410 | Gone | Resource existed but has been permanently deleted. Unlike 404, the client should stop trying. |
| 422 | Unprocessable Entity | Syntactically valid but semantically wrong (e.g., end date before start date). |
| 429 | Too Many Requests | Rate limit exceeded. Should include `Retry-After` header. |

**401 vs 403 — get this right:**
```
No token supplied          → 401 Unauthorized
Expired / invalid token    → 401 Unauthorized
Valid token, wrong role    → 403 Forbidden
Valid token, own resource  → 200 OK
Valid token, other's resource → 403 Forbidden (or 404 to obscure existence)
```

### 5xx — Server Error

Something went wrong on the server side. Clients *may* retry with back-off; infrastructure layers will usually alert.

| Code | Name | When to use |
|------|------|-------------|
| 500 | Internal Server Error | Unhandled exception, catch-all server error. |
| 501 | Not Implemented | The server does not support the functionality required. |
| 502 | Bad Gateway | Upstream service returned an invalid response. |
| 503 | Service Unavailable | Server is temporarily overloaded or down for maintenance. Include `Retry-After`. |
| 504 | Gateway Timeout | Upstream service did not respond in time. |

**502 vs 503 vs 504:**
```
Your app crashed                 → 500
Your upstream returned garbage   → 502
Your app is overloaded / paused  → 503
Your upstream was too slow       → 504
```

---

## Build It / In Depth

### Designing a REST API with correct status codes

Consider a `/users` API. Walk through each operation:

```
GET    /users/42        → 200 OK            (user found)
GET    /users/99        → 404 Not Found     (no such user)

POST   /users           → 201 Created       (body: new user, Location: /users/43)
POST   /users           → 400 Bad Request   (missing required field "email")
POST   /users           → 409 Conflict      (email already registered)

PUT    /users/42        → 200 OK            (full update, return updated resource)
PATCH  /users/42        → 200 OK            (partial update)
PATCH  /users/42        → 422 Unprocessable Entity  (age: -5 is invalid)

DELETE /users/42        → 204 No Content    (deleted, no body)
DELETE /users/99        → 404 Not Found     (can't delete what doesn't exist)
```

### Async job pattern with 202

When a `POST /reports` triggers a long-running job:

```
Client → POST /reports
Server → 202 Accepted
         Location: /jobs/abc-123

Client → GET /jobs/abc-123
Server → 200 OK  {"status": "running", "progress": 40}

Client → GET /jobs/abc-123
Server → 200 OK  {"status": "done", "result_url": "/reports/789"}
```

The client knows from `202` that the work is deferred, not complete. `Location` gives a polling URL. When done, the job resource links to the result.

### Rate limiting response (429)

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 30
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1719360000

{
  "error": "rate_limit_exceeded",
  "message": "You have exceeded 100 requests/minute. Try again in 30 seconds."
}
```

The client reads `Retry-After: 30` and backs off exactly 30 seconds. Without the correct 429, a retry loop hammers the server.

### Interpreting status codes in a flow diagram

```
                     ┌─────────────────────────┐
   HTTP Response     │   Read Status Code Class │
        │            └───────────┬─────────────┘
        │                        │
        ├── 1xx ─────────────────► Continue / protocol switch
        │
        ├── 2xx ─────────────────► Parse body, surface to application
        │
        ├── 3xx ─────────────────► Follow Location header (up to N hops)
        │
        ├── 4xx ─────────────────► Surface error to user; DO NOT retry
        │   ├── 429 ──────────── ► Retry after Retry-After delay
        │   └── other 4xx ──────► Log + alert (programmer / user error)
        │
        └── 5xx ─────────────────► Retry with exponential back-off
            ├── 503 ──────────── ► Respect Retry-After if present
            └── 500/502/504 ────► Back-off, circuit break after N failures
```

---

## Use It

### Where specific codes matter most

| System | Key codes | Why |
|--------|-----------|-----|
| REST APIs | 201, 400, 401, 403, 404, 409, 422, 429 | Clients and SDKs branch on these |
| Browser / SPA | 301, 302, 304 | Cache and navigation behavior |
| CDN / Reverse Proxy | 200, 304, 301, 404, 5xx | Cache storage, pass-through decisions |
| Load balancer health check | 200, 503 | Health probe passes on 2xx, removes instance on 5xx |
| Webhook delivery | 200, 2xx, 5xx | Provider retries on non-2xx |
| gRPC-HTTP transcoding | All | gRPC status maps 1:1 to HTTP status |

### Framework conventions

- **Express / Fastify (Node):** `res.status(201).json({...})` — status is set explicitly; defaults to 200.
- **Django REST Framework:** `Response(data, status=status.HTTP_201_CREATED)` — named constants reduce typos.
- **FastAPI (Python):** `@app.post("/items", status_code=201)` — declared in the route decorator; OpenAPI schema reflects it automatically.
- **Spring Boot:** `ResponseEntity.created(uri).body(dto)` — builder sets 201 + Location.

### CDN caching rules

CDNs cache by status code policy. Cloudflare, for example:
- `200`, `206`, `301` → cache by default
- `404`, `410` → cache with short TTL (avoids thundering herd on popular missing URLs)
- `5xx` → never cache (serve stale if available)

---

## Common Pitfalls

- **Returning 200 for errors.** The classic anti-pattern: `{"success": false, "error": "not found"}` with status 200. Breaks every layer that acts on status codes — monitors, SDKs, retry logic, caches. Use the semantically correct 4xx or 5xx.

- **Confusing 401 and 403.** Using 403 when the user is not logged in leaks the fact that a resource exists and is guarded. Return 401 when credentials are absent or invalid; 403 only when authentication succeeded but authorization failed.

- **Using 404 for "nothing matched a search."** A search endpoint returning zero results is a success — respond `200 OK` with an empty array. 404 means the endpoint itself doesn't exist, not that the query matched nothing.

- **Omitting `Retry-After` on 429 and 503.** Without it, clients guess a back-off interval and often choose wrong — either hammering the server or waiting too long. Always include the header.

- **Reusing 500 everywhere in server error handling.** When your gateway cannot reach an upstream, return 502 or 504. Operators and SREs read status codes to locate blame: 502/504 points to the upstream; 500 points to your service.

---

## Exercises

1. **Easy:** List the correct HTTP status code for each scenario: (a) a DELETE request succeeds with no body to return, (b) a user tries to access a resource they are not allowed to see, (c) a request body has a valid JSON structure but a field has an impossible value.

2. **Medium:** Design the full response for a `POST /payments` endpoint that triggers an asynchronous charge. Include the status code, required headers, and a sketch of the polling endpoint's response schema for `running`, `succeeded`, and `failed` states.

3. **Hard:** A CDN sits in front of your API. A bug causes your app to return `200 OK` with an error body instead of `503`. Trace the consequences through (a) the CDN cache, (b) the client retry logic, (c) the on-call alert pipeline. Then explain what you would have needed to return to make all three behave correctly.

---

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|------------------------|
| 401 Unauthorized | "The user is not authorized (wrong role)" | The request lacks valid authentication credentials — the user is not identified yet |
| 403 Forbidden | "The server is broken or down" | Authentication succeeded, but the caller does not have permission for this specific resource |
| 404 Not Found | "The server is hiding the resource" | The resource simply does not exist at this URI (can intentionally replace a 403 to hide existence) |
| 200 OK | "Request succeeded, everything is fine" | The HTTP exchange succeeded; the body may still describe a business-logic failure — parse it |
| 5xx | "The client did something wrong" | The server encountered a problem processing a request that appeared valid |
| 302 Found | "Resource moved permanently, update your links" | A temporary redirect — the original URL remains valid and should not be updated |
| 422 Unprocessable Entity | "Same as 400" | The request was syntactically valid but semantically invalid; preferred over 400 for domain validation errors |

---

## Further Reading

- [RFC 9110 — HTTP Semantics, Section 15: Status Codes](https://www.rfc-editor.org/rfc/rfc9110#section-15) — the authoritative specification; Section 15 covers every standardized code.
- [MDN Web Docs — HTTP response status codes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status) — well-organized reference with browser compatibility notes and usage guidance.
- [IANA HTTP Status Code Registry](https://www.iana.org/assignments/http-status-codes/http-status-codes.xhtml) — the official registry of all registered codes, including experimental and vendor extensions.
- [Google Cloud API Design Guide — Errors](https://cloud.google.com/apis/design/errors) — practical mapping of gRPC and HTTP status codes from a large-scale API producer.
- [Stripe API Reference — Errors](https://stripe.com/docs/api/errors) — a real-world example of clear, consistent HTTP status code usage in a production payment API.
