# REST API Vs. GraphQL

> Choose the contract that matches your data-access pattern, not your hype cycle.

**Type:** Learn
**Prerequisites:** HTTP and Web Fundamentals, API Design Principles, Introduction to System Design
**Time:** ~35 minutes

---

## The Problem

You're building a social-feed product. The mobile client needs a user's name, avatar, and the titles of their last five posts. Your REST API has a `/users/{id}` endpoint that returns 40 fields — bio, email, phone, account settings — and a separate `/users/{id}/posts` endpoint that returns full post objects including body text, tags, and metadata. The mobile client fires two requests, discards 90% of the data, and users in low-bandwidth regions see a 3-second load time.

Six months later, the product team adds a "stories" feature. Every team that touches the frontend has to coordinate with the backend team to get a new `/users/{id}/stories` endpoint shipped and deployed before they can build the UI. Meanwhile, a different team is building an analytics dashboard that needs to join users, posts, and engagement metrics — so they hit three separate endpoints, stitch the responses in JavaScript, and pray the three calls return in a consistent order.

This is the core tension: **REST organizes APIs around resources; clients organize their needs around use-cases.** When the two don't align — and they rarely align permanently — you end up with over-fetching (getting data you don't need), under-fetching (needing multiple roundtrips), or an explosion of purpose-built endpoints that become hard to maintain. GraphQL was designed to close that gap. Understanding when it does and when REST is still the right tool is a foundational system-design decision.

---

## The Concept

### REST: Resources, Verbs, and Contracts

REST (Representational State Transfer) maps HTTP semantics onto resources. Each URL identifies a noun; the HTTP method expresses the operation.

```
GET    /articles/42          → fetch article 42
POST   /articles             → create a new article
PUT    /articles/42          → replace article 42
PATCH  /articles/42          → partial update
DELETE /articles/42          → remove article 42
```

The design bets that resources are stable, versioned contracts — a `/users` response looks the same whether the caller is a mobile app, a CLI tool, or another service. HTTP caching (ETags, `Cache-Control`) works naturally at the URL level. Load balancers, CDNs, and reverse proxies understand GET vs. POST semantics without inspecting request bodies.

**What REST does well:**

| Strength | Why |
|---|---|
| HTTP caching | GET responses cache by URL natively; CDN-friendly |
| Uniform interface | Any HTTP client can consume without a custom library |
| Statelessness | Each request carries full context; horizontal scaling is trivial |
| Debuggability | `curl`, browser dev tools, Postman — no special tooling |
| Mature ecosystem | Middleware, rate limiters, API gateways understand HTTP natively |

**Where REST bends:**

- **Over-fetching:** The endpoint contract returns a fixed shape; clients take what they get.
- **Under-fetching:** Related data lives on different endpoints; N resources require N round-trips.
- **Chatty mobile UIs:** Each screen often needs data from multiple domain models.
- **Rapid schema evolution:** New frontend needs often require new backend endpoints or query parameters.

### GraphQL: A Query Language for Your API

GraphQL replaces the collection-of-endpoints model with a **typed schema** and a **single endpoint** (`/graphql`). Clients send a query document describing exactly what they need; the server resolves only those fields.

```
POST /graphql
{
  user(id: "42") {
    name
    avatar
    posts(last: 5) {
      title
    }
  }
}
```

The server returns exactly:

```json
{
  "data": {
    "user": {
      "name": "Ada",
      "avatar": "https://cdn.example.com/ada.png",
      "posts": [
        { "title": "Distributed Locks" },
        { "title": "CAP Theorem" }
      ]
    }
  }
}
```

No second request. No unused fields. The schema defines what's possible; the query defines what's needed.

**Three root operation types:**

| Operation | Purpose | Example |
|---|---|---|
| `query` | Read data (idempotent) | Fetch user profile |
| `mutation` | Write data | Create post, update settings |
| `subscription` | Real-time stream over WebSocket | Live comment feed |

### Architecture Comparison

```
REST                              GraphQL
─────────────────────────────     ─────────────────────────────
Client                            Client
  │                                 │
  ├─ GET /users/42                  └─ POST /graphql
  ├─ GET /users/42/posts                  { user(id:"42") {
  └─ GET /users/42/stories                  name posts { title }
       │                                  } }
       │                                  │
  [3 round-trips]                   [1 round-trip]
       │                                  │
  Backend Services              GraphQL Server (resolvers)
  ┌──────────────┐               ┌────────────────────────────┐
  │ User Service │               │ userResolver → User Svc    │
  │ Post Service │               │ postsResolver → Post Svc   │
  │ Story Svc    │               │ storiesResolver → Story Svc│
  └──────────────┘               └────────────────────────────┘
```

The GraphQL server is itself a **data-aggregation layer**. Each field in the schema is backed by a *resolver function* — a small piece of code that knows how to fetch that piece of data (from a database, another microservice, a cache, etc.).

### How Resolvers Execute

When the server receives a query, it parses the document into an AST, validates it against the schema, and then walks the tree calling resolvers depth-first:

```
query
 └─ user(id: "42")        → calls userResolver  (DB call)
      ├─ name              → value from user object
      ├─ avatar            → value from user object
      └─ posts(last: 5)   → calls postsResolver (DB call)
           └─ title        → value from each post object
```

Without optimization, this triggers the **N+1 problem**: if you query 10 users with their posts, `postsResolver` fires once per user. The solution is **DataLoader** — a batching utility that coalesces individual resolver calls into a single bulk query per tick of the event loop.

### Caching Trade-offs

REST caching is HTTP-native: GET requests to the same URL return the same response; CDNs and proxies cache automatically. GraphQL uses a single POST endpoint, so HTTP caching doesn't apply at the transport level. Instead, GraphQL relies on:

- **Client-side normalized caches** (Apollo Client, urql) that store objects by ID and deduplicate across queries.
- **Persisted queries** — pre-registered query hashes that allow GET-based caching.
- **CDN caching with persisted queries + GET** — effectively restoring HTTP caching semantics.

---

## Build It / In Depth

### Scenario: Product Feed API

You have products with categories. Compare how each approach handles "give me name, price, and category name for the first 10 products."

**REST approach — two requests:**

```bash
# 1. Fetch products (returns id, name, price, categoryId, description, sku, stock, ...)
curl https://api.shop.com/products?page=1&limit=10

# 2. For each unique categoryId, fetch category name
curl https://api.shop.com/categories/7
curl https://api.shop.com/categories/3
# ... up to N more calls
```

**REST approach — solve with a custom endpoint:**

```bash
# Bespoke endpoint for this exact screen
curl https://api.shop.com/products/summary?limit=10
# Returns only: { id, name, price, categoryName }
```

Every new client need risks a new endpoint. The API becomes a collection of use-case-specific routes.

**GraphQL approach — one request, exact shape:**

```graphql
# Schema (defined once on the server)
type Product {
  id: ID!
  name: String!
  price: Float!
  sku: String
  description: String
  category: Category!
}

type Category {
  id: ID!
  name: String!
}

type Query {
  products(limit: Int, offset: Int): [Product!]!
}
```

```graphql
# Query sent by the client
query ProductFeed {
  products(limit: 10) {
    name
    price
    category {
      name
    }
  }
}
```

```python
# Server-side resolver (Python / Strawberry example)
@strawberry.type
class Query:
    @strawberry.field
    def products(self, limit: int = 10, offset: int = 0) -> list[Product]:
        return db.query(ProductModel).limit(limit).offset(offset).all()

# Category resolver with DataLoader batching
async def load_categories(category_ids: list[int]) -> list[Category]:
    rows = db.query(CategoryModel).filter(CategoryModel.id.in_(category_ids)).all()
    lookup = {r.id: r for r in rows}
    return [lookup.get(cid) for cid in category_ids]
```

The single GraphQL query fires one SQL for products and one batched SQL for categories — regardless of how many products are returned.

### Adding a Mutation and Subscription

```graphql
type Mutation {
  createProduct(input: ProductInput!): Product!
}

type Subscription {
  productCreated: Product!
}
```

```graphql
# Client creates a product
mutation {
  createProduct(input: { name: "Widget", price: 9.99, categoryId: "3" }) {
    id
    name
  }
}

# Client subscribes to real-time new products (over WebSocket)
subscription {
  productCreated {
    id
    name
    price
  }
}
```

REST would require polling (`GET /products?after=<timestamp>`) or a separate WebSocket/SSE channel disconnected from the API contract. GraphQL unifies all three interaction modes under one schema.

---

## Use It

### When to Choose REST

| Signal | Reason |
|---|---|
| Public API consumed by unknown clients | Stable URL contracts, curl-friendly, no client library needed |
| Heavy CDN/proxy caching required | HTTP GET caching works natively by URL |
| Simple CRUD service | No aggregation needed; resource = use-case |
| Teams strongly invested in HTTP tooling | API gateways, rate limiters, WAFs understand HTTP semantics |
| File uploads / binary streaming | HTTP multipart, range requests, streaming are native to REST |

**Examples:** GitHub REST API, Stripe API, AWS S3 REST API, Twilio, most payment providers.

### When to Choose GraphQL

| Signal | Reason |
|---|---|
| Multiple client types with different data needs | Mobile, web, and partner can query the same schema differently |
| Complex nested data across multiple services | Single query replaces N REST calls |
| Rapid frontend iteration | Frontend can request new field combinations without backend deploys |
| Real-time requirements alongside queries | Subscriptions unify query and streaming under one schema |
| Internal / BFF (Backend For Frontend) layer | Not a public API; controlled client set |

**Examples:** GitHub GraphQL API v4, Shopify Storefront API, Facebook's internal systems, Twitter API (partial), Airbnb, Netflix internal tooling.

### Hybrid: GraphQL as a BFF Over REST Microservices

A common production pattern keeps REST microservices internally and adds a GraphQL gateway as the client-facing layer:

```
Mobile App / Web App
        │
        ▼
  GraphQL Gateway  (Apollo Federation, Hasura, StepZen)
   ├─ Resolver → User Service (REST)
   ├─ Resolver → Product Service (REST / gRPC)
   └─ Resolver → Order Service (REST)
```

This lets teams keep their well-understood REST services and still give frontends a flexible, type-safe query interface.

### Tooling Snapshot

| Tool | REST | GraphQL |
|---|---|---|
| OpenAPI / Swagger | Native spec | Via third-party adapters |
| Postman | First-class | Supported |
| Apollo Client | — | Primary client library |
| urql | — | Lightweight client |
| Hasura | — | Auto-generates from Postgres |
| Kong / AWS API Gateway | Native | Passthrough only |
| Introspection / schema docs | Manual (OpenAPI) | Built into the protocol |

---

## Common Pitfalls

- **Ignoring the N+1 problem in GraphQL.** Every nested list resolver can trigger one query per parent item. Always use DataLoader (or equivalent batching) for any resolver that could be called in a loop. Skipping this turns a "10 products" query into 11 database calls.

- **Treating GraphQL as a silver bullet for microservices.** GraphQL solves the "shape mismatch between client and API" problem, not the "service orchestration" problem. If your resolvers call 10 services sequentially, you've just moved the round-trip problem into your resolvers.

- **Exposing an unrestricted GraphQL API publicly.** Without query depth limits, complexity limits, and rate limiting, a single deeply nested query can bring down your server. Use libraries like `graphql-depth-limit` and `graphql-query-complexity` before going public.

- **Abandoning HTTP caching entirely in GraphQL.** Defaulting to POST requests for all queries throws away CDN caching. Use persisted queries with GET for cacheable reads, or add a server-side query result cache (Redis) keyed by query hash + variables.

- **Versioning REST APIs with URL segments without planning ahead.** `/v1/`, `/v2/` in URLs signals contract breakage. Consider using content negotiation (`Accept` header) or additive, backward-compatible field additions. Forcing `/v2/` for every new field is maintenance overhead that often drives teams toward GraphQL unnecessarily — many REST APIs can stay on v1 far longer with disciplined additive design.

---

## Exercises

1. **Easy:** Take a REST endpoint like `GET /orders/{id}` that returns an order with customer, items, and shipping fields. Sketch the equivalent GraphQL schema types and a query that fetches only the customer name and item titles. Identify which fields are over-fetched by the REST endpoint in a typical "order summary" view.

2. **Medium:** You have three microservices — Users, Posts, and Comments — each with REST APIs. Design a GraphQL schema that lets a client fetch "the display name and avatar of a user, their last 3 posts with title, and the top comment on each post" in a single query. Write the resolver functions in pseudocode and identify where you would add DataLoader batching.

3. **Hard:** A startup is building an e-commerce platform with a public API (to be consumed by third-party integrators) and an internal BFF for their own mobile app. Propose a hybrid architecture: decide which layer uses REST and which uses GraphQL, justify the boundary, explain how caching is handled at each layer, and describe how you would handle schema evolution without breaking existing integrators.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Over-fetching** | "Getting too much data is fine; bandwidth is cheap" | Receiving fields the client doesn't use wastes bandwidth, parse time, and serialization overhead — critical on mobile and high-frequency endpoints |
| **Under-fetching** | "Just make one more request" | Each additional round-trip adds latency; on mobile with 100ms RTT, five round-trips cost 500ms before any business logic runs |
| **Resolver** | "A controller that handles a GraphQL query" | A per-field function that knows how to fetch one piece of data; the engine calls the correct resolver for each field in the query tree |
| **DataLoader** | "A caching layer" | A batching utility that collects individual resolver calls across one event-loop tick and issues a single bulk query — solving N+1 without manual join logic |
| **Persisted Query** | "A stored procedure for GraphQL" | A pre-registered query identified by hash; the client sends `?queryId=abc&variables=...` enabling GET-based HTTP caching for GraphQL |
| **Schema Introspection** | "Documentation generation" | A built-in GraphQL feature where clients can query the schema itself (`__schema`, `__type`) to discover available types and fields at runtime |
| **BFF (Backend For Frontend)** | "A microservice for the UI team" | A purpose-built API layer shaped around one client's exact needs; often implemented in GraphQL to avoid the mismatch between generic services and specific UI requirements |

---

## Further Reading

- **GraphQL specification** — The authoritative source for query syntax, type system, and execution semantics: [https://spec.graphql.org](https://spec.graphql.org)
- **Apollo GraphQL documentation** — Production guidance on schema design, resolvers, DataLoader, and caching: [https://www.apollographql.com/docs](https://www.apollographql.com/docs)
- **"REST vs GraphQL" — Phil Sturgeon's field notes** — A balanced practitioner comparison from someone who has shipped both at scale: [https://apisyouwonthate.com/blog/rest-and-graphql](https://apisyouwonthate.com/blog/rest-and-graphql)
- **DataLoader (GitHub)** — The canonical batching library; reading the README explains the N+1 problem and the batching solution precisely: [https://github.com/graphql/dataloader](https://github.com/graphql/dataloader)
- **"Designing APIs with Swagger and OpenAPI"** — O'Reilly book covering REST contract design, versioning strategy, and tooling; a practical counterpart to GraphQL schema design: [https://www.oreilly.com/library/view/designing-apis-with/9781617296284](https://www.oreilly.com/library/view/designing-apis-with/9781617296284)
