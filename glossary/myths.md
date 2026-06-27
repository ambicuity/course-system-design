# System Design Myths

### Myth: Microservices are always better than monoliths
**Reality:** Microservices trade in-process simplicity for network calls, distributed transactions, eventual consistency, and a fleet of deployment pipelines. For most teams a well-structured ("modular") monolith ships faster, debugs easier, and scales further than you'd think. Microservices solve an *organizational* scaling problem — letting many teams deploy independently — not a performance one. Reach for them when team coordination, not code, is your bottleneck. Starting with microservices on a small team usually buys you a distributed monolith: all the complexity, none of the independence.

### Myth: NoSQL is faster than SQL
**Reality:** "Faster" depends entirely on the access pattern. NoSQL stores win when their data model matches your queries (key lookups, denormalized documents) and when you can drop the guarantees relational databases enforce. A modern Postgres with proper indexes outperforms a misused NoSQL store, and many NoSQL "wins" come from giving up joins, transactions, and consistency — not from inherent speed. Choose a data store by its consistency model and access patterns, not by the SQL/NoSQL label.

### Myth: Adding more servers always scales the system
**Reality:** Horizontal scaling only works if the workload can be partitioned and the bottleneck isn't shared. Add servers behind a single database and you just move the queue to the database. Amdahl's Law is unforgiving: the serial fraction of your work caps your speedup no matter how many machines you add, and coordination overhead can make more nodes *slower*. Find the actual bottleneck before you provision; often it's one lock, one table, or one hot partition.

### Myth: Caching solves everything
**Reality:** A cache is a bet on locality that introduces a second source of truth you must keep honest. It does nothing for write-heavy workloads, it adds stale-data bugs, and a cold or stampeding cache can take down the very database it was meant to protect. Caching hides a performance problem; it doesn't fix the underlying query, schema, or access pattern. Add it deliberately, with a clear invalidation strategy, not as a reflex.

### Myth: The CAP theorem lets you freely pick 2 of 3
**Reality:** Partition tolerance isn't a choice on a real network — partitions *will* happen, so you must tolerate them. CAP only forces a decision *during* a partition: stay consistent (reject some requests) or stay available (serve possibly-stale data). When there's no partition you can have both consistency and availability. The honest framing is CP-vs-AP under partition, and even that is a spectrum, not a binary — see PACELC for the latency tradeoff CAP ignores.

### Myth: You need Kafka
**Reality:** Kafka is a distributed, partitioned, durable commit log built for genuinely high-throughput streaming and replay — and it brings operational weight: brokers, partitions, consumer-group rebalancing, and ZooKeeper/KRaft to run. Most apps that "need Kafka" actually need a job queue (a database table, SQS, Redis, RabbitMQ) and would be better served by one. Adopt Kafka when you have real streaming volume, multiple independent consumers, or replay requirements — not because it's on every architecture diagram.

### Myth: Sharding early is smart future-proofing
**Reality:** Sharding is one of the most expensive, hardest-to-reverse decisions you can make. It breaks joins, complicates transactions, scatters queries, and re-sharding a live system is genuinely painful. A single well-tuned database with read replicas handles far more load than people assume — often millions of users. Shard when you've exhausted vertical scaling, indexing, and caching and have measured proof you must, not preemptively.

### Myth: Eventual consistency means data loss
**Reality:** Eventual consistency guarantees that replicas *converge* to the same value once writes stop — reads may be briefly stale, but committed writes aren't lost. Data loss comes from misconfigured replication, ignoring write acknowledgements, or unsafe failover, not from the consistency model itself. Plenty of correct, durable systems (DNS, shopping carts, social feeds) are eventually consistent by design. Stale-for-a-moment is not the same as gone.

### Myth: A 99.9% SLA means basically always up
**Reality:** 99.9% allows about 8.7 hours of downtime per year — roughly 43 minutes a month. 99.99% is ~52 minutes a year; 99.999% is about 5 minutes. Each extra nine costs exponentially more in redundancy, testing, and operational discipline. And your effective availability is the *product* of every dependency in the request path, so chaining several "three nines" services yields far less than three nines overall. Know what the number actually buys before you promise it.

### Myth: More database indexes always make things faster
**Reality:** Indexes speed up reads but tax every write — each insert, update, and delete must maintain every relevant index — and they consume storage and memory. Too many indexes slow writes, bloat the buffer cache, and can even confuse the query planner into a worse plan. The goal is the *right* indexes for your actual query patterns (composite, covering, partial), not the most indexes. Unused indexes are pure overhead.

### Myth: Exactly-once delivery is achievable everywhere
**Reality:** In a distributed system with failures and retries, end-to-end exactly-once *delivery* is generally impossible; you get at-most-once or at-least-once. What systems actually provide is exactly-once *processing*, achieved by combining at-least-once delivery with idempotent consumers or transactional dedup. Design for duplicates: make your operations idempotent rather than chasing a guarantee the network can't give you.

### Myth: Serverless means you don't manage servers or scaling
**Reality:** Serverless removes server provisioning, but it adds cold starts, execution time and memory limits, concurrency caps, and connection-pool exhaustion against your database. Costs can spike unpredictably under load, debugging is harder, and you trade infra ops for vendor lock-in and a new class of tuning problems. It's a tradeoff with a different operational surface, not the absence of operations.

### Myth: A message queue guarantees ordered processing
**Reality:** Global ordering across a partitioned, multi-consumer queue is expensive and usually not provided. Most systems guarantee ordering only within a partition/key, and the moment you scale to multiple consumers for throughput, messages can be processed out of order or concurrently. If you need ordering, you design for it explicitly — partition by key, single-threaded consumers per key, or sequence numbers — and accept the throughput cost.

### Myth: Optimistic locking is always better than pessimistic locking
**Reality:** Optimistic concurrency (version checks, retry on conflict) shines under low contention, where conflicts are rare and locks would just add overhead. Under high contention it degrades badly: transactions repeatedly collide, retry, and waste work — a livelock of conflict. Pessimistic locking is the better choice for hot rows with frequent contention. The right answer depends on your conflict rate, not on a blanket rule.

### Myth: The cloud is automatically more reliable and cheaper
**Reality:** The cloud gives you primitives for reliability (multi-AZ, managed failover, autoscaling), but you only get reliability if you architect for it — a single-AZ instance with no backups fails just like a server in a closet. And cloud bills routinely surprise teams: egress fees, idle over-provisioned resources, and per-request pricing add up fast. The cloud trades capex for opex and convenience for a complex cost model; it isn't a free reliability or savings button.
