# Design A Chat System

## Overview
This chapter explores designing a chat system supporting 50 million daily active users with features including one-on-one messaging, group chat (max 100 people), online presence indicators, multi-device support, and push notifications.

---

## Step 1: Understand the Problem and Establish Design Scope

### Key Clarification Questions

**Chat Type & Scale:**
- Support both one-on-one and group-based messaging
- Support mobile and web applications
- Target: 50 million daily active users
- Maximum group size: 100 people

**Features:**
- One-on-one chat with low delivery latency
- Small group chat capability
- Online presence indicators
- Multiple device support (same account logged in simultaneously)
- Push notifications
- Text messages only (no attachments)
- Message size limit: less than 100,000 characters
- Chat history storage: permanent

**Non-Requirements (for now):**
- End-to-end encryption (optional for future)

---

## Step 2: Propose High-Level Design and Get Buy-In

### Fundamental Operations

The chat service must:
1. Receive messages from clients
2. Identify and route messages to correct recipients
3. Store messages on server for offline recipients until they reconnect

### Client-Server Communication Model

Clients connect to a centralized chat service rather than communicating directly with each other. The service handles storage and message relay.

### Network Protocol Selection

#### Polling
- Client periodically asks server for new messages
- Highly inefficient due to constant unnecessary requests
- Wastes server resources answering negative responses

#### Long Polling
- Client holds connection open until messages arrive or timeout occurs
- **Drawbacks:**
  - Sender and receiver may connect to different servers; HTTP-based servers are typically stateless
  - Difficult for server to detect disconnected clients
  - Inefficient for inactive users (still generates periodic timeout-based reconnections)

#### WebSocket (Selected Approach)
- Bidirectional, persistent connection initiated by client
- Begins as HTTP connection, upgraded via handshake
- Works through firewalls (uses port 80/443)
- Server can push updates to client asynchronously
- Superior choice for both sending and receiving due to efficiency

### High-Level Architecture

The system divides into three major categories:

#### Stateless Services
Traditional request/response services handling:
- User login/signup
- User profile management
- Service discovery (provides clients with available chat server addresses)
- Authentication
- Group management

Uses load balancer for request routing; can be monolithic or microservices.

#### Stateful Service
**Chat Service** maintains persistent WebSocket connections with clients. Clients remain connected to the same server as long as it's available.

#### Third-Party Integration
**Push Notification Service** alerts users of new messages when app is inactive.

### Scalability Considerations

**Concurrent Connection Capacity:**
- Estimate: 10KB memory per connection
- 1 million concurrent users ≈ 10GB memory
- *Single-server design is unacceptable* (single point of failure, lacks redundancy)
- Start with single-server design but architect for distribution

### Complete High-Level Design

```
Users → Load Balancer → API Servers + Notification Servers
                           ↓
                      Real-time Service
                    (Chat + Presence Servers)
                           ↓
                        KV Stores
```

**Components:**
- **Chat servers:** Facilitate message sending/receiving
- **Presence servers:** Manage online/offline status
- **API servers:** Handle login, signup, profile changes
- **Notification servers:** Send push notifications
- **Key-value store:** Persist chat history

### Storage Strategy

#### Data Types
1. **Generic data** (user profile, settings, friend lists) → Relational databases
2. **Chat history** → Key-value stores

#### Chat Data Characteristics
- Enormous volume (60 billion messages daily across major platforms)
- Random access needed for search, mentions, specific message jumps
- Read-to-write ratio approximately 1:1 for one-on-one chat

#### Why Key-Value Stores
- Easy horizontal scaling
- Very low latency access
- Handle long-tail data access better than relational databases
- Proven by industry leaders (Facebook Messenger uses HBase; Discord uses Cassandra)

---

## Step 3: Design Deep Dive

### Data Models

#### Message Table for One-on-One Chat

| Column | Type | Purpose |
|--------|------|---------|
| message_id | bigint | Primary key; determines message sequence |
| message_from | bigint | Sender user ID |
| message_to | bigint | Recipient user ID |
| content | text | Message body |
| created_at | timestamp | Message creation time |

*Note:* Cannot rely on created_at for sequencing because multiple messages may share identical timestamps.

#### Message Table for Group Chat

| Column | Type | Purpose |
|--------|------|---------|
| channel_id | bigint | Partition key; identifies group/channel |
| message_id | bigint | Part of composite primary key |
| user_id | bigint | Message sender ID |
| content | text | Message body |
| created_at | timestamp | Message creation time |

**Composite Primary Key:** (channel_id, message_id)

#### Message ID Generation

Requirements:
- Must be globally unique
- Should be sortable by time (newer rows have higher IDs than older ones)

**Approaches:**
1. **Auto-increment** (MySQL-style) - not available in NoSQL systems
2. **Global 64-bit sequence number** (Snowflake) - complex to implement but ensures global uniqueness
3. **Local sequence number** - only unique within a group channel; sufficient for message ordering within single channel; simpler implementation

### Service Discovery

**Purpose:** Recommend optimal chat server for client based on geographical location, server capacity, and other criteria.

**Technology:** Apache Zookeeper (popular open-source solution)

**Process:**
1. User A initiates login
2. Load balancer routes to API servers
3. API servers query Zookeeper for available chat server
4. Zookeeper returns best server (e.g., Server 2)
5. User A establishes WebSocket connection to assigned server

### Message Flows

#### One-on-One Chat Flow

```
User A → Chat Server 1 → (1) Request message ID from ID generator
                         (2) Push message to message sync queue
                         (3) Store in KV store
                         (4a) If User B online: forward to Chat Server 2
                         (4b) If User B offline: send to PN servers
User B ← Chat Server 2 ← Receive message
```

**Detailed Steps:**
1. User A sends message to Chat Server 1
2. Chat Server 1 requests unique message ID from ID generator
3. Message pushed to message sync queue
4. Message stored in key-value store
5a. If User B is online → forward to Chat Server 2
5b. If User B is offline → send push notification via PN servers
6. Chat Server 2 forwards message to User B through persistent WebSocket

#### Message Synchronization Across Multiple Devices

Each device maintains `cur_max_message_id` variable tracking latest message ID on that device.

**New Message Criteria:**
- Recipient ID equals logged-in user ID
- Message ID in KV store exceeds `cur_max_message_id`

This allows each device to independently sync new messages without conflicts, since each tracks its own progress separately.

#### Small Group Chat Flow

**Design Choice:** Copy message to each recipient's message sync queue (individual inbox)

**Advantages:**
- Simplifies sync flow; clients only check own inbox
- Acceptable for small groups

**Limitations:**
- Infeasible for large groups (WeChat limits to 500 members)

**Reception Side:** Recipients receive messages from multiple senders; each maintains inbox containing messages from various senders.

### Online Presence

Presence servers manage online status via WebSocket connections with clients.

#### User Login Flow

After WebSocket connection establishment:
- User's online status saved to KV store
- `last_active_at` timestamp recorded
- Presence indicator shows user as online

#### User Logout Flow

- Online status changed to offline in KV servers through API servers
- Presence indicator updates accordingly

#### User Disconnection Handling

**Problem:** Frequent network disconnects (e.g., tunnel traversal) would constantly toggle presence indicator, creating poor user experience.

**Solution:** Heartbeat mechanism

**Implementation:**
- Client sends heartbeat event to presence servers every 5 seconds
- If heartbeat received within threshold (e.g., 30 seconds), user marked online
- If no heartbeat within threshold, user marked offline
- Prevents status flapping from brief connection interruptions

#### Online Status Fanout

**Model:** Publish-subscribe system where each friend pair maintains a channel

**Process:**
- When User A's status changes, event published to channels: A-B, A-C, A-D
- Users B, C, D subscribe to respective channels
- Friends receive status updates via WebSocket
- Communication happens in real-time through WebSocket

**Scalability Note:** For large groups (100,000+ members), fetching status on group entry or manual refresh is more efficient than pushing individual status change events.

---

## Step 4: Wrap Up

### Core Architecture Summary

**Key Components:**
- Chat servers for real-time messaging
- Presence servers for online status management
- Push notification servers
- Key-value stores for chat history persistence
- API servers for auxiliary functionalities
- Service discovery via Zookeeper
- WebSocket for client-server communication

### Additional Discussion Topics (if time permits)

**Media Support:**
- Extend system to support photos and videos
- Address compression, cloud storage, thumbnail generation

**End-to-End Encryption:**
- Implement sender-only, recipient-only message visibility
- Reference WhatsApp implementation

**Client-Side Caching:**
- Cache messages locally to reduce data transfer

**Load Time Optimization:**
- Geographically distributed caching networks (Slack's Flannel model)

**Error Handling:**
- Chat server failures: Service discovery reassigns clients
- Message resend mechanism: Retry and queuing strategies

---

## Key Design Tradeoffs

| Decision | Tradeoff |
|----------|----------|
| **WebSocket over HTTP** | Persistent connection overhead vs. real-time capability |
| **Local message IDs over global** | Simpler implementation vs. cross-shard ordering complexity |
| **KV stores over relational DB** | Scalability and latency vs. consistency guarantees |
| **Message copying for small groups** | Simplified sync logic vs. storage overhead |
| **Heartbeat presence tracking** | Delayed offline detection vs. eliminated status flapping |

---

## Step 5: Back-of-the-Envelope Math

### Volumes and rates (chapter baseline, 50M DAU)

```
DAU:                50M
Avg messages/user/day (active senders ~30% of DAU):
                    50 messages / day (texting-heavy users)
                    × 0.3 active senders
                    ≈ 15 messages / DAU / day average
Total messages/day: 50M × 15 = 750M / day
                    = 7.5 × 10^8 / 86,400 ≈ 8,700 messages / s average
Peak (5× avg):      ~43,500 messages / s

Reads (sync, search, history scroll):
  Heavy read traffic — every reconnect, every app open, every scroll
  Conservative: 10× writes  ⇒  87K reads / s avg,  ~435K reads / s peak

Concurrent connections:
  ~10–20% of DAU are "online" at any moment
  ⇒ 5–10M concurrent WebSocket connections
```

### Industry scale (WhatsApp / Messenger / Discord) — for orientation

```
WhatsApp (Meta quarterly disclosures, ~2023):
  ~100B messages / day    ≈ 1.16 × 10^6 / s  avg
  Peak during holidays:  ~2×  ≈ 2.3M / s
  2B+ MAU

Facebook Messenger (Meta engineering blog, ~2020):
  ~17B real-time messages / day  ≈ 200K / s avg
  Many more "non-real-time" via Stories, etc.

Discord (Discord Engineering blog, 2022):
  ~4B messages / day  ≈ 46K / s  avg  (then ~5–10× peak)

Slack (SREcon 2023):
  ~10B messages / quarter  ≈ ~1.3M / day  ≈ 15 / s avg
  (Much lower message rate than consumer chat; collaboration, not conversation.)
```

### Connection math

```
Per-WebSocket memory:       ~10 KB  (kernel TCP + userspace app state)
Concurrent connections:     5–10M
Total connection memory:    50–100 GB

Chat server sizing:
  A modern chat server: ~100K–250K concurrent connections per node
  (Erlang-based systems like WhatsApp push to 2M+ connections / node;
   JVM/Go systems cap lower because GC and threads don't scale the same way)
  ⇒ 5–10M connections ⇒ 20–100 chat server nodes
```

### Storage math

```
Per-message record:
  message_id (8 B) + from (8 B) + to (8 B) + content (~200 B avg) +
  created_at (8 B) + metadata (~50 B)  ≈ 300 B raw, ~150 B compressed

750M messages / day × 300 B = 225 GB / day  =  82 TB / year

After 5 years:
  410 TB raw
  With column-family compression (Cassandra): ~150 TB

If we add media (images, video):
  Average media / message: 50 KB
  750M × 50 KB = 37.5 TB / day   = 13.7 PB / year
  This is the dominant cost; the chapter's text-only assumption is unrealistic for any production system.

Hot retention (e.g., last 30 days in fast storage):
  750M × 30 days × 300 B = 6.75 TB  — fits on a small cluster of SSDs
```

### Latency budget for message delivery

```
Click-to-render budget (one-on-one, both online):

  Client → LB → Chat Server (entry):       10–30 ms
  ID generation:                            1–5 ms
  Persist (sync queue + KV write):         10–30 ms
  Recipient lookup (cache):                  1–3 ms
  Forward to recipient chat server:        10–30 ms
  Recipient WebSocket write + ack:          5–20 ms
  Total server-side:                       40–120 ms
  Network RTT client ↔ server:             20–100 ms (geo-dependent)
  Total end-to-end:                        60–220 ms

p99 SLO targets (industry standard):
  WhatsApp:       < 100 ms median
  Slack:          < 200 ms median
  Discord voice:  < 50 ms (real-time media)
  iMessage:       < 500 ms typical
```

### Presence math

```
Heartbeat:           1 / 5 s   =  0.2 / s per online user
Online users:        5M
Heartbeats / s:      5M × 0.2 = 1M heartbeats / s  (cluster-wide)

Each heartbeat:      small write to presence service
                     ⇒ 1M QPS is significant — needs sharded presence KV
                     ⇒ batch heartbeats in 1-second windows to drop to 5M QPS / 5 = manageable

Status change fanout (user goes online):
  Friends of that user: ~150 (median)
  Status events to push: 150 × (5M / presence_change_rate) ≈ 750K / s aggregate
  This is bounded; a status change happens at most a few times per day per user.
```

### Throughput ladder

```
At 50M DAU (chapter):
  Chat servers:   50–100 nodes
  Presence:       20–50 nodes
  KV store:       10–20 nodes per cluster × 3 replicas = 30–60 nodes
  API tier:       20–50 nodes
  Total compute:  ~150 nodes

At 1B DAU (WhatsApp / Messenger):
  Chat servers:   1,000–5,000 nodes (or ~500 Erlang nodes if BEAM-based)
  Presence:       200–500 nodes
  KV store:       100s of nodes per cluster, multiple clusters
  Total compute:  ~5,000–20,000 nodes
```

---

## Step 6: ASCII Architecture Diagrams

### 6.1 — End-to-end chat system (logical)

```
   ┌────────────────────────┐
   │   Clients              │
   │  (mobile / web)        │
   └────────────┬───────────┘
                │  WebSocket / REST
                ▼
   ┌──────────────────────────────────────────────────────────┐
   │                    Load Balancer                         │
   └────────────────────────┬─────────────────────────────────┘
                            ▼
   ┌──────────────────────────────────────────────────────────┐
   │   Stateless API Tier    (login, profile, group mgmt)     │
   └──────┬──────────────────────────┬────────────────────────┘
          │                          │
          │                          │  (service discovery:
          │                          │   Zookeeper / etcd)
          ▼                          ▼
   ┌────────────────────────┐  ┌────────────────────────────┐
   │   Chat Servers         │  │   Presence Servers         │
   │   (stateful, sticky    │  │   (stateful, sticky)       │
   │    WebSocket)          │  │                            │
   └──┬────────────┬────────┘  └─────────────┬──────────────┘
      │            │                          │
      │            │  (sync queue / Kafka)    │
      │            ▼                          ▼
      │   ┌────────────────────────────────────────────┐
      │   │  Message Sync Queue  │  Presence Service   │
      │   │  (Kafka per region)  │  (Redis / ScyllaDB) │
      │   └────────────┬────────┴─────────┬────────────┘
      │                │                  │
      │                ▼                  │
      │   ┌──────────────────────────────────────┐
      │   │      KV Store (Cassandra / HBase)    │
      │   │      - message_id → message blob     │
      │   │      - user_id → recent messages     │
      │   └──────────────────────────────────────┘
      │
      ▼
   ┌────────────────────────────────────────────┐
   │  Push Notification Providers               │
   │  (APNs / FCM) — used when recipient offline│
   └────────────────────────────────────────────┘
```

### 6.2 — Sequence: 1:1 message, both users online

```
   Alice    ChatSrv-1    IDGen    SyncQ    KVStore    ChatSrv-2    Bob
     │          │          │        │         │           │          │
     │  WS send │          │        │         │           │          │
     │─────────►│          │        │         │           │          │
     │          │ alloc    │        │         │           │          │
     │          │─────────►│        │         │           │          │
     │          │ m_id=42  │        │         │           │          │
     │          │◄─────────│        │         │           │          │
     │          │ produce  │        │         │           │          │
     │          │──────────────────►│         │           │          │
     │          │ persist (m_id, from, to, body)            │          │
     │          │────────────────────────────►│           │          │
     │          │ ack     │        │         │           │          │
     │          │◄────────────────────────────│           │          │
     │  ack     │          │        │         │           │          │
     │◄─────────│          │        │         │           │          │
     │          │          │        │         │ route to Bob           │
     │          │          │        │         │──────────►│          │
     │          │          │        │         │           │ WS push  │
     │          │          │        │         │           │─────────►│
     │          │          │        │         │           │          │
     │          │          │        │         │           │  ack     │
     │          │          │        │         │           │◄─────────│
     │          │          │        │         │  delivery │          │
     │          │          │        │         │  ack      │          │
     │          │          │        │         │◄──────────│          │
```

### 6.3 — Sequence: multi-device sync on reconnect

```
   Phone-A    Phone-B    ChatSrv    KVStore     Presence
     │           │          │          │            │
     │           │          │          │            │ (Bob reconnects Phone-B)
     │           │          │          │            │
     │           │ WS open  │          │            │
     │           │─────────►│          │            │
     │           │          │ GET max_message_id for Bob              │
     │           │          │───────────────────────►              │
     │           │          │◄────────────────────── │              │
     │           │ 42       │          │            │
     │           │◄─────────│          │            │
     │           │          │ LIST messages where id > 42            │
     │           │          │───────────────────────►              │
     │           │          │ [m_43, m_44, m_45]     │              │
     │           │          │◄────────────────────── │              │
     │           │ deliver m_43..m_45             │              │
     │           │◄─────────│          │            │
     │           │ update cur_max = 45             │              │
     │           │          │          │            │
     │           │          │          │  (Phone-A is also online; both devices have separate cursors)
     │ (later)   │          │          │            │
     │ WS open   │          │          │            │
     │──────────►│          │          │            │
     │          │ GET max  │          │            │
     │          │───────────────────────►              │
     │          │◄────────────────────── │              │
     │ 45       │          │          │            │
     │◄─────────│          │          │            │
     │          │ LIST id > 45                       │
     │          │───────────────────────►              │
     │          │ (none)  │          │            │
     │◄─────────│          │          │            │
```

### 6.4 — Group chat fan-out (small groups ≤ 100)

```
   Sender    ChatSrv    SyncQ (group)   Worker   N recipient inboxes
     │          │            │             │              │
     │ WS send  │            │             │              │
     │─────────►│            │             │              │
     │          │ alloc id   │             │              │
     │          │ produce (channel_id=g7, m_id, body)        │
     │          │───────────►│             │              │
     │ ack      │            │             │              │
     │◄─────────│            │             │              │
     │          │            │ consume     │              │
     │          │            │────────────►│              │
     │          │            │             │ For each member u in g7:
     │          │            │             │   write (u, g7, m_id) → u's inbox
     │          │            │             │──────────────►
     │          │            │             │  (per-recipient inbox row)
     │          │            │             │
     │          │            │             │  Recipient devices pull their inbox,
     │          │            │             │  see new (g7, m_id), fetch body, render.
```

---

## Step 7: Trade-off Tables

### 7.1 — Real-time transport comparison

| Mechanism | Latency | Server cost | Client battery | Failure mode | Best fit |
|---|---|---|---|---|---|
| **WebSocket** | < 100 ms | High (persistent) | Medium | Server stickiness required | Default for chat |
| **Long polling** | 1–5 s | Medium | Medium | Server can't detect drop | Legacy HTTP-only |
| **Server-Sent Events** | < 1 s | Medium | Low | One-way only | Notifications, read-only streams |
| **MQTT** | < 100 ms | Medium | Very low | Broker SPOF | IoT, mobile-optimized |
| **gRPC streams** | < 100 ms | Medium | Medium | HTTP/2 required | Service-to-service |
| **Polling** | 1–30 s | High (waste) | High | Wasteful | None — avoid |

### 7.2 — Message ID generation

| Approach | Uniqueness | Sortable by time | Complexity | Cross-shard order |
|---|---|---|---|---|
| **Auto-increment DB** | Strict | Yes | Low | Single source |
| **UUIDv4** | Probabilistic (~10⁻³⁶ collision) | No | Low | None |
| **UUIDv7** | Probabilistic | Yes (timestamp prefix) | Low | Approximate |
| **Snowflake (Twitter)** | Strict (10-bit machine + 12-bit seq) | Yes | Medium | Approximate |
| **Local per-channel sequence** | Per-channel | Yes (within channel) | Very low | Strictly within channel |
| **Hybrid (channel_id, local_seq)** | Per-channel strict | Yes (within channel) | Very low | Per-channel |
| **Logical clock (Lamport)** | Strict per-process | No natural time order | Medium | Strict total order if sync |

### 7.3 — Chat history storage

| Backend | Read latency | Write latency | Horizontal scale | Best fit |
|---|---|---|---|---|
| **Cassandra** | Low (partition key) | Very low | Native (consistent hashing) | Wide-row per user |
| **HBase** | Low (region server) | Low | Native (regions) | High-throughput append |
| **DynamoDB** | Single-digit ms | Single-digit ms | Native | AWS-native |
| **FoundationDB** | Low (record layer) | Low | Native | Strong-consistency needs |
| **PostgreSQL + partitioning** | Medium (with btree) | Medium | Manual sharding | Small scale, ACID needs |
| **MongoDB** | Medium | Medium | Native sharding | Mixed workloads |

### 7.4 — Presence representation

| Model | Storage | Update cost | Read cost | Best fit |
|---|---|---|---|---|
| **Heartbeat (last_active_at)** | KV TTL | Low per heartbeat | 1 read | Default |
| **Explicit state (online/away/DND)** | Per-user state | 1 write per state change | 1 read | Status-as-product |
| **Derived (connection count > 0)** | Connection registry | Per-connect/disconnect | Aggregate read | Large fleets |
| **Hybrid (state + heartbeat)** | Both | Both | Both | Most production systems |

---

## Step 8: Real-World Case Studies

### 8.1 — WhatsApp (Erlang, ~2B MAU)

WhatsApp is the canonical case study in chat architecture:

- **Erlang/BEAM runtime.** WhatsApp chose Erlang because its actor model and lightweight processes map directly to "one process per connection." A single server can hold ~2M concurrent connections.
- **End-to-end encryption** using the Signal protocol since 2016. Messages are encrypted on the client; the server is a dumb pipe. This means the server **cannot** do server-side search, ranking, or rich features on message contents.
- **Message protocol: FunXMPP** (custom XMPP variant). Stanzas carry messages, presence, ack; routing is via phone number, not username.
- **Per-country sharding.** Each user's "home" region is one shard; messages stay within that shard as much as possible. Cross-region messages use a smaller inter-region path.
- **Scale disclosures (2017 onward):** 1B+ MAU served by ~50 chat server engineers (one of the lowest engineer-per-user ratios in tech); at acquisition by Meta, WhatsApp was doing ~60B messages/day with a few hundred servers.

### 8.2 — Discord (Cassandra, trillions of messages)

Discord Engineering blog (2017–2023) is one of the richest public sources for chat architecture.

- **Cassandra wide-row pattern** for message storage. Each channel is a partition; messages are columns ordered by `message_id` (a Snowflake). A single Cassandra row can hold billions of messages.
- **"Trillions of messages" milestone (2022).** Storage grew from 100B → 1T → several T messages over a few years.
- **Cassandra compaction pain.** Discord went through multiple compaction strategy migrations as their data grew; eventually moved to **incremental compaction** to reduce write amplification.
- **Frontend cache tier (Redis) + ScyllaDB hot tier** for sub-millisecond reads of recent messages, with Cassandra as the durable backend.
- **Gateway servers** maintain WebSocket connections to clients. Discord operates ~1,000 gateway nodes to handle millions of concurrent connections.
- **Voice** is a separate system (WebRTC + selective forwarding units); voice gateway and chat gateway are independently scaled.

### 8.3 — Slack (WebSocket fanout, Flannel)

From Slack Engineering blog:

- **WebSocket-based real-time messaging.** Slack uses its own RTM (Real Time Messaging) protocol plus the newer Events API over WebSocket.
- **Server-side message fanout:** when a message is posted to a channel, the chat server publishes it to a fanout service that delivers to all online members.
- **Flannel** (Slack's edge network) caches recent message history per team near users, reducing load times for mobile clients.
- **Channel-based sharding** for very large workspaces — a "shared channel" model allows cross-workspace messages with explicit federation.
- **Search:** Slack runs a separate search pipeline that crawls the message store and indexes into Elasticsearch. Search is async; messages are searchable within seconds of being sent.

### 8.4 — Signal protocol (the E2E encryption standard)

The Signal protocol is used by WhatsApp, Signal, Facebook Messenger's "Secret Conversations," and others.

- **Double Ratchet Algorithm:** combines a Diffie-Hellman ratchet and a symmetric-key ratchet to provide:
  - **Forward secrecy** — compromising a current key doesn't reveal past messages.
  - **Post-compromise security** — keys heal over time after a compromise.
- **X3DH key agreement** establishes the first session between two users when one may be offline.
- **Sealed sender** (2018) hides the sender's identity from the server in addition to the message content.
- **Why it matters for design:** the chat server can't index, search, or rank encrypted message bodies. Server-side features have to work on metadata (who, when, group membership) only.

### 8.5 — Telegram (MTProto)

Telegram's protocol — MTProto — is custom and controversial:

- **MTProto mobile protocol** uses authenticated encryption with a custom handshake. Critiqued by cryptographers for years; Telegram eventually added end-to-end "Secret Chats" using a different scheme.
- **Server-client model:** messages are stored server-side in Telegram's cloud; cloud chats are not E2E by default. Secret Chats are E2E.
- **Supergroups up to 200,000 members** — the chapter's 100-member limit is for illustration; production systems support much larger groups with a different fanout model (fan-out-on-read for the membership list).
- **Channels** are one-to-many broadcast: 1 message in, millions of subscribers out. Implemented as a fan-out-on-write with subscriber-cache TTLs.

### 8.6 — Facebook Messenger architecture (HBase)

From Meta engineering disclosures:

- **HBase** as the message store (wide-row per thread). Threads are partition keys; messages within a thread are columns sorted by `message_id`.
- **TAO** for graph storage (friend / conversation metadata).
- **Iris** as the Messenger chat service: handles WebSocket connections, message routing, presence.
- **Migration history:** Messenger started on a Node.js / MySQL stack, migrated to HBase for scale, then to TAO-backed graph + HBase messages.
- **Real-time path:** message → Iris → presence lookup → forward to recipient's gateway; offline path → store in HBase + send push notification.

---

## Step 9: Common Pitfalls and Failure Modes

### 9.1 — WebSocket server stickiness loss on deploys

Symptom: every deploy breaks 10% of active connections; users see "reconnecting."

Cause: clients connect to a chat server but the server is killed mid-deploy; clients fall back to reconnecting but service discovery sends them somewhere else.

Fix: drain connections before deploy (stop accepting new ones, send a "go away" frame, let clients reconnect to a fresh node). Use a connection registry so other services know which node holds which connection. Never fail-over the connection mid-message — wait for the message to ack first.

### 9.2 — Sticky sessions under uneven load

Symptom: one chat server has 50K connections; another has 5K. The busy one is at 95% CPU.

Cause: client discovery picks the first available server; long-lived sessions mean imbalance persists for hours.

Fix: **consistent hashing** with virtual nodes — distribute users uniformly by `hash(user_id) mod N` where N adapts to capacity. Implement a "rebalance" tool that nudges users to different nodes during low-traffic windows.

### 9.3 — Message ordering breaks under retries

Symptom: messages appear out of order on the recipient's screen — "yes" arrives after "yes no".

Cause: server retries messages that "failed to ack" but the original was actually delivered. Client receives both, displays in order received.

Fix: assign each message a per-conversation monotonic ID; client deduplicates and orders by ID. The chapter's "local sequence number per channel" handles this cleanly. Even with retries, the client only renders by ID, not by arrival order.

### 9.4 — Push notification storm from a viral group

Symptom: a 500-member group suddenly bursts to 50K members; every member gets a push; APNs/FCM starts throttling.

Cause: chapter-style "send push to every recipient" doesn't account for group size or recipient availability.

Fix: aggregate pushes — if a recipient has 5 unread messages from the same sender/group in 30 s, send one push with a count. Detect recipient online state first; push only to offline recipients.

### 9.5 — Heartbeat / presence flapping

Symptom: a user's status flickers online/offline every few minutes; friends see "unstable" indicator.

Cause: aggressive heartbeat threshold (e.g., 5 s) combined with brief network blips.

Fix: chapter's 30-second threshold is a reasonable starting point. Add **hysteresis**: require 2 consecutive missed heartbeats to mark offline; require an explicit reconnect to mark online after a brief disconnect. Avoid recording "last_active_at" on heartbeat — only on real activity.

### 9.6 — Media messages blow up storage and bandwidth

Symptom: a chat app that "only does text" gets image / video support and storage triples in a week.

Cause: media is 1,000× larger than text. KV stores and chat servers weren't sized for it.

Fix: media goes to **object storage** (S3) with CDN in front; chat metadata holds only URLs. Compress images server-side; transcode videos to multiple bitrates. Apply per-conversation media size limits.

### 9.7 — Replay attacks on reconnect

Symptom: after a reconnect, a client receives messages it already saw.

Cause: the server's "last delivered" pointer is stale; client receives duplicates.

Fix: client tracks `cur_max_message_id` (per device, as in the chapter). Server returns only `id > cur_max`. Combined with idempotent message IDs, duplicates are harmless.

### 9.8 — Time bombs in the message store

Symptom: storage grows linearly forever; "permanent history" turns into a 50 PB problem.

Cause: chat history is treated as free; nobody owns retention.

Fix: explicit retention policy (typ. indefinite for 1:1, configurable for groups). Implement a background job that ages out media older than N years (keep text). Compress old messages. Track PII separately for GDPR/CCPA erasure.

### 9.9 — Group fanout O(N²) blowup

Symptom: a group of 1,000 users has 1M inbox writes for a single message.

Cause: chapter-style "copy to each recipient's inbox" doesn't scale beyond ~100.

Fix: large groups use **fan-out-on-read** — write the message once to the channel; recipients query the channel on connect / refresh. Materialized views / indexes maintained per recipient only for active recipients.

---

## Step 10: Interview Q&A

### Q1. "Why WebSocket and not HTTP/2 streams or gRPC?"

**Answer sketch:**
WebSocket is the simplest standard that gives bidirectional, low-overhead messaging over port 443 (firewall-friendly). HTTP/2 streams work but require HTTP/2 throughout the stack and client support. gRPC streams are great for service-to-service but cumbersome for browser clients (needs grpc-web). For chat, **WebSocket for the client-server path** + **gRPC for service-to-service** is a common combination.

### Q2. "How do you make sure a message reaches every device?"

**Answer sketch:**
Each device tracks `cur_max_message_id` for the conversations it cares about. On reconnect (or via a long-lived WebSocket subscription), it pulls all messages with `id > cur_max`. The server's responsibility is to make sure the message is **persisted** and **addressable** by ID — not to guarantee every device received it in real time. This model is naturally multi-device and handles intermittent connectivity gracefully.

### Q3. "How do you scale WebSocket connections beyond a single server?"

**Answer sketch:**
Three things:
1. **Stateful chat servers with sticky routing** — a user always lands on the same server (by consistent hashing on user_id) for as long as that server is alive.
2. **Service discovery** (Zookeeper, etcd) tracks which server holds which user; clients query it on login.
3. **Inter-server fanout** — when user A's chat server needs to send to user B, it looks up B's server in the registry and forwards. If B is offline, B's server persists to B's inbox; if B is online, it pushes directly.

Add a rebalancing tool that, during low-traffic, drains users off overloaded servers.

### Q4. "Walk me through message persistence. Why Cassandra, not Postgres?"

**Answer sketch:**
Cassandra's wide-row model maps directly to "messages in a conversation": partition key = channel_id, clustering key = message_id. A single read returns the last N messages in time order, in a single round trip. Postgres can do this with `(channel_id, message_id)` indexes, but write amplification and index size grow painfully past ~100M rows. Cassandra was built for this pattern: append-mostly, time-series, hot recent + cold old, horizontal scale via consistent hashing. Discord, Messenger, and Instagram all made similar choices for the same reason.

### Q5. "How does end-to-end encryption change the design?"

**Answer sketch:**
Three big changes:
1. **Server is a dumb pipe.** It sees ciphertext only. Server-side search, ranking, and link previews become impossible on encrypted content.
2. **Key management is client-side.** Each device must hold the user's identity key; new devices need a key-exchange flow (Signal's X3DH).
3. **Group keys are harder.** Each group member needs the group key; adding/removing members requires a re-keying round (Sender Keys in Signal, asymmetric for very large groups).

The trade-off is privacy vs features. WhatsApp picked E2E by default and lost search; Messenger kept server-side features and offered E2E as an opt-in ("Secret Conversations").

### Q6. "How do you 10× to 500M DAU?"

**Answer sketch:**
Same architecture; bigger numbers. Key adjustments:
- **Connection density per server** — if you started at 100K connections/server, push to 250K (depends on runtime; Erlang can do millions). Otherwise add more chat server nodes.
- **Sync queue** — scale Kafka horizontally by adding partitions; rebalance by `user_id` hash.
- **KV store** — Cassandra scales horizontally but compaction and repair become operations concerns; budget for ongoing ops.
- **Multi-region** — pick a region per user (home region); cross-region messaging uses a separate queue; presence is per-region.
- **Push notification budget** — APNs/FCM costs scale linearly; renegotiate contracts and use batching aggressively.

Architecturally the design holds. Operationally it's a much bigger team.

### Q7. "What if we go global?"

**Answer sketch:**
Three patterns:
1. **Home region per user.** Each user is anchored to one region. Messages from A (US) to B (EU) traverse US→EU inter-region path. Latency: 100–300 ms cross-region; 50 ms intra-region.
2. **Active-active with CRDTs.** Both regions accept writes; conflicts resolved by message timestamp + ID. Complicated; rarely worth it for chat.
3. **Edge gateways.** The connection layer runs in many PoPs (Cloudflare, AWS Local Zones); chat servers and storage stay in fewer regions. Reduces client-to-server latency without multi-region storage complexity.

Most production chat systems use (1) + (3) — home-region storage + edge gateways for connection locality.

### Q8. "How do you test chat at scale?"

**Answer sketch:**
Three layers:
1. **Unit tests** for protocol / state machines (reconnect, dedup, ordering).
2. **Integration tests** with a real chat server + a fake client that opens thousands of WebSocket connections; assert message delivery, ordering, ack timing.
3. **Load tests** using tools like **k6**, **wrk**, or **Artillery** with WebSocket support. Target: 1M concurrent connections from a single load generator box using many file descriptors. Measure: p50/p99 latency, message loss, reconnection time after server kill.

Chaos testing: kill chat servers mid-test; verify that other servers pick up the load, clients reconnect, no messages lost.

---

## Step 11: Glossary

| Term | Definition | Common misconception |
|---|---|---|
| **WebSocket** | Bidirectional persistent connection over TCP, started as an HTTP upgrade. | "Replaces HTTP." WebSocket is layered on top of HTTP and shares port 443; it's a protocol for a specific use case. |
| **Long Polling** | Client holds an HTTP request open until the server has data or times out. | "Same as WebSocket." Long polling is request-response with extended timeouts; it doesn't push without a subsequent request. |
| **MQTT** | Lightweight pub/sub protocol designed for constrained devices. | "Required for chat." It's optional — useful for IoT but most chat uses raw WebSocket. |
| **Erlang / BEAM** | Runtime with lightweight processes and native support for millions of concurrent connections. | "Required for chat." Only WhatsApp-scale really needs it; most chat systems run fine on Go or JVM. |
| **Snowflake ID** | A 64-bit time-sortable ID (timestamp + machine + sequence). | "Globally unique forever." Unique in practice at the resolution of milliseconds; collisions require deliberate engineering. |
| **Signal Protocol** | E2E encryption protocol providing forward secrecy and post-compromise security. | "Encryption only." It's a protocol family — X3DH, Double Ratchet, Sesame — not just an algorithm. |
| **Presence** | Real-time online/offline state for users. | "Always accurate." Presence is eventually consistent; flapping and brief disconnects are normal. |
| **Sticky Session** | Routing a client to the same server across requests. | "Same as affinity." Sticky specifically means "same server for the duration of a WebSocket connection"; affinity is a broader term. |
| **Inbox Pattern** | Each recipient has a per-device or per-user inbox of message IDs to consume. | "Solves everything." Simplifies sync but introduces duplication and invalidation cost for group edits/deletes. |
| **Fan-out Service** | Component that delivers a single message to all recipients of a group or channel. | "Cheap at scale." A 100K-member group with chapter-style fanout = 100K writes per message; use fan-out-on-read for large groups. |
| **Group Channel** | A persistent logical room identified by `channel_id` that contains ordered messages. | "Same as a thread." In some products yes, in others channels are top-level and threads are sub-channels. |
| **Idempotency** | A property that processing the same message twice yields the same result as processing it once. | "Free." Idempotency requires either deterministic operations or external dedup state. |
| **TAO** | Facebook's distributed data store optimized for the social graph. | "Publicly available." Bespoke Facebook infrastructure. |