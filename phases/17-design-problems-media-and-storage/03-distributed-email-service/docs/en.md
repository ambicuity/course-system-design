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
- Deduplicate identical attachments by content hash to save space.

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
