# Design A News Feed System

## Overview

A news feed system delivers a continuously updating list of content from followed users. This design covers both publishing and retrieval flows for a social media platform similar to Facebook, Instagram, or Twitter.

## Step 1: Problem Understanding and Design Scope

### Clarification Questions and Requirements

**Platform & Features:**
- Supports both mobile and web applications
- Core capability: users publish posts and view friends' content
- Feed sorted in reverse chronological order
- User capacity: up to 5,000 friends per account
- Traffic volume: 10 million daily active users
- Content types: text, images, and videos

## Step 2: High-Level Design

### Two Primary Flows

**Feed Publishing:** Posts written to cache and database; content propagated to friends' feeds

**News Feed Building:** Aggregates friends' posts in reverse chronological order for display

### Essential APIs

**Feed Publishing API**
```
POST /v1/me/feed
Parameters:
- content: post text
- auth_token: authentication credential
```

**News Feed Retrieval API**
```
GET /v1/me/feed
Parameters:
- auth_token: authentication credential
```

### Feed Publishing Architecture Components

- **User Layer:** Web browser or mobile app initiating requests
- **Load Balancer:** Distributes traffic across servers
- **Web Servers:** Route requests to internal services; enforce authentication and rate limiting
- **Post Service:** Persists posts in database and cache
- **Fanout Service:** Delivers content to friends' news feeds via cache
- **Notification Service:** Alerts friends about new content

### News Feed Retrieval Architecture

- **Load Balancer:** Manages incoming traffic
- **Web Servers:** Direct requests to news feed service
- **News Feed Service:** Fetches feed from cache layer
- **News Feed Cache:** Stores post IDs for rapid retrieval

## Step 3: Deep Dive Design

### Feed Publishing Deep Dive

**Web Server Responsibilities:**
- Authenticate users via auth_token
- Enforce rate limiting to prevent spam
- Validate requests before downstream processing

### Fanout Service Strategy

The fanout process delivers posts to all friends. Two competing models exist:

**Fanout on Write (Push Model)**

Strengths:
- Real-time feed generation
- Fast retrieval (pre-computed)

Weaknesses:
- Hotkey problem when users have many friends
- Wasted resources for inactive users

**Fanout on Read (Pull Model)**

Strengths:
- Efficient for inactive users
- No hotkey problem

Weaknesses:
- Slow feed fetching (on-demand computation)

**Hybrid Approach (Recommended):**
Deploy push model for typical users; implement pull model for celebrities/high-follower accounts using consistent hashing to distribute load evenly.

### Fanout Service Workflow

1. Retrieve friend IDs from graph database
2. Fetch friend information from user cache; filter based on settings (muted users, privacy restrictions)
3. Push friends list and post ID to message queue
4. Fanout workers process queue messages
5. Store post ID and user ID pairs in news feed cache
6. Cache contains only IDs (not full objects) to minimize memory; configurable limits prevent excessive storage

**Cache Structure:** News feed cache maintains `<post_id, user_id>` mappings, with newest posts appended first.

### News Feed Retrieval Deep Dive

**Retrieval Flow:**

1. User sends `/v1/me/feed` request
2. Load balancer routes to web servers
3. Web servers invoke news feed service
4. Service retrieves post IDs from news feed cache
5. Service fetches complete user and post objects from respective caches
6. Missing data fetched from databases (post DB, user DB)
7. Fully populated feed returned as JSON to client
8. Media content (images, videos) served via CDN for performance

### Cache Architecture (5-Layer Model)

| Layer | Purpose | Details |
|-------|---------|---------|
| News Feed | Feed composition | Stores post IDs |
| Content | Post data | Hot cache for popular content; separate tier for normal content |
| Social Graph | Relationships | Stores follower/following data |
| Action | User interactions | Tracks likes, replies, other engagements |
| Counters | Metrics | Like counts, reply counts, follower counts |

## Step 4: Conclusion and Scalability Considerations

### Database Scaling Topics

- Vertical vs. horizontal scaling tradeoffs
- SQL vs. NoSQL selection criteria
- Master-slave replication architecture
- Read replica deployment
- Consistency model selection
- Database sharding strategies

### Additional Design Considerations

- Maintain stateless web tier
- Maximize caching at all layers
- Deploy multiple data centers
- Use message queues for loose coupling
- Monitor key metrics: peak hour QPS, feed refresh latency

---

**References:**
- Facebook Help: How News Feed Works
- Neo4j and SQL Server friend-of-friend recommendation techniques

---

## Step 5: Back-of-the-Envelope Math

### Volumes and rates (chapter baseline, 10M DAU)

```
DAU:                10M
Avg posts/user/day: 1 post / day   (active posters are ~10% of DAU)
  → ~1M posts / day
  → ~12 posts / s average
  → peak: ~120 posts / s   (10× average)

Reads (feed fetches):
  Avg feed opens: 5 / DAU / day   = 50M feed reads / day
  = 50 × 10^6 / 86,400 ≈ 580 feed reads / s average
  Peak: 5,800 reads / s

If 10% of users have 500 friends (mid-tier), 0.1% have 5,000 friends:
  Avg fanout per post = 200 friends  (weighted: 90% × 50 + 9% × 500 + 0.1% × 5,000)
  → 1M posts × 200 = 200M feed entries / day
  → 2,300 feed entries / s average
```

### Storage sizing

```
Per feed entry:    post_id (8 B) + user_id (8 B) + author_id (8 B) + ts (4 B) = 28 B
                   but practical serialized size with overhead = ~50 B
                   With 5,000 max feed entries per user cache: 250 KB / user

Total feed cache entries:
  200M entries/day × 50 B = 10 GB / day
  Trim cache to 1,000 entries / user:
    10M users × 1,000 × 50 B = 500 GB resident cache
  Trim cache to 500 entries / user (default):
    10M × 500 × 50 B = 250 GB resident cache

Post storage (content + metadata):
  Avg post: 200 B text + ~2 MB media (image or short video)
  1M posts / day × 2 MB = 2 TB / day = 730 TB / year

User / social graph:
  10M users × (profile 1 KB + social-graph 200 KB bidirectional) ≈ 2 TB resident
  Trim to "active" subgraph in cache, fall through to graph DB on miss
```

### Fanout work and compute

```
Per-post fanout work:
  Read friend list:   1 query  ~5 ms
  Filter by prefs:    in-memory
  Enqueue N messages: ~1 ms per 1K
  Worker fanout writes: ~10 µs per feed entry (Memcached SET)

200M feed entries / day ÷ 86,400 s ≈ 2,300 writes / s average
Peak: 23K writes / s

Each worker handles ~1K writes / s (single-threaded).
Need ~25 fanout workers at peak; double for headroom and retry load.
```

### ML ranking cost (where production systems spend)

```
Candidate generation (fanout-on-write provides ~500 candidates):
  Lightweight model, ~5 ms / request
  → 5,800 reads/s × 5 ms = 29K CPU-s/s = ~30 cores

Full ranker (50–200 features, DNN):
  ~50 ms / request on a single GPU/CPU
  → 5,800 × 50 ms = 290K ms/s = 290 CPU cores  (or 2–3 GPUs at ~10× throughput)

If using fan-out-on-read, candidate generation itself becomes the dominant cost
because every read recomputes the candidate set.
```

### Capacity ladder (powers of 2)

```
Order-of-magnitude growth:
  10× to 100M DAU:
    - feed entries/day: 2B → 20B
    - cache: ~2.5 TB resident
    - post media: 7.3 PB / year
    - workers: 250 fanout, 1K read

  100× to 1B DAU (Twitter / Meta scale):
    - feed entries/day: 20B → 200B
    - post media: 73 PB / year
    - ranking infra: 100s of GPUs
    - separate cache tier for "celebrities" (millions of followers)
    - dedicated discovery + ranking + retrieval microservices
```

---

## Step 6: ASCII Architecture Diagrams

### 6.1 — End-to-end publish + fanout

```
   ┌────────────────────────┐
   │   Client (Mobile/Web)  │
   └────────────┬───────────┘
                │  POST /v1/me/feed
                ▼
   ┌──────────────────────────────────────────────────────────┐
   │                    Web Tier (stateless)                  │
   │  ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐  │
   │  │  Auth       │  │ Rate-limit  │  │ Spam / abuse     │  │
   │  └──────┬──────┘  └──────┬──────┘  └────────┬─────────┘  │
   └─────────┼────────────────┼──────────────────┼────────────┘
             │                │                  │
             ▼                ▼                  ▼
   ┌──────────────────────────────────────────────────────────┐
   │                    Post Service                          │
   │  ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐  │
   │  │  Persist    │  │  Index in   │  │  Enqueue fanout  │  │
   │  │  Post DB    │  │  Content    │  │  Kafka topic     │  │
   │  │             │  │  Cache      │  │                  │  │
   │  └──────┬──────┘  └──────┬──────┘  └────────┬─────────┘  │
   └─────────┼────────────────┼──────────────────┼────────────┘
             │                │                  │
             │                │                  ▼
             │                │      ┌──────────────────────────┐
             │                │      │   Fanout Workers         │
             │                │      │  ┌─────────────────────┐ │
             │                │      │  │ Get friend list     │ │
             │                │      │  │ Filter prefs/blocks │ │
             │                │      │  │ Hydrate entries     │ │
             │                │      │  └──────────┬──────────┘ │
             │                │      └─────────────┼────────────┘
             │                │                    │
             │                │                    ▼
             │                │      ┌──────────────────────────┐
             │                │      │  Per-user Feed Cache     │
             │                │      │  (Redis list, capped)    │
             │                │      └─────────────┬────────────┘
             │                ▼                    │
             │      ┌──────────────────────┐      │
             │      │  Notification Queue  │      │
             │      └──────────┬───────────┘      │
             │                 │                  │
             ▼                 ▼                  ▼
   ┌──────────────────────────────────────────────────────────┐
   │  Post DB │ Content Cache │ Graph DB │ Feed Cache │ Notif │
   └──────────────────────────────────────────────────────────┘
```

### 6.2 — End-to-end read (ranked feed)

```
   ┌────────────────────────┐
   │   Client (Mobile/Web)  │
   └────────────┬───────────┘
                │  GET /v1/me/feed
                ▼
   ┌──────────────────────────────────────────────────────────┐
   │                    Web Tier                              │
   └────────────────────────┬─────────────────────────────────┘
                            ▼
   ┌──────────────────────────────────────────────────────────┐
   │               News Feed Service                          │
   │  ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐  │
   │  │ Candidate   │  │ Lightweight │  │ Heavy Ranker     │  │
   │  │ Generation  │─►│ Filter      │─►│ (DNN, 50–200 fs) │  │
   │  │ (fanout-    │  │ (block list,│  │                  │  │
   │  │  on-write   │  │  seen, dedup│  │                  │  │
   │  │  + celeb    │  │  diversity) │  │                  │  │
   │  │  pull)      │  │             │  │                  │  │
   │  └──────┬──────┘  └──────┬──────┘  └────────┬─────────┘  │
   └─────────┼────────────────┼──────────────────┼────────────┘
             │                │                  │
             ▼                ▼                  ▼
   ┌──────────────────────────────────────────────────────────┐
   │  Hydration step: enrich with user objects, post objects, │
   │  media URLs, social proof (likes, comments)              │
   └────────────────────────┬─────────────────────────────────┘
                            ▼
   ┌──────────────────────────────────────────────────────────┐
   │  Response assembly (JSON / Thrift / Protobuf)            │
   └──────────────────────────────────────────────────────────┘
```

### 6.3 — Sequence: fanout on write

```
   Author    PostSrv   PostDB    Kafka     FanoutW    SocialG    FeedCache
     │           │         │         │          │          │           │
     │  POST     │         │         │          │          │           │
     │──────────►│         │         │          │          │           │
     │           │ INSERT  │         │          │          │           │
     │           │────────►│         │          │          │           │
     │           │ OK      │          │          │          │           │
     │           │◄────────│          │          │          │           │
     │           │ PRODUCE fanout(postId, authorId)            │           │
     │           │─────────────────►│          │          │           │
     │  202      │         │         │          │          │           │
     │◄──────────│         │         │          │          │           │
     │           │         │         │ CONSUME  │          │           │
     │           │         │         │─────────►│          │           │
     │           │         │         │          │ GET friends          │
     │           │         │         │          │───────────────────►│
     │           │         │         │          │ [u_2, u_5, u_7]      │
     │           │         │         │          │◄──────────────────│
     │           │         │         │          │ for each:           │
     │           │         │         │          │   LPUSH feed:u_X postId│
     │           │         │         │          │────────────────────────────────►
     │           │         │         │          │  LTRIM feed:u_X 0 999│
     │           │         │         │          │────────────────────────────────►
```

### 6.4 — Sequence: fanout on read (celebrity tier)

```
   Reader   NewsFeedSrv  CandidateG   Ranker   GraphDB   PostDB   PostCache
     │           │           │          │          │         │          │
     │ GET feed  │           │          │          │         │          │
     │──────────►│           │          │          │         │          │
     │           │ expand:   │          │          │         │          │
     │           │  followers │          │          │         │          │
     │           │─────────────────── │          │ QUERY    │         │
     │           │           │          │─────────►│         │          │
     │           │           │          │          │         │          │
     │           │           │          │◄─────────│         │          │
     │           │           │ for each celebrity:         │          │
     │           │           │ recent posts               │          │
     │           │           │ QUERY recent posts         │          │
     │           │           │────────────────────────────┼────────►│
     │           │           │           post list        │         │
     │           │           │◄────────────────────────────┼────────│
     │           │           │ combine + rank             │          │
     │           │           │──────────►│                │         │
     │           │           │  top-N  │                  │         │
     │           │           │◄─────────│                 │         │
     │           │ hydrate    │          │                │         │
     │ 200 + JSON feed       │          │                │         │
     │◄──────────│           │          │                │         │
```

---

## Step 7: Trade-off Tables

### 7.1 — Fan-out strategies

| Aspect | Fan-out on Write | Fan-out on Read | Hybrid |
|---|---|---|---|
| **Read latency** | O(1) cache hit | O(N) graph query | Mixed |
| **Write cost** | High (N writes per post) | Low (1 write) | Mixed |
| **Inactive user cost** | Wasted work | Cheap | Cheap |
| **Celebrity problem** | Severe (millions of writes) | Free | Solved by routing |
| **Freshness** | Real-time | Stale until query | Mostly real-time |
| **Cache size** | N × feed entries | Small | Both |
| **Failure mode** | Lost push = lost entry | Lost read = recomputed | Layered |
| **Used by** | Twitter (classic), Instagram | Original Facebook News Feed | Twitter post-2016, Meta today |

### 7.2 — Ranking signal families

| Signal family | Examples | Compute cost | Latency contribution |
|---|---|---|---|
| **Engagement** | Likes, comments, shares | Low (counters) | 5–10 ms |
| **Recency** | `1 / (age + 1)` | Trivial | < 1 ms |
| **Affinity** | Past interactions with author | Medium (graph lookup) | 10–20 ms |
| **Content** | Topic, language, media type | Low–medium (embeddings) | 5–20 ms |
| **Diversity** | Author / topic / media diversity | Medium (re-rank) | 5–10 ms |
| **Negative** | Block, mute, "show less" | Medium | 10 ms |
| **Trend** | Velocity of engagement in last hour | Medium (stream count) | 10 ms |

### 7.3 — Feed storage shape

| Storage | Use | Pros | Cons |
|---|---|---|---|
| **Redis list per user** | Feed timeline (ordered post IDs) | O(1) LPUSH / LRANGE, TTL support | Hot keys, capped at ~10K items |
| **Redis sorted set (score = ts)** | Time-windowed reads | Score-based filtering | Slightly slower writes |
| **Cassandra wide row per user** | Massive timelines (millions of items) | Horizontally scalable | Higher read latency |
| **TAO (Facebook's graph cache)** | Graph + feed at huge scale | Optimized for social access patterns | Bespoke; not generally available |
| **Postgres + btree on (user_id, ts DESC)** | Small-scale / hybrid | SQL ergonomics | Write amplification at high cardinality |
| **ClickHouse / event log** | Analytics + cold rebuild | Cheap, columnar | Not for online serving |

### 7.4 — Cache freshness model

| Approach | Stale window | Read cost | Failure mode |
|---|---|---|---|
| **Write-through on fanout** | Zero | One read | Coupled to write path |
| **Read-through with TTL (60 s)** | 60 s | One read + occasional miss | Acceptable |
| **Refresh-ahead (background)** | Near zero | Warm reads | Background job complexity |
| **Stale-while-revalidate** | Up to TTL but always serves | Cache hit even on miss | Slightly stale if hot item invalidates |

---

## Step 8: Real-World Case Studies

### 8.1 — Twitter timeline (the canonical case study)

Twitter's timeline architecture has been written about extensively (QCon talks 2013–2017; Twitter Engineering blog; Raffi Krikorian's famous talk).

**Pre-2016 (pure fan-out on write):**
- Tweet stored in `tweet` service (Cassandra + Manhattan KV).
- **Fanout service** delivered each tweet to the home timelines of all followers.
- ~5,000 tweets/s peak; ~150M timeline deliveries / s during big events (World Cup, elections).
- **BigBird** tier introduced for celebrities: their tweets were stored in a separate "B-tweet" service and merged into the timeline at read time, avoiding the "Taylor Swift tweets" hot-key problem.

**Post-2016 ("earlybird" + ranked timeline):**
- Switched to a **ranked** timeline using an Earlybird (Lucene-based) index for candidate generation, followed by a lightweight ML ranker.
- Reduces wasted work for inactive users (no need to materialize a timeline no one reads).
- Allows personalization — a chronological feed isn't where engagement lives.

**Lessons:**
- Pure fan-out-on-write is unsustainable past 100M+ DAU; celebrity blow-ups, inactive users, and ranking demands force the move to hybrid.
- The hybrid split must be **operationally clean** — a single ranked-blend service, not two separate code paths.

### 8.2 — Facebook News Feed (the original)

Facebook's original News Feed (2006) was **fan-out on read**:
- Posts stored once in `post` table.
- On read, the server queried all friends' recent posts, merged, sorted, returned.
- Works well at small scale; collapses past ~50M users because every read becomes a multi-way join.

**TAO (2013):** Facebook's purpose-built cache layer for the social graph and feed. TAO serves the social graph from in-memory caches with billions of QPS, fan-out is implemented inside TAO as `objects_assoc(user, post)` writes. This is the modern realization of fan-out-on-write at Meta scale.

**Ranking:** From 2011 onward, Facebook's EdgeRank gave way to ML ranking (hundreds of models, multi-stage ranking). The pipeline is now: candidate generation (graph-based) → light ranker → heavy ranker → re-rank with rules (diversity, integrity).

### 8.3 — Instagram's ranked feed

From Instagram Engineering blog:

- **Heavy use of cache-aside pattern** with Redis for the timeline cache. The cache key is `feed:{user_id}` and stores pre-computed post IDs.
- **Two cache layers:** "feed" (post IDs) and "post" (full post objects). Hydration joins the two.
- **ML ranking introduced 2016.** Pre-ranking with a lightweight model over ~500 candidates; full DNN ranker over the top 100; rules layer for diversity and integrity.
- **Story vs Feed distinction.** Stories use a separate pipeline optimized for ephemeral content; feed is the persistent timeline.
- **Rate-limited fan-out** to prevent a single celebrity post from saturating fanout workers. Workers batch inserts into the per-user cache.

### 8.4 — LinkedIn's feed

LinkedIn's feed uses **fan-out on write** with a deliberate hybrid for "Voyager" (LinkedIn's feed system, 2017+):

- **Voyager** introduced a stream processing pipeline (Apache Samza) that batches and orders fan-out operations, dramatically reducing the per-tweet cost.
- **Member-feed** materialized view maintained per member, sharded by member ID.
- **Celebrity tier** pulled at read time, blended with the materialized feed.
- **Ranking via LinkedIn's "AI-driven feed"** since 2019, with personalization signals from profile, network, and engagement.

### 8.5 — TikTok's For You feed

TikTok is the most aggressive example of **personalized recommendation** in a feed:

- **No "follow" graph at the core** — the For You feed is generated from engagement signals (watch time, completion rate, likes, shares, follows).
- **Pure fan-out-on-read** (pull) — every impression is a ranking over a candidate pool.
- **Two-stage ranking:** candidate generation via collaborative filtering (typically matrix factorization + embedding lookups over millions of candidate videos), then a multi-task DNN that predicts watch time, like, share, etc.
- **For You feed latency budget:** ~200 ms end-to-end including network. This is much tighter than the chapter baseline because each request recomputes the candidate set.
- **Cold-start** solved by exploring popular content and quickly profiling new users from their first interactions.

### 8.6 — Quora's feed (chronological + ranked hybrid)

Quora blends an answer-ranking model with follow-graph signals:

- Each user has a candidate set drawn from followed topics and writers.
- A ranker re-orders these by predicted time-spent and quality.
- Feed is capped (typ. 50–100 items per session) to encourage quality over volume.

---

## Step 9: Common Pitfalls and Failure Modes

### 9.1 — The "celebrity hot key" problem

Symptom: a single post from a user with 10M followers causes 10M cache writes, dominating fanout worker capacity for minutes. Other users' posts queue up.

Cause: pure fan-out-on-write without a celebrity tier. A single viral post is a thundering herd.

Fix: detect "celebrity" (follower count > K) and route their posts to fan-out-on-read. Cache only a "this celebrity posted" pointer; merge at read time. Twitter's BigBird is the canonical implementation.

### 9.2 — Stale feeds after privacy changes

Symptom: a user changes their post to "friends only" but friends who already had it in their feed cache can still see it for hours.

Cause: privacy / block / unfollow changes don't propagate to inboxes.

Fix: emit **invalidation events** alongside the original fanout; on privacy change, delete the post from all inboxes where it's been materialized. Maintain a reverse index `post_id → [user_id]` for fast invalidation. Twitter's "tweet delete" propagates within seconds; this is the standard.

### 9.3 — Feed pagination / cursor bugs

Symptom: users see the same post twice on infinite scroll, or skip posts entirely.

Cause: pagination cursor (offset / timestamp) doesn't account for new posts arriving between page fetches; `LIMIT 20 OFFSET 40` produces inconsistent results when the underlying list is mutated.

Fix: **cursor-based pagination** using `(timestamp, post_id)` tuples; tie-breaker ensures stable ordering even under concurrent inserts. Avoid offset pagination entirely.

### 9.4 — Cold-start for new users

Symptom: a new user signs up and sees an empty feed; never engages; churns.

Fix: seed the feed with trending posts in their geography / language, popular posts from suggested follows, and onboarding content. Track "first-week feed engagement" as a health metric.

### 9.5 — Echo chambers and "engagement-bait"

Symptom: the ranking model optimizes for clicks but the feed becomes homogeneous / rage-bait.

Cause: ML ranker rewards outrage; no diversity or integrity layer.

Fix: hard constraints in the re-ranker: max N posts per author per session, max N posts per topic cluster, "see something different" injection, downvote penalties for misinformation. Treat integrity rules as part of the contract, not optional.

### 9.6 — Timeline cache bloat

Symptom: feed cache grows unbounded; costs spike; eviction latency rises.

Cause: per-user feed cache grows up to whatever users post; LRU eviction doesn't help because every key looks "hot."

Fix: hard cap per user (typ. 500–1,000 entries via `LTRIM`). For users with 100K+ followers, prefer a streaming materialization (queue-driven) over a cache.

### 9.7 — Ranking model latency budget overrun

Symptom: feed read latency p99 jumps from 200 ms to 1 s after a model upgrade; users complain "feed is slow."

Cause: new model is 2× the size; nobody benchmarked p99 under load.

Fix: latency budget enforcement in CI: every model PR must show p99 < 200 ms at target QPS on a representative load test. Have a "fast model" fallback that automatically engages when the heavy ranker is unhealthy.

### 9.8 — Inbox vs. profile consistency

Symptom: user A deletes a post; user B's inbox still shows it as "exists"; clicking through 404s.

Cause: delete is async; inbox entries don't know about the post's lifecycle.

Fix: **tombstone** the post in the post service; on read, hydrate checks tombstones and filters out. For actively deleted content, write a "hide from feed" entry to the inbox.

### 9.9 — Time-zone / locale ordering

Symptom: a user sees "yesterday's" post as "today's" or vice versa.

Cause: server timestamps in UTC, client displays in local time; or server returns timestamps without timezone info.

Fix: ISO-8601 with explicit offset; render in user's locale on the client; for ordering, use UTC consistently on the server.

---

## Step 10: Interview Q&A

### Q1. "How do you decide between fan-out-on-write and fan-out-on-read?"

**Answer sketch:**
Three signals:
1. **Read:Write ratio.** If reads >> writes (most feeds, most of the time), fan-out-on-write pays off because it amortizes work over many reads.
2. **Follower distribution.** If follower counts are long-tailed (1% have 50% of the audience), fan-out-on-write has a celebrity problem; fan-out-on-read is safer.
3. **Personalization needs.** If you want ranked / personalized feeds, fan-out-on-write gives you pre-computed candidates; fan-out-on-read forces you to compute them every time.

In practice almost every large system uses **hybrid**: push for normal users, pull for celebrities, with a single ranked-blend service in front of both.

### Q2. "How does ranking fit into this architecture?"

**Answer sketch:**
Ranking sits on the read path between candidate generation and hydration. The fanout service produces ~500 candidate post IDs per request; the ranker scores them with a DNN; the top 20 are returned. Ranking is what makes a feed feel personalized — without it, both fan-out strategies produce the same chronological dump.

### Q3. "How do you handle a user who follows 50,000 people?"

**Answer sketch:**
Two angles. First, the **product**: most feeds cap follows (Twitter at one point capped at 5,000; LinkedIn ~3,000). Second, the **architecture**: even at 5,000 follows, the feed cache is bounded to 500–1,000 entries (LTRIM), so write amplification is bounded. The bigger problem isn't follows — it's **high fan-in** (a single followed celebrity). That's solved by the celebrity tier.

### Q4. "How do you A/B test ranking models?"

**Answer sketch:**
Bucket users by `hash(user_id, experiment_id)`. The candidate-generation service tags each response with the bucket; the ranker is configured to use model variant X for buckets A and model Y for buckets B. Metrics: time-spent, click-through, retention, downvote rate, ad revenue (if applicable). Pre-register sample size and stop conditions. Watch out for **novelty effects** — a new model often wins for 1–2 weeks then converges. Run experiments for at least 4 weeks before calling a winner.

### Q5. "Walk me through feed read latency p99 from a click to pixels on screen."

**Answer sketch:**
At 10M DAU baseline:
- DNS + TLS + connect: 30–80 ms
- Request to web tier: 1–5 ms
- Candidate generation (cache + graph): 5–10 ms
- Light filter (block, dedup, seen): 5 ms
- Heavy ranker: 20–50 ms
- Hydration (post + user objects): 10–20 ms
- Response serialization: 5 ms
- Total server-side: 50–120 ms
- Network transit to client: 20–80 ms
- Client render + image fetch (CDN): 200–500 ms

So p99 around 800 ms. The dominant cost is image / video fetch, which is why CDNs and progressive rendering are critical. Ranking is a small slice.

### Q6. "What if we 10× the DAU?"

**Answer sketch:**
Same architecture; bigger everything:
- 10× the cache size → 2.5 TB feed cache resident → need sharded Redis.
- 10× the fanout workers → 250 pods, partitioned by `hash(author_id)`.
- 10× the ranker traffic → dedicated GPU pool, or model distillation to CPU.
- 10× the post media → S3 + CDN; aggressive transcoding and image variants.
- Hot keys become more common → bigger celebrity tier (follower > 100K goes to pull).

Architecturally the design doesn't change. Operationally it's a different problem.

### Q7. "What if we go global — multiple regions?"

**Answer sketch:**
Three patterns:
1. **Read-local, write-global.** Each region has its own feed cache; writes propagate globally. Reads are local — low latency. Cost: brief inconsistency windows (typ. < 1 s) where a post in region A is not yet visible in region B.
2. **Per-region post IDs.** Posts get a region prefix; feed entries are scoped. Avoids cross-region reads for the user's "primary" feed. Cost: cross-region interactions (user in EU follows user in US) need to merge two feeds.
3. **Active-active with last-writer-wins on the post.** Use CRDTs or vector clocks for the social graph to avoid split-brain.

Most production systems use (1) with async fanout replication (Kafka MirrorMaker) and accept the small consistency window.

### Q8. "How do you stop a misbehaving user from spamming their followers' feeds?"

**Answer sketch:**
Three layers:
1. **Rate limit at the publish API** (e.g., 100 posts / hour / user; 30 / 10 minutes for new accounts).
2. **Spam / abuse classification** (ML model on post content + behavior). Flagged posts don't enter the fanout pipeline.
3. **Recipient-side suppression.** If a recipient has marked this author as muted / blocked, they're filtered out before fanout — saving work and matching user expectations.

The right answer is **layered** — none of the three alone is sufficient. Rate limiting alone allows low-quality high-volume spam; spam models alone allow novel attacks; recipient suppression alone wastes fanout work.

---

## Step 11: Glossary

| Term | Definition | Common misconception |
|---|---|---|
| **Fan-out on Write** | Materializing a per-recipient inbox at write time. | "Always faster to read." It's faster to read but the write cost scales with follower count — celebrity posts become a hot key. |
| **Fan-out on Read** | Computing the recipient's inbox at read time by querying the social graph. | "Always cheaper." It's cheaper at write but pushes cost to the read path; ranking systems need this flexibility. |
| **Candidate Generation** | Producing a small set of relevant items for a user before ranking. | "Just give me the latest posts." Without candidate generation, the ranker sees the entire corpus — infeasible at scale. |
| **Ranking** | Scoring candidates by predicted utility (click, time-spent, relevance). | "Pure ML problem." In practice, ranking is a pipeline: model + re-rank rules + diversity constraints. |
| **EdgeRank** | Facebook's 2011-era ranking algorithm based on affinity, weight, and time decay. | "Still used." Deprecated since 2011 in favor of ML ranking; the name is historical. |
| **Hot Key** | A cache key that receives disproportionately many requests, causing a single shard to overload. | "Solved by sharding." Sharding distributes writes but a single key with millions of writes/sec still overloads its shard. |
| **Materialized View** | A pre-computed data structure (the feed cache) derived from raw data (posts + graph). | "Always consistent." Materialized views are stale by definition; reconcile via async invalidation. |
| **Cursor-based Pagination** | Returning the next page using a stable cursor (timestamp + ID) rather than OFFSET. | "Same as OFFSET." OFFSET breaks under concurrent inserts; cursors don't. |
| **Cold Start** | The problem of serving a new user with no engagement history. | "Solved by onboarding." Onboarding helps but true cold start requires exploration / bandit policies. |
| **Diversity Re-ranker** | A post-ranking stage that enforces variety (max N posts per author, topic, etc.). | "Anti-engagement." It trades some engagement for trust and long-term retention. |
| **TAO** | Facebook's distributed data store for the social graph and feed, optimized for billions of QPS. | "Publicly available." It isn't; it's bespoke Facebook infrastructure. |
| **Wide Row** | A storage pattern (Cassandra-style) where one partition contains many columns, ideal for per-user feed timelines. | "Same as a SQL row." Wide rows can have millions of columns and span multiple physical pages. |