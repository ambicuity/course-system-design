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
