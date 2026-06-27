# Design Consistent Hashing

## Chapter Overview
This chapter explores consistent hashing as a solution for distributing requests and data efficiently across servers in horizontally scaled systems. It addresses problems with traditional modulo-based hashing and presents a scalable alternative.

## The Rehashing Problem

### Traditional Hash Distribution
The basic load balancing formula:
```
serverIndex = hash(key) % N
```
where N represents the total number of servers in the pool.

### Example Distribution (4 Servers)
The chapter provides a table showing 8 keys with their hash values and modulo results:
- key0: hash=18358617, hash%4=1
- key1: hash=26143584, hash%4=0
- key2: hash=18131146, hash%4=2
- key3: hash=35863496, hash%4=0
- key4: hash=34085809, hash%4=1
- key5: hash=27581703, hash%4=3
- key6: hash=38164978, hash%4=2
- key7: hash=22530351, hash%4=3

### Critical Problem: Server Removal
When server 1 goes offline, the pool shrinks to 3 servers. Using `hash % 3` instead:
- Most keys require remapping to different servers
- The same hash values produce different server indices
- Cache clients connect to incorrect servers
- Results in widespread cache misses ("storm of cache misses")

This illustrates why traditional modulo hashing fails in dynamic environments.

---

## Consistent Hashing Foundation

### Definition
Per Wikipedia, consistent hashing is "a special kind of hashing such that when a hash table is re-sized and consistent hashing is used, only k/n keys need to be remapped on average, where k is the number of keys, and n is the number of slots."

**Key Advantage:** Unlike traditional hash tables where most keys must be remapped during resizing, consistent hashing minimizes redistribution.

### Hash Space Concept
- Uses SHA-1 as the hash function
- Output range: 0 to 2^160 - 1
- Denoted as: x0, x1, x2, x3, …, xn
- Creates a continuous space of possible hash values

### Hash Ring Structure
The linear hash space is transformed into a circular ring by "collecting both ends." This creates a continuous structure where:
- Values wrap around (0 follows 2^160 - 1)
- Positions on the ring are uniform
- Enables the clockwise lookup mechanism

---

## Core Implementation: Three Mapping Steps

### Step 1: Map Servers to Ring
Using SHA-1 hash function, place servers onto the ring:
- Server 0, Server 1, Server 2, Server 3 each get positions
- Positions determined by `hash(server_IP_or_name)`
- No modulo operation applied

### Step 2: Map Keys to Ring
Similarly hash cache keys:
- key0, key1, key2, key3 get positions on the same ring
- Uses same hash function as servers
- No modulo operation

### Step 3: Server Lookup (Clockwise Traversal)
To find a key's location:
1. Start at the key's position on the ring
2. Move clockwise around the ring
3. Stop at the first server node encountered
4. That server stores the key

**Example from text:** "Going clockwise, key0 is stored on server 0; key1 is stored on server 1; key2 is stored on server 2 and key3 is stored on server 3."

---

## Dynamic Server Operations

### Adding a Server
When server 4 is added:
- Only affected keys are those between the new server and the previous server (going counter-clockwise)
- In the example: only key0 needs redistribution
- key0 moves from server 0 to server 4
- key1, key2, key3 remain unchanged

**Benefit:** Minimal data movement compared to traditional hashing

### Removing a Server
When server 1 is removed:
- Affected range: keys between the removed server and the previous server (counter-clockwise)
- In the example: only key1 needs redistribution
- key1 moves from server 1 to server 2
- key0, key2, key3 remain on original servers

**Benefit:** Only small fraction of keys require remapping

---

## Two Critical Problems in Basic Approach

### Problem 1: Unbalanced Partition Sizes
**Issue:** Cannot maintain uniform partition sizes when servers are added/removed. A partition is the hash space between adjacent servers.

**Example:** If server 1 is removed, server 2's partition becomes twice as large as server 0 and server 3's partitions.

**Impact:** Uneven load distribution and resource utilization

### Problem 2: Non-Uniform Key Distribution
**Issue:** Keys may not distribute evenly across servers on the ring.

**Example:** Most keys concentrate on server 2, while server 1 and server 3 have no data.

**Impact:** Creates "hotspot" scenarios with uneven server loads

**Solution:** Virtual nodes (replicas) address both problems.

---

## Virtual Nodes / Replicas

### Concept
Instead of one position per server, each server is represented by multiple virtual nodes (replicas) on the ring.

### Implementation Details
- Each real server gets multiple virtual node positions
- Server 0 represented as: s0_0, s0_1, s0_2 (example uses 3 replicas)
- Server 1 represented as: s1_0, s1_1, s1_2
- Each server manages partitions labeled with its identity

### Key Lookup with Virtual Nodes
To find where key0 is stored:
1. Start from key0's position
2. Move clockwise
3. Find first virtual node (example: s1_1)
4. Determine associated server (server 1)

### Impact on Distribution

The text notes that with virtual nodes, "the standard deviation gets smaller with more virtual nodes, leading to balanced data distribution."

**Research findings:**
- 100 virtual nodes: 10% standard deviation from mean
- 200 virtual nodes: 5% standard deviation from mean
- Higher virtual node counts produce more balanced distribution

### Tradeoff Analysis
**Advantages:** More balanced key distribution, improved load distribution

**Disadvantage:** Increased memory overhead for storing virtual node metadata

**Resolution:** Tune the number based on system requirements

---

## Finding Affected Keys During Changes

### Adding a New Server
Process for identifying keys to redistribute:
1. Start at the newly added server position
2. Move counter-clockwise around the ring
3. Stop when encountering another server
4. All keys between these two points are affected

**Example:** When server 4 is added, keys between s3 and s4 must move to server 4.

### Removing an Existing Server
Process for identifying keys to redistribute:
1. Start at the removed server position
2. Move counter-clockwise around the ring
3. Stop when encountering another server
4. Redistribute those keys to the next server clockwise

**Example:** When server 1 is removed, keys between s0 and s1 are redistributed to server 2.

---

## Benefits Summary

### Minimal Key Redistribution
"Minimized keys are redistributed when servers are added or removed."

### Horizontal Scalability
"It is easy to scale horizontally because data are more evenly distributed."

### Hotspot Mitigation
The text explains that "excessive access to a specific shard could cause server overload. Imagine data for Katy Perry, Justin Bieber, and Lady Gaga all end up on the same shard. Consistent hashing helps to mitigate the problem by distributing the data more evenly."

---

## Real-World Applications

### Industry Implementations
- **Amazon Dynamo:** Partitioning component of the key-value store
- **Apache Cassandra:** Data partitioning across clusters
- **Discord:** Chat application infrastructure
- **Akamai:** Content delivery network
- **Maglev:** Google's software network load balancer

---

## Key Takeaways

1. **Problem Solved:** Consistent hashing reduces key redistribution from O(n) to O(n/m) operations, where n is keys and m is servers

2. **Ring Structure:** Converting hash space to a ring enables elegant clockwise traversal for server lookup

3. **Virtual Nodes:** Essential for achieving balanced distribution in production systems

4. **Scalability:** Supports dynamic server addition/removal with minimal data movement

5. **Industry Standard:** Proven approach used by major infrastructure companies

---

# Interview-Grade Enrichment

## Back-of-the-Envelope Math

### Constants we use throughout

| Symbol | Value | Meaning |
|--------|-------|---------|
| K | 10^9 (1 B) | total keys |
| N | 1,000 | physical servers |
| V | 256 | virtual nodes per physical server |
| H | 2^160 | hash space size (SHA-1) |
| avg | K / N = 10^6 | keys per server |

### How many keys move when one server is added or removed?

With N physical servers and V virtual nodes per server, the ring has N * V positions. Removing one physical server deletes V virtual nodes, so a fraction `1/N` of the ring disappears. Each key is uniformly distributed, so the expected fraction of keys that remap is `1/N`. Only those keys that lived in the now-empty arc actually move, while the rest stay put.

Expected remap count = K / N = 10^9 / 10^3 = 10^6 keys.

Compare that to modulo hashing with the same growth: if N grows from 1,000 to 1,001, every key whose hash mod 1000 differs from mod 1001 can move. Roughly 1,000/1,001 ≈ 99.9% of keys remap, which is ~10^9 keys. That is three orders of magnitude more data movement, and that is the rehashing storm consistent hashing exists to prevent.

### Partition-size distribution with virtual nodes

Treat the ring as N*V i.i.d. uniform points on [0, H). The arc length owned by one virtual node is exponentially distributed with mean H/(N*V). A real server owns V such arcs, so its total owned length L_i has mean H/N and variance approximately (V * (H/(N*V))^2) = H^2 / (N^2 * V).

Standard deviation of L_i:

  sigma(L) = H / (N * sqrt(V))

Coefficient of variation:

  CV = sigma(L) / mean(L) = 1 / sqrt(V)

With V = 256:

  CV = 1 / 16 = 6.25%

So the busiest physical server handles roughly mean + 6% of the average, and the lightest handles about mean - 6%. The textbook's "100 vnodes = 10% stddev, 200 vnodes = 5% stddev" matches `1/sqrt(V)` almost exactly, which is the asymptotic law of large numbers at work.

### Memory overhead of the virtual-node map

The ring map is a sorted array of (position, serverId) pairs. Each entry is roughly 24 bytes (8-byte hash + 8-byte server id + alignment). Total ring entries:

  N * V = 1,000 * 256 = 256,000 entries
  Memory = 256,000 * 24 B ≈ 6 MB

That fits in the L2 cache of a single core and is replicated to every node, so it is essentially free. This is why V in the low hundreds is the sweet spot.

### Effect on hotspot keys

If 1% of keys account for 50% of traffic (a typical celebrity-skew distribution), each of those hot keys still hashes to exactly one server, so they are NOT mitigated by consistent hashing alone. They need additional techniques: key fanout (splitting one logical key into N physical keys), per-key rate limiting at the proxy layer, or a separate cache tier with a smaller, dedicated ring.

---

## ASCII Architecture Diagrams

### Diagram 1: Hash ring with three physical servers and virtual nodes

```
                       0
                       |
              s1_v0    .   s0_v2
                 \         /
                  \       /
                   \     /
       s2_v2 ........X........ s1_v1
                  /     \
                 /       \
                /         \
            s0_v1            s2_v1
                |             |
            s0_v0          s2_v0
                       |
                     (2^160 - 1)
                     wraps to 0

  Legend:
   s0_v0..s0_v2  -> 3 virtual nodes for server 0
   s1_v0..s1_v1  -> 2 virtual nodes for server 1
   s2_v0..s2_v2  -> 3 virtual nodes for server 2
   X              -> lookup position of key k

  Lookup rule: walk clockwise from X, return the server
  that owns the first virtual node encountered.
```

### Diagram 2: Server-removal sequence and remap range

```
  BEFORE (server 1 is alive):

    s0_prev (s0_v2)
        \
         \  <- this arc moves to s2 when s1 dies
          \
          s1_v0  s1_v1  s1_v2
              \________|

  AFTER (server 1 is dead):

    s0_prev (s0_v2)
        \
         \  <- formerly-owned arc now belongs to s2
          \
          (s1 is gone) -- clockwise walk skips it
                            \
                             s2_v0

  Number of keys that move = keys in arc between
  s0_prev and s1_v0 (counter-clockwise boundary).
  In expectation: K / N.
```

### Diagram 3: Read-path sequence diagram

```
  Client           Proxy          Ring-LUT         Server
    |                |                |                |
    |-- GET k1 ----->|                |                |
    |                |-- lookup(k1) ->|                |
    |                |<- server=s2 ---|                |
    |                |---------------------------------->|
    |                |                    <- value v ---|
    |<- 200 v -------|                                 |
    |                |                                |
```

### Diagram 4: Add-server sequence diagram

```
  Operator   Coordinator    NewNode S_new    AffectedNodes
     |             |              |                |
     |-- add ----->|              |                |
     |             |-- join ----->|                |
     |             |              |-- heartbeat -->|
     |             |              |                |
     |             |-- publish(vnode list) ---->    |
     |             |              |                |
     |             |-- compute affected ranges ---> |
     |             |              |                |
     |             |              |                |-- stream keys
     |             |              |<---------------|
     |             |              |                |
     |             |<-- ack -------|                |
     |<-- done -----|              |                |
```

---

## Trade-off Tables

### Table 1: Partitioning strategies compared

| Strategy | Remap on add/remove | Balance | Lookup cost | Use when |
|---|---|---|---|---|
| Modulo hashing (hash % N) | O(K) | Perfect if N is fixed | O(1) | Static N, cache never resizes |
| Consistent hashing, no vnodes | O(K/N) | Poor with small N | O(log N) walk or O(N) ring | Tiny clusters only |
| Consistent hashing with V vnodes | O(K/N) | sigma ~ mean/sqrt(V) | O(log(N*V)) with sorted ring | General-purpose sharding |
| Rendezvous (HRW) hashing | O(K/N) | Excellent | O(N) per key (hash all servers) | Small N, want strict balance |
| Jump consistent hash | O(K/N) | Excellent | O(log N) | In-memory, want no ring storage |
| Maglev hashing | O(K/N) | Good with large table | O(1) average | L4 load balancers, Google-style |

### Table 2: Virtual-node count vs cost

| V per server | Std dev of load | Ring entries (N=1000) | Ring memory | Use case |
|---|---|---|---|---|
| 1 | ~100% of mean | 1,000 | ~24 KB | Unacceptable in production |
| 10 | ~32% | 10,000 | ~240 KB | Dev / test only |
| 100 | ~10% | 100,000 | ~2.4 MB | Acceptable minimum |
| 256 | ~6% | 256,000 | ~6 MB | Cassandra-style, sweet spot |
| 1,000 | ~3% | 1,000,000 | ~24 MB | Diminishing returns |
| 10,000 | ~1% | 10,000,000 | ~240 MB | Usually not worth it |

### Table 3: Replication placement options

| Strategy | Failure domain isolation | Balance | Complexity | Cost |
|---|---|---|---|---|
| Walk clockwise N distinct physical servers | Per-server isolation only | Excellent | Low | Low |
| Walk clockwise, one per rack | Rack-level isolation | Good | Medium | Medium (rack-aware ring) |
| Walk clockwise, one per (rack, zone, region) | Tiered isolation | Good | High | High |
| Random pick of N from ring | Per-server isolation | Good but harder to reason about | Medium | Low |
| Leader-follower with deterministic leader | Strong consistency, single primary | Excellent for writes | High | High |

---

## Real-World Case Studies

### Case study 1 — Amazon Dynamo and DynamoDB

Dynamo (DeCandia et al., SOSP 2007) was the original production system that popularized consistent hashing with virtual nodes for Amazon's shopping cart. Each physical node owned V = 100–200 tokens chosen via MD5 hashing of (node IP, a per-node integer counter). DynamoDB, the managed successor, hides the mechanism but still partitions by a 128-bit hash of the primary key into internal shards called "partitions"; each partition maps to 3 replicas across 3 AZs. The reasons were (1) elastic scaling — Amazon adds capacity in minutes during peak — and (2) failure containment — losing an AZ must not lose the cart. The lesson: virtual nodes are not optional; the paper explicitly showed that without them, the imbalance was unacceptable at Amazon's scale.

### Case study 2 — Apache Cassandra and the Murmur3 partitioner

Cassandra uses Murmur3Partitioner, which hashes keys to a 64-bit ring (not 160-bit). Each node owns V = 256 tokens by default, configured via `num_tokens` in cassandra.yaml. Why Murmur3? It is faster than MD5/SHA-1 and produces uniform output, which matters because Cassandra's per-row read path hashes the partition key on every read. The 64-bit ring halves storage and lookup cost relative to SHA-1. The lesson: pick a hash function that matches your coordinate size. SHA-1's 160 bits is overkill for thousands of nodes.

### Case study 3 — Discord's guild routing

Discord runs millions of "guilds" (chat servers). Each guild is sharded by guild_id using consistent hashing across gateway processes. When a user connects to Discord, they are routed to the gateway process that owns their guild, and messages fan out within that process. Consistent hashing is critical because Discord adds and removes gateway processes frequently to absorb traffic spikes (large raid events). Only the guilds whose hashes fall in the new process's arc migrate. The lesson: when your workload is dominated by many small independent units, consistent hashing at the unit level gives you elastic capacity without the coordination cost of a centralized directory.

### Case study 4 — Akamai and Cloudflare CDN edge routing

Akamai and Cloudflare both use consistent-hashing-like techniques to map a client request (often via the URL or a stable client identifier) to one of thousands of edge servers. The ring is logical — edge servers register and deregister as they come online or are drained for maintenance. The benefit is that purging an edge server only affects the keys in its arc, not the entire fleet. Cloudflare's published design (Unimog) goes further with a hybrid approach: consistent hashing for cache keys plus a separate workload-aware scheduler. The lesson: at CDN scale, even a small percentage of unnecessary cache misses costs millions of dollars in origin load.

### Case study 5 — Google's Maglev load balancer

Maglev (Eisenbud et al., NSDI 2016) uses a custom consistent-hashing-like scheme called "Maglev hashing" with a precomputed lookup table of size `M` (typically 65537 or larger). On lookup, the client picks one of M entries, then uses a permutation table to find the backend. It produces O(1) lookup with excellent balance and minimal disruption on backend changes — better than naive ring-walking for L4 load balancing. Google reports using Maglev at the front of essentially every service. The lesson: when you need O(1) lookup at millions of QPS, hash-table-based variants beat sorted-ring variants.

---

## Common Pitfalls & Failure Modes

### Pitfall 1 — The cache-miss storm on member-set change

When a server joins or leaves, the cache clients with the OLD view of the ring will route keys to servers that no longer own them. Those servers will return a miss, the client will re-fetch from origin, and now your origin database sees a spike of traffic proportional to the number of stale clients. Mitigation: gossip-based membership propagation with bounded convergence time (Cassandra uses 3 seconds for phi-accrual failure detection); gossip should carry both adds AND removes, not just heartbeats. Also, version-stamp the ring so old gossip messages cannot resurrect a removed node.

### Pitfall 2 — Heterogeneous capacity without weighted vnodes

If you assign the same number of virtual nodes to a 32-core machine and a 4-core machine, the 4-core box is the bottleneck. The fix is weighted virtual nodes: the 32-core box gets 8x more tokens. DynamoDB and Cassandra both expose this knob (Cassandra's `num_tokens` per node). Failing to weight it correctly is one of the most common production mishaps. Interviewers will probe: "what if your nodes are not identical?"

### Pitfall 3 — Hash function quality

A bad hash function produces clustered positions on the ring, which negates the entire point of virtual nodes. SHA-1, MD5, and Murmur3 are all acceptable. Common mistakes include using Java's `String.hashCode()` (only 32 bits, terrible distribution) or rolling your own. The interviewer will ask: "why Murmur3 over SHA-1?" Answer: speed, determinism, sufficient uniformity at the 64-bit scale, and you do not need cryptographic properties for sharding.

### Pitfall 4 — Token rebalancing is operationally expensive

When you first deploy a cluster with random token assignment, distribution is roughly balanced, but as you add capacity non-uniformly over time, imbalance creeps in. Reassigning tokens requires a "bootstrap" or "rebalance" operation that streams huge amounts of data between nodes. Cassandra's `nodetool repair` and `nodetool move` exist precisely to address this. Interviewers will press: "you added a node and the ring is now unbalanced — what do you do?" The realistic answer is: use a partitioner with predetermined token ranges per node (like sorted token assignment), or accept some imbalance and repair periodically.

### Pitfall 5 — Time-dependent hashing breaks stability

If your hash function uses anything time-varying (timestamp, counter, random nonce), the same key will hash to different ring positions on every lookup, which means you can never cache, never route consistently, and never deduplicate. Snowflake-style IDs work in part because the high bits are time but the ring key is the entire 64-bit ID, which is stable. A common interview trap is "what if I hash by (key, current_minute)?" — that breaks everything.

### Pitfall 6 — Ring partition during network splits

If the cluster experiences a network partition, two halves of the ring can disagree about which nodes are alive. Each half independently accepts writes, and on healing you have divergent replicas. Consistent hashing itself does not solve this; you need replication plus a conflict-resolution policy (last-write-wins, vector clocks, application-level merge). Interviewers will probe: "what happens during a partition?" The honest answer: consistent hashing gives you WHERE to write; you still need to decide WHAT to write.

### Pitfall 7 — Cold-start problem with very small N

With N = 2 or 3 nodes and V = 256 vnodes, you still get good balance in theory. But the standard deviation of partition size is ~1/sqrt(V) of the MEAN, and with only N partitions the law of large numbers has not yet kicked in. Production clusters with fewer than ~10 nodes often see noticeable imbalance. Real-world mitigation: start with N >= 8, or use a partitioner that enforces balanced token assignment (Cassandra's `AllocateTokensForLocalReplicationFactor`-style approach).

---

## Interview Q&A

### Q1 — Walk me through what happens, step by step, when a cache server fails in a traditional `hash % N` setup. Why is that bad?

**Answer sketch:** When the server count changes from N to N-1, every key's target index changes because the modulus changed. Even keys whose hash values did not change will map to a different server index. Cache clients with stale views will route to wrong servers, get cache misses, and stampede the origin database. The cluster effectively re-caches from scratch. In a system with millions of keys and a hot origin path, this manifests as a 5-15 minute latency spike. Consistent hashing reduces the affected fraction from ~99% to 1/N, which at N=1000 is 0.1% — a thousand-fold improvement.

### Q2 — How many virtual nodes per physical server should I pick, and why?

**Answer sketch:** Around 100–256 in production. The coefficient of variation of load is 1/sqrt(V), so V=100 gives ~10% std dev and V=256 gives ~6%. Beyond V=1000 the marginal improvement is small (3%) but the ring lookup table grows linearly and starts to hurt CPU cache locality. The right tradeoff depends on (1) how costly imbalance is — if you're sharding a database, 6% imbalance is fine; if you're load-balancing per-connection, you may want V=1000 — and (2) how often nodes are added — churn increases the cost of lookup table rebuilds.

### Q3 — If I add a new server to my consistent-hash ring, exactly which keys move?

**Answer sketch:** Only the keys whose position falls in the arc counter-clockwise from the new server's first virtual node to the next existing virtual node (going counter-clockwise). All other keys remain on their original servers. The expected fraction that moves is 1/N. In contrast, in `hash % N` essentially 100% of keys move. If you have heterogeneous nodes, the rule generalizes: the new server "claims" a portion of each existing server's partition proportional to its added token count.

### Q4 — My key space is not uniform. Katy Perry's data gets 100x more traffic than most keys. Does consistent hashing help?

**Answer sketch:** No, not by itself. Consistent hashing distributes KEYS uniformly across servers, but it does nothing about TRAFFIC. If a single key is hot, that hot key still lands on exactly one server. Mitigations: (1) key fanout — split "katy_perry" into N sub-keys at the application layer; (2) per-key rate limiting at a proxy layer in front of the cache; (3) a dedicated hot-key cache with its own ring; (4) read replicas on the owning server. The interviewer is testing whether you understand that hashing solves placement, not popularity.

### Q5 — How would you design for multi-region?

**Answer sketch:** Two layers. Layer 1: a per-region ring that places data on servers within the region, optimized for latency. Layer 2: a smaller cross-region ring or explicit region list for replication (typically 2-3 regions, async). Each region's per-region ring is independent and consistent-hashes only within its own fleet. Writes propagate cross-region via a separate replication log (Kafka, DynamoDB global tables). For read paths, you can pin reads to the local region for latency or allow cross-region reads for consistency. The interviewer is checking that you understand the difference between "place this key" (consistent hashing) and "replicate this key" (cross-region policy).

### Q6 — What is the time complexity of a key lookup, and how do you implement it?

**Answer sketch:** O(log(N*V)) with a sorted array and binary search, O(1) with a hash table variant like Maglev, or O(N) with a naive linear scan. Production implementations use the sorted-array variant because it also makes range scans trivial and is cache-friendly. Pseudocode:

```python
def lookup(ring: list[tuple[int, str]], key_hash: int) -> str:
    # ring is sorted by hash position, ascending
    lo, hi = 0, len(ring) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if ring[mid][0] < key_hash:
            lo = mid + 1
        else:
            hi = mid
    # wrap-around
    if ring[lo][0] < key_hash:
        lo = 0
    return ring[lo][1]
```

The wrap-around at `2^160 - 1` is the only subtle piece: if no virtual node has a position greater than the key hash, you return the first entry in the ring (position 0).

---

## Key Terms / Glossary

| Term | Precise definition | Common misconception |
|---|---|---|
| Consistent hashing | A hashing scheme where keys and servers are both mapped onto a circle, and a key is assigned to the next server clockwise on the circle | That it guarantees perfect balance (it does not — it guarantees minimum disruption) |
| Hash ring | The continuous circular hash space [0, 2^H) with endpoints identified | That it is a physical data structure (it is conceptual — the implementation is usually a sorted array) |
| Virtual node (vnode) | A virtual position on the ring owned by a real server; a server typically owns many | That vnodes are separate processes (they are entries in a lookup table) |
| Token | The specific hash value of a virtual node on the ring | That tokens are the same as server IDs (they are derived from server IDs via hashing) |
| Partition | The arc of hash space between two adjacent servers on the ring | That partitions are fixed-size (they are not — they shrink and grow as servers join/leave) |
| HRW / Rendezvous hashing | An alternative to consistent hashing that hashes (key, server) pairs and picks the server with the highest hash | That it is just a name for consistent hashing (it is a distinct algorithm) |
| Gossip protocol | A decentralized failure-detection and membership-propagation scheme where nodes exchange state with random peers | That gossip guarantees convergence in bounded time (it is probabilistic; you need phi-accrual or similar to bound it) |
| Phi accrual failure detector | An adaptive failure detector that outputs a continuous suspicion level instead of a binary alive/dead | That it is binary (it is a continuous phi value; you pick a threshold) |
| Rebalance | The process of moving data when the membership set changes | That rebalance is automatic and instantaneous (it is a heavy, streaming operation in real systems) |
| Jump hash | Lamping and Veach's algorithm for consistent hashing without a ring; uses a single integer and O(log N) per lookup | That it requires storing the ring (it does not — the ring is implicit) |
| Cold start | The state of a cluster with very few nodes, where statistical balance has not converged | That it is solved by virtual nodes alone (with N<8 you still have imbalance) |
| Hash slot | Redis Cluster's term for a fixed partition of the hash ring (16384 slots) | That hash slots are owned by vnodes (in Redis Cluster, slots are owned by primary nodes) |

---

## References

- Karger, Lehman, Leighton, Panigrahy, Levine, Lewin — "Consistent Hashing and Random Trees" (1997)
- DeCandia, Hastorun, Jampani, Kakulapati, Lakshman, Pilchin, Sivasubramanian, Vosshall, Vogels — "Dynamo: Amazon's Highly Available Key-value Store" (SOSP 2007)
- Lamping, Veach — "A Fast, Minimal Memory, Consistent Hash Algorithm" (2014) — jump consistent hash
- Eisenbud, Yi, Contavalli, Smith, Kononov, Lewis-Hood, Kuretzky — "Maglev: A Fast and Reliable Software Network Load Balancer" (NSDI 2016)
- Apache Cassandra documentation — Murmur3Partitioner, num_tokens
- Discord engineering blog — guild sharding
- Cloudflare blog — Unimog load balancing