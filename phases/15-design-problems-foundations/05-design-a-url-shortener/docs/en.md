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
In a highly distributed environment, implementing a unique ID generator is challenging. The design references the dedicated chapter "Design A Unique ID Generator in Distributed Systems" for implementation strategies such as Snowflake or similar distributed ID systems.

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
