# Distributed Email Service

## Background: Email Protocols

- **SMTP (Simple Mail Transfer Protocol):** the standard for **sending** mail from one server to another.
- **POP (Post Office Protocol):** downloads email to a single device and typically removes it from the server. No good multi-device support.
- **IMAP (Internet Message Access Protocol):** standard for a mail client **retrieving** mail; the message stays on the server and syncs across multiple devices. Preferred for modern multi-device use.
- **HTTPS:** not strictly a mail protocol, but commonly used by webmail clients to talk to their own mail servers (e.g., Gmail's web interface).
- **DNS / MX records:** a sending server looks up the recipient domain's **MX (Mail Exchanger)** record to find the destination mail server.

## Step 1: Understand the Problem and Establish Design Scope

### Functional Requirements
- Send and receive emails
- Fetch all emails (folder/label listing)
- Filter emails by read/unread status
- Search emails by subject, sender, and body
- Anti-spam and anti-virus
- Support web and mobile clients

### Non-Functional Requirements
- **Reliability:** do not lose email data
- **Availability:** email + attachments highly available
- **Scalability:** performance does not degrade as users/emails grow
- **Flexibility & extensibility:** room for custom protocols/features

### Scale Estimation
- **1 billion users**
- Outgoing emails QPS ≈ (1B users × ~10 sent/day) / 10^5 sec ≈ **100,000+ QPS**
- Metadata read QPS is much higher (clients poll/list frequently)
- Average email metadata ~50 KB, attachment ~500 KB; storage grows to **petabytes**

---

## Step 2: High-Level Design

### Traditional Mail Server (Single-Server, Won't Scale)
Classic setup: a mail-transfer agent (e.g., Sendmail), local storage (mbox/Maildir files), and POP/IMAP for retrieval. Works only for small user counts. Modern internet-scale email requires a **distributed** design.

### Distributed Architecture Components

**Send path:**
1. **Webmail / mobile clients** → talk over HTTPS/SMTP
2. **Load balancer** distributes traffic
3. **Web servers** (stateless) handle auth, rate limiting, request routing
4. **SMTP outgoing servers / queue** — outgoing emails are placed on a **message queue (outgoing queue)**; SMTP workers send them out
5. **SMTP outgoing workers** look up recipient **MX records** and deliver; handle bounces/retries

**Receive path:**
1. **SMTP incoming servers** accept mail from the outside world
2. Mail processing workers run **spam/virus filtering** and **rules/filters**
3. Accepted mail is written to **storage** and **metadata**, then pushed to clients (via real-time channel) and made retrievable via IMAP/HTTPS

### Core Services
- **Authentication service** — verifies users
- **Web servers** — RESTful (or webmail) front-end for clients
- **Real-time servers** — push new email to connected clients (long polling / WebSocket / SSE)
- **Metadata service** — stores email metadata (subject, sender, recipients, flags, folder/label)
- **Attachment service** — stores attachments in distributed object storage
- **Distributed cache** — caches the most recent emails (hot data) for fast inbox loads
- **Search service** — full-text search over email content
- **Message queues** — decouple incoming/outgoing processing

### Email Sending Flow (numbered)
1. User composes and sends; web server validates and assigns metadata
2. Basic validations (size limits, recipient format)
3. Email handed to the **outgoing queue**
4. If the recipient is on the **same** mail service, write directly to that user's storage (skip external SMTP)
5. Otherwise, an SMTP outgoing worker resolves MX and delivers; on failure it retries with backoff and eventually bounces

### Email Receiving Flow (numbered)
1. SMTP incoming server accepts the connection
2. Worker performs anti-spam / anti-virus, then applies user filter rules
3. Email and attachments written to storage; metadata recorded
4. If the recipient is online, the **real-time server** pushes a notification; otherwise the email waits and the client syncs via IMAP/HTTPS later

---

## Step 3: Design Deep Dive

### Metadata Storage Characteristics
Email metadata has special properties driving the data-store choice:
- **Heavy in number, small in size** — billions of small rows
- Read-heavy with frequent updates (read/unread, labels)
- Strong need for **isolation** between users (one user's data never bleeds into another's)
- Heavy use of **folder/label/conversation** views and ordering by time

### Why a Distributed (NoSQL/Column) Store
A single relational DB cannot hold petabytes of metadata for 1B users. Choose a distributed store. The chapter weighs options and favors a **distributed column-family / NoSQL store** (e.g., a Bigtable/Cassandra/HBase-style system) because:
- Massive horizontal scale and high write throughput
- Natural fit for a **wide-column** model keyed by user
- Tunable consistency

### Metadata Table Design
A common design is to partition by **user_id** so all of a user's mail is co-located:

**Row key:** `user_id`
**Column families:**
- **Inbox / folder index:** columns keyed by `(folder/label, timestamp, email_id)` → enables ordered listing and read/unread filters
- **Email object:** `email_id` → metadata blob (subject, from, to, flags, snippet, attachment refs)

This supports the core queries efficiently:
- List all emails in a folder (range scan over the folder index)
- Filter read/unread (a flag column / secondary index)
- Get a single email's metadata by id

### Attachment Storage
- Attachments are large and immutable → store in **distributed object storage** (S3-like blob store), not in the metadata DB.
- Metadata holds a **reference (pointer/URL)** to each attachment blob.
- Dedup identical attachments by content hash to save space.

### Distributed Object Storage Properties
- Erasure coding / replication for durability
- Attachments are write-once, read-many; cache hot ones at the edge

### Email Deliverability & Anti-Spam
- **Reputation:** sending-IP and domain reputation affect deliverability
- **Authentication standards:** **SPF**, **DKIM**, and **DMARC** verify sender legitimacy and reduce spoofing
- **Spam/virus pipeline** scores inbound mail; rules route to spam folder or reject

### Search
Searching email by subject/sender/body for 1B users is the hardest read-side feature.

**Two approaches discussed:**
1. **Elasticsearch (separate search cluster):**
   - Pros: mature full-text search, ranking, easy to integrate
   - Cons: a second system to operate; keeping it in sync with the metadata store; very high write/index volume; large cost at email scale
2. **Native/custom search built into the storage layer:**
   - Build inverted indexes co-located with the document store (like Gmail's approach)
   - Pros: single system, consistency, scales with the data store, lower cross-system overhead
   - Cons: much more engineering effort to build and maintain

At billion-user scale, large providers tend to build a **custom search** tightly integrated with storage; Elasticsearch is a reasonable starting point for smaller scale.

### Consistency vs. Availability
- Email favors **availability** and **eventual consistency** for most operations (e.g., a label change can propagate slightly late).
- However, the **same email must not be lost** and must not be shown twice — use idempotent writes keyed by `email_id`.
- Within a single user's mailbox, stronger ordering/consistency is desirable for a coherent inbox view.

### Scaling & Fault Tolerance
- **Stateless web/real-time servers** scale horizontally behind load balancers
- **Metadata store** scales by partitioning on `user_id`; replicate partitions across nodes/zones
- **Message queues** absorb spikes and decouple send/receive workers
- **Caching** of recent emails reduces store load for the common "load my inbox" request
- Replicate across data centers/regions for disaster recovery

---

## Step 4: Wrap Up

### Summary of Key Decisions
- Use **SMTP** to send, **IMAP/HTTPS** to retrieve (multi-device sync via IMAP).
- Decouple send/receive with **message queues**; SMTP workers handle MX lookup, retries, bounces.
- Store **metadata** in a distributed **wide-column/NoSQL** store partitioned by `user_id`.
- Store **attachments** in distributed **object storage**, referenced from metadata.
- Provide **search** via Elasticsearch (smaller scale) or a custom storage-integrated index (hyperscale).
- Enforce **SPF/DKIM/DMARC** and a spam/virus pipeline for deliverability and safety.
- Favor **availability + eventual consistency**, with idempotency to avoid loss/duplication.
- Real-time push for new mail; cache recent emails for fast inbox loads.

### Additional Talking Points
- Mark read/unread, labels/folders, threading (conversations)
- Rate limiting and abuse prevention on the send path
- GDPR/retention/deletion and per-user data isolation
- Cross-region replication for reliability and locality

---

## Deep Enrichment: Distributed Email Service

### Back-of-the-Envelope Math (Detail)

Worked numbers, step by step, for a 1B-user service.

**Step 1 — Outbound mail.**
- 1B users × 10 sent/day = 10B sends/day.
- Average QPS = 10^10 / 86,400 ≈ 115K QPS. Round to **~100K QPS**.
- Peak: 5× average ≈ **~500K QPS** for outbound SMTP workers.

**Step 2 — Inbound mail.**
- Asymmetric: business / spam recipients see ~100× inbound of outbound. Estimate inbound ≈ 50B/day ≈ **~580K QPS** average, multi-million peak for the largest providers.
- Of inbound, the spam pipeline filters >70% at SMTP-time (pre-DATA or during DATA) before the mail ever hits storage.

**Step 3 — Read QPS.**
- Webmail idle poll: ~30s; mobile push tokens reduce polling. Effective read QPS for "new mail arrived?" checks: **~1M QPS** at billion-user scale.
- Inbox listing (folder open): assume each user opens the inbox ~10×/day → **~115K QPS** for inbox renders, cacheable.

**Step 4 — Storage.**
- Metadata per email: ~50 KB (sender, recipients, headers, snippet, body excerpt).
- Attachment average: ~500 KB; long tail of multi-MB attachments.
- Total mail kept: assume 90 days hot, 5 years cold archive.
  - Daily inbound (kept) ≈ 30B × 0.3 = 9B × 50 KB metadata = 450 TB/day metadata.
  - Daily attachments ≈ 5% of mail × 500 KB ≈ 5 × 10^8 × 500 KB = 250 TB/day attachments.
  - 90-day hot: ~62 PB metadata + ~22 PB attachments.
  - 5-year cold: on the order of **exabytes** total.

**Step 5 — Search index.**
- 9B docs/day × ~10 KB indexed each = 90 TB/day of new index data.
- Index size typically 1.5–3× raw text → 100–300 TB/day of new index.

**Step 6 — Cache sizing.**
- Per-user recent-N (last 50 emails metadata): 50 × 50 KB = 2.5 MB.
- 1B users × 2.5 MB = **2.5 PB** for a full cache — infeasible. Mitigate by caching only **active users** (last 30 days): 200M users × 2.5 MB = 500 GB. Comfortable in a Redis cluster.

**Step 7 — SMTP worker fleet.**
- 500K QPS outbound, each SMTP delivery takes ~500 ms (DNS + connection + DATA): 500K × 0.5 = 250K concurrent outbound. Spread across 10K workers = 25 conn/worker. Realistic.

### ASCII Architecture Diagrams

#### 1) Send path (sequence)

```
User        Web App     Auth Svc    Outgoing MQ    SMTP Worker    DNS (MX)   Recipient MX
  |             |            |            |              |             |             |
  | POST /send  |            |            |              |             |             |
  |------------>|            |            |              |             |             |
  |             | validate   |            |              |             |             |
  |             |----------- |-->         |              |             |             |
  |             |<-- 200 OK--|            |              |             |             |
  |             | enqueue(msg, idemp)     |              |             |             |
  |             |------------------------>|              |             |             |
  |             |            |            |  poll        |             |             |
  |             |            |            |------------->|             |             |
  |             |            |            |              | MX lookup   |             |
  |             |            |            |              |------------>|             |
  |             |            |            |              |<-- MX 10 --|             |
  |             |            |            |              | SMTP connect               |
  |             |            |            |              |-------------------------->|
  |             |            |            |              | MAIL FROM / RCPT TO       |
  |             |            |            |              |-------------------------->|
  |             |            |            |              | DATA                      |
  |             |            |            |              |-------------------------->|
  |             |            |            |              | 250 OK                    |
  |             |            |            |              |<--------------------------|
  |             |            |            |              | ack -> remove from queue  |
  |             |            |            |              |----->                      |
  |<-- 200 OK---|            |            |              |             |             |
```

Internal recipient shortcut (same service):
```
Web App -> Outgoing MQ -> Recipient Svc (write to recipient's metadata + storage)
        (skip external SMTP)
```

#### 2) Receive path (sequence)

```
External MX  SMTP In   Spam/Virus  Filter Rules  Storage  Metadata  Real-Time  Client
    |          Worker     Pipeline        |         |          |         |          |
    | connect  |            |             |         |          |         |          |
    |--------->|            |             |         |          |         |          |
    |          | HELO/EHLO  |             |         |          |         |          |
    |          |<---------->|             |         |          |         |          |
    |          | MAIL FROM  |             |         |          |         |          |
    |          |<---------->|             |         |          |         |          |
    |          | DATA       |             |         |          |         |          |
    |          |<---------->|             |         |          |         |          |
    |          | submit     |             |         |          |         |          |
    |          |----------->|             |         |          |         |          |
    |          |            | RBL/DNSBL   |         |          |         |          |
    |          |            | SPF/DKIM/DMARC       |          |         |          |
    |          |            | content scan         |          |         |          |
    |          |            | Bayes/SpamAssassin   |          |         |          |
    |          |            | reject or accept     |         |          |         |          |
    |          |            |-------------->       |         |          |         |          |
    |          |            |            | apply user rules  |          |         |          |
    |          |            |            |-------->|         |          |         |          |
    |          |            |            |         | write obj|          |         |          |
    |          |            |            |         |-------->|          |         |          |
    |          |            |            |         | metadata|          |         |          |
    |          |            |            |         |------------------> |         |          |
    |          |            |            |         |          | push   |          |          |
    |          |            |            |         |          |----------------->|          |
    |          |            |            |         |          |         |  notify          |
    |<-- 250 --|            |             |         |          |         |          |
    |          |            |             |         |          |         |          |
```

#### 3) Metadata storage layout (Cassandra-style)

```
Partition key: user_id
Within partition, clustering keys:

  InboxIdx:  (folder, ts_ms desc, email_id)  -> flags(read, starred, label_ids…)
  EmailObj:  email_id                       -> {subject, from, to, snippet, att_refs[], size}
  FolderIdx: (folder, conversation_id, ts)  -> email_id
  LabelIdx:  (label_id, ts_ms desc, email_id) -> 1

A single user mailbox = one partition row (replicated 3x).
Cassandra stores these as wide-column rows; range scans are over the clustering keys.
```

### Trade-off Tables

#### 1) Metadata store choice

| Store | Read pattern fit | Write throughput | Operational cost | Per-user isolation | Notes |
|--------|------------------|------------------|------------------|---------------------|-------|
| Cassandra | Excellent (wide-column, range scan) | Very high | Medium | Native partition | Industry default |
| HBase | Excellent | Very high | High (ZooKeeper, HDFS) | Native partition | Used at older hyperscalers |
| ScyllaDB | Excellent | Higher than Cassandra | Lower than Cassandra | Native partition | C++ rewrite, lower tail latency |
| Bigtable | Excellent | Very high | Low (managed) | Native partition | Google internal + GCP |
| DynamoDB | Good (single-partition range scans ok) | High | Pay-per-request | Partition key | Easy, but hot partition pricing risk |
| Postgres (sharded) | Good | Medium | Low–medium | Manual | Single-DB simplicity; scale ceiling |
| MongoDB | Good (rich indexing) | Medium-high | Medium | Shard key | Doc-model fits metadata |

#### 2) Search architecture

| Approach | Latency | Index freshness | Operational cost | Engineering cost | Best fit |
|----------|---------|------------------|------------------|-------------------|----------|
| Elasticsearch (separate) | ~100 ms | Seconds | Medium-high | Low | Small/medium scale |
| Self-hosted Solr | ~100 ms | Seconds | Medium-high | Medium | Open-source shops |
| Custom storage-integrated | ~50 ms | Real-time | Lower per query at scale | Very high | Hyperscale (Gmail-style) |
| OpenSearch (managed) | ~100 ms | Seconds | Medium | Low | AWS-native |
| Typesense / Meilisearch | ~50 ms | Seconds | Low | Low | Smaller scale, simpler |

#### 3) Deliverability & security

| Mechanism | What it stops | Failure mode | Operational cost |
|-----------|---------------|--------------|-------------------|
| SPF | Sender-IP spoofing | Forwarders break SPF | Low (DNS record) |
| DKIM | Body tampering, header spoofing | Key rotation, replay | Medium (signing infra + DNS) |
| DMARC | Aligns SPF/DKIM, reporting | Policy misconfig drops legit mail | Medium (reporting + alignment) |
| SpamAssassin / rspamd | Spam content scoring | Rules go stale; new bypasses | Medium |
| RBL/DNSBL | Known-bad senders | False positives | Low |
| TLS (SMTP+IMAP) | On-wire eavesdropping | Misconfigured certs | Low–medium |
| ARC | Forwarded mail authentication | Complex, niche | Medium |

#### 4) Real-time push

| Mechanism | Latency | Battery impact | Connection cost | Best fit |
|-----------|---------|----------------|------------------|----------|
| WebSocket | Sub-second | Low (idle) | Medium | Webmail |
| Server-Sent Events (SSE) | Sub-second | Low (idle) | Low | Webmail (one-way) |
| Long polling | 1–30 s | Medium | Medium | Legacy clients |
| Push (APNs/FCM) | Sub-second | Very low | Very low | Mobile |
| Idle polling | 30–60 s | Medium | High | Fallback |

### Real-World Case Studies

#### 1) Gmail (Google)
Gmail runs on Google's internal stack: **GFS / Colossus** for attachment storage, **Bigtable** for per-user metadata (one Bigtable row per user with column families for folders, conversations, and message data), **Google Search appliances** for full-text indexing, and a custom spam pipeline. Gmail's "search, don't sort" philosophy drives the search-integrated storage. Public talks (Jeff Dean, 2009; more recent Velocity conferences) describe durability via replication across data centers and consistent hashing for mail storage. (Sources: Dean & Ghemawat, "MapReduce", OSDI 2004; Google AI Blog; High Scalability posts.)

#### 2) Microsoft Exchange / Outlook.com
Exchange historically used **Extensible Storage Engine (ESE/ISAM)** for mailbox stores. Outlook.com's migration to cloud ("Project Titan", ~2015) moved mailboxes to a distributed store backed by **Azure Cosmos DB** and Azure Blob Storage. The cloud migration is a textbook example of migrating a deeply stateful, IMAP-coupled protocol stack to a multi-tenant cloud-native architecture while preserving IMAP and POP interop. (Sources: Microsoft Mechanics, Exchange Team blog posts.)

#### 3) SendGrid (Twilio)
SendGrid pioneered **APIs as a delivery service** — `POST /v3/mail/send` with a JSON body — and ran the largest non-Google outbound mail platform for years. Architecture emphasizes **IP reputation isolation per sender**, **dedicated sending IPs**, **suppression lists**, and **event webhooks** for delivery/bounce/spam reports. After Twilio acquisition, SendGrid continues to operate as a managed SMTP relay with strong deliverability tooling. (Sources: SendGrid docs, Twilio blog.)

#### 4) Mailgun (Sinch / Pathwire)
Mailgun is a developer-focused transactional email API. Internally it routes mail through **Mailgun MTA** (Postfix-derived) with custom milter pipelines for spam scanning, DKIM signing, and bounce classification. The platform surfaces per-domain analytics (opens, clicks, bounces) via a Kafka-driven event pipeline. (Sources: Mailgun engineering blog.)

#### 5) Postmark
Postmark distinguishes **transactional** vs. **broadcast** streams and uses **dedicated transactional IPs** with strict reputation policing to ensure deliverability for password-reset and 2FA emails. They publish detailed deliverability blog posts on **DMARC alignment**, **BIMI**, and **List-Unsubscribe** headers. (Sources: Postmark blog, ActiveCampaign engineering.)

#### 6) AWS SES
SES is AWS's SMTP relay / API service. It runs a multi-tenant MTA pool with **sending IP reputation** tracked per-account, a managed suppression list, and **configuration sets** that emit events (delivery, bounce, complaint, reject) to SNS/Kinesis/Firehose. SES sits behind a **sandbox** mode for new senders to prevent abuse. (Sources: AWS docs.)

#### 7) Postfix / Exim (MTA internals)
Postfix is a queue-and-daemon MTA architecture (qmgr, smtpd, cleanup, local, virtual) with separate processes for queue management, SMTP acceptance, content filtering, and delivery. Exim uses a single daemon with routing driven by **filter rules** and **string expansion**. Reading Postfix source is the canonical way to understand SMTP queue backpressure, retry policies, and bounce handling. (Sources: Postfix documentation; "The Book of Postfix".)

#### 8) SpamAssassin / rspamd
SpamAssassin is a Perl-based rule scorer with Bayesian classification; **rspamd** is a modern C/Lua alternative used by Fastmail and others. Both integrate with Postfix via **milter** protocol and combine header checks, body checks, RBLs, and reputation data. The industry has broadly moved from "score + threshold" to **reputation-driven** (SenderScore, Cisco Talos) with ML scoring on top. (Sources: Apache SpamAssassin docs, rspamd.com.)

#### 9) DKIM / SPF / DMARC / ARC
- **SPF** (RFC 7208): DNS TXT record listing authorized sending IPs.
- **DKIM** (RFC 6376): asymmetric signature over signed headers; public key in DNS.
- **DMARC** (RFC 7489): alignment policy (none/quarantine/reject) over SPF and DKIM, with reporting (RUA/RUF).
- **ARC** (RFC 8617): authenticated relay chain for forwarded mail (mailing lists, Gmail "send as").
- **BIMI** (RFC Proposed): brand logo in inbox; relies on DMARC.
Adoption accelerated after 2023 when Gmail and Yahoo began **requiring DMARC + SPF/DKIM alignment** for bulk senders. (Sources: M3AAWG; Gmail Sender Guidelines 2023/2024.)

#### 10) Spamhaus
Spamhaus Project maintains DNS-based blocklists (SBL, XBL, PBL, DBL) that most mail servers query in real time to reject known-spammy sources. Inclusion in SBL is reputational damage; delisting requires documented remediation.

### Common Pitfalls & Failure Modes

#### 1) Bounce loop / mail loop
**Scenario:** A vacation auto-responder replies to a bounce notification, which triggers another bounce, ad infinitum. Mail queue fills, disk exhausts.
**Mitigation:** detect loops via the `Auto-Submitted` header (RFC 3834) and silently drop; cap auto-response frequency per sender-recipient pair; use **VERP** (variable envelope return path) to identify the loop.

#### 2) SMTP TLS downgrade
**Scenario:** A misconfigured destination advertises `STARTTLS` but only supports weak ciphers; an attacker forces downgrade and reads mail in clear.
**Mitigation:** require **MTA-STS** (RFC 8461) and **TLSRPT** for enforced TLS; monitor reports; set minimum TLS 1.2 with modern cipher suites.

#### 3) Backscatter
**Scenario:** Spammers forge `From` addresses; your server sends bounces to victims. Victims receive spam.
**Mitigation:** never bounce on RCPT-time rejects (`550` instead of `bounce`); verify `From` against authenticated credentials; use a **VERP** envelope sender to identify legitimate bounces.

#### 4) Idempotency gap on retries
**Scenario:** Webmail POST `/send` is retried by the mobile app. Server creates two outgoing queue entries; recipient receives duplicates.
**Mitigation:** require an `Idempotency-Key` header; store `(user_id, idempotency_key)` with a TTL of 24h; return the prior result on retry.

#### 5) Search index falls behind
**Scenario:** A new mail is stored in metadata but not in the search index (write to one failed). User can't find an email they know exists.
**Mitigation:** dual-write to metadata + outbox table; indexer consumes outbox; backfill job reconciles drift. Use **change data capture** from metadata to indexer to avoid app-level dual-writes.

#### 6) DMARC quarantine traps legit mail
**Scenario:** An admin sets `p=quarantine` while a 3rd-party ESP still sends mail but isn't yet DKIM-aligned. Legitimate mail goes to spam.
**Mitigation:** start with `p=none`; analyze DMARC reports for 30 days; only then move to `quarantine` then `reject`. Maintain a controlled-rollout change management process.

#### 7) User data leak across users
**Scenario:** A bug in the partition router routes user A's metadata query to user B's partition. User A sees user B's mail. P0 incident.
**Mitigation:** unit-test partition router against fuzz inputs; assert that `partition(user_id) != partition(user_id')` implies `user_id != user_id'`; add a read-time authorization check that compares the requesting user's token to the queried `user_id`.

#### 8) Spam false positives cost users
**Scenario:** A spam rule update starts flagging legitimate transactional email (receipts, shipping confirmations). Users miss orders.
**Mitigation:** A/B test rule changes against a held-out corpus; require human review of false-positive impact; maintain a per-user "this is not spam" override.

#### 9) Attachment virus scanning pipeline is single-threaded
**Scenario:** All inbound attachments go through one ClamAV scanner instance. A 100 MB attachment blocks the queue.
**Mitigation:** scanner pool with bounded concurrency; stream-scan without buffering entire file; reject oversized attachments early; sandbox scanning in an isolated VM for high-risk file types.

#### 10) Time-bombed mailbox growth
**Scenario:** User mailbox grows to 50 GB over years; index lookups slow; backup windows blow out.
**Mitigation:** per-user quotas with warning thresholds; archive-and-trash rules; lazy compaction of soft-deleted rows; retention policy based on folder type (Trash 30 days, Spam 7 days, etc.).

### Interview Q&A

**Q1 — Clarifications.**
Sketch: 1B users vs. 10M (very different infra choices)? Inbound:outbound ratio (transactional vs. mailbox service)? SLA on delivery latency (seconds for transactional, minutes for marketing)? Compliance requirements (GDPR, HIPAA, data residency)? Search depth (full-text body vs. metadata-only)? Mobile vs. web traffic split (drives real-time push design)?

**Q2 — Capacity estimation.**
Sketch: 1B users, ~10 sends/day/user → 10B sends/day → ~115K QPS outbound, 500K peak. Inbound 5–10× outbound. Storage: 90-day hot = ~84 PB metadata+attachments; 5-year cold = exabytes. Search index ~100–300 TB/day of new index data. SMTP worker fleet ~10K for outbound. Cache 200M active users × 2.5 MB = 500 GB.

**Q3 — Why a wide-column store for metadata?**
Sketch: per-user mailbox is naturally a wide row: many small entries (emails) keyed by timestamp; range scans for "list inbox" are cheap; updates are localized; partition by user_id gives natural isolation. A relational DB at 1B users hits operational limits; document stores index overhead per doc; wide-column gives both scale and natural access pattern.

**Q4 — Search at scale: Elasticsearch vs. custom?**
Sketch: at <100M users, **Elasticsearch** is the right answer — mature, integrates, ~100 ms latency, ops overhead manageable. At 1B+, the cost of indexing 9B docs/day and the latency of cross-cluster queries argue for **storage-integrated search** (Bigtable + custom index, like Gmail). The trade-off is engineering effort vs. ops cost.

**Q5 — Exactly-once vs. at-least-once.**
Sketch: emails are **idempotent by content hash + recipient tuple**. Store `message_id` on first write; reject duplicates by `(message_id, recipient)`. The receiving client may still see duplicates if a retry succeeded but the ack was lost — clients de-duplicate by `Message-ID` header.

**Q6 — Real-time push design.**
Sketch: persistent WebSocket per web client (idle cost is negligible); mobile uses FCM/APNs; fallback to IMAP IDLE for legacy clients. Server holds an in-memory map `user_id -> [connection]`; on new mail, push to each connection. If a user has 5 devices, fan out 5 messages; clients de-duplicate by `message_id`.

**Q7 — "What if we 10×?"**
Sketch: SMTP worker fleet scales linearly with outbound QPS; partition metadata by `hash(user_id)` to add shards; add regions. Cache compresses metadata blobs; consider per-user mailbox compaction (combine small mail into a single object blob) to reduce metadata row count. Move cold attachments to cheaper storage tier with lifecycle policies.

**Q8 — "What if we go global?"**
Sketch: region-local mail storage (data residency); global routing layer resolves `user_id -> home region`. Cross-region read (e.g., user travels) uses read replicas or a low-latency cache. MX records geo-locate inbound; spam pipeline runs per region. Watch for **GDPR cross-border transfer** — keep EU users' data in EU region.

**Q9 — Anti-spam pipeline order.**
Sketch: connection-time RBL/DNSBL (cheap reject); HELO/EHLO hostname checks; SPF/DKIM/DMARC alignment; size limits; spam score (rspamd/SpamAssassin); user filter rules; quarantine vs. accept. Order matters: do cheap network checks first so a million inbound bots don't cost CPU.

**Q10 — How do you handle a user reporting spam from your platform?**
Sketch: every email gets a `List-Unsubscribe` header (RFC 8058 one-click) — users can opt out without your UI. Feed complaints (FBL — feedback loop) from major receivers (Yahoo, Outlook, Comcast) into a **reputation system** that throttles or suspends senders. Maintain suppression list with hash of `(email, sender)` to prevent re-add.

### Key Terms / Glossary

| Term | Precise definition | Common misconception |
|------|---------------------|----------------------|
| **MTA** | Mail Transfer Agent — server that sends/receives SMTP. Postfix, Exim, Sendmail. | Confusing MTA with MDA (delivery agent) or MUA (client). |
| **MDA** | Mail Delivery Agent — final delivery to mailbox. procmail, dovecot LDA. | Often merged with MTA in modern stacks. |
| **MUA** | Mail User Agent — the client. Outlook, Apple Mail, webmail. | A modern webmail is its own IMAP server. |
| **MX record** | DNS record type that maps a domain to one or more mail servers. | Lower preference value = higher priority; not all DNS providers sort correctly. |
| **SPF** | Sender Policy Framework — DNS TXT record listing IPs allowed to send mail for a domain. | SPF breaks when mail is forwarded; use DKIM + DMARC alignment to compensate. |
| **DKIM** | DomainKeys Identified Mail — asymmetric signature over headers; key in DNS. | DKIM does not authenticate the envelope sender (MAIL FROM), only the signed headers. |
| **DMARC** | Policy + reporting on top of SPF/DKIM alignment. | `p=reject` without verified alignment breaks legitimate third-party senders. |
| **ARC** | Authenticated Received Chain — preserves auth results across forwarding. | Solves the "mailing list breaks SPF" problem; adoption is uneven. |
| **IMAP IDLE** | Server pushes a notification when a mailbox changes; client doesn't need to poll. | Not all IMAP servers support IDLE; some only support it on a single connection. |
| **Maildir vs. mbox** | Maildir = one file per message; mbox = one file per folder. | mbox corruption loses the whole folder; Maildir is the modern default. |
| **Backscatter** | Bounces sent to forged From addresses, victimizing innocent third parties. | Bounces should be sent only to authenticated senders, never to envelope From. |
| **Bounce vs. DSN** | DSN (Delivery Status Notification) is the standardized bounce format. | Custom bounce formats break threading; prefer DSN per RFC 3461. |
| **BIMI** | Brand Indicators for Message Identification — verified brand logo in inbox. | Requires DMARC enforcement; logos must be VMC-signed. |
| **List-Unsubscribe** | Header for one-click unsubscribe (RFC 8058). | Required by Gmail/Yahoo for bulk senders (2024+). |
| **FBL** | Feedback Loop — complaint feed from receivers back to senders. | Major receivers (Yahoo, Outlook) provide FBL; not all do. |
| **Suppression list** | List of addresses that should never receive mail (bounced, complained, unsubscribed). | Suppression must be **global across sender accounts** to prevent re-add. |