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
