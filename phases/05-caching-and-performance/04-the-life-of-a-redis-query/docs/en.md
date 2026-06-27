# The Life of a Redis Query

> Redis is fast not because of magic — it is fast because every design decision eliminates a source of latency.

**Type:** Learn
**Prerequisites:** Caching Fundamentals, Cache Invalidation Strategies, Intro to In-Memory Databases
**Time:** ~25 minutes

---

## The Problem

Most engineers know Redis is fast. Fewer can explain *why*, and almost no one can reason about *what goes wrong* when it isn't. You add Redis to a system expecting sub-millisecond reads, then you hit an outage because a cron job runs `KEYS *` on a 10-million-key instance. Or you notice p99 latency spikes every 30 seconds and can't explain them. Or a replica falls behind after a failover and you don't know which durability knob caused it.

These problems share a root cause: the engineering team treated Redis as a black box. They knew the interface (`GET`, `SET`, `HSET`), but not the internals — the single-threaded event loop, the I/O multiplexing model, the persistence pipeline, and how all three interact under load.

This lesson traces a single Redis query from the moment the client writes bytes onto the network socket all the way to the moment the response arrives back. Understanding this lifecycle gives you a mental model that predicts behavior, explains anomalies, and lets you tune Redis with confidence rather than guesswork.

---

## The Concept

### Redis's Threading Model

Redis executes commands on a **single main thread**. There is no locking, no concurrent modification, and no context switching between commands. This sounds like a limitation — it is actually a feature. A single-threaded loop processes one command atomically at a time, which means you never need distributed locks for read-modify-write operations on a single Redis node.

```
┌────────────────────────────────────────────────────┐
│                  Redis Main Thread                 │
│                                                    │
│   ┌──────────┐   ┌────────────┐   ┌────────────┐  │
│   │ I/O Poll │ → │  Command   │ → │  Response  │  │
│   │ (epoll)  │   │ Execution  │   │  Write     │  │
│   └──────────┘   └────────────┘   └────────────┘  │
│         ↑                                  ↓       │
│   ┌─────┴────┐                    ┌────────┴────┐  │
│   │ Client   │                    │ Client      │  │
│   │ Sockets  │                    │ Sockets     │  │
│   └──────────┘                    └─────────────┘  │
└────────────────────────────────────────────────────┘
```

Redis uses **I/O multiplexing** — specifically `epoll` on Linux and `kqueue` on macOS/BSD — to monitor thousands of client sockets simultaneously without blocking on any one of them. The event loop wakes only when data is ready to read or a socket is ready to write.

### The Event Loop in Detail

Redis's core loop (`ae.c` in the source) repeats this cycle continuously:

1. **File event phase** — Call `epoll_wait()` with a short timeout. The kernel returns a list of sockets with pending reads or writes.
2. **Read phase** — For each readable socket, read the incoming RESP (Redis Serialization Protocol) bytes into a per-client input buffer.
3. **Command phase** — If the input buffer contains a complete command, parse it and dispatch to the command handler. Execute the command against the in-memory data structure.
4. **AOF write phase** — If AOF is enabled, append the command to the AOF write buffer (not necessarily to disk yet — see persistence below).
5. **Write phase** — Format the response and add it to the per-client output buffer. The kernel will drain it on the next writable event.
6. **Time event phase** — Run periodic tasks: `serverCron` fires every 100 ms to handle key expiry, replication heartbeats, RDB snapshot scheduling, and statistics.

```
while (server.shutdown_asap == 0) {
    aeProcessEvents(server.el, AE_ALL_EVENTS | AE_DONT_WAIT);
    // one iteration = one pass through all ready file events
    //              + one pass through due time events
}
```

The key insight: **no command can be interrupted mid-execution**. A slow command (like `SORT` on 1 million elements) blocks every other client until it finishes. This is why O(N) commands are dangerous.

### Memory Layout

When Redis executes a `SET foo bar`, it:

1. Computes the hash of the key `foo` in the global dictionary (a hash table with open addressing and incremental rehashing).
2. Creates or updates a `robj` (Redis object) holding the value. Redis auto-selects an encoding:
   - Short strings ≤ 44 bytes → `embstr` (object + string in a single `malloc` allocation)
   - Long strings → `raw` (two separate allocations)
   - Small integers 0–9999 → shared integer objects (no allocation at all)
3. Updates expiry metadata in a second hash table if a TTL is set.

```
Key Dictionary (hash table)
┌─────────────────────────────────────────┐
│ slot 0  → [key:"foo", val:robj{bar}]    │
│ slot 1  → NULL                          │
│ slot 2  → [key:"counter", val:robj{42}] │
│  ...                                    │
└─────────────────────────────────────────┘
              ↑
       Incremental rehash: when load > 1.0,
       Redis allocates a 2× table and migrates
       one bucket per command until complete.
```

### Persistence: AOF

After executing the command in memory, Redis logs it for durability:

```
Client:  SET session:abc "user=100"  →  Redis RAM updated
                                     ↓
                              AOF write buffer
                                     ↓  (when?)
                              Kernel page cache
                                     ↓  (when?)
                              Disk (WAL file)
```

The "when?" is controlled by `appendfsync`:

| Setting | Behavior | Durability | Latency Impact |
|---|---|---|---|
| `always` | `fsync()` after every command | Maximum — lose 0 commands | High — disk latency per write |
| `everysec` | Background thread calls `fsync()` once per second | Lose at most ~1 second of writes | Low — async |
| `no` | Never call `fsync()` — OS decides when to flush | OS-dependent | Lowest |

**`everysec` is the default and the production recommendation** for most workloads. The background `fsync` runs in a separate I/O thread so it does not block the main loop. However, if the previous `fsync` has not completed when the next one is due, Redis will delay the current command by up to 2 seconds to avoid writing to a file while it is being flushed — this is a source of latency spikes.

### Persistence: RDB

RDB snapshots are taken by `BGSAVE`:

1. The main thread calls `fork()`. This is fast (copy-on-write at the OS level) but does briefly pause the event loop — typically 10–200 ms depending on memory size and OS.
2. The child process serialates the entire dataset to a new `.rdb` file.
3. The main thread continues serving commands. Any page modified during the snapshot is duplicated by the OS (copy-on-write), so the child sees a consistent snapshot.
4. When the child finishes, it atomically renames the temp file to `dump.rdb`.

```
Main thread (fork)
     │
     ├──────────────────────────────────────────► Child (bgsave)
     │  continues serving commands                │  reads shared pages
     │                                            │  writes dump.rdb.tmp
     │  modified pages → OS duplicates them       │
     │                                            │
     ◄────────────────────────────────────────────┘
     │  receives SIGUSR1, reloads dump.rdb ref
```

RDB is efficient for bulk recovery (loading 10 GB from RDB is 3–5× faster than replaying 10 GB of AOF), but you lose all writes since the last snapshot on a crash.

### The Mixed Persistence Mode

Since Redis 4.0, you can enable `aof-use-rdb-preamble yes`. On AOF rewrite, Redis writes an RDB snapshot at the start of the new AOF file, then appends only the delta commands after that. This gives fast startup (load the embedded RDB) and full durability (replay the short AOF tail).

---

## Build It / In Depth

Let's trace `SET session:u100 "{uid:100}" EX 3600` from client to disk.

### Step 1 — Client sends RESP

The Redis client encodes the command in RESP (Redis Serialization Protocol):

```
*4\r\n
$3\r\n
SET\r\n
$12\r\n
session:u100\r\n
$10\r\n
{uid:100}\r\n
$2\r\n
EX\r\n
$4\r\n
3600\r\n
```

`*4` = 4 arguments. Each `$N` is a bulk string of N bytes.

### Step 2 — epoll wakes the main thread

```bash
# You can watch this with strace on Linux:
strace -e epoll_wait,read,write -p $(pgrep redis-server) 2>&1 | head -40
```

The kernel returns the client's fd as readable. Redis reads the bytes into `client->querybuf`.

### Step 3 — Command dispatch

The RESP parser sees a complete command. Redis looks up `"SET"` in the command table (a hash map of ~200 entries):

```c
// Simplified from t_string.c
void setCommand(client *c) {
    // parse optional EX/PX/NX/XX flags
    // call setGenericCommand → dbSetKey → dictAdd/dictReplace
    // set expiry in server.db[0].expires dict
    // call notifyKeyspaceEvent for pub/sub listeners
    // addReply(c, shared.ok)
}
```

Memory cost: 1 `dictEntry` (key + value pointers) + 1 `robj` for value (`embstr` since 10 bytes < 44). No extra allocation for the expiry — it is stored in a parallel hash table keyed by the same SDS string.

### Step 4 — AOF append

```
// In-memory AOF write buffer grows by:
"*4\r\n$3\r\nSET\r\n$12\r\nsession:u100\r\n..."
```

With `appendfsync everysec`, this buffer is flushed to the kernel page cache immediately but `fsync()` to physical disk runs once per second in a background I/O thread.

### Step 5 — Response written back

`addReply(c, shared.ok)` enqueues `"+OK\r\n"` in `client->buf`. On the next writable event, the main loop calls `write()` and the bytes travel back to the client.

**Total wall-clock time:** ~100–200 µs on a local network. The breakdown:
- Network round-trip: ~50–100 µs (localhost) or 0.5–2 ms (cross-AZ)
- Event loop scheduling: < 1 µs
- Memory operation (hash lookup + insert): < 5 µs
- AOF buffer append: < 1 µs

---

## Use It

| Scenario | Recommended Configuration |
|---|---|
| Session store, tolerate 1s data loss | `appendonly yes`, `appendfsync everysec`, RDB every 5 min |
| Leaderboard / counters, can replay from DB | `appendonly no`, RDB only, or no persistence |
| Financial data, zero loss | `appendonly yes`, `appendfsync always` (+ synchronous replica) |
| Cache-only (data in primary DB) | `save ""` (disable RDB), `appendonly no` |
| Fastest restart after crash | Mixed persistence (`aof-use-rdb-preamble yes`) |

**Pub/Sub:** Operates inside the same event loop. A `PUBLISH` command iterates over subscriber lists inline, meaning a slow subscriber that cannot drain its output buffer will cause `PUBLISH` to block.

**Lua scripts and MULTI/EXEC transactions:** Both run atomically on the main thread. A long Lua script has the same blocking risk as a slow command.

**Redis 6.0+ threaded I/O:** Redis optionally uses background threads for reading and writing socket data (`io-threads 4`), but command execution remains single-threaded. This helps at very high connection counts where kernel syscall overhead dominates.

---

## Common Pitfalls

- **Running `KEYS *` in production.** `KEYS` is O(N) over the entire keyspace and blocks the event loop for the full scan. Use `SCAN` with a cursor instead — it returns a small batch per call and lets other commands interleave.

- **Ignoring `fork()` latency.** A `BGSAVE` or AOF rewrite on a 20 GB Redis instance can pause the event loop for 200–500 ms as `fork()` copies page-table entries. Schedule snapshots during off-peak hours, or use a replica to take the snapshot.

- **Setting `appendfsync always` without understanding the cost.** Each write goes to disk synchronously. On a spinning disk this limits throughput to ~100 writes/sec. Even NVMe drives top out around 500 µs per `fsync`. Use it only when the workload truly demands zero data loss.

- **Using long-running Lua scripts.** A Lua script that loops over thousands of keys will monopolize the main thread for its entire duration. There is no way to interrupt it without killing the server (`SCRIPT KILL` only works if the script has not yet performed a write).

- **Not accounting for copy-on-write memory overhead during snapshots.** Under a high write rate, copy-on-write can double the RSS of the Redis process during a `BGSAVE`. If your Redis instance uses 8 GB of RAM and your server has 12 GB total, the OS can OOM-kill the child — or the parent — mid-snapshot.

---

## Exercises

1. **Easy** — Start a Redis server locally with `redis-server --appendonly yes --appendfsync everysec`. Run `SET foo bar`, then open the `appendonly.aof` file and identify the RESP encoding of your command. Predict what `SET foo bar EX 60` will look like in the AOF.

2. **Medium** — A Redis instance is showing p99 latency spikes of ~2 seconds every 30 seconds. List three possible root causes based on what you know about the event loop and persistence, and describe how you would confirm each one using `redis-cli --latency`, `INFO persistence`, and `SLOWLOG GET`.

3. **Hard** — Design a persistence strategy for a rate-limiter service backed by Redis that: (a) must survive a server restart without losing more than 1 second of counter increments, (b) must restart within 5 seconds even with 50 GB of data, and (c) runs on a server with exactly 2× the Redis RSS available. Justify your choice of AOF fsync policy, RDB schedule, and whether to use mixed persistence, and explain how copy-on-write affects your memory budget.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Single-threaded** | Redis can only use one CPU core and is therefore slow | The *command execution* is single-threaded for atomicity; I/O and persistence use background threads in modern Redis |
| **AOF** | A log file that stores key-value pairs | A write-ahead log of raw Redis commands in RESP format, replayed on restart to rebuild state |
| **RDB** | A backup of Redis data | A point-in-time binary snapshot of the in-memory dataset, written by a forked child process |
| **`appendfsync everysec`** | Syncs to disk every second, so you lose at most 1 second | Calls `fsync()` once per second in a background thread; if the prior sync is still running, Redis may delay the next write by up to 2 seconds |
| **Event loop** | An async framework similar to Node.js | The `ae` (async event) loop in Redis that multiplexes I/O with `epoll`/`kqueue` and interleaves file events with periodic time events |
| **Copy-on-write** | A way Redis avoids copying data during snapshots | An OS mechanism where forked child and parent share physical pages until either modifies one; then the OS copies only the modified page |
| **`BGSAVE`** | A background task with no performance impact | A `fork()` call that briefly pauses the event loop and doubles memory usage under high write rates |

---

## Further Reading

- [Redis Internals — How Redis Works](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/) — Official Redis documentation on AOF and RDB persistence options, with configuration reference.
- [Redis Source: ae.c event loop](https://github.com/redis/redis/blob/unstable/src/ae.c) — The actual event-loop implementation; reading `aeMain()` and `aeProcessEvents()` makes the lifecycle concrete.
- [Redis Latency Monitoring](https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/) — Official guide to diagnosing latency spikes including fork latency, slow commands, and fsync stalls.
- [Antirez — Redis persistence demystified](http://oldblog.antirez.com/post/redis-persistence-demystified.html) — The original author explains the trade-offs between AOF and RDB in plain language; still the best single-page summary.
- [High Performance Browser Networking — Chapter 1](https://hpbn.co/) — Not Redis-specific, but the latency primer (speed of light, round-trip times, kernel scheduling) provides essential context for understanding where Redis's microseconds fit in end-to-end system latency.
