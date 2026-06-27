# How to Design a System like Instagram

> At planetary scale, every innocent feature — the like button, the home feed, the upload — hides a distributed-systems problem waiting to detonate.

**Type:** Learn
**Prerequisites:** Database Sharding, CDN and Caching, Message Queues and Async Processing
**Time:** ~35 minutes

---

## The Problem

You are the first engineer at a photo-sharing startup. On day one you wire up a Django app, an RDS Postgres instance, and an S3 bucket. It works fine for 10,000 users. Then you hit the front page of TechCrunch. Within 48 hours you have 2 million users, each uploading an average of 3 photos per day. Your database is melting, your storage costs are spiking, and — most visibly — the home feed takes 12 seconds to load. You scale vertically until you run out of instance sizes, then you panic.

The root issue is that social media products have three separate scaling axes that all explode at once: **storage** (media files), **write throughput** (likes, follows, uploads), and **read latency** (the home feed, which is the product's core loop). A naive design treats these as one problem and reaches for a bigger server. A production design treats them as three distinct sub-problems with different solutions.

Understanding how to decompose a system like Instagram is not just interview preparation. It is a blueprint for thinking clearly about any content-sharing platform — TikTok, Pinterest, Twitter/X, Snapchat — because they all share the same fundamental tension: globally consistent social graph, massive media storage, and a personalized ranked feed that must load in under 200 ms.

---

## The Concept

### Scoping the Requirements

Before drawing boxes and arrows, pin down what you are and are not building.

**Functional requirements (core):**
- Users can upload photos and short videos.
- Users can follow other users.
- Users see a home feed of recent posts from people they follow.
- Users can like and comment on posts.
- Users can search for accounts and hashtags.

**Non-functional requirements:**
- 500 million daily active users (DAU).
- 50 million photo uploads per day (~580 uploads/second).
- Read-heavy: reads outnumber writes 100:1.
- High availability (99.99 %); eventual consistency is acceptable for feeds and counts.
- Media latency: p99 < 200 ms for photos already cached; p99 < 2 s for first-byte of fresh uploads.

### Capacity Estimation

| Dimension | Calculation | Result |
|-----------|-------------|--------|
| Photo uploads/sec | 50 M / 86 400 | ~580 req/s |
| Peak upload (3× avg) | 580 × 3 | ~1 750 req/s |
| Storage per photo (compressed) | avg 200 KB | — |
| Daily storage added | 50 M × 200 KB | ~10 TB/day |
| 5-year storage | 10 TB × 365 × 5 | ~18 PB |
| Feed reads/sec | 500 M × 10 views/day / 86 400 | ~58 000 req/s |

These numbers tell you immediately: you cannot serve media from your API servers; you need object storage and a CDN. You also cannot rebuild feeds on every read at 58 000 req/s without aggressive caching or pre-computation.

### High-Level Architecture

```
┌──────────────┐       ┌─────────────────┐       ┌────────────────────┐
│   Mobile /   │──────▶│   API Gateway   │──────▶│  Auth Service (JWT)│
│   Web Client │       │  (rate limiting)│       └────────────────────┘
└──────────────┘       └────────┬────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
     ┌────────────────┐ ┌────────────────┐ ┌────────────────┐
     │  Upload Service│ │  Feed Service  │ │  Social Graph  │
     │                │ │                │ │  Service       │
     └───────┬────────┘ └───────┬────────┘ └───────┬────────┘
             │                  │                   │
     ┌───────▼────────┐ ┌───────▼────────┐ ┌───────▼────────┐
     │  Object Store  │ │   Redis Feed   │ │  Graph DB /    │
     │  (S3 / GCS)    │ │   Cache        │ │  Postgres      │
     └───────┬────────┘ └────────────────┘ └────────────────┘
             │
     ┌───────▼────────┐     ┌────────────────┐
     │  CDN (CloudFront│     │  Message Queue │
     │  / Akamai)     │     │  (Kafka)       │
     └────────────────┘     └───────┬────────┘
                                    │
                             ┌──────▼──────┐
                             │  Workers    │
                             │ (resize,    │
                             │  notify,    │
                             │  fan-out)   │
                             └─────────────┘
```

### Data Model

**Users table** — lives in Postgres (relational, ACID, low cardinality at user level):
```sql
users(user_id UUID PK, username TEXT UNIQUE, bio TEXT,
      profile_pic_url TEXT, created_at TIMESTAMPTZ)
```

**Follows table** — also Postgres, but sharded by `follower_id`:
```sql
follows(follower_id UUID, followee_id UUID,
        created_at TIMESTAMPTZ, PRIMARY KEY (follower_id, followee_id))
```

**Posts table** — Postgres for metadata, sharded by `user_id`:
```sql
posts(post_id UUID PK, user_id UUID, media_url TEXT,
      caption TEXT, created_at TIMESTAMPTZ)
```

**Likes and counts** — High write throughput. Store raw events in Cassandra (append-only, write-optimised) and maintain approximate counts in Redis counters. Exact counts are eventually consistent and that is fine — users accept a 1–2 second delay on like counts.

**Feed store** — Redis sorted set per user, scored by post timestamp:
```
Key:   feed:{user_id}
Type:  Sorted Set
Score: Unix timestamp of post
Value: post_id
```

### Feed Generation: Push vs Pull vs Hybrid

This is the crux of Instagram's architecture. Three strategies exist:

| Strategy | How it works | Pros | Cons |
|----------|-------------|------|------|
| **Pull (fan-out on read)** | On feed request, query DB for all followees, merge timelines | No write amplification | Slow for users with many follows; hammers DB on every read |
| **Push (fan-out on write)** | On upload, write post_id into every follower's feed cache | O(1) read; fast feed loads | Write amplification for celebrities (Beyoncé has 300 M followers) |
| **Hybrid** | Push for normal users; pull for celebrities | Best of both | More complex routing logic |

Instagram and Twitter both settled on the **hybrid approach**. When Kylie Jenner posts, her 400 million followers do not each get a pre-computed row written immediately. Instead her posts are flagged as "high-follower" and pulled into the feed at read time and merged with the pre-computed portion from normal accounts the user follows.

---

## Build It / In Depth

### Step 1 — Photo Upload Flow

```
Client                   Upload Service          S3 / GCS              Kafka
  │                            │                     │                    │
  │── POST /upload ───────────▶│                     │                    │
  │   (multipart form)         │── PutObject ───────▶│                    │
  │                            │◀── 200 OK ──────────│                    │
  │                            │── INSERT posts ─┐   │                    │
  │                            │                 └──▶ Postgres             │
  │                            │── Publish "new_post" event ──────────────▶│
  │◀── 200 OK (post_id) ───────│                     │                    │
```

Key decisions:
- **Presigned URLs**: Instead of proxying the binary through your API servers, return a presigned S3 URL so the client uploads directly to object storage. This removes the upload bandwidth from your application tier entirely.
- **Async processing**: After the object lands in S3, S3 triggers a Lambda (or Kafka consumer) to generate thumbnails (320px, 640px, 1080px), run content moderation, and extract EXIF metadata. The original post record is created immediately with `status=processing`, updated to `status=published` when workers finish.

### Step 2 — Fan-out Worker

```python
# Simplified fan-out worker (Kafka consumer)
def handle_new_post(event):
    post_id    = event["post_id"]
    author_id  = event["author_id"]
    timestamp  = event["created_at"]

    follower_count = social_graph.get_follower_count(author_id)

    if follower_count > CELEBRITY_THRESHOLD:   # e.g. 1 million
        # Skip push fan-out; feed service will pull at read time
        celebrity_posts_cache.add(author_id, post_id, score=timestamp)
        return

    # Push fan-out: write into each follower's Redis sorted set
    followers = social_graph.get_followers(author_id, batch_size=1000)
    pipeline = redis.pipeline()
    for follower_id in followers:
        key = f"feed:{follower_id}"
        pipeline.zadd(key, {post_id: timestamp})
        pipeline.zremrangebyrank(key, 0, -(MAX_FEED_SIZE + 1))  # trim to 800 posts
    pipeline.execute()
```

### Step 3 — Feed Read Flow

```
Client ──▶ Feed Service
              │
              ├── 1. ZREVRANGE feed:{user_id} 0 19  (Redis — ~1 ms)
              │
              ├── 2. For each celebrity the user follows:
              │       GET celebrity_posts:{celeb_id} (Redis — ~1 ms per celeb)
              │       Merge + sort by timestamp
              │
              ├── 3. Batch-fetch post metadata for post_ids
              │       (Redis look-aside → Postgres if miss)
              │
              └── 4. Return ranked/ordered list to client
```

A cold start (user with no pre-computed feed) falls back to a direct DB query, populates the Redis sorted set, and is served from cache thereafter.

### Step 4 — CDN Strategy for Media

```
Upload                          Read
  │                               │
  S3 (origin)                     Client
  │                               │
  └── CloudFront distribution ◀───┘
          │
          ├── Edge cache hit  ──▶ served in < 20 ms
          └── Cache miss      ──▶ pull from S3, cache at edge, TTL = 7 days
```

Use immutable URLs tied to the `post_id`. Because a photo never changes, you can set `Cache-Control: max-age=31536000, immutable`. This virtually eliminates S3 egress costs for popular content.

### Database Sharding

The `posts` table is sharded by `user_id`. A shard key of `user_id` means:
- All posts for a user live on one shard → efficient "get my posts" queries.
- Cross-user queries (feed) are handled by the pre-computed feed cache, not by scatter-gather across shards.

The `follows` table is sharded by `follower_id` for "who do I follow?" queries and maintains a secondary index sharded by `followee_id` for fan-out workers.

---

## Use It

| Component | Technology Options | When to Choose |
|-----------|-------------------|----------------|
| Object storage | AWS S3, GCS, Azure Blob | Default for any scale; use S3 multipart for files > 100 MB |
| CDN | CloudFront, Akamai, Fastly | CloudFront if already on AWS; Fastly for fine-grained cache purge APIs |
| Feed cache | Redis Cluster (sorted sets) | Up to ~100 GB working set; Redis Cluster for horizontal scale |
| Social graph | Postgres + pgbouncer | For moderate scale; switch to dedicated graph DB (Neo4j, TAO) at Facebook-scale |
| High-write counters | Cassandra, DynamoDB | Likes, views, impression counts — eventual consistency acceptable |
| Async workers | Kafka + Flink / Celery | Kafka for durability and replay; Celery if Python ecosystem and simpler ops |
| Search | Elasticsearch | Username and hashtag search; index posts asynchronously via Kafka consumer |

---

## Common Pitfalls

- **Synchronous fan-out on write.** Writing to every follower's feed in the request path of a post API call means a user with 1 million followers causes a 1-million-row write under your API's P99 latency budget. Always push fan-out to an async worker via a message queue.

- **Serving media through your application servers.** This burns CPU on I/O and bandwidth, caps your throughput, and costs 10× more than object storage egress through a CDN. Use presigned URLs or CDN-backed object storage from day one.

- **Single shard for the follows table.** If you do not shard the follows table early, querying "who follows user X?" for a celebrity becomes a full-table scan. Partition by both `follower_id` and `followee_id` and maintain both directions.

- **Ignoring the cold-start feed problem.** A new user or a user returning after months has no pre-computed feed. Without a fallback read-path (pull from DB, hydrate cache), the first request fails or returns empty. Always implement and test the fallback.

- **Using the same database for hot and cold data.** Post metadata accessed in the first 24 hours after upload is 100× hotter than posts from two years ago. Mixing them in one table tier wastes expensive fast storage and saturates I/O. Tier your storage: hot posts in Postgres + Redis; archive posts in cheaper columnar storage with lazy loading.

---

## Exercises

1. **Easy** — Draw the complete request flow for a user tapping the "like" button on a post: client → API gateway → like service → storage → notification. Identify where eventual consistency is acceptable and where it is not.

2. **Medium** — Redesign the fan-out strategy so that a user who follows 50 celebrities does not experience a slow feed load at read time. What data structure would you maintain in Redis, and how many Redis reads does a single feed request require?

3. **Hard** — Instagram Stories expire after 24 hours. Design the expiration mechanism: data model, how you enforce deletion at scale (without a full-table scan), and how you handle the edge case where a story goes viral and is cached aggressively across hundreds of CDN edge nodes before expiration.

---

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|------------------------|
| **Fan-out** | Sending a notification to many users | Writing a single event (a new post) into the feed caches of all followers — can mean millions of writes per event |
| **Feed hydration** | Loading the feed from the database | The multi-step process of fetching post IDs from cache, then batch-fetching post metadata, user profiles, and media URLs to compose a complete feed response |
| **Presigned URL** | A public S3 link | A time-limited URL signed with AWS credentials that allows a client to upload/download directly to/from S3 without going through your servers |
| **Hot–cold data tiering** | Archiving old data | Actively routing recent (hot) data to fast storage and old (cold) data to cheap storage, with the retrieval path made transparent to clients |
| **Celebrity problem** | Famous users getting more likes | The write-amplification bottleneck where a user with millions of followers makes push fan-out prohibitively expensive — solved by hybrid push/pull strategies |
| **Sharding key** | The column you index | The dimension you partition data on; a poor choice (e.g. timestamp) creates hot partitions while a good choice (e.g. user_id) distributes load evenly |
| **Eventual consistency** | Data might be wrong | Data across replicas will converge to the same value after propagation delay; acceptable for like counts and feed ordering, not acceptable for financial transactions |

---

## Further Reading

- **System Design Interview Vol. 1, Chapter 13** (Alex Xu) — canonical structured walkthrough of photo-sharing system design with capacity estimates and component diagrams.
- **Instagram Engineering Blog** — https://engineering.instagram.com — first-party posts on their migration from Python monolith to services, Cassandra adoption, and feed architecture evolution.
- **"Scaling Instagram Infrastructure" (PyCon 2014)** — https://www.youtube.com/watch?v=hnpzNAPiC0E — 40-minute talk by Instagram's infrastructure team on their actual sharding and caching choices.
- **AWS Architecture Blog — Building a Photo-Sharing Platform** — https://aws.amazon.com/blogs/architecture — reference architectures using S3, CloudFront, ElastiCache, and RDS that map directly to the components discussed here.
- **Martin Kleppmann — Designing Data-Intensive Applications, Chapter 11** (O'Reilly) — deep treatment of stream processing and fan-out patterns that underpin feed generation at scale.
