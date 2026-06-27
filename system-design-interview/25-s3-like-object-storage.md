# S3-like Object Storage

## Background & Terminology

Storage systems fall into three broad categories:
- **Block storage** — raw volumes/disks (e.g., HDD, SSD, AWS EBS, iSCSI/Fibre Channel). The OS sees raw blocks and lays a filesystem over them. Lowest-level, highest performance.
- **File storage** — a hierarchical file/folder abstraction over block storage with a filesystem (e.g., NFS, SMB). Easy to use; shared file semantics.
- **Object storage** — flat namespace, stores objects in **buckets**, accessed via **RESTful API**; trades lower performance/no in-place edits for massive scalability and durability (e.g., AWS S3). Designed for **infrequently updated**, write-once-read-many data.

**Key terms:**
- **Bucket** — a logical container for objects; name is globally unique.
- **Object** — the data (payload) plus metadata; identified by a key.
- **Versioning** — keep multiple versions of an object in a bucket.
- **URI / Object ID** — addresses a bucket/object via the API.
- **SLA** — service-level agreement (durability, availability targets, e.g., 11 nines durability).

**Object storage vs. file/block — distinguishing properties:**
- Immutable objects (no in-place partial updates; replace the whole object)
- Flat structure (no real directories — "folders" are key prefixes)
- Lower price, very high durability/scalability
- Best for large, rarely-modified data (images, video, backups, logs)

## Step 1: Understand the Problem and Establish Design Scope

### Functional Requirements
- **Bucket creation**
- **Object upload and download**
- **Object versioning**
- **Listing objects** in a bucket (similar to `aws s3 ls`)

### Non-Functional Requirements
- **100 PB** of data scale
- **Six-nines (99.9999%) data durability**
- **Four-nines (99.99%) service availability**
- **Storage efficiency** — keep cost low while maintaining high reliability

### Design Considerations / Estimation
- Use **replication** vs **erasure coding** to balance durability and storage cost (see deep dive).
- Disk capacity and IOPS drive node sizing; metadata is small but high in count.

---

## Step 2: High-Level Design

### Object Storage Properties Recap
- Data is **immutable**; uploads create new objects/versions.
- A flat key namespace within a bucket.
- Frequent reads, infrequent writes; strong durability requirement.

### High-Level Architecture Components
- **Load balancer** — distributes RESTful requests across API servers.
- **API service (stateless)** — orchestrates calls to the IAM (identity/auth), metadata service, and data store. This is the "brain" coordinating each request; it is stateless so it scales horizontally.
- **Identity and Access Management (IAM)** — central place for **authentication, authorization, and access control** (who can do what to which bucket/object).
- **Data store** — stores and retrieves the **actual object data**. Comprises:
  - **Data routing service** — queries the placement service for where to store/read data and routes requests to data nodes.
  - **Placement service** — maintains a **virtual cluster map**: the physical topology (data centers, racks, nodes) and decides where replicas go. Uses heartbeats to track node health.
  - **Data node** — stores the actual object bytes on disk; replicates data to peer nodes.
- **Metadata store** — stores object metadata (bucket name, object id/key, size, version, location of the data, etc.). Logically separate from the data path so metadata and data scale independently.

### Uploading an Object (numbered flow)
1. Client sends an HTTP PUT to create object `script.txt` in bucket `bucket-to-share`.
2. API service authenticates via **IAM** (is the user allowed to write?).
3. API service forwards the payload to the **data store**; the data store persists the object and returns a **UUID (object id)**.
4. API service calls the **metadata service** to create a metadata entry mapping `(bucket_name, object_name)` → `object_id`, plus size, etc.
5. Success returned to the client.

### Downloading an Object (numbered flow)
1. Object storage has a **flat structure** with no real directories; the bucket+object name uniquely identifies an object.
2. Client sends HTTP GET `/bucket-to-share/script.txt`.
3. API service authorizes via **IAM**.
4. API service queries the **metadata store** to resolve the object's **UUID** and storage location.
5. API service fetches the object bytes from the **data store** by UUID and streams them back.

---

## Step 3: Design Deep Dive

### Data Store Deep Dive — How Objects Are Persisted
The data store has three components working together:
- **Data routing service** — stateless; exposes RPC/HTTP; calls placement service; routes read/write to the right data nodes; replicates writes to all replicas before acking.
- **Placement service** — keeps the **cluster map** and decides replica placement using a topology that spans **multiple data centers, racks, and nodes** to maximize fault isolation. It validates node health using a **heartbeat** mechanism (e.g., via Paxos/consensus for the placement service itself, run on a small odd number of nodes for high availability).
- **Data node** — stores bytes; one node is the **primary** replica that coordinates replication to **secondary** replicas; acknowledges the write to the routing service only after enough replicas persist.

### How Data Is Persisted on a Data Node
- Many **small objects** would waste space and inodes if each were its own file.
- Solution: **store many small objects together in a large, append-only file (WAL-style)** and keep a per-node, in-machine database/table mapping `object_id → (file_name, offset, size)`.

**Read path on the node:** look up the object id in the local mapping table → seek to `(file, offset)` → read `size` bytes.

### Durability: Replication vs. Erasure Coding

**Replication (e.g., 3x):**
- Store N full copies on different failure domains (nodes/racks/DCs).
- **Pros:** simple, fast reads/writes, easy recovery.
- **Cons:** high storage overhead (3x = 200% overhead).

**Erasure Coding (e.g., 8+4 / Reed-Solomon):**
- Split data into **k** data chunks and compute **m** parity chunks; any **k of (k+m)** chunks reconstruct the data.
- Example: **8 data + 4 parity** survives up to 4 chunk failures with only **1.5x** storage (50% overhead) vs **3x** replication.
- **Pros:** much higher storage efficiency at the same or better durability.
- **Cons:** higher CPU cost to encode/decode; slower/more expensive recovery and small-read amplification.

**Durability math intuition:** with N independent failure domains and a known annual failure rate, replication and erasure coding both push durability to **6–11 nines**; erasure coding reaches the same durability with far less raw storage. The chapter computes durability assuming an annual node/disk failure rate and shows erasure coding meeting six-nines cheaply.

**Recommendation:** use **erasure coding** for cold/large data to hit six-nines durability at ~1.5x cost; replication is fine where simplicity/latency matters.

### Correctness — Detecting Corruption
- Disks suffer **bit rot / in-flight corruption**.
- Store a **checksum** (e.g., MD5/SHA/CRC) per object (and per chunk). Verify on read; if a chunk fails its checksum, reconstruct it from replicas or parity chunks. This guarantees end-to-end integrity.

### Metadata Data Model
Two key tables:
- **Bucket table** — keyed by `bucket_id`/name (globally unique), owner, creation time, etc. Small (one row per bucket); read-heavy. Can be a single, well-replicated relational DB.
- **Object table** — keyed by `(bucket_id, object_name)` → `object_id`, version, size, etc. Huge (one row per object/version) → must be **sharded**.

**Listing objects:** `aws s3 ls` lists objects in a bucket, optionally by prefix. To make listing efficient, the object table is **indexed/sharded by `bucket_id` then `object_name`** so a bucket's objects are co-located and a prefix scan is a range scan.

**Sharding the object table:**
- Shard by **bucket_id** → all objects of a bucket on one shard; simple listing but a huge bucket creates a hotspot.
- Shard by **hash(bucket_id, object_name)** → even distribution but listing a bucket requires scatter-gather across shards.
- The chapter discusses the trade-off; a common compromise is sharding by bucket with care for very large buckets.

### Object Versioning
- Add a **version id** (object_version) to the object metadata key.
- Each upload to an existing key creates a **new version** rather than overwriting; older versions are retained and addressable.
- A **delete** inserts a **delete marker** (tombstone) as the latest version rather than physically removing data; the object can be restored by removing the marker.
- Listing returns the latest non-deleted version by default; all versions are listable explicitly.

### Optimizing Uploads: Multipart Upload
- Large objects are uploaded in **parts** (multipart upload):
  1. Client initiates a multipart upload and receives an **uploadId**.
  2. Client uploads parts in parallel, each acknowledged with an **ETag**.
  3. Client sends a **complete** request listing parts; the server assembles them into the final object.
- Benefits: parallelism, resumability, and handling objects larger than a single request.
- **Garbage collection** reclaims space from **abandoned/incomplete** multipart uploads and from **orphan/unreferenced** data after deletes.

### Garbage Collection
- Triggered by: object deletion (delete markers), failed/abandoned multipart uploads, replaced/old versions beyond retention, and orphaned data after a crash.
- A background **compaction/GC** process scans for objects no longer referenced by metadata and frees their space; it must coordinate with the metadata store to avoid deleting live data.

### Scalability & Availability
- **Stateless API + data routing services** scale horizontally.
- **Placement service** uses consensus (e.g., Paxos) on a small cluster for a consistent cluster map; heartbeats detect failed nodes and trigger re-replication/repair.
- Spread replicas/erasure chunks across **racks and data centers** for fault isolation.
- **Metadata** scales via sharding; **data** scales by adding data nodes; the placement service rebalances.

---

## Step 4: Wrap Up

### Summary of Key Decisions
- Separate the **data path** (object bytes) from the **metadata path** so each scales independently.
- **Stateless API service** orchestrates IAM + metadata + data store per request.
- Store many small objects in **large append-only files** with an in-node `object_id → (file, offset, size)` index.
- Use **erasure coding** (e.g., 8+4, ~1.5x overhead) to reach **six-nines durability** cheaply; replication where simplicity/latency wins.
- Verify integrity with **checksums**; reconstruct corrupted chunks from parity/replicas.
- Shard the huge **object metadata table**; keep the small **bucket table** centralized; index by bucket for efficient **listing**.
- Support **versioning** with delete markers (tombstones) and **multipart upload** for large objects.
- Run **garbage collection** to reclaim space from deletes, old versions, and abandoned uploads.
- Use a **placement service** with consensus + heartbeats to manage the cluster map and re-replication.

### Additional Talking Points
- Durability vs. cost trade-off (replication factor vs. erasure-coding parameters).
- Strong vs. eventual consistency for metadata vs. data.
- Cross-region replication and lifecycle policies (e.g., move cold objects to cheaper tiers).
- IAM/access policies, signed URLs, encryption at rest and in transit.

---

## Deep Enrichment: S3-like Object Storage

### Back-of-the-Envelope Math (Detail)

Worked numbers, step by step, for 100 PB of data at six-nines durability.

**Step 1 — Storage at scale.**
- 100 PB usable, 50% overhead with 8+4 erasure coding (k=8, m=4) → 150 PB raw on disks.
- Assume 20 TB drives (estimate; HDDs in 2024 ship 20–24 TB): 150 PB / 20 TB ≈ **7,500 disks**.
- Rack size ~60 disks → ~125 racks.
- Datacenter: ~20 racks per DC pod → ~6 DC pods; spread across 3 regions for fault isolation → 2 DC pods per region.

**Step 2 — Disk failure rate.**
- Industry estimate: ~1–2% annual AFR for HDDs (Backblaze publishes quarterly stats; ~1.5% is a reasonable working number for 2023–2024).
- 7,500 disks × 1.5% AFR = ~112 disk failures/year → ~9/month → ~3/week.
- Reconstruction cost per disk: a 20 TB disk needs ~20 TB read + 20 TB write. At 200 MB/s/disk ≈ 30 hours per reconstruction. With 4 parallel reconstruction workers per failed disk, ~7–8 hours. Mitigate by **parallel reconstruction across multiple nodes**.

**Step 3 — Durability comparison.**
Define `p = annual disk failure probability = 0.015`; with `N` independent failure domains, probability of losing `>M` out of `N` in a year drives durability.
- **3x replication**: lose data only if 3 replicas fail in the same erasure group; `P ≈ p^3 ≈ 3.4 × 10^-6`. Per object durability ≈ 1 - 3.4e-6 ≈ **5.5 nines**. Insufficient for SLA.
- **8+4 erasure coding**: lose data only if ≥5 of 12 chunks fail; `P ≈ Σ_{i=5..12} C(12,i) p^i (1-p)^(12-i) ≈ 7.5 × 10^-10`. Per object ≈ **9.1 nines**. Comfortably exceeds the 6-nines SLA.
- Adding **cross-region replication** (3 copies across 3 regions) multiplies these numbers further; S3's published **11 nines durability** assumes multi-region with erasure coding.

**Step 4 — Network egress at scale.**
- Assume 10% of stored data egressed/month (estimate; varies wildly by workload).
- 100 PB × 10% = 10 PB egress/month ≈ **3.3 Gbps average, ~30 Gbps peak**.
- At $0.09/GB egress, that's $900K/month just on egress for 10 PB.

**Step 5 — Metadata DB sizing.**
- 100 PB / 1 MB average object ≈ **100 billion objects**. Real workloads are bimodal: many small, few huge. Median ~100 KB, so object count ≈ **1 trillion**.
- Each metadata row ~256 bytes → metadata ≈ **256 TB**. Index overhead ×3 → ~768 TB. Distributed across ~16 shards, each ~50 TB; feasible on commodity NVMe.

**Step 6 — Listing throughput.**
- A bucket with 1B objects: full list takes ~30 minutes (estimate; depends on page size and sharding). Users accept this for one-time operations; paginated listing is the common access pattern (1000 objects per page).

### ASCII Architecture Diagrams

#### 1) Put / Get object (sequence)

```
Client         API Svc     IAM      MetaDB    Placement   Data Router   Data Nodes (replicas)
  |               |          |         |          |              |              |
  | PUT /b/k obj  |          |         |          |              |              |
  |-------------->|          |         |          |              |              |
  |               | authz    |         |          |              |              |
  |               |--------->|         |          |              |              |
  |               |<-- allow-|         |          |              |              |
  |               |          |         |          |              |              |
  |               | ask where to write              |              |
  |               |------------------------------->|              |
  |               |<-- {primary, replicas}          |              |
  |               |          |         |          |              |
  |               | PUT chunk to primary                        |
  |               |---------------------------------->|--------->|  (write A, B, C)
  |               |          |         |          |              |              |
  |               |          |         |          |              |  ack 3/3
  |               |          |         |          |              |<-------------|
  |               |<-----------------------------------| ack     |
  |               |          |         |          |              |              |
  |               | write metadata         |          |              |
  |               |------------------------>|          |              |
  |<-- 200 ETag --|          |         |          |              |              |
  |               |          |         |          |              |              |
  | GET /b/k obj  |          |         |          |              |              |
  |-------------->|          |         |          |              |              |
  |               | authz    |         |          |              |              |
  |               |--------->|         |          |              |              |
  |               | lookup object_id     |          |              |
  |               |------------------------>|          |              |
  |               |<-- {object_id, replicas}        |              |
  |               | ask where to read                |              |
  |               |------------------------------->|              |
  |               |<-- {replicas}      |              |
  |               |          |         |          | GET (nearest)|
  |               |------------------------------------------>|
  |               |<------------------ chunk bytes ---------------|
  |               |          |         |          |              |
  |<-- 200 + body |          |         |          |              |              |
```

#### 2) Erasure coding strip + placement

```
Object (1 MB logical) split into k=8 data chunks, m=4 parity chunks.

       d1  d2  d3  d4  d5  d6  d7  d8   <- data chunks
       p1  p2  p3  p4                    <- parity (Reed-Solomon)
        |   |   |   |   |   |   |   |
        v   v   v   v   v   v   v   v
       Rack A1-A8    Rack B1-B8   (spread so no 2 chunks share a rack)
       (each chunk on a different disk; each disk in a different server)

Reed-Solomon property: any 8 of the 12 chunks reconstruct the object.

Layout policy (example):
  d1..d4 on racks {R1, R2, R3, R4}
  d5..d8 on racks {R5, R6, R7, R8}
  p1..p4 on racks {R9, R10, R11, R12}
```

#### 3) Internal node layout (large append-only file)

```
Disk:
/var/data/objectstore/
  shard-0001.dat   <-- append-only file (WAL-style)
  shard-0001.idx   <-- object_id -> (file, offset, size) B-tree / LSM
  shard-0002.dat
  shard-0002.idx
  ...

Write path:
  Append(object_bytes) -> file_handle.append(bytes)
                          -> fsync
                          -> record(object_id, file, offset, size) in idx

Read path:
  Lookup(object_id) -> (file, offset, size)
  open(file).pread(offset, size) -> bytes
```

### Trade-off Tables

#### 1) Replication vs. erasure coding

| Scheme | Storage overhead | Durability (per object) | Read amplification | Recovery cost | Best fit |
|--------|------------------|--------------------------|---------------------|---------------|----------|
| 3x replication | 3.0× | ~5.5 nines (per disk failure math) | 1× | Cheap (re-replicate from any replica) | Hot data, small files |
| 8+4 RS | 1.5× | ~9.1 nines | 1× (whole) / k× (small) | Higher (decode 8 chunks) | Cold data, large files |
| 6+3 RS | 1.5× | ~8 nines | 1× / 6× | Medium | Mid-cold |
| 12+4 RS | 1.33× | ~10 nines | 1× / 12× | Higher | Archival |
| Locally Repairable Codes (LRC, Azure) | 1.25–1.5× | ~9 nines | 1× (single failure, local repair) | Lowest | Mixed workloads |
| Cross-region replication (×3) | 3× per region | 11+ nines | 1× | Cross-region expensive | Compliance, low-RPO |

#### 2) Metadata sharding

| Approach | Listing efficiency | Hot-bucket risk | Operational cost | Notes |
|----------|--------------------|------------------|-------------------|-------|
| Shard by `bucket_id` | Excellent (range scan on one shard) | High (one shard per huge bucket) | Low | Used by S3 at large scale with per-bucket sub-sharding |
| Shard by `hash(bucket_id, object_name)` | Poor (scatter-gather per list) | Low (even distribution) | Medium | Good for writes, bad for listings |
| Shard by `bucket_id` with internal hashing | Good (range scan on bucket partition) | Medium | Medium | Compromise |
| Two-level: index shard + object shards | Excellent with index | Medium | High | Maintained at hyperscalers |

#### 3) Consistency model

| Option | Consistency | Latency | Availability | Use case |
|--------|-------------|---------|--------------|----------|
| Strong (after-metadata-write visible) | Strong | Higher | Lower | Critical reads-after-write |
| Read-after-write for single object | Strong for one key | Slightly higher | Medium | S3 default per-object |
| Eventual | Eventual | Lowest | Highest | Bulk listing, analytics |
| Versioned read (read latest version) | Strong with version pin | Medium | Medium | Concurrent writers |

#### 4) API tier vs. data tier storage

| Tier | Storage | Retrieval | Cost | Latency | Lifecycle |
|------|---------|-----------|------|---------|-----------|
| Standard | HDD/SSD | Free | $$$ | ms | Hot, frequent |
| Infrequent Access | HDD | $/GB | $$ | tens of ms | ≥30 days |
| Archive (Glacier-like) | Tape / cold disk | $/GB + retrieval fee | $ | minutes–hours | ≥90 days |
| Deep archive | Tape / cold disk | $/GB + high fee | ¢ | hours | ≥1 year |

### Real-World Case Studies

#### 1) Amazon S3
S3 launched in 2006 with the "11 nines of durability" claim, achieved via cross-region replication + erasure coding internally. S3 stores trillions of objects and handles >100M requests/second at peak. Public papers include "Amazon S3: 16+ Years of Cloud Object Storage" (Vogt et al., 2023) and the original "AWS S3 Architecture" deep dives (Brandwine, 2009). Internal architectural choices: separate **index/metadata subsystem** (DynamoDB-backed) from **storage subsystem**; **request routing** via DNS-weighted load balancers; **incremental listing** via cursor pagination. (Sources: Vogt et al., USENIX FAST 2023.)

#### 2) MinIO
MinIO is an open-source S3-compatible object store written in Go. It uses **erasure coding (Reed-Solomon)** as the default storage layout and supports both 8+4 and configurable `k+m`. It stores objects as **append-only** files in a content-addressable format (called "xl.meta") with bitrot detection via HighwayHash. The codebase is the most readable open reference for the chapter's design. (Source: min.io/docs, GitHub.)

#### 3) Ceph
Ceph (Sage Weil's PhD thesis, 2007) provides object (RADOS), block (RBD), and file (CephFS) storage on top of a unified object store. RADOS uses **CRUSH** (Controlled Replication Under Scalable Hashing) — a deterministic placement algorithm that maps objects to OSDs without a centralized directory. Ceph uses replication by default but supports **erasure-coded pools** (jerasure / ISA-L). The CRUSH map is the chapter's "placement service" generalization. (Source: Weil, "Ceph: Reliable, Scalable, and High-Performance Distributed Storage", UCSC PhD thesis 2007.)

#### 4) HDFS
HDFS uses 3x replication by default and is designed for batch analytics (Hadoop). Its architecture — NameNode (metadata) + DataNodes (chunks of 128 MB) — directly maps to the chapter's metadata/data split. HDFS erasure coding (HDFS-7285) added EC support with schemes like RS-6-3-1024k, achieving ~1.5× overhead vs 3× replication. (Source: hadoop.apache.org docs.)

#### 5) Google Cloud Storage (GCS)
GCS uses Colossus (successor to GFS) for storage and Spanner/Bigtable for metadata. Public talks describe auto-balancing, lifecycle management, and nearline/coldline tiers. GCS is the only major provider that publishes its **consistency model** explicitly: strong read-after-write for object data and listing. (Source: Google Cloud Next talks.)

#### 6) Azure Blob Storage
Azure Blob Storage uses **Locally Repairable Codes (LRC)** as part of its coding scheme, which reduces repair cost vs. Reed-Solomon by allowing single-failure repairs to use only a local group of chunks. Microsoft published "Erasure Coding in Windows Azure Storage" (Huang et al., USENIX ATC 2012) describing 12+3 and 6+3 schemes and the LRC extension. (Source: USENIX ATC 2012.)

#### 7) Backblaze B2 + Vault durability
Backblaze publishes detailed drive statistics quarterly ("Hard Drive Cost Per GB", "Hard Drive Failure Rates") and has open-sourced its Storage Pod designs. Their B2 service targets aggressive cost ($0.005/GB/month). Backblaze Vaults are built on commodity hardware with erasure coding; they document durability targets and explicitly call out the cost/availability trade-off. (Sources: backblaze.com/blog, Vault design posts 2019+.)

#### 8) Wasabi
Wasabi is hot-cloud storage priced at $0.0069/GB/month with **no egress fees**. Their architecture emphasizes a single hot tier (no archive tier) and aggressive use of erasure coding + replication to deliver 11 nines durability. Useful interview example for "no egress fee" pricing model.

#### 9) Reed-Solomon and LRC papers
- Reed & Solomon, "Polynomial Codes over Certain Finite Fields" (1960) — original construction.
- Plank & Ding, "Note: Correction to the 1997 Tutorial on Reed-Solomon Coding" (2003) — practical tutorial.
- Huang et al., "Erasure Coding in Windows Azure Storage" (USENIX ATC 2012) — production LRC.
- Sathiamoorthy et al., "XORing Elephants: Novel Erasure Codes for Big Data" (VLDB 2013) — HDFS-RAID-style local codes.
- Rashmi et al., "A Solution to the Network Challenges of Data Recovery in Erasure-coded Distributed Storage Systems" (2013) — LRC variants.

### Common Pitfalls & Failure Modes

#### 1) Hot-bucket thundering herd
**Scenario:** A celebrity uploads a 1 TB file. 1M users GET the same object. Cache fill rates spike; data node serving the hot replica saturates.
**Mitigation:** tiered caching (edge CDN → per-region cache → per-DC cache → disk); replication on demand (auto-add replicas for hot keys); **request coalescing** at the CDN edge.

#### 2) Erasure coding cascading rebuilds
**Scenario:** A rack fails; 8+4 layout loses 2 chunks; system begins rebuilding from the remaining 10. Rebuild reads are intense and trigger 2 more disks to fail in adjacent racks; another rebuild begins; the system oscillates.
**Mitigation:** **throttle rebuilds**; cap concurrent repairs per node; **degraded read mode** instead of immediate rebuild; spread rebuild I/O across the cluster. The famous Facebook "HDFS RAID" case study showed this exact failure mode.

#### 3) Tombstone explosion in versioning
**Scenario:** A bug deletes an object 1000 times per second, each generating a delete marker. Metadata table bloats; listing slows to a crawl.
**Mitigation:** rate-limit deletes; batch delete markers into a single tombstone; expire delete markers after retention; alert on `delete_marker_count` > N per bucket.

#### 4) Metadata DB hotspot on a single huge bucket
**Scenario:** A bucket with 10B objects lands on one shard. Listing the bucket overloads that shard.
**Mitigation:** auto-split a bucket across multiple shards when object count exceeds a threshold; use **secondary indexes** (e.g., on `(bucket_id, prefix)`) so common list-prefix queries hit a narrow index; rate-limit list operations per bucket.

#### 5) Cross-region replication lag causes RPO violation
**Scenario:** Primary region writes succeed; replication to secondary lags 30 minutes. Primary region goes down; secondary has 30 min of unacknowledged writes lost.
**Mitigation:** measure and alert on replication lag; consider **synchronous replication** for critical objects (cost is latency); communicate RPO clearly in SLA; offer multi-region writes with last-writer-wins on conflict.

#### 6) Checksum collision (theoretical)
**Scenario:** An MD5 collision lets an attacker replace a stored object with a different payload that hashes the same. Not a known real-world exploit on S3 (which uses stronger checksums internally for integrity) but a perennial interview trap.
**Mitigation:** use SHA-256 or BLAKE3 for stored integrity checks; sign sensitive objects client-side; verify checksums end-to-end.

#### 7) Multipart upload garbage
**Scenario:** Client initiates a multipart upload and never sends `Complete` or `Abort`. Server keeps the partial parts indefinitely. Storage fills with garbage.
**Mitigation:** lifecycle policy that auto-aborts multipart uploads after 7 days (S3 default rule); monitor abandoned-upload count; per-bucket limits on concurrent multipart uploads.

#### 8) Bit rot in cold storage
**Scenario:** An object in archive storage is read after 3 years; 2 chunks have silent bit rot. Without checksums, the user gets corrupted data.
**Mitigation:** periodic **scrubbing** jobs that read every chunk, verify checksum, and repair on failure; **end-to-end checksums** stored in metadata; **client-side encryption** with integrity verification on the user's side.

#### 9) Placement service split-brain
**Scenario:** Network partition splits the placement service consensus group; two cluster maps exist briefly; two clients write to the same logical key but different physical replicas; on heal, both writes "win" and one is silently lost.
**Mitigation:** require majority quorum for placement service writes (Paxos/Raft); use **generation numbers** (epoch) on every write; on heal, the older-generation writes are rejected. Classic Paxos lesson.

**Scenario (continued) — cascading rebuilds + placement churn:**
A split-brain can also cause the placement service to issue rebuild plans based on inconsistent views; data ends up duplicated or lost. Mitigations above plus **write fencing tokens** to detect stale leaders.

### Interview Q&A

**Q1 — Clarifications.**
Sketch: ask total storage scale (PB vs. EB), read:write ratio (immutable log vs. frequently updated), consistency needs (strong read-after-write for sensitive objects vs. eventual for batch), expected object size distribution (small image-heavy vs. large video), retention (months vs. forever), cross-region requirements, encryption model (server-side, client-side, KMS-managed), compliance (HIPAA, FedRAMP).

**Q2 — Capacity estimation.**
Sketch: 100 PB usable; 8+4 EC = 150 PB raw; ~7,500 disks at 20 TB each; ~125 racks across 3 regions. Metadata: 1T objects × 256 B = 256 TB → 768 TB indexed across 16 shards. Egress: 10 PB/month → ~3.3 Gbps average. Reconstruction: 3 disk failures/week × ~8 hours/rebuild.

**Q3 — Replication vs. erasure coding.**
Sketch: 3x replication is simple and meets ~5.5 nines at the chapter's failure rate — insufficient for 6-nines SLA. 8+4 RS meets ~9.1 nines with 1.5× overhead, well within the SLA budget. Recommendation: 8+4 RS for bulk; 3x for hot small objects; LRC for fast-repair mid-tier.

**Q4 — Why separate data and metadata stores?**
Sketch: they scale on different axes. Data scales by disk count, IOPS, throughput. Metadata scales by object count, query latency, indexing. A monolithic system bottlenecks on whichever is harder; separating them lets each scale independently. S3, GCS, and Azure Blob all use this pattern.

**Q5 — Multipart upload design.**
Sketch: client requests `InitiateMultipartUpload` → server returns `upload_id`. Client uploads parts in parallel (5 MB min, 5 GB max each, 10,000 parts max for S3). Each part gets an ETag. Client sends `CompleteMultipartUpload` with the ordered list of part ETags. Server verifies all parts exist, then atomically combines them into the final object with one metadata entry. Lifecycle policy aborts incomplete uploads after 7 days.

**Q6 — Versioning and tombstones.**
Sketch: every object has a `version_id`. Uploads create new versions. Deletes insert a delete marker (tombstone) as the latest version. List returns the latest non-deleted version. `DELETE ?versions` removes all versions. The deletion is **logical**; physical GC frees unreferenced data later.

**Q7 — "What if we 10×?"**
Sketch: add regions for egress locality; move metadata to a distributed SQL (CockroachDB, Spanner) for global consistency; introduce tiered storage (hot SSD, cold HDD, archive tape); deploy a CDN for the most-read 1% of objects; consider an LRC scheme for cheaper reconstruction.

**Q8 — "What if we go global?"**
Sketch: deploy regions in NA, EU, AP. Replicate critical data cross-region (3 regions for 11 nines). Use geo-DNS to route uploads to the user's home region. Use a **global metadata index** (Spanner or DynamoDB Global Tables) for cross-region list operations. Beware of data residency laws (GDPR); keep EU user data in EU.

**Q9 — How do you prevent bit rot in cold storage?**
Sketch: store SHA-256 checksum of every chunk; run a daily **scrubber** that reads each chunk, verifies checksum, and reconstructs from parity on failure. For very cold data (years), use **client-side encryption with client-held keys** so the client can verify integrity on read.

**Q10 — Concurrency on a single key.**
Sketch: last-writer-wins on `version_id` (UUID); the API server returns the version it observed on the request; on PUT, the server accepts any new version; race is acceptable because objects are immutable. For pre-conditions (e.g., "only if current version is X"), use **conditional writes** with `If-Match: <version_etag>` like HTTP ETag semantics.

### Key Terms / Glossary

| Term | Precise definition | Common misconception |
|------|---------------------|----------------------|
| **Bucket** | A flat namespace container; globally unique name. | Not a directory; objects have no parent-child relationship to the bucket. |
| **Object** | Bytes + metadata + key; immutable per version. | Not a file; partial updates create new versions. |
| **Erasure coding** | Reed-Solomon or similar: split into k data + m parity chunks; any k chunks reconstruct. | Not the same as RAID; EC chunks are distributed across failure domains. |
| **Replication factor (RF)** | Number of full copies of each object. | RF=3 across racks ≠ 3 independent failure domains if all racks share a PDU. |
| **Locally Repairable Code (LRC)** | EC variant where single failures can be repaired from a local group, reducing I/O. | Not a general replacement for RS; trades storage efficiency for repair cost. |
| **Multipart upload** | Client-driven parallel upload of parts with an `upload_id`. | Without lifecycle GC, abandoned uploads leak storage. |
| **Delete marker** | A tombstone versioning record; object appears deleted but bytes remain. | `DELETE ?versions` removes the marker and underlying data; default `DELETE` only adds the marker. |
| **ETag** | HTTP entity tag returned by PUT; checksum or version identifier. | ETag ≠ MD5 in all providers (S3 multipart ETag is a multi-part hash). |
| **Pre-signed URL** | A time-limited URL that grants temporary access to an object without exposing credentials. | Not a substitute for proper IAM; leaked URLs leak access. |
| **Lifecycle policy** | Automated rule that transitions objects between tiers or expires them after a date. | Policies apply to **current version** by default; old versions need a separate rule. |
| **Bit rot** | Silent data corruption on storage media over time. | Detected only by checksumming on read or periodic scrubbing. |
| **Scrubber** | Background job that reads stored data, verifies checksums, repairs on failure. | Without a scrubber, cold data accumulates undetectable corruption. |
| **Placement service** | A component that owns the cluster map and decides where chunks/replicas go. | Often confused with the metadata service; placement decides *where*, metadata decides *what*. |
| **CRUSH** | Ceph's deterministic placement algorithm; computes location from object_id and cluster map. | CRUSH gives different answers under different cluster maps; rebalancing is a deliberate operation. |
| **Cross-region replication (CRR)** | Asynchronous replication of objects to a second region. | Not the same as multi-region writes; CRR has lag and is best-effort. |
| **Strong consistency (per-object)** | A successful PUT is visible to subsequent reads. | S3 added strong consistency for object metadata in 2020; before that, listings were eventually consistent. |