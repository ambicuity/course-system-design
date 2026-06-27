# Scale From Zero To Millions Of Users

## Chapter Overview

This chapter explores the iterative process of scaling a system from supporting a single user to millions of users. It demonstrates essential architectural techniques and design patterns necessary for building reliable, high-performance distributed systems.

The progression below is deliberately incremental: each stage solves a specific failure mode introduced by the previous one. Vertical scaling breaks because of hardware ceilings. Caches break because of consistency. Sharding breaks because of resharding pain. Treat each transition as a response to a known concrete problem, not as a fashion choice.

---

## Single Server Setup

### Architecture Description

The foundational design runs all components on one machine: web application, database, cache, and related services. This represents the starting point for system development.

### Request Flow Process

1. Users access websites via domain names (e.g., api.mysite.com)
2. Domain Name System (DNS) translates domain names to IP addresses
3. HTTP requests travel directly to the web server using the resolved IP
4. Web server returns HTML pages or JSON responses

### Traffic Sources

**Web Application:**
- Server-side languages (Java, Python) handle business logic and storage
- Client-side languages (HTML, JavaScript) manage presentation

**Mobile Application:**
- HTTP protocol enables communication with web servers
- JSON format serves as the standard API response structure

Example JSON API response for retrieving user data demonstrates lightweight data transfer suitable for mobile clients.

### When the Single Server Breaks

A single host combining nginx, a Python WSGI app, MySQL, and Redis can serve tens of thousands of requests per minute if you tune it carefully. What kills it is not throughput but the absence of a second copy: a kernel panic, an OOM event from a bad migration, or a network blip during a deploy. Once a single component dies, the entire product goes down. The single-server stage is therefore not a real production target. It is a one-day spike to confirm the idea is interesting enough to invest in a second box.

---

## Database Separation

### Multi-Server Architecture

When user bases grow, separating web/mobile traffic (web tier) from database storage (data tier) enables independent scaling of each component. This prevents resource contention and allows optimization targeted to specific functions.

### Database Type Selection

**Relational Databases (RDBMS/SQL):**
- Popular options: MySQL, Oracle, PostgreSQL
- Data organized in tables and rows
- Supports JOIN operations across tables
- Proven technology with 40+ year history

**Non-Relational Databases (NoSQL):**
- Types: CouchDB, Neo4j, Cassandra, HBase, DynamoDB
- Categorized as: key-value stores, graph stores, column stores, document stores
- Generally no JOIN operation support

**NoSQL Selection Criteria:**
- Application requires super-low latency
- Data is unstructured or lacks relational characteristics
- Only serialization/deserialization needed (JSON, XML, YAML)
- Massive data storage requirements

### Choosing SQL vs NoSQL in Practice

The textbook framing suggests you pick based on data shape. In practice you pick based on the dominant access pattern. If the workload is point reads by primary key and you cannot afford cross-region replication latency, you reach for a key-value store. If you need multi-row transactions, secondary indexes, and ad-hoc analytics over the same tables, you stay on a relational engine and pay the price of careful schema work. Polyglot persistence — MySQL for transactions, Elasticsearch for search, S3 for blobs — is the normal outcome at scale, not the exception.

---

## Vertical vs. Horizontal Scaling

### Vertical Scaling ("Scale Up")

Adding computational power to existing servers—increasing CPU, RAM, or disk capacity.

**Limitations:**
- Hardware maximum thresholds prevent unlimited expansion
- Single point of failure without redundancy
- High capital costs for powerful server hardware

### Horizontal Scaling ("Scale Out")

Distributing load across multiple servers rather than concentrating on one.

**Advantages:**
- No inherent hardware ceiling
- Enables redundancy and failover capabilities
- More economical for large-scale applications

### Trade-off Table: Vertical vs Horizontal Scaling

| Dimension | Vertical | Horizontal |
|---|---|---|
| Latency | Lowest possible (no RPC between tiers) | Slightly higher due to network hops |
| Failure domain | Whole system fails if box fails | Failure isolated per node |
| Cap on growth | Hardware ceiling (typically 1-2 TB RAM, 128 cores) | Effectively unbounded |
| Capital cost | Exponential at the high end | Linear |
| Operational cost | Low (one machine to patch) | Higher (many machines, config drift) |
| Re-shaping workload | Requires downtime | Add or remove nodes online |
| Consistency model | Trivially consistent | Must design around distributed state |
| Right for | Early stage, single-tenant workloads | Multi-tenant, global, public-facing products |

---

## Load Balancer

### Function and Benefits

A load balancer distributes incoming traffic evenly among multiple web servers, addressing both availability and performance challenges.

### Architecture Details

- Users connect to load balancer's public IP address
- Web servers communicate internally via private IPs
- Private IPs remain unreachable from the internet but enable secure internal communication

### Problem Resolution

**Failover Protection:**
- If one server fails, traffic automatically routes to healthy servers
- New healthy servers join the pool automatically

**Scalability:**
- Adding servers to the pool enables graceful traffic distribution
- Load balancer automatically routes requests to new servers

### L4 vs L7 Load Balancing

L4 load balancing operates on connection-level metadata (src/dst IP, src/dst port, protocol). It is fast — typically a kernel-bypass datapath on modern hardware — and is the right choice when you want raw TCP/UDP fan-out with minimal cost per packet. L7 load balancing parses the HTTP request and can route on host, path, headers, or cookies. L7 costs more CPU but unlocks per-route policies (send `/api/*` to one fleet, `/static/*` to another) and request-aware features like rate limiting, auth checks, and sticky-by-cookie sessions. A common pattern is L4 in front of L7: the L4 balancer terminates TCP and forwards to a fleet of L7 proxies (Envoy, NGINX, HAProxy) which then apply route logic.

---

## Database Replication

### Master-Slave Model

"Database replication can be used in many database management systems, usually with a master/slave relationship between the original (master) and the copies (slaves)."

**Write Operations:** Directed exclusively to master database

**Read Operations:** Distributed across slave databases

### Advantages

**Performance Enhancement:**
- Write and update operations concentrate on master nodes
- Read operations distribute across slave nodes
- Parallel query processing increases throughput

**Reliability:**
- Data survives natural disasters through geographic distribution
- Complete data loss prevented through multi-location replication

**High Availability:**
- Websites continue operating despite individual database failures
- Data access persists via alternative database servers

### Failure Handling

**Slave Database Failure:**
- Temporary read redirection to master database
- Replacement slave database quickly provisions
- Multiple slaves enable read distribution to healthy instances

**Master Database Failure:**
- Slave database promotes to master status
- All operations redirect to new master temporarily
- Data recovery scripts reconcile missing information
- New slave database provisions for data replication

### Replication Topologies

Beyond simple master-slave, real systems use:
- **Synchronous replication to one replica, asynchronous to others** — gives you a hot spare without paying the latency of a quorum commit on every write (used at Amazon, Google).
- **Cascading replicas** — replicas feed other replicas, which keeps WAN traffic low but extends replication lag.
- **Multi-master** — writes accepted in any region, with conflict resolution (typically last-writer-wins or CRDTs). DynamoDB Global Tables, Cassandra, and Spanner deployments lean on multi-master.

Each topology trades a different amount of write latency and operational complexity for a different availability and consistency profile. Interview-grade answers name the topology explicitly rather than waving at "replication."

---

## Cache Layer

### Cache Tier Architecture

A temporary data store operating significantly faster than databases, positioned between web servers and persistent storage.

**Benefits:**
- Improved system performance
- Reduced database workload
- Independent cache tier scaling

### Read-Through Caching Strategy

1. Web server checks cache for requested data
2. If present, data returns to client immediately
3. If absent, query database and store response in cache
4. Data returns to client for future rapid access

### Common Cache APIs

Cache systems typically provide simple interfaces. Example Memcached operations include setting values with TTL (Time-to-Live) expiration and retrieving stored data.

### Caching Considerations

**Usage Decisions:**
- Optimal for frequently-read, infrequently-modified data
- Unsuitable for persistent data storage (volatile memory)
- Cache server restarts cause complete data loss

**Expiration Policies:**
- Implement time-based expiration to prevent staleness
- Avoid excessively short expiration causing frequent database reloads
- Avoid excessively long expiration maintaining data freshness

**Consistency Challenges:**
- Data store and cache can become out-of-sync
- Non-transactional updates create inconsistency risks
- Multi-region scaling amplifies synchronization complexity

**Single Point of Failure Mitigation:**
- Deploy multiple cache servers across data centers
- Overprovision memory capacity for buffer during growth increases

**Eviction Policies:**
- Least-Recently-Used (LRU) represents the most common approach
- Alternative strategies: LFU (Least Frequently Used), FIFO (First In First Out)
- Policy selection depends on specific access patterns

### Cache Patterns Beyond Read-Through

- **Write-through:** every write hits the database and the cache in the same call. Simpler reasoning, but every write pays a cache round-trip even when nobody will read the value soon.
- **Write-behind (write-back):** write goes only to the cache; a background worker flushes to the database. Very fast writes, but you can lose data if the cache dies before flushing. Used in heavy-write paths like view counters and analytics.
- **Cache-aside (lazy loading):** what read-through is called when the application — not the cache library — is responsible for populating entries. Most web frameworks default to this.
- **Refresh-ahead:** cache pre-emptively refreshes entries before they expire. Best for hot keys where a cache miss storm would crush the origin.

### The Thundering Herd Problem

When a hot key expires and a thousand concurrent requests all see "miss," they stampede the database. Mitigations: a single-flight lock (only one request fetches, others wait), request coalescing, jittered TTLs (each replica expires at a slightly different time), and probabilistic early expiration.

---

## Content Delivery Network (CDN)

### Overview

A globally-distributed server network delivering static content efficiently. Servers cache images, videos, CSS files, JavaScript, and similar assets.

### Performance Benefits

Geographic proximity determines delivery speed. Users receive content from CDN servers closest to their location, reducing latency compared to retrieving from origin servers.

Example: CDN delivery (30ms) dramatically improves on direct origin access (120ms) for users far from origin infrastructure.

### CDN Workflow

1. User requests static content (e.g., image.png) via CDN provider domain
2. CDN checks internal cache for requested file
3. On cache miss, CDN retrieves file from origin server
4. Origin returns file with optional TTL header indicating cache duration
5. CDN caches file and returns to user
6. Subsequent requests for same file serve from cache during TTL validity

### Implementation Considerations

**Cost Management:**
- Third-party providers charge data transfer fees
- Infrequently-accessed assets provide minimal benefit
- Cost-benefit analysis necessary for asset inclusion

**Cache Expiration Strategy:**
- Appropriately-timed expiration critical for time-sensitive content
- Short expiration triggers unnecessary origin reloads
- Long expiration allows content staleness

**Failure Handling:**
- Design fallback mechanisms for CDN outages
- Clients should detect failures and request directly from origin

**File Invalidation:**
- API-based removal enables explicit cache clearing
- Object versioning via URL parameters (e.g., image.png?v=2) serves alternate versions

### When the CDN Is the Wrong Answer

CDNs shine for static, globally read, infrequently updated assets: images, JS bundles, fonts, video chunks. They are the wrong tool for personalized HTML, authenticated API responses, or anything that requires real-time consistency. A common over-eager mistake is "just put it behind a CDN" — that buys you cache-control headaches, origin-shield misconfiguration, and surprise egress bills for cache misses during traffic spikes.

---

## Stateless Web Tier

### Stateful Architecture Problems

A stateful server maintains client data between requests. Each client must route to the same server, creating rigid coupling.

**Challenges:**
- Sticky sessions increase load balancer overhead
- Server addition/removal becomes complex
- Server failures cause client disconnection

### Stateless Architecture Solution

Moving session data to persistent external storage (relational database, NoSQL, cache systems) enables any web server to service any request.

**Benefits:**
- HTTP requests route to any available server
- Simplified horizontal scaling through server addition/removal
- Improved robustness against individual server failures
- Enhanced system reliability

### Implementation

State data stores in shared persistent storage, allowing web servers to fetch session information on-demand. Autoscaling provisions or removes servers based on traffic without data migration concerns.

### What "Stateless" Actually Means

It means the server holds no per-client state in local memory between requests. It does not mean the system has no state — sessions live in Redis, uploads stream to S3, counters live in Cassandra. The discipline is about where the state lives (a shared tier) versus where it does not live (process-local memory). This separation is what makes horizontal autoscaling, blue-green deploys, and graceful failover possible.

---

## Data Centers

### Multi-Data Center Strategy

Operating across geographic regions improves availability and user experience. Users receive service from the nearest data center through geoDNS routing.

### Normal Operation

GeoDNS (geographic DNS) routes users based on location. Traffic distribution splits between data centers (e.g., x% US-East, (100-x)% US-West) proportional to user distribution.

### Failure Scenarios

Complete data center outages trigger automatic rerouting. Example: US-West offline redirects 100% traffic to US-East temporarily.

### Technical Challenges

**Traffic Redirection:**
- GeoDNS automatically directs requests to nearest healthy data center
- User location determines routing decisions

**Data Synchronization:**
- Different regions maintain separate databases and caches
- Failover scenarios may route users to data centers with unavailable information
- Asynchronous replication across data centers maintains consistency
- Netflix demonstrates effective multi-data center replication patterns

**Testing and Deployment:**
- Multi-location validation ensures consistent behavior
- Automated deployment tools maintain service consistency across data centers

### Active-Active vs Active-Passive

Two-region topologies split into two camps:
- **Active-active** — both regions serve traffic and accept writes. Maximizes utilization, but forces you to deal with cross-region write conflicts (last-writer-wins, CRDTs, vector clocks) and per-region consistency. DynamoDB Global Tables and Cloudflare's anycast network run this way.
- **Active-passive** — one region takes writes, the other is a warm replica promoted only during failover. Easier to reason about (still one source of truth) but burns the cost of the passive region 24/7.

Most consumer products start active-passive and migrate to active-active once their traffic and engineering investment justify it.

---

## Message Queue

### Architecture and Purpose

A durable, memory-resident component enabling asynchronous communication between system components. Producers publish messages; consumers subscribe and process them independently.

**Decoupling Benefits:**
- Producers operate without consumer availability
- Consumers process messages when available
- Producer and consumer scale independently

### Use Case Example

Photo customization application demonstrates message queue utility. Web servers publish photo processing tasks to a queue; dedicated worker processes asynchronously complete customization operations (cropping, sharpening, blurring).

**Scaling Flexibility:**
- Large queue sizes trigger worker addition, reducing processing time
- Empty queues enable worker reduction, optimizing resource utilization

### Message Queue Semantics That Matter

In interviews, name the delivery guarantee you want:
- **At-most-once** — message may be lost, but never duplicated. Cheap. Use for metrics.
- **At-least-once** — message will arrive, but may be duplicated. Workers must be idempotent. The Kafka/SQS default.
- **Exactly-once** — true exactly-once is famously hard. Most "exactly-once" systems are at-least-once plus consumer-side dedup using an idempotency key.

Also call out ordering. Kafka preserves per-partition order; SQS standard queues do not. If your business logic depends on "send email before charge card," you need ordered delivery and a single consumer for that partition.

---

## Logging, Metrics, and Automation

### Logging

Error log monitoring enables rapid problem identification. Centralized log aggregation services improve searchability and analysis across distributed systems.

### Metrics Collection

Different metric categories provide system health insights:

**Host-Level Metrics:**
- CPU utilization
- Memory consumption
- Disk I/O performance

**Aggregated Metrics:**
- Database tier performance
- Cache tier efficiency
- Multi-component system health

**Business Metrics:**
- Daily active users
- User retention rates
- Revenue figures

### Automation

As systems grow complex, automation becomes essential:

**Continuous Integration:**
- Automated verification of code check-ins
- Early problem detection
- Improved team productivity

**Build/Test/Deploy Automation:**
- Streamlined development workflows
- Reduced manual errors
- Faster iteration cycles

### The Four Golden Signals

When asked "what do you monitor?" the best answer references Google's SRE book explicitly: **latency, traffic, errors, saturation**. Latency distinguishes successful from failed requests. Traffic is demand on the system. Errors are rate of failed requests (explicit 5xx and policy failures). Saturation is how "full" the service is — closest utilization to its limit. Add the **USE method** (utilization, saturation, errors) at the host level and the **RED method** (rate, errors, duration) at the service level. Most teams that don't have a framework end up with vanity dashboards and miss the actual incident.

---

## Database Scaling

### Vertical Scaling Approach

Adding computational resources to individual servers (CPU, RAM, disk capacity).

**Limitations:**
- Hardware maximums create absolute scaling ceiling
- Single server failure causes complete system outage
- Expensive powerful servers increase capital costs

**Real-World Example:**
Stack Overflow supported 10+ million monthly users with single master database through vertical scaling, demonstrating viability at certain scales.

### Horizontal Scaling (Sharding)

Distributing large databases across multiple servers into independent "shards"—each sharing identical schema while containing unique data subsets.

### Sharding Implementation

**Hash Function Routing:**
Data allocation uses hash functions to direct queries to appropriate shards. Example: user_id % 4 determines which of four shards stores user data.

**Sharding Key Selection:**
The sharding key (partition key) determines data distribution. Critical selection criteria include even data distribution preventing some shards from becoming bottlenecks.

### Sharding Challenges

**Resharding Requirements:**
- Individual shards reach capacity limits during rapid growth
- Uneven data distribution causes some shards to exhaust faster
- Sharding function updates and data migration become necessary
- Consistent hashing provides common solution for resharding problems

**Celebrity Problem (Hotspot Keys):**
Excessive access to specific shards overwhelms servers. Example: social network celebrities (Katy Perry, Justin Bieber, Lady Gaga) might hash to identical shard, causing read operation overload.

**Solutions:**
- Dedicated shards for high-access celebrities
- Further partition celebrity shards for extreme cases

**Join and De-normalization Complexity:**
- Join operations across sharded databases become difficult
- Common workaround: de-normalize databases for single-table queries
- Data redundancy increases but eliminates cross-shard JOIN requirements

### Sharding Topologies Compared

| Topology | How data splits | Strengths | Weaknesses |
|---|---|---|---|
| Hash-based | hash(key) mod N | Even distribution | Re-sharding is a full re-map |
| Range-based | by key range (e.g., user_id 0–10M) | Range queries are cheap | Hotspots at the high end |
| Directory-based | lookup service maps key -> shard | Flexible | Lookup service is a SPOF unless replicated |
| Consistent hashing | hash to a ring | Adding nodes moves ~1/N keys | Uneven load without virtual nodes |
| Geo-sharding | by user region | Low read latency locally | Cross-region joins and aggregations are painful |

---

## Complete Scaling Architecture

### Final Design Components

The comprehensive system incorporates:

1. **Load Balancer** - Distributes traffic across multiple web servers
2. **Web Tier** - Stateless servers enabling horizontal scaling
3. **Cache Layer** - Reduces database load through data caching
4. **Database Tier** - Sharded databases supporting massive data volumes
5. **NoSQL Storage** - Handles non-relational data requirements
6. **Message Queue** - Enables asynchronous task processing
7. **CDN** - Serves static content globally
8. **Multi-Data Center** - Geographic distribution for availability
9. **Monitoring Tools** - Logging, metrics, and automation infrastructure

### Reference Architecture Diagram

```
                            ┌────────────────────────────────────────┐
                            │              GeoDNS                   │
                            │   resolves user to nearest region     │
                            └───────────────────┬────────────────────┘
                                                │
        ┌───────────────────────────────────────┼───────────────────────────────────┐
        │                                       │                                   │
        ▼                                       ▼                                   ▼
   US-EAST REGION                       EU-WEST REGION                     AP-SOUTH REGION
   ┌──────────────┐                    ┌──────────────┐                   ┌──────────────┐
   │ L4 LB / ANY  │                    │ L4 LB / ANY  │                   │ L4 LB / ANY  │
   └──────┬───────┘                    └──────┬───────┘                   └──────┬───────┘
          │                                   │                                   │
          ▼                                   ▼                                   ▼
   ┌──────────────┐                    ┌──────────────┐                   ┌──────────────┐
   │  L7 Gateway  │                    │  L7 Gateway  │                   │  L7 Gateway  │
   │  (auth, RL)  │                    │  (auth, RL)  │                   │  (auth, RL)  │
   └──────┬───────┘                    └──────┬───────┘                   └──────┬───────┘
          │                                   │                                   │
   ┌──────┼───────────────┐            ┌──────┼───────────────┐          ┌──────┼───────────────┐
   ▼      ▼               ▼            ▼      ▼               ▼          ▼      ▼               ▼
 User  Post  Notif     Workers     User  Post  Notif     Workers    User  Post  Notif     Workers
 Svc   Svc   Svc       (queue)     Svc   Svc   Svc       (queue)    Svc   Svc   Svc       (queue)
   │      │       │       │            │      │       │       │         │      │       │       │
   ▼      ▼       ▼       ▼            ▼      ▼       ▼       ▼         ▼      ▼       ▼       ▼
 Redis  Redis  Redis   Kafka        Redis  Redis  Redis   Kafka       Redis  Redis  Redis   Kafka
 (LRU)  (LRU)  (pub)  (partitions)  (LRU)  (LRU)  (pub)  (partitions) (LRU)  (LRU)  (pub)  (partitions)
   │      │               │            │      │               │         │      │               │
   └──────┼───────────────┼────────────┘      │               │         └──────┼───────────────┼────────────┘
          ▼               ▼                   ▼               ▼                 ▼               ▼
        Shard 0  ...  Shard N (per-shard primary + 2 replicas, async cross-region replication)
```

The same diagram, collapsed, looks like this for one region:

```
        Client
          │
          ▼
        CDN  ──────► Origin (for cache miss / API)
          │
          ▼
      Load Balancer (L4 + L7)
          │
          ▼
   ┌──────┴──────┐
   ▼             ▼
 Web Node 1   Web Node N
   │             │
   └──────┬──────┘
          │
          ▼
       Cache (Redis)
          │ (miss)
          ▼
   DB Primary ──► DB Replicas (read fan-out)
```

---

## Back-of-the-Envelope Math

A worked example for "what does it take to serve 10 million DAU" — the kind of number a candidate should be able to chew through in 90 seconds.

**Assumptions (state them out loud):**
- 10 M DAU
- Average user makes 20 read requests and 2 write requests per day
- Average response payload: read 10 KB, write 1 KB
- Peak hour carries 2x the average load

**QPS:**

```
Avg read  QPS = 10e6 * 20 / 86_400      ≈ 2,315 QPS
Avg write QPS = 10e6 *  2 / 86_400      ≈   231 QPS
Peak QPS (2x)                           ≈ 4,630 read + 462 write
```

**Bandwidth:**

```
Read  bandwidth = 2_315 * 10 KB/s ≈ 23 MB/s avg, ~46 MB/s peak
Write bandwidth =   231 *  1 KB/s ≈  0.23 MB/s avg,  ~0.46 MB/s peak
```

**Storage per day:**

```
Writes/day = 10e6 * 2 = 20 M writes
Bytes/day = 20e6 * 1 KB = 20 GB/day raw
5-year retention = 20 GB * 365 * 5 ≈ 36.5 TB (raw, before replication and indexes)
With 3x replication overhead                 ≈ 110 TB
```

**Cache sizing:**

```
Hot working set (1% of users active in any minute) ≈ 100 K users
Session objects at ~5 KB each               ≈ 500 MB
10x headroom for hot reads + joins          ≈ 5 GB
```

**Servers (rough):**

```
A single web node can serve ~1 K QPS at p99 < 100 ms.
Peak QPS ≈ 5 K → 5 web nodes minimum, 10 for headroom and rolling deploys.
DB primary can absorb ~1 K write QPS → 1 primary, 2 read replicas is sufficient.
```

These numbers are back-of-envelope; the real value is showing the shape of the workload, not the precision.

---

## ASCII Architecture Diagrams

### 1. Read Path with Cache and CDN

```
       Browser (US-East user)
              │
              │  GET /product/42
              ▼
        ┌─────────────┐
        │   CDN edge  │  <─ cache hit for static assets (HTML/JS/CSS/images)
        └──────┬──────┘
               │ cache miss for /product/42 payload
               ▼
        ┌─────────────┐
        │  DNS / Anycast
        └──────┬──────┘
               │
               ▼
        ┌─────────────┐
        │  L4 LB      │
        └──────┬──────┘
               │
               ▼
        ┌─────────────┐
        │  L7 Gateway │  <─ auth, rate limit, request tracing
        └──────┬──────┘
               │
               ▼
        ┌─────────────┐         ┌─────────────────┐
        │  Web Node   │ ──GET─►│  Redis cluster  │
        │ (stateless) │ ◄─hit─ │  (product cache)│
        └──────┬──────┘         └─────────────────┘
               │ miss
               ▼
        ┌─────────────┐
        │  Product DB │  <─ primary (master) + replicas (slaves)
        └─────────────┘
```

### 2. Write Path with Async Side Effects

```
       Client POST /order
              │
              ▼
        ┌─────────────┐
        │  L7 Gateway │  <─ auth, validation, rate limit, idempotency-key check
        └──────┬──────┘
               │
               ▼
        ┌─────────────┐
        │  Order Svc  │ ──BEGIN TX──► Order DB (primary)
        │             │ ──INSERT────► Order table (committed)
        └──────┬──────┘
               │
               │ publish "order.created" event
               ▼
        ┌─────────────┐
        │    Kafka    │   <─ durable, partitioned by order_id
        └──┬──────┬───┘
           │      │
           ▼      ▼
   Payment Svc  Email Svc    <─ independent consumers, separate failure domains
   (idempotent) (idempotent)
```

### 3. Multi-Region Failover

```
   NORMAL:                       FAILOVER (us-east down):
                                  ┌──────────────┐
   US users ─► GeoDNS ─► us-east ┌► US users ─► GeoDNS ─► us-west (100%)
   EU users ─► GeoDNS ─► eu-west │  EU users ─► GeoDNS ─► ap-south
   AP users ─► GeoDNS ─► ap-south│  AP users ─► GeoDNS ─► us-west (partial)
                                  └──────────────┘
   Cross-region replication:      Cross-region replication:
   us-east (R) ──► us-west (W)    us-west now accepts writes from US users;
   us-west (R) ──► eu-west (W)    ap-south may briefly serve stale reads
   ap-south (R) ◄── eu-west (W)   until replication catches up
```

---

## Trade-off Tables

### Database Choice: SQL vs NoSQL vs NewSQL

| Dimension | MySQL/Postgres | Cassandra / ScyllaDB | Spanner / CockroachDB | DynamoDB |
|---|---|---|---|---|
| Consistency | Strong (per-shard) | Tunable, eventually consistent by default | Strong, global | Tunable (per-request) |
| Write latency (single region) | Low | Very low | Medium | Very low |
| Multi-region writes | Single writer per shard | Multi-master, last-write-wins | Multi-master with HLC | Multi-master, conflict resolution |
| Operational burden | Medium | Medium-High | High | Low (managed) |
| Query flexibility | Rich SQL | CQL, narrow queries | SQL | Key/secondary index only |
| Cost at scale | Low (open-source) | Medium | High | High at very large scale |
| Best for | OLTP, joins, transactions | Time-series, write-heavy | Global OLTP | Serverless, simple key access |

### Cache Choice: Redis vs Memcached

| Dimension | Redis | Memcached |
|---|---|---|
| Data structures | Strings, hashes, lists, sets, sorted sets, streams, bitmaps | Strings only |
| Persistence | RDB snapshots, AOF log | None (always in memory, evict on restart) |
| Replication | Built-in primary-replica | Client-side hashing across nodes |
| Pub/Sub | Yes | No |
| Memory efficiency | Slightly higher overhead per key | Best-in-class bytes-per-key |
| Operational maturity | Mature, complex knobs | Trivial to run |
| Sweet spot | When you need TTL, pub/sub, sorted sets, or persistence | Pure read-through cache with huge item counts |

### Stateful Sessions: Sticky Sessions vs Centralized Store

| Dimension | Sticky Sessions | Centralized Session Store (Redis) |
|---|---|---|
| Latency | Lowest (one hop) | +1 ms typical |
| Resilience to node loss | Bad — sessions lost on crash | Excellent — session outlives any node |
| Autoscaling | Awkward (must drain) | Trivial |
| Operational burden | Low initially, high later | Higher initially, scales linearly |
| Right for | Legacy systems you cannot refactor | Any new stateless design |

---

## Real-World Case Studies

### 1. Instagram — Sharding Postgres for Billions of Photos

Around 2012 Instagram publicly described how they scaled a single Postgres instance by sharding across 12 logical shards hosted on a smaller number of physical boxes. They used Postgres's `schema` namespace feature to keep all shards on one server early, then promoted each schema to its own dedicated server as traffic grew. Their primary key strategy (`nextval` from a centralized sequence on a separate schema) avoided the classic "shard-local sequences produce conflicting IDs" bug. They also exposed a "friendship" service that knew how to route queries to the right shard by user_id. The lesson for interviews: sharding is not a single big-bang decision, it is a series of migrations where each step keeps the system running. Source: Instagram Engineering blog, "Sharding & IDs at Instagram."

### 2. Stack Overflow — A Vivid Counter-Example

Stack Overflow famously served the entire planet's developers from a handful of servers — by 2013, the team reported running on a single SQL Server instance handling billions of requests per month. Why does this matter for an interview? It shows that vertical scaling with disciplined queries and aggressive caching is a legitimate endgame for many workloads. The mistake is treating it as universally applicable. The takeaway is to ask "what is the size and shape of this workload" before reaching for sharding. Source: Marco Cecconi, "What it takes to run Stack Overflow," multiple Stack Overflow blog posts.

### 3. Dropbox — Magic Pocket and the Metadata Service

Dropbox split its storage into two problems: the bytes (file content) and the metadata (filenames, namespaces, sharing permissions). They moved bytes to "Magic Pocket," a custom exabyte-scale object store built from commodity hardware. Metadata went into a separate sharded MySQL fleet called the "namespace service" with carefully designed consistency boundaries. By 2018 they had consolidated billions of metadata entries into a system handling millions of QPS with strict consistency. The lesson: when scaling, decouple storage of bytes from storage of relationships. Most "scaling" failures in interviews come from conflating them. Source: James Cowling et al., "Magic Pocket," Dropbox Tech Blog.

### 4. Discord — The Trillion-Message Storage Migration

Discord stored messages in a sharded MongoDB cluster that, by 2022, had crossed a trillion documents. They migrated the entire message store to Cassandra and then later to ScyllaDB, primarily because MongoDB's per-document storage overhead and compaction behavior stopped scaling for them. Key detail: they redesigned the data model around composite partition keys (`channel_id, bucket`) and wrote a parallel-run system that compared query results across both stores during cutover. For interviews: when sharding is "almost working but not quite," the fix is usually data-model redesign, not more shards. Source: Discord Engineering blog, "How Discord Stores Billions of Messages."

### 5. Cloudflare — Anycast + Global Edge

Cloudflare's edge runs as a single anycast network — the same IP address advertised from every point of presence. When a user requests a page, BGP routes them to the topologically nearest healthy PoP. Inside each PoP, the request hits a Varnish/nginx-based proxy that handles caching, TLS termination, and a layer-7 firewall. Cloudflare famously uses this architecture for rate limiting — the rate limit decision happens at the edge, in front of origin, with counters eventually consistent across regions. For interviews, Cloudflare is the canonical reference for "do it at the edge." Source: Cloudflare blog, "Introducing Cloudflare" and subsequent engineering posts.

---

## Common Pitfalls & Failure Modes

### Pitfall 1: Treating the Single Server as Production

A single box is fine for an MVP. It is not fine as a long-running target. Teams that keep "the production server" running for nine months discover on day 270 that nobody knows which kernel version is on it, the disk is 92% full, and the only engineer who knew how to deploy it has left. The fix is to formalize "second box day" early — even if the second box only takes 1% of traffic. Running two boxes turns every operational process (deploys, backups, schema migrations, observability) into a real exercise instead of a future theoretical problem.

### Pitfall 2: Caching Everything and Invalidation Nowhere

The most common cache bug is not "we forgot to cache this." It is "we cached it three different ways with three different TTLs and nobody knows which one the user sees." Symptoms: a user changes their avatar and sees the old one for an hour, or worse, a price-tag cache shows different values to different customers during a flash sale. Fix: pick one canonical write path (e.g., always invalidate on the database write), and prefer TTLs short enough that bugs self-heal even if invalidation logic is wrong.

### Pitfall 3: Sharding Before You Need To

Sharding is a tax you pay for years. Once your data lives in shards, every operational tool — backups, restores, schema migrations, ad-hoc analytics, joins — becomes more expensive. Teams that shard at 100 GB of data to feel "scalable" often regret it at 5 TB when they want to run a cross-shard aggregation. The better path is usually: vertical scaling, then read replicas with caching, then carefully chosen sharding once the workload actually demands it. In interviews, "have you considered not sharding?" is a strong signal of engineering judgment.

### Pitfall 4: Stateful Sessions Hidden in Process Memory

It is easy to ship a feature that stores a counter, a JWT refresh token, or a WebSocket connection map in `self.__dict__`. The first time the load balancer routes the next request to a different node, the user gets logged out. The fix is to be religious about statelessness at the web tier: every piece of per-user state goes to Redis, the database, or an external store. Treat process-local memory as a bug unless you have a specific, named reason for it.

### Pitfall 5: Synchronous Chains That Cross the Ocean

A request that calls an API in `us-east-1`, then a payment service in `eu-west-1`, then writes back to a primary in `ap-southeast-1` carries three round trips of cross-region latency (~70 ms each, ~210 ms minimum). At p99 it becomes seconds. The cure is to colocate the request path with the data: route by user region, replicate writes asynchronously across regions, and avoid the temptation to do "one global strongly consistent database" unless your consistency requirements genuinely demand it.

---

## Interview Q&A

### Q1: "When do you stop vertically scaling and start horizontally scaling?"

**Answer sketch:** Stop when you hit the next ceiling — usually hardware, single-thread performance, or the cost-per-vertical-step curve becoming exponential. Concretely: once a single box costs more than ~$20K/month, once a single MySQL primary cannot absorb your write QPS at p99 < 50 ms, or once one outage takes down the entire product. The real signal is not a load number — it is whether the system has become a single point of failure for the business.

### Q2: "How do you choose a sharding key?"

**Answer sketch:** Pick the key that appears in the vast majority of queries. For a user-facing product that is `user_id`. For a messaging product that is `conversation_id`. Avoid picking "the obvious key" (`created_at`) — it produces range scans but extreme hotspots. Then verify two properties: (1) the key distributes load evenly (hash, not range), and (2) every cross-shard query path is identified and has an explicit strategy (denormalization, scatter-gather, or a different storage layer).

### Q3: "Your cache layer goes down. What happens?"

**Answer sketch:** Two scenarios. If the cache simply goes away, requests fall through to the database — which may melt if the cache was masking a 50x read multiplier. Mitigations: cache stampede protection (request coalescing), circuit breaker to return cached-once-or-error, and origin protection via per-key request rate limiting. If the cache returns wrong data (split brain, stale connection), you can serve incorrect data silently — which is worse. Mitigations: short TTLs, versioned keys per write, and treating cache state as advisory, never authoritative.

### Q4: "Walk me through what changes if traffic 10x overnight."

**Answer sketch:** First, the database is the bottleneck. Reads can be saved by adding replicas and a larger cache. Writes need sharding or a higher-throughput engine. Second, the load balancer becomes a single point — add Anycast or a second tier. Third, the CDN carries the weight of static content; static-cache hit rate should already be above 95%. Fourth, message queues need partitions and consumer pods that autoscale. Fifth, observability: at 10x, dashboards that worked at 1x become useless because their resolution is wrong. Add high-cardinality tracing.

### Q5: "You need to go global next quarter. What changes in the architecture?"

**Answer sketch:** Three big shifts. (1) Geo-routing — anycast or geoDNS to put the user on the nearest region. (2) Data locality — accept that one global strongly consistent database is unrealistic; either accept eventual consistency or use a globally consistent engine like Spanner/Cockroach. (3) Edge concerns — push auth, rate limiting, and personalization to the edge so cross-region round trips happen only when strictly necessary. The hidden fourth: compliance — data residency laws may force you to keep user data in the region where it was created.

### Q6: "Why is consistent hashing useful when adding a database shard?"

**Answer sketch:** With naive `hash(key) mod N`, adding a new shard requires remapping nearly every key — a full re-shard. With consistent hashing, keys are mapped onto a ring of size 2^32; each shard owns a contiguous range of that ring. Adding a new shard splits one existing range in two, so only `1/N` of keys move. This makes growth online and bounded instead of an outage-length migration.

---

## Key Terms / Glossary

| Term | What people say | What it actually means |
|---|---|---|
| Stateless web tier | "The web server has no state." | The web tier process holds no per-client state between requests; all session, profile, and counters live in a shared tier (DB, Redis, S3). This is what makes autoscaling and graceful failover possible. |
| Vertical scaling | "Bigger box." | Adding CPU, RAM, or disk to one machine. Cheap and fast up to a hard ceiling (~1-2 TB RAM, ~128 cores on commodity hardware). Single point of failure. |
| Horizontal scaling | "More boxes." | Distributing load across many machines. No ceiling but introduces distributed-systems problems: consistency, leader election, fan-out. |
| Sharding | "Splitting the database." | Partitioning a single logical dataset across multiple physical databases, each holding a subset of rows, with the same schema. Sometimes called "partitioning"; pick one term and stick to it. |
| Replication | "Copies of the data." | Multiple copies of the same data on different machines. Asynchronous replication trades durability for write latency; synchronous trades write latency for durability. |
| CDN | "Edge cache." | A globally distributed cache that serves static content close to the user. Wrong tool for personalized or strongly consistent content. |
| Anycast | "One IP, many places." | A single IP address advertised from many physical locations; BGP routes each user to the topologically nearest healthy location. The architectural foundation of Cloudflare, AWS Global Accelerator, and many DDoS-mitigation networks. |
| Cache stampede | "Thundering herd." | Many concurrent requests for the same cache key after it expires, all hitting the origin simultaneously. Mitigated by single-flight locks, jittered TTLs, and request coalescing. |
| Eventual consistency | "It's slow but correct." | In a distributed system, all replicas will converge to the same value given enough time without new writes. Trade-off: low write latency and high availability at the cost of read-your-writes violations. |
| Hot key | "Popular thing." | A specific cache key or shard that receives a disproportionate share of traffic. Causes uneven load even when the average looks fine. Often requires explicit sharding of the hot key (the "celebrity problem"). |
| Idempotency | "Same call twice = same effect." | An operation that can be applied multiple times without changing the result beyond the first application. Critical for at-least-once delivery systems to avoid duplicate side effects. |

---

## Summary: Scaling Principles

Key techniques supporting millions of users:

- Maintain stateless web tier architecture
- Implement redundancy at every system layer
- Maximize data caching strategies
- Support multiple geographic data centers
- Host static assets on CDN infrastructure
- Scale databases through sharding
- Decompose tiers into individual services
- Establish comprehensive system monitoring with automation

---

## Reference Materials

The chapter cites authoritative sources covering HTTP protocols, database technologies, replication strategies, caching approaches, Facebook's Memcache implementation, single points of failure, CloudFront capabilities, multi-region resilience patterns, AWS infrastructure, Stack Overflow's architecture, and NoSQL use cases.