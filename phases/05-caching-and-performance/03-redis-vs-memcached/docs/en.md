# Redis VS Memcached

> Choose Memcached when you need raw throughput for simple strings; choose Redis when your data has shape.

**Type:** Learn
**Prerequisites:** Caching Fundamentals, Cache Eviction Policies
**Time:** ~25 minutes

---

## The Problem

Your API is hammering Postgres on every request. You decide to add a cache layer. You Google "in-memory cache" and immediately hit two options: Redis and Memcached. Both store data in RAM, both use a key-value model, both are battle-tested at massive scale. So which one do you pick?

The wrong answer is "it doesn't matter, they're basically the same." That assumption has bitten engineering teams. A team building a leaderboard wires up Memcached and then spends a week reimplementing sorted-set logic in application code — work that Redis does natively in a single command. Another team reaches for Redis when they need to cache 50 million raw HTML fragments and later discovers Memcached would have fit 20% more data in the same RAM with lower latency because it has less per-key overhead.

Understanding the differences isn't academic. It determines whether you pay for extra servers, whether you end up with race conditions in your application layer, and whether your cache survives a process restart.

---

## The Concept

### The Fundamental Distinction

Memcached is a distributed hash table. It maps strings to strings, nothing more. All complexity — sorting, filtering, counting — happens in your application.

Redis is a data structure server. The value at a key can be a string, list, hash, sorted set, set, bitmap, HyperLogLog, stream, or geospatial index. Operations on those structures are atomic, happen server-side, and are exposed as first-class commands.

```
MEMCACHED MODEL                      REDIS MODEL
─────────────────                    ─────────────────────────────────
key  →  opaque byte string           key  →  typed value
                                           ├── string     ("hello")
GET / SET / DELETE / INCR            │── list       ([a, b, c])
                                           ├── hash       ({f1:v1})
No persistence                             ├── set        ({a, b, c})
No replication (built-in)                  ├── sorted set ({a:1.0, b:2.0})
No Pub/Sub                                 ├── bitmap
No scripting                               ├── HyperLogLog
                                           └── stream
                                     Full persistence options
                                     Built-in replication + Sentinel + Cluster
                                     Pub/Sub, Lua scripting, transactions
```

### Threading Model

This is where a common misconception lives.

- **Memcached** is multi-threaded. A single node can use all CPU cores to serve requests in parallel. For pure GET/SET workloads at extreme concurrency, this matters.
- **Redis** (≤ 5.x) is single-threaded for command processing. One event loop, one core for commands. Redis 6.0 added I/O threading (network read/write) but command execution stays single-threaded.

In practice this matters far less than people expect. Redis command latency is sub-millisecond for nearly everything. The bottleneck in most production systems is network round-trips, not CPU cycles spent processing commands. On a single node, both systems comfortably exceed 100k ops/sec on commodity hardware.

### Persistence

| Capability | Memcached | Redis |
|---|---|---|
| Survives process restart | No | Yes (with config) |
| RDB snapshots | No | Yes (`SAVE` / `BGSAVE`) |
| AOF write-ahead log | No | Yes (`appendonly yes`) |
| Hybrid RDB+AOF | No | Yes (Redis 4+) |

Redis RDB takes a point-in-time snapshot at configurable intervals. AOF logs every write command; on restart, Redis replays the log. You can tune the AOF fsync policy: `always` (safest, slowest), `everysec` (default, at most 1 second of data loss), or `no` (fastest, OS decides).

Memcached has zero persistence. A restart empties the cache entirely. Design your system to tolerate that, or don't use Memcached for data you can't reconstruct.

### Replication and High Availability

Redis ships with:
- **Replication**: one primary, N replicas, asynchronous by default
- **Redis Sentinel**: monitors primaries and replicas, triggers automatic failover
- **Redis Cluster**: horizontal sharding across 16,384 hash slots, built-in failover

Memcached has no native replication. To shard across nodes you implement consistent hashing in the client (libraries like `libmemcached` or `pylibmc` do this). If a node goes down, that partition of your key space is cold until the node recovers. This is fine for pure caching where cache misses are tolerable; it's a problem if you're using Memcached for session storage.

### Memory Efficiency

Memcached allocates memory using a slab allocator: pre-defined chunk sizes to avoid fragmentation. For workloads with many similarly-sized objects, this is extremely efficient.

Redis stores richer metadata per key (TTL, encoding type, LRU clock). For small strings, this overhead is proportionally larger. Redis also uses special compact encodings for small collections (listpack, intset, ziplist) that trade CPU for RAM, but once a collection grows past configurable thresholds it promotes to a full heap structure.

Rule of thumb: for storing millions of small raw strings, Memcached uses ~30% less memory than Redis for the same data.

### Feature Comparison at a Glance

| Feature | Memcached | Redis |
|---|---|---|
| Data types | String only | String, List, Hash, Set, ZSet, Bitmap, HLL, Stream, Geo |
| Atomic increment | `INCR` (int only) | `INCR`, `INCRBY`, `INCRBYFLOAT` + type-specific ops |
| Server-side sort/rank | No | `ZADD` / `ZRANK` / `ZRANGE` (sorted sets) |
| Pub/Sub messaging | No | Yes |
| Transactions | No | `MULTI` / `EXEC` (optimistic, no rollback) |
| Lua scripting | No | Yes (`EVAL`) |
| Keyspace notifications | No | Yes |
| Persistence | No | RDB + AOF |
| Built-in clustering | No | Yes (Redis Cluster) |
| Max value size | 1 MB | 512 MB (string); collections: up to 2^32 elements |
| Threading | Multi-threaded | Single-threaded commands; I/O threads in 6.0+ |
| Protocol | text + binary | RESP (text) |

---

## Build It / In Depth

### Scenario: Leaderboard for a Gaming Platform

You need to maintain a real-time leaderboard of top 100 players, updated after every match, with the ability to fetch a player's current rank.

**With Memcached — the hard way:**

```python
# You'd have to GET the entire leaderboard blob, deserialize,
# update in Python, re-serialize, SET back. Non-atomic, race-prone.

import memcache
import json

mc = memcache.Client(["127.0.0.1:11211"])

def update_score(player_id: str, delta: int):
    # Non-atomic: another process can overwrite between GET and SET
    board = json.loads(mc.get("leaderboard") or "[]")
    for entry in board:
        if entry["id"] == player_id:
            entry["score"] += delta
            break
    board.sort(key=lambda x: -x["score"])
    mc.set("leaderboard", json.dumps(board[:100]))
```

Problems: not atomic, O(n) scan, full blob re-serialized on every update.

**With Redis — the idiomatic way:**

```python
import redis

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

# Add or update a player's score atomically
def record_match_result(player_id: str, points_earned: int):
    r.zincrby("leaderboard:global", points_earned, player_id)

# Fetch top 10 with scores
def top_players(n: int = 10):
    return r.zrevrange("leaderboard:global", 0, n - 1, withscores=True)

# Get a specific player's rank (0-indexed from top)
def player_rank(player_id: str):
    return r.zrevrank("leaderboard:global", player_id)

# Usage
record_match_result("player:42", 150)
record_match_result("player:7", 300)
print(top_players(3))
# [('player:7', 300.0), ('player:42', 150.0)]
print(player_rank("player:42"))
# 1
```

`ZINCRBY` is atomic. `ZREVRANK` is O(log N). The sorted set is maintained server-side with zero application-layer race conditions.

### Scenario: Session Storage at Scale

A stateless API needs to look up session tokens. Sessions are plain JSON blobs, expire after 30 minutes, and are read far more than they're written.

**Memcached — a legitimate fit here:**

```bash
# Connection
memcached -d -m 2048 -l 127.0.0.1 -p 11211

# Set a session (30-min TTL)
# In Python with pymemcache:
client.set("sess:abc123", json.dumps(session_data), expire=1800)

# Get a session
data = client.get("sess:abc123")
```

This is one of the few cases where Memcached's simplicity is an advantage. You need fast string GET/SET, multi-threading helps at extreme concurrency, and you don't need persistence — if the server restarts, users just log in again. Memcached's lower per-key overhead means more sessions fit in RAM.

### Redis Persistence Configuration

```bash
# redis.conf — recommended production settings

# --- RDB snapshot ---
save 900 1       # snapshot if ≥1 key changed in 900 seconds
save 300 10      # snapshot if ≥10 keys changed in 300 seconds
save 60 10000    # snapshot if ≥10000 keys changed in 60 seconds

# --- AOF ---
appendonly yes
appendfsync everysec   # at most 1 second of data loss on crash
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb

# --- Memory ---
maxmemory 4gb
maxmemory-policy allkeys-lru
```

---

## Use It

### When to Choose Redis

- **Any non-trivial data structure**: leaderboards (sorted sets), activity feeds (lists), unique visitor counts (HyperLogLog), online/offline presence (sets + TTL), time-series events (streams).
- **Session storage where persistence matters**: user shopping carts, auth tokens that must survive a restart.
- **Rate limiting**: `INCR` + `EXPIRE` or the sliding-window pattern with sorted sets.
- **Pub/Sub messaging**: lightweight fan-out between services (though for heavy messaging, prefer Kafka/RabbitMQ).
- **Distributed locks**: Redis + Lua scripts or the Redlock algorithm.
- **Feature flags / config cache**: low cardinality, hash structures fit naturally.

### When Memcached Is a Reasonable Choice

- **Pure object caching at extreme scale**: you cache millions of opaque serialized objects (HTML fragments, API response JSON), all roughly the same size, and need to squeeze every byte out of RAM.
- **Simple GET/SET with multi-threaded throughput**: if you're already saturating a Redis node's I/O threads and CPU with pure string ops and can't scale horizontally, Memcached's multithreaded model helps.
- **You explicitly need multi-threaded single-node performance**: rare in practice because Redis Cluster horizontal scaling is almost always cheaper and easier than tuning Memcached.

### Cloud Offerings

| Cloud | Redis | Memcached |
|---|---|---|
| AWS | ElastiCache for Redis, MemoryDB for Redis | ElastiCache for Memcached |
| GCP | Memorystore for Redis | Memorystore for Memcached |
| Azure | Azure Cache for Redis | (Redis only) |

AWS MemoryDB for Redis adds Multi-AZ durability with a transaction log — it's Redis API-compatible with stronger persistence guarantees than ElastiCache.

---

## Common Pitfalls

- **Using Memcached for sessions without a fallback strategy.** When the node restarts or is evicted from your cluster, all sessions are gone. Users hit 401s at scale with no warning. Either tolerate this explicitly (re-login on cold cache) or use Redis with persistence.

- **Treating Redis transactions as ACID.** `MULTI`/`EXEC` in Redis is not a rollback transaction. It queues commands and executes them atomically (no interleaving), but if a command inside `MULTI` fails, other commands in the batch still execute. There is no `ROLLBACK`. Use Lua scripts (`EVAL`) when you need conditional atomic logic.

- **Ignoring Redis memory policy under pressure.** If you set `maxmemory` without `maxmemory-policy`, Redis returns OOM errors once full — it does not evict. Set `allkeys-lru` or `volatile-lru` explicitly and monitor `used_memory` vs `maxmemory`.

- **Putting large blobs in Redis and wondering why it's slow.** Redis is single-threaded for command processing. A single `SET` of a 10 MB payload blocks the event loop for all other clients during the network transfer. Chunk large objects, compress them, or use a blob store (S3) with Redis holding only the reference key.

- **Assuming Redis Pub/Sub is a reliable message queue.** Redis Pub/Sub is fire-and-forget. If a subscriber disconnects and reconnects, it misses messages sent during the gap. For reliable fan-out use Redis Streams (`XADD` / `XREAD` / `XGROUP`) or a dedicated broker.

---

## Exercises

1. **Easy** — Set up a local Redis instance and implement a simple rate limiter using `INCR` and `EXPIRE`. The limiter should allow at most 10 requests per minute per user ID. Print "OK" or "RATE LIMITED" for each call.

2. **Medium** — Build a "recent activity feed" for a social app using a Redis list. Each user's feed should store the last 20 events (push to head, trim to 20). Implement `post_event(user_id, event)` and `get_feed(user_id)`. Then implement the same with Memcached and compare the code complexity.

3. **Hard** — Design the cache layer for a multi-region e-commerce platform where product prices are cached. Write a design document addressing: (a) Redis vs Memcached choice and justification, (b) how you handle cache invalidation when a price changes, (c) how you prevent the thundering herd on a cold start, and (d) what happens to the cache layer when the primary database fails over to a replica with a few seconds of replication lag.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **In-memory cache** | "It's just a fast dictionary" | A process that stores data in RAM with configurable eviction, optional persistence, and specialized data structures; behavior depends heavily on the implementation |
| **Redis single-threaded** | "Redis can't scale" | Commands execute on one thread (no parallel command races), but I/O is async via epoll/kqueue; scales to hundreds of thousands of ops/sec on a single node |
| **Memcached multi-threaded** | "Memcached is always faster" | Multiple threads handle connections in parallel, which helps saturate CPU on pure string workloads; irrelevant for latency in most production scenarios |
| **Redis persistence** | "Redis is like a database" | Redis can persist to disk via snapshots (RDB) or an append-only log (AOF), but it is still primarily a cache; persistence adds durability, not ACID semantics |
| **Cache eviction** | "Eviction means the cache is broken" | A normal, expected behavior when `maxmemory` is reached; `allkeys-lru` evicts the least-recently-used keys to make room for new ones |
| **Redis Cluster** | "You need it at any scale" | Automatic sharding across 16,384 hash slots with built-in failover; not needed until a single Redis node is a bottleneck (~100k+ ops/sec sustained) |
| **Pub/Sub** | "Redis is a message broker" | Redis Pub/Sub is a lightweight fan-out primitive with no message durability; for reliable messaging, use Redis Streams or a dedicated broker |

---

## Further Reading

- [Redis documentation — Data Types](https://redis.io/docs/data-types/) — official reference for every Redis data structure with complexity guarantees
- [Redis persistence demystified](https://redis.io/docs/management/persistence/) — official guide to RDB vs AOF trade-offs and configuration
- [Memcached wiki — Internals](https://github.com/memcached/memcached/wiki/Internals) — slab allocator, threading model, and protocol details from the maintainers
- [AWS ElastiCache: Choosing between Redis and Memcached](https://docs.aws.amazon.com/AmazonElastiCache/latest/red-ug/SelectEngine.html) — cloud-operator perspective on the trade-offs
- [High Scalability — Instagram's Redis usage](http://highscalability.com/blog/2012/3/26/7-lessons-learned-while-building-reddit-to-270-million-page.html) — real-world case study on using Redis data structures to replace application-layer logic
