# Design A News Feed System

## Overview

A news feed system delivers a continuously updating list of content from followed users. This design covers both publishing and retrieval flows for a social media platform similar to Facebook, Instagram, or Twitter.

## Step 1: Problem Understanding and Design Scope

### Clarification Questions and Requirements

**Platform & Features:**
- Supports both mobile and web applications
- Core capability: users publish posts and view friends' content
- Feed sorted in reverse chronological order
- User capacity: up to 5,000 friends per account
- Traffic volume: 10 million daily active users
- Content types: text, images, and videos

## Step 2: High-Level Design

### Two Primary Flows

**Feed Publishing:** Posts written to cache and database; content propagated to friends' feeds

**News Feed Building:** Aggregates friends' posts in reverse chronological order for display

### Essential APIs

**Feed Publishing API**
```
POST /v1/me/feed
Parameters:
- content: post text
- auth_token: authentication credential
```

**News Feed Retrieval API**
```
GET /v1/me/feed
Parameters:
- auth_token: authentication credential
```

### Feed Publishing Architecture Components

- **User Layer:** Web browser or mobile app initiating requests
- **Load Balancer:** Distributes traffic across servers
- **Web Servers:** Route requests to internal services; enforce authentication and rate limiting
- **Post Service:** Persists posts in database and cache
- **Fanout Service:** Delivers content to friends' news feeds via cache
- **Notification Service:** Alerts friends about new content

### News Feed Retrieval Architecture

- **Load Balancer:** Manages incoming traffic
- **Web Servers:** Direct requests to news feed service
- **News Feed Service:** Fetches feed from cache layer
- **News Feed Cache:** Stores post IDs for rapid retrieval

## Step 3: Deep Dive Design

### Feed Publishing Deep Dive

**Web Server Responsibilities:**
- Authenticate users via auth_token
- Enforce rate limiting to prevent spam
- Validate requests before downstream processing

### Fanout Service Strategy

The fanout process delivers posts to all friends. Two competing models exist:

**Fanout on Write (Push Model)**

Strengths:
- Real-time feed generation
- Fast retrieval (pre-computed)

Weaknesses:
- Hotkey problem when users have many friends
- Wasted resources for inactive users

**Fanout on Read (Pull Model)**

Strengths:
- Efficient for inactive users
- No hotkey problem

Weaknesses:
- Slow feed fetching (on-demand computation)

**Hybrid Approach (Recommended):**
Deploy push model for typical users; implement pull model for celebrities/high-follower accounts using consistent hashing to distribute load evenly.

### Fanout Service Workflow

1. Retrieve friend IDs from graph database
2. Fetch friend information from user cache; filter based on settings (muted users, privacy restrictions)
3. Push friends list and post ID to message queue
4. Fanout workers process queue messages
5. Store post ID and user ID pairs in news feed cache
6. Cache contains only IDs (not full objects) to minimize memory; configurable limits prevent excessive storage

**Cache Structure:** News feed cache maintains `<post_id, user_id>` mappings, with newest posts appended first.

### News Feed Retrieval Deep Dive

**Retrieval Flow:**

1. User sends `/v1/me/feed` request
2. Load balancer routes to web servers
3. Web servers invoke news feed service
4. Service retrieves post IDs from news feed cache
5. Service fetches complete user and post objects from respective caches
6. Missing data fetched from databases (post DB, user DB)
7. Fully populated feed returned as JSON to client
8. Media content (images, videos) served via CDN for performance

### Cache Architecture (5-Layer Model)

| Layer | Purpose | Details |
|-------|---------|---------|
| News Feed | Feed composition | Stores post IDs |
| Content | Post data | Hot cache for popular content; separate tier for normal content |
| Social Graph | Relationships | Stores follower/following data |
| Action | User interactions | Tracks likes, replies, other engagements |
| Counters | Metrics | Like counts, reply counts, follower counts |

## Step 4: Conclusion and Scalability Considerations

### Database Scaling Topics

- Vertical vs. horizontal scaling tradeoffs
- SQL vs. NoSQL selection criteria
- Master-slave replication architecture
- Read replica deployment
- Consistency model selection
- Database sharding strategies

### Additional Design Considerations

- Maintain stateless web tier
- Maximize caching at all layers
- Deploy multiple data centers
- Use message queues for loose coupling
- Monitor key metrics: peak hour QPS, feed refresh latency

---

**References:**
- Facebook Help: How News Feed Works
- Neo4j and SQL Server friend-of-friend recommendation techniques
