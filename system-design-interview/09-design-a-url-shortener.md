# Design A URL Shortener

## Chapter Overview

This chapter addresses a classic system design interview question: creating a URL shortening service similar to TinyURL. The design encompasses API endpoints, URL redirection mechanisms, hash function strategies, and deep technical implementation details.

---

## Step 1: Understanding the Problem and Establishing Design Scope

### Clarification Questions & Answers

- **Functionality Example**: Convert long URLs like `https://www.systeminterview.com/q=chatsystem&c=loggedin&v=v3&l=long` into concise aliases such as `https://tinyurl.com/y7keocwj`
- **Traffic Volume**: 100 million URLs generated daily
- **Shortened URL Length**: As compact as possible
- **Character Set**: Alphanumeric characters (0-9, a-z, A-Z)
- **Deletion/Updates**: Assume URLs cannot be deleted or updated for simplicity

### Primary Use Cases

1. URL shortening: transform lengthy URLs into shortened versions
2. URL redirecting: route shortened URLs back to originals
3. System qualities: high availability, scalability, and fault tolerance

### Back-of-the-Envelope Estimation

**Write Operations:**
- Daily volume: 100 million URLs
- Per-second rate: ~1,160 write requests/second (100M ÷ 24 ÷ 3600)

**Read Operations:**
- Assuming 10:1 read-to-write ratio
- Per-second rate: ~11,600 read requests/second

**Storage Requirements (10-year lifespan):**
- Total records: 365 billion (100M × 365 × 10)
- Average URL length: 100 bytes
- Total capacity needed: 36.5 terabytes

---

## Step 2: Proposing High-Level Design

### API Endpoints

**URL Shortening Endpoint:**
```
POST api/v1/data/shorten
- Request parameter: {longUrl: longURLString}
- Returns: shortURL
```

**URL Redirecting Endpoint:**
```
GET api/v1/shortUrl
- Returns: longURL for HTTP redirection
```

### URL Redirecting Flow

When users access a shortened URL via browser, the service responds with an HTTP redirect response, converting the short alias to its original long form.

**HTTP Response Details:**
The server responds with appropriate headers including:
- Status code (301 or 302)
- Location header containing the original URL
- Cache-control directives

**301 vs 302 Redirect Comparison:**

| Aspect | 301 Redirect | 302 Redirect |
|--------|--------------|--------------|
| Semantics | Permanent move | Temporary move |
| Browser Caching | Browser caches the mapping | Browser doesn't cache |
| Server Load | Reduced (subsequent requests bypass shortener) | Higher (all requests hit shortener) |
| Analytics | Limited click tracking | Comprehensive click tracking possible |

**Implementation Approach:**
- Utilize hash tables storing `<shortURL, longURL>` pairs
- Retrieve longURL using lookup: `longURL = hashTable.get(shortURL)`
- Execute URL redirect after retrieval

### URL Shortening Overview

The core requirement involves designing a hash function that maps lengthy URLs to concise representations. The pattern follows: `www.tinyurl.com/{hashValue}`

**Hash Function Requirements:**
- Each longURL must consistently hash to one hashValue
- Each hashValue must be reversibly mappable to the original longURL

---

## Step 3: Design Deep Dive

### Data Model

Rather than in-memory hash tables, production systems use relational databases for persistence and scalability.

**Database Schema:**

| Column | Type | Purpose |
|--------|------|---------|
| id | Primary Key | Unique identifier |
| shortURL | String | Abbreviated URL |
| longURL | String | Original URL |

### Hash Function Design

#### Determining Hash Value Length

The hashValue character set includes: 0-9, a-z, A-Z = 62 possible characters.

**Calculating Required Length:**
Find the smallest *n* where `62^n ≥ 365 billion`

| Length (n) | Maximum URLs Supported |
|------------|------------------------|
| 1 | 62 |
| 2 | 3,844 |
| 3 | 238,328 |
| 4 | 14,776,336 |
| 5 | 916,132,832 |
| 6 | 56,800,235,584 |
| **7** | **~3.5 trillion** |
| 8 | 218,340,105,584,896 |

**Result:** A 7-character hash value suffices for 365 billion URLs.

#### Approach 1: Hash + Collision Resolution

**Strategy:** Use established hash functions (CRC32, MD5, SHA-1) and extract the first 7 characters.

**Example Hash Results for:** `https://en.wikipedia.org/wiki/Systems_design`

| Function | Output (Hexadecimal) |
|----------|---------------------|
| CRC32 | 5cb54054 |
| MD5 | 5a62509a84df9ee03fe1230b9df8b84e |
| SHA-1 | 0eeae7916c06853901d9ccbefbfcaf4de57ed85b |

**Collision Handling Process:**
1. Hash the longURL and extract the first 7 characters
2. Check database for existence of this shortURL
3. If collision detected, append a predefined string to the original longURL
4. Re-hash and repeat until no collision occurs
5. Save the collision-free mapping to database

**Performance Optimization:**
Employ Bloom filters—a space-efficient probabilistic technique to test if an element is a member of a set—to reduce database queries for collision checking.

**Tradeoffs:**
- **Advantages**: Fixed short URL length, no unique ID generator dependency
- **Disadvantages**: Collisions possible, requires collision resolution logic

#### Approach 2: Base 62 Conversion

**Concept:** Convert sequential unique IDs to base 62 representation using the 62-character alphabet.

**Character Mappings:**
- 0-9 → represent values 0-9
- a-z → represent values 10-35
- A-Z → represent values 36-61

**Conversion Example:**
Converting decimal ID 11157 to base 62:
- 11157 ÷ 62 = 179 remainder 59 (X)
- 179 ÷ 62 = 2 remainder 55 (T)
- 2 ÷ 62 = 0 remainder 2 (2)
- Result: "2TX" (reading remainders bottom-to-top)

**Mathematical Representation:**
11157₁₀ = 2 × 62² + 55 × 62¹ + 59 × 62⁰ = [2, T, X] in base 62

**Result:** Short URL becomes `https://tinyurl.com/2TX`

**Tradeoffs:**
- **Advantages**: No collisions (IDs are unique), fixed (no) collision resolution needed
- **Disadvantages**: Variable URL length grows with ID, security risk (next URL predictable), depends on a unique ID generator

#### Comparison Summary

| Factor | Hash + Collision | Base 62 Conversion |
|--------|-----------------|-------------------|
| Short URL Length | Fixed | Variable (increases with ID) |
| Unique ID Generator | Not required | Required |
| Collision Possibility | Yes, needs resolution | No |
| Predictability | Unpredictable | Predictable (security risk) |

### URL Shortening Deep Dive

**Chosen Approach:** Base 62 conversion.

**Process Flow:**

1. **Input**: Receive longURL from client
2. **Database Check**: Query whether longURL already exists in database
3. **Existing Match**: If found, retrieve and return corresponding shortURL
4. **New URL Generation**: If not found, use unique ID generator to create a new ID
5. **Base 62 Conversion**: Transform ID to shortURL via the base 62 conversion algorithm
6. **Database Storage**: Save ID, shortURL, and longURL as a new database row

**Concrete Example:**

Input longURL: `https://en.wikipedia.org/wiki/Systems_design`

Process:
- Unique ID generated: 2009215674938
- Base 62 conversion result: "zn9edcu"
- Database entry created:

| id | shortURL | longURL |
|---|----------|---------|
| 2009215674938 | zn9edcu | `https://en.wikipedia.org/wiki/Systems_design` |

**Unique ID Generator Significance:**
In a highly distributed environment, implementing a unique ID generator is challenging. The design references the dedicated chapter "Design A Unique ID Generator in Distributed Systems" for implementation strategies such as Twitter Snowflake or similar distributed ID systems.

### URL Redirecting Deep Dive

**Architecture Pattern:**
Since read operations vastly outnumber writes (10:1 ratio), implement caching to maximize performance.

**System Components:**
1. **Load Balancer**: Distributes incoming requests across web servers
2. **Web Servers**: Process requests (stateless for horizontal scaling)
3. **Cache Layer**: Stores frequent `<shortURL, longURL>` mappings for rapid retrieval
4. **Database**: Persistent storage for all mappings

**Request Flow:**

1. User navigates to shortened URL: `https://tinyurl.com/zn9edcu`
2. Load balancer routes request to an available web server
3. Web server checks cache for the shortURL
4. **Cache Hit**: Return longURL directly to user
5. **Cache Miss**: Query database for longURL
6. **Database Miss**: Invalid shortURL (user error or expired)
7. Return appropriate HTTP redirect response to user

**Performance Optimization:**
Caching dramatically reduces database load since redirects are read-heavy operations. Popular shortened URLs remain in cache, eliminating repeated database queries.

---

## Step 4: Wrap-Up and Additional Considerations

### Rate Limiting

Protect against malicious URL creation floods by implementing request throttling based on IP address or other filtering criteria. Reference the dedicated "Design a rate limiter" chapter for implementation details.

### Web Server Scaling

The stateless nature of web servers enables horizontal scaling—adding or removing instances based on demand without architectural complexity.

### Database Scaling

Production systems employ:
- **Replication**: Distribute read load across replicas
- **Sharding**: Partition data by ID or other attributes for horizontal scaling

### Analytics Integration

Integrate analytics to track:
- Click-through rates per shortened URL
- Temporal click patterns
- Geographic or device-based click sources
- User engagement metrics

### System Qualities

**Availability, Consistency, and Reliability:** These foundational principles merit detailed review in the "Scale From Zero To Millions Of Users" chapter, covering:
- Redundancy and failover mechanisms
- Data consistency strategies
- Fault tolerance patterns

---

**Conclusion:** The design balances simplicity, performance, and scalability through strategic technology choices including base 62 conversion for collision-free ID mapping, cache layers for read optimization, and database design for persistence at scale.

---

# Interview-Grade Enrichment

## Back-of-the-Envelope Math

### Constants and assumptions

| Symbol | Value | Meaning |
|--------|-------|---------|
| W | 100M / day | new URLs written |
| R | 10:1 read-to-write | traffic ratio |
| Avg URL bytes | 100 B | encoded |
| Avg short key | 7 chars | base-62 |
| DB row | ~250 B | metadata + indices |
| Lifespan | 10 yr | planning horizon |
| Total records | 365 B | 100M * 365 * 10 |

### Why a 7-character key

We need a key space large enough to hold 365 B unique IDs without exhausting the alphabet. With 62 characters and length n, capacity = 62^n. Solving 62^n >= 365 * 10^9:

  log10(62^n) = n * log10(62) = n * 1.7924
  log10(365 * 10^9) = 11.562

  n >= 11.562 / 1.7924 = 6.45

So n=7 is the smallest safe integer. n=6 gives 56.8 B — barely above the requirement and with zero headroom. n=7 gives 3.52 trillion — about 9.6x headroom, which is the right safety margin for traffic spikes, retries, and the rare collisions that sneak through.

At n=7, average URL is `https://t.co/XXXXXXX` — 22 characters total. That's short enough for SMS (160-char limit) and tweet-friendly.

### Per-second and peak traffic

Average writes: 100M / 86,400 = 1,157 writes/sec.
Average reads: 11,570 reads/sec.

Peaks are typically 3-5x average in real consumer workloads (US morning + evening peaks). Design for peak:

  Peak writes:   ~5,000 / sec
  Peak reads:    ~50,000 / sec

With cache absorbing 95% of reads, the database sees:

  DB writes:  5,000 / sec
  DB reads:   50,000 * 0.05 = 2,500 / sec

That's trivially within the capability of a sharded MySQL/PostgreSQL cluster.

### Storage math over 10 years

  Records:        365 B
  Bytes per row:  250 B (with metadata, indices, soft-delete marker)
  Total storage:  365 B * 250 B = 91.25 TB

With 3x replication: ~275 TB. Distributed across 30 nodes at 10 TB each — fits comfortably.

But hot data (last 90 days) is 100M * 90 = 9 B records, ~2.25 TB. That fits in a single high-memory instance or a small Redis cluster. Cold data (>90 days) goes to cheaper storage.

### Bandwidth math

Reads at 50,000/sec, each returning ~100 bytes for the long URL plus ~22 bytes for headers:
  Read bandwidth:  50,000 * 122 B = 6.1 MB/s outbound

Writes at 5,000/sec, each request/response ~300 bytes:
  Write bandwidth: 5,000 * 300 B = 1.5 MB/s

Both fit easily on a single 10 Gbps link with 1000x headroom. The bottleneck is never network.

### Cache hit ratio and what it means

Cache key: the 7-character short URL.
Hot key set: a small fraction of URLs account for most traffic (think viral tweets, marketing campaigns). Empirically, 1% of keys account for ~50% of traffic — the same Pareto pattern as KV stores.

If we cache the top 1% of URLs (3.65 B keys at 100 bytes each = 365 GB), we serve roughly 50% of reads from cache. Cache hit ratio: ~50% with 365 GB of cache.

To hit 95% cache hit, we'd need to cache ~10% of URLs (36.5 B keys = 3.65 TB), which is still feasible with Redis Cluster or memcached.

### Cost of failure: cache outage

If the cache layer goes down for 1 hour during peak:
  50,000 reads/sec * 3,600 sec = 180 M reads hit DB directly
  At 1 ms per indexed point lookup: 180,000 sec of DB CPU = 50 DB-hours.

If you provision DB for normal load (2,500 reads/sec), this is a 20x spike. Either your DB has to be massively over-provisioned, or it falls over. The right answer: a multi-tier cache (CDN edge + regional cache + local in-process) so a single cache tier failing doesn't take the system down.

### Bitly's reported scale

Bitly publicly disclosed (2011-ish era) handling ~6 billion clicks per month and ~1 billion short URLs created to date. At the time, that's ~2,000 clicks/sec average and ~30 clicks/sec writes — about an order of magnitude above our assumptions. The architecture described in this chapter scales to that with sharding.

---

## ASCII Architecture Diagrams

### Diagram 1: High-level system block diagram

```
                          +-----------+
                          |  Browser  |
                          | (client)  |
                          +-----+-----+
                                |
                                v
                      +-------------------+
                      |   DNS / Anycast   |
                      +-------------------+
                                |
                                v
                +-------------------------------+
                |   CDN edge (e.g. CloudFront,  |
                |   Cloudflare)                |
                |   - serves static assets     |
                |   - optional redirect cache  |
                +-------------------------------+
                                |
                                v
                +-------------------------------+
                |   L7 Load Balancer (HAProxy,  |
                |   Envoy, NGINX, ALB)          |
                +-------------------------------+
                                |
              +-----------------+-----------------+
              |                 |                 |
              v                 v                 v
        +----------+      +----------+      +----------+
        | App srv  |      | App srv  |      | App srv  |   <-- stateless
        | (write   |      | (read    |      | (read    |
        |  path)   |      |  path)   |      |  path)   |
        +----+-----+      +----+-----+      +----+-----+
             |                 |                 |
             v                 v                 v
        +---------------------------------------------+
        |      Redis / Memcached (read cache)         |
        +---------------------------------------------+
             |                                 |
             v                                 v
   +--------------------+             +---------------------+
   |  Write DB cluster  |             |   Read DB replicas  |
   |  (Postgres /       |             |   (sharded, async   |
   |   MySQL primary)   |             |    replication)     |
   +--------------------+             +---------------------+
             |
             v
   +--------------------+
   |  Async pipeline    |
   |  (Kafka / SQS)     |
   +--------------------+
             |
             v
   +--------------------+
   | Analytics store    |
   | (ClickHouse,       |
   |  BigQuery, etc.)   |
   +--------------------+
```

### Diagram 2: Shorten (write) sequence diagram

```
  Client    AppServer   IDService    Cache    WriteDB    AsyncQ
    |           |            |          |         |          |
    |--POST---->|            |          |         |          |
    | /shorten  |            |          |         |          |
    | {longUrl} |            |          |         |          |
    |           |-- check dedup in cache (longUrl hash)-->|
    |           |            |          |         |          |
    |           |<- miss ----|----------|         |          |
    |           |            |          |         |          |
    |           |-- get next ID ---->    |         |          |
    |           |            |          |         |          |
    |           |<- Snowflake id (e.g. 2.0e12) --|         |
    |           |            |          |         |          |
    |           |-- encode base62 (e.g. "zn9edcu") -|       |
    |           |            |          |         |          |
    |           |-- INSERT row ----------------->  |         |
    |           |            |          |         |          |
    |           |-- SET cache (shortUrl -> longUrl) ---->   |
    |           |            |          |         |          |
    |           |-- emit click event (creation) --->        |
    |           |            |          |         |          |
    |<- 201 ----|            |          |         |          |
    | {shortUrl}            |          |         |          |
    |           |            |          |         |          |
```

### Diagram 3: Redirect (read) sequence diagram

```
  Browser     Edge      AppSrv      Cache      ReadDB
    |          |          |           |            |
    | GET t.co/zn9edcu   |           |            |
    |-------->|--------->|           |            |
    |          |          |-- GET zn9edcu ->|     |
    |          |          |           |            |
    |          |          |<- hit ----|            |
    |          |          |  (longUrl)|            |
    |          |          |           |            |
    |          |<- 302 ---|<- Location: longUrl --|
    |          |  Location: longUrl  |            |
    |<---------|          |           |            |
    |          |          |           |            |
    | (browser follows)  |           |            |
    |          |          |           |            |
    | GET longUrl         |           |            |
    |---------------------|---------> (origin)    |

  Cache miss path:
    AppSrv -> Cache (miss) -> ReadDB (query by shortURL)
           -> AppSrv populates cache with TTL
           -> AppSrv returns 302 to browser
```

### Diagram 4: Base-62 conversion walkthrough

```
  Decimal ID:    11157

  Step 1: 11157 / 62 = 179  remainder 59  -> 'X'
  Step 2:  179 / 62 =   2  remainder 55  -> 'T'
  Step 3:    2 / 62 =   0  remainder  2  -> '2'

  Read remainders bottom-to-top: "2TX"

  Character mapping table (constant):
    0-9  -> '0'..'9'         (offset 0)
    10-35 -> 'a'..'z'        (offset 10)
    36-61 -> 'A'..'Z'        (offset 36)

  Reverse mapping (decode):
    '2' -> 2, 'T' -> 55, 'X' -> 59
    id = 2*62^2 + 55*62^1 + 59*62^0
       = 2*3844 + 55*62 + 59
       = 7688 + 3410 + 59
       = 11157  (matches)
```

### Diagram 5: Collision resolution with hash+counter

```
  longURL = "https://example.com/a"

  Attempt 1:  hash = MD5(longURL)[:7] = "abc1234"
              DB lookup: SELECT WHERE short='abc1234' -> 0 rows
              INSERT (id=N, short='abc1234', long=...)
              OK.

  longURL = "https://example.com/b"  (different URL, same hash)

  Attempt 1:  hash = MD5(longURL)[:7] = "abc1234"
              DB lookup: SELECT WHERE short='abc1234' -> 1 row
              COLLISION.
  Attempt 2:  hash = MD5(longURL + "salt1")[:7] = "xyz9876"
              DB lookup: SELECT WHERE short='xyz9876' -> 0 rows
              INSERT (id=N+1, short='xyz9876', long=...)
              OK.

  Bloom filter optimization: cache the membership of every
  short URL. Bloom lookup before DB: O(1) and avoids DB hit
  for the common "no collision" case. False positive rate
  ~1% with proper sizing.
```

---

## Trade-off Tables

### Table 1: Short-key generation strategies

| Strategy | Length | Collisions | Predictability | Throughput | Complexity |
|---|---|---|---|---|---|
| Hash + collision (MD5/SHA-1 truncate) | Fixed | Probabilistic, mitigated | Low (random) | High (one DB lookup per write) | Medium |
| Base 62 from auto-increment ID | Variable, growing | Impossible (unique ID) | High (next ID = next+1) | High (no collision check) | Low |
| Random + check + retry | Variable | Probabilistic | Medium | Medium (depends on retry count) | Low |
| UUIDv4 truncated to 7 base-62 chars | Fixed | High (only 3.5T space) | High | High | Low |
| Snowflake ID base-62 | Variable, growing | Impossible | Medium (worker ID + ms visible) | High | Low |
| Pre-allocated ranges (segment) | Variable | Impossible | Medium | Very high | Medium |

### Table 2: Read-path caching options

| Cache layer | Hit rate | Latency | Cost | Survives origin failure? | Used for |
|---|---|---|---|---|---|
| In-process LRU | ~10-20% | <1 ms | Free | No (process-level) | Hottest keys |
| Local Redis | ~50% | 1-2 ms | Low | No (single instance) | Shared per DC |
| Redis Cluster | ~70-80% | 2-5 ms | Medium | Partial (single shard) | Cross-instance |
| CDN edge | ~30-50% | 10-50 ms | Medium | Yes (origin behind) | Geographic distribution |
| Multi-tier (edge + regional + local) | ~95%+ | Variable | High | Yes | Production deployments |

### Table 3: Redirect HTTP status codes

| Status | Semantics | Browser cache | Server load | Analytics | Use when |
|---|---|---|---|---|---|
| 301 Moved Permanently | URL moved forever | Aggressive | Low (browser skips next time) | Poor (no subsequent request) | Static redirects, SEO-friendly |
| 302 Found | URL moved temporarily | Conservative | High (every click hits server) | Excellent | Tracking critical, time-limited |
| 303 See Other | After a non-GET | Never | High | Excellent | Form-POST results, rare for URL shorteners |
| 307 Temporary Redirect | Preserves HTTP method | Conservative | High | Excellent | API redirects |
| 308 Permanent Redirect | Permanent, preserves method | Aggressive | Low | Poor | Static redirects for APIs |

### Table 4: Database choices

| Store | Use case | Reads | Writes | Cost | Examples |
|---|---|---|---|---|---|
| MySQL/Postgres | OLTP, primary store | Indexed lookups fast | OK | Low | Most URL shorteners |
| DynamoDB / Cassandra | Auto-sharded, key-value lookups | Eventually consistent reads possible | High throughput | Medium | Bitly, production scale |
| Redis Cluster | Hot key cache | Sub-ms | High | Low | Cache layer, not primary |
| FoundationDB | Transactional KV | Strongly consistent | High | Medium | When multi-key atomicity matters |
| Object storage (S3) + index in DynamoDB | Cold storage | Slow first, then cached | OK | Very low | Archived URLs |

---

## Real-World Case Studies

### Case study 1 — bit.ly

bit.ly launched in 2008 and grew to billions of URLs. Their architecture (publicly described in talks and engineering blogs) uses: a custom base-62 ID generation scheme similar to the chapter's approach, sharded MySQL for primary storage, Redis for cache, and heavy analytics on the click stream. They invested heavily in analytics (country, referrer, time of day) early on, which became a primary value proposition beyond simple URL shortening. Lessons: (1) base-62 from a numeric ID is the right default for low collision risk, (2) the cache hit ratio determines your database cost — invest in caching aggressively, (3) analytics is a feature, not an afterthought.

### Case study 2 — TinyURL

TinyURL (launched 2002) is one of the original URL shorteners. It uses a deterministic hash of the long URL (not a counter), which means the same long URL always produces the same short URL. This means idempotency is built in: submitting the same long URL twice returns the same short URL. The cost is higher collision probability, but TinyURL mitigates with a salt counter. The benefit: no unique ID generator needed, which made the early system trivially simple. Lesson: deterministic hashing gives you free idempotency, which is huge for cache hit rate and storage deduplication.

### Case study 3 — Twitter t.co

Twitter operates t.co, a URL shortener that wraps every URL shared in tweets. Why? Three reasons: (1) character count — short URLs let users fit more text in 140 (now 280) characters; (2) security — Twitter inspects the destination for malware and phishing before the user clicks; (3) analytics — Twitter knows which links get clicked and from where, even if the destination is off-platform. t.co runs at Twitter's scale: billions of short URLs created and tens of billions of clicks per month. The lesson: the value of a URL shortener at scale isn't the shortening — it's the visibility and control over what users actually click.

### Case study 4 — goo.gl (Google's discontinued shortener)

Google's goo.gl ran from 2009 to 2019 before being shut down. Google's approach was different from TinyURL/bit.ly: they used a hash-based scheme (not a counter) so the same long URL always produced the same short URL. Combined with browser-side prefetching in Chrome and Google's CDN, goo.gl redirects had very low latency. They also had built-in spam detection and warning pages for suspicious destinations. Lesson: owning both the shortener AND the browser (Chrome) lets you prefetch and validate redirects at the edge, achieving latency that's hard to match otherwise.

### Case study 5 — Amazon's short links (amzn.to)

Amazon runs amzn.to for product links, mainly for affiliate tracking and analytics. Each amzn.to URL encodes an affiliate ID and product ID. Amazon's scale: hundreds of millions of short URLs across millions of products, with click volumes into the billions per month. The interesting wrinkle: amzn.to URLs are NOT pure redirects — they include a server-side click attribution step (which affiliate sent the click) before the 302 to the product page. This means even a brief server-side processing window is acceptable because the affiliate data is high-value. Lesson: when your shortener is also doing attribution or other server-side work, latency SLOs can be looser than pure redirects.

### Case study 6 — YouTube youtu.be

YouTube's youtu.be short URLs map directly to video IDs (11-character base-64 strings that match the v= parameter in full YouTube URLs). The mapping is deterministic: video ID "dQw4w9WgXcQ" always corresponds to the same video. This means youtu.be can be implemented as a simple CDN redirect with no database lookup at all — the video ID is the entire key, and the destination URL can be reconstructed as `https://www.youtube.com/watch?v=<id>`. Lesson: when your short key is the same length as the long URL's "meaningful" identifier, you can skip the lookup entirely. Many modern shorteners aspire to this design.

---

## Common Pitfalls & Failure Modes

### Pitfall 1 — Predictable short URLs are enumerable

With base-62 from a sequential counter, the short URL `aaaaaaa` came before `aaaaaab`. An attacker who creates a few short URLs can guess the next ones and:
- Enumerate all URLs created in a time window (privacy leak).
- Pre-register short URLs for spam or phishing.
- Profile user creation rates by watching ID gaps.

Mitigations: (1) start the counter at a random base to obscure the current value, (2) use a non-sequential ID generator like Snowflake (timestamps make the next ID less predictable), (3) rate-limit short URL creation per IP/user. Twitter learned this lesson when researchers enumerated millions of tweet IDs.

### Pitfall 2 — Cache stampede on hot key

When a viral URL hits, the cache is hot for that one short URL. If the cache entry expires, every subsequent request races to the database to repopulate it. With thousands of requests per second for one key, you can DoS your own database. Mitigations: (1) probabilistic early expiration — refresh the cache before TTL expires, on a random subset of requests; (2) request coalescing — only one request hits the DB, others wait for the result; (3) "stale-while-revalidate" pattern — serve the stale value while refreshing.

### Pitfall 3 — Collision storms with hash-based generation

With base-62 truncation of MD5/SHA-1, collision probability is non-zero. At 100M URLs/day and a 7-char space (~3.5T), you're at ~3% utilization — collisions are rare. But if you go to 1B URLs/day, you're at 30% utilization, and birthday paradox collisions become statistically common. At that scale, hash+collision starts showing pathological behavior (many attempts per insert). The fix: switch to a counter-based or Snowflake-based scheme before collision rates hurt write latency.

### Pitfall 4 — Analytics pipeline swallows production traffic

A common mistake is to write click events synchronously to the analytics store. If the analytics store slows down, the redirect path slows down. If it fails, redirects fail. Mitigations: (1) emit click events to a queue (Kafka, SQS, Kinesis) and process async, (2) batch events client-side and flush periodically, (3) use a separate analytics pipeline entirely (fire-and-forget HTTP to a logging service). Twitter learned this lesson early — their analytics is on a separate code path with its own SLOs.

### Pitfall 5 — DB write amplification on sharding by short URL hash

If you shard by short URL hash (modulo number of shards), each insert and each lookup uses the same shard. This means: (1) range scans by short URL prefix are impossible — every shard needs to be queried; (2) during a shard rebalance, every key potentially moves. Better to shard by the underlying numeric ID (Snowflake ID, auto-increment) so the shard routing is consistent and ID ranges correspond to time ranges.

### Pitfall 6 — 301 vs 302 confusion breaking analytics

If you serve 301 (permanent), browsers cache the redirect aggressively and never come back. You lose all subsequent click data. For analytics-driven services, 302 (temporary) is almost always correct. The SEO implications of 301 vs 302 are small for shorteners (the long URL is the canonical destination for SEO purposes anyway). Lesson: choose 302 unless you have a specific reason for 301.

### Pitfall 7 — Long URL validation gaps

Allowing arbitrary long URLs creates phishing, malware, and abuse vectors. Common gaps: (1) accepting URLs to internal networks (SSRF), (2) accepting javascript: URIs, (3) accepting URLs to private IP ranges, (4) accepting URLs longer than reasonable (e.g., 2 KB). Validate against an allowlist of schemes (http, https), check the destination IP isn't in private ranges, and enforce a max length.

### Pitfall 8 — Abuse — malicious short URLs used for phishing

Short URLs are a perfect phishing vector because the destination is hidden behind an opaque string. Mitigations: (1) reputation scoring per long URL — known-bad URLs get a warning interstitial; (2) link to a "report abuse" flow; (3) maintain a blacklist of destination domains; (4) for high-risk URLs, serve an interstitial warning page instead of a direct redirect. Twitter, Facebook, and Google all run link-scanning services (Twitter's link classifier, Google's Safe Browsing) that warn before redirecting.

### Pitfall 9 — ID generation becomes the bottleneck

If the ID service (Snowflake, ticket server) is slow or down, the entire shortener is down for writes. Reads can continue from cache. Mitigations: (1) deploy the ID service redundantly across multiple AZs, (2) batch ID requests (allocate ranges of 1000 IDs at a time), (3) fall back to a slower ID source if the primary fails (e.g., random UUIDv4 + collision check).

---

## Interview Q&A

### Q1 — Why pick base-62 conversion over hash + collision resolution?

**Answer sketch:** Three reasons. (1) No collisions by construction — each ID is unique by ID-generator guarantee, so the short URL is unique without retry logic. (2) Simpler code path — no retry loop, no collision detection, no Bloom filter needed. (3) Predictable storage growth — you can size your shards based on ID range. The tradeoff: (a) variable URL length as the counter grows (mitigated by planning for ~7 chars at 10-year scale), (b) predictability of next IDs (mitigated by randomizing the starting counter value or using Snowflake's time-based IDs). For most production use cases, base-62 wins because collision-free simplicity is worth more than fixed-length URLs.

### Q2 — What's the difference between 301 and 302 for redirects? When do you pick which?

**Answer sketch:** 301 (Moved Permanently) tells the browser to cache the redirect and never come back to the shortener. 302 (Found, technically "Temporary Redirect") tells the browser to ask the shortener every time. Pick 301 when (a) the redirect is genuinely permanent and (b) you don't need analytics on subsequent clicks. Pick 302 when (a) you want analytics on every click, (b) the destination might change, or (c) you want to revoke a URL by changing the mapping. For a URL shortener, 302 is the right default because you want analytics and you want to be able to update the destination.

### Q3 — How would you handle 10x traffic (1 billion URLs/day, 100K redirects/sec)?

**Answer sketch:** Three bottlenecks to address: (1) ID generation — at 1B/day = ~12K writes/sec average, you're still well within Snowflake's per-node capacity. Add more nodes if needed; the bottleneck is not the ID service. (2) Database — at 100K reads/sec with 95% cache hit, DB sees 5K reads/sec. Sharded Postgres or DynamoDB handles that. The bigger issue is write throughput at 12K/sec sustained; sharding by ID range helps. (3) Cache — at 100K reads/sec, a single Redis instance is too small. Redis Cluster with sharding, plus a CDN edge cache for geographic distribution, is the production answer. At 100x, you're looking at multi-region active-active, sharded read replicas per region, and possibly a custom analytics pipeline.

### Q4 — A user reports their short URL returns the wrong destination. How do you debug?

**Answer sketch:** Three steps. (1) Check the cache — is the cached long URL correct? If the cache is stale, the fix is to invalidate it (DEL on the cache key). (2) Check the database — query `SELECT * FROM urls WHERE short_url = ?` and confirm the stored long URL. If the DB has the right value but the cache was stale, the bug is cache invalidation. (3) Check the ID generator — if two URLs got the same short URL (collision or duplicate worker ID), you have a generation bug. Add monitoring: every short URL should be unique, and every (short, long) mapping should be consistent across cache and DB. In production, you'd also check: was this short URL ever modified? (Most designs forbid updates, but the rule should be enforced at the DB level with no UPDATE grants on the URL table.)

### Q5 — How would you design for global (multi-region) deployment?

**Answer sketch:** Three layers. (1) DNS/Anycast routing: short URL requests go to the nearest region via geoDNS or anycast. (2) Per-region cache and DB: each region has its own cache cluster and DB replicas. Reads are local — no cross-region latency. (3) Cross-region replication: writes propagate to other regions via async replication (DynamoDB global tables, Spanner, or a custom CDC pipeline). The tradeoff: writes are eventually consistent across regions — a URL created in us-east might not be visible in eu-west for 100-500 ms. That's acceptable because the common case is "create then immediately click" within the same region. The uncommon case (cross-region click within the replication lag) is rare enough to tolerate. For strong consistency, you can use synchronous cross-region replication, but at the cost of write latency.

### Q6 — How do you handle a URL that points to malware or phishing content?

**Answer sketch:** Three layers of defense. (1) At creation time: scan the destination against a threat intelligence feed (Google Safe Browsing, PhishTank, your own list). If the destination is flagged, reject the creation or quarantine the URL. (2) At click time: even for URLs created before they became malicious, check the destination against the threat feed on each click (cache the result for a few minutes). If flagged, serve an interstitial warning page. (3) User-driven: provide a "report this URL" mechanism that escalates to human review or auto-blacklist. The right answer in production: integrate with a third-party link scanner (like Google's Web Risk API) for the destination check, and serve a warning interstitial (200 OK with a "this URL is flagged" page) instead of a 302 redirect when the destination is risky.

### Q7 — Walk me through the request flow when a user clicks a short URL.

**Answer sketch:** (1) Browser resolves `t.co` via DNS to the nearest CDN edge. (2) CDN edge forwards the request to a regional load balancer (or serves the redirect from its own cache if hit). (3) Load balancer routes to one of N stateless app servers. (4) App server checks local cache (in-process LRU) for the short URL. If hit, return 302 with the long URL. (5) If miss, app server queries Redis cache. If hit, return 302 and populate local cache. (6) If Redis miss, app server queries the read DB replica. (7) DB returns the long URL. App server populates Redis with TTL and returns 302. (8) In parallel (async), app server emits a click event to Kafka for analytics — does not block the response. (9) Browser follows the 302 Location header to the long URL origin. Total latency target: p99 < 50 ms for the redirect, with cache hit being the common case.

---

## Key Terms / Glossary

| Term | Precise definition | Common misconception |
|---|---|---|
| URL shortener | Service that maps a long URL to a short alias and back | That it's just a redirect (it often includes analytics and abuse prevention) |
| Base-62 | A positional number system using 0-9, a-z, A-Z (62 chars) | That base-62 is the only option (base-36, base-64 are also used) |
| Short URL / short key | The compact alias used in the redirect | That it must be a fixed length (length can grow with ID space) |
| 301 redirect | "Moved Permanently" — browser caches aggressively | That 301 means the URL changed (it means the URL is now elsewhere forever) |
| 302 redirect | "Found" / "Temporary Redirect" — browser does not cache | That 302 is wrong for permanent moves (302 is correct when you want server-side control) |
| Collision | Two long URLs producing the same short URL | That collisions only matter for hash-based schemes (they can also occur if the ID generator has a bug) |
| Birthday paradox | Probability of collision rises sharply as you fill a hash space | That 50% utilization means 50% collision probability (it's much higher — ~40% at 50% fill) |
| Cache stampede | When a hot cache entry expires and many requests race to repopulate it | That high cache hit ratio prevents stampedes (the stampede happens DURING repopulation) |
| Request coalescing | Synchronizing multiple requests for the same key so only one hits the DB | That it's the same as caching (it's an explicit single-flight pattern) |
| Idempotency | Property that the same operation applied multiple times produces the same result | That idempotency requires coordination (a deterministic hash achieves it locally) |
| TinyURL-style hashing | Deterministic hash of the long URL (no counter) | That it eliminates collisions (birthday paradox still applies) |
| Bitly-style counter | Auto-incrementing ID converted to base-62 | That the counter must start at 1 (you should randomize the starting value to obscure creation order) |
| Affiliate link | A URL that includes an identifier for the referrer, often via a shortener | That affiliate links are just regular redirects (they often include attribution processing) |
| Safe Browsing | Google's API that flags known-malicious URLs | That it's the only option (PhishTank, Web of Trust, and your own lists are alternatives) |
| SSRF | Server-Side Request Forgery — making the server request internal resources | That URL shorteners are immune (they need to validate destinations to prevent SSRF) |
| Cache TTL | Time-to-live — how long a cached entry remains valid | That longer TTL is always better (longer TTL = stale data, more stampede risk) |
| Probabilistic early expiration | Refreshing cache entries before their TTL, on a random subset | That it's complicated to implement (a few lines in any language) |

---

## References

- TinyURL public documentation and behavior
- Bitly engineering blog (historical) — architecture, scaling
- Twitter t.co engineering — link wrapping, security
- Google goo.gl (archived) — link safety integration
- YouTube help docs — youtu.be format and behavior
- RFC 7231 — HTTP/1.1 semantics (301, 302 definitions)
- Cloudflare Workers / Fastly edge computing — modern CDN redirect patterns
- Bloom filter — Burton Bloom, 1970
- Snowflake — Twitter engineering (cross-referenced with chapter 8)
- Google Safe Browsing API — Web Risk
- Apache Kafka documentation — for async analytics pipelines