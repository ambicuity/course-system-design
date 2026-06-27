# Design a Proximity Service

A proximity service answers the question: "What businesses are near me?" It powers Yelp-style discovery, "restaurants near me," store locators, and the backend of many location features. The technical heart of the problem is the **geospatial index** — a data structure that lets you find points within a radius of a location without scanning every record on Earth.

---

## Step 1 — Understand the Problem & Establish Scope

### Clarifying questions

- What does "nearby" mean — a fixed radius (e.g., 5 km) or the nearest *k* results?
- Can the **search radius** change? Yes — users may widen/narrow the search.
- What's the **business count**? E.g., 200M businesses worldwide.
- What's the **query volume**? E.g., 5,000 searches/sec — read-heavy.
- Do business locations change often? Rarely — businesses are mostly static (added/edited/removed occasionally), unlike moving users.
- Do we return business details too, or just IDs? Both: find nearby IDs, then fetch details.

### Functional requirements

1. **Return businesses within a given radius** of a user's location (lat/long).
2. Business owners can **add, update, delete** businesses (not reflected in real time — eventual consistency is fine).
3. Users can **view detailed information** about a business.

### Non-functional requirements

- **Low latency** — users expect fast results.
- **High availability** — handle traffic spikes (lunchtime, events).
- **Scalability** — 200M businesses, billions of lookups.
- **Read-heavy** — far more searches than writes; optimize the read path. This is a defining property: business data is relatively static, so we can precompute and heavily cache the spatial index.

### Back-of-envelope estimation

- Businesses: ~200M.
- Search QPS: ~5,000/sec (reads dominate).
- Each search reads a small set of nearby candidates, so per-query work must be tiny — we cannot scan 200M rows per request. The index is everything.

---

## Step 2 — Propose High-Level Design & Get Buy-In

### High-level architecture

Two logically separate services behind a load balancer:

```
                    ┌─────────────────┐
   Users ──► LB ──► │  LBS (Location-  │ ──► Geospatial index / cache
   (search)         │  Based Service)  │      (read-only, replicated)
                    └─────────────────┘
                    ┌─────────────────┐
 Owners ──► LB ──►  │ Business Service │ ──► Business DB (primary + replicas)
 (CRUD)             └─────────────────┘
```

- **Location-Based Service (LBS)** — the **read-heavy core**. Given a location and radius, it returns nearby business IDs using the geospatial index. It is **stateless** and read-only (no writes), so it scales horizontally with ease and can be aggressively cached.
- **Business Service** — handles **owner CRUD** (add/update/delete business) and **serving business details** to users. Writes go here.

Separating these matters because their access patterns differ wildly: LBS is high-QPS read-only; Business Service is write-capable but low-volume. Decoupling lets each scale on its own profile.

### The core challenge: indexing geospatial data

A naive approach — store `(lat, long)` and run `SELECT ... WHERE distance(loc, :me) < :r` — forces a **full table scan** because the two coordinates are independent dimensions; a standard B-tree index on `lat` and another on `long` can't efficiently answer a 2D range/radius query. We need a **geospatial index** that maps 2D space onto something indexable.

Main families of solutions:

1. **Even/uniform grids** — divide the world into fixed-size cells.
2. **Geohash** — recursively divide the world into 4 quadrants, encoding each cell as a string.
3. **Quadtree** — an in-memory tree that adaptively subdivides dense regions.
4. **Google S2 / Hilbert curve** — maps 2D to 1D along a space-filling curve.

### Approach 1 — Evenly divided grid

Split the map into fixed-size squares. Problem: **uneven distribution** — Manhattan has thousands of businesses per cell while a desert has none. Fixed cells either overload dense areas or waste space. This motivates *adaptive* schemes.

### Approach 2 — Geohash (recommended baseline)

**Geohash** recursively bisects the world into 4 quadrants and encodes the path as a base-32 string. Each added character refines the cell (smaller area, higher precision).

- A geohash is a **prefix code**: nearby locations usually share a **common prefix**. `9q8yy` and `9q8yz` are adjacent-ish; the longer the shared prefix, the closer they are.
- **Precision vs length:**

| Geohash length | Approx cell size |
|---|---|
| 4 | ~39 km × 20 km |
| 5 | ~5 km × 5 km |
| 6 | ~1.2 km × 0.6 km |
| 7 | ~150 m × 150 m |

- **Query pattern:** convert the user's location to a geohash at the precision matching the search radius, then `SELECT * FROM geohash_index WHERE geohash LIKE '9q8yy%'`. A prefix match becomes a fast B-tree range scan on a single string column — exactly what databases are good at.

**Edge cases to address (important deep-dive points):**

- **Boundary problem:** two very close points can fall in adjacent cells with *different* prefixes (e.g., right at a quadrant border). Fix by also querying the **8 neighboring geohashes** around the center cell, then filtering by true distance.
- **Not enough results:** if a precise geohash returns too few businesses, **remove the last character** (zoom out one level) to widen the search until enough candidates are found.

### Approach 3 — Quadtree

A **quadtree** is an in-memory tree that recursively subdivides space, but **adaptively**: a node splits into 4 children only when it holds more than a threshold number of businesses. Dense areas get deep subdivision; sparse areas stay shallow.

- **Build:** start with the whole world at the root; recursively split any node exceeding the capacity (e.g., 100 businesses) until leaves are small enough.
- **Query:** traverse from the root to the leaf containing the user, collect businesses in that leaf and neighboring leaves within the radius.
- **Trade-offs:** memory-resident (fast, but must fit in RAM and be rebuilt on startup); building the tree for 200M points takes time and memory; updates require rebalancing. A typical quadtree of hundreds of millions of points still fits comfortably in a few GB of RAM per server.

### Approach 4 — Google S2 / Hilbert curve

Maps the sphere to a 1D index along the **Hilbert space-filling curve**, so points close in 2D are usually close in 1D. Great for **region coverage** queries and used by Google Maps. More complex; worth naming as an alternative, especially for arbitrary-shaped region queries.

### Redis Geo — a practical off-the-shelf option

**Redis GEO** commands (`GEOADD`, `GEOSEARCH`/`GEORADIUS`) implement geohashing on a **sorted set** internally: the 52-bit geohash is the score, and Redis range-scans it. For many real systems this is the pragmatic choice — it gives an in-memory geospatial index with radius queries out of the box, easily replicated for read scaling.

---

## Step 3 — Design Deep Dive

### Data model

**Business table** (source of truth, in a relational DB):

| Column | Type |
|---|---|
| business_id (PK) | bigint |
| name | varchar |
| address, city, country | varchar |
| latitude, longitude | double |
| category, hours, … | various |

**Geospatial index table** (geohash approach):

| Column | Type | Notes |
|---|---|---|
| geohash | varchar | indexed; e.g., length 6 |
| business_id | bigint | FK to business |

Index on `geohash` enables prefix range scans. One business maps to one (or, for robustness, several precision-level) geohash rows.

### Read path (search)

1. User sends `(lat, long, radius)`.
2. LBS computes the geohash prefix for that radius and queries the index (plus the 8 neighbors).
3. Returns candidate `business_id`s.
4. Optionally re-rank/filter by **true geodesic distance** (Haversine) and radius, since cells are approximate.
5. Hydrate details from the Business Service / business DB (often cached).

### Scaling the read path

- The geospatial **index is small and read-only**, so **replicate it widely** and cache it. Reads scale by adding read replicas / cache nodes behind the LBS.
- **Cache** the index in Redis; cache popular business details. Because business data changes rarely, cache hit rates are very high and TTLs can be long.
- LBS is **stateless** → autoscale horizontally behind the load balancer.

### Scaling the write / storage path

- 200M businesses fit in a single well-provisioned relational DB, but for headroom **shard** the business DB by `business_id`.
- Use a **primary for writes** and **read replicas** for detail reads.
- When a business is added/updated/deleted, update both the business table and the geospatial index (the index update can be **asynchronous** since real-time reflection isn't required).

### Consistency

- Eventual consistency is acceptable: a newly added business appearing in search after a short delay is fine. This relaxation is what lets us cache and replicate aggressively.

### Choosing the approach

| Criterion | Geohash | Quadtree | Redis Geo |
|---|---|---|---|
| Storage | DB column + prefix index | In-memory tree | In-memory sorted set |
| Adapts to density | No (fixed precision) | Yes | No |
| Ease of implementation | High (just strings + LIKE) | Medium | Highest (built-in) |
| Update cost | Low | Higher (rebalance) | Low |
| Best for | Simple radius search, SQL-friendly | Skewed density, k-NN | Fast prod deployment |

A common interview answer: **geohash stored in a relational/Redis index** for simplicity and SQL-friendliness, mentioning quadtree as the adaptive alternative for highly skewed data.

---

## Step 4 — Wrap Up

### Summary

- Split into **LBS (read-heavy geospatial search)** and **Business Service (CRUD + details)** because their access patterns differ.
- The crux is a **geospatial index**; a naive 2D range query scans the whole table, so we encode space into something indexable.
- **Geohash** (prefix-based, SQL/Redis-friendly) is the recommended baseline; handle **boundary** and **sparse-result** edge cases by querying neighbor cells and reducing precision.
- **Quadtree** offers density-adaptive subdivision; **Redis Geo** offers a production-ready built-in geohash index; **S2/Hilbert** suits arbitrary region coverage.
- The workload is **read-heavy with mostly-static data**, so we **replicate and cache the index** widely and accept **eventual consistency** for writes.

### Additional talking points

- **Re-ranking** by rating, popularity, or sponsored placement after the spatial filter.
- **Multiple precision levels** indexed per business to serve different radii efficiently.
- **Hot regions** (dense cities) may need finer sharding or dedicated cache nodes.
- **CDN/edge caching** of popular searches for the lowest latency.
- **Monitoring**: query latency percentiles, cache hit ratio, index freshness lag.
