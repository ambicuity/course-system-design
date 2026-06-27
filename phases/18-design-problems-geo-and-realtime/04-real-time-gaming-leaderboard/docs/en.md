# Real-Time Gaming Leaderboard

## Step 1: Understanding the Problem and Establishing Design Scope

### Clarification Questions and Answers

| Question | Answer |
|----------|--------|
| Score calculation method | Users earn 1 point per match win |
| All players included? | Yes |
| Time segmentation | New tournament/leaderboard each month |
| Focus on top users? | Top 10 plus a specific user position and ±4 surrounding users |
| User scale | 5M daily active users; 25M monthly active users |
| Daily match volume | Average 10 matches per player daily |
| Tie handling | Same rank assigned; can break ties by timestamp if needed |
| Real-time requirement | Yes, real-time or near-real-time results required |

### Functional Requirements
- Display top 10 players on the leaderboard
- Show a user's specific rank
- Display players positioned four places above and below a desired user (bonus feature)

### Non-Functional Requirements
- Real-time score updates reflected on the leaderboard immediately
- General scalability, availability, and reliability

### Back-of-the-Envelope Estimation

**User Load:**
- 5M DAU over 24 hours = ~50 users/second average
- Peak: 5x average = 250 users/second

**QPS for Score Updates:**
- Average: 50 users/sec × 10 games/day = ~500 QPS
- Peak: 500 × 5 = 2,500 QPS

**QPS for Fetching Top 10:** ~50 (users load top 10 on first open daily)

---

## Step 2: High-Level Design and Buy-In

### API Design

#### POST /v1/scores
Update a user's position after winning a game.

**Request Parameters:** `user_id` (winner), `points` (points gained)
**Response:** 200 OK (updated) / 400 Bad Request (failed)

#### GET /v1/scores
Fetch the top 10 players.
```json
{
  "data": [
    { "user_id": "user_id1", "user_name": "alice", "rank": 1, "score": 12543 },
    { "user_id": "user_id2", "user_name": "bob", "rank": 2, "score": 11500 }
  ],
  "total": 10
}
```

#### GET /v1/scores/{:user_id}
Fetch the rank of a specific user.
```json
{ "user_info": { "user_id": "user5", "score": 1000, "rank": 6 } }
```

### High-Level Architecture

**Two main services:**
1. **Game Service:** Lets users play and validates wins
2. **Leaderboard Service:** Creates, maintains, and displays the leaderboard

**Data Flow:**
1. Player wins → request sent to Game Service
2. Game Service validates win → calls Leaderboard Service to update score
3. Leaderboard Service updates the Leaderboard Store
4. Player requests leaderboard data directly from Leaderboard Service

### Design Trade-offs

#### Should the Client Talk to Leaderboard Service Directly?
**Current:** Client → Game Service → Leaderboard Service.
**Rejected alternative (direct client access):** insecure; vulnerable to man-in-the-middle attacks where players modify scores. Server-side scoring required. **Exception:** server-authoritative games (e.g., online poker) handle all logic on game servers.

#### Should We Use a Message Queue?
Kafka could distribute score data to multiple consumers (leaderboard, analytics, push notifications). Not included in the primary design since multiple consumers weren't explicitly required, but could be added for turn-based/multiplayer notification scenarios.

---

## Step 3: Data Models

### Solution 1: Relational Database (RDS)

**Leaderboard Table:** `user_id (varchar) | score (int)`

**When a user wins a point:**
- New user: `INSERT INTO leaderboard (user_id, score) VALUES ('mary1934', 1);`
- Existing: `UPDATE leaderboard SET score=score + 1 WHERE user_id='mary1934';`

**Finding a user's rank:**
```sql
SELECT (@rownum := @rownum + 1) AS rank, user_id, score
FROM leaderboard
ORDER BY score DESC;
```

**Performance Issues:**
- Sorting millions of rows for exact rank is extremely slow (10+ seconds)
- Not suitable for real-time; poor scalability with constant updates
- Caching infeasible due to constant updates; table scans inefficient

A `LIMIT 10` optimization only helps top results, not mid-leaderboard rank calculation.

### Solution 2: Redis with Sorted Sets

**Why Sorted Sets:** members unique (one per user), each member has a score, members auto-ranked by score, fast read/write.

**Internal Architecture (two data structures):**
1. **Hash table:** maps users → scores
2. **Skip list:** maps scores → users for efficient ordering

**Skip List:** layered index structure; each level skips nodes of the level below, giving O(log n) insert/remove/search (vs. O(n) for a plain linked list).

**Redis Operations:**
| Operation | Complexity | Purpose |
|-----------|-----------|---------|
| ZADD | O(log n) | Insert user or update score |
| ZINCRBY | O(log n) | Increment user's score; assumes 0 if new |
| ZRANGE / ZREVRANGE | O(log n + m) | Fetch range of users (m = entries fetched) |
| ZRANK / ZREVRANK | O(log n) | Get position of any user |

**Implementation Workflow:**
- **User scores a point:** `ZINCRBY leaderboard_feb_2021 1 'mary1934'` (monthly sorted set created fresh; previous months archived)
- **Fetch top 10:** `ZREVRANGE leaderboard_feb_2021 0 9 WITHSCORES`
- **Fetch user position:** `ZREVRANK leaderboard_feb_2021 'mary1934'`
- **Fetch relative position (±4):** if rank is 361, `ZREVRANGE leaderboard_feb_2021 357 365`

**Storage Requirements:**
- Per user: 24-char user ID + 2-byte score = 26 bytes
- Worst case (25M MAU): 26 × 25M = 650 MB; with skip list + hash overhead ~1.3 GB
- **Single modern Redis server is sufficient.** Peak update QPS 2,500/sec is well within single-Redis capacity.

**Persistence and Reliability:**
- Redis is in-memory; node failure causes data loss
- Configure a read replica; on failure, promote replica and attach a new one
- **Supporting MySQL tables:** User data + Point history (user_id, score, timestamp). Enables play history and disaster recovery (rebuild Redis from point history)
- **Optional:** cache top-10 user details separately

---

## Step 4: Design Deep Dive

### Decision 1: Cloud Provider vs. Self-Managed

#### Option 1: Manage Your Own Services
- Monthly sorted set in Redis
- User details in MySQL (name, profile image)
- Optional Redis user-profile cache for top 10
- Load-balanced web servers handle API requests; query Redis + DB, using profile cache for top 10

#### Option 2: Build on Cloud (AWS)
- **Amazon API Gateway** defines HTTP REST endpoints
- **AWS Lambda** for serverless compute

| API Endpoint | Lambda Function |
|--------------|-----------------|
| GET /v1/scores | LeaderboardFetchTop10 |
| GET /v1/scores/{:user_id} | LeaderboardFetchPlayerRank |
| POST /v1/scores | LeaderboardUpdateScore |

**Advantages:** no provisioning, automatic scaling with DAU growth, AWS-managed environment, cost-effective for variable loads. **Recommendation:** serverless preferred for new implementations. Alternatives: Google Cloud Functions, Azure Functions.

### Scaling Redis for Massive Scale (500M DAU, 100x)
- Leaderboard size: ~65 GB; Peak QPS: ~250,000/sec
- Single Redis node insufficient → data sharding

#### Sharding Approach 1: Fixed Partition
Divide score range into fixed buckets (e.g., 10 shards: 1-100, 101-200, …, 901-1000).
- **Insert/update:** determine score from MySQL → identify shard → update; if score crosses a boundary, remove from old shard, add to new shard
- **Find rank:** local rank within shard + count of all users in higher shards
- **Fetch top 10:** query the highest-range shard
- **Optimization:** secondary cache mapping user_id → score to avoid MySQL lookups

#### Sharding Approach 2: Hash Partition (Redis Cluster)
- Redis Cluster uses 16,384 hash slots; slot = `CRC16(key) % 16384`
- Each node manages a slot range; adding/removing nodes only reassigns slot ranges
- **Fetch top 10:** scatter-gather — query top 10 from each shard, application merges/sorts
- **Limitations:** high latency for large K, latency bound by slowest partition, no straightforward per-user rank
- **Recommendation:** fixed partition preferred over hash partition for rank simplicity

**Redis Node Sizing:** allocate ~2x expected data for write-heavy workloads (snapshot creation); use redis-benchmark for capacity planning.

### Alternative: NoSQL (DynamoDB)
Desired properties: optimized for heavy writes, efficient sorting within a partition.

**Initial design problem:** linear scan to find top scores doesn't scale.

**Global Secondary Index iteration 1:** partition key `game_name#{year-month}` (e.g., `chess#2020-02`), sort key `score` → creates a **hot partition** (all current-month users in one partition).

**Solution — Write Sharding:** partition key `game_name#{year-month}#p{partition_number}`, with partition number = `user_id % number_of_partitions`.
| Partition Key | Sort Key | Attributes |
|---|---|---|
| chess#2020-02#p0 | score | user_id, email, profile_pic |
| chess#2020-02#p1 | score | user_id, email, profile_pic |
| chess#2020-02#p2 | score | user_id, email, profile_pic |

**Trade-off:** reduced per-partition load vs. increased read complexity (must query all partitions). Partition count based on write volume/DAU; requires benchmarking.

**Fetch top 10:** scatter-gather across partitions, merge/sort 30 entries → global top 10.

**User rank queries — Percentile Ranking:** instead of exact rank, return percentile (e.g., "top 10-20%"). A cron job analyzes per-shard distribution and caches percentile boundaries. Assumes roughly similar distributions across shards.

---

## Step 4: Wrap-Up and Additional Considerations

### Real-Time Performance Optimizations
- **Redis hash for user display data:** map user_id → user object (names, images) for faster retrieval than DB
- **Tie-breaking:** store user_id → timestamp of most recent win; on equal scores, earlier timestamp ranks higher

### System Failure Recovery
1. MySQL point table holds user_id, score_awarded, timestamp per win
2. Iterate entries, calling `ZINCRBY` once per win
3. Rebuild leaderboard offline; restore from snapshot once rebuilt

Historical data enables complete reconstruction without data loss.

## Key Takeaways
1. Redis sorted sets are ideal for real-time leaderboards at millions of users
2. Skip lists give O(log n) ranking operations
3. Fixed partitioning scales better than hash partitioning for rank queries
4. Write sharding with NoSQL needs careful load distribution
5. Serverless (Lambda) simplifies infrastructure for variable loads
6. MySQL point table enables disaster recovery
7. Percentile ranking can substitute exact ranks at massive scale
