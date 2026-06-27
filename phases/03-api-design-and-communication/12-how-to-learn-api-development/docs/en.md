# How to Learn API Development?

> APIs are the contracts that hold distributed systems together — learn to design them right and everything downstream gets easier.

**Type:** Learn
**Prerequisites:** HTTP and Web Fundamentals, REST vs GraphQL vs gRPC, Client-Server Architecture
**Time:** ~35 minutes

---

## The Problem

You land on a new backend service that needs to expose data to three consumers: a mobile app, a web frontend, and a third-party partner. You add a few endpoints, return JSON, and call it done. Six months later the mobile team is pinned to v1 because you changed a field name. The partner is hammering an endpoint with no rate limit and your database is on fire. The web team discovered that fetching a user's orders also returns every line item nested three levels deep — a 200 KB payload for a list view.

None of this is a technology failure. It is a knowledge gap. Knowing that HTTP verbs exist is not the same as knowing when to use `PATCH` vs `PUT`. Knowing that JWTs are tokens is not the same as understanding their expiry semantics and signing key rotation. Knowing that REST is "resource-based" is not the same as knowing how to version a resource without breaking clients.

API development is a discipline with a clear learning path. It spans fundamentals, request/response mechanics, authentication and security, design principles, testing, and production deployment. This lesson maps out that entire path — concretely, with the depth needed to avoid the mistakes above.

---

## The Concept

### What an API Actually Is

An API (Application Programming Interface) is a defined contract: *given input X, you will receive output Y, over channel Z*. The contract hides the implementation. The caller does not care whether your service runs on PostgreSQL or DynamoDB, whether it is written in Go or Python — it only cares that POST `/orders` with the right body creates an order.

APIs take many forms:

| Style | Transport | Primary Use Case | Data Format |
|-------|-----------|-----------------|-------------|
| REST | HTTP/1.1–2 | CRUD web services | JSON, XML |
| GraphQL | HTTP | Flexible data fetching, multiple clients | JSON |
| gRPC | HTTP/2 | High-throughput inter-service | Protobuf (binary) |
| WebSocket | TCP (upgraded HTTP) | Real-time, bidirectional | JSON, binary |
| SOAP | HTTP, SMTP | Legacy enterprise, WS-* tooling | XML |
| Webhook | HTTP (reverse) | Push event notifications | JSON |

REST is the dominant style for public APIs and you should learn it first. gRPC is the dominant style for internal microservice communication where performance matters. GraphQL is valuable when multiple client types have divergent data needs.

### The HTTP Layer

Every REST API runs over HTTP. You must know this layer cold.

```
Client                          Server
  |                               |
  |  GET /users/42 HTTP/1.1       |
  |  Host: api.example.com        |
  |  Authorization: Bearer <jwt>  |
  |  Accept: application/json     |
  |------------------------------>|
  |                               |  [Route match → handler]
  |  HTTP/1.1 200 OK              |  [DB query]
  |  Content-Type: application/json  [Serialize]
  |  Cache-Control: max-age=60    |
  |                               |
  |  {"id":42,"name":"Alice"}     |
  |<------------------------------|
```

**HTTP Methods — what each guarantees:**

| Method | Safe? | Idempotent? | Meaning |
|--------|-------|-------------|---------|
| GET | Yes | Yes | Retrieve a resource |
| HEAD | Yes | Yes | Retrieve headers only |
| POST | No | No | Create a new resource or trigger action |
| PUT | No | Yes | Replace a resource entirely |
| PATCH | No | No* | Partially update a resource |
| DELETE | No | Yes | Remove a resource |

*PATCH can be made idempotent if you use conditional request semantics (ETags), but it is not guaranteed by the spec.

**Status Codes — the ones you must memorize:**

| Range | Meaning | Key codes |
|-------|---------|-----------|
| 2xx | Success | 200 OK, 201 Created, 204 No Content |
| 3xx | Redirect | 301 Moved Permanently, 304 Not Modified |
| 4xx | Client error | 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 409 Conflict, 422 Unprocessable Entity, 429 Too Many Requests |
| 5xx | Server error | 500 Internal Server Error, 502 Bad Gateway, 503 Service Unavailable |

The most misused: **401 vs 403**. 401 means "I don't know who you are — authenticate first." 403 means "I know exactly who you are, and you are not allowed to do this."

### Authentication and Security

Authentication answers *who are you?* Authorization answers *what are you allowed to do?*. Mix them up and you get security holes.

**The four main mechanisms:**

```
API Key             — Long-lived secret, sent in header or query param.
                      Simple but coarse-grained; rotate manually.

Basic Auth          — base64(username:password) in Authorization header.
                      Only acceptable over TLS; effectively deprecated for APIs.

JWT (Bearer Token)  — Signed, self-contained token. Server can verify without
                      a database lookup. Expiry is baked in. Key rotation is
                      the hard part.

OAuth 2.0           — A delegated authorization framework. The user grants a
                      third party access to their resources without sharing
                      a password. Built on access tokens + refresh tokens.
```

**JWT anatomy:**

```
header.payload.signature

header:  {"alg":"HS256","typ":"JWT"}
payload: {"sub":"42","role":"admin","exp":1756000000}
sig:     HMAC-SHA256(base64(header) + "." + base64(payload), secret)
```

The server validates the signature. If the signature checks out, it trusts the payload — no database round-trip. The risk: if the secret leaks, all tokens are compromised until you rotate the key and invalidate existing tokens.

**Security checklist every API must pass:**

- TLS everywhere — never accept credentials over plain HTTP
- Input validation on every field — type, length, allowed characters
- Rate limiting — per IP, per API key, per user
- No sensitive data in URLs (they appear in server logs and browser history)
- CORS configured to an explicit allowlist, not `*`
- Secrets in environment variables, never in code

### RESTful Design Principles

Good REST API design is mostly about being boring and consistent.

**Resources over verbs in URLs:**

```
Bad:  GET /getUser?id=42
      POST /createOrder
      POST /deleteProduct/5

Good: GET  /users/42
      POST /orders
      DELETE /products/5
```

**Versioning — three strategies:**

```
URI versioning:     /v1/users, /v2/users          — most explicit, easiest to route
Header versioning:  Accept: application/vnd.api+json;version=2
Query param:        /users?version=2              — acceptable, pollutes query string
```

URI versioning wins in practice because it is cache-friendly and immediately obvious in logs and documentation.

**Pagination — two approaches:**

```
Offset-based:
  GET /orders?limit=20&offset=40
  Cheap to implement. Breaks when records are inserted/deleted mid-page.

Cursor-based:
  GET /orders?limit=20&after=cursor_opaque_xyz
  Consistent under mutations. Required for infinite-scroll feeds.
  Cursor encodes position (e.g., last seen ID or timestamp), base64-encoded.
```

**Response envelope pattern:**

```json
{
  "data": [...],
  "meta": {
    "total": 243,
    "page": 2,
    "per_page": 20
  },
  "error": null
}
```

Wrap all responses in a consistent shape. When errors occur, `data` is null and `error` contains a code and message. Clients write one error handler, not one per endpoint.

### Documentation as a Contract

OpenAPI (formerly Swagger) lets you describe your API in a YAML/JSON schema. From that schema you get: auto-generated interactive docs, auto-generated client SDKs, server stub generation, and contract testing. Write the spec *before* you write the code — it forces you to think through the contract without being distracted by implementation.

---

## Build It / In Depth

### Step 1 — Bare HTTP server with correct status codes

```python
# Python + FastAPI (auto-generates OpenAPI spec)
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

app = FastAPI(title="Orders API", version="1.0.0")

class OrderCreate(BaseModel):
    product_id: int
    quantity: int

ORDERS: dict[int, dict] = {}
_counter = 0

@app.post("/v1/orders", status_code=status.HTTP_201_CREATED)
def create_order(body: OrderCreate):
    global _counter
    _counter += 1
    order = {"id": _counter, "product_id": body.product_id, "quantity": body.quantity}
    ORDERS[_counter] = order
    return order

@app.get("/v1/orders/{order_id}")
def get_order(order_id: int):
    if order_id not in ORDERS:
        raise HTTPException(status_code=404, detail="Order not found")
    return ORDERS[order_id]
```

### Step 2 — Add authentication middleware

```python
from fastapi import Depends, Header
import jwt  # PyJWT

SECRET = "change-me-in-production"

def require_auth(authorization: str = Header(...)):
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        return payload  # contains {"sub": user_id, ...}
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or missing token")

@app.get("/v1/orders/{order_id}")
def get_order(order_id: int, user=Depends(require_auth)):
    # user is now the decoded JWT payload
    if order_id not in ORDERS:
        raise HTTPException(status_code=404, detail="Order not found")
    return ORDERS[order_id]
```

### Step 3 — Add pagination

```python
from fastapi import Query

@app.get("/v1/orders")
def list_orders(
    limit: int = Query(default=20, ge=1, le=100),
    after: int = Query(default=0, ge=0),
    user=Depends(require_auth),
):
    all_orders = sorted(ORDERS.values(), key=lambda o: o["id"])
    page = [o for o in all_orders if o["id"] > after][:limit]
    next_cursor = page[-1]["id"] if len(page) == limit else None
    return {
        "data": page,
        "meta": {"limit": limit, "next_cursor": next_cursor},
        "error": None,
    }
```

### Step 4 — Test it with cURL and validate the spec

```bash
# Start the server
uvicorn main:app --reload

# Create an order (should return 201)
curl -s -w "\nStatus: %{http_code}\n" \
  -X POST http://localhost:8000/v1/orders \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_jwt>" \
  -d '{"product_id": 7, "quantity": 3}'

# Fetch with pagination
curl -s "http://localhost:8000/v1/orders?limit=5&after=0" \
  -H "Authorization: Bearer <your_jwt>"

# View auto-generated OpenAPI spec
curl http://localhost:8000/openapi.json

# Interactive docs
open http://localhost:8000/docs
```

### Step 5 — Rate limiting at the gateway level

```yaml
# Kong declarative config (deck format)
plugins:
  - name: rate-limiting
    config:
      minute: 60         # 60 requests per minute per consumer
      policy: local
      error_message: "Rate limit exceeded. Retry after 60 seconds."
```

Add rate limiting at the API gateway, not inside every service. The gateway returns `429 Too Many Requests` with a `Retry-After` header before the request even reaches your service.

---

## Use It

| Technology | Role | When to use it |
|------------|------|---------------|
| **FastAPI** (Python) | API framework | Rapid development, automatic OpenAPI, async support |
| **Express / Fastify** (Node) | API framework | JavaScript ecosystem, high-throughput I/O |
| **Spring Boot** (Java) | API framework | Enterprise, heavy ecosystem, strong typing |
| **OpenAPI / Swagger** | API specification | Design-first contracts, docs, SDK generation |
| **Postman / Insomnia** | API testing client | Manual exploration, collection-based testing |
| **cURL / HTTPie** | CLI testing | Scripting, quick checks, CI pipelines |
| **AWS API Gateway** | Managed gateway | Auth, throttling, Lambda integration, low ops overhead |
| **Kong** | Self-hosted gateway | Plugin ecosystem, fine-grained routing, on-prem control |
| **Apigee (Google)** | Enterprise gateway | Analytics, monetization, large org governance |
| **Stripe API** | Third-party example | Idiomatic REST, excellent versioning, webhook model |
| **Twilio / SendGrid** | Third-party example | Consuming external APIs with SDK wrappers |

**Decision rule for API style:**

```
Public API or multiple unrelated clients?     → REST
Mobile + web with very different data needs?  → GraphQL
Internal microservices, high throughput?      → gRPC
Real-time events (chat, live updates)?        → WebSocket + REST hybrid
Push notifications from external services?    → Webhooks
```

---

## Common Pitfalls

- **Returning 200 for every response, including errors.** Some teams return `{"success": false, "error": "not found"}` with HTTP 200. This breaks HTTP caching, monitoring alerts, and client error handling. Use the correct 4xx/5xx status codes — they are there for a reason.

- **Ignoring idempotency on POST.** Network retries happen. If a client POSTs to `/orders` and gets a timeout, it retries — and you now have two orders. Require an idempotency key header (`Idempotency-Key: <uuid>`) and cache the first response keyed to it.

- **Embedding IDs in URLs that change.** If `/users/alice@example.com` is a valid URL and the user changes their email, every bookmarked URL breaks. Use stable internal IDs in URLs; expose human-friendly identifiers only in the response body.

- **Over-nesting resources.** `/companies/5/departments/12/employees/99/projects/3` is unnavigable. Flatten where possible: `/projects/3`. Keep nesting to one level max: `/departments/12/employees` is fine.

- **Returning the entire entity on every mutation.** A PATCH to update a single field should not return a 5 KB object with every related entity. Return only the updated resource, or 204 with no body. Let the client decide when it needs the full representation.

- **No versioning strategy from day one.** Adding versioning after you have clients is painful. Start with `/v1/` in the path from the first public endpoint, even if you never release a v2. The cost is zero; the regret of skipping it is high.

---

## Exercises

1. **Easy — status codes drill.** Without looking at the reference, write down the correct HTTP status code for each scenario: (a) resource created successfully, (b) client sent malformed JSON, (c) user is logged in but not allowed to view that resource, (d) the endpoint no longer exists and never will, (e) your service is temporarily down for maintenance. Check against the table in The Concept section.

2. **Medium — design a pagination scheme.** You are building a feed of tweets sorted by recency. Tweets are inserted continuously. A user is on page 3 (offset 40). Ten new tweets are posted. Explain why offset pagination breaks here and design a cursor-based alternative. What does the cursor encode? What does the client send on the next request? Write out the request/response cycle for two consecutive pages.

3. **Hard — secure a webhook endpoint.** You integrate with Stripe and want to receive payment events. Stripe sends a POST request to your URL with an event payload. The problem: anyone on the internet can POST to your URL and fake a payment event. Research Stripe's webhook signature verification mechanism, implement it in any language of your choice, and write a test that (a) accepts a correctly signed payload and (b) rejects a tampered one.

---

## Key Terms

| Term | What people think | What it actually means |
|------|------------------|----------------------|
| **REST** | "JSON over HTTP" | An architectural style with constraints: statelessness, uniform interface, resource identification via URI, representation-based interaction. A JSON API that breaks statelessness or uses RPC-style URLs is not REST. |
| **Idempotent** | "Same request, same result every time" | Applying the operation N times produces the same *server state* as applying it once. GET and DELETE are idempotent; POST is not. The *response* may differ (a second GET could return 404 if deleted in between). |
| **JWT** | "A secure session cookie replacement" | A *self-contained*, *signed* token. The server trusts the payload without a DB lookup because the signature proves the server issued it. It is not encrypted by default — the payload is base64-encoded and readable by anyone. |
| **OAuth 2.0** | "OAuth is how you log in with Google" | OAuth 2.0 is an *authorization* framework, not authentication. It lets users grant limited access to their data at one service to another service. OpenID Connect (OIDC) adds identity on top of OAuth 2.0. |
| **API Gateway** | "A fancy reverse proxy" | A layer that handles cross-cutting concerns — authentication, rate limiting, request routing, SSL termination, analytics — before requests reach your backend services. It is the front door of your API surface. |
| **Idempotency Key** | "A request ID" | A client-generated unique key sent with a request. The server caches the response keyed to it. If the same key arrives again (retry), the server returns the cached response without re-executing the operation. Critical for safe retries on non-idempotent operations. |
| **OpenAPI** | "Swagger docs" | A language-agnostic specification format (YAML/JSON) for describing REST APIs — endpoints, request/response schemas, auth mechanisms. Formerly called Swagger. The spec is the source of truth; documentation and SDKs are generated from it. |

---

## Further Reading

- **OpenAPI Specification** — The authoritative spec and tooling ecosystem: https://spec.openapis.org/oas/latest.html
- **Roy Fielding's REST Dissertation (Chapter 5)** — The original definition of REST constraints, still the clearest source: https://ics.uci.edu/~fielding/pubs/dissertation/rest_arch_style.htm
- **Stripe API Reference** — The industry standard for what a well-designed REST API documentation looks like: https://stripe.com/docs/api
- **OAuth 2.0 RFC 6749** — The spec itself is readable and clarifies the flows better than most tutorials: https://datatracker.ietf.org/doc/html/rfc6749
- **API Security Checklist** (shieldfy/API-Security-Checklist on GitHub) — A practical, checklist-driven security reference covering auth, input validation, transport, and output: https://github.com/shieldfy/API-Security-Checklist
