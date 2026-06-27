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
- Recent chats accessed frequently; old chats rarely accessed
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

- Online status changed to offline in KV store through API servers
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
