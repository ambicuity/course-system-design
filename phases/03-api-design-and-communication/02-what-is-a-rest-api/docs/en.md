# What is a REST API?

> REST turns the web's own architecture into a contract for building services that scale.

**Type:** Learn
**Prerequisites:** How the Internet Works, HTTP Basics
**Time:** ~25 minutes

---

## The Problem

You're building a mobile app, a web frontend, and a third-party partner integration — all of which need to read and write the same data. Without an agreed interface, each consumer forces you to write bespoke server-side code, coupling your backend to every client. Add a second backend team and you now have two people arguing over JSON shapes at 11 pm before a launch.

What you need is a stable, self-describing contract: a way for any client, written in any language, to discover and use your service without reading your source code. The contract must survive versioning, caching layers, and load balancers placed between client and server. And it should re-use infrastructure the industry already understands — HTTP verbs, status codes, URLs — rather than inventing a new protocol.

REST is that contract. It is not a protocol or a library. It is an architectural style — a set of constraints — that, when applied to HTTP, produces APIs that are predictable, scalable, and independently evolvable.

---

## The Concept

### What REST Actually Is

Roy Fielding defined REST in his 2000 PhD dissertation as six architectural constraints applied to a distributed hypermedia system. An API that satisfies all six is called "RESTful." Violating even one of the mandatory constraints puts you in the grey zone most real-world APIs actually occupy.

### The Six Constraints

| Constraint | Mandatory? | What it means |
|---|---|---|
| **Client–Server** | Yes | UI and data logic are separated. Clients do not connect to databases; servers do not render HTML. Each side evolves independently. |
| **Stateless** | Yes | Every request carries all context needed to serve it. The server holds zero per-session state between calls. Auth tokens, pagination cursors — all go in the request. |
| **Cacheable** | Yes | Responses must declare whether they are cacheable (`Cache-Control`, `ETag`, `Last-Modified`). Clients and intermediaries may reuse cached responses. |
| **Uniform Interface** | Yes | Four sub-constraints: resource identification via URI; manipulation through representations; self-descriptive messages; hypermedia as the engine of application state (HATEOAS). |
| **Layered System** | Yes | The client cannot tell whether it is talking to the origin server or an intermediary (CDN, load balancer, API gateway). Each layer only sees the next. |
| **Code on Demand** | No | The server may send executable code (e.g., JavaScript) to the client to extend its behaviour. Almost never used in practice. |

### Resources, Not Actions

The central shift REST forces: **model your domain as nouns (resources), not verbs (actions).**

```
# Non-RESTful (RPC-style)
POST /createUser
POST /deleteUser?id=42
GET  /getUserOrders?userId=42

# RESTful
POST   /users
DELETE /users/42
GET    /users/42/orders
```

A resource has a stable URI. HTTP verbs describe what to do with it.

### HTTP Verbs and Their Semantics

| Verb | Idempotent? | Safe? | Typical Use |
|---|---|---|---|
| `GET` | Yes | Yes | Fetch a resource or collection |
| `HEAD` | Yes | Yes | Same as GET, headers only |
| `POST` | No | No | Create a new resource |
| `PUT` | Yes | No | Replace a resource entirely |
| `PATCH` | No | No | Partial update |
| `DELETE` | Yes | No | Remove a resource |

**Safe** means no side effects. **Idempotent** means repeating the call produces the same server state. These properties matter for retry logic — a client can safely retry a `DELETE` on network failure; retrying a `POST` may create duplicates.

### A RESTful Request/Response Cycle

```
Client                           Server
  |                                |
  |  GET /users/42                 |
  |  Accept: application/json      |
  |  Authorization: Bearer <token> |
  | -----------------------------> |
  |                                |  Look up user 42
  |  HTTP/1.1 200 OK               |
  |  Content-Type: application/json|
  |  Cache-Control: max-age=60     |
  |  ETag: "a3f9b2"                |
  |                                |
  |  {                             |
  |    "id": 42,                   |
  |    "name": "Aisha",            |
  |    "email": "aisha@example.com"|
  |  }                             |
  | <----------------------------- |
```

Notice: the request is self-contained (auth header present), the response declares cacheability, and both sides use the standard Content-Type negotiation that HTTP already provides.

### Statelessness: The Performance / UX Trade-off

Statelessness enables horizontal scaling — any server in the pool can serve any request because no sticky sessions exist. The cost: clients must re-send auth credentials and context on every call, increasing payload size. Session-based auth trades this for server-side session storage, which does not survive server failures without external session stores (Redis, etc.). REST chooses client-side state; the scalability payoff is usually worth the overhead.

---

## Build It / In Depth

### A Minimal REST API in Python (FastAPI)

```python
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

# In-memory store (replace with a real DB)
users: dict[int, dict] = {}
next_id = 1


class UserCreate(BaseModel):
    name: str
    email: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None


@app.get("/users/{user_id}", status_code=200)
def get_user(user_id: int):
    if user_id not in users:
        raise HTTPException(status_code=404, detail="User not found")
    return users[user_id]


@app.post("/users", status_code=201)
def create_user(body: UserCreate):
    global next_id
    user = {"id": next_id, **body.model_dump()}
    users[next_id] = user
    next_id += 1
    return user


@app.patch("/users/{user_id}", status_code=200)
def update_user(user_id: int, body: UserUpdate):
    if user_id not in users:
        raise HTTPException(status_code=404, detail="User not found")
    for field, value in body.model_dump(exclude_none=True).items():
        users[user_id][field] = value
    return users[user_id]


@app.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int):
    users.pop(user_id, None)
```

Run it:

```bash
pip install fastapi uvicorn
uvicorn main:app --reload
```

Test it:

```bash
# Create
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"name":"Aisha","email":"aisha@example.com"}'

# Read
curl http://localhost:8000/users/1

# Partial update
curl -X PATCH http://localhost:8000/users/1 \
  -H "Content-Type: application/json" \
  -d '{"email":"new@example.com"}'

# Delete
curl -X DELETE http://localhost:8000/users/1
```

### Status Codes That Matter

```
2xx  Success
  200 OK           – successful GET, PUT, PATCH
  201 Created      – successful POST; include Location header
  204 No Content   – successful DELETE (no body)

4xx  Client error
  400 Bad Request  – malformed JSON, missing required field
  401 Unauthorized – no/invalid credentials
  403 Forbidden    – authenticated but not allowed
  404 Not Found    – resource doesn't exist
  409 Conflict     – e.g., duplicate email on create
  422 Unprocessable Entity – valid JSON but failed business validation

5xx  Server error
  500 Internal Server Error – unhandled exception
  503 Service Unavailable   – overloaded or in maintenance
```

Return the right code. A 200 with `{"success": false}` inside the body breaks every HTTP client, CDN, and monitoring tool that reads status codes.

---

## Use It

### Where REST Appears in Real Systems

| Context | How REST is used |
|---|---|
| **Public APIs** (Stripe, Twilio, GitHub) | The standard choice; well-understood by every developer |
| **Microservices (synchronous)** | Service-to-service calls where request/response fits the use case |
| **Mobile backends** | Stateless calls fit mobile network flakiness; caching reduces data usage |
| **Third-party integrations** | Webhooks and REST pairs are the default integration surface |
| **CDN + caching** | Cacheable GET responses served from edge nodes (CloudFront, Fastly) |

### REST vs. Alternatives

| | REST | GraphQL | gRPC |
|---|---|---|---|
| Transport | HTTP/1.1+ | HTTP/1.1+ | HTTP/2 |
| Schema | None (OpenAPI optional) | Strongly typed schema | Protobuf |
| Payload | JSON (usually) | JSON | Binary |
| Over/under-fetching | Common problem | Solved by design | N/A (method-level) |
| Browser support | Native | Native | Needs proxy |
| Best for | Public APIs, CRUD services | Complex clients, mobile | Internal high-throughput services |

Use REST as your default for public-facing APIs. Switch to GraphQL when mobile clients need precise field selection. Switch to gRPC for internal services where throughput and latency are critical.

---

## Common Pitfalls

- **Verbs in URLs.** `/createOrder`, `/deleteUser?id=5` — these are RPC, not REST. Use nouns and let the HTTP method carry the action. Every linter and API reviewer will flag this.

- **Wrong status codes.** Returning `200 OK` for a failed operation, or `500` for a bad client request, confuses every downstream consumer. Map your error conditions to the correct 4xx/5xx code.

- **Ignoring idempotency.** Using POST for operations that should be idempotent (like "set user email") means clients cannot safely retry. Prefer PUT or PATCH for updates and document retry semantics explicitly.

- **Treating statelessness as optional.** Storing user sessions in server memory and routing by sticky session breaks horizontal scaling. Any state that must survive a request must live in the client or in a shared external store (database, Redis).

- **Skipping cache headers.** Not setting `Cache-Control` on GET responses means CDNs and browsers cache nothing by default — or, worse, cache with unpredictable TTLs. Set explicit directives: `Cache-Control: max-age=300` for public data, `Cache-Control: no-store` for private/dynamic data.

---

## Exercises

1. **Easy — Map CRUD to REST.** Given a blog application with posts and comments, write out the full set of RESTful endpoints (method + URI) for: creating a post, listing all comments on a post, updating a comment, and deleting a post.

2. **Medium — Debug a broken API.** An API returns `200 OK` with body `{"error": "not found"}` when a user ID doesn't exist, and it uses `POST /getUserProfile` to fetch data. Identify every REST violation and rewrite the two endpoints correctly, including appropriate status codes.

3. **Hard — Design a stateless pagination scheme.** You have a `/products` endpoint returning 10,000 rows. Design a cursor-based pagination scheme that is stateless (no server-side session), cacheable, and handles the case where items are inserted between page fetches. Document the request/response shape, cursor encoding strategy, and which HTTP headers you'd set.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **REST** | A protocol or library | An architectural style — a set of six constraints on how to design a networked system |
| **RESTful** | Any API that uses HTTP | An API that satisfies all mandatory REST constraints, especially statelessness and uniform interface |
| **Resource** | A database table or row | Any named concept the API exposes; identified by a URI; can be a document, collection, or virtual concept |
| **Stateless** | The server has no memory | The server holds no per-client session state between requests; all context travels in each request |
| **Idempotent** | The same as "safe" | Repeating the operation produces the same server state; safe means no state change at all |
| **HATEOAS** | An obscure academic idea | Hypermedia as the Engine of Application State — responses include links to available next actions, making the API self-discoverable |
| **Representation** | The resource itself | The serialized form of a resource sent over the wire (JSON, XML, etc.); not the resource, just a view of it |

---

## Further Reading

- [Roy Fielding's original dissertation (Chapter 5 — REST)](https://www.ics.uci.edu/~fielding/pubs/dissertation/rest_arch_style.htm) — the authoritative source; dense but worth reading Chapter 5 at minimum.
- [MDN HTTP Methods reference](https://developer.mozilla.org/en-US/docs/Web/HTTP/Methods) — precise semantics for every HTTP verb, including idempotency and safety classification.
- [OpenAPI Specification (swagger.io)](https://swagger.io/specification/) — the standard for describing REST APIs in a machine-readable way; essential for tooling, code generation, and documentation.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) — the IETF standard defining status codes, headers, and method semantics that REST builds on.
- [Microsoft REST API Guidelines (GitHub)](https://github.com/microsoft/api-guidelines/blob/vNext/azure/Guidelines.md) — opinionated, production-tested REST design rules from a large engineering org; useful as a baseline for your own API style guide.
