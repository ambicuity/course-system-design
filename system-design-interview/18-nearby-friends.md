# Design Nearby Friends

"Nearby Friends" shows you which of your friends are physically close *right now*, updating continuously as everyone moves. It looks superficially like the Proximity Service, but the requirements are fundamentally different: instead of a mostly-static index of businesses, we have **millions of constantly-moving users** pushing location updates every few seconds, and we must deliver those updates to friends in **near real time**. This shifts the design from "geospatial index + caching" to "persistent connections + pub/sub fan-out."

---

## Step 1 — Understand the Problem & Establish Scope

### Clarifying questions

- What's "nearby"? Friends within a radius (e.g., **5 miles**).
- How fresh must locations be? Near real-time, with updates roughly every few seconds (e.g., **every 30 seconds**, acceptable delay tolerated).
- Is this **friends-only**? Yes — only mutual friends who opted in are shown (vs. proximity service which is anyone/anything).
- Distance computed as straight-line? Yes, simple geodesic distance is fine.
- Do we store **location history**? Optionally for analytics, but the live feature only needs current locations.
- **Scale**? E.g., 100M DAU, ~10% using nearby-friends concurrently → ~10M active users.

### Functional requirements

1. Users see **friends nearby** (within a radius) on a map/list.
2. The displayed **distance updates periodically** as friends move.
3. Friends appearing/disappearing from the radius update in near real time.
4. Respect privacy / **opt-in** sharing.

### Non-functional requirements

- **Low latency** — location updates propagate to friends within a few seconds.
- **Reliability** — occasional dropped updates are tolerable (next update corrects it); the feature is soft real-time, not life-critical.
- **Eventual consistency** — small staleness is acceptable.
- **Scalability** — millions of concurrent users each pushing updates and receiving many friends' updates.

### Back-of-envelope estimation

- ~10M concurrent users.
- Each sends a location update **every 30 s** → 10M / 30 ≈ **~334,000 location updates/sec**.
- **Fan-out:** each update must reach the user's online friends within range. Average ~400 friends, but only nearby + online ones matter — still a large fan-out multiplier. Total downstream messages can be millions/sec.
- This write- and fan-out-heavy, low-latency profile is what dictates the architecture (persistent connections + pub/sub), the opposite of the read-heavy, cacheable proximity service.

---

## Step 2 — Propose High-Level Design & Get Buy-In

### Why not plain HTTP polling?

Clients could poll "where are my friends?" every few seconds, but at this scale polling is wasteful (constant requests even when nothing changed) and adds latency. We want the **server to push** updates as they arrive → **WebSocket** persistent connections.

### High-level architecture

```
            ┌──────────────────────────────────────────────┐
 Mobile ───▶│  Load Balancer  ───▶  WebSocket Servers       │
 clients ◀──│                       (stateful, hold conns)  │
            └─────────────┬───────────────┬─────────────────┘
                          │               │
                 location updates   subscribe to friends
                          ▼               ▼
                   ┌─────────────┐   ┌──────────────────┐
                   │  Redis Pub/ │   │  Location Cache   │
                   │  Sub        │◀─▶│  (Redis, TTL)     │
                   └─────────────┘   └──────────────────┘
                          ▲
                   ┌─────────────┐   ┌──────────────────┐
                   │ User DB /   │   │ Location History  │
                   │ Friends DB  │   │ DB (optional)     │
                   └─────────────┘   └──────────────────┘
```

Core components:

- **WebSocket servers** — maintain a **persistent bidirectional connection** per online user. They receive location updates from clients and push friends' updates down. These are **stateful** (they own live connections), unlike a typical stateless web tier.
- **Load balancer** — distributes WebSocket connections across servers.
- **Redis Pub/Sub** — the message backbone. Each user has a **channel**; when a user moves, their update is published to their channel, and the WebSocket servers holding that user's *friends'* connections are subscribed to it, so the update fans out to friends.
- **Location cache (Redis with TTL)** — stores each user's **most recent location** with a short **TTL** (e.g., 30–60 s). TTL means a user who stops sending updates (went offline) naturally expires and disappears — no explicit cleanup needed.
- **User/Friends DB** — friendship graph and profiles (relatively static).
- **Location history DB (optional)** — append-only store if historical analytics are needed.

### End-to-end update flow

1. User A's phone sends a **location update** over its WebSocket connection (e.g., every 30 s).
2. The WebSocket server:
   - Writes A's location to the **location cache** (refreshing the TTL).
   - **Publishes** the update to A's **Redis Pub/Sub channel**.
   - Optionally appends to the location history DB.
3. Every WebSocket server that holds a connection for one of A's friends is **subscribed** to A's channel. It receives the published update.
4. For each subscribed friend B, the server **computes the distance** between A and B (using B's last known location from the cache) and, if within the radius, **pushes** the update down B's WebSocket connection.
5. B's app updates the map/list. The reverse happens for B → A.

### Subscription setup

When user B comes online and opens nearby-friends, B's WebSocket server **subscribes to the Redis channels of all of B's friends** (or just nearby ones). Now any movement by those friends flows to B. On disconnect, the server unsubscribes.

---

## Step 3 — Design Deep Dive

### Distance calculation: where and when

- The distance check happens **on the WebSocket server** when it receives a friend's published update. It compares the sender's new location against the recipient's last-known location (from cache).
- Use simple geodesic (Haversine) distance; only push to the client if within the radius (e.g., 5 miles).
- Doing the filter server-side avoids spamming clients with out-of-range updates, but every update still triggers distance checks against all subscribed friends — a real cost driver at scale.

### Scaling the WebSocket servers (the central bottleneck)

WebSocket servers are **stateful** and hold huge numbers of long-lived connections, which complicates scaling:

- **Connection capacity:** a tuned server handles tens of thousands to ~100k+ concurrent connections (limited by memory and file descriptors). 10M users / 100k per server ≈ **~100+ servers**, plus headroom.
- **Horizontal scaling:** add more servers behind the load balancer. Because connections are sticky/long-lived, use connection-aware load balancing.
- **Graceful scale-down / deploys:** dropping a server drops its connections; clients must **auto-reconnect** (to a possibly different server) and re-subscribe. Reconnect storms must be handled with backoff and jitter.
- **Auto-scaling difficulty:** unlike stateless tiers, you can't instantly shift load — existing connections stay until reconnect. Plan capacity with headroom and bleed connections gradually during scale-in.

### Scaling Redis Pub/Sub

- A single Redis Pub/Sub node can't handle millions of channels/messdrops at full scale → run a **cluster / ring of Redis Pub/Sub servers**, sharding channels across nodes (e.g., by hashing userId).
- A WebSocket server subscribes on the Redis node(s) that own its friends' channels. A **service discovery** layer maps channel → Redis node.
- **Fan-out cost** dominates: a user with many online friends generates many downstream messages per update. Pub/Sub naturally fans out, but the aggregate message rate (millions/sec) sets the cluster size.

### Location cache with TTL

- Store `userId -> {lat, long, timestamp}` in Redis with a **TTL slightly longer than the update interval** (e.g., 30 s updates → ~60 s TTL).
- **Self-cleaning:** if updates stop, the entry expires and the user is treated as offline/unavailable — no separate "user went offline" bookkeeping required.
- This cache is the source of "last known location" used in distance checks.

### Handling users with many friends (super-users)

- A user with thousands of friends causes heavy subscription/fan-out load.
- Mitigations: only subscribe to **online** friends, cap or shard subscriptions, and possibly use a **dedicated Pub/Sub channel-per-server aggregation** so one server isn't overwhelmed by a celebrity's update fanning to everyone.

### Privacy & correctness

- Only share location for **opted-in** users; enforce friendship + consent before subscribing.
- Allow users to pause sharing (stop publishing; cache entry expires).
- Don't leak precise coordinates beyond what's needed; the client only needs friends within range.

### Reliability trade-offs

- **At-most-once is acceptable** for location updates: if one update is dropped, the next (a few seconds later) corrects the displayed position. This lets us avoid the cost of durable queues/retries that a notification system needs.
- WebSocket reconnect + periodic full re-send keeps clients eventually consistent after blips.

### Optional: periodic vs event-driven updates

- **Periodic (every N seconds)** is simplest and predictable — used here.
- **Adaptive** updates (send more frequently when moving fast, less when stationary) cut traffic significantly; worth mentioning as an optimization to reduce the ~334k updates/sec.

---

## Step 4 — Wrap Up

### Summary

- Nearby Friends is **write- and fan-out-heavy and real-time**, the inverse of the read-heavy, cacheable Proximity Service — so the architecture centers on **persistent WebSocket connections** and **Redis Pub/Sub fan-out**, not a heavily-cached geospatial index.
- Clients push periodic location updates over WebSocket; servers write to a **TTL'd location cache**, **publish** to the user's channel, and friends' servers (subscribed to that channel) **compute distance** and push in-range updates down.
- **TTL** on the location cache makes offline detection automatic.
- The hardest scaling problems are **stateful WebSocket servers** (connection capacity, reconnect handling, hard auto-scaling) and **Redis Pub/Sub fan-out** at millions of messages/sec, addressed by clustering/sharding channels.
- **Eventual consistency** and **at-most-once** delivery are acceptable, which keeps the design simpler than a guaranteed-delivery system.

### Additional talking points

- **Adaptive update frequency** to cut traffic from stationary users.
- **Geo-sharding** WebSocket servers by region so most friend updates stay within a region's cluster (lower cross-shard fan-out).
- **Reconnect storms** after a deploy — backoff + jitter + connection draining.
- **Hybrid with geospatial index** if you ever need "nearby strangers" too: layer a geohash/Redis-Geo index over the live location cache.
- **Monitoring**: connections per server, Pub/Sub message rate, update propagation latency (p99), cache hit/expiry rates.

---

## Deep Dive: Back-of-the-Envelope Math

Working in powers of 2 and realistic constants. Assume a Facebook-scale system.

### Constants

| Constant | Value | Notes |
|---|---|---|
| MAU | 1,000,000,000 (10^9) | 1 B MAU |
| DAU/MAU ratio | 0.20 | ~200 M DAU |
| Nearby-friends DAU fraction | 0.10 | 20 M users open the feature/day |
| Concurrent at peak (CCU) | ~50% of feature DAU | ~10 M concurrent |
| Average friend count | 400 | Power-law tail; 90th percentile ~1,000 |
| Average **online** friends in range at any moment | 5–20 | most friends are not nearby |
| Update cadence | 1 / 30 s | ~2 bits of GPS resolution per second when moving |
| Update payload | ~100 B | `{userId, lat, lng, ts, heading?, speed?}` |
| Radius | 5 mi ≈ 8 km | configurable, often 1 mi default |
| Earth radius (R) | 6,371 km | for Haversine |

### Write side

- Updates/sec ingest = `CCU / cadence` = `10^7 / 30` ≈ **334,000 updates/sec**
- Bytes/sec ingest = `334,000 × 100 B` ≈ **33 MB/s** raw, easily handled
- Per-day raw = `33 MB/s × 86,400 s` ≈ **2.85 TB/day** of location events before any downsampling

### Fan-out (the real number)

A naive count of "messages each update creates" overstates things. Use a realistic model:

- Each update publishes to **1 channel** (the user's own).
- It is consumed by every WebSocket server that holds at least one of that user's **online + in-range** friends.
- For a typical user, the number of online in-range friends at any moment is small (5–20), so the **server-side fan-out** is correspondingly small.
- But the **aggregate** Pub/Sub message rate is still large: `334,000 publishes/sec × N_subscribers` where N_subscribers is the average number of WebSocket-server processes subscribed to a given user's channel.
- If we shard users across, say, 200 WebSocket server processes (so that "all of A's friends" are spread across ~50 of them), then each publish hits ~50 subscribers → `~17 million pub/sub messages/sec` across the cluster. That is the cluster's internal traffic.

### Subscriptions (subscribe cost)

When user B connects, B's WebSocket server issues ~400 SUBSCRIBE commands. Across 10 M concurrent users that's up to `10M × 400 = 4 × 10^9` subscription state entries in Redis. Two practical responses:

- Only subscribe to **online friends** (a smaller set after pruning the location cache); cuts subscriptions by 5–10x.
- Use a **server-local subscription fan-out** instead: one Redis SUBSCRIBE per "in-range group" the server cares about, then locally dispatch to the relevant connections.

### Storage

- Location cache: `10M users × ~100 B = ~1 GB` in Redis (one entry per active user). Comfortable on a few Redis nodes.
- Location history: at 33 MB/s raw, 1 day ≈ 2.85 TB; 30 days ≈ 86 TB; this is why **downsampling** is critical for the optional history store (keep 10 s for 7 days, 1 min for 30 days, 1 hour beyond).

### Connections

- File-descriptor budget: each WebSocket uses 1 fd; default Linux `ulimit -n` is 1024, raised to ~100k with tuning. With `epoll`/kernel tuning, a single process comfortably holds 50k–100k connections.
- RAM per connection: ~5–10 KB for buffers, presence flags, last-known-friend table. At 100k connections that is 0.5–1 GB just for connection state.
- 10 M CCU / 100k per server = **~100 WebSocket servers** at full load, plus replicas per AZ and headroom for rebalances.

---

## Deep Dive: ASCII Architecture Diagrams

### Diagram 1 — End-to-end write/read sequence (per location update)

```
  Alice's phone            LB        WS-Srv-1 (holds Alice)        Redis Pub/Sub        WS-Srv-2 (holds Bob)        Bob's phone
       │                    │                │                         │                       │                       │
       │  WS frame: loc upd │                │                         │                       │                       │
       │───────────────────▶│────────────────▶│                         │                       │                       │
       │                    │                │ 1) SETEX user:alice loc │                       │                       │
       │                    │                │    (TTL=60s)             │                       │                       │
       │                    │                │────────────────────────▶│                       │                       │
       │                    │                │                         │                       │                       │
       │                    │                │ 2) PUBLISH user:alice   │                       │                       │
       │                    │                │    {lat,lng,ts}         │                       │                       │
       │                    │                │────────────────────────▶│                       │                       │
       │                    │                │                         │ 3) fanout to subs     │                       │
       │                    │                │                         │──────────────────────▶│                       │
       │                    │                │                         │                       │ 4) lookup Bob's last  │
       │                    │                │                         │                       │    loc in cache        │
       │                    │                │                         │                       │    (GET user:bob)      │
       │                    │                │                         │                       │ 5) Haversine(A,B)     │
       │                    │                │                         │                       │    = 1.2 mi ≤ 5 mi     │
       │                    │                │                         │                       │ 6) WS frame to Bob    │
       │                    │                │                         │                       │──────────────────────▶│
       │                    │                │                         │                       │                       │ update UI
```

Key points: (1) and (2) are on the writer's path; (4)–(6) are on every subscriber's path. (3) is the fan-out hop where most cost hides.

### Diagram 2 — Reconnect storm after a deploy

```
        t=0s                  t=0..3s               t=3..30s            t=30..60s
        ─────                 ────────              ─────────            ──────────
Normal    │   WS-Srv-1 dies    │  1k conns/sever    │  clients retry     │  clients land
traffic   │   (deploy)        │  reconnect with    │  with backoff      │  on other
          │                    │  NO backoff        │  + jitter applied  │  servers, new
          │                    │  → thundering herd │  on client SDK     │  subs issued
          │                    │                    │                    │
          │   BAD:             │   GOOD:            │
          │   ──▶  ┌──────┐    │   ──▶  ┌──────┐    │
          │         │ LB   │    │         │ LB   │    │
          │         │ saturates   │         │ healthy │    │
          │         │ ❌          │         │ ✅     │    │
          │         └──────┘    │         └──────┘    │
```

Without exponential backoff + jitter, a deploy of a single WebSocket pod can synchronously reconnect tens of thousands of clients to the remaining servers within seconds, saturating them. Solution: SDK-side `min(max(2^n × base, cap), maxDelay)` + random jitter.

### Diagram 3 — Geo-sharded clusters

```
                      ┌──────────────────────────────────────────┐
                      │            Global Edge / DNS              │
                      └─────────────┬──────────┬──────────┬───────┘
                                    │          │          │
                          ┌─────────▼─┐  ┌─────▼────┐ ┌───▼────────┐
                          │ US-East   │  │ EU-West  │ │ APAC       │
                          │ WS cluster│  │ WS cluster│ │ WS cluster │
                          │ Redis shard│  │ Redis shard│ │ Redis shard│
                          │ (region-  │  │ (region- │ │ (region-   │
                          │  scoped   │  │  scoped  │ │  scoped    │
                          │  friends) │  │  friends)│ │  friends)  │
                          └──────────┘  └──────────┘ └────────────┘
                                    \          |          /
                                     \         |         /
                              Cross-shard Pub/Sub bridge (rare)
                              (e.g., user in EU with many US friends)
```

If a user has 400 friends but 380 are in their home region, geo-sharding keeps 95% of fan-out inside one cluster and one Redis shard, which is the only way to make this design cheap at continent scale.

---

## Deep Dive: Trade-off Tables

### 1. WebSocket vs alternatives for the server-push channel

| Property | HTTP/1.1 polling | HTTP/2 SSE | **WebSocket** | Long-poll (XHR) |
|---|---|---|---|---|
| Server-push latency | pull-interval (5–30s) | ~hundreds of ms | tens of ms | ~hundreds of ms |
| Per-conn overhead | new HTTP req each time | 1 conn, server pushes | 1 conn, full-duplex | 1 short-lived conn at a time |
| Battery cost on mobile | high | medium | **low** | medium |
| Bidirectional (client can push too) | separate POST | separate POST | **yes, single conn** | separate POST |
| Proxy / LB compatibility | excellent | good | good (sticky) | excellent |
| Failure recovery | trivial | trivial | needs reconnect | trivial |
| Best fit | tiny scale, compatibility | one-way fan-out | **bidirectional real-time** | low-scale, simple |

### 2. Pub/Sub transport: Redis Pub/Sub vs Kafka vs NATS vs gRPC streams

| Property | Redis Pub/Sub | **Apache Kafka** | NATS | gRPC server-streaming |
|---|---|---|---|---|
| Delivery guarantee | at-most-once (fire-and-forget) | at-least-once / exactly-once | at-most-once / at-least-once (JetStream) | application-level |
| Persistence | none | durable log (days) | optional (JetStream) | none |
| Throughput per cluster | ~1 M msg/s, hot | **millions/sec** | millions/sec | per-conn limited |
| Replay / late joiners | no (offline = miss) | yes (offset seek) | yes (JetStream) | no |
| Fan-out topology | in-process + cluster | consumer groups | subject-based | client-driven |
| Ops complexity | low | medium–high | low–medium | low |
| Best for | ephemeral notifications | **durable event flow** | lightweight pub/sub | RPC-like streams |

For pure real-time presence/location: Redis Pub/Sub or NATS. For anything that must survive broker restart or be replayed: Kafka.

### 3. Distance filter placement

| Place | Pros | Cons |
|---|---|---|
| Client | saves server compute | leaks raw friend locations; battery cost on the client |
| WebSocket server (per update) | **filters at the source, doesn't push to out-of-range friends** | every update costs N friend-distance checks; hot users are expensive |
| Background batch (every N seconds, scan all users in a cell) | amortizes cost; simpler | adds latency to the "appearing" experience |
| Geospatial index (Redis GEO / S2) updated in real time | O(log N) range queries | extra write path; index can lag the cache |

The "filter at the server" approach in the design above is the interview-friendly default; the production system often uses a **hybrid**: write to a geospatial index, query the index only when a UI needs a snapshot.

### 4. Update cadence: fixed vs adaptive

| Strategy | Stationary-user load | Moving-user freshness | Complexity |
|---|---|---|---|
| Fixed 30 s | 334k updates/s always | up to 30 s stale | trivial |
| Adaptive (Δ-distance threshold + min/max interval) | drops to ~30k/s when most users idle | sub-second when moving fast | medium |
| Significant-change only (cell-crossed) | minimal | seconds to minutes | medium; harder for distance UI |

---

## Deep Dive: Real-World Case Studies

### Facebook Nearby Friends (2014 launch)

Facebook's Nearby Friends launched as part of the main app's "More" tab. It was the canonical implementation of this pattern and is the source of most of the design pressures above.

- **Push channel**: a proprietary long-poll/streaming HTTP channel (the "Mara messenger" stack underneath Messenger), not raw WebSockets, for compatibility with the diverse client environments of the time. The trade-offs and topology are equivalent.
- **Storage**: the "last-known location" was kept in **TAO** (Facebook's distributed data store) as a graph node keyed by user, with a TTL. Reads from TAO were the source of truth for "where is my friend right now" queries.
- **Fan-out**: implemented as a topic-per-user system inside the messenger pipe, with the message broker colocated with the chat shards. The "only push to online friends in range" filter was applied per-subscriber.
- **Privacy**: opt-in was the gate. Even opted-in users could pause; pausing meant no publishes, which meant the TTL-expired location would mean "no longer sharing" automatically.
- **Caveat**: the "draining" behavior on TTL was a deliberate choice — Facebook did not want to maintain a separate presence channel, so absence of updates and absence of sharing were unified as "no fresh location in the last N seconds."

### Snapchat Snap Map (2017)

Snap Map is the highest-scale public example of this exact pattern. It shows anonymized friend locations on a world map, plus heat-map "action" events at venues.

- **Stack**: Snap uses its own persistent-connection gateway ("Snapchatter Connectivity Service") backed by a custom gRPC + streaming HTTP transport.
- **Update cadence**: Snap's mobile SDK uses **significant-change + activity-class triggers** rather than a fixed timer; the SDK bumps update frequency when accelerometer/CMPedometer says the user is moving.
- **Geocoding reverse lookup**: Snap Map is built on top of the **Mapbox** vector tile stack (a deliberate choice over Google Maps for licensing and customization reasons), and a **Snap-curated POI dataset** for "venues" and "actionmoji."
- **Geohashing**: Snap shards its location data using a custom hierarchical cell (publicly described as similar to H3) so that "who is in this cell right now" is a single range query on the live index.

### Apple Find My (offline finding, 2019+)

Find My solves the harder "find a friend's device even when neither side is online" problem and uses Bluetooth Low Energy broadcasts + a crowdsourced relay network — not exactly this design, but instructive.

- **Why it isn't the same problem**: in Find My, the "publisher" is the missing device (no power, no network). Relaying is done by any nearby Apple device that opportunistically forwards an encrypted BLE report to Apple.
- **The lesson for our design**: when the publisher is unreliable or offline, you cannot rely on a periodic publish-then-push model. You need **opportunistic relay** and **eventual consistency on retrieval**.
- **What it shares with nearby-friends**: the location cache with TTL, friend-relationship-gated delivery, and a strict opt-in privacy posture. Apple's design hardens the "absence means gone" assumption with a separate explicit "offline mode" the user can toggle.

### Google Maps friends-location (a.k.a. Location Sharing)

Google's "Share location" inside Maps is the most boring and instructive version of this design.

- **Transport**: persistent MQTT-over-QUIC for the live channel; HTTP fallback. The QUIC choice is driven by mobile roaming and IP changes (the connection survives network switches without reconnect, which WebSockets do not).
- **Why it's a useful comparison**: Google is unusual in that the data path (location) and the rendering (Map tiles) live in the same product. The location updates ride the same edge infrastructure that serves the map; you get "geographically local everything" essentially for free.
- **Caching**: Google's location store is **Fusion Tables / Spanner-backed** with TTL; reads are served from a strongly-consistent store, which is overkill for soft real-time but provides a clean debugging surface.

### Life360

Life360 is a long-running, location-centric family-safety app and a useful counter-example because it leans the opposite way: **consistency over freshness** for battery life.

- **Cadence**: location updates are throttled to a few per minute per user; "precision" mode (during a trip) bumps to every few seconds.
- **Architecture**: classic REST + push-notification based; less real-time than nearby-friends, more like a tracking system. Highlights the cost of "always-on high-cadence location" — battery and cellular data budget dominate the design.

### Zenly (acquired by Snap, 2017; sunset 2023)

Zenly pushed the design to its limits: real-time friend avatars, ghost trails, and venue presence.

- **Cadence**: very high (every few seconds) when active, with battery-aware fallback.
- **Why it's instructive**: Zenly demonstrated that the **federation of "context"** — venues, events, friends-of-friends — turns the location cache into a multi-tenant index where every cell has both users and places. This is the natural evolution if you ever add "nearby places my friends are at right now."

---

## Deep Dive: Common Pitfalls & Failure Modes

### 1. Stateful WebSocket pods + K8s naively killing pods on autoscaler events

**Symptom:** during a scale-in event, the HPA evicts WebSocket pods. Their clients all reconnect within ~1 s, hammering the remaining pods. Total connection count drops to ~30% then slowly climbs; p99 latencies spike; pings get queued in Redis.

**Fix:** use a Kubernetes `PodDisruptionBudget` for WebSocket pods (e.g., `minAvailable: 80%`); drain connections on `SIGTERM` (send a "please reconnect" frame, wait up to N seconds); on the client SDK, exponential backoff with full jitter.

### 2. Pub/Sub cluster saturation by a single user's friends list

**Symptom:** one user has 10,000 online friends (a "celebrity"). Every time they move, their update fans out to 10,000 downstream subscribers on the same broker node. That node's pub/sub CPU/memory saturates and all of its other users' updates stall.

**Fix:**
- Use a **server-side aggregation** step: subscribers register an interest in "any update from A" with the broker; the broker coalesces within a small window (e.g., 200 ms) so a moving user doesn't generate 5 publishes/sec downstream.
- For the truly pathological case, use a **dedicated channel cluster per shard** with the celebrity's friends hashed to a different shard, or **shard the subscriber list** across multiple brokers with consistent hashing.

### 3. Location cache TTL mismatch with update cadence

**Symptom:** users on a poor network lose connectivity for 90 s. The 60 s TTL expires their location entry, so when they reconnect their friends see "no friend here" for a moment, then a fresh update arrives, then the friend icon "pops back in." Visually jumpy and on social graphs people will report it as a bug.

**Fix:**
- Choose TTL ≥ 2× the update cadence (e.g., 60 s for 30 s updates, or 90 s for headroom).
- Distinguish "no recent update" from "explicitly offline" — only treat as offline after a longer "stale after" window (e.g., 5 minutes).
- Send a "session ended" frame on graceful disconnect so the server can actively invalidate rather than waiting for TTL.

### 4. Mobile background-mode and OS-imposed throttling

**Symptom:** iOS/Android suspend the app aggressively; in background, the WebSocket is torn down or the OS only lets the app wake every few minutes. The server sees a constant background trickle of reconnection attempts, and the "30 s update cadence" becomes "5 minutes" in practice.

**Fix:**
- Push notifications (APNs/FCM) as the cold-start signal: when a friend's location changes meaningfully, send a silent push to wake the app, then the app reconnects WebSocket and re-subscribes.
- Client SDK must distinguish "app in background" (long-poll / push-driven) from "app in foreground" (full WebSocket).

### 5. Clock skew breaking the "last seen" calculation

**Symptom:** the location cache stores `timestamp` from the client, but clients have skewed clocks (especially on Android, and especially after travel). The server's "Bob's last known location is 90 s old, treat as offline" logic misfires for users whose device clock is 60 s ahead.

**Fix:** record `server_received_at` on the server, not the client-supplied timestamp; treat that as the source of truth for "how stale is this?"; only use client timestamps for UI display.

### 6. Privacy leakage through "appeared nearby" notifications

**Symptom:** a user with sharing off should not be paged. But because the location cache is keyed by userId and the WS server has a `last_known_loc` for every user (opt-in or not, for analytics purposes), a bug in the subscribe-pipeline accidentally pushes their position to a friend.

**Fix:** the canonical "this user has sharing on" bit must be checked in the same code path that issues the subscribe; treat it as a security boundary, not a UX toggle. Add a test that subscribes as friend A → friend B and asserts no push when B's sharing flag is off.

### 7. Geofence-flipping: a user at the radius edge flickers in and out

**Symptom:** at the edge of the 5-mile radius, a user moving slowly oscillates around the boundary. Their friend sees them pop in and out of the list every 30 s.

**Fix:** apply a **hysteresis band** — e.g., show the friend when within 4.5 mi, only hide when beyond 5.5 mi. Same for time-based debouncing (require N consecutive updates outside the band before hiding).

### 8. Sticky WebSocket load balancing that defeats horizontal scale

**Symptom:** the load balancer is configured with `sticky-session` based on source IP. Mobile clients often share a NAT, so all clients behind one carrier-grade NAT land on the same WebSocket pod. That pod runs hot; others are idle.

**Fix:** use consistent hashing on a per-user identifier (or on a per-connection token) and let connections be re-established gracefully if the pod dies. Don't use IP stickiness for real-time.

---

## Deep Dive: Interview Q&A

### Q1. The interviewer pushes back: "Why WebSocket? HTTP/2 SSE gets you server-push, and it works through more proxies."

**Answer sketch.** SSE is server-push only. Nearby Friends needs the client to *also* push a location update every 30 s on the same connection, and ideally on the same channel as the server's responses (to share TCP/TLS state, heartbeat, and authentication context). With SSE you'd have an extra POST for each client update, doubling connection count, doubling the number of TLS handshakes, and adding a round trip's worth of latency. WebSockets also survive HTTP/1.1 quirks better in long-lived mobile scenarios. The trade-off is real: WebSockets need a sticky LB and a custom reconnect story, and that's a deliberate cost we accept for the bidirectional efficiency.

### Q2. How would you size this for 10x? 100x?

**Answer sketch (10x).** 100 M CCU, ~3.3 M updates/sec ingest, ~30 M pub/sub messages/sec internally. Same architecture but more shards: split the WebSocket fleet into geo-regions (US-East, US-West, EU, APAC), and put a Redis Pub/Sub shard per region. Most users' friends live in the same region, so 80%+ of fan-out stays intra-cluster. Cross-shard updates ride a small bridge tier.

**Answer sketch (100x).** 1 B CCU, ~33 M updates/sec ingest, ~300 M pub/sub messages/sec internally. This is well past "stack of Redis" and you must move to **Kafka or NATS JetStream** as the durable pub/sub layer. Each update is now a produce + consume (not a fire-and-forget publish) so the system can survive broker restarts and rebalance cleanly. A "presence service" of Redis-shards may still sit in front for fast last-known-location queries, but the fan-out backbone becomes a real streaming system.

### Q3. What if the user count is 1,000x but each user has only 5 friends?

**Answer sketch.** Fan-out is now trivial (5× per update = ~17 M msg/sec) but the number of connections is still huge (10 M concurrent). The bottleneck shifts from Pub/Sub to **WebSocket pod connection density**. Tuning matters more than ever: raise `ulimit -n` aggressively, use `epoll` (or `io_uring` on newer kernels), minimize per-connection memory, run multiple WS processes per host, and rely on **edge presence** (Cloudflare-style termination) to absorb the connection management.

### Q4. What's your consistency model? Can a friend be "displayed as in range" with an old position?

**Answer sketch.** The system is **soft real-time and eventually consistent**. There is no "exactly-once position" guarantee: a friend can be shown at position P while they're actually at P+1, because the update hasn't propagated yet. The TTL'd cache and the next update will correct this within ~30 s. We choose this over guaranteed delivery because (a) the next update naturally repairs the inconsistency, (b) at-most-once is dramatically cheaper, and (c) the user-visible behavior is "this friend is roughly here, refreshing every 30 s" — which is exactly the expectation.

### Q5. How do you handle the "celebrity" friend who has 50,000 online friends?

**Answer sketch.** Three layers of defense: (1) **subscription cap** — a single server doesn't subscribe to more than K celebrities' channels at once, with the rest coalesced into a "many-friends" channel; (2) **server-side aggregation** — coalesce rapid updates within a small window so the celebrity's 5 updates/sec become 1 per 200 ms downstream; (3) **dedicated tier** — for true super-users, give them a private channel cluster with their friends fanned across multiple brokers via consistent hashing, and let the celebrity's update ride a "broadcast" topic that all subscriber pods listen to with throttling.

### Q6. How would you make this work globally (cross-region)?

**Answer sketch.** Region-pair the WebSocket fleets. A US user with EU friends is "anchored" to the US WS cluster; the EU friends' updates cross an inter-region bridge (NATS leaf nodes or Kafka MirrorMaker) to land in the US cluster's pub/sub. To keep latency low, **default-share radius to the user's home region only** — friends abroad show up only if they're physically traveling. The cross-region bridge should be **best-effort** with an explicit "this friend is far away, lower update frequency" hint sent to the client.

### Q7. How do you test it?

**Answer sketch.** Three layers: (a) **synthetic load** — a fleet of headless WebSocket clients that publish scripted movement traces (drives around Manhattan, stationary in a coffee shop, etc.); (b) **canary region** — push new code to one region first and watch the propagation-latency SLO; (c) **chaos** — kill a Redis shard mid-test, drop a WebSocket pod, partition one AZ, and verify the system stays within its 30 s end-to-end freshness SLO without losing more than one update per user.

### Q8. Why is your fan-out model per-publish, not per-recipient-pull?

**Answer sketch.** Per-recipient-pull (each WS server polling each friend) would mean `CCU × friends × poll_rate` requests — a multiplicative disaster. Per-publish fan-out inverts the cost: one publish per update, broker fans to subscribers, subscribers do local filtering. The trade-off is that the broker's connection topology is exposed (it has to know which server holds which user), which is acceptable because the broker is a small internal tier and the topology is stable.

---

## Glossary

| Term | Definition | Common misconception |
|---|---|---|
| **WebSocket** | A persistent, full-duplex TCP connection established via HTTP upgrade. | "WebSocket is over HTTP/2." It is over TCP, started as an HTTP/1.1 Upgrade. HTTP/2 does not have WebSocket; HTTP/3 + WebSocket rides QUIC. |
| **Pub/Sub** | A messaging pattern where publishers emit to a topic/channel and subscribers receive without the publisher knowing subscribers. | "Pub/Sub is durable." Redis Pub/Sub is fire-and-forget; Kafka/NATS JetStream can be durable. Always check the durability story. |
| **Channel** (in Redis Pub/Sub) | A named bus; subscribers on a channel receive every message published to it. | "Channels are like queues." No — every subscriber gets every message. Use Streams or Kafka for consumer-group semantics. |
| **TTL (Time-to-Live)** | An expiration timestamp; the key is removed automatically when it elapses. | "TTL is exact." Redis TTLs are best-effort; expiration is lazy + periodic. Don't rely on TTL for hard deadlines. |
| **Haversine distance** | The great-circle distance between two lat/lng points on a sphere, in km. | "Haversine is fast enough; don't optimize." At 300k+ checks/sec it is, but for cheap checks use a precomputed "manhattan on a flat projection" within a small bounding box. |
| **Geohash** | A base-32 string encoding of lat/lng where shared prefixes mean spatial proximity. | "Geohash gives you a perfect grid." It does, but with significant boundary distortion at cell edges; S2 and H3 are the production-grade fixes. |
| **ISR (In-Sync Replica)** | A replica that has caught up to the leader's log; only ISR can be elected. | "All replicas are ISR." No — a lagging replica is removed from the ISR. |
| **At-most-once** | The message is delivered zero or one time; loss is acceptable. | "At-most-once is buggy." It is a deliberate choice when next-update-corrects semantics apply. |
| **At-least-once** | The message is delivered one or more times; duplicates are possible. | "At-least-once is the safe default." It is the practical default, but requires idempotent processing downstream. |
| **Exactly-once** | Each message is observed and acted on exactly one time across the system. | "Exactly-once is just a flag." It requires transactional producers + idempotent consumers or 2PC; it is real cost, not a config. |
| **Connection draining** | Stop accepting new connections, signal existing ones to reconnect, then exit. | "Pods can be killed any time." Stateful long-lived services need explicit drain; otherwise you get reconnect storms. |
| **Reconnect storm** | A synchronized mass reconnect after a server failure or deploy, overwhelming remaining servers. | "The LB will just balance them." Without client-side backoff + jitter, the LB will saturate. |
| **Hysteresis** | A threshold gap between enter and exit conditions to prevent oscillation. | "Hysteresis is overkill." It is the standard fix for boundary-flicker problems; cheap, no downside. |
| **H3 / S2** | Hierarchical spatial index systems (Uber's H3, Google's S2) that subdivide the globe into cells. | "H3 and S2 are the same." They differ in cell shape (hex vs. quad on a sphere projection) and the API. |
| **Soft real-time** | A timeliness guarantee where missing the deadline is a quality issue, not a correctness one. | "Soft real-time means sloppy." No — it means we explicitly trade guarantees for cost, and document the SLA. |
| **Geo-sharding** | Partitioning users/data by geographic region so that locality is preserved. | "Geo-sharding fixes latency." It reduces cross-shard traffic; absolute latency still needs edge presence. |
| **Backpressure** | A signal from a slower consumer to a faster producer to slow down. | "Backpressure is the broker's problem." It is the system's problem; the SDK must respect it. |
