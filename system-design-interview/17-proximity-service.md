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
   Users ──► LB ──▶ │  LBS (Location-  │ ──► Geospatial index / cache
   (search)         │  Based Service)  │      (read-only, replicated)
                    └─────────────────┘
                    ┌─────────────────┐
   Owners ──► LB ──▶  │ Business Service │ ──► Business DB (primary + replicas)
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

---

# Deep Dive Addendum

The remainder of this chapter is enrichment for interview-grade depth: extended capacity math, ASCII diagrams, trade-off tables, real-world case studies (Yelp, Uber, Tinder, Google Places, Foursquare), failure modes, interviewer Q&A, and a glossary.

## Back-of-the-Envelope Math (Extended)

The chapter's headline assumption — 200M businesses, 5,000 QPS — gives a single concrete picture. Push further to defend the design.

### Step 1 — derive QPS and bandwidth

```
QPS_search_avg   = 5,000
QPS_search_peak  ≈ 5× avg = 25,000  (lunchtime, events)
QPS_writes_avg   ≈ 5,000 / 1000     ≈ 5 writes/sec (1 write per 1000 reads)
QPS_writes_peak  ≈ 25  (rare; batched index updates)
```

The ratio of ~1000:1 reads-to-writes is the defining property. It justifies aggressive caching and eventual consistency.

Per-query payload size:

```
response ≈ 20 businesses × 200 B = 4 KB
```

Per-second bandwidth at peak:

```
bandwidth_out = 25,000 × 4 KB = 100 MB/s ≈ 800 Mbps
```

A single 1 Gbps link covers the entire API tier. The bottleneck is **query latency**, not bandwidth.

### Step 2 — index size

At geohash precision 6 (≈ 1.2 km × 0.6 km cells), how many cells exist? The geohash base-32 grid has 32^6 = ~10^9 possible 6-character cells. Most are empty (oceans, uninhabited). Real count:

```
active_cells ≈ 10^7  (rough estimate: 10M populated 1km² cells worldwide)
```

Per cell, store `(geohash, business_id)` rows. With 200M businesses spread across 10M cells:

```
avg_businesses_per_cell = 200M / 10M = 20 businesses/cell
total_rows              = 200M (one per business, indexed by primary geohash)
row_size                ≈ 32 (geohash) + 8 (business_id) + overhead = 64 B
index_storage           ≈ 200M × 64 B ≈ 12.8 GB
```

With 8-byte precision geohash (rather than the full 6-character string), the index halves. Either way, the entire geospatial index fits on a single commodity server with RAM to spare.

### Step 3 — Redis sizing

If we use Redis Geo with 200M points:

```
52-bit score           = 8 B
business_id            = 8 B
member name (id)       = 8 B
overhead               ≈ 16 B per entry
total Redis memory     ≈ 200M × 40 B ≈ 8 GB
```

A single Redis Enterprise node or 3-node cluster comfortably handles 8 GB of data with replication. The 52-bit geohash fits in a Redis sorted-set score (double precision gives 52 bits of mantissa).

### Step 4 — query latency budget

For a 100 ms target:

| Step | Budget |
|---|---|
| Network to LBS | 5-15 ms |
| LBS compute (geohash + query plan) | <1 ms |
| Index lookup (Redis) | 1-3 ms |
| 8-neighbor expansion | 1-5 ms |
| Re-rank by true distance | 1-5 ms |
| Hydrate business details (cache hit) | 5-15 ms |
| Network back to client | 5-15 ms |
| **Total (cache hit)** | **20-60 ms** |
| Hydrate business details (cache miss) | 20-50 ms |
| **Total (cache miss)** | **35-110 ms** |

A 100 ms target is achievable when the index and details cache hit; a cache miss pushes you to the edge of SLO.

### Step 5 — write amplification on index updates

When a business moves (rare but happens):

```
business table     : 1 row updated
geohash index      : old geohash row deleted + new geohash row inserted
dedup cache        : TTL expires, no action
detail cache       : invalidated, refilled on next read
```

Total: 4-5 small writes per business move. With 5 writes/sec aggregate, this is invisible load. Even at 1000 writes/sec (a bad batch importer), it's well within DB capacity.

### Step 6 — global scale

If we generalize to "places of interest" rather than just businesses (adding parks, landmarks, transit stations), the count roughly 10×s:

```
places_worldwide   ≈ 2 × 10^9
geohash index      ≈ 130 GB
Redis memory       ≈ 80 GB
```

At this scale, the index no longer fits on one Redis node but is still well within a small cluster. Sharding by region (one Redis cluster per continent) is the natural break.

---

## ASCII Architecture Diagrams

### Diagram 1 — End-to-end proximity search

```
   Client (mobile)                  LBS                          Backends
        │                            │                              │
        │  GET /search?lat=…&lon=…   │                              │
        │  &radius=2000              │                              │
        │───────────────────────────▶│                              │
        │                            │                              │
        │                            │ 1. compute geohash + radius  │
        │                            │    + 8 neighbors              │
        │                            │                              │
        │                            │ 2. ZRANGEBYSCORE geohash:6*  │
        │                            │─────────────────────────────▶│ Redis
        │                            │◀──── candidate IDs ──────────│
        │                            │                              │
        │                            │ 3. filter by Haversine       │
        │                            │    (true distance ≤ radius)  │
        │                            │                              │
        │                            │ 4. MGET business:{id}        │
        │                            │─────────────────────────────▶│ Redis (details cache)
        │                            │◀─── JSON per business ───────│
        │                            │                              │
        │                            │ 5. (cache miss) hydrate from │
        │                            │    business DB                │
        │                            │─────────────────────────────▶│ Postgres
        │                            │◀─────────────────────────────│
        │                            │                              │
        │◀─── JSON: 20 businesses ────│                              │
```

### Diagram 2 — Geohash cell layout (8-neighbor expansion)

```
   The user's location falls in cell "9q8yy" (center).
   Boundary problem: a business 50 m away might be in a
   neighboring cell with a different prefix.

              ┌────────┬────────┬────────┐
              │ 9q8yv  │ 9q8yw  │ 9q8yx  │
              ├────────┼────────┼────────┤
              │ 9q8yt  │ 9q8yy  │ 9q8yz  │
              │        │  YOU   │        │
              ├────────┼────────┼────────┤
              │ 9q8ys  │ 9q8yr  │ 9q8yq  │
              └────────┴────────┴────────┘

   Query: SELECT * FROM geo_index
          WHERE geohash IN (
            '9q8yy', '9q8yz', '9q8yw', '9q8yx',
            '9q8yt', '9q8yv', '9q8ys', '9q8yr',
            '9q8yq'
          )
   Then filter by Haversine(lat, lon, business_lat, business_lon) ≤ radius
```

### Diagram 3 — Quadtree subdivision (adaptive)

```
   World
     │
     ├── N. America
     │      │
     │      ├── East Coast (dense)        ← splits deeper
     │      │      │
     │      │      ├── NYC                ← ~50 businesses
     │      │      ├── Boston             ← ~30 businesses
     │      │      └── Philadelphia       ← ~40 businesses
     │      │
     │      └── West (sparse)             ← stays one node
     │             └── Wyoming            ← ~5 businesses
     │
     ├── Europe
     │      │
     │      ├── London area (very dense)
     │      │      │
     │      │      ├── Central London     ← ~200 businesses
     │      │      │      │
     │      │      │      ├── Soho        ← ~80 businesses (split)
     │      │      │      └── Shoreditch  ← ~70 businesses (split)
     │      │      └── Greater London    ← ~30 businesses
     │      │
     │      └── Rural Spain              ← ~3 businesses (one node)
     │
     └── Pacific (mostly water)          ← stays one node
```

### Diagram 4 — Write path (owner adds a business)

```
   Owner                API GW          Business DB         Geo Index Updater
     │                    │                  │                       │
     │ POST /businesses   │                  │                       │
     │───────────────────▶│                  │                       │
     │                    │ BEGIN            │                       │
     │                    │─────────────────▶│                       │
     │                    │ INSERT           │                       │
     │                    │─────────────────▶│                       │
     │                    │ COMMIT           │                       │
     │                    │◀─────────────────│                       │
     │                    │  enqueue (biz)   │                       │
     │                    │─────────────────────────────────────────▶│
     │                    │                                          │
     │◀── 201 Created ────│                  │                       │
     │                    │                                          │
     │                    │                       compute geohash    │
     │                    │                       INSERT into        │
     │                    │                       geo_index          │
     │                    │                                          │
     │                    │                       invalidate        │
     │                    │                       details cache      │
     │                    │                                          │
     │                    │◀──────── ack ───────────────────────────│
     │                    │                                          │
     │  (search now       │                                          │
     │   returns new biz  │                                          │
     │   within seconds)  │                                          │
```

---

## Trade-off Tables

### Trade-off 1 — Geospatial index choice

| Index | Memory | Adapt to density | Query latency | Update cost | Best for |
|---|---|---|---|---|---|
| Fixed grid | O(cells × density) | No (worst case) | O(cells in radius) | Low | Uniform datasets, prototypes |
| Geohash | O(businesses) | No (fixed precision) | O(neighbors × businesses/cell) | Low | General radius search |
| Quadtree | O(businesses) | Yes | O(depth × neighbors) | Higher (rebalance) | Skewed density, k-NN |
| R-tree | O(businesses) | Yes | O(log N + k) | Higher | Range + k-NN combined |
| S2 / Hilbert | O(businesses) | Yes (region cover) | O(cover cells) | Medium | Region / polygon queries |
| Redis Geo | O(businesses) | No | O(log N + k) | Low | Fast to ship, in-memory only |

### Trade-off 2 — Storage backend

| Backend | Index latency | Persistence | Replicas | Best for |
|---|---|---|---|---|
| Redis (Geo) | 1-5 ms | Optional (AOF/RDB) | Built-in (replicas) | Hot path, ephemeral |
| Postgres + GIST | 5-50 ms | Yes (WAL) | Streaming replication | Source of truth + ad hoc queries |
| Elasticsearch (geo_point) | 20-100 ms | Yes | Sharding | Combined search + geo |
| MySQL + spatial | 5-50 ms | Yes | Group replication | Existing MySQL stack |
| RocksDB / LevelDB | 5-20 ms | Local | Manual | Embedded / single-node |
| S2 library + custom store | 5-50 ms | Yes | Per backend | Google-class systems |

### Trade-off 3 — Radius vs k-NN

| Approach | User experience | Latency | Filtering needed |
|---|---|---|---|
| Fixed radius (e.g., 5 km) | Predictable | Low | True distance check |
| k-NN (e.g., nearest 20) | Adapts to density | Higher (must scan further) | Optional |
| Adaptive radius (expand if <k results) | Best of both | Higher (multiple passes) | True distance check |
| Tile-based (sliding window) | Map-style | Variable | Heavy |

### Trade-off 4 — Cache freshness

| Strategy | Freshness | Cache hit ratio | Best for |
|---|---|---|---|
| Long TTL (24 h) | Up to 24 h stale | Very high (>95%) | Static businesses |
| Short TTL (5 min) | 5 min stale | High (~80%) | Moderately dynamic |
| Write-through invalidation | Real-time | High (~70%) | Frequently changing |
| No cache (DB read) | Real-time | 0% | Low-QPS / cold cache |

### Trade-off 5 — Boundary handling

| Approach | Correctness | Cost | Best for |
|---|---|---|---|
| 8-neighbor expansion | Correct within geohash boundary | ~9× query cost | Standard |
| 24-neighbor (for big radius) | Correct for very large radii | ~25× query cost | Large radius |
| Pre-filter by bounding box + true distance | Correct, cheaper for sparse areas | 2× | Production |
| Hilbert / S2 cover | Correct for any shape | Region-dependent | Polygon queries |

---

## Real-World Case Studies

### Case Study 1 — Yelp's proximity search

Yelp's engineering blog and conference talks describe their proximity search as a multi-stage pipeline:

1. **Stage 1: geospatial prefilter** using a tile-based index. The world is divided into ~10 million tiles (~1 km²); each tile is a primary key in a custom distributed store.
2. **Stage 2: candidate expansion**. From the user's tile, expand to all tiles overlapping the search radius (typically 9-25 tiles).
3. **Stage 3: re-rank**. Apply Haversine distance, then sort by Yelp's **ranking signal** (rating, review count, recency, "not a competitor" filter, sponsored placement).
4. **Stage 4: hydrate** business details from a separate cache tier.

Yelp's distinctive contribution: the **business-detail caching is per-region** so a "popular SF restaurant" is hot in SF but cold in NYC. This is a great interview answer because it shows awareness that **the index and the detail cache are different beasts**.

### Case Study 2 — Uber's geohash grid

Uber has published extensively on its **geospatial indexing for dispatch**:

- **Geohash precision 6** (about 1.2 km × 0.6 km) for the citywide index.
- **Hexagonal grid** for finer-grained supply/demand matching (H3, Uber's open-source library).
- **Two-tier index**: city → geohash → hex. Each tier has different QPS and freshness requirements.

Why Uber uses hexagons (H3) instead of squares (geohash):

- Hexagons have **6 neighbors** vs. 8 for squares, but more importantly, **all 6 neighbors are equidistant**, which simplifies distance calculations.
- Hexagons tile the plane without gaps; squares have ambiguity at corners.

The H3 library (open-sourced 2018) is the canonical example of an **adaptive geospatial index** purpose-built for ride-sharing.

### Case Study 3 — Tinder's location

Tinder's matching requires **"find people near me"** for millions of active users, but with two critical differences from a Yelp-style service:

- **Moving users**: people change location constantly, so the index cannot be precomputed and must update in real time.
- **Privacy**: a user should not appear in searches outside their stated radius.

Tinder's solution (described in their engineering blog and recruiting talks):

- **Geohash precision 5-6** for the user-location index.
- **In-memory index** keyed by geohash; updated on every location change (every few minutes per user).
- **Privacy filter** at query time: the server enforces "caller's stated distance ≥ distance between caller and target."

The interview angle: Tinder is the case study for **mobile / moving-object indexes** where the data is dynamic and the index cannot be precomputed.

### Case Study 4 — Google Places API

Google Places API is the closest production analog to the chapter's problem:

- Uses **Google S2** internally (publicly documented in Google's S2 library).
- Supports both **radius search** (`nearbysearch`) and **text search** (`textsearch`).
- Returns place IDs, which can be hydrated via the Place Details API.
- Combines **geospatial** and **textual relevance** ranking; the ranking model is proprietary but documented in Google's public talks.

The S2 library maps the sphere to a Hilbert space-filling curve at multiple resolutions (cell levels 0-30). Each level corresponds to a different cell size; the library supports region cover queries natively (returning all cells covering a given shape).

### Case Study 5 — Foursquare's POI pipeline

Foursquare operates one of the largest POI databases (places of interest):

- **Source data**: a mix of user contributions, OSM imports, and venue-owner claims.
- **Geospatial index**: Foursquare uses a **PostgreSQL + PostGIS** deployment; PostGIS provides GIST-based spatial indexes natively.
- **Place matching**: when a user "checks in," Foursquare must resolve the lat/long to a venue; this is a separate **reverse-geocoding** service that uses the same geospatial index.
- **Pipelines**: POI updates flow through Kafka; consumers update the index and the place details in near-real-time.

The Foursquare case study is the canonical reference for **open-source geospatial** at scale: PostGIS handles hundreds of millions of points with proper indexing and tuning.

---

## Common Pitfalls & Failure Modes

### Pitfall 1 — 2D B-tree on lat/long is not a spatial index

A common rookie mistake: creating two B-tree indexes (one on `lat`, one on `long`) and assuming the database will use both for a radius query. It will not — it picks one. The result is a full scan of the larger of the two indexes (or a bitmap intersection that ends up scanning half the table). **Mitigation**: use a real spatial index (GIST, geohash, quadtree).

### Pitfall 2 — Geohash boundary problem

Two businesses 50 m apart fall in different geohash cells with **no shared prefix** because they straddle a quadrant boundary. Naively querying only the user's geohash misses them. **Mitigation**: always expand to the 8 (or 24) neighbors and filter by true distance.

### Pitfall 3 — Geohash precision mismatch

If the user searches for "within 200 m" but the geohash precision is 6 (cells of 1.2 km), every cell returned is ~6× the requested radius — you pull 36× the data and filter most of it out. **Mitigation**: choose the geohash precision to match the requested radius. At precision 7 (~150 m cells), a 200 m search returns ~9 cells.

### Pitfall 4 — Pole and antimeridian distortion

Geohash cells get stretched near the poles and have severe distortion near the antimeridian (180° longitude). A "cell" at the pole is essentially a triangle. **Mitigation**: for global systems, use a library that handles spherical geometry (S2, H3) rather than raw geohash.

### Pitfall 5 — Cache stampede on cold cache

After a cache eviction, the first request to each cell hits the DB and triggers a flood of queries. **Mitigation**: **request coalescing** (single-flight), **negative caching** of empty cells, and **pre-warming** the cache on deploy.

### Pitfall 6 — Stale cache for closed businesses

A business closes, but the detail cache holds the stale "open" status for hours. **Mitigation**: explicit invalidation on business updates; lower TTL for fast-changing fields; per-field caching with field-level invalidation.

### Pitfall 7 — Hot region overload

During lunch on a sunny day in Manhattan, the LBS tier behind the Manhattan geographic tile saturates. **Mitigation**: **geographic sharding** of the LBS tier; finer-grained sharding in dense cities; rate limiting per tile.

### Pitfall 8 — Haversine vs Euclidean distance

The earth is a sphere; a flat-earth (`sqrt((x2-x1)^2 + (y2-y1)^2)`) distance is wrong by up to 0.5% at mid-latitudes and much more near the poles. **Mitigation**: always use the **Haversine formula** for distance, or better, use a library that handles spherical geometry (geographiclib, S2).

### Pitfall 9 — Index explosion with high precision

A geohash precision of 8 (cell size ~38 m × 19 m) means **32^8 = ~10^12 cells**. Most are empty, but indexing all of them is wasteful. **Mitigation**: store only cells that contain at least one business; use a sparse representation.

---

## Interview Q&A

**Q1 — How do you handle a "near me" search when the user is moving?**

A: Three answers. (1) **Client-side throttling**: don't fire a search on every GPS tick. Throttle to one search every 5-10 s, or only when the user has moved >100 m. (2) **Server-side caching of recent queries**: cache `(lat_bucket, lon_bucket, radius) → results` for a short TTL; if the user is approximately stationary, the same cached result serves. (3) **Push model**: subscribe the client to "places near my path" rather than "places near my point" — precompute cells along the user's route. This is the right answer for navigation apps.

**Q2 — What if the user wants "nearby" with a variable radius (5 km, 10 km, anywhere)?**

A: Two strategies. (1) **Compute geohash precision to match radius**: precision 5 for 5 km, precision 4 for 20 km, etc. (2) **Tile pyramid**: precompute multiple precision levels per business, so a query can pick the right precision without recomputing. The two strategies compose well: store geohashes at multiple precision levels per business, query the one that matches the user's radius.

**Q3 — How would you make this system global?**

A: Three answers. (1) **Geographic sharding**: the LBS tier is sharded by region (continent/country). A query goes to the shard that owns the user's location. (2) **Edge POPs**: deploy LBS replicas close to users; replicate the index per region. (3) **Compliance**: data residency rules differ by jurisdiction; the business DB may need to be partitioned to comply with local law. For a global system, **Google S2** is the right library — it handles spherical geometry correctly and supports region covers.

**Q4 — How do you handle a 10× traffic spike (e.g., during a festival)?**

A: Layered. (1) **Autoscale the LBS tier**: it's stateless, so add boxes. (2) **Pre-warm the cache** for the festival's location in advance. (3) **Reduce query breadth**: temporarily cap the max-radius at 5 km to limit the cells searched per query. (4) **Aggressive client-side caching**: increase the client TTL for the duration of the event. (5) **Rate limiting**: per-IP and per-prefix limits to prevent a single bad actor from saturating the tier.

**Q5 — How would you handle "find me the nearest X" (k-NN) instead of radius?**

A: Three approaches. (1) **k-NN with binary search on radius**: start with a small radius, double until you have k results, then re-rank. (2) **Quadtree traversal**: traverse the quadtree from the root, prioritizing children whose centers are closer; accumulate businesses until you have k. (3) **S2 knn**: Google S2 has a `Closest` API that does this directly. The interview should mention that **k-NN has no natural "geohash prefix" answer**; you must search outward, which is why quadtree / S2 are better fits than fixed-grid geohash.

**Q6 — How do you rank results once you have the candidates?**

A: Multiple signals combined via a learned model. (1) **Distance**: closer is better, but with diminishing returns (so use `1 - exp(-d/d0)` rather than `1/d`). (2) **Rating**: weighted by review count to penalize 5-star ratings from 1 review. (3) **Popularity / click-through rate**: business-agnostic CTR. (4) **Open now**: filter or boost if the business is open at query time. (5) **Sponsored placement**: businesses pay to be featured in specific geo queries. The model is trained on past query → click data; ranking is a separate service from the geospatial prefilter.

**Q7 — How do you handle businesses with multiple locations (chains)?**

A: Two answers. (1) **One business, many place IDs**: the canonical entity is the chain (e.g., Starbucks, Inc.); each location has a separate place_id. (2) **Aggregated results**: queries like "nearby Starbucks" can group by chain_id and return the 3 closest locations. The data model has a `chain_id` column on each business; the index can be queried by chain_id for chain-specific searches.

---

## Glossary

| Term | Definition | Common misconception |
|---|---|---|
| Geohash | Base-32 encoding of recursive lat/long subdivision | Adjacent cells can have totally different prefixes at boundaries |
| Quadtree | Tree that recursively subdivides 2D space into 4 children | "Quadtree = quadhash" — quadtree is a tree structure; quadhash would be a flat encoding |
| R-tree | Tree for spatial data with arbitrary-shaped bounding boxes | "R-tree = B-tree for 2D" — close, but R-trees group nearby rectangles, not sort by key |
| Hilbert curve | Space-filling curve mapping 2D to 1D | "Hilbert = Z-order" — both are space-filling curves but with different locality properties |
| S2 | Google's library for spherical geometry; cell-based | "S2 = geohash on a sphere" — S2 is much more; it supports region covers, polygons, knn |
| H3 | Uber's hierarchical hexagonal grid | "H3 = geohash with hexagons" — H3 is hierarchical (16 resolutions); geohash is recursive |
| Haversine formula | Great-circle distance on a sphere | "Haversine = exact" — accurate to ~0.5% on Earth; for higher accuracy use Vincenty or S2 |
| Bounding box | Rectangular region (min lat, max lat, min lon, max lon) | "Bounding box = radius query" — bounding box is rectangular; radius is circular |
| Region cover | Set of cells covering a region | "Region cover = grid" — covers are computed per query from the region shape |
| Geofence | Virtual perimeter around a geographic area | "Geofence = radius" — geofences can be any shape; used for triggers, not search |
| PostGIS | Postgres extension for spatial data | "PostGIS = MySQL spatial" — MySQL spatial is more limited; PostGIS implements the OGC standard |
| GIST index | Generalized Search Tree; Postgres's spatial index type | "GIST = B-tree" — GIST supports many indexable types (spatial, full-text, ranges) |
| k-NN | k-nearest neighbors; find the k closest points | "k-NN = radius" — k-NN has no fixed radius; the result set size is fixed |
| Radius query | Find all points within distance r | "Radius = exact distance" — cell-based approximations introduce error |
| Tile | A cell on a map (e.g., slippy map tile, S2 cell) | "Tile = pixel" — tiles are vector or raster cells; pixels are raster elements |
| Slippy map | XYZ tile scheme used by web maps | "Slippy map = projection" — slippy map is a tile naming scheme, not a projection |
| WGS84 | Standard geodetic datum used by GPS | "WGS84 = lat/lon" — WGS84 is a datum; lat/lon are coordinates |
| Edge POP | Point of presence close to users | "POP = data center" — POPs are smaller; data centers are full facilities |
| Single-flight | Pattern that coalesces concurrent identical requests | "Single-flight = cache" — single-flight protects the backend during cache misses |
| Boundary problem | Two nearby points falling in cells with no shared prefix | Often forgotten in geohash-based designs |