# Real-Time Gaming Leaderboard

## Step 1: Understanding the Problem and Establishing Design Scope

### Clarification Questions and Answers

| Question | Answer |
|----------|--------|
| Score calculation method | Users earn 1 point per match win |
| All players included? | Yes |
| Time segmentation | New tournament/leaderboard each month |
| Focus on top users? | Top 10 plus a specific user position and ±4 surrounding users |
| User scale | 5M daily active users; 25M monthly active users |
| Daily match volume | Average 10 matches per player daily |
| Tie handling | Same rank assigned; can break ties by timestamp if needed |
| Real-time requirement | Yes, real-time or near-real-time results required |

### Functional Requirements
- Display top 10 players on the leaderboard
- Show a user's specific rank
- Display players positioned four places above and below a desired user (bonus feature)

### Non-Functional Requirements
- Real-time score updates reflected on the leaderboard immediately
- General scalability, availability, and reliability

### Back-of-the-Envelope Estimation

**User Load:**
- 5M DAU over 24 hours = ~50 users/second average
- Peak: 5x average = 250 users/second

**QPS for Score Updates:**
- Average: 50 users/sec × 10 games/day = ~500 QPS
- Peak: 500 × 5 = 2,500 QPS

**QPS for Fetching Top 10:** ~50 (users load top 10 on first open daily)

---

## Step 2: High-Level Design and Buy-In

### API Design

#### POST /v1/scores
Update a user's position after winning a game.

**Request Parameters:** `user_id` (winner), `points` (points gained)
**Response:** 200 OK (updated) / 400 Bad Request (failed)

#### GET /v1/scores
Fetch the top 10 players.
```json
{
  "data": [
    { "user_id": "user_id1", "user_name": "alice", "rank": 1, "score": 12543 },
    { "user_id": "user_id2", "user_name": "bob", "rank": 2, "score": 11500 }
  ],
  "total": 10
}
```

#### GET /v1/scores/{:user_id}
Fetch the rank of a specific user.
```json
{ "user_info": { "user_id": "user5", "score": 1000, "rank": 6 } }
```

### High-Level Architecture

**Two main services:**
1. **Game Service:** Lets users play and validates wins
2. **Leaderboard Service:** Creates, maintains, and displays the leaderboard

**Data Flow:**
1. Player wins → request sent to Game Service
2. Game Service validates win → calls Leaderboard Service to update score
3. Leaderboard Service updates the Leaderboard Store
4. Player requests leaderboard data directly from Leaderboard Service

### Design Trade-offs

#### Should the Client Talk to Leaderboard Service Directly?
**Current:** Client → Game Service → Leaderboard Service.
**Rejected alternative (direct client access):** insecure; vulnerable to man-in-the-middle attacks where players modify scores. Server-side scoring required. **Exception:** server-authoritative games (e.g., online poker) handle all logic on game servers.

#### Should We Use a Message Queue?
Kafka could distribute score data to multiple consumers (leaderboard, analytics, push notifications). Not included in the primary design since multiple consumers weren't explicitly required, but could be added for turn-based/multiplayer notification scenarios.

---

## Step 3: Data Models

### Solution 1: Relational Database (RDS)

**Leaderboard Table:** `user_id (varchar) | score (int)`

**When a user wins a point:**
- New user: `INSERT INTO leaderboard (user_id, score) VALUES ('mary1934', 1);`
- Existing: `UPDATE leaderboard SET score=score + 1 WHERE user_id='mary1934';`

**Finding a user's rank:**
```sql
SELECT (@rownum := @rownum + 1) AS rank, user_id, score
FROM leaderboard
ORDER BY score DESC;
```

**Performance Issues:**
- Sorting millions of rows for exact rank is extremely slow (10+ seconds)
- Not suitable for real-time; poor scalability with constant updates
- Caching infeasible due to constant updates; table scans inefficient

A `LIMIT 10` optimization only helps top results, not mid-leaderboard rank calculation.

### Solution 2: Redis with Sorted Sets

**Why Sorted Sets:** members unique (one per user), each member has a score, members auto-ranked by score, fast read/write.

**Internal Architecture (two data structures):**
1. **Hash table:** maps users → scores
2. **Skip list:** maps scores → users for efficient ordering

**Skip List:** layered index structure; each level skips nodes of the level below, giving O(log n) insert/remove/search (vs. O(n) for a plain linked list).

**Redis Operations:**
| Operation | Complexity | Purpose |
|-----------|-----------|---------|
| ZADD | O(log n) | Insert user or update score |
| ZINCRBY | O(log n) | Increment user's score; assumes 0 if new |
| ZRANGE / ZREVRANGE | O(log n + m) | Fetch range of users (m = entries fetched) |
| ZRANK / ZREVRANK | O(log n) | Get position of any user |

**Implementation Workflow:**
- **User scores a point:** `ZINCRBY leaderboard_feb_2021 1 'mary1934'` (monthly sorted set created fresh; previous months archived)
- **Fetch top 10:** `ZREVRANGE leaderboard_feb_2021 0 9 WITHSCORES`
- **Fetch user position:** `ZREVRANK leaderboard_feb_2021 'mary1934'`
- **Fetch relative position (±4):** if rank is 361, `ZREVRANGE leaderboard_feb_2021 357 365`

**Storage Requirements:**
- Per user: 24-char user ID + 2-byte score = 26 bytes
- Worst case (25M MAU): 26 × 25M = 650 MB; with skip list + hash overhead ~1.3 GB
- **Single modern Redis server is sufficient.** Peak update QPS 2,500/sec is well within single-Redis capacity.

**Persistence and Reliability:**
- Redis is in-memory; node failure causes data loss
- Configure a read replica; on failure, promote replica and attach a new one
- **Supporting MySQL tables:** User data + Point history (user_id, score, timestamp). Enables play history and disaster recovery (rebuild Redis from point history)
- **Optional:** cache top-10 user details separately

---

## Step 4: Design Deep Dive

### Decision 1: Cloud Provider vs. Self-Managed

#### Option 1: Manage Your Own Services
- Monthly sorted set in Redis
- User details in MySQL (name, profile image)
- Optional Redis user-profile cache for top 10
- Load-balanced web servers handle API requests; query Redis + DB, using profile cache for top 10

#### Option 2: Build on Cloud (AWS)
- **Amazon API Gateway** defines HTTP REST endpoints
- **AWS Lambda** for serverless compute

| API Endpoint | Lambda Function |
|--------------|-----------------|
| GET /v1/scores | LeaderboardFetchTop10 |
| GET /v1/scores/{:user_id} | LeaderboardFetchPlayerRank |
| POST /v1/scores | LeaderboardUpdateScore |

**Advantages:** no provisioning, automatic scaling with DAU growth, AWS-managed environment, cost-effective for variable loads. **Recommendation:** serverless preferred for new implementations. Alternatives: Google Cloud Functions, Azure Functions.

### Scaling Redis for Massive Scale (500M DAU, 100x)
- Leaderboard size: ~65 GB; Peak QPS: ~250,000/sec
- Single Redis node insufficient → data sharding

#### Sharding Approach 1: Fixed Partition
Divide score range into fixed buckets (e.g., 10 shards: 1-100, 101-200, …, 901-1000).
- **Insert/update:** determine score from MySQL → identify shard → update; if score crosses a boundary, remove from old shard, add to new shard
- **Find rank:** local rank within shard + count of all users in higher shards
- **Fetch top 10:** query the highest-range shard
- **Optimization:** secondary cache mapping user_id → score to avoid MySQL lookups

#### Sharding Approach 2: Hash Partition (Redis Cluster)
- Redis Cluster uses 16,384 hash slots; slot = `CRC16(key) % 16384`
- Each node manages a slot range; adding/removing nodes only reassigns slot ranges
- **Fetch top 10:** scatter-gather — query top 10 from each shard, application merges/sorts
- **Limitations:** high latency for large K, latency bound by slowest partition, no straightforward per-user rank
- **Recommendation:** fixed partition preferred over hash partition for rank simplicity

**Redis Node Sizing:** allocate ~2x expected data for write-heavy workloads (snapshot creation); use redis-benchmark for capacity planning.

### Alternative: NoSQL (DynamoDB)
Desired properties: optimized for heavy writes, efficient sorting within a partition.

**Initial design problem:** linear scan to find top scores doesn't scale.

**Global Secondary Index iteration 1:** partition key `game_name#{year-month}` (e.g., `chess#2020-02`), sort key `score` → creates a **hot partition** (all current-month users in one partition).

**Solution — Write Sharding:** partition key `game_name#{year-month}#p{partition_number}`, with partition number = `user_id % number_of_partitions`.
| Partition Key | Sort Key | Attributes |
|---|---|---|
| chess#2020-02#p0 | score | user_id, email, profile_pic |
| chess#2020-02#p1 | score | user_id, email, profile_pic |
| chess#2020-02#p2 | score | user_id, email, profile_pic |

**Trade-off:** reduced per-partition load vs. increased read complexity (must query all partitions). Partition count based on write volume/DAU; requires benchmarking.

**Fetch top 10:** scatter-gather across partitions, merge/sort 30 entries → global top 10.

**User rank queries — Percentile Ranking:** instead of exact rank, return percentile (e.g., "top 10-20%"). A cron job analyzes per-shard distribution and caches percentile boundaries. Assumes roughly similar distributions across shards.

---

## Step 4: Wrap-Up and Additional Considerations

### Real-Time Performance Optimizations
- **Redis hash for user display data:** map user_id → user object (names, images) for faster retrieval than DB
- **Tie-breaking:** store user_id → timestamp of most recent win; on equal scores, earlier timestamp ranks higher

### System Failure Recovery
1. MySQL point table holds user_id, score_awarded, timestamp per win
2. Iterate entries, calling `ZINCRBY` once per win
3. Rebuild leaderboard offline; restore from snapshot once rebuilt

Historical data enables complete reconstruction without data loss.

## Key Takeaways
1. Redis sorted sets are ideal for real-time leaderboards at millions of users
2. Skip lists give O(log n) ranking operations
3. Fixed partitioning scales better than hash partitioning for rank queries
4. Write sharding with NoSQL needs careful load distribution
5. Serverless (Lambda) simplifies infrastructure for variable loads
6. MySQL point table enables disaster recovery
7. Percentile ranking can substitute exact ranks at massive scale

---

## Back-of-the-Envelope Math (Extended)

### Storage math, made concrete

Suppose 25M MAU, monthly leaderboard, 1 point per win, integer scores.

| Item | Math | Result |
|------|------|--------|
| Member string length | UUID with dashes | 36 bytes |
| Score field | double (IEEE 754) | 8 bytes |
| Hash table entry overhead | pointer + key + value | ~50 bytes |
| Skip list node | level + span + backward + score + member | ~32 bytes (avg) |
| **Per-user footprint** | 36 + 8 + 50 + 32 | **~126 bytes** |
| **25M users** | 126 × 25,000,000 | **~3.15 GB** |
| With fragmentation (2x) | | **~6.3 GB** |

This fits comfortably in a single `cache.r6g.4xlarge` AWS ElastiCache node (~25 GB usable). At 100x scale (2.5B MAU), you'd need ~315 GB; one node no longer fits — that's the sharding point.

### QPS math, peak vs average

- Average win QPS: 5M DAU × 10 wins/day ÷ 86,400 s ≈ 578 QPS.
- Peak is not "5x average" by accident. It comes from the *shape* of the daily curve. Empirically, gaming load is heavily concentrated: ~50% of daily volume happens in the top 6 hours, and within that the top hour can be ~25% of daily volume.
- That implies peak QPS ≈ daily volume / 3600 s × ~2.5 (a "rush factor"): 5M × 10 / 3600 × 2.5 ≈ **34,700 QPS**, not 2,500.
- This 14x gap is the difference between "fits one Redis" and "needs sharding today." Always ask the interviewer what peak-to-average ratio they assume.

### Read QPS math

- Top-10 fetch is on the **hot path**: every active user opening the home screen triggers one.
- A typical mobile game re-opens the leaderboard screen 2–3 times per session; with 5M DAU averaging 3 sessions of 20 minutes each, the top-10 endpoint sees ~5M × 3 = 15M reads/day.
- 15M ÷ 86,400 ≈ 174 QPS average, but spiky — multiply by 5–10x peak and you are at ~1,500 QPS on a tiny payload (under 1 KB). This is exactly the access pattern that benefits from an in-memory cache with sub-millisecond response.

### Why percentile rank beats exact rank at scale

A user's exact rank requires either (a) a global sort or (b) maintaining counts per score. At 2.5B entries, neither is cheap. If you store per-shard histograms and a global "score → cumulative count" map updated periodically, you can answer "user X is in the top 0.3%" in O(log S) where S is the number of score buckets (a few hundred). The error band is small for most users and only matters near the top.

---

## ASCII Architecture Diagrams

### Diagram 1 — Write path: win event to sorted set

```
  Player          Game           Leaderboard           Redis          MySQL
    │              Server            Service            (sorted set)   (history)
    │               │                  │                    │            │
    │  match win    │                  │                    │            │
    │──────────────►│                  │                    │            │
    │               │  validate win    │                    │            │
    │               │  (server-        │                    │            │
    │               │   authoritative) │                    │            │
    │               │                  │                    │            │
    │               │  POST /v1/scores │                    │            │
    │               │  (idempotency    │                    │            │
    │               │   key = UUID)    │                    │            │
    │               │─────────────────►│                    │            │
    │               │                  │  INSERT            │            │
    │               │                  │  history row       │            │
    │               │                  │────────────────────────────────►│
    │               │                  │                    │            │
    │               │                  │  ZINCRBY           │            │
    │               │                  │  monthly:set       │            │
    │               │                  │  user_id +1        │            │
    │               │                  │───────────────────►│            │
    │               │                  │                    │            │
    │               │                  │  200 OK            │            │
    │               │◄─────────────────│◄───────────────────│            │
    │               │                  │                    │            │
    │  win          │                  │                    │            │
    │  confirmed    │                  │                    │            │
    │◄──────────────│                  │                    │            │
    │               │                  │                    │            │
    │               │                  │  async: publish    │            │
    │               │                  │  to Kafka (fan-out │            │
    │               │                  │  to analytics,     │            │
    │               │                  │  notifications)    │            │
    │               │                  │═══════════════════►│
```

The write path is two durable steps — MySQL history then Redis increment. Redis is the **fast read source**; MySQL is the **durable audit log**. If Redis crashes, replay MySQL into a fresh Redis; if MySQL is briefly unavailable, you queue the write (Kafka) and reconcile.

### Diagram 2 — Read path: top-10 and per-user rank

```
  Client         API          Leaderboard       Redis        Redis Hash     MySQL
                 Gateway      Service           sorted set   user:profile   users
    │              │              │                  │            │            │
    │  GET /v1/    │              │                  │            │            │
    │  scores      │              │                  │            │            │
    │─────────────►│              │                  │            │            │
    │              │  forward     │                  │            │            │
    │              │─────────────►│                  │            │            │
    │              │              │  ZREVRANGE       │            │            │
    │              │              │  0 9 WITHSCORES  │            │            │
    │              │              │─────────────────►│            │            │
    │              │              │  10 user_ids     │            │            │
    │              │              │◄─────────────────│            │            │
    │              │              │                  │            │            │
    │              │              │  HMGET           │            │            │
    │              │              │  user:profile    │            │            │
    │              │              │  id1,id2,..id10  │            │            │
    │              │              │─────────────────────────────────►│         │
    │              │              │  names + avatars │            │            │
    │              │              │◄─────────────────────────────────│         │
    │              │              │                  │            │            │
    │              │              │  (cache miss?    │            │            │
    │              │              │   fall through   │            │            │
    │              │              │   to MySQL)      │            │            │
    │              │              │──────────────────────────────────────────►│
    │              │              │                  │            │            │
    │              │              │  rank map        │            │            │
    │              │  200 JSON    │                  │            │            │
    │◄─────────────│◄─────────────│                  │            │            │
```

Top-10 reads are O(log n + 10). Profile enrichment is a single batched `HMGET` against a second Redis hash (a materialized projection of the users table). The MySQL fallback is cold; in steady state the hash is hit 99%+.

### Diagram 3 — Sharded leaderboard (fixed partition by score band)

```
                         ┌──────────────┐
                         │ Leaderboard  │
                         │   Service    │
                         └──────┬───────┘
                                │  ZINCRBY user, +1
                                │  user_score -> shard
                                │
       ┌───────────┬────────────┼────────────┬───────────┐
       ▼           ▼            ▼            ▼           ▼
  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
  │ Shard 0 │ │ Shard 1 │ │ Shard 2 │ │  ...    │ │ Shard 9 │
  │ 1-1000  │ │1001-2k  │ │2k1-3k   │ │         │ │9k1-10k  │
  │ (ZSET)  │ │ (ZSET)  │ │ (ZSET)  │ │         │ │ (ZSET)  │
  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘

  Rank query for user with score 5400 (shard 5):
   1. local_rank = ZREVRANK shard5 user
   2. global_rank = sum(cardinality of shards 6..9) + local_rank + 1
   3. return global_rank
```

Fixed partition makes global rank *one sum + one local rank* — O(1) per shard for the count, O(log n) for the local rank. No scatter-gather for rank queries. Compare with hash partition (16k slots) where every rank query fans out to all primaries.

### Diagram 4 — Event-sourced write fan-out (for very large scale)

```
   Game ─► Kafka ─┬─► Leaderboard writer ─► Redis (sorted set, sharded)
                  ├─► Analytics writer    ─► ClickHouse / BigQuery
                  ├─► Notification writer  ─► Push / Email / Inbox
                  ├─► Anti-cheat writer    ─► Streaming rules engine
                  └─► Audit / Compliance   ─► Cold object store (S3)
```

Once you have Kafka in the path, the leaderboard is just *one* consumer of an immutable win-event log. The same event feeds analytics, anti-cheat, push notifications, and compliance — exactly the "fan-out" pattern that justifies introducing a queue in the first place.

---

## Trade-off Tables

### Storage / engine choice

| Option | Latency (P50 read) | Throughput (writes/sec) | Operational complexity | Cost @ 25M MAU | Best fit |
|--------|--------------------|-------------------------|------------------------|----------------|----------|
| MySQL + indexes | 50–500 ms | 1k–5k (with row locks) | Low (familiar) | $ (single RDS) | < 1M DAU, infrequent updates |
| Redis sorted set (single) | < 1 ms | 100k–500k | Low (single node) | $$ (RAM-bound) | < 25M MAU, real-time reads |
| Redis Cluster (hash shards) | 1–5 ms | 1M+ (aggregate) | High (shard ops) | $$$ | Hundreds of M MAU, exact rank not required |
| Fixed-partition sharded Redis | < 2 ms | 500k–2M | Medium (rebalance scripts) | $$$ | Real-time top-K + per-user rank at scale |
| DynamoDB (write-sharded) | 5–15 ms | Millions (per partition 1k) | Low (managed) | $$$ (per WCU/RCU) | Variable load, serverless preferred |
| Spanner / CockroachDB | 10–30 ms | 10k–100k | High (DB admin) | $$$$ | Global, strongly consistent, financial |
| ClickHouse / Druid (analytical) | 50–200 ms (queries) | 1M+ ingest | Medium | $$ | Analytics-heavy, not real-time |

### Sharding strategy for ranks

| Strategy | Top-10 latency | Per-user rank latency | Rebalancing | When to pick |
|----------|----------------|------------------------|-------------|--------------|
| Single sorted set | sub-ms | sub-ms | N/A | Fits in one node |
| Hash partition (Redis Cluster) | parallel query, O(K) | O(K) per shard | Slot migration | Need horizontal write scale, no per-user rank SLA |
| Fixed partition by score band | O(1) shard read | O(1) global rank | Manual re-banding | Real-time rank + top-K at 100M+ users |
| Time-bucketed (per-tournament) | trivial | trivial | None | Independent leaderboards (no cross-tournament rank) |
| Geohash / regional | parallel per region | parallel per region | Re-shard on growth | Multi-region with regulatory data residency |

### Real-time push (live top-10 changes)

| Mechanism | Freshness | Server cost | Client cost | Best for |
|-----------|-----------|-------------|-------------|----------|
| Client polls every 5 s | 0–5 s | High (read amp) | Battery hit | Low-budget, small DAU |
| WebSocket / SSE | sub-second | Medium (conn. state) | Live | Casual games with sub-1s feel |
| Server-Sent Events from leaderboard change feed | sub-second | Medium | Live | Mid-scale, real-time |
| Long-poll (Comet) | sub-second | High (held conn) | High latency feel | Legacy clients only |
| Push notification (APNs/FCM) on rank change | tens of seconds | Low | Battery-friendly | Tournament end / milestone alerts |

### Update semantics on ties

| Tie rule | User-visible behavior | Storage cost | Perceived fairness |
|----------|------------------------|--------------|---------------------|
| No tie-break (same rank for equal scores) | Two users share rank 5 | Cheapest | "I beat them, why same rank?" |
| Earlier timestamp wins | First to reach score wins | One timestamp per member | Strict fairness, but timestamp updates on every increment |
| Lower user_id wins | Deterministic, no extra writes | None | "Why is my account 2nd even though I scored later?" |
| Higher user_id wins (anti-sniper) | Pushes late tie-breakers up | None | Discourages last-second score boosts |

### Anti-cheat placement

| Where | What it catches | What it misses |
|-------|-----------------|----------------|
| Client-only | Cosmetic anomalies | Real cheats (any server-unaware check is theatre) |
| Game server | Game-rule violations | Statistical exploits, account networks |
| Leaderboard writer | Sudden score spikes, impossible rates | Slow-pattern cheats, multi-accounting |
| Streaming rules engine (Kafka side) | Cross-user patterns, collusion | Sophisticated emulation farms |
| Manual review (flagged) | Everything | Volume-limited; needs automated prior filters |

---

## Real-World Case Studies

### Halo / Bungie — TrueSkill ranking

Halo 2 (2004) and onward used Microsoft's **TrueSkill** ranking system, a Bayesian skill rating for 1v1 and team play. Halo 3 (2007) and Halo: Reach scaled TrueSkill to **millions of players** with daily updates. The engineering takeaway: skill rating is *not* a sorted set of integers. It's a per-player **mean μ and variance σ²** that updates after each match. A leaderboard surface still uses a sorted set keyed by a projected skill (μ − 2σ, "conservative skill"), but the **authoritative state is per-player parameters in a relational store**. Bungie later moved Halo Infinite's skill tracking to a service called "TACL" (True Skill and Matchmaking) — concrete confirmation that ranking *math* and ranking *storage* are separate problems.

### Fortnite — seasonal leaderboard at hyperscale

Epic Games' Fortnite runs a monthly/seasonal leaderboard that ingests match results from a global player base that has peaked above 200M MAU. Lessons reported in Epic SRE and Unreal Engine talks:

- **Match results flow through Kafka** with millions of events per minute. A **dedicated leaderboard service** consumes these events; it does not share a write path with gameplay.
- The live top-K is served from **in-memory structures** (Redis sorted sets and a custom in-process ranking service) and the **per-user rank** comes from the same store.
- The "stats" page (per-user lifetime stats) is built by a **batch pipeline** (Spark / BigQuery) that recomputes aggregates offline. Online answers are projections of those aggregates — never the source of truth.
- Live updates reach clients via **WebSocket / push** with rate-limited "rank-change" notifications (a deltas feed, not a full snapshot on every change).

### League of Legends — MMR, LP, and tier splits

Riot's League of Legends separates three concepts:

- **MMR (Matchmaking Rating)** — hidden, integer, used to matchmake. Updated after every ranked game.
- **LP (League Points)** — visible, integer, the "rank bar" you see in the client. Earned per win, lost per loss.
- **Tier / division** — derived from LP, e.g., Gold IV with 75 LP.

The leaderboard is **not** "sort all players by MMR." The visible surface is *per-tier* (Iron, Bronze, Silver, ..., Challenger) with **Challenger / Grandmaster / Master** being the only tiers where you see an actual ranked list across a region. Riot publishes the player count cap for Challenger (300) per region — an admission that the global cross-tier exact rank is **not** a product feature. Engineering takeaway: pick a *visible* leaderboard surface and *own* its semantics; don't expose internal ranking math.

### Roblox — multi-game leaderboards

Roblox's leaderboards are **per-experience** (per game), not global. Each experience has up to a few thousand concurrent players, with leaderboards that fit comfortably in one Redis instance. The engineering at Roblox's scale is in the **platform**: a leaderboard service that game developers call via a simple API. This shifts the design from "one massive leaderboard" to "tens of millions of small leaderboards." Storage math: 10M experiences × 1 MB per leaderboard = 10 TB; that's no longer a Redis problem, it's a sharded multi-tenant key-value problem.

### Zynga — abuse-driven design

Zynga's social games (Words With Friends, FarmVille) exposed leaderboards that were heavily targeted by **score inflation and account farming**. Their reported design choices:

- **Server-authoritative** scoring for all ranked play — never trust the client.
- A **streaming fraud pipeline** that watches for statistical anomalies (score rate, playtime distribution, network patterns) and quarantines suspicious accounts.
- **Time-windowed leaderboards** (daily, weekly) so cheats have a short blast radius.

The pattern: at scale, *anti-cheat* is part of the leaderboard design, not an afterthought.

### Google — Spanner-backed leaderboard for Google Play Games

Google Play Games uses **Cloud Spanner** as the backing store for cross-device leaderboards. Spanner provides global strong consistency with external consistency (TrueTime), which means "your friend's score that just appeared on their phone" is immediately visible to you. The trade-off: Spanner is ~10–30ms per read, ~5–10ms per write — 10–100x slower than Redis but globally consistent and durable. For Play Games' use case (player count is small, global consistency matters), Spanner is the right call. For high-frequency competitive games, it isn't.

### Redis sorted sets — how it actually works

Redis's `ZADD` is implemented as:

1. Look up the member in the **hash table** (O(1)) to get its current score.
2. If found and the score changes, **remove the member from the skip list** at the old score and **insert** it at the new score (O(log n)).
3. Update the hash table entry.

`ZINCRBY` is `ZADD` with `INCR` — same complexity, plus the increment.

A Redis sorted set with N members has a skip list of expected depth O(log N) (typically ~32 levels for billions of entries). The **rank query** (`ZRANK` / `ZREVRANK`) walks the skip list from the head using cumulative "span" fields — every node knows how many nodes it skips at its level, so a rank is computable in O(log n) without scanning.

### Dragonfly and KeyDB — multi-threaded Redis forks

- **KeyDB** (Snap, 2019): a Redis fork that is multi-threaded for network I/O and certain commands. Same wire protocol, same sorted-set semantics, ~2–5x throughput on multi-core boxes.
- **Dragonfly** (DragonflyDB, 2022): a from-scratch Redis-compatible server, **shared-nothing, multi-threaded** for the entire data path. Published benchmarks of ~1M ops/sec per node on a 32-core box for typical workloads.
- Sorted sets in both are still O(log n) per operation; the wins are in **concurrent client handling** and **memory efficiency** (Dragonfly reports ~30% less RAM per entry for hash-heavy workloads).

The interview angle: "Redis doesn't scale" is no longer accurate in 2024+. Single-threaded Redis is fine to ~100–500k ops/sec; beyond that, look at forks or sharding.

---

## Common Pitfalls & Failure Modes

### Pitfall 1 — "We can just use a `SELECT ... ORDER BY score DESC LIMIT 10`"

This works on day one with 10k users. It silently degrades to "we time out at 8 PM every day when the player peak hits" at 1M users. **Symptom**: top-10 endpoint P99 spikes during peak hours. **Diagnosis**: `EXPLAIN` shows a full sort with no usable index. **Fix**: move to Redis sorted sets before you launch, not after.

A related trap: using the same query for **per-user rank** with a counter trick (`SELECT COUNT(*) FROM leaderboard WHERE score > ?`). That works on a small table; on 25M rows it becomes a sequential scan of 25M rows per request, killing both the leaderboard DB and anything else sharing it.

### Pitfall 2 — Trusting the client score

The chapter's `POST /v1/scores` is documented as called by the **Game Service**, not the client. This is not a stylistic choice — it is the entire security posture. If a client can `POST /v1/scores { user_id: "attacker", points: 999999 }`, the leaderboard is meaningless. The single most important line in this design is "Game Service validates win" — *before* the score update.

A weaker version of the same pitfall: client sends the score *and* the game result, and the server "validates" by trusting the client payload. The fix is to make the game itself server-authoritative: the server runs the simulation, or the server verifies the result cryptographically (signed move receipts, server-issued seeds, etc.).

### Pitfall 3 — Hot keys in the sorted set

When a few players are streaming in scores (e.g., a Twitch streamer playing a tournament live), they generate a write rate orders of magnitude above the average. On a single Redis node this is fine. On Redis Cluster with hash sharding by user_id, it can create **hot shard** problems if the hot users hash to the same slot. Mitigations:

- **Pre-shard hot users** by routing their writes to a dedicated shard.
- **Batch / coalesce** writes from the same user (e.g., one `ZINCRBY` per second rather than per match event).
- **Local top-K cache** for the most-watched players — bypass the sorted set entirely for them.

### Pitfall 4 — Race conditions on rank

A player has rank 100 at time T₀. They play three games between T₀ and T₁. Each win is a `ZINCRBY` followed by a `ZREVRANK`. Between the second and third win, another player who was at rank 99 wins too. At T₁, the original player's rank is 98, not 97 as they expected. **This is not a bug — it's the reality of a live leaderboard**. If "rank N at the moment I won" matters (e.g., for rewards), the application must capture rank inside the same atomic operation as the increment. Redis's `EVAL` (Lua scripting) can do this atomically:

```lua
-- Atomic: increment, return new rank
local new_score = redis.call('ZINCRBY', KEYS[1], ARGV[1], ARGV[2])
local new_rank = redis.call('ZREVRANK', KEYS[1], ARGV[2])
return { new_score, new_rank }
```

Calling `EVAL "..." 1 leaderboard:2026-06 1 user42` returns `(score, rank)` in a single atomic step. The alternative — increment, then rank, with retries — is a race condition waiting to ship.

### Pitfall 5 — "Redis is in memory, so it's fast" applied to persistence

Redis is fast for reads because data is in RAM. Redis is **not** fast for `BGSAVE` (a full snapshot) or for the AOF rewrite — those touch the disk and the main thread can stall. The pitfall: deploying Redis on a disk that can't sustain the snapshot write rate, and getting P99 latency spikes every minute (when `BGSAVE` runs by default) or every few hours (when AOF rewrite triggers).

Mitigations:

- Schedule `BGSAVE` to a quiet hour if traffic is bursty.
- Use AOF with `everysec` (not `always`) and accept ≤ 1 second of potential loss.
- Use a disk with provisioned IOPS (io1/io2 on AWS), not gp2/gp3 burst credits.
- Allocate `maxmemory` with headroom for fork copy-on-write — `maxmemory = 0.5 × RAM` is a safe rule during heavy writes.

### Pitfall 6 — Score updates lost on Redis crash

Without persistence, a Redis crash loses all in-flight scores. Even with AOF `everysec`, you can lose up to one second of writes. For most leaderboards, that means "the top 10 looked wrong for a few seconds after recovery" — usually acceptable. For some products (paid tournaments with real-money rewards), it's not.

The durable answer is the chapter's design: **the MySQL point-history table is the system of record**. Redis is a derived, fast view. If Redis is empty, you can rebuild it deterministically from MySQL. The cost is that MySQL must keep up with peak write QPS. At 2,500 QPS, this is trivial. At 250,000 QPS, it requires sharded MySQL or a streaming pipeline (Kafka + per-shard reducer).

### Pitfall 7 — "Just cache the top 10 forever"

A common over-optimization: cache `GET /v1/scores` for 60 seconds. Result: the leaderboard updates every 60 seconds, not in real time, and the product loses the live feel. The fix: cache **the user details** (names, avatars), not the **ranking itself**. The ranking changes frequently; the metadata rarely does. Cache the 10 user_ids, then fetch the metadata in a single `HMGET` against a per-user hash with a long TTL.

### Pitfall 8 — Confusing "rank" with "score percentile"

If the product asks for "what percentile am I in?", don't compute it by walking the sorted set. Maintain a **score histogram** (Redis `HINCRBY` on bucketed scores) updated alongside `ZINCRBY`. A `HGETALL` on the histogram (or a precomputed cumulative version) answers percentile in O(buckets) ≈ O(100). Walking a 25M-entry sorted set for this is not appropriate.

### Pitfall 9 — Cheaters "tactically disconnecting" before a loss

A player who knows they're about to lose disconnects, the server treats it as a tie or no-op, no score penalty. Mitigation: **the game server is the source of truth for outcomes**, and a forfeit/loss-by-disconnect is a server-side decision, not a client message. Score updates are not coupled to client confirmation of the outcome.

### Pitfall 10 — Migration breaks rankings mid-tournament

You switch from single-Redis to Redis Cluster mid-month. Hash slots change, and the per-user rank shifts (because the global sort is now a merge of shards that are no longer bit-identical to the pre-migration sort). Mitigation: **freeze the leaderboard at migration time, snapshot, re-derive all ranks from the snapshot, and only then cut over**. Never migrate in the middle of a live tournament.

---

## Interview Q&A

### Q1 — How would the design change if we needed sub-second real-time updates pushed to a million concurrent clients?

Walk through the read-path fan-out problem. Even if Redis serves 1M `GET /v1/scores` per second, the clients are still polling. The fix is push:

1. **Change data capture** on the sorted set (Redis keyspace notifications, or a Kafka producer on every `ZINCRBY`).
2. **A deltas feed**: only emit the rows whose rank actually changed. A `ZINCRBY` only affects the user's row and the rows they "swap" with — usually 1–2 deltas per write.
3. **A pub/sub or WebSocket fan-out** from a stateless gateway to subscribed clients.
4. **Backpressure**: if a client is slow, drop them from the live feed (they fall back to polling on next connect).
5. **Sharding the WS gateway by user_id** to keep any one box from holding a million connections.

Capacity math: 1M users × 1 delta/sec × 100 bytes ≈ 100 MB/s outbound — well within a single multi-gigabit NIC. The hard part is connection count, not bandwidth.

### Q2 — At 25M MAU, single Redis fits, but what changes at 500M?

Walk the numbers:

- Storage: 500M × 126 bytes ≈ 63 GB. Still fits in a beefy node.
- QPS at peak (with the 5x rush factor): 500M × 10 / 3600 × 2.5 ≈ 3.5M writes/sec. **This** is the cliff.
- Single-Redis `ZINCRBY` throughput: ~100k–500k/sec depending on payload and persistence. Three orders of magnitude short.

The answer is fixed-partition sharding by score band. Each shard handles ~35k writes/sec — easy. The complication: the top shard (highest scores) gets *more* writes because the active elite players play more. Monitor per-shard QPS and re-band over time.

### Q3 — The interviewer pushes back: "Redis is in-memory, so it must lose data. How do you guarantee no loss?"

The careful answer is "I don't use Redis as the system of record." The MySQL point history is. Redis is a derived fast view. On Redis crash:

1. Promote the replica (with the most recent AOF) — small loss window.
2. Replay the trailing minutes from MySQL into Redis (`SELECT user_id, SUM(score_awarded) GROUP BY user_id WHERE ts > last_replay_ts`).
3. Bring the leaderboard back online.

The remaining risk is: what if MySQL also failed? Then you replay from your **offline backup** (S3 snapshot or binlog shipping). The interview-grade answer mentions RPO/RTO explicitly: "RPO is the binlog shipping lag, sub-minute; RTO is the time to rebuild the sorted set from MySQL, also sub-minute at 25M users."

### Q4 — How would you handle tournaments with buy-ins and cash prizes?

This is the moment the design stops being "just a leaderboard" and becomes a **payment + leaderboard system**. The score update is no longer `ZINCRBY +1` — it must be a transactional event tied to a verified match result, and the prize payout is a downstream flow:

1. Match result is server-validated.
2. Win event is appended to MySQL with `tournament_id`, `user_id`, `verified_at`.
3. Leaderboard service updates the tournament's sorted set.
4. At tournament close, a separate settlement service walks the top-N players and triggers payouts via the payment system.
5. The settlement is idempotent and auditable — the leaderboard is *one input* to settlement, not its only source.

Payouts use the same idempotency / exactly-once machinery as Chapter 27. The leaderboard is read by settlement, never the source of cash.

### Q5 — What if we go global — players in EU, US, and APAC, with a "global" leaderboard?

Three concerns:

1. **Latency**: cross-Atlantic read of a US-hosted sorted set is 100–200 ms from EU. For a top-10 view, this is OK; for a per-user rank, it's noticeable. Mitigate with **regional Redis primaries** (one per region), each fed by the same Kafka topic of win events. Reads from the closest region.
2. **Regulatory / data residency**: a player's score isn't personal data under GDPR in most readings, but their account linkage to the score is. Keep the **user_id mapping** in the user's home region; replicate only the **scores** globally.
3. **Clock skew**: tie-breaking by timestamp across regions is dangerous if your events come from independent clocks. Solution: stamp events with **a single source of truth's sequence number** (the sequencer pattern from Chapter 29), not the originating server's wall clock. The sorted set orders by score; ties break by sequence number.

### Q6 — How do you test a real-time leaderboard?

Six test categories, each with concrete assertions:

- **Functional**: top-K returns the expected N; per-user rank matches a recomputation; ±4 returns the right slice.
- **Concurrency**: hammer `ZINCRBY` from N parallel clients for the same user; final score is the sum of all increments (Redis single-threaded server guarantees this for the same key).
- **Failure injection**: kill the Redis primary, verify replica promotion; replay MySQL; verify set equality.
- **Performance**: `redis-benchmark -t zadd -n 1000000`; expect ≥ 100k ops/sec on your target hardware. Profile with `redis-cli --latency-history`.
- **Determinism**: replay the same Kafka event stream twice; Redis state must be identical.
- **Cheat resistance**: replay historical events with the anti-cheat rules; expected false-positive rate < 0.1%, false-negative rate on planted cheats 100%.

---

## Key Terms / Glossary

| Term | Definition | Common misconception |
|------|------------|----------------------|
| **Sorted set (ZSET)** | Redis data type: unique members each with a score; ordered by score. Backed by a hash table + skip list. | "It's sorted alphabetically by member" — sorted by score, not member. |
| **Skip list** | Probabilistic layered index: O(log n) insert/search/rank. Used internally by Redis ZSET. | "It's a balanced BST" — skip lists are simpler, lock-free friendly, and have comparable O(log n) without rotations. |
| **Skip list span** | Each node tracks how many nodes it skips at its level. Cumulative spans let `ZRANK` compute rank in O(log n) without scanning. | "Rank requires a global counter" — span tracking is local, and the walk is O(log n). |
| **Price-time priority** | Order book rule: best price first, then earliest arrival. Not directly relevant to gaming, but the same priority pattern (score then timestamp) appears in scoreboards. | "Ties are broken randomly" — they are not, in any well-defined leaderboard. |
| **Top-K** | The first K entries of a sorted set. In a leaderboard, almost always K = 10. | "K must be small to be fast" — `ZREVRANGE 0 K-1` is O(log n + K), so K = 10 is essentially free even at 1B members. |
| **Percentile rank** | The fraction of users with a strictly lower score. Cheap to approximate via histograms, expensive to compute exactly. | "It's the same as 'top X%'" — close, but a 0.3% percentile means 0.3% of users are strictly better; "top 0.3%" usually means inclusive. |
| **Idempotency key** | A unique tag on a logical operation; replays of the same operation return the stored result. Mandatory for `POST /v1/scores` so retried clients don't double-credit. | "Idempotency is the same as dedupe" — idempotency is at the *operation* level; dedupe is one mechanism to achieve it. |
| **Server-authoritative** | The server, not the client, is the source of truth for game outcomes and scores. | "Server-side validation is enough" — validation alone is not authority; the server must be the one that *records* the result. |
| **Score-based partitioning** | Sharding by score range, so top-K and rank queries are O(1) per shard. | "It's the same as range sharding" — range sharding can be by any key; score-based partitioning is a specific choice for ranking workloads. |
| **AOF (Append-Only File)** | Redis persistence mode: log every write. `everysec` = at most 1s loss on crash; `always` = no loss but slow. | "AOF gives full durability" — only with `always` fsync, which is too slow for most use cases. `everysec` is the standard. |
| **BGSAVE** | Redis background snapshot (RDB fork). Cheap reads, brief fork-stall on writes during copy-on-write. | "It's free" — fork blocks the main thread proportional to memory size; on 64 GB instances, this is 100s of ms of stall. |
| **Hot partition / hot key** | A single shard or member receiving disproportionate traffic. In a leaderboard, this is the top-1 player being watched. | "Hot keys are evenly distributed" — they are not; the heavy tail of players dominates the top-K view count. |
| **Push vs poll (real-time)** | Push: server initiates update to client (WebSocket, SSE). Poll: client asks. Trade-off freshness for cost. | "Push is always better" — push costs connection state, heartbeat, and reconnection logic; for low-frequency updates it's overkill. |
| **Event sourcing** | Append-only event log as the source of truth; current state is a fold of events. Enables reproducibility and replay. | "It's the same as CDC" — CDC captures DB changes for downstream; event sourcing *is* the change log, not a derivative of it. |
| **CQRS** | Command-Query Responsibility Segregation: separate write and read models. Useful when reads and writes have very different shapes. | "It's the same as event sourcing" — CQRS can be used without event sourcing (e.g., a denormalized read table) and vice versa. |
| **Hot replica** | A Redis standby that receives writes synchronously (or near-synchronously) and can be promoted on primary failure. | "It's the same as a regular replica" — a regular replica is async; promotion loses the most recent second of writes. |
| **Lua scripting in Redis** | `EVAL` runs a script atomically on the server. Used to make "increment + return rank" a single atomic step. | "It's slow" — scripts block the single Redis thread but are usually < 1ms; for complex multi-step work this is faster than a client round-trip. |
