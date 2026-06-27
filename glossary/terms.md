# System Design Glossary

## A

### ACID
- **What people say:** "The properties that make a database reliable."
- **What it actually means:** Atomicity (a transaction fully commits or fully rolls back), Consistency (it moves the database from one valid state to another respecting constraints), Isolation (concurrent transactions don't see each other's partial work), and Durability (committed data survives a crash). It's a contract about transaction behavior, not a vague quality badge — and "Consistency" here means constraint integrity, not the distributed-systems notion.
- **Why it's called that:** Acronym coined by Härder and Reuter in 1983 to describe reliable transaction processing.

### API Gateway
- **What people say:** "A single entry point for all your APIs."
- **What it actually means:** A managed reverse proxy in front of your services that handles cross-cutting concerns once instead of in every service: authentication, rate limiting, request routing, protocol translation, response aggregation, and observability. The risk is letting it absorb business logic and become a distributed monolith's choke point.
- **Why it's called that:** It's the gateway through which API traffic enters your system.

## B

### Backpressure
- **What people say:** "Slowing down when you're overwhelmed."
- **What it actually means:** A mechanism by which a downstream consumer signals upstream producers to slow or stop sending, so a fast producer can't overwhelm a slow consumer and exhaust memory or queues. Without it, buffers grow unbounded and the system fails catastrophically instead of degrading gracefully. Implemented via bounded queues, blocking, or explicit credit/flow-control protocols.
- **Why it's called that:** Pressure pushing back upstream against the flow, like water against a pump.

### BASE
- **What people say:** "The NoSQL opposite of ACID."
- **What it actually means:** Basically Available, Soft state, Eventually consistent — a design philosophy that trades strong consistency for availability and partition tolerance. The system stays available, state may change over time without input as replicas converge, and reads eventually return the latest write. It's a deliberate set of tradeoffs, not "ACID but worse."
- **Why it's called that:** A chemistry pun — BASE is the opposite of ACID.

### B-Tree
- **What people say:** "The data structure databases use for indexes."
- **What it actually means:** A self-balancing, multi-way search tree where nodes hold many keys and have many children, keeping the tree shallow so lookups need few disk reads. It keeps data sorted and supports range scans efficiently. B+ trees (the common variant) store all values in leaves linked together. Optimized for read-heavy, update-in-place storage — the classic counterpart to LSM trees.
- **Why it's called that:** The "B" is debated (balanced, Bayer, broad) — Rudolf Bayer never definitively said.

### Bloom Filter
- **What people say:** "A way to check if something is in a set."
- **What it actually means:** A space-efficient probabilistic data structure that answers set membership with no false negatives but possible false positives. It hashes an element to several bit positions and sets them; a query checks those bits. "Definitely not present" is certain; "probably present" must be verified. Used to skip expensive disk/network lookups, e.g. in LSM-tree databases.
- **Why it's called that:** Invented by Burton Howard Bloom in 1970.

### Blue-Green Deployment
- **What people say:** "Having two environments and switching between them."
- **What it actually means:** A release strategy with two identical production environments — Blue (live) and Green (idle). You deploy the new version to Green, run smoke tests, then flip the router so all traffic goes to Green instantly. Rollback is just flipping back. It minimizes downtime and risk but requires double the infrastructure and careful handling of shared state like databases.
- **Why it's called that:** The two interchangeable environments are conventionally labeled blue and green.

### Bulkhead
- **What people say:** "Isolating parts of your system."
- **What it actually means:** A resilience pattern that partitions resources (thread pools, connection pools, instances) so a failure or overload in one partition can't consume all resources and sink the whole system. If one downstream dependency hangs, only its dedicated pool is exhausted; other features keep working.
- **Why it's called that:** Named after a ship's bulkheads — watertight compartments that keep one breach from flooding the entire hull.

## C

### Cache Invalidation
- **What people say:** "Clearing the cache when data changes."
- **What it actually means:** The hard problem of ensuring cached copies don't serve stale data after the source of truth changes — via TTL expiry, explicit purge on write, write-through/write-behind, or versioned keys. The difficulty is that the source and cache update at different times and places, so there's always a window where they disagree, and getting it exactly right is famously one of computing's two hard problems.
- **Why it's called that:** You're marking cached entries invalid so they're refetched.

### Cache Stampede
- **What people say:** "When the cache gets overloaded."
- **What it actually means:** When a popular cache entry expires and many concurrent requests simultaneously miss, all hammering the backend to recompute the same value at once — often crushing the database. Mitigated with request coalescing (single-flight), probabilistic early expiration, or serving stale-while-revalidate. Closely related to the thundering herd.
- **Why it's called that:** A stampede of requests rushing the backend at the same instant.

### Caching
- **What people say:** "Storing stuff in memory to make things fast."
- **What it actually means:** Keeping a copy of expensive-to-fetch or expensive-to-compute data in a faster, closer tier (memory, CDN, local) so future requests skip the slow path. The engineering is all in the policy: eviction (LRU/LFU), TTLs, consistency with the source, and accepting that a cache is a bet on locality that introduces a second source of truth you must keep honest.
- **Why it's called that:** From French "cacher," to hide — a hidden fast store between you and the slow source.

### Canary Release
- **What people say:** "Rolling out to a few users first."
- **What it actually means:** Releasing a new version to a small, controlled slice of traffic (say 1–5%), watching error rates, latency, and business metrics, then progressively widening the rollout if healthy or rolling back if not. It catches problems with real traffic at limited blast radius. Requires good metrics and automated rollback to be more than a vibe check.
- **Why it's called that:** From the "canary in a coal mine" — an early-warning sentinel that detects danger before it spreads.

### CAP Theorem
- **What people say:** "Pick two of Consistency, Availability, Partition tolerance."
- **What it actually means:** During a network partition, a distributed system must choose between Consistency (every read sees the latest write) and Availability (every request gets a non-error response) — you cannot have both. Partition tolerance isn't optional in a real network, so the real choice is CP vs AP *when a partition occurs*. When there's no partition, you can have both. The "pick 2 of 3" framing is misleading.
- **Why it's called that:** Acronym of Consistency, Availability, Partition tolerance, proven by Gilbert and Lynch from Brewer's conjecture.

### CDN
- **What people say:** "Servers around the world that make your site faster."
- **What it actually means:** A Content Delivery Network — a geographically distributed fleet of edge caches that serve content from the location nearest each user, cutting latency and offloading origin servers. Beyond static assets it does TLS termination, request collapsing, edge compute, and DDoS absorption. The trade-off is cache invalidation across hundreds of edge nodes.
- **Why it's called that:** A network whose purpose is delivering content close to users.

### Circuit Breaker
- **What people say:** "Stops calling a service when it's down."
- **What it actually means:** A stateful wrapper around remote calls that trips open after a failure threshold, then immediately fails fast (or returns a fallback) instead of waiting on timeouts and piling up. After a cooldown it goes half-open to test a few requests, closing again if they succeed. It prevents a struggling dependency from cascading failures upstream and gives it room to recover.
- **Why it's called that:** Like an electrical circuit breaker that trips to stop current and protect the circuit.

### Consistent Hashing
- **What people say:** "A hashing trick for distributing data."
- **What it actually means:** A hashing scheme that maps both keys and nodes onto a ring, so adding or removing a node only remaps the keys adjacent to it (roughly K/N keys) instead of rehashing everything. Virtual nodes smooth out the distribution. It's foundational for sharding, distributed caches, and load balancers where the node set changes over time.
- **Why it's called that:** The mapping stays "consistent" — mostly stable — as nodes join and leave.

### CQRS
- **What people say:** "Separating reads and writes."
- **What it actually means:** Command Query Responsibility Segregation — using distinct models (often distinct data stores) for writes (commands) and reads (queries), so each can be optimized and scaled independently. The write side enforces invariants; the read side is denormalized for fast queries, kept in sync asynchronously. Powerful for read-heavy or complex domains, but it adds eventual consistency and operational complexity you shouldn't pay for trivial CRUD.
- **Why it's called that:** It segregates the responsibility of commands from that of queries.

## D

### Data Lake
- **What people say:** "A place to dump all your data."
- **What it actually means:** A central repository that stores raw, structured and unstructured data at scale in its native format (schema-on-read), typically on cheap object storage, for later analytics and ML. Unlike a warehouse (schema-on-write, curated), it defers structure. Without governance, catalogs, and quality controls a data lake degenerates into a "data swamp" nobody can use.
- **Why it's called that:** A large body holding data in its natural state, fed by many streams.

### Denormalization
- **What people say:** "Breaking the rules of database design."
- **What it actually means:** Deliberately duplicating or pre-joining data across tables/documents to avoid expensive joins at read time, trading write complexity and storage for read speed. It's a conscious optimization, not sloppiness — you accept the burden of keeping copies in sync in exchange for faster, simpler reads at scale.
- **Why it's called that:** It undoes normalization, the process of eliminating redundancy.

## E

### Event Sourcing
- **What people say:** "Storing events instead of state."
- **What it actually means:** Persisting every state change as an immutable, append-only sequence of events as the source of truth; current state is derived by replaying them. This gives a full audit log, time-travel, and the ability to build new read models retroactively. The costs are schema evolution of old events, snapshotting for performance, and the mental shift away from updating rows in place.
- **Why it's called that:** State is sourced from a log of events.

### Eventual Consistency
- **What people say:** "The data might be wrong for a while."
- **What it actually means:** A consistency model guaranteeing that if no new writes occur, all replicas will *converge* to the same value given enough time. Reads may return stale data temporarily, but the system doesn't lose writes — it just doesn't promise everyone sees them at the same instant. It buys availability and low latency; it does not mean data corruption or loss.
- **Why it's called that:** Consistency is reached eventually, not immediately.

## F

### Forward Proxy
- **What people say:** "A proxy that hides your IP."
- **What it actually means:** A proxy that sits in front of *clients* and forwards their outbound requests to the internet on their behalf — used for egress control, content filtering, caching, anonymity, or bypassing geo-restrictions. The destination server sees the proxy, not the client. It represents the client; a reverse proxy represents the server.
- **Why it's called that:** It forwards client requests outward to origin servers.

## G

### Gossip Protocol
- **What people say:** "How nodes talk to each other."
- **What it actually means:** A decentralized communication protocol where each node periodically exchanges state with a few randomly chosen peers, so information spreads epidemically through the cluster without any central coordinator. It's robust to node failures and scales well, at the cost of eventual (not instant) propagation. Used for membership, failure detection, and metadata in systems like Cassandra and DynamoDB.
- **Why it's called that:** Information spreads the way gossip does — peer to peer, exponentially.

## H

### Heartbeat
- **What people say:** "A signal that something is alive."
- **What it actually means:** A periodic message a node sends to peers or a coordinator to signal liveness. Missing some threshold of consecutive heartbeats marks the node as failed and triggers failover or rebalancing. The tuning is a tradeoff: aggressive timeouts detect failures fast but cause false positives during transient slowness; lax ones are stable but slow to react.
- **Why it's called that:** Like a pulse — a steady beat proving the node still lives.

### Horizontal Scaling
- **What people say:** "Adding more servers."
- **What it actually means:** Scaling out by adding more machines/instances and distributing load across them, rather than enlarging one machine. It offers near-linear, fault-tolerant capacity growth — but only if the workload can be partitioned and the app is stateless or its state is externalized. The hard parts are coordination, data partitioning, and consistency, not buying more boxes.
- **Why it's called that:** You grow the system sideways — more nodes — rather than upward.

### Hot Partition
- **What people say:** "When one server gets too much traffic."
- **What it actually means:** A single shard/partition that receives a disproportionate share of reads or writes because of a skewed key distribution (e.g. a celebrity user, a monotonically increasing timestamp key), becoming a bottleneck while others sit idle. It defeats the purpose of sharding. Fixed by better partition keys, key salting, or splitting the hot key.
- **Why it's called that:** That partition runs "hot" while the rest stay cool.

## I

### Idempotency
- **What people say:** "Running it twice does the same thing."
- **What it actually means:** A property where performing an operation multiple times has the same effect as performing it once. Critical in distributed systems where retries, network timeouts, and at-least-once delivery mean the same request may arrive repeatedly. Achieved with idempotency keys, conditional writes, or naturally idempotent operations (set, not increment), so retries are safe and don't double-charge or double-create.
- **Why it's called that:** From mathematics — an idempotent function f satisfies f(f(x)) = f(x).

### Index
- **What people say:** "Makes database queries faster."
- **What it actually means:** An auxiliary data structure (usually a B-tree or hash) that maps column values to row locations so the database can find rows without scanning the whole table. It accelerates reads and ordering at the cost of extra storage and slower writes (every insert/update must maintain the index). Choosing which columns to index, and composite/covering indexes, is core query optimization.
- **Why it's called that:** Like a book's index — a lookup that points you to where the data lives.

## L

### Latency
- **What people say:** "How fast the system is."
- **What it actually means:** The time elapsed for a single operation to complete — the delay between request and response. It's distinct from throughput (volume per unit time): a system can have high throughput and high latency at once. Latency is best described by a distribution (median, p99), not a single average, because tail behavior dominates user experience.
- **Why it's called that:** From Latin "latens," hidden — the hidden delay before a result appears.

### Leader Election
- **What people say:** "Picking which server is in charge."
- **What it actually means:** A coordination procedure by which a cluster agrees on a single node to act as leader/coordinator for some responsibility (e.g. accepting writes), and reliably elects a new one when it fails. Done correctly it requires consensus (Raft, Paxos) or a coordination service (ZooKeeper/etcd) to avoid split-brain, where two nodes both think they're leader.
- **Why it's called that:** The nodes "elect" a leader among themselves.

### Load Balancer
- **What people say:** "A thing that spreads traffic"
- **What it actually means:** A reverse proxy that distributes incoming requests across a pool of backend servers using an algorithm (round-robin, least-connections, consistent hashing), with health checks to route around dead nodes. It can operate at L4 (TCP/UDP) or L7 (HTTP), and is the front door for both scaling and availability.
- **Why it's called that:** It balances the load — request volume — evenly so no single server becomes a bottleneck.

### Long Polling
- **What people say:** "A hack to fake real-time updates."
- **What it actually means:** A technique where the client makes an HTTP request and the server holds it open until it has data (or a timeout), then responds; the client immediately reconnects. It approximates server push over plain HTTP without WebSockets, at the cost of held connections and reconnect overhead. A pragmatic middle ground between naive polling and full duplex streaming.
- **Why it's called that:** It's polling, but each request is held "long" instead of returning immediately empty.

### LSM Tree
- **What people say:** "What modern databases use to write fast."
- **What it actually means:** Log-Structured Merge tree — a write-optimized storage engine that buffers writes in memory (memtable), flushes them as sorted immutable files (SSTables) to disk, and periodically merges/compacts them in the background. Sequential writes make ingestion fast; reads may check multiple levels (helped by Bloom filters). The trade-off versus B-trees is write amplification from compaction and read amplification. Used by Cassandra, RocksDB, LevelDB.
- **Why it's called that:** It's log-structured (append-only) and merges sorted runs over time.

## M

### MapReduce
- **What people say:** "How big data gets processed."
- **What it actually means:** A programming model for batch processing huge datasets across a cluster: a Map step transforms input into key-value pairs in parallel, a shuffle groups them by key, and a Reduce step aggregates each group. The framework handles distribution, fault tolerance, and retries. Largely superseded by faster engines (Spark) but conceptually foundational to distributed data processing.
- **Why it's called that:** Named after the two functional operations it's built on, map and reduce.

### Message Queue
- **What people say:** "A pipe between services."
- **What it actually means:** A buffer that decouples producers from consumers: producers enqueue messages and move on, consumers process them at their own pace. It absorbs traffic spikes, enables async processing and retries, and lets components fail independently. Key design questions are delivery semantics (at-least-once vs exactly-once), ordering guarantees, and what happens to messages that can't be processed (dead-letter queues).
- **Why it's called that:** It's a queue that holds messages between sender and receiver.

## P

### P99
- **What people say:** "The slowest 1% of requests."
- **What it actually means:** The 99th percentile latency — the value below which 99% of requests complete. It's a tail-latency metric that captures the experience of your unlucky users far better than an average, which hides outliers. At scale, p99 matters because a single user request often fans out to many backend calls, so the slow tail of each compounds into a likely-slow overall response.
- **Why it's called that:** The 99th percentile of the latency distribution.

### PACELC
- **What people say:** "An extension of CAP."
- **What it actually means:** A refinement of CAP: if there's a Partition (P), choose Availability or Consistency (A/C); Else (E), in normal operation, choose Latency or Consistency (L/C). It captures the consistency-vs-latency tradeoff that CAP ignores — even with no partition, stronger consistency costs more coordination and thus latency. Systems are classified e.g. PA/EL (Dynamo) or PC/EC (traditional RDBMS).
- **Why it's called that:** Acronym for Partition→Availability/Consistency, Else→Latency/Consistency, coined by Daniel Abadi.

### Partitioning
- **What people say:** "Splitting up your database."
- **What it actually means:** Dividing a dataset into distinct subsets (partitions) so each can be stored and processed independently — by range, hash, or list of a partition key. It's the general concept; sharding is partitioning across separate machines. Done well it spreads load and shrinks working sets; done poorly it creates hot partitions or cross-partition queries that defeat the point.
- **Why it's called that:** You partition the data into separate parts.

### Paxos
- **What people say:** "A consensus algorithm nobody understands."
- **What it actually means:** A family of protocols for reaching consensus among unreliable distributed nodes, guaranteeing safety (never two conflicting decisions) even with failures, as long as a majority is reachable. It works via proposers, acceptors, and promise/accept phases. Correct but notoriously hard to understand and implement, which is why Raft was created as a more teachable alternative.
- **Why it's called that:** Lamport framed it as the legislative system of the fictional Greek island Paxos.

### Pub/Sub
- **What people say:** "Broadcasting messages to subscribers."
- **What it actually means:** Publish/Subscribe — a messaging pattern where publishers emit messages to topics without knowing who receives them, and subscribers register interest in topics to receive matching messages. It fully decouples senders from receivers in space, time, and count (one message fans out to many consumers). Contrast with a point-to-point queue where each message goes to exactly one consumer.
- **Why it's called that:** Publishers publish; subscribers subscribe.

## Q

### Quorum
- **What people say:** "A majority of nodes agreeing."
- **What it actually means:** The minimum number of nodes that must participate for an operation to be considered successful in a replicated system. With N replicas, if write quorum W + read quorum R > N, reads and writes overlap on at least one node, guaranteeing reads see the latest committed write. Tuning R and W trades consistency against availability and latency. A majority (W = R = N/2 + 1) is the common, but not only, choice.
- **Why it's called that:** From the parliamentary term for the minimum members needed to make a decision valid.

## R

### Raft
- **What people say:** "Paxos but easier."
- **What it actually means:** A consensus algorithm designed for understandability that keeps a replicated log consistent across a cluster. It decomposes the problem into leader election, log replication, and safety, with a single strong leader handling all writes and replicating to followers; a new leader is elected on failure via randomized timeouts and majority votes. Used in etcd, Consul, CockroachDB, and TiKV.
- **Why it's called that:** A loose acronym/metaphor — a raft to escape the "sea of Paxos" (Reliable, Replicated, Redundant, And Fault-Tolerant).

### Rate Limiting
- **What people say:** "Stopping people from spamming your API."
- **What it actually means:** Capping how many requests a client may make in a time window to protect resources, ensure fairness, and resist abuse — enforced with algorithms like token bucket, leaky bucket, fixed/sliding window. It defines a hard policy ("100 req/min per key") and returns 429s when exceeded. Distinct from throttling, which usually means dynamically slowing rather than rejecting.
- **Why it's called that:** It limits the rate of requests.

### Replication
- **What people say:** "Copying data to multiple servers."
- **What it actually means:** Maintaining copies of data on multiple nodes for durability, availability, and read scaling. The hard questions are *how* copies stay in sync: synchronous (consistent but slower, blocks on replicas) vs asynchronous (fast but can lose recent writes on failover), and topology — single-leader, multi-leader, or leaderless. Replication is about redundancy of the same data; sharding splits different data.
- **Why it's called that:** You replicate — make replicas of — the data.

### Reverse Proxy
- **What people say:** "Same as a load balancer."
- **What it actually means:** A server that sits in front of *backend servers* and handles incoming client requests on their behalf — doing TLS termination, caching, compression, routing, and request shaping, while hiding the backend topology. Load balancing is one thing a reverse proxy can do, but not the only one. It represents the server side; a forward proxy represents the client side.
- **Why it's called that:** It proxies in the reverse direction of a forward proxy — toward servers, not clients.

## S

### Saga
- **What people say:** "Transactions across microservices."
- **What it actually means:** A pattern for managing a long-lived business process spanning multiple services without a distributed transaction: a sequence of local transactions, each with a compensating action to undo it if a later step fails. Coordinated via orchestration (a central coordinator) or choreography (services react to events). It gives you eventual atomicity at the business level, but you must design compensations and tolerate intermediate inconsistency.
- **Why it's called that:** From a 1987 paper using "saga" for a long-running sequence of related transactions.

### Service Mesh
- **What people say:** "Networking for microservices."
- **What it actually means:** A dedicated infrastructure layer that handles service-to-service communication — load balancing, retries, mTLS, traffic shifting, and observability — by injecting sidecar proxies next to each service, controlled centrally. It moves these concerns out of application code and into the platform. The cost is real operational complexity and latency, so it earns its keep only past a certain scale.
- **Why it's called that:** The interconnected sidecar proxies form a "mesh" carrying service traffic.

### Sharding
- **What people say:** "Splitting a database across servers."
- **What it actually means:** Horizontal partitioning of data across multiple independent databases/nodes, each holding a subset chosen by a shard key, so capacity and throughput scale beyond a single machine. The shard key choice is everything — it determines balance, hot spots, and whether common queries hit one shard or fan out. Re-sharding a live system is one of the harder operational tasks in the field.
- **Why it's called that:** Each partition is a "shard" — a fragment of the whole dataset.

### Sidecar
- **What people say:** "A helper container next to your app."
- **What it actually means:** A pattern where a separate process/container is deployed alongside the main application in the same unit (e.g. pod), sharing its lifecycle and network, to provide supporting features — proxying, logging, config, secrets — without modifying the app. It keeps cross-cutting concerns language-agnostic and decoupled. The foundation of service meshes.
- **Why it's called that:** Like a motorcycle sidecar — attached to the main vehicle, along for the same ride.

### SLA
- **What people say:** "A promise about uptime."
- **What it actually means:** Service Level Agreement — a formal, often contractual commitment to a customer about service levels (e.g. 99.9% availability) with defined consequences (credits, penalties) if breached. It's the externally-facing legal/business contract, built on top of internal SLOs and measured by SLIs. The agreement, not the measurement.
- **Why it's called that:** It's an agreement about service levels.

### SLI
- **What people say:** "A metric you track."
- **What it actually means:** Service Level Indicator — a precisely defined quantitative measure of a service's behavior, such as the ratio of successful requests, p99 latency, or error rate. It's the actual measurement against which SLOs are set and SLAs are judged. A good SLI reflects the user's experience, not just internal health.
- **Why it's called that:** It indicates the service level you're actually delivering.

### SLO
- **What people say:** "Your uptime target."
- **What it actually means:** Service Level Objective — an internal target for an SLI over a window (e.g. "99.95% of requests succeed over 30 days"). It's stricter than the customer-facing SLA, leaving headroom, and it powers error budgets: the allowed amount of unreliability you can "spend" on shipping fast before you must slow down and stabilize.
- **Why it's called that:** It's the objective you set for your service level.

### Statelessness
- **What people say:** "The server doesn't remember anything."
- **What it actually means:** A design where each request contains all information needed to process it, and the server keeps no client session state between requests (state lives in the request, a token, or an external store). This makes any instance able to handle any request, enabling trivial horizontal scaling, load balancing, and failover. It doesn't mean the *system* is stateless — just that the compute tier is.
- **Why it's called that:** The server holds no per-client state.

### Sticky/Affinity
- **What people say:** "Routing related requests together."
- **What it actually means:** A general routing property where requests sharing some attribute (user, session, key) are consistently directed to the same node — for cache locality, in-memory state, or ordered processing. Session stickiness is one case; consistent-hash affinity in caches and partition affinity in stream processors are others. The benefit is locality; the risk is imbalance and reduced fault tolerance.
- **Why it's called that:** Requests have an "affinity" for, and stick to, a particular node.

### Sticky Session
- **What people say:** "Keeping a user on the same server."
- **What it actually means:** Session affinity — a load-balancer policy that routes all of a given client's requests to the same backend instance, usually so in-memory session state stays valid. It's a pragmatic crutch that undermines even load distribution and breaks gracefully when that instance dies (the session is lost). The cleaner fix is externalizing session state so any instance can serve any request.
- **Why it's called that:** The client "sticks" to one server.

### Strong Consistency
- **What people say:** "Always reading the latest data."
- **What it actually means:** A guarantee that once a write completes, every subsequent read (from any client) returns that write or a later one — the system behaves as if there's a single, up-to-date copy. Linearizability is the strict form. It requires coordination (consensus, quorums, synchronous replication), which costs latency and availability during partitions. The opposite end of the spectrum from eventual consistency.
- **Why it's called that:** It's the strongest consistency guarantee — no stale reads.

## T

### Tail Latency
- **What people say:** "The slow requests."
- **What it actually means:** The high-percentile end (p95/p99/p999) of the latency distribution — the slowest responses that the average conveniently hides. It dominates user experience at scale because a single page often fans out to dozens of backend calls, so the probability that *at least one* hits the slow tail is high. Reducing tail latency (via hedged requests, timeouts, better load balancing) is often more impactful than improving the median.
- **Why it's called that:** It's the long tail of the latency distribution curve.

### Throttling
- **What people say:** "Same as rate limiting."
- **What it actually means:** Dynamically slowing down or shaping a client's request rate — queuing, delaying, or degrading rather than hard-rejecting — often in response to current system load. Rate limiting enforces a fixed quota and rejects over it; throttling is the softer, adaptive cousin that smooths traffic. In practice the terms overlap, but the distinction is reject-vs-slow.
- **Why it's called that:** Like a throttle valve restricting flow to control speed.

### Throughput
- **What people say:** "How much the system can handle."
- **What it actually means:** The rate of work a system completes per unit time — requests/sec, transactions/sec, bytes/sec. It's orthogonal to latency: batching and parallelism can raise throughput while raising per-request latency. Capacity planning is largely about sustained throughput at an acceptable latency percentile, not peak numbers in isolation.
- **Why it's called that:** The amount of work that gets "through" the system over time.

### Thundering Herd
- **What people say:** "Everything hits at once."
- **What it actually means:** When a large number of waiting processes/requests are all released or triggered simultaneously — by a cache expiry, a service coming back online, or a single event waking many blocked clients — and overwhelm a shared resource at the same instant. Mitigated with jitter, backoff, request coalescing, and staggered retries. Cache stampede is a specific instance.
- **Why it's called that:** Like a herd of animals all stampeding toward the same spot at once.

### Two-Phase Commit
- **What people say:** "How distributed transactions work."
- **What it actually means:** 2PC — an atomic commit protocol where a coordinator first asks all participants to *prepare* (phase 1) and, only if all vote yes, tells them to *commit* (phase 2), otherwise abort. It guarantees atomicity across nodes but is a blocking protocol: if the coordinator fails after prepare, participants hold locks indefinitely. This fragility is why sagas and eventual consistency are often preferred at scale.
- **Why it's called that:** It commits in two distinct phases — prepare, then commit.

## V

### Vector Clock
- **What people say:** "Timestamps for distributed systems."
- **What it actually means:** A data structure — a vector of per-node counters — that captures causal ordering of events across nodes without synchronized clocks. By comparing two vectors you can tell whether one event happened-before another or whether they're concurrent (conflicting). Used to detect and resolve conflicting replica updates in systems like Dynamo. It tracks causality, not wall-clock time.
- **Why it's called that:** It's a logical clock represented as a vector of counters.

### Vertical Scaling
- **What people say:** "Buying a bigger server."
- **What it actually means:** Scaling up by adding more resources (CPU, RAM, faster disk) to a single machine. It's simple — no distribution, no consistency headaches — and often the right first move, but it hits hard ceilings (you can't buy an infinitely large box), gets exponentially expensive, and leaves a single point of failure. Eventually you must scale horizontally.
- **Why it's called that:** You grow the machine upward — bigger — rather than adding more of them.

## W

### WebSocket
- **What people say:** "Real-time connection for the browser."
- **What it actually means:** A protocol providing a single, long-lived, full-duplex TCP connection between client and server over an HTTP-upgraded handshake, so both sides can push messages anytime with low overhead. Unlike polling or long polling, there's no per-message HTTP cost. The trade-offs are stateful connections that complicate load balancing and scaling, and the need for your own reconnection and heartbeat logic.
- **Why it's called that:** A socket-like bidirectional channel for the web.

### Write-Ahead Log
- **What people say:** "A log databases keep."
- **What it actually means:** WAL — a durability technique where every change is appended to a sequential on-disk log *before* it's applied to the main data structures. On crash, the database replays the log to recover committed transactions and roll back incomplete ones. Sequential log writes are fast, and the WAL is the basis for durability, crash recovery, and replication streams.
- **Why it's called that:** You write to the log ahead of applying the change.
