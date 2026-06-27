# Design A Key-Value Store

## Chapter Overview

This chapter addresses designing a distributed key-value store supporting `put(key, value)` and `get(key)` operations. The design emphasizes scalability, high availability, and tunable consistency for systems handling large datasets.

---

## Understanding the Problem

### Problem Statement

A key-value store is a non-relational database pairing unique identifiers with associated values. Keys can be plain text (e.g., "last_logged_in_at") or hashed values (e.g., 253DDEC4), while values may be strings, lists, or objects.

### Design Requirements

The system must support:
- **Data size**: Key-value pairs smaller than 10 KB
- **Scale**: Ability to store massive datasets
- **High availability**: Rapid responses despite failures
- **Horizontal scalability**: Support growth through additional servers
- **Automatic scaling**: Dynamic node addition/removal based on traffic
- **Tunable consistency**: Configurable consistency guarantees
- **Low latency**: Minimal response delays

---

## Single Server Key-Value Store

### Architecture

A basic implementation uses an in-memory hash table for fast access. However, this approach faces capacity limitations.

### Optimization Strategies

1. **Data compression**: Reduce memory footprint through encoding techniques
2. **Hybrid storage**: Maintain frequently accessed data in memory; store remainder on disk

**Limitation**: Single servers inevitably reach capacity constraints, necessitating distribution.

---

## Distributed Key-Value Store

### Foundational Concept

A distributed key-value store (also termed a distributed hash table) disperses key-value pairs across multiple servers to overcome single-server limitations.

---

## CAP Theorem

### Definition

CAP theorem states it is impossible for a distributed system to simultaneously provide more than two of these three guarantees: consistency, availability, and partition tolerance.

### Three Properties Explained

**Consistency**: All clients observe identical data simultaneously, regardless of node connection point.

**Availability**: Every client request receives a response, even when certain nodes fail.

**Partition Tolerance**: System operations continue despite communication breaks between nodes.

### Practical Implications

Since network partitions are inevitable in real-world systems, designers must choose between:

**CP Systems** (Consistency + Partition Tolerance): Sacrifice availability. Block write operations during partitions to prevent inconsistency. Example use case: banking systems requiring accurate balance data.

**AP Systems** (Availability + Partition Tolerance): Sacrifice consistency. Accept writes during partitions and reconcile afterward. Example use case: social media feeds tolerating temporary staleness.

**CA Systems**: Theoretically impossible in distributed environments due to inevitable network failures.

### Real-World Scenario

When node n3 fails, a system must choose:
- **CP approach**: Block writes to n1 and n2 to prevent divergence
- **AP approach**: Continue accepting writes; synchronize when connectivity restores

---

## Core System Components

### 1. Data Partition

#### Challenge

Distribute datasets evenly across servers while minimizing data movement during node changes.

#### Solution: Consistent Hashing

Servers are positioned on a hash ring. Keys hash onto the same ring and store on the first server encountered moving clockwise.

**Advantages**:
- **Automatic scaling**: Servers added/removed with minimal redistribution
- **Heterogeneity**: Virtual node allocation proportional to server capacity

#### Example

Eight servers (s0-s7) positioned on a ring. Key0 hashes to a position on the ring, then stores on s1 (first server clockwise).

---

### 2. Data Replication

#### Approach

Data asynchronously replicates across N servers (configurable parameter). After a key maps to a position, traverse clockwise and select the first N unique physical servers.

#### Example (N=3)

Key0 replicates across s1, s2, s3.

#### Geographic Distribution

Replicas placed in distinct data centers connected by high-speed networks to mitigate correlated failures from power outages or natural disasters.

#### Virtual Nodes Consideration

When using virtual nodes, the clockwise walk selects only unique physical servers to avoid concentrating replicas on single machines.

---

### 3. Consistency

#### Quorum Consensus Parameters

- **N** = Number of replicas
- **W** = Write quorum size. Successful writes require acknowledgment from W replicas.
- **R** = Read quorum size. Successful reads require responses from R replicas.

#### Configuration Tradeoffs

| Configuration | Optimization | Tradeoff |
|---|---|---|
| R=1, W=N | Fast reads | Slower writes |
| W=1, R=N | Fast writes | Slower reads |
| W+R > N | Strong consistency (typically N=3, W=R=2) | Slower operations |
| W+R ≤ N | Weak consistency | Faster operations |

**Key principle**: When W + R > N, strong consistency is guaranteed because at least one overlapping node possesses the latest data.

#### Consistency Models

**Strong consistency**: All reads reflect the most recent writes; clients never encounter stale data. Achieved by blocking new operations until replicas achieve agreement (expensive for availability).

**Weak consistency**: Subsequent reads may not reflect recent updates.

**Eventual consistency**: Given sufficient time, all updates propagate and replicas converge. Recommended approach balancing availability and eventual correctness.

---

### 4. Inconsistency Resolution: Versioning

#### Problem

Concurrent writes to different replicas create conflicting values requiring reconciliation.

#### Example Scenario

- Initial state: Both n1 and n2 contain "name: john"
- Concurrent writes: Server 1 writes "johnSanFrancisco" to n1; Server 2 writes "johnNewYork" to n2
- Result: Conflicting versions with no obvious resolution path

#### Solution: Vector Clocks

A vector clock represents a data item as D([S1, v1], [S2, v2], ..., [Sn, vn]):
- S denotes a server identifier
- v represents a version counter

**Update rules**: When data writes to server Si:
- Increment vi if [Si, vi] exists
- Otherwise create new entry [Si, 1]

#### Conflict Detection Logic

**Ancestry** (no conflict): Version X is an ancestor of version Y if all participants in Y's vector clock have counters ≥ corresponding counters in X.

Example: D([s0, 1], [s1, 1]) is an ancestor of D([s0, 1], [s1, 2]).

**Sibling** (conflict exists): Version X conflicts with Y if any participant in Y has a lower counter than the corresponding position in X.

Example: D([s0, 1], [s1, 2]) conflicts with D([s0, 2], [s1, 1]).

#### Concrete Example (5-Step Process)

1. Client writes D1 to Sx → D1([Sx, 1])
2. Update to D2, write through Sx → D2([Sx, 2])
3. Read D2, update to D3, write through Sy → D3([Sx, 2], [Sy, 1])
4. Read D2, update to D4, write through Sz → D4([Sx, 2], [Sz, 1])
5. Detect conflict between D3 and D4; resolve and write through Sx → D5([Sx, 3], [Sy, 1], [Sz, 1])

#### Limitations

1. **Client complexity**: Application logic must implement conflict resolution
2. **Vector clock growth**: [Server, version] pairs expand over time. Mitigation: Set length thresholds and remove oldest entries (potential reconciliation inefficiency, though Amazon reports no production issues)

---

### 5. Handling Failures

#### Failure Detection

**Problem**: Single failure reports are insufficient; multiple independent confirmation sources required.

**All-to-all multicasting**: Inefficient approach sending heartbeats from every node to every other node (O(n²) complexity).

**Gossip Protocol** (Preferred solution):

Each node maintains a membership list containing member IDs and heartbeat counters. Process:
- Increment heartbeat counter periodically
- Send heartbeats to random nodes, propagated further
- Update membership lists upon receiving heartbeats
- Mark members offline if heartbeat hasn't increased beyond a predefined threshold

**Advantage**: Decentralized detection requiring less communication overhead than all-to-all multicasting.

#### Temporary Failure Handling

**Sloppy Quorum**: Instead of enforcing strict quorum requirements, select the first W healthy servers for writes and first R healthy servers for reads on the hash ring, ignoring offline servers.

**Hinted Handoff**: When a server becomes unavailable, another node processes requests temporarily. Upon recovery, the temporary holder returns data to the original server to restore consistency.

Example: If s2 is offline, s3 temporarily handles its requests. When s2 recovers, s3 transfers data back.

#### Permanent Failure Handling

**Anti-entropy Protocol**: Compares replica data and updates versions to the newest. Uses Merkle trees to detect inconsistencies and minimize transfer volume.

**Merkle Tree Definition**: A hash tree or Merkle tree is a tree in which every non-leaf node is labeled with the hash of the labels or values (in the case of leaves) of its child nodes.

**Construction Steps**:

1. **Step 1**: Divide key space into buckets (root level nodes maintain limited tree depth).
2. **Step 2**: Hash each key in a bucket using a uniform hashing method.
3. **Step 3**: Create a single hash node per bucket.
4. **Step 4**: Build upward to root by calculating hashes of children.

**Comparison Process**: Compare root hashes. If matching, servers have identical data. If divergent, recursively compare child hashes to identify unsynchronized buckets.

**Efficiency**: Data requiring synchronization scales with differences between replicas, not total data volume. Example: One million buckets per billion keys means approximately 1000 keys per bucket.

#### Data Center Outage Handling

**Strategy**: Replicate data across geographically distinct data centers. Complete data center failure doesn't prevent access through remaining locations.

---

## System Architecture Diagram

### High-Level Architecture

**Components**:
- Client communicates via `get(key)` and `put(key, value)` APIs
- Coordinator acts as a proxy between client and key-value store
- Nodes distributed on ring via consistent hashing
- Completely decentralized; no single point of failure
- Every node possesses identical responsibilities

### Per-Node Responsibilities

Each node implements:
- Client API handling
- Failure detection
- Conflict resolution
- Failure repair mechanisms
- Data replication coordination
- Storage engine management

---

## Write Path

1. **Step 1**: Write request persists to commit log file on disk (durability guarantee)
2. **Step 2**: Data saves to in-memory cache (quick access)
3. **Step 3**: When the memory cache reaches capacity or a predefined threshold, data flushes to an SSTable (Sorted-String Table) on disk

**Purpose**: Write-ahead logging ensures durability even if the server crashes after memory storage but before disk persistence.

---

## Read Path

### Cache Hit Scenario

Memory cache contains data → return immediately to client.

### Cache Miss Scenario

1. **Step 1**: Check memory cache; if absent, proceed
2. **Step 2**: Query disk layer
3. **Step 3**: Consult Bloom filter to identify candidate SSTables (probabilistic data structure indicating key presence)
4. **Step 4**: Access identified SSTables for data retrieval
5. **Step 5**: Return result to client

**Bloom Filter Purpose**: Efficiently determines whether a key might exist before expensive SSTable access, eliminating unnecessary disk I/O.

---

## Design Tradeoffs Summary Table

| Goal/Problem | Technique |
|---|---|
| Store massive datasets | Consistent hashing distributes load across servers |
| Highly available reads | Data replication across nodes |
| Multi-datacenter resilience | Cross-datacenter replication |
| Highly available writes | Vector clocks enable versioning and conflict resolution |
| Dataset partitioning | Consistent hashing |
| Incremental scalability | Consistent hashing |
| Server heterogeneity support | Virtual node allocation proportional to capacity |
| Tunable consistency | Quorum consensus via W, R, N parameters |
| Temporary failure tolerance | Sloppy quorum and hinted handoff |
| Permanent failure tolerance | Merkle tree anti-entropy protocol |
| Data center failure tolerance | Cross-datacenter replication |

---

## Key Architectural Decisions

1. **Choose CAP guarantees**: Balance between consistency and availability based on use case requirements
2. **Configure quorum parameters**: Adjust W, R, N based on latency vs. consistency needs
3. **Select consistency model**: Eventual consistency recommended for high-availability systems
4. **Implement vector clocks**: Enable conflict detection and client-side resolution
5. **Deploy decentralized failure detection**: Use gossip protocol for scalability
6. **Use hybrid failure strategies**: Combine hinted handoff (temporary) with Merkle trees (permanent)
7. **Replicate geographically**: Distribute across data centers for resilience

---

## References

- Amazon DynamoDB documentation
- Memcached cache platform
- Redis key-value store
- Dynamo: Amazon's Highly Available Key-value Store (research paper)
- Apache Cassandra distributed database
- Google Bigtable distributed storage system
- Merkle tree theoretical foundations
- Cassandra architecture documentation
- SSTable and log-structured storage (LevelDB)
- Bloom filter algorithms
