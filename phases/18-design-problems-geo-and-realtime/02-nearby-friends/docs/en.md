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
