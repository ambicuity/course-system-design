# Design a Unique ID Generator in Distributed Systems

Generating unique identifiers sounds trivial until you remove the single source of truth. On one machine a database auto-increment column solves the whole problem. Across hundreds of machines in multiple data centers, with no shared coordinator on the hot path, the problem becomes a genuine distributed-systems exercise: how do independent nodes agree on globally unique IDs without talking to each other on every request?

---

## Step 1 — Understand the Problem & Establish Scope

Before proposing a scheme, pin down the requirements. The "right" ID generator changes dramatically depending on the answers.

### Clarifying questions

- What does an ID need to look like? Numeric only, or alphanumeric/string?
- How large can an ID be? 64 bits is the common target so IDs fit in a `BIGINT`/`long`.
- Must IDs be **globally unique**? (Almost always yes.)
- Do IDs need to be **sortable by creation time** (roughly time-ordered)? This is a key differentiator.
- Do IDs need to be **strictly monotonically increasing**, or just trend upward?
- How many IDs do we need per second? (Drives the design.)
- Should IDs be hard to guess (security/enumeration concern)?

### Functional requirements (typical answer set)

1. IDs are **unique** across the whole system.
2. IDs are **numeric** and fit in **64 bits**.
3. IDs are **ordered by date / roughly time-sortable** (newer IDs are larger).
4. The system can generate **>10,000 IDs per second** (often much more).

### Non-functional requirements

- **High availability** — the ID service must essentially never go down; everything depends on it.
- **Low latency** — ID generation is on the critical path of writes; it must be fast.
- **Scalability** — throughput must grow horizontally.
- **No coordination on the hot path** — ideally a node generates an ID locally without a network round trip.

### Why not just use a database auto-increment?

A single auto-increment column is simple and ordered, but:

- It is a **single point of failure** and a write bottleneck.
- It does not scale horizontally; every insert serializes on one sequence.
- Cross-region latency makes a central counter painfully slow.

So we evaluate distributed alternatives.

---

## Step 2 — Propose High-Level Design & Get Buy-In

There are several canonical approaches. Each makes different trade-offs across uniqueness guarantees, ordering, coordination cost, and ID length.

### Option A — Multi-master replication

Use several database servers, each with auto-increment, but **increase the increment step** to the number of servers (`k`) and give each server a different **starting offset**.

- Server 1 produces 1, 1+k, 1+2k, …
- Server 2 produces 2, 2+k, 2+2k, …

**Pros**

- Reuses familiar database auto-increment.
- Scales writes across `k` masters.

**Cons**

- IDs are **not time-sortable** across servers.
- Adding or removing a server breaks the modulo scheme and is awkward.
- Hard to scale across data centers.
- Each server is still its own SPOF for its slice of IDs.

This approach is rarely the final answer but is useful to mention as a baseline.

### Option B — UUID (Universally Unique Identifier)

A 128-bit value generated **independently on each node** with no coordination. UUIDv4 is random; the probability of collision is negligibly small.

**Pros**

- Generated locally — **no coordination, no SPOF, trivially scalable**.
- Simple to implement; libraries everywhere.

**Cons**

- **128 bits**, not 64 — violates the size requirement and bloats indexes.
- **Not numeric** in the usual representation (hex/string).
- **Not time-sortable** (UUIDv4 is random), which hurts B-tree insert locality and range scans. (Note: newer UUIDv7 is time-ordered and addresses this, worth mentioning if asked.)

### Option C — Ticket server

A dedicated **centralized** server (popularized by Flickr) that hands out IDs using a single database auto-increment behind a service.

**Pros**

- IDs are numeric and 64-bit.
- Simple, centralized, easy to reason about.

**Cons**

- The ticket server is a **single point of failure**. Running two for redundancy reintroduces the ordering/coordination problem.
- Network round trip per ID (or per batch) adds latency.
- Throughput is capped by the single server unless you batch.

A common mitigation: hand out **ID ranges in batches** so a client gets, say, 1,000 IDs per round trip and serves them locally.

### Option D — Twitter Snowflake (recommended)

Snowflake generates a **64-bit ID locally** on each node by **partitioning the bits** of the integer into meaningful sections. This meets all our requirements: 64-bit, numeric, time-sortable, no hot-path coordination, and very high throughput.

**This is the design we deep-dive.**

---

## Step 3 — Design Deep Dive: Snowflake

### Bit layout (64 bits total)

| Section | Bits | Purpose |
|---|---|---|
| Sign bit | 1 | Always 0; keeps the ID a positive signed 64-bit integer |
| Timestamp | 41 | Milliseconds since a custom **epoch** |
| Data center ID | 5 | Up to 32 data centers |
| Machine ID | 5 | Up to 32 machines per data center |
| Sequence number | 12 | Counter that resets every millisecond |

The exact split is configurable. The 5+5 split for datacenter/machine can be merged into a single 10-bit "worker ID" if you don't need the datacenter dimension.

### How each section is filled

- **Sign bit (1)** — reserved, always 0. Keeping IDs positive avoids surprises in languages with signed integers.
- **Timestamp (41 bits)** — milliseconds elapsed since a **custom epoch** chosen by us (e.g., the day the service launched), not the Unix epoch. Using a custom epoch maximizes the usable lifespan.
  - 41 bits ≈ 2^41 ms ≈ **69 years** of range. After that you must reset the epoch or change the layout.
  - The timestamp lives in the **high-order bits**, which is what makes IDs **sortable by time** — a numerically larger ID was generated later.
- **Data center ID (5 bits)** — assigned per data center; 2^5 = 32 data centers.
- **Machine ID (5 bits)** — assigned per machine within a data center; 2^5 = 32 machines each.
  - Together, datacenter+machine uniquely identify the worker, so two workers never collide even if they generate at the same millisecond.
- **Sequence number (12 bits)** — a per-machine counter that **increments for every ID generated within the same millisecond** and **resets to 0** when the millisecond ticks over.
  - 2^12 = **4,096 IDs per machine per millisecond** → ~4.09 million IDs/sec **per machine**. Far above the 10k/sec requirement.

### Generation algorithm (per node)

1. Read the current timestamp in ms.
2. If it equals the last-seen timestamp, **increment the sequence counter**.
   - If the sequence overflows (exceeds 4,095), **busy-wait until the next millisecond**, then reset sequence to 0.
3. If it is greater than the last-seen timestamp, **reset sequence to 0**.
4. Compose the ID by bit-shifting each section into place:
   `id = (timestamp - epoch) << 22 | datacenterId << 17 | machineId << 12 | sequence`
5. Store the timestamp as last-seen and return the ID.

No network call, no lock contention across machines — each node is fully autonomous as long as its `(datacenterId, machineId)` is unique.

### Worker ID assignment

Each node needs a unique worker ID. Options:

- **Static configuration** — simple but error-prone at scale.
- **Coordination service** — ZooKeeper / etcd / Consul assigns a unique worker ID on startup (lease-based). This is the common production choice; it centralizes only the rare assignment event, not ID generation itself.

---

### The clock problem (the most important deep-dive)

Snowflake's correctness depends on the **timestamp being monotonic** on each node. Real clocks are not perfectly behaved.

#### Clocks moving backward

NTP (Network Time Protocol) periodically corrects machine clocks, and a correction can move the clock **backward**. If a node generates an ID, then its clock jumps back, it could produce an ID with a **smaller or duplicate** timestamp — breaking ordering and risking collisions.

**Mitigations:**

- **Detect and refuse:** if the current timestamp is less than the last-seen timestamp, **reject / wait** until the clock catches up to the last-seen value before generating.
- **Small backward tolerance:** if the regression is tiny (a few ms), block briefly and resume; if it's large, raise an alert and stop generating (fail loud rather than emit bad IDs).
- **Use a monotonic clock source** where the platform offers one for measuring elapsed time, while still anchoring to wall-clock for the timestamp section.

#### Clock skew across nodes

Different machines have slightly different clocks, so IDs are only **roughly** time-ordered globally, not strictly. Within a single node, IDs are strictly increasing; across nodes, two IDs generated in the same millisecond can be ordered by their datacenter/machine bits rather than true time. This is an accepted trade-off — Snowflake promises *sortable-by-time*, not *globally strictly monotonic*.

#### NTP and operations

- Keep nodes on **well-synchronized NTP** to minimize skew.
- Avoid large step corrections; prefer **slewing** (gradual adjustment) so the clock never jumps backward.

---

### Trade-offs and tuning the bit allocation

The 41/5/5/12 split is a default, not a law. You tune it to your scale:

- **More sequence bits** → more IDs per ms per machine (higher single-node throughput), fewer machines or shorter lifespan.
- **More machine/datacenter bits** → more nodes, but lower per-node throughput.
- **More timestamp bits** → longer lifespan, fewer of the other sections.

Document the chosen epoch and layout carefully; changing them later is a migration headache because old IDs assume the old layout.

---

## Step 4 — Wrap Up

### Comparison summary

| Approach | 64-bit | Numeric | Time-sortable | Coordination | SPOF | Notes |
|---|---|---|---|---|---|---|
| DB auto-increment | Yes | Yes | Yes (single node) | Central | Yes | Doesn't scale |
| Multi-master replication | Yes | Yes | No (across nodes) | Config | Per shard | Awkward to grow |
| UUID (v4) | No (128) | No | No | None | None | Simplest; bloats indexes |
| Ticket server | Yes | Yes | Yes | Central | Yes | Batch to reduce round trips |
| **Snowflake** | **Yes** | **Yes** | **Yes (roughly)** | **Only worker-ID assignment** | **None on hot path** | **Recommended** |

### Why Snowflake wins for the stated requirements

It satisfies every functional requirement — 64-bit, numeric, time-sortable, high throughput — while being highly available and requiring **no coordination during ID generation**. The only shared dependency (worker-ID assignment) happens once at startup and can use a battle-tested coordination service.

### Talking points if time remains

- **UUIDv7 / ULID** — modern time-ordered 128-bit alternatives if 64-bit isn't required and you want zero coordination.
- **Security/enumeration** — Snowflake IDs are guessable (sequential-ish). If you must not leak counts or ordering to clients, expose a separate opaque public ID or encrypt the ID for external use.
- **Section-recovery** — because the timestamp is embedded, you can extract the creation time from any ID, which is handy for debugging, sharding, and TTL logic.
- **Clock as the central risk** — most production Snowflake incidents trace back to NTP misconfiguration; treat clock discipline as a first-class operational concern.
