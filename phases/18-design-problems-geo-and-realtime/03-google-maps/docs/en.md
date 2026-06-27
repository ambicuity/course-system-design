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
