# Top 20 System Design Concepts You Should Know

> Twenty terms that come up in every system design interview and every architecture review — defined once, properly, with the trade-offs each one implies.

**Type:** Learn
**Prerequisites:** None
**Time:** ~30 minutes

---

## The Problem

System design has its own vocabulary. The same word ("consistency," "availability," "sharding") means different things in different contexts. Teams lose hours arguing about the wrong definitions. Interviews hinge on whether you know the standard terms. Architecture reviews stall because the participants are using different words for the same concepts.

This lesson is a glossary of the twenty concepts that come up constantly — load balancing, caching, sharding, replication, CAP, consistent hashing, message queues, rate limiting, and more. For each, you get the precise definition, the problem it solves, the trade-offs, and the moment to reach for it. By the end, you should be able to read any system design article and recognize every term.

---

## The Concept

### The twenty concepts, grouped

The concepts fall into five clusters:

```
   1. Traffic & Delivery       →  Load Balancing, CDN, API Gateway, Rate Limiting, WebSockets
   2. Data & Storage           →  Caching, Database Indexing, Database Sharding, Replication,
                                  Data Partitioning
   3. Distributed Consistency  →  CAP Theorem, Eventual Consistency, Consistent Hashing
   4. Architecture             →  Microservices, Message Queues, Service Discovery, Scalability,
                                  Fault Tolerance
   5. Operations & Security    →  Monitoring, Authentication & Authorization
```

We will walk through each cluster.

---

### Cluster 1: Traffic and Delivery

**1. Load Balancing**

*Definition:* distributes incoming traffic across multiple servers to improve reliability, availability, and throughput.

*Problem it solves:* a single server can only handle so much traffic. Beyond that limit, requests queue and latency spikes. A single server is also a single point of failure.

*How it works:* a load balancer (hardware or software) sits in front of a pool of servers and routes each request to one of them. Common algorithms: round-robin, least-connections, weighted, IP-hash.

*Trade-offs:* load balancers add a hop (some latency); they are a critical piece of infrastructure that needs HA itself; algorithms differ in how evenly they distribute load.

---

**2. Caching**

*Definition:* stores frequently accessed data in a fast, in-memory layer to avoid recomputing or hitting a slower source.

*Problem it solves:* repeated queries for the same data put unnecessary load on the database; some computations are expensive and can be reused.

*How it works:* application code checks the cache before the database; on a miss, the database is queried and the cache is populated. TTLs and eviction policies (LRU, LFU) keep the cache fresh and bounded.

*Trade-offs:* cached data may be stale; cache invalidation is famously hard; cache stampede (many misses at once) can overload the source.

---

**3. CDN (Content Delivery Network)**

*Definition:* a geographically distributed network of servers that cache and serve content close to users.

*Problem it solves:* a single data center has high latency for users far away. Static assets (images, CSS, JavaScript) are identical for all users — perfect for caching at the edge.

*How it works:* content is cached at edge servers around the world; requests are routed to the nearest edge; on a cache miss, the edge pulls from the origin and caches.

*Trade-offs:* costs money; dynamic content is harder; cache invalidation across edges is non-trivial.

---

**4. API Gateway**

*Definition:* a centralized entry point for routing, authenticating, and managing API requests across microservices.

*Problem it solves:* without a gateway, every client must know the URLs of every service, handle auth separately, retry on its own. The gateway centralizes these concerns.

*How it works:* requests hit the gateway, which authenticates, rate-limits, routes to the appropriate backend service, possibly transforms the request, and returns the response.

*Trade-offs:* the gateway is a critical piece of infrastructure; performance bottleneck; coupling if not designed carefully.

---

**5. Rate Limiting**

*Definition:* controls the rate at which requests can be made by a client to protect the system from overload and abuse.

*Problem it solves:* without limits, a single client can overwhelm the system (intentionally or due to a bug); fair usage requires controlling resource allocation.

*How it works:* count requests per client (by IP, user ID, API key) over a time window; reject requests that exceed the limit. Algorithms: fixed window, sliding window, token bucket, leaky bucket.

*Trade-offs:* legitimate users may be limited; counters are distributed-system problems; the algorithm choice affects smoothness vs. burstiness.

---

**6. WebSockets**

*Definition:* a protocol that provides bidirectional, full-duplex communication over a single TCP connection.

*Problem it solves:* HTTP is request/response; some applications (chat, live updates, multiplayer games) need server-pushed updates without polling.

*How it works:* HTTP upgrade handshake establishes a long-lived TCP connection; both client and server can send messages at any time.

*Trade-offs:* more complex than HTTP to scale (long-lived connections); harder to load balance; many proxies don't handle them well by default.

---

### Cluster 2: Data and Storage

**7. Database Indexing**

*Definition:* a data structure (usually a B-Tree) that lets the database find rows matching a condition without scanning the entire table.

*Problem it solves:* sequential scans of large tables are O(n); indexes make equality and range queries O(log n) or O(1).

*How it works:* an index is a separate data structure keyed by the indexed column(s); the database maintains it automatically on writes.

*Trade-offs:* indexes speed reads, slow writes, and use disk; over-indexing is a real cost; wrong column order in composite indexes wastes the optimization.

---

**8. Database Sharding**

*Definition:* splitting a database into smaller pieces (shards), each holding a subset of the data, typically across multiple machines.

*Problem it solves:* a single database has limits on storage and throughput; sharding spreads load.

*How it works:* data is partitioned by a shard key (e.g., user_id, region); each shard holds a subset; the application or a routing layer directs queries to the correct shard.

*Trade-offs:* cross-shard queries are expensive; rebalancing is hard; joins across shards are not natural; most operational complexity of distributed systems.

---

**9. Replication**

*Definition:* copying data across multiple database instances for availability, fault tolerance, and read scaling.

*Problem it solves:* a single database is a single point of failure; reads may exceed the primary's capacity.

*How it works:* a primary handles writes; replicas receive the same writes (synchronously or asynchronously); reads can be served from replicas.

*Trade-offs:* synchronous replication adds latency; asynchronous replication has lag; replicas may diverge (read-your-writes is not guaranteed); failover is non-trivial.

---

**10. Data Partitioning**

*Definition:* dividing data into smaller chunks for performance or scalability. Includes sharding (across machines) and partitioning (within one database).

*Problem it solves:* a single large table or database is hard to query, hard to back up, and hard to scale.

*How it works:* partitions can be by range, hash, or list. Within one database, partitioning splits a table physically while keeping it logically one. Across databases, partitioning (sharding) splits the data store.

*Trade-offs:* cross-partition queries are slow; partition strategy affects performance unevenly; managing partitions adds operational overhead.

---

### Cluster 3: Distributed Consistency

**11. CAP Theorem**

*Definition:* in a distributed system, you can have at most two of: **C**onsistency (every node sees the same data at the same time), **A**vailability (every request receives a response), **P**artition tolerance (the system continues to operate despite network partitions).

*Problem it solves:* the impossibility result says you cannot have all three. The theorem forces a deliberate choice.

*How it works:* during a network partition, you must choose to either (1) reject writes to maintain consistency (CP), or (2) accept writes on both sides and reconcile later (AP).

*Trade-offs:* there is no "right" answer; the choice depends on the use case (banking often picks CP; social feeds often pick AP).

---

**12. Eventual Consistency**

*Definition:* a consistency model where, in the absence of new updates, all replicas of a piece of data will converge to the same value.

*Problem it solves:* strong consistency across distributed systems is expensive (latency, availability cost). Eventual consistency trades strong guarantees for performance and availability.

*How it works:* writes are accepted on the local node; replication happens asynchronously; replicas converge over time.

*Trade-offs:* users may read stale data; the application must be designed for it (e.g., "your post was published" without a confirmation that everyone sees it).

---

**13. Consistent Hashing**

*Definition:* a hashing scheme that minimizes the number of keys that must be remapped when the number of slots (servers, partitions) changes.

*Problem it solves:* in a simple hash mod N scheme, adding or removing a server remaps nearly every key. Consistent hashing only remaps keys on the affected slice.

*How it works:* servers and keys are hashed onto a ring; a key is assigned to the next server clockwise on the ring. Adding a server only takes over the keys in its new slice.

*Trade-offs:* more complex than simple hashing; virtual nodes (replicas per server) are used to balance load; used in DynamoDB, Cassandra, distributed caches.

---

### Cluster 4: Architecture

**14. Microservices**

*Definition:* an architectural style that structures an application as a suite of small, independent services, each owning its data and deployable independently.

*Problem it solves:* a monolithic application scales as a unit and requires coordinated deployments; microservices enable independent scaling, deployment, and team autonomy.

*How it works:* services communicate over the network (REST, gRPC, async messaging); each owns its data; deployment is per-service.

*Trade-offs:* distributed-system complexity; network failures; eventual consistency; operational overhead; not appropriate for small systems or small teams.

---

**15. Message Queues**

*Definition:* an asynchronous communication mechanism where producers send messages to a queue and consumers process them, decoupling sender and receiver in time.

*Problem it solves:* synchronous calls create tight coupling; if a downstream service is slow or down, the upstream is too. Message queues buffer and decouple.

*How it works:* producers publish messages; a broker (RabbitMQ, Kafka, SQS) stores them; consumers subscribe and process at their own pace.

*Trade-offs:* eventual consistency; debugging distributed flows is harder; ordering guarantees vary by queue.

---

**16. Service Discovery**

*Definition:* the mechanism by which services find each other in a distributed system.

*Problem it solves:* in a dynamic environment with many services coming and going, hard-coding URLs does not work; clients need to discover endpoints at runtime.

*How it works:* services register themselves with a registry (Consul, etcd, Kubernetes DNS); clients query the registry to find an available instance.

*Trade-offs:* the registry becomes a critical piece of infrastructure; split-brain scenarios; health checks must be accurate.

---

**17. Scalability**

*Definition:* the system's ability to handle increased load by adding resources.

*Problem it solves:* demand grows; the system must grow with it.

*How it works:* two main strategies. **Vertical scaling** (bigger machines) is simpler but has limits. **Horizontal scaling** (more machines) is the standard approach for distributed systems but requires stateless services and load balancing.

*Trade-offs:* horizontal scaling requires stateless services; some workloads (heavy writes to a single database) are hard to scale horizontally; cost grows with scale.

---

**18. Fault Tolerance**

*Definition:* the system's ability to continue operating despite hardware or software failures of individual components.

*Problem it solves:* everything fails eventually — disks, servers, network links, even entire data centers. The system must keep working.

*How it works:* redundancy (multiple instances of each component), graceful degradation (reduce functionality rather than failing completely), automated failover (replace failed components automatically).

*Trade-offs:* cost (every component must be duplicated); complexity; eventual consistency when failures cause split-brain.

---

### Cluster 5: Operations and Security

**19. Monitoring**

*Definition:* the continuous collection and analysis of metrics, logs, and traces to understand system health and diagnose problems.

*Problem it solves:* you cannot fix what you cannot see. Distributed systems fail in subtle ways; without monitoring, you are guessing.

*How it works:* three pillars: **metrics** (Prometheus, Datadog) for aggregates (CPU, latency, error rate); **logs** (ELK, Loki) for individual events; **traces** (Jaeger, Zipkin) for request flows across services.

*Trade-offs:* storage and tooling cost; high-cardinality data can blow up metrics systems; choosing the right metrics matters more than the storage.

---

**20. Authentication and Authorization**

*Definition:* **authentication** is verifying who a user is; **authorization** is verifying what they are allowed to do.

*Problem it solves:* without auth, anyone can do anything; with bad auth, attackers impersonate users or escalate privileges.

*How it works:* authentication is typically via password, token (JWT, OAuth), or credential (mTLS, API key). Authorization is typically via roles, scopes, or attribute-based rules.

*Trade-offs:* session management complexity; token revocation; balancing security with user experience; OAuth has many gotchas.

---

## Build It / In Depth

### How the twenty concepts compose in a real system

```
   User request
       │
       ▼
   [CDN] serves cached static assets         ← Concept 3
       │
       ▼
   [API Gateway] authenticates, rate-limits   ← Concepts 4, 5, 20
       │
       ▼
   [Load Balancer] routes to service instance ← Concept 1
       │
       ▼
   [Microservice A] handles business logic   ← Concept 14
       │
       ├──► [Cache] checks in-memory first   ← Concept 2
       │
       ├──► [Database] with indexes          ← Concept 7
       │
       └──► [Message Queue] publishes event  ← Concept 15
                   │
                   ▼
              [Microservice B] consumes       ← Concept 14
                   │
                   ▼
              [Sharded DB] for scale           ← Concepts 8, 10
                   │
                   ▼
              [Replicated] for HA              ← Concept 9
```

A real system uses ten or more of these concepts together. Knowing each one lets you reason about the system as a composition.

---

### When to reach for each concept

| When you face… | Reach for… |
|---|---|
| Traffic exceeding single-server capacity | Load Balancing, Scalability |
| Repeated queries for the same data | Caching |
| Users far from your data center | CDN |
| Multiple microservices with shared concerns | API Gateway |
| Single client overwhelming the system | Rate Limiting |
| Need for real-time updates to clients | WebSockets |
| Slow database queries | Database Indexing |
| Database exceeding single-node capacity | Sharding, Partitioning |
| Single database as a point of failure | Replication |
| Distributed system with network failures | CAP, Eventual Consistency |
| Adding/removing servers without remapping | Consistent Hashing |
| Tight coupling between services | Microservices, Message Queues |
| Services coming and going dynamically | Service Discovery |
| Hardware failures | Fault Tolerance |
| Cannot diagnose production issues | Monitoring |
| User identity and access control | Authentication & Authorization |

---

## Common Pitfalls

- **Knowing the term without knowing when to use it.** "I know what consistent hashing is" without understanding when simple hashing is fine is useless.

- **Confusing similar concepts.** Caching vs. replication. Sharding vs. partitioning. Authentication vs. authorization. Knowing the differences matters.

- **Cargo-culting without measurement.** Adding a CDN because someone said "we need a CDN" without measuring latency improvement wastes money.

- **Premature complexity.** Microservices, sharding, message queues are not defaults. They solve specific problems; reach for them when the problem appears.

- **Ignoring CAP.** Every distributed system makes the choice, often implicitly. Knowing you made it — and why — is essential.

- **Mixing up durability with availability.** Durability is about data not being lost. Availability is about the system responding. Both matter, for different reasons.

- **Underestimating monitoring cost.** Without observability, you cannot debug. With it, you can debug anything. Pay the cost upfront.

---

## Exercises

1. **Easy** — Pick any five of the twenty concepts. For each, write one sentence defining it and one real-world system or product that uses it.

2. **Medium** — Pick a system you have built or used (e.g., a chat app, an e-commerce site, a video streaming service). Identify which ten of the twenty concepts it uses. For each, explain how.

3. **Hard** — You are designing a system from scratch for a new social media platform that will serve 10 million users within the first year. Pick the ten most important concepts from the twenty for this system. Justify each choice and explain how it solves a specific scaling, reliability, or performance challenge.

---

## Key Terms

The full glossary is in the lesson body. The five most-confused pairs:

| Confused pair | Difference |
|---|---|
| Authentication vs Authorization | Who you are vs what you can do |
| Caching vs Replication | Speed up reads (cache) vs fault tolerance + read scaling (replica) |
| Sharding vs Partitioning | Across machines vs within one database |
| Scalability vs Performance | Handle more load vs handle each request faster |
| Durability vs Availability | Data is not lost vs system responds |

---

## Further Reading

- **"Designing Data-Intensive Applications"** — Martin Kleppmann's book; the canonical reference for distributed systems concepts: https://dataintensive.net/
- **"System Design Interview"** — Alex Xu's books (Vol 1 & 2); covers most of these concepts. 
- **AWS Architecture Center** — practical whitepapers on each concept: https://aws.amazon.com/architecture/
- **The Twelve-Factor App** — methodology that underlies most modern scalable systems: https://12factor.net/
- **Martin Fowler's website** — deep articles on microservices, event sourcing, and architectural patterns: https://martinfowler.com/