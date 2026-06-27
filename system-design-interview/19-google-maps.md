# Design Google Maps

Google Maps is a web mapping platform that renders the world, finds places, and gives turn-by-turn navigation with live traffic. The interesting parts for a system-design interview are: serving billions of map tiles cheaply, turning addresses into coordinates (geocoding) and back, computing shortest paths over a continent-scale road graph, and producing an ETA that adapts to real-time traffic.

---

## Step 1 — Understand the Problem and Establish Scope

### Functional requirements

1. **Map rendering** — display a map of any region at multiple zoom levels, panning/zooming smoothly.
2. **Geocoding** — convert a textual address or place name into latitude/longitude, and reverse-geocode coordinates into an address.
3. **Directions / routing** — given an origin and destination, return the best route (by time, distance, or other criteria) for driving, walking, cycling, transit.
4. **Navigation** — turn-by-turn guidance that updates as the user moves, including rerouting.
5. **ETA** — estimated time of arrival that reflects current and predicted traffic.
6. **Location updates** — accept continuous GPS pings from active navigators (both to drive the UI and to feed the traffic model).

### Out of scope (call this out explicitly)

- Street View, satellite imagery pipeline, business listings/reviews, indoor maps, lane-level AR. We acknowledge them but won't design them.

### Non-functional requirements

- **Massive read scale**: tile and routing reads dominate; writes (traffic ingest) are smaller but continuous.
- **Low latency**: tiles should feel instant (<100 ms from edge); a route request should return in a few hundred ms.
- **High availability**: a degraded map is acceptable, an unavailable one is not. Routing can fall back to stale traffic.
- **Accuracy**: routes must be correct; ETA should be within a reasonable error band.
- **Smooth navigation under poor connectivity** (tunnels, rural areas) — needs client buffering/prefetch.
- **Cost efficiency**: tiles are the bulk of traffic; serving them from origin servers would be ruinously expensive, so caching/CDN is core.

### Back-of-the-envelope estimation

Assume **1 billion** monthly active users, and **first-order daily** numbers:

| Quantity | Estimate | Reasoning |
|---|---|---|
| DAU | ~200 M | ~20% of MAU |
| Navigation sessions/day | ~50 M | a fraction of DAU navigate |
| Location pings | 1 ping/sec during navigation | a 30-min trip = ~1,800 pings |
| Peak ping QPS | ~1–2 M/s | concurrent active navigators × 1/s |
| Tile requests | far larger than route requests | each pan/zoom fetches a grid of tiles |

**Tile storage**: the world tiled at zoom levels 0–21. The number of tiles at zoom `z` is `4^z`. Summed across all levels this is on the order of **hundreds of billions of tiles**. Most are ocean/empty and compress to almost nothing; realistic detailed coverage with multiple styles still lands in the **petabytes** range. Key insight: tiles are **mostly static** and **highly cacheable**.

**Traffic data ingest**: ~1–2 M pings/sec × tens of bytes = tens of MB/s sustained — modest compared to tile bandwidth, but high-fan-in and continuous, so it needs a streaming buffer.

---

## Step 2 — Propose High-Level Design

### Core geospatial idea: tiling and geohashing

The whole system rests on **partitioning the surface of the Earth into a discrete grid** so that we can name, cache, index, and shard by location.

- **Web Mercator tiles**: the standard. The world is a square; at zoom `z` it's a `2^z × 2^z` grid of 256×256-pixel tiles. A tile is addressed by `(z, x, y)`. Zooming in one level quadruples the tile count and doubles resolution. This is exactly the addressing a CDN loves: an immutable URL per `(z, x, y, style)`.
- **Geohash**: encodes lat/long into a short string where shared prefixes mean spatial proximity. Useful for **range queries**, **proximity search**, and **sharding** location data so that nearby pings/objects land near each other.
- **S2 / H3** (production systems) are more sophisticated cell systems (S2 uses a Hilbert curve on a cube-projected sphere; H3 is hexagonal). For an interview, geohash conveys the idea; mention S2/H3 as the real-world refinement that avoids geohash's distortion near boundaries.

### Major services

```
            ┌────────────┐      ┌──────────────┐
  Client ──▶│   CDN/Edge │─────▶│  Tile Service │──▶ Tile store (object storage)
            └────────────┘      └──────────────┘
                 │
                 ├──▶ Geocoding Service ──▶ Place/Address index
                 │
                 ├──▶ Routing Service  ──▶ Road graph store + traffic cache
                 │
                 └──▶ Location Service ──▶ stream (Kafka) ──▶ Traffic pipeline
```

1. **Tile service (+ CDN)** — serves pre-rendered raster or vector tiles by `(z, x, y)`. Almost everything is cached at the edge.
2. **Geocoding service** — forward and reverse geocoding over an address/place index.
3. **Routing service** — shortest-path over the road graph with traffic-weighted edges; returns route geometry + ETA + turn instructions.
4. **Location/navigation service** — receives GPS pings, drives turn-by-turn guidance, detects off-route conditions, triggers reroutes, and forwards anonymized pings to the traffic pipeline.
5. **Traffic pipeline** — aggregates pings into per-road-segment speeds, feeds the routing edge weights and the ETA model.

### API design (sketch)

```
# Tiles (cacheable, GET, served by CDN)
GET /tiles/{style}/{z}/{x}/{y}.{png|mvt}

# Geocoding
GET /geocode?q="1600 Amphitheatre Pkwy"      -> [{lat, lng, formattedAddress, placeId, confidence}]
GET /reverse?lat=..&lng=..                     -> {formattedAddress, components, placeId}

# Directions
POST /directions
  body: { origin:{lat,lng}, destination:{lat,lng}, mode:"drive", departAt, alternatives:true }
  resp: { routes:[ { polyline, distanceMeters, durationSeconds, steps:[...], etaSeconds } ] }

# Navigation session / location updates
POST /nav/{sessionId}/location
  body: { lat, lng, heading, speed, timestamp, accuracy }
  resp: { onRoute:bool, nextManeuver, distanceToManeuver, updatedEta, reroute? }
```

Notes:
- Tile GETs are **idempotent and immutable per version** → set long `Cache-Control: max-age` + content-hash/version in the path so a style update is a new URL (cache busting without purges).
- Directions is a POST in practice (large bodies, no caching of personalized/traffic-sensitive results), though GET is fine conceptually.

### Data model

**Road graph** — the heart of routing:
- **Nodes**: intersections (and graph-split points). Each has lat/lng.
- **Edges**: road segments connecting two nodes. Attributes: length, speed limit, road class (highway/arterial/local), one-way flag, turn restrictions, time-dependent restrictions, current traffic speed.
- Stored as an adjacency structure. For continent-scale graphs you don't keep the whole thing hot per query; you **partition** it (see deep dive) and precompute shortcuts.

**Geocoding index** — addresses, POIs, place polygons; spatially indexed (geohash / S2 / R-tree / inverted index for text) to support both text lookup and nearest-neighbor.

**Tiles** — pre-rendered blobs in object storage, keyed by `(style, version, z, x, y)`.

---

## Step 3 — Design Deep Dive

### 3.1 Serving map tiles cheaply

**Vector vs raster tiles**
- **Raster** (PNG/WebP): rendered server-side, simple client, large bytes, one image per style/zoom.
- **Vector** (e.g. Mapbox Vector Tiles): geometry + attributes; the client renders. Smaller, restylable on the fly, smooth zoom/rotation, label re-placement. Modern maps prefer vector; raster is the simpler interview answer.

**Why a CDN is non-negotiable**
- Tiles are static and shared by all users → cache hit rates are extremely high (popular city centers are requested constantly).
- Pushing tiles to **edge POPs** serves them near users at <50–100 ms and offloads origin almost entirely. This is the single biggest cost lever.
- Versioned URLs (`/tiles/{style}/{version}/{z}/{x}/{y}`) make cache invalidation trivial: ship a new version, old tiles age out naturally.

**Tile generation**
- An **offline rendering pipeline** consumes raw geographic data (roads, water, landuse, labels) and produces tiles per zoom/style. This is a batch job; only changed regions are re-rendered. Hot, popular tiles are pre-warmed into the CDN; the long tail (empty ocean, remote areas) is rendered lazily or stored compressed.
- **Pre-render popular zoom levels** eagerly; render rare deep-zoom tiles on demand and then cache.

**Client behavior**
- The client requests the **grid of tiles** covering the viewport plus a margin, and **prefetches adjacent tiles** in the pan direction. It keeps a local cache so panning back is instant and to survive brief disconnects.

### 3.2 Geocoding

**Forward geocoding** (text → coordinates):
- Parse and normalize the query (abbreviations, country formats, typos).
- Use an **inverted text index** over address components + a ranking model (proximity to the user, popularity, match confidence).
- Return candidates with confidence; interpolate along a street segment when an exact house number isn't a known point.

**Reverse geocoding** (coordinates → address):
- Spatial lookup: find the enclosing/nearest address or place. Use a **spatial index** — geohash prefix scan, S2 cell lookup, or R-tree — to get nearby candidates fast, then pick the best (containing polygon for a building, nearest segment for a street address).

**Sharding**: geocoding data shards naturally **by region/geohash prefix**, keeping a country or city's data colocated. Heavily queried regions (large cities) may need finer splits.

### 3.3 Routing / shortest path

The naive answer is **Dijkstra** or **A\*** (A\* with a straight-line/haversine heuristic prunes the search toward the destination). On a graph with hundreds of millions of nodes, plain Dijkstra per request is too slow for interactive latency. Production uses **preprocessing-based speedups**:

| Technique | Idea | Trade-off |
|---|---|---|
| **A\*** | Heuristic-guided Dijkstra | Easy, helps, but still slow continent-scale |
| **Contraction Hierarchies (CH)** | Precompute "shortcut" edges by contracting nodes in importance order; query does a bidirectional search over a much smaller effective graph | Very fast queries (ms), but preprocessing must be redone when edge weights change a lot |
| **Customizable Route Planning (CRP)** | Separate the slow topology preprocessing from a fast **metric customization** step, so traffic-updated weights can be re-applied cheaply | Better fit for live traffic; more complex |
| **Graph partitioning / overlay graphs** | Partition the map into regions; precompute boundary-to-boundary distances; route in 3 hops: source→boundary, across overlay, boundary→dest | Scales to continents; partition boundaries need care |

**Why partitioning matters**: you can't load the planetary graph for every query. Partition the road network into cells (often geohash/S2-aligned). Long-distance routes traverse a small **overlay graph** of region boundaries (mostly highways), and only expand detail near the endpoints. This mirrors how humans navigate: local streets → highway → local streets.

**Edge weights are time-dependent**: travel time on an edge depends on the road's traffic at the time you'll actually traverse it, which for a long route is *in the future*. So edge cost = `f(segment, predicted_speed_at_arrival_time)`. This is why CH's static-weight assumption is awkward and CRP-style customization or live re-weighting is preferred.

**Alternatives & criteria**: return 2–3 routes (fastest, shortest, fewer tolls). Mode (drive/walk/bike/transit) selects different edge sets and weights; transit routing is a separate time-expanded graph over schedules.

### 3.4 Navigation, location updates, and rerouting

**Session flow**
1. Client starts a nav session; server returns the route polyline + maneuver list + initial ETA.
2. Client streams **location pings (~1/s)** to the location service.
3. Server (or client, for resilience) performs **map matching**: snap the noisy GPS point to the most likely road segment using the road geometry and recent trajectory (an HMM/Viterbi map-matcher handles GPS noise and parallel roads).
4. Detect **off-route**: if matched position deviates beyond a threshold for N consecutive pings, **trigger a reroute** from the current position to the destination.
5. Continuously **recompute ETA** from current position + live traffic.

**Resilience under poor connectivity**
- The route and upcoming maneuvers are **buffered on the client**, so guidance continues through tunnels/dead zones without server round-trips.
- Pings are **batched and retried** when connectivity returns; the UI never blocks on the network for the next instruction.

**Two roles of a ping**: (a) drive *this* user's UI, and (b) feed the **traffic model** in aggregate (anonymized). Decouple them — the UI path is synchronous/low-latency; the analytics path is fire-and-forget into a stream.

### 3.5 Adaptive ETA with live traffic

**Ingest → aggregate → serve** pipeline:

1. **Ingest**: millions of pings/sec land on the location service and are published to a durable **stream (Kafka)**. The stream absorbs bursts and decouples producers from the slower aggregation consumers.
2. **Map-match & aggregate**: stream processors snap pings to road segments and compute **rolling average speeds per segment** over short windows. Sparse/low-volume segments fall back to **historical/predicted speeds** for that segment at that time-of-day/day-of-week.
3. **Publish traffic**: per-segment current speeds are written to a fast **traffic cache** (in-memory KV) that the routing service reads as edge weights, and a **prediction model** estimates speeds at future arrival times for long routes.
4. **ETA** = sum over route segments of `length / speed(segment, predicted_time_at_segment)`, plus turn/junction penalties. For a long trip, the speed used for a far-away segment is the *predicted* speed when you'll reach it, not its speed now.

**Why predicted, not just current**: by the time you reach a highway 40 minutes away, current congestion there is irrelevant; the model uses historical patterns + current trend to predict. ETA is continuously corrected as you progress and as live data refines the prediction.

---

## Step 4 — Wrap Up

### Scaling and bottlenecks recap

- **Tiles**: the dominant bandwidth cost; solved by **versioned, immutable, CDN-cached** tiles with client prefetch. Origin sees only cache misses.
- **Routing latency**: solved by **graph preprocessing** (contraction hierarchies / CRP / overlay graphs over partitioned regions) so queries are milliseconds, not seconds.
- **Traffic ingest fan-in**: solved by a **streaming buffer (Kafka)** + windowed aggregation; the UI path is kept separate and synchronous.
- **Geospatial sharding**: **geohash/S2** partitions tiles, geocoding data, road-graph cells, and location streams so nearby data colocates and queries stay local.
- **ETA accuracy**: live + historical speeds, future-time prediction, continuous recomputation.

### Additional considerations

- **Hot regions**: dense cities concentrate tile, geocode, route, and ping load → finer sharding and more replicas for those geohash cells.
- **Privacy**: traffic pings must be **anonymized and aggregated**; never store identifiable trajectories in the traffic model.
- **Consistency model**: maps tolerate **eventual consistency** — slightly stale traffic or a not-yet-rendered new road is acceptable; availability and latency win.
- **Map data updates**: roads, closures, and turn restrictions change. New road data flows through the rendering pipeline (new tile version) and the routing preprocessing (re-customization), ideally incrementally per region.
- **Failure modes**: if the traffic cache is down, route on **historical speeds**; if routing is overloaded, shed to cached/precomputed common routes; tiles keep serving from CDN even if origin is degraded.

### Key takeaways

- Everything is anchored on **discretizing the globe** (tiles + geohash/S2) so you can cache, index, and shard by location.
- **CDN-cached static tiles** make a planet-scale map economically viable.
- **Routing at scale = preprocessing**, not raw Dijkstra; partition the graph and precompute shortcuts/overlays.
- **ETA is a streaming + prediction problem**, not a static distance/speed division.

---

## Deep Dive: Back-of-the-Envelope Math

### Constants and assumptions

| Constant | Value | Notes |
|---|---|---|
| MAU | 1 × 10^9 | global |
| DAU/MAU | 0.20 | 2 × 10^8 DAU |
| Active navigators at peak | 1 × 10^6 | a fraction of DAU, peaks in commute hours |
| Pings/sec per active nav | 1 | ~1 ping/sec, ~1.8k pings per 30-min trip |
| Tile request fanout per viewport load | 12–60 | depending on device pixel ratio and zoom |
| Panning session/zoom-in | 20 viewport loads / session | a user opening Maps sees a few dozen tile grids |
| Address searches / day | 1 × 10^9 | ~5 per DAU, geocoder is hot |
| Route requests / day | 2 × 10^8 | ~1 per DAU |
| Earth surface area | 510 × 10^12 m² | |
| Web Mercator tile edge at z=0 | 40,075 km | full equator |
| Tile pixel size | 256 × 256 | or 512 for high-DPI |

### Tile universe at zoom levels 0..21

The number of tiles at zoom `z` is `4^z`. Summing `4^z` for `z = 0..21` gives `4^22 - 1 / 3 ≈ 5.6 × 10^12` tiles at the deepest level. In practice:

- Zoom 0–10: covers the world coarsely, ~1.2 M tiles total. **All rendered**, fit on a single disk.
- Zoom 11–15: regional detail, ~4.3 × 10^9 tiles. ~5% are "interesting" (have roads/buildings), the rest are ocean/desert/forest at this scale. ~200 M interesting tiles.
- Zoom 16–18: street-level, ~70 × 10^9 tiles globally. ~30% interesting, ~20 B interesting tiles.
- Zoom 19–21: building-level, ~5 × 10^12 tiles. Sparse content, only ~5–10% are interesting; a significant fraction can be empty/blank.

At an average of 5–10 KB of compressed vector per interesting tile, the "interesting" subset lands in the **low-tens of TB** even before aggressive tile compression; raster is 2–4× larger. The number cited in the chapter (hundreds of billions of tiles, petabytes) includes the long tail of blank tiles; the **active** working set is on the order of **tens of TB of vector data**.

### Bandwidth math (the number that matters)

Assume 200 M DAU × 20 viewport loads/session × 24 tiles/viewport ≈ **9.6 × 10^10 tile fetches/day** ≈ **1.1 M tile requests/sec on average, ~3 M/sec at peak**. At 5 KB per vector tile: **~15 GB/sec average, ~45 GB/sec at peak**. This is why origin-served tiles would be ruinous: a single origin would need ~10 Gbps just to keep up at peak, and that's before any cache. With a CDN, the same workload is served from RAM at the edge, costing a fraction of a cent per GB.

### Traffic ingest math

- Peak ping QPS: 1 M navigators × 1 ping/sec = **1 × 10^6 pings/sec**.
- Per-ping payload (anonymized): `{segmentId, speed, ts, deviceClass}` ≈ 60 bytes.
- Bandwidth: 1 M × 60 B = **60 MB/sec** at peak. Sustainable on a single Kafka broker; sharded by region for headroom.

### Routing math

- Continent-scale graph: ~10^8 nodes, ~3 × 10^8 edges for OSM-grade data.
- Plain Dijkstra explores ~10^7 nodes per query → too slow. A* with great-circle heuristic prunes ~10× → still 10^6 nodes. With Contraction Hierarchies the effective search graph is ~10^3–10^4 nodes → milliseconds.

### ETA math

- For a 30-km route with 200 segments, summing per-segment `length / speed` is 200 floating-point divisions. Negligible.
- The expensive part is **maintaining the speed prediction per segment**: at 10^7 road segments globally with 5-min freshness, that's ~3.3 × 10^4 updates/sec. Trivial.
- The hard part is **the prediction model**: 10^7 segments × (time-of-day × day-of-week × seasonality) = a large but tractable model; training and serving are not the bottleneck, **freshness** of the live feature is.

---

## Deep Dive: ASCII Architecture Diagrams

### Diagram 1 — End-to-end navigation request (sequence)

```
  Mobile App        Edge/CDN        Routing Svc       Road Graph        Traffic Cache    Map-Match Svc
      │                │                 │                │                  │                │
      │ POST /dirs     │                 │                │                  │                │
      │ (origin, dest) │                 │                │                  │                │
      │───────────────▶│                 │                │                  │                │
      │                │ /directions     │                │                  │                │
      │                │────────────────▶│                │                  │                │
      │                │                 │ load region    │                  │                │
      │                │                 │ graph shard    │                  │                │
      │                │                 │───────────────▶│                  │                │
      │                │                 │                │                  │                │
      │                │                 │ pull current   │                  │                │
      │                │                 │ edge weights   │                  │                │
      │                │                 │─────────────────────────────────▶│                │
      │                │                 │                │                  │                │
      │                │                 │ A* + CH (with time-dep weights)  │                │
      │                │                 │   compute top-2 routes          │                │
      │                │                 │                │                  │                │
      │                │  routes JSON    │                │                  │                │
      │                │◀────────────────│                │                  │                │
      │ routes + ETA   │                 │                │                  │                │
      │◀───────────────│                 │                │                  │                │
      │                │                 │                │                  │                │
      │ start nav      │                 │                │                  │                │
      │                │                 │                │                  │                │
      │ ping @1Hz      │                 │                │                  │                │
      │───────────────▶│                 │                │                  │                │
      │                │ POST /nav/loc   │                │                  │                │
      │                │────────────────▶│                │                  │                │
      │                │                 │ map-match      │                  │                │
      │                │                 │─────────────────────────────────────▶             │
      │                │                 │                │                  │ segmentId+speed│
      │                │                 │ on-route? ETA delta?             │                │
      │                │                 │                │                  │                │
      │                │ nav response    │                │                  │                │
      │                │◀────────────────│                │                  │                │
      │ updated UI     │                 │                │                  │                │
      │◀───────────────│                 │                │                  │                │
```

Key path latencies (target): edge → routing ≤ 200 ms p99; routing → map-match ≤ 50 ms p99; map-match → ETA update ≤ 50 ms p99. Total nav cycle ≤ 300 ms p99.

### Diagram 2 — Tile request and CDN cache hierarchy

```
  Mobile App         PoP  Edge       PoP  Mid-Tier       Origin Shield       Tile Store (S3)
      │                  │                │                  │                     │
      │ GET /tiles/      │                │                  │                     │
      │   streets/       │                │                  │                     │
      │   12/2048/1353   │                │                  │                     │
      │─────────────────▶│                │                  │                     │
      │                  │ HIT?           │                  │                     │
      │                  │ (most likely)  │                  │                     │
      │ ◀────tile bytes──│                │                  │                     │
      │                  │                │                  │                     │
      │ MISS path:       │                │                  │                     │
      │                  │                │                  │                     │
      │ GET /tiles/...   │                │                  │                     │
      │─────────────────▶│                │                  │                     │
      │                  │ MISS           │                  │                     │
      │                  │───────────────▶│                  │                     │
      │                  │                │ HIT?             │                     │
      │                  │                │ (regional cache) │                     │
      │                  │                │                  │                     │
      │                  │                │ MISS             │                     │
      │                  │                │─────────────────▶│                     │
      │                  │                │                  │  GET S3 (signed)    │
      │                  │                │                  │────────────────────▶│
      │                  │                │                  │ ◀──── tile bytes ───│
      │                  │                │ ◀──── tile ─────│                     │
      │                  │ ◀──── tile ───│                  │                     │
      │ ◀──── tile ──────│                │                  │                     │
      │                  │                │                  │                     │
      │                  │ (each layer populates its cache on the way back)
```

Cache hit rate math: a typical map session repeats a few key tiles (home, work) over and over. Edge hit rate is ~95% for any large user base. Origin sees <1% of requests.

### Diagram 3 — Traffic pipeline (data flow)

```
  Active Nav Pings                       Windowed Aggregator             ML Predictor
        │                                        │                            │
        │ Kafka topic:                            │                            │
        │ "pings.raw" (60 B)                      │                            │
        │ 1 M/s peak                              │                            │
        ▼                                        ▼                            │
  ┌─────────┐    ┌─────────────────┐    ┌──────────────────┐    ┌──────────┐  │
  │ Kafka   │───▶│ Map-Match       │───▶│ Speed Aggregator │───▶│ Live KV  │  │
  │ Cluster │    │ Worker (Flink)  │    │ (5-min window)   │    │ (Redis)  │  │
  └─────────┘    └─────────────────┘    └──────────────────┘    └──────────┘  │
        │                                        │                            │
        │                                        └─────────────┐              │
        │                                                      ▼              ▼
        │                                              ┌──────────────────────────┐
        │                                              │   ETA Predictor          │
        │                                              │   (sparse + historical)  │
        │                                              └──────────────────────────┘
        │
        │ (also)
        ▼
  ┌─────────────┐
  │ S3 /        │  (anonymized pings, long-term analytics)
  │ Data Lake   │
  └─────────────┘
```

The pipeline is **stateless + horizontally scalable**: the windowed aggregator is a Flink job; state is in RocksDB; output is written to Redis (hot) and S3 (cold). Failure recovery is just "re-read from Kafka from last committed offset."

### Diagram 4 — Routing: contraction hierarchy intuition

```
  Original graph (top):                     CH-augmented (bottom):
    A──B──C──D──E──F                              S
       \  |  /  \  /                              │   shortcuts
        \ | /    \/                                │
         X──Y──Z                                  
                                                high-importance nodes (S, T)
                                                contracted first; shortcuts
                                                bypass them
  ─────────────────────────────────────────────────────
  Query A → F:
    A* + CH: A→S→T→F (3 hops, via shortcuts)
    Plain Dijkstra:  A→B→C→X→Y→Z→E→F (8 hops, much larger explored set)
```

CH makes queries dramatically faster by *not exploring* the low-importance local streets except near the origin and destination.

---

## Deep Dive: Trade-off Tables

### 1. Raster vs vector tiles

| Property | Raster (PNG/WebP) | **Vector (MVT/Mapbox)** |
|---|---|---|
| Bytes per tile | 10–30 KB | 2–10 KB (geometry + attrs) |
| Restylable on the client | no (per-style re-render) | **yes** (theme in client) |
| Smooth zoom across levels | "pixelated" between zooms | **continuous** |
| Label placement | server-rendered, fixed | **client-side, can re-flow on rotation** |
| Render cost on client | none (it's a bitmap) | meaningful (WebGL/Canvas) |
| Server render pipeline | rasterizer per (style, z) | once for vector, client stylizes |
| Best for | low-end devices, simple UI | modern, smooth, interactive maps |

### 2. Routing algorithms: Dijkstra / A* / CH / CRP / ALT

| Algorithm | Preprocess cost | Query time | Handles live traffic? | Memory |
|---|---|---|---|---|
| Dijkstra | none | O(N log N) bad | trivially (re-weight) | low |
| A* | none | O(N) good w/ heuristic | trivially | low |
| **CH** (Contraction Hierarchies) | hours, redo on weight changes | **<10 ms** | hard (CH is weight-sensitive) | medium |
| **CRP** (Customizable) | hours for topology; seconds for metric | **<10 ms** | **excellent** | medium |
| **ALT** (A* + Landmarks) | minutes | ~5–10× faster than A* | yes | small |
| Overlay / Hub Labels | hours | <5 ms | hard (precomputed) | large |

The interview-friendly answer is "CH or CRP for live traffic; CRP when traffic updates are frequent."

### 3. Geocoding: Elasticsearch vs dedicated spatial index

| Property | Elasticsearch | **S2/H3-aware geocoder** | PostGIS |
|---|---|---|---|
| Text relevance ranking | excellent | must layer on top | poor |
| Spatial prefix queries | okay | **excellent** | good |
| Scale to global POIs | medium (sharding pain) | high | low |
| Custom scoring (popularity, user location) | easy | manual | manual |
| Cost at 1 B Q/day | high | medium | high |

Production: a hybrid — Elasticsearch for text relevance, an S2/H3 spatial index for candidate generation, then a custom ranker for "this user is 2 km from the result so it should rank above an exact-text match that's 50 km away."

### 4. ETA model: live-only vs live+historical vs ML-predicted

| Model | Quality | Cost | Failure mode |
|---|---|---|---|
| Live only (current segment speed) | poor on future segments | low | assumes future = now, wildly wrong in rush hour |
| Live + historical fallback | decent | medium | reacts late to incidents |
| **Live + historical + ML predicted** | **best** | high (training + serving) | needs careful retraining; sensitive to events |

### 5. Tile storage: S3 + CDN vs regional origin servers

| Property | S3 + CDN | Regional origin |
|---|---|---|
| Cost per GB | low | medium |
| Latency to user | edge (10–50 ms) | origin-region (100–300 ms) |
| Cache invalidation | versioned URL (cheap) | purge API (slow) |
| Update propagation | hours (CDN TTL) | instant |
| Best for | mostly-static tiles | frequently-changing traffic overlays |

---

## Deep Dive: Real-World Case Studies

### Google Maps (the original design)

Google Maps' roadmap over 20+ years is a tour of the trade-offs above. The 2005 launch served raster tiles generated by an offline pipeline and pulled from MySQL-backed tile servers; the 2010s introduced vector tiles and the contraction-hierarchies-based routing engine; the 2018–2024 era added live traffic, lane-level guidance, and AR walking navigation.

- **Tile architecture**: raster → vector (protobuf-encoded Mapbox Vector Tiles, then Google's own `.mvt` variant). Tiles are immutable, versioned by a content hash in the URL; the CDN never needs to be purged.
- **Routing**: publicly described as a multi-level graph with Contraction Hierarchies + time-dependent edge weights. The "free-flow" baseline uses posted speed limits; live traffic overlays adjust.
- **ETA**: Google has published multiple papers describing its traffic-prediction system (DeepMind collaboration, 2020+) using graph neural networks over road segments with historical + live features. The 50% accuracy improvement on ETA during the COVID period was a notable public result.
- **Privacy**: the public model is "anonymized aggregated probe data" — a ping contributes to a segment average, not to an individual trajectory.

### OpenStreetMap (OSM) and the tile server stack

OSM is the open-data source behind most non-Google maps. Its tile-serving stack is a useful interview example of how an open-source community handles the same problems at smaller scale.

- **Tile generation**: a pipeline (`tilemaker`, `osm2pgsql`, `osm-carto`) reads the OSM XML/PGF planet file and produces raster tiles. The full planet render at zoom 0–14 takes ~1 day on commodity hardware; deeper zooms are community-rendered per region.
- **Tile serving**: a CDN fronts a render farm. `tile.openstreetmap.org` served tens of billions of requests per year before the policy tightened to protect the volunteer infrastructure; community runtimes now use tile-server implementations like `tileserver-gl`.
- **Geocoding**: Nominatim is the canonical OSM geocoder, built on PostGIS. It is **slow** at scale compared to Google's geocoder and is a great example of "good enough for thousands of QPS, not for Google-scale."
- **Routing**: OSRM (Open Source Routing Machine) and GraphHopper implement CH and ALT over OSM data and are used by default in many smaller apps.

### Mapbox

Mapbox is the commercial successor to the open-source Mapbox stack and is the canonical example of vector-tile-first design.

- **Tiles**: vector tiles pre-rendered by `tippecanoe` and served via CDN. Custom styles rendered client-side.
- **Geocoding**: a hosted service (formerly `mapbox-geocoding-v5`) that combines text relevance with proximity-based ranking.
- **Routing**: optimized for "fast and pretty" — uses CH-style preprocessing; lower emphasis on live-traffic depth than Google.
- **Adoption**: Snap Map, Strava, Facebook (parts of), and many news/mapping products use Mapbox; their API is a clean reference for the public-facing surface.

### Waze (and the real-time traffic angle)

Waze is the canonical example of a community-driven traffic system. Its design point is *the driver as a sensor*:

- **Ingest**: every Waze-equipped phone is a probe — pings every few seconds with speed and heading.
- **Aggregation**: server-side map-matching converts raw GPS into per-segment speeds, with a heavy emphasis on **incident detection** (sudden slowdowns = accidents, hazards, police).
- **Editing**: Waze pioneered the "user-edited map" — closed roads, new roundabouts, gas prices — with editorial review.
- **Architectural lesson**: Waze's traffic signal-to-noise ratio is lower than Google's (fewer users, lower density in many regions) but the *editorial* layer is a force multiplier. Acquired by Google in 2013, it now feeds incident data into Google Maps.

### HERE Maps (and OpenLR)

HERE (formerly Nokia/Navteq) is the second-largest commercial map provider and a useful counter-example to Google.

- **Tile architecture**: vector-first since the early 2010s, similar to Mapbox but with a more enterprise/government customer base (automotive, fleet).
- **Routing**: heavy emphasis on **truck routing** (height, weight, hazmat) and ADAS-grade geometry.
- **OpenLR**: HERE published OpenLR, an open standard for **location referencing** — a compact encoding of a road segment's position so traffic reports can be matched between maps of different vendors. This is the "geocoding for road segments" problem and is widely used in automotive traffic feeds.

### Uber / DeepETA and Lyft ETA models

Ride-hailing ETAs are different from driving ETAs because the optimization target is "minimize driver-rider wait" not "minimize travel time" — but the data plumbing is informative.

- **Uber's DeepETA** (publicly described 2019): a deep-learning model that predicts arrival time using a graph representation of the road network, historical trips, and live features (weather, time of day, events). Reduces ETA error by ~26% over the baseline gradient-boosted-tree model.
- **Lyft**: similar architecture, with a public paper on their segment-speed and ETA service.
- **Lesson for our design**: ML-predicted ETAs are now the bar; the interview answer should at least name this.

---

## Deep Dive: Common Pitfalls & Failure Modes

### 1. Stale tiles after a map data update

**Symptom:** a new highway opens, but for weeks users see "no road here" or are routed the long way around.

**Root cause:** tile rendering is a batch job; if it isn't triggered for the changed region, or if a new tile version is generated but the CDN is still serving the old version (cache TTL of weeks), users see stale data.

**Fix:**
- Treat map data updates as events: each change in the source GIS dataset triggers a partial re-render of affected tiles, with a new content hash, and the CDN URL is versioned so old tiles age out without explicit invalidation.
- Run a **freshness monitor** that, for known landmarks (e.g., the new highway), periodically renders a tile and checks it against the source.

### 2. Routing on stale traffic weights

**Symptom:** ETA is consistently optimistic during rush hour. The map says "30 min," reality is 50 min.

**Root cause:** the traffic cache is updated on a 5-min window, but commute conditions change in seconds. Or: the cache went read-only during an outage, and the system fell back to historical speeds that don't match the live regime.

**Fix:**
- Tier the traffic cache: **hot** segment speeds in memory with <30 s freshness; **warm** speeds in Redis with 1–5 min; **cold** historical averages in TSDB. Fall back tier-by-tier.
- Add a **stale-cache detector** that compares a sample of live pings against the cached value; if divergence exceeds a threshold, force-refresh that segment.

### 3. Geocoding "in this country" bias

**Symptom:** "Paris" returns Paris, France to a user in Paris, Texas. Or "Springfield" returns the wrong one of 30+ Springfields.

**Root cause:** the geocoder ranks purely on text relevance and global popularity, with weak location bias.

**Fix:** bias the ranker by the user's current location, IP geolocation, or search history. This is a well-known ML problem; the system needs a "user location" feature in the ranker and a robust cold-start fallback (IP-based country/city).

### 4. Graph explosion in the road network

**Symptom:** the routing service OOMs on a long route because it expanded too many local nodes.

**Root cause:** the graph partitioning scheme isn't actually partitioning — or the boundaries were defined at a level that still has too many nodes.

**Fix:**
- Always **bound the search** by a bounding box around origin and destination plus a "this region is fully expanded" radius (e.g., 50 km).
- Use **cell-based shortcuts**: within a cell, expand freely; between cells, use precomputed boundary distances.
- Profile per-region graph density; some areas (dense cities) need finer partitioning.

### 5. Map matching failures on parallel roads

**Symptom:** two adjacent one-way streets or a divided highway; the map-matcher keeps snapping the user to the wrong carriageway.

**Root cause:** the HMM/Viterbi map-matcher is using only the closest segment, not the trajectory.

**Fix:** the map-matcher must use a sequence of pings (not just one) and consider heading, speed, and the prior matched segment. Pure proximity matching will fail on parallel structures. A standard reference: Newson & Krumm (2009), "Hidden Markov Map Matching Through Noise and Sparseness."

### 6. Routing that violates turn restrictions

**Symptom:** the route says "turn left here" at a no-left-turn intersection.

**Root cause:** the turn restriction isn't in the routing graph, or it's there but the search ignores it.

**Fix:** turn restrictions are explicit edges in the graph (a "turn restriction node" that says "you cannot go from edge A to edge B"). Validate against a known fixture set on every graph build; CI must include turn-restriction regression tests.

### 7. The "reroute loop" bug

**Symptom:** the user is on a long route. One GPS ping is off. The system reroutes. The new route is longer. The next ping is "off-route again" (because the new route passes through the same spot). Reroute storm.

**Root cause:** the reroute trigger fires on every off-route ping instead of N consecutive off-route pings with a distance threshold.

**Fix:**
- Off-route detection: require N consecutive pings more than ε meters off the polyline.
- Cooldown: after a reroute, no second reroute within X seconds.
- Snapshot: if the user re-enters the original route's polyline buffer, cancel any pending reroute.

### 8. Privacy leak: stored identifiable trajectories

**Symptom:** the traffic-ping store has user IDs and full GPS traces; a researcher runs an "anonymized" query and de-anonymizes individuals.

**Fix:**
- Strip user IDs at ingest; the traffic model never sees them.
- Aggregate pings into segment-speed buckets within 5-min windows; never store the per-user trajectory.
- Differential-privacy noise on the aggregates.
- Compliance review: any new "personalized traffic" feature must be reviewed by privacy.

### 9. Tile fetches exhausting the user's data plan

**Symptom:** a user opens Maps in a low-bandwidth region and burns through 200 MB in a session.

**Fix:** client-side tile compression, **conditional GETs** with `If-None-Match` for the ETag, lower pixel-ratio on slow networks, and a "lite" tile style for low-bandwidth mode.

---

## Deep Dive: Interview Q&A

### Q1. "Why CDN-cached tiles instead of a custom rendering service that generates tiles on demand?"

**Answer sketch.** Tile rendering is **expensive** (it touches the full planet's worth of data) and tiles are **highly cacheable** (one tile is shared by millions of users). The break-even hit rate is very low — even a 50% cache hit makes on-demand generation wasteful. Add the latency: on-demand generation takes 100+ ms per tile, vs. <20 ms from edge cache. A CDN is the natural answer. On-demand rendering is only appropriate for the long tail of deep-zoom tiles in obscure regions.

### Q2. "How do you keep ETAs accurate when traffic changes in real time?"

**Answer sketch.** Two parallel paths: (1) **live traffic cache** updated every ~30 s with rolling average speeds per segment, populated by the streaming pipeline that map-matches incoming pings; (2) **historical baseline** (per-segment, per-time-of-day, per-day-of-week) for fallback when the live cache is sparse. ETA = sum of `length / max(live_speed, historical_speed × confidence)`. For long trips, weight the speed for a far-away segment by the **predicted** speed at the time of arrival (a small ML model). Continuously recompute as the user progresses and the prediction horizon shrinks.

### Q3. "How do you route across continents in <100 ms?"

**Answer sketch.** Partition the graph into cells. Precompute boundary-to-boundary distances as **shortcuts** (CH or hub labels). A query: expand from origin to the boundary of its cell (~1 ms), hop across the cell-boundary overlay graph (~1 ms), expand to destination in its cell (~1 ms). Total: a few ms for the search, plus per-segment speed lookup (a few ms), plus serialization. The whole thing is dominated by network latency to the user, not compute.

### Q4. "What if we 10x to 10 B MAU? 100x to 100 B MAU?"

**Answer sketch (10x).** Same architecture, more shards. Tiles are fine — the CDN already does most of the work. Routing: more graph cells, more replicas per region. Geocoding: more shards of the address index. Traffic ingest: scale the Kafka cluster linearly; the map-match and aggregation tier is the bottleneck, scale that horizontally. Risk: more pings means the live traffic model is denser, which improves accuracy — no fundamental ceiling.

**Answer sketch (100x).** At 100 B MAU we're well past human population; the framing probably means "every connected device." This is the Waze-of-everything regime. The traffic pipeline becomes a continuous learning system: every device is a probe, and the segment-speed model must be a global GNN (à la DeepMind-Google Maps 2020) updated continuously. Routing latency becomes less interesting (CDN for everything) than prediction latency (how fresh can the model be). You'd also see **federated learning on the device** to keep personalization local.

### Q5. "How do you go global — multi-region, multi-language, multi-jurisdiction?"

**Answer sketch.** Three layers:
- **Tile/render infra**: edge presence in each major region; tile generation per region because the data is local and the language set differs. CDN serves from the nearest edge.
- **Geocoding**: data is regional; each region has its own shards and language-specific tokenizers. A global front router reads the user's locale from the request and routes to the right shard.
- **Compliance**: traffic pings may be subject to data-residency laws (e.g., EU, China, India). Ingest and aggregate within the region; only ship aggregate outputs across borders. The data-residency boundary should be a first-class architectural line, not a config knob.

### Q6. "How do you handle map data updates without breaking the world?"

**Answer sketch.** Tiles are versioned: every change in the source GIS data produces a new tile version, and the CDN URL has the version in the path. Old tiles age out via the cache TTL — no explicit purge. The routing graph is also rebuilt incrementally per region on data changes, with the **CRP** trick: the topology (which nodes/edges exist) is rebuilt slowly; the metric (edge weights for traffic) is updated continuously. New roads appear with default speeds until traffic data populates them. The whole pipeline is event-driven: a change in OSM (or HERE, or your internal source) triggers a re-render of affected tiles and an incremental re-customization of the routing graph.

### Q7. "What about offline / dead zones during navigation?"

**Answer sketch.** The route polyline + maneuver list is delivered to the client once at the start of navigation. The client buffers upcoming maneuvers (next 5–10) locally, so guidance continues without a server round-trip. Pings during dead zones are buffered on the client and retried on reconnect; the server reconciles by replaying the trajectory. Map tiles for the route corridor are pre-fetched before departure (e.g., for the next 30 km), so even a tunnel doesn't break rendering. The reroute logic is the only piece that requires connectivity; in offline mode, the client shows "searching for signal" rather than auto-rerouting.

### Q8. "How would you test this?"

**Answer sketch.** Four layers: (a) **graph correctness fixtures** — known routes between landmarks must match the expected polyline; checked in CI on every graph build. (b) **geocoding fixtures** — a sample of address queries with expected coordinates and confidence. (c) **load tests** — synthetic pings from a fleet of headless nav clients, measuring end-to-end p99 propagation latency. (d) **canary regions** — push a new tile/routing build to one region first; compare ETAs and routing outputs against a holdout. (e) **chaos** — partition an edge POP, kill a routing shard, see whether traffic falls back to historical and tiles keep serving.

---

## Glossary

| Term | Definition | Common misconception |
|---|---|---|
| **Web Mercator** | A square projection of the Earth used by all major web maps. Distorts area near the poles but preserves shape and angles. | "It's accurate everywhere." No — Greenland looks as big as Africa. |
| **Tile** | A 256×256 (or 512×512) pixel image or vector blob at a given zoom `(z, x, y)`. | "Tiles are always images." Vector tiles are geometry + attributes, not pixels. |
| **Geohash** | Base-32 string encoding of lat/lng where shared prefix = spatial proximity. | "Geohash is uniform." It has large area distortion at edges of the 32-cell. |
| **H3** | Uber's hexagonal hierarchical spatial index. | "Hexagons are more accurate than squares." Slightly, but the real reason is uniform neighbor counts (6 vs. 8). |
| **S2** | Google's spherical geometry cell system, Hilbert-curve on a cube projection. | "S2 and H3 are interchangeable." They have different cell shapes, different APIs, different edge cases. |
| **Contraction Hierarchies (CH)** | Routing speedup: precompute shortcuts by contracting low-importance nodes. | "CH is free." Preprocessing is hours, must be redone when weights change. |
| **CRP (Customizable Route Planning)** | Two-level preprocess: slow topology, fast metric. | "CRP is the same as CH." It separates *what* the graph is from *how expensive* it is. |
| **A\* / ALT** | A* with landmarks; heuristic-pruned shortest path. | "A* solves routing." A* alone doesn't scale continent-scale; it needs preprocessing. |
| **Map matching** | Snap noisy GPS points to the road network using a sequence model (typically HMM). | "Map matching = closest segment." Proximity alone fails on parallel roads. |
| **ETA** | Estimated time of arrival; sum of segment travel times with traffic + predicted traffic. | "ETA = distance / speed_limit." Real ETA uses live + predicted speeds. |
| **Vector tile** | A protobuf-encoded blob of geometry + attributes; the client renders. | "Vector tiles are smaller than raster." Usually, but the bigger win is restylability and smooth zoom. |
| **Overlay graph** | A coarser graph over a partitioned base graph, used to cross partitions cheaply. | "Just one big graph works." Try it; the in-memory cost is prohibitive. |
| **CDN (Content Delivery Network)** | A geographically distributed cache that serves static content from the edge near the user. | "CDN is for images only." Map tiles, JS, and most static assets benefit equally. |
| **Ingest** | The act of receiving and writing data into the system. | "Ingest is one API call." Production ingest is a stream with backpressure and durability. |
| **Live traffic** | Per-segment current speed derived from probe data. | "Live traffic is exact." It's an estimate with confidence; sparse segments fall back to historical. |
| **Histograms (for quantiles)** | Bucket counts recorded at ingest so quantiles can be merged across instances. | "Average the percentiles." Never — pre-aggregated percentiles cannot be averaged. |
| **Push vs pull probes** | Pings actively sent by devices vs. pings scraped from devices. | "Pull is always fresher." Pull is fixed by the scrape interval; push can be near-real-time. |
| **Tile pyramid** | The set of all tiles across zoom levels 0..max. | "Higher zoom = bigger image." Higher zoom = more tiles at finer resolution. |
| **Distance matrix** | Precomputed travel time/distance between O-D pairs. | "Distance matrix = routing." It is a precomputed cache, not a substitute for live routing. |
