# Design Google Drive

## Overview

The task is to design a file storage and synchronization service like Google Drive or Dropbox. Files can be accessed on any device, automatically synced across a user's devices, and (in the full chapter) shared between users. The design emphasizes resumable uploads, low latency, data integrity, and cost efficiency at massive scale.

---

## Step 1: Requirements & Scope

### Functional Requirements

**Core:**
- Users can upload files from any of their devices
- Users can download their files to any of their devices
- Files automatically sync between a user's devices
- Basic file operations: rename, move, delete
- File versioning and recovery (version history)
- File sharing with permissions and shareable links (covered in full chapter)
- Notifications when files change

**Out of scope (in the condensed treatment):**
- File sharing between users
- File organization
- Real-time collaborative editing (i.e., Google Docs)

### Non-Functional Requirements

- Prioritize **availability over consistency** for synchronization operations
- Low-latency uploads and downloads
- Support large files (the chapter caps around 50 GB; some treatments use 5-10 GB)
- Uploads should be **resumable**
- Reliability and data integrity (no data loss / corruption)
- High availability (target ~99.99% uptime) and high durability (target ~eleven nines)
- Horizontal scalability for billions of objects; cost efficiency at petabyte/exabyte scale

### Back-of-Envelope Estimation

Representative assumptions:
- ~50 million daily active users (from a 500M user base, ~10% DAU)
- Average storage per user ~5-10 GB
- ~1,000 files per user

Derived figures:
- Total logical storage on the order of exabytes (e.g., 2.5 EB), growing with replication and shrinking with deduplication
- ~3x replication offset by ~40% deduplication
- Metadata operations on the order of tens of thousands of QPS (e.g., ~60,000 QPS)
- File operations on the order of thousands of ops/sec

---

## Step 2: High-Level Design

### The API

- `POST /files` → upload files (returns pre-signed URLs rather than uploading through the API server)
- `GET /files` → list files
- `GET /files/{fileID}` → download a file (provides a pre-signed download URL)
- `GET /files/revisions?since={timestamp}` → list changes to all files since a timestamp

### Moving Away From a Single-Server Setup

- Begin with a simple single-server setup, then scale out.
- Upload files **directly to blob storage** using **pre-signed URLs**, rather than routing file bytes through the API server.
- `POST /files` provides pre-signed URLs the client uses to upload to blob storage.
- On upload, metadata (file name, type, size, owner, blob storage key) is inserted into a database.
- Pre-signed URLs are generated on demand for both uploads and downloads.
- `GET /files/{fileID}` returns the pre-signed URL so clients download directly from blob storage.
- Make the API server **stateless** and scale it horizontally behind a **load balancer**.

### High-Level Architecture Components

| Component | Responsibility |
|-----------|-----------------|
| Load Balancer | Routes and distributes traffic across stateless API servers |
| API Gateway / API Servers | Authentication, authorization, rate limiting, request routing |
| Metadata Service (formerly "API Servers") | File info, hierarchy, permissions, version links, chunk/block mappings |
| Storage Service / Block Servers (formerly "Block Servers") | Chunk transfer, hashing, delta sync, resumable/parallel streaming |
| Chunk Storage (Object/Blob Store) | Distributed block storage with replication / erasure coding |
| Metadata Database | Relational DB (e.g., Postgres) for file/block metadata; strong consistency |
| Sync Service | Change logs, device coordination, offline queue management |
| Notification Engine | Real-time updates via push/polling hybrid |
| Access Control Service | Permission enforcement, ACL evaluation |
| CDN | Global content distribution for downloads |
| Offline Backup Queue | Holds changes for offline clients until reconnect |

### Syncing

- When a user updates a file, the file is uploaded to blob storage and its metadata (`updated_at`, etc.) is updated in the database.
- Other devices **poll for changes** via `GET /files/revisions?since={timestamp}`, which lists files that have been updated and need to be re-downloaded.
- Fetching updated contents can be **eager or lazy** depending on need.
- As clients grow, continuous polling becomes expensive and adds latency. Alternatives: **long polling, Server-Sent Events (SSE), WebSockets, or push notifications** to notify clients when revisions occur.

### Conflicts

Conflicts arise when two clients/users update the same file concurrently. Resolution strategies:
1. First write wins
2. Last write wins
3. Create copies/variants when conflicts arise (e.g., "filename (conflicted copy)")
4. Automatic merging with CRDTs

Given strict data-integrity requirements (avoid data loss from overwrites), prefer **option 3 or 4**.

---

## Step 3: Design Deep Dive

### Block Servers & Delta Sync

**Problem:** If only a single line in a file changes, uploading/downloading the entire file is wasteful.

**Solution — chunking + delta sync:**
- Split the file into small **blocks (chunks)**, typically ~4-8 MB each.
- **Hash each block** (e.g., SHA-256) so clients and servers can quickly determine which blocks changed.
- **Delta sync** transfers only the modified blocks, not the whole file.
- Files are represented as **ordered lists of block hashes**, allowing the system to determine which blocks changed, which already exist, and how to reconstruct the file.
- The **metadata database maps files to their constituent blocks**; the blocks live in blob storage.

**Block Servers are responsible for:**
- Chunking files into small blocks
- Managing block hash metadata
- Identifying changed blocks during synchronization
- Maintaining file → block mapping metadata
- Deduplication, encryption, compression, etc.

**Client flow:** Instead of one pre-signed URL for the whole file, clients receive metadata describing the file's blocks plus pre-signed URLs for each required block. The client downloads blocks directly from blob storage and reassembles locally. Before upload, clients compute block hashes locally — if a block already exists in storage it is skipped; only new/modified blocks are uploaded.

**Replication options for blocks:**
- Synchronous: write to multiple locations before ACK (strong durability, higher latency)
- Asynchronous: ACK immediately, propagate in background (better performance)
- Erasure coding: split into fragments + parity (less overhead than 3x replication)

### Metadata Database

File contents are in blob storage; metadata is in a relational DB (e.g., Postgres). Metadata may include:
- File name, File ID, File size
- Owner, Path / location
- `created_at`, `updated_at` timestamps
- Version number
- Block hashes (or references to constituent blocks)
- Access control lists, sharing configuration, soft-delete flags

This lets the system list files and identify block deltas **without querying blob storage**.

**Consistency:** Metadata demands **strong consistency** (a rename or permission change must appear immediately everywhere → ACID guarantees). Chunks and search indexes can be eventually consistent.

**Indexing strategies:** secondary indexes on filenames (search), timestamps (sorting), owner fields (permission queries), materialized paths (fast folder lookups without traversal).

**Sharding approaches:**
- User-based: all of a user's files on the same shard (fewer cross-shard ops)
- File-based: distributes load evenly (handles hot users)

**Caching layers:** client-side (recently accessed metadata), edge/CDN (popular files), backend in-memory (hot folder structures and permissions).

### Large File Uploads

- Files are uploaded in chunks.
- If an upload is interrupted, the client retries only the **missing chunks** rather than restarting the whole transfer (resumable uploads).
- Chunks can be uploaded in parallel.

### Notification Service

- Notifies clients when file revisions occur so they re-sync.
- Implemented with **long polling** (the chapter's choice) — clients hold a connection open until a change or timeout; alternatives are WebSockets/SSE/push.
- Long polling fits because changes are not extremely frequent per client and connections need not be bidirectional/persistent.

### Reliability & Data Integrity

To prevent data loss:
- Replicate file blocks in blob storage across multiple availability zones / data centers
- Replicate and routinely back up the metadata database
- Use hashes/checksums to detect corrupted blocks
- Retain previous file versions to recover from accidental deletion, corruption, and sync conflicts

### Save Storage Space / Cost Savings

- Routinely **deduplicate blocks** (identical chunks across users/files stored once)
- Set **per-user storage limits**
- Move infrequently accessed contents to **cold storage** classes (e.g., S3 Glacier)
- **Expire and delete old file versions** (and cap version count)
- Compression for compressible types; tiered (hot/cold) storage

### Versioning Strategy

| Approach | Storage efficiency | Restore speed | Complexity |
|----------|--------------------|---------------|------------|
| Full snapshots | Lower | Fast (direct) | Simple |
| Differential | Higher | Slower (chain) | Complex |
| Hybrid | Moderate | Moderate | Moderate |

Updates create new versions (immutable storage model); old data persists unchanged, which simplifies consistency and enables efficient caching.

---

## Failure Handling

| Failure | Handling Strategy |
|---------|-------------------|
| Load balancer failure | Secondary LB becomes active; heartbeat monitoring between LBs |
| Block/Storage server failure | Other servers pick up unfinished/pending work; blocks replicated |
| Cloud/blob storage failure | Multi-region replication; serve from another region |
| API server failure | Stateless — load balancer reroutes to healthy servers |
| Metadata DB failure | Promote a replica to primary; restore from backups; replicas serve reads |
| Notification service failure | Reconnect on recovery; clients resume polling for revisions |
| Offline backup queue failure | Queue replicated; consumers re-subscribe to a backup queue |

---

## Step 4: Wrap Up

### Final High-Level Design

- The former "API Servers" are reframed as the **Metadata Service**, and the former "Block Servers" as the **Storage Service**, to better reflect responsibilities.
- The system separates **metadata (strongly consistent)** from **block contents (eventually consistent)** and **search (eventually consistent)**, enabling independent optimization of each layer.

### Key Tradeoffs Discussed

- **Strong vs. eventual consistency:** metadata is strongly consistent; chunk propagation and search are eventually consistent.
- **Availability vs. consistency:** sync prioritizes availability.
- **Replication vs. erasure coding:** durability vs. storage overhead.
- **Snapshot vs. differential versioning:** restore speed vs. storage efficiency.
- **Push vs. polling vs. long polling:** immediacy and connection cost vs. simplicity.
- **Pre-signed URLs + direct-to-blob upload:** offloads bandwidth from API servers.
- **Delta sync / dedup:** bandwidth and storage savings at the cost of hashing/metadata complexity.

### Discussion Extensions
- Tension between strong consistency and high availability; consider tuning consistency per operation.
- Reducing block-server load by moving online presence/sync logic, and handling clients that go offline via the offline backup queue.

---

**Reference:** *System Design Interview - An Insider's Guide* by Alex Xu. Copyright 2020 Byte Code LLC.

---

# Deep Dive Addendum

The remainder of this chapter is enrichment for interview-grade depth: extended capacity math, ASCII diagrams, trade-off tables, real-world case studies (Dropbox block magic, OneDrive differential sync, iCloud, Box, CRDTs vs OT), failure modes, interviewer Q&A, and a glossary.

## Back-of-the-Envelope Math (Extended)

The chapter's headline numbers (50M DAU, 5-10 GB/user, 1,000 files/user) imply exabytes of logical storage. Defend and refine.

### Step 1 — derive storage in powers of 2

```
DAU              = 50,000,000           ≈ 5 × 10^7
avg storage/user = 7.5 GB (midpoint)   ≈ 7.5 × 2^30 bytes
total logical    = 5e7 × 7.5 GB
                 = 375 PB (logical)
```

With 3× replication (raw on disk):

```
raw = 375 × 3 = 1,125 PB ≈ 1.1 EB
```

After 40% deduplication (Dropbox has published that real-world dedup rates are 30-60% for general file corpora):

```
dedup_factor = 0.40
post_dedup   = 1.1 × (1 - 0.40) ≈ 0.66 EB
```

The chapter's "2.5 EB" estimate uses a higher per-user figure (likely closer to 10 GB average) and 4× replication, hence the larger number. Both estimates are in the right range; either is interview-defensible.

### Step 2 — block count and dedup math

Assume a 4 MB block size (Dropbox has used 4 MB; OneDrive uses larger, around 8 MB for cold tiers).

```
avg files / user     = 1,000
avg file size        = 7.5 MB (7.5 GB / 1000)
avg blocks / file    = 7.5 / 4 = 1.875 ≈ 2 blocks
total blocks (all)   = 50M × 1000 × 2 = 1e11 blocks
```

Hash size: SHA-256 = 32 bytes per block. With deduplication:

```
unique_blocks       ≈ 1e11 × 0.60  (40% dedup)
                    = 6e10 blocks
hash_storage_only   = 6e10 × 32 B   = 1.92 TB (hash index)
```

The hash index itself is small enough to fit on a single beefy metadata DB. The block content storage is the elephant.

### Step 3 — QPS for metadata vs blocks

Assume 50M DAU with 10 syncs/user/day (open the app, edit a file, save, sync):

```
metadata_ops / day  = 50M × 10 = 5 × 10^8
metadata_qps_avg    = 5e8 / 86400 ≈ 5,787 QPS
metadata_qps_peak   ≈ 5 × avg ≈ 29,000 QPS
```

Block transfer QPS is a fraction of this (most syncs touch <5 blocks):

```
block_ops / day     ≈ 5e8 × 5 = 2.5e9 block ops / day
block_qps_avg       ≈ 28,935 QPS
block_qps_peak      ≈ 145,000 QPS
```

That is the same order as the chapter's "60,000 QPS" because the assumptions differ. The point is: **metadata is not the bottleneck; block storage bandwidth is**. Plan accordingly.

### Step 4 — bandwidth budget for downloads

Average download size per sync ≈ 1 MB (a small file or a few blocks of a larger one):

```
downloads / day   ≈ 5e8
bytes / day       ≈ 5e8 × 1 MB = 500 TB / day
avg_bandwidth     ≈ 500 TB / 86400 s ≈ 5.8 GB/s ≈ 46 Gbps
peak_bandwidth    ≈ 230 Gbps
```

A single 100 Gbps port can carry the average; peak needs multiple. The CDN offloads most of this in production.

### Step 5 — durability math

"Eleven nines" of durability means annual loss probability of 10^-11 per object. With 10^11 blocks, the **expected annual loss** at 11 nines is:

```
expected_loss = 10^11 × 10^-11 = 1 block / year
```

Dropbox, Google Drive, and OneDrive all publish durability claims at this level, which is achievable only with **cross-region replication + erasure coding + periodic integrity scrubbing**. A single-region 3× replication only achieves ~6 nines.

### Step 6 — dedup economics

Assume S3 standard at $0.023/GB-month. Without dedup:

```
monthly_cost = 0.66 EB × $0.023/GB ≈ $15,180 / month (raw) per EB
annual        ≈ $182k / EB / year
```

For 0.66 EB:

```
annual_storage_cost ≈ 0.66 × 182k ≈ $120k / year
```

Wait — that is suspiciously low. Real-world numbers:

- Dropbox's 2023 10-K filing disclosed storage costs in the hundreds of millions of dollars across their custom Magic Pocket infrastructure.
- The discrepancy comes from the fact that cloud storage prices assume sequential I/O at high utilization; sync workloads have heavy random-read IOPS requirements that 3-5× the storage cost.

So plan for **3-5× the headline $/GB** when sizing for production.

---

## ASCII Architecture Diagrams

### Diagram 1 — End-to-end upload + sync

```
                                              ┌─────────────────────────┐
                                              │  Metadata DB (primary)  │
                                              │  Postgres / Spanner     │
                                              └────────────┬────────────┘
                                                           │
   ┌──────────┐    ┌──────────┐    ┌──────────┐            │
   │  Client  │───▶│   API    │───▶│ Metadata │────────────┘
   │ (laptop) │    │  GW +    │    │ Service  │──▶ Metadata cache (Redis)
   └────┬─────┘    │  AuthN   │    └────┬─────┘
        │          └──────────┘         │
        │  1. POST /files (metadata)    │
        │  ◀── pre-signed PUT URLs per block ──┐
        │                                       │
        │  2. PUT blocks (parallel)             │
        ▼                                       │
   ┌──────────┐                                 │
   │  Chunk   │  ───────────────────────────────┘
   │  Storage │      3. block upload complete (event)
   │  (S3 /   │
   │   GCS)   │
   └────┬─────┘
        │
        │  event: ObjectCreated
        ▼
   ┌──────────┐    ┌──────────┐    ┌──────────┐
   │  Block   │───▶│  Hash &  │───▶│ Dedup    │
   │  queue   │    │  index   │    │  service │
   └──────────┘    └──────────┘    └──────────┘
        │
        │  4. metadata update complete
        ▼
   ┌──────────────────┐
   │  Sync fan-out    │──▶ Notification (long-poll / WS) ──▶ Other devices
   │  service         │
   └──────────────────┘
```

### Diagram 2 — Sync (delta) on a second device

```
   Device B                       API GW                    Metadata DB
      │                              │                          │
      │  GET /files/revisions?       │                          │
      │      since=last_sync_ts      │                          │
      │─────────────────────────────▶│                          │
      │                              │  query revisions > ts    │
      │                              │─────────────────────────▶│
      │                              │◀─── list of file_ids ───│
      │                              │   + per-file block_list │
      │◀── JSON list ────────────────│                          │
      │                              │                          │
      │  for each changed file:      │                          │
      │   compute local block hashes │                          │
      │   diff against server list   │                          │
      │                              │                          │
      │  GET /files/{id}/blocks?ids=…│  (block URLs only for    │
      │─────────────────────────────▶│   blocks client lacks)   │
      │◀── pre-signed GET URLs ─────│                          │
      │                              │                          │
      │  GET each missing block      │                          │
      │  from chunk storage          │                          │
      │                              │                          │
      │  reassemble file locally     │                          │
      │  update local sync cursor    │                          │
```

### Diagram 3 — Conflict resolution (last-writer-wins with copy)

```
   Device A                          Server                       Device B
      │                                 │                              │
      │ PUT /files/123 (v17)             │                              │
      │ ts=T2, blocks=[a,b,c]            │                              │
      │─────────────────────────────────▶│                              │
      │                                 │  (server has v16 from B)    │
      │                                 │  ts=T1                       │
      │                                 │                              │
      │                                 │                              │
      │                                 │  T2 > T1, A wins             │
      │                                 │  rename B's version:         │
      │                                 │   123 (B's conflicted copy)  │
      │                                 │                              │
      │◀────── 200 OK ──────────────────│                              │
      │                                 │  ─────── notify B ──────────▶│
      │                                 │                              │
      │                                 │   "file 123 was modified     │
      │                                 │    by another device; your  │
      │                                 │    version saved as          │
      │                                 │    '123 (B's conflicted...)' "│
```

### Diagram 4 — Erasure coding layout (6+3 example)

```
Block contents:  B1 B2 B3 B4 B5 B6  (6 data fragments)
                 ───────────────────
                 P1 P2 P3           (3 parity fragments)
                 ───────────────────
                 Total: 9 fragments
                 Storage overhead: 9/6 = 1.5× (vs 3× for replication)
                 Tolerable failures: any 3 fragments

Distribution:    9 fragments spread across 9 distinct AZ/rack combos
                 using a deterministic placement algorithm
                 (e.g., CRUSH, RS(6,3) + placement)
```

---

## Trade-off Tables

### Trade-off 1 — Replication vs erasure coding

| Approach | Storage overhead | Read latency | Write latency | Tolerated failures | Best for |
|---|---|---|---|---|---|
| 3× replication | 3× | Low | Low | 2 of 3 | Hot data, low-latency reads |
| Erasure coding (6+3) | 1.5× | Higher (decode multiple fragments) | Higher (compute parity) | 3 of 9 | Warm/cold storage at scale |
| Hybrid (replicated hot, EC cold) | Variable | Low (hot) / Higher (cold) | Low / Higher | Tier-dependent | Most production |
| Replication across regions (geo) | 3N× for N regions | Low per region | High (sync write) | Region failure | Disaster recovery |

### Trade-off 2 — Chunk size

| Chunk size | Dedup granularity | Metadata overhead | Upload parallelism | Resumable granularity |
|---|---|---|---|---|
| 64 KB | Fine (high dedup) | Very high (millions of blocks per file) | High | Fine |
| 1 MB | Moderate | High | Moderate | Fine |
| 4 MB | Moderate | Reasonable | Moderate | Reasonable |
| 16 MB | Coarse (lower dedup) | Low | Low | Coarse |
| Variable / content-defined | Excellent | Medium | Good | Good |

Dropbox uses 4 MB (variable block sizing with rolling hash). rsync uses content-defined chunks at the byte level. The trade-off is "more dedup vs. more metadata."

### Trade-off 3 — Conflict resolution

| Strategy | Data loss risk | Complexity | User experience | Best for |
|---|---|---|---|---|
| First-write-wins | High (loses second edit) | Low | Confusing | Single-writer scenarios |
| Last-write-wins | High (loses first edit) | Low | Confusing | Single-writer scenarios |
| Server-side vector clocks | None | High | Transparent | CRDT-friendly data |
| Copy-on-conflict | None | Medium | Clear (file "filename (conflicted copy)") | Documents, generic files |
| Operational Transform (OT) | None | Very high | Transparent | Real-time co-editing (Google Docs) |
| CRDT | None | High | Transparent | Real-time co-editing, collaborative apps |
| 3-way merge (text) | None | Medium | Familiar to developers | Text files (git-style) |

### Trade-off 4 — Notification mechanism

| Mechanism | Latency | Server cost | Client cost | Battery impact | Best for |
|---|---|---|---|---|---|
| Polling | High (interval-bounded) | High (many requests) | Low | Low | Low-frequency clients |
| Long polling | Low (sub-second on change) | Medium (held connections) | Low | Low | Moderate-frequency |
| SSE | Low | Medium | Low | Low | One-way streaming |
| WebSockets | Very low | Higher (stateful) | Higher (keepalive) | Higher | Real-time co-editing |
| Push (APNs/FCM) | Low | Low (vendor handles fan-out) | Low | Vendor-dependent | Mobile |

### Trade-off 5 — Sync model

| Model | Consistency | Conflict behavior | Best for |
|---|---|---|---|
| Strong (read-after-write, single-master) | Strong | Rare, simple | Single-device workloads |
| Eventually consistent with last-write-wins | Eventual | Lost writes possible | Simple file sync |
| Eventually consistent with copy-on-conflict | Eventual | Conflicted copy surfaced | Most file sync |
| CRDT-based | Strong (semantic) | Automatic merge | Collaborative editing |

---

## Real-World Case Studies

### Case Study 1 — Dropbox's block magic

Dropbox's 2016 announcement of "Magic Pocket" — their custom-built exabyte-scale storage infrastructure — is the canonical case study for this chapter:

- **Block size**: 4 MB, with content-defined chunking using a rolling hash (similar to rsync). A change in the middle of a file invalidates only a few blocks, not the whole file.
- **Sharding**: blocks hashed (SHA-256) and stored in a custom storage system; the block hash is the address.
- **Dedup**: blocks deduplicated across all users; the 4 MB granularity gives >30% dedup in practice.
- **Erasure coding**: Reed-Solomon (6,3) — 6 data + 3 parity fragments, distributed across 9 failure domains.
- **Migration**: in 2016, Dropbox migrated ~90% of user data from AWS S3 to Magic Pocket, claiming significant cost savings and durability improvements.

The interview-relevant insight: **the chapter's design is the textbook description of what Dropbox built**, with the addition of:
- Content-defined chunking (CDC) for better dedup than fixed-size chunks
- Reed-Solomon erasure coding (not 3× replication) for storage efficiency at scale
- Custom hardware and storage nodes rather than commodity S3

### Case Study 2 — Google Drive sync

Google Drive's sync has a few distinctive properties:

- **Files are stored in Google Colossus** (Google's GFS successor) with similar properties to Magic Pocket.
- **Sync protocol** uses a proprietary binary RPC over HTTP/2; the open-source `drive` CLI tools and `rclone` have documented enough of it that the broad strokes are public.
- **Real-time collaboration** in Google Docs, Sheets, Slides is built on a separate stack (OT-based, now migrating to CRDTs) that handles fine-grained edit merging.
- **OCR and content indexing** run on uploaded files asynchronously; search results reflect OCR'd content within minutes.

The interview-relevant point: Google separates **file storage** (Drive) from **live collaboration** (Docs), and each has a different architecture.

### Case Study 3 — OneDrive's differential sync

Microsoft's OneDrive (formerly SkyDrive) has had multiple sync architectures; the current "OneDrive sync app" (replacing the older Groove/OneDrive client):

- Uses **differential sync** at the block level (similar to rsync); only changed blocks are transferred.
- Stores data in **Azure Blob Storage** with **zone-redundant storage** (3 AZs in a region) and **geo-redundant storage** (cross-region replication) for higher durability tiers.
- The client uses **Windows Push Notification Service (WNS)** for push notifications to wake up sync clients on change.
- Files are organized in **personal vault** (encrypted, requires 2FA) vs. **standard** storage tiers.

OneDrive is a useful counter-example to Dropbox's Magic Pocket: OneDrive is built on top of Azure blob primitives, not custom hardware, and still achieves the same user-facing properties (delta sync, version history).

### Case Study 4 — iCloud (and the iCloud Drive split)

Apple's iCloud has gone through several architectures:

- The original iCloud (2011) was largely a relabel of MobileMe / me.com; storage was on AWS and Azure.
- The 2018-2022 "iCloud Drive" split introduced a **per-app storage model** with third-party apps getting their own sandboxed container.
- **Advanced Data Protection** (2022) added end-to-end encryption for most data categories (except iCloud Mail, Contacts, Calendar due to interoperability).

iCloud is the canonical example of **per-app storage containers** with strong sandbox isolation. The interview angle is privacy and compliance rather than scale.

### Case Study 5 — Box sync engine

Box (enterprise-focused) has several distinctive features:

- **Heavy compliance** (HIPAA, FedRAMP, GxP) — their sync is designed for regulated industries.
- **Per-tenant encryption** keys, with key rotation on demand.
- **Version history** retained for 7 years by default for enterprise customers.
- **"Box Drive"** is the modern sync client; it streams files on demand rather than syncing everything locally — a different model than Dropbox.

The Box model is "sync on demand" (similar to OneDrive Files On-Demand, macOS File Provider) rather than "sync everything" — this avoids the offline-storage problem for large enterprise accounts.

### Case Study 6 — Conflict resolution: CRDTs vs OT

Two dominant approaches for collaborative editing (relevant if you expand the chapter to "Google Docs-style" real-time co-editing):

**Operational Transform (OT)** — pioneered by Google Docs:
- Every edit is an operation (insert, delete, retain).
- Server transforms incoming ops against the current state to maintain convergence.
- Requires a **central server** to canonicalize the order of operations.
- Mature, well-tested at Google scale.
- Trade-off: server is single point of failure / coordination; client logic is complex.

**Conflict-free Replicated Data Types (CRDTs)**:
- Data structures designed so concurrent edits always converge without coordination.
- Two main families: **state-based** (CvRDTs, merge via join-semilattice) and **operation-based** (CmRDTs, broadcast via causal delivery).
- Examples: Yjs (JS), Automerge (JS/Rust), Delta CRDT (Rust).
- Trade-off: data structures are non-trivial; some operations (counters, sets) are easy, others (rich text, JSON trees) are subtle.
- Can work **peer-to-peer** with no central server.

In 2022, Google announced that Google Docs was migrating from OT to a CRDT-based architecture, citing lower infrastructure complexity and offline support. This is the most public OT-to-CRDT migration at hyperscale.

---

## Common Pitfalls & Failure Modes

### Pitfall 1 — Chunk hash collisions

SHA-256 collisions are not practically attackable, but if the system uses **MD5 or SHA-1** for block hashing (some legacy systems do), collision risk becomes real. With 10^11 blocks, the birthday paradox gives a collision probability around 10^-10 for SHA-1 — too low to ignore for global storage. **Mitigation**: use SHA-256 (or stronger) for block addressing.

### Pitfall 2 — Reference leak in dedup

If the same block is referenced by 100 users, deleting one user's file must **decrement** the reference count, not delete the block. If the system deletes the block immediately, the other 99 users lose data. **Mitigation**: reference-counted blocks, or "tombstone with TTL" before actual deletion.

### Pitfall 3 — Metadata DB hotspot on a power user

A user with 100M files (heavy camera roll sync, for example) hammers the metadata shard that holds their data. **Mitigation**: split that user's metadata across multiple shards by file-id range, not by user-id; or apply per-user rate limits.

### Pitfall 4 — Sync loops on misbehaving clients

A bug in the client that re-uploads the same block repeatedly can saturate the upload pipeline. **Mitigation**: client-side deduplication, server-side upload idempotency keys, and per-client rate limits.

### Pitfall 5 — Quota exhaustion attack

If quotas are computed against logical storage, a user can upload 1 TB of duplicate content and not see the dedup benefit. Conversely, if quotas are computed against post-dedup, a malicious user could exploit dedup accounting bugs. **Mitigation**: charge users against **logical** storage (the size they uploaded), not physical storage.

### Pitfall 6 — Version history unbounded growth

Every edit creates a new version. Without caps, a heavily edited file balloons to thousands of versions. **Mitigation**: per-file version count cap (e.g., 100), TTL on old versions, and "major version" pinning.

### Pitfall 7 — Notification storm

A user editing 100 files rapidly generates 100 notification events; clients re-poll for each. **Mitigation**: **batched notifications** (deliver every N seconds or every M changes, whichever first), with a debounce window at the server.

### Pitfall 8 — Privacy leak via pre-signed URLs

A pre-signed URL grants bearer-token access. If leaked, anyone with the URL can download the file until expiry. **Mitigation**: short TTLs (5-15 min), IP-binding for sensitive content, audit logs on URL issuance.

### Pitfall 9 — Cross-device race during a sync

User opens the file on phone, edits, saves. Laptop was about to download the same file based on a stale cursor. **Mitigation**: server-side monotonic version numbers, conditional writes (CAS) on the client, and a "stale cursor" check that forces re-fetch.

---

## Interview Q&A

**Q1 — How do you keep two devices in sync when the network is unreliable?**

A: Three layers. (1) **Local queue**: the client persists pending changes in a local log; sync resumes on reconnect. (2) **Server-side offline queue**: for cross-device sync, the server holds pending updates for offline devices and delivers them on reconnect (the chapter's offline backup queue). (3) **Idempotent operations**: each sync operation carries a client-generated ID; the server dedups retries so re-sending a queued operation is safe. The interview should mention that **the metadata cursor** is the linchpin: it's a high-water-mark timestamp that lets the client ask "what changed since X?" without trusting local clocks.

**Q2 — How do you handle two devices editing the same file at the same time?**

A: Depends on the file type. (1) **Generic files**: copy-on-conflict. The second writer wins; the first writer's version is preserved as "filename (Device A's conflicted copy, date)." The user manually merges. (2) **Text files**: 3-way merge via the user's text editor; this is how Dropbox and Google Drive handle .txt/.md. (3) **Collaborative documents**: OT or CRDT-based real-time merging (Google Docs). The interview answer should describe the **trade-off**: copy-on-conflict is simple but loses work; CRDTs preserve work but require application support; OT is mature but server-centralized.

**Q3 — How would you handle a 50 GB file upload?**

A: Resumable upload with chunking. (1) The client requests a session via `POST /files/init` with file metadata. (2) The server returns a session ID and chunk size (e.g., 8 MB). (3) The client chunks the file locally, computes SHA-256 per chunk, and uploads chunks in parallel with the session ID + chunk index. (4) Each chunk is ACKed independently; failed chunks retry. (5) On completion, the server returns the file's block list and the client confirms. Resumption after disconnect: the client asks `GET /files/init/{session_id}/status` and resumes only the missing chunks. For a 50 GB file at 8 MB chunks, that's 6,400 chunks — parallelism of 10 reduces upload time to ~1 hour on a 100 Mbps link.

**Q4 — How do you deduplicate across users?**

A: Two-layer approach. (1) **Content-addressed storage**: blocks are addressed by their SHA-256 hash. The upload flow is "compute hash → check if hash exists in storage → if yes, just record metadata referencing existing block; if no, upload." (2) **Privacy-preserving dedup**: for sensitive content, encrypt-then-hash or use **convergent encryption** (the hash is derived from the plaintext, but the block is encrypted with a key derived from the hash; identical plaintext yields identical ciphertext and identical hash). The security trade-off is the "confirmation of a file" attack — a malicious user can test whether another user has a specific file by trying to upload a known hash. Dropbox and Google Drive have both addressed this with **per-user encryption keys** layered over content addressing.

**Q5 — How do you scale to a billion users?**

A: Three pillars. (1) **Sharding the metadata DB**: by user-id range, with cross-shard queries resolved at the API tier. Spanner/CockroachDB-style globally distributed transactions become necessary; alternatively, per-shard transactions with eventual cross-shard consistency. (2) **Tiered storage**: hot blocks in S3 standard, warm blocks in S3 IA, cold blocks in Glacier; the dedup index routes reads to the right tier. (3) **CDN for downloads**: most user reads are repeated reads (re-opening a file), so a CDN with appropriate TTLs absorbs the bulk of the read load. At this scale, **deduplication savings alone pay for the engineering team**.

**Q6 — How do you make this GDPR-compliant?**

A: GDPR gives users the right to erasure ("right to be forgotten"). The problem: with dedup, deleting one user's data may not delete the underlying block (other users reference it). Approaches: (1) **Per-user encryption keys** with key deletion on user erasure (cryptographic erasure). (2) **Reference-counted blocks** with copy-on-conflict semantics: deleting a user leaves the block in place if other references exist, but the user's plaintext copy is destroyed via key deletion. (3) **Audit trail**: every access is logged; users can request a copy of their access history. Most production systems combine (1) and (2) for "true" erasure.

**Q7 — How would you redesign for 10× the upload volume?**

A: Layered answer. (1) **Regional ingest POPs**: instead of one global upload endpoint, accept uploads at regional POPs and replicate to the home region in the background. (2) **Streaming chunked upload with backpressure**: don't buffer full files; stream chunks into the storage tier as they arrive. (3) **Client-side dedup**: compute hashes on the client; skip blocks that already exist. (4) **Parallel uploads**: 10-20 concurrent chunks per file. (5) **Asynchronous metadata commit**: the metadata DB is the bottleneck; commit only after the full file is durable, not after each chunk. The dominant scaling axis is **storage bandwidth**, not API QPS.

---

## Glossary

| Term | Definition | Common misconception |
|---|---|---|
| Block / chunk | A contiguous piece of a file used for delta sync | "Block = file" — blocks compose files; a file is an ordered list of blocks |
| Content-defined chunking (CDC) | Block boundaries determined by content (rolling hash), not fixed offsets | "CDC always gives same boundaries" — small changes can shift boundaries |
| Delta sync | Transferring only changed blocks rather than the whole file | "Delta sync = rsync" — rsync is one implementation; the protocol varies |
| Content-addressed storage | Storage where the address is a hash of the content | "CAS = dedup" — CAS enables dedup but the two are distinct concepts |
| Erasure coding | Reed-Solomon or similar: split data into data + parity fragments | "Erasure coding = compression" — EC is for redundancy, not compression |
| Replication factor | Number of copies maintained per object | "Replication factor 3 = 3× storage" — usually yes, plus any parity |
| Deduplication | Storing identical blocks only once across the corpus | "Dedup saves 50%" — varies wildly by content type; backups dedup better than user files |
| Pre-signed URL | Time-limited URL granting direct blob access | "Pre-signed = public" — bearer token; treat as secret |
| ACID | Atomicity, Consistency, Isolation, Durability — database transaction guarantees | "ACID = slow" — modern distributed systems (Spanner, CockroachDB) achieve ACID at scale |
| BASE | Basically Available, Soft state, Eventual consistency | Often confused with CAP's "A" — BASE is a design philosophy, not a theorem |
| CAS (compare-and-swap) | Atomic operation: update only if value matches expected | "CAS = optimistic locking" — CAS is the primitive; optimistic locking is one pattern |
| Vector clock | Logical clock for tracking causality in distributed systems | "Vector clock = timestamp" — vector clocks capture ordering, not wall time |
| CRDT | Conflict-free Replicated Data Type; converges without coordination | "CRDTs solve all conflicts" — only for data types that fit the model |
| OT (Operational Transform) | Algorithm for real-time collaborative editing | "OT = CRDT" — OT requires a central server; CRDTs can run peer-to-peer |
| WNS / FCM / APNs | Microsoft / Google / Apple push notification services | "Push notifications = push" — push notification delivery is throttled by the OS |
| Long polling | HTTP request held open until the server has data to send | "Long polling = WebSocket" — both reduce latency vs. polling; long polling is HTTP-based |
| Idempotency key | Client-generated ID that makes a request safely retryable | "Idempotent = same result" — idempotent means **safe to repeat**, not necessarily identical |
| Reconciliation | Process of bringing two replicas to the same state | "Reconciliation = sync" — reconciliation is one phase of sync |
| Tombstone | Marker indicating a deleted item; preserved until safe to purge | "Tombstone = deleted" — tombstones linger to handle concurrent deletes |
| Quota | Per-user storage cap | "Quota = storage cost" — quotas are policy; storage cost is paid by the provider |
| Per-file version cap | Maximum number of historical versions retained | Often confused with file size cap; distinct concern |
| Cross-device cursor | Per-device high-water-mark for "what version do I have?" | "Cursor = timestamp" — usually a server-assigned monotonic version, not a wall-clock time |