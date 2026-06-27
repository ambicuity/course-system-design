# Design A Web Crawler

## Chapter Overview

This chapter covers the design of a scalable web crawler system, addressing the complexity of building infrastructure to discover and index billions of web pages across the internet.

---

## Part 1: Problem Understanding and Scope

### What is a Web Crawler?

A web crawler (also called robot or spider) is automated software that discovers content by collecting web pages and following hyperlinks. Search engines like Google use crawlers for indexing purposes.

### Primary Use Cases

- **Search engine indexing**: Building searchable indexes of web content
- **Web archiving**: Preserving digital content for historical records
- **Web mining**: Extracting data and patterns from internet content
- **Web monitoring**: Detecting copyright violations and trademark infringements

### Design Scope Clarifications

The chapter illustrates asking clarifying questions:
- Primary purpose: Search engine indexing
- Scale: 1 billion pages per month
- Content types: HTML only
- Include newly added/edited pages: Yes
- Storage duration: 5 years
- Handle duplicates: Yes, ignore duplicate content

### Key Characteristics of Quality Crawlers

- **Scalability**: Handle billions of web pages through parallelization
- **Robustness**: Navigate bad HTML, unresponsive servers, malicious links, and crashes
- **Politeness**: Avoid overwhelming servers with excessive request rates
- **Extensibility**: Support new content types with minimal redesign

### Back-of-the-Envelope Estimations

**Traffic calculations:**
- 1 billion pages monthly ÷ 30 days ÷ 24 hours ÷ 3600 seconds = ~400 pages/second
- Peak QPS: 800 pages/second (2× average)

**Storage requirements:**
- Average page size: 500 KB
- Monthly storage: 1 billion × 500 KB = 500 TB
- Five-year storage: 500 TB × 12 months × 5 years = 30 PB

---

## Part 2: High-Level Architecture

### System Components

**Seed URLs**
Starting points for crawling. Selection strategies include:
- Geographic division (different countries have different popular sites)
- Topic-based division (shopping, sports, healthcare categories)

**URL Frontier**
Data structure storing URLs awaiting download, typically implemented as a FIFO queue. Handles two key states:
- URLs to be downloaded
- Already downloaded URLs

**HTML Downloader**
Retrieves web pages from the internet using the HTTP protocol. Interacts with the DNS resolver to convert domain names to IP addresses.

**DNS Resolver**
Translates URLs to IP addresses (e.g., www.wikipedia.org → 198.35.26.96). Acts as a performance bottleneck requiring optimization.

**Content Parser**
Validates and parses downloaded HTML to prevent malformed pages from consuming resources. Implemented as a separate component to avoid slowing crawlers.

**Content Seen?**
Detects duplicate content using hash comparisons rather than character-by-character comparison. Approximately 29% of the web pages are duplicated content.

**Content Storage**
Stores HTML pages using a hybrid approach:
- Disk storage for the majority of content (manageable scale)
- Memory caching for popular content (reduced latency)

**URL Extractor (Link Extractor)**
Parses HTML to extract hyperlinks, converting relative URLs to absolute URLs (e.g., /wiki/Example → https://example.com/wiki/Example).

**URL Filter**
Excludes unwanted content:
- Specific file extensions
- Error links
- Blacklisted sites
- Certain content types

**URL Seen?**
Tracking mechanism preventing duplicate URL processing. Implementations use:
- Bloom filters (space-efficient probabilistic data structure)
- Hash tables (faster lookup)

**URL Storage**
Database maintaining visited URLs for reference.

### Crawler Workflow (Steps)

1. Add seed URLs to URL Frontier
2. HTML Downloader fetches URLs from the frontier
3. DNS resolver provides IP addresses; download begins
4. Content Parser validates HTML pages
5. Parsed content passes to "Content Seen?" check
6. If content already exists, discard; if new, proceed to Link Extractor
7. Link Extractor pulls URLs from HTML
8. URL Filter removes unwanted links
9. "URL Seen?" component checks if URLs previously processed
10. Query URL Storage for history
11. New URLs added back to URL Frontier (cycle continues)

---

## Part 3: Deep Dive — Technical Implementation

### Graph Traversal: DFS vs BFS

**Depth-First Search (DFS)**
- Not recommended for web crawling
- Can result in excessively deep traversals

**Breadth-First Search (BFS)**
- Implemented via FIFO queue
- Standard for web crawlers
- Problems with naive implementation:
  - Floods the same host with requests (impolite behavior)
  - Ignores URL importance/priority

### URL Frontier Architecture

The URL Frontier manages three critical aspects: politeness, priority, and freshness.

#### Politeness Implementation

**Problem**: Naive BFS can send thousands of requests/second to a single website.

**Solution**: Host-based queue partitioning
- **Queue Router**: Directs URLs to host-specific queues
- **Mapping Table**: Maps hostnames to queue numbers
- **FIFO Queues (b1, b2...bn)**: Each queue contains only URLs from a single host
- **Queue Selector**: Assigns worker threads to queues
- **Worker Threads**: Download one page at a per host with a delay between requests

This ensures crawlers behave courteously by spacing requests.

#### Priority Management

**Problem**: Not all web pages have equal importance.

**Solution**: Prioritization system
- **Prioritizer Component**: Assigns priority scores (using PageRank, web traffic, update frequency)
- **Front Queues (f1-fn)**: Each maintains URLs at a specific priority level
- **Queue Selector**: Randomly selects from queues with bias toward higher priority

#### Freshness Optimization

Web content constantly changes. Optimization strategies:
- Recrawl based on historical update patterns
- Prioritize important pages for more frequent recrawling

#### Storage Architecture for URL Frontier

Given hundreds of millions of URLs, the hybrid approach:
- **Disk storage**: Majority of URLs (scalability)
- **Memory buffers**: Enqueue/dequeue operations
- **Periodic writes**: Buffer data flushed to disk regularly

### HTML Downloader Optimization

**Robots.txt Compliance**

The "Robots Exclusion Protocol" specifies crawler permissions:
```
User-agent: Googlebot
Disallow: /creatorhub/*
Disallow: /rss/people/*/reviews
```

Best practice: Cache robots.txt results periodically to avoid redundant downloads.

**Performance Optimizations:**

1. **Distributed Crawl**: Partition URL space across multiple servers with multiple threads each
2. **DNS Caching**: Maintain a domain-to-IP mapping cache (DNS lookups take 10-200ms); update via cron jobs
3. **Geographic Locality**: Deploy crawl servers near target website hosts
4. **Short Timeouts**: Set a maximum wait time for unresponsive servers

### Robustness Strategies

- **Consistent Hashing**: Distributes load; enables dynamic server addition/removal
- **Crawl State Persistence**: Save states/data to enable recovery from failures
- **Exception Handling**: Graceful error management prevents system crashes
- **Data Validation**: Prevents downstream errors from corrupted data

### Extensibility Design

System designed for modular expansion:
- PNG Downloader module (for image downloads)
- Web Monitor module (copyright/trademark protection)
- Pluggable architecture minimizes core system changes

### Problematic Content Detection and Avoidance

**1. Redundant Content**
- Use hashing/checksums to detect duplicates
- Nearly 30% of the web consists of duplicate pages

**2. Spider Traps**
Infinite loops caused by structural issues (e.g., `http://example.com/foo/bar/foo/bar/...`)
- Solution: Set maximum URL length limits
- Manual verification for website-specific traps
- Custom URL filters for known problematic sites

**3. Data Noise**
Filter out low-value content:
- Advertisements
- Code snippets
- Spam URLs

---

## Part 4: Additional Considerations

### Advanced Topics Not Fully Covered

**Server-Side Rendering**
Many modern websites use JavaScript/AJAX to generate links dynamically. Solution requires rendering pages before parsing.

**Anti-Spam Filtering**
With finite storage and resources, filtering low-quality/spam pages improves efficiency.

**Database Replication and Sharding**
Techniques for improving data layer availability, scalability, and reliability.

**Horizontal Scaling**
Large-scale crawls require hundreds or thousands of servers. Design principle: keep servers stateless.

**System Properties**
Core considerations for large-scale systems:
- Availability
- Consistency
- Reliability

**Analytics and Monitoring**
Data collection essential for system tuning and optimization.

---

## Key Design Tradeoffs

| Aspect | Consideration |
|--------|---------------|
| Memory vs Disk | Use disk for most data; memory buffers for performance |
| Breadth vs Depth | BFS preferred over DFS to avoid getting stuck in deep paths |
| Politeness vs Speed | Host-based queuing slows crawl but prevents server overload |
| Completeness vs Quality | Prioritization ensures important pages crawled more frequently |
| Storage vs Freshness | Recrawl strategies balance freshness against resource costs |

---

## Part 5: Back-of-the-Envelope Math (Interview-Grade)

The numbers in Part 1 are the textbook baseline. Senior interviews want you to defend those numbers with second-order reasoning and power-of-2 fluency. The full crawler at Google scale is roughly four orders of magnitude larger than the chapter scenario.

### Capacity ladder (powers of 2)

Start from the chapter baseline and step up:

```
Assumption:        1B pages / month
                   30 days × 86,400 s = 2,592,000 s/month  ≈ 2.6 × 10^6
Crawl rate (avg):  10^9 / 2.6 × 10^6 ≈ 386 pages/s  ≈ 400 pages/s
Peak (2× avg):     ~800 pages/s
Bytes/page (avg):  500 KB = 5 × 10^5 bytes
```

Step up to a search-engine scale crawl (Google disclosure estimates):

```
Crawl rate:        10,000 pages/s   ≈ 10^4  (≈ 25× the chapter scenario)
Bytes/page:        500 KB           ≈ 5 × 10^5
Per-second bytes:  10^4 × 5 × 10^5 = 5 × 10^9  = 5 GB/s   of raw content
Per-day bytes:     5 × 10^9 × 86,400 ≈ 4.3 × 10^14 = 430 TB/day
Per-year bytes:    430 TB × 365     ≈ 1.6 × 10^5 TB ≈ 157 PB/year
Storage over 5 y:  ≈ 785 PB (no compression; with 3:1 raw→indexed ≈ 260 PB)
```

Common Crawl disclosure (public dataset) is a useful real anchor:

```
Common Crawl (2024 monthly snapshot, public figures):
  - Raw web pages / month:  ~2.5–3 billion  (≈ 2.5 × 10^9)
  - Raw WARC compressed:    ~80–100 TB / month
  - Per page (uncompressed avg): ~150–250 KB
  - Annual raw crawl volume: ~1 PB / year compressed, multi-PB uncompressed
```

### Networking and bandwidth

```
Per-page bytes (avg):      500 KB
Pages/s (avg / peak):      400 / 800
Avg bandwidth:             400 × 500 KB = 200 MB/s ≈ 1.6 Gbps
Peak bandwidth:            800 × 500 KB = 400 MB/s ≈ 3.2 Gbps
With HTTP/2 + headers + retries (~1.5×):  ~5 Gbps peak
```

DNS, the hidden bottleneck:

```
DNS lookup per host (cold):  ~50–200 ms
Crawler fan-out across workers (say 1,000 workers):
  Per-worker DNS rate ≤ 5/s to stay under 1k QPS resolver limit
DNS cache hit rate target:  ≥ 80% (otherwise crawler stalls)
DNS cache size: ~10^7 hostnames × 100 B ≈ 1 GB (fits in RAM)
```

### Storage tiering math

```
Total 5-year raw:                 30 PB (chapter)  /  ~785 PB (search-scale)
Indexed (forward index) @ 30%:     9 PB / 235 PB
Compressed inverted index @ 5%:    1.5 PB / 39 PB
Per-shard (target 5 TB shards):    300 shards / 7,800 shards
Disk cost ($0.02/GB-month, S3 IA): $7,200 /mo  (chapter) / $190,000 /mo (search-scale)
```

### Fingerprint stores

```
URL deduplication (Bloom filter sizing):
  Target: 10^10 unique URLs, false-positive rate ε = 1%
  m = -n ln ε / (ln 2)^2  ≈ 10^10 × 4.6 / 0.48 ≈ 9.6 × 10^10 bits ≈ 12 GB
  k = -ln ε / ln 2  ≈ 7 hash functions

Content fingerprint (SimHash / SHA-256):
  SHA-256 truncated to 64 bits = 8 B per doc
  10^9 docs × 8 B = 8 GB (fits in RAM on a beefy box)
```

---

## Part 6: ASCII Architecture Diagrams

### 6.1 — End-to-end crawl pipeline (data-flow view)

```
                     ┌──────────────────────────────┐
                     │       Seed URL Source        │
                     │  (sitemaps, manual, prior    │
                     │   crawl log, link DB)        │
                     └──────────────┬───────────────┘
                                    │
                                    ▼
   ┌──────────────────────────────────────────────────────────┐
   │                    URL Frontier                          │
   │  ┌────────────┐  ┌────────────┐  ┌─────────────────────┐ │
   │  │ Prioritizer│  │ Host Queues│  │ Bloom / Hash Lookup │ │
   │  │  (f1..fn)  │  │  (b1..bn)  │  │   "URL Seen?"       │ │
   │  └─────┬──────┘  └─────┬──────┘  └──────────┬──────────┘ │
   │        └────────────────┴──────────────────┘            │
   └──────────────────────────┬───────────────────────────────┘
                              │  next URL + host
                              ▼
   ┌──────────────────────────────────────────────────────────┐
   │                   Fetcher (Worker)                        │
   │  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐   │
   │  │ robots.txt  │  │ HTTP/HTTPS   │  │ DNS resolver   │   │
   │  │ cache check │  │ client (TLS, │  │ (cached 80%+)  │   │
   │  │             │  │ retries)     │  │                │   │
   │  └──────┬──────┘  └──────┬───────┘  └────────┬───────┘   │
   │         └─────────────────┴───────────────────┘           │
   └──────────────────────────┬───────────────────────────────┘
                              │  raw HTML (or error)
                              ▼
   ┌──────────────────────────────────────────────────────────┐
   │              Parse / Extract / Filter stage              │
   │  ┌─────────────┐  ┌─────────────┐  ┌────────────────┐    │
   │  │ HTML parser │  │ URL filter  │  │ Normalizer     │    │
   │  │ + link ext. │  │ (ext, host) │  │ (rel→abs,      │    │
   │  │             │  │             │  │  dedup params) │    │
   │  └──────┬──────┘  └──────┬──────┘  └────────┬───────┘    │
   │         └─────────────────┴──────────────────┘            │
   └──────────────────────────┬───────────────────────────────┘
                              │  text + URL set
                              ▼
   ┌──────────────────────────────────────────────────────────┐
   │           Dedup + Persist (downstream pipeline)          │
   │  ┌────────────────┐  ┌────────────────┐  ┌───────────┐   │
   │  │ Content Seen?  │  │ Document store │  │ Indexer   │   │
   │  │ (SimHash /     │  │ (S3/HDFS WARCs)│  │ (inverted │   │
   │  │  SHA cluster)  │  │                │  │  index)   │   │
   │  └────────┬───────┘  └────────┬───────┘  └─────┬─────┘   │
   └───────────┼────────────────────┼─────────────────┘        │
               │  new URLs          │                           │
               └────────►URL Frontier (close the loop)         │
```

### 6.2 — Politeness / priority / freshness (URL Frontier internals)

```
       new URLs ──────► Prioritizer (compute score)
                           │
                           ▼
              ┌──── Front Queues (priority) ────┐
              │   f1 (highest)  …  fn (lowest)  │
              └──────────────┬──────────────────┘
                             │  weighted pop
                             ▼
                       Queue Selector
                             │
        ┌────────────────────┼─────────────────────────────┐
        ▼                    ▼                             ▼
  Back Queues b1         Back Queues b2               Back Queues bn
  (host: cnn.com)       (host: nyt.com)              (host: wikpedia)
  ──── FIFO ────         ──── FIFO ────               ──── FIFO ────
        │                    │                             │
        └────────────────────┼─────────────────────────────┘
                             ▼
                     Worker pool (one thread
                     per host queue; sleep
                     between requests; respect
                     robots.txt crawl-delay)
```

Two-stage indirection: **front queues** give priority, **back queues** give politeness. Selection pops from a weighted front queue, then a round-robin from the back queues behind it.

### 6.3 — Sequence: discover → fetch → enqueue

```
   Producer thread        Frontier       Fetcher       Origin          Parser       Dedup
        │                     │             │              │               │            │
        │  enqueue(new_url)   │             │              │               │            │
        │ ───────────────────►│             │              │               │            │
        │                     │             │              │               │            │
        │                     │  next_url   │              │               │            │
        │                     │ ──────────► │              │               │            │
        │                     │             │  GET /page   │               │            │
        │                     │             │ ───────────►│               │            │
        │                     │             │              │               │            │
        │                     │             │  200 + HTML  │               │            │
        │                     │             │ ◄─────────── │               │            │
        │                     │             │              │               │            │
        │                     │             │  parse(raw_html)            │            │
        │                     │             │ ────────────────────────────►│            │
        │                     │             │              │               │            │
        │                     │             │              │               │  seen?     │
        │                     │             │              │               │ ─────────►│
        │                     │             │              │               │            │
        │                     │             │              │               │  new       │
        │                     │             │              │               │ ◄──────── │
        │                     │             │              │               │            │
        │                     │             │              │               │ extract(L) │
        │                     │             │              │               │  filter(L) │
        │                     │             │              │               │            │
        │                     │ enqueue(URLs)               │               │            │
        │                     │ ◄──────────────────────────│               │            │
```

---

## Part 7: Trade-off Tables

### 7.1 — Deduplication primitives

| Approach | False-positive rate | Memory / 1B URLs | Lookups | Exact? | Notes |
|---|---|---|---|---|---|
| **Hash set (full URL)** | 0 | ~150 GB (avg URL 150 B) | O(1) | Yes | Cost-prohibitive at scale; disk-backed variants exist |
| **Bloom filter** | tunable (typ. 1%) | ~12 GB | O(k) hash ops | No (FP only) | Compaction / re-sizing is tricky; standard choice |
| **Counting Bloom / Cuckoo** | tunable, supports delete | ~2× Bloom | O(1) avg | No FP on membership; still possible on dup | Better for short TTL windows; worse for permanent dedup |
| **Hash table on disk (LevelDB/RocksDB)** | 0 | ~80 GB incl. overhead | O(log N) | Yes | Slower; needs compaction; used for permanent log |
| **HyperLogLog on host+path prefix** | ~0.8% std error | ~16 KB per shard | O(1) | Cardinality only | Only answers "have I seen N distinct?" not "have I seen this URL?" |

### 7.2 — Politeness enforcement mechanisms

| Mechanism | Complexity | Granularity | Failure mode | Ops burden |
|---|---|---|---|---|
| **robots.txt crawl-delay** | Low | Per host | Host lies / omits; no standard for sub-paths | Low |
| **Per-host token bucket in-process** | Low | Per host, per worker | Bucket needs to be shared across workers | Low–medium |
| **Distributed rate limiter (Redis)** | Medium | Per host globally | Redis is a SPOF; needs sharding | Medium |
| **Adaptive delay based on response time** | Medium | Per host | Penalizes slow-but-well-behaved hosts | Medium |
| **Per-IP backoff on 5xx/429** | Medium | Per IP | IPs are shared (CDNs); can under-crawl | Medium |
| **HTTP/2 connection multiplexing** | Medium | Per host | Doesn't help across hosts | Medium |

### 7.3 — Graph traversal strategies

| Strategy | Pros | Cons | When to use |
|---|---|---|---|
| **Pure BFS** | Simple, fair-ish | Single-host flooding | Tiny crawls only |
| **BFS + host partitioning** | Politeness | More moving parts | Default for most crawlers |
| **PageRank-weighted** | Biases to important pages | Needs link graph; rank drift | Search-engine discovery |
| **Online learning / contextual** | Adapts to query traffic | Cold start, drift | Specialized vertical crawlers |
| **Random walk / snowball sampling** | Bias-free samples | Slow coverage | Research datasets, not production search |

---

## Part 8: Real-World Case Studies

### 8.1 — Googlebot (Google)

**Architecture (public disclosures + reverse engineering):**

- **Scale:** tens of billions of pages; Google has not published exact QPS but research estimates are 10K–100K pages/s for the active crawl tier. See the public notes in "Google's Search Engine – The History of Search" (Stanford, ~2010) and the open Web Data Commons crawl traces.
- **Crawl budget per host:** Google assigns each host a crawl budget based on PageRank signals, server response patterns, sitemap freshness, and historical change rate. Hosts that 503 spike get throttled. This is the practical operationalization of politeness at scale.
- **Per-host scheduling:** The scheduler uses a "segment" abstraction — groups of URLs from the same host scheduled together to maximize connection reuse and minimize DNS / TLS handshakes.
- **Rendering tier:** Google operates a headless rendering pipeline (originally Caffeine / WRS — Web Rendering Service) that executes JS to discover AJAX-injected links. A separate index ("the supplemental index") holds pages requiring rendering before they graduate to the main index.
- **Robots.txt interpretation:** Includes extensions like `Crawl-delay`, `Sitemap`, and pattern matching against `Allow` / `Disallow` longest-match semantics, plus a hash of rules in the response to bypass re-parsing on subsequent fetches.

**Takeaway:** Googlebot is not a single pipeline but a federation of crawlers (discovery, refresh, news, images) each with its own queue and politeness policy.

### 8.2 — Mercator (Heydon / Najork, used at AltaVista and Google)

Mercator is the canonical academic reference crawler. It introduced many of the design primitives in this chapter:

- **Front queues + back queues** for priority × politeness (this chapter's design comes from Mercator).
- **Per-host "assignment tables"** that determine which worker may fetch which host.
- **Hostname-based politeness** via a separate thread per host that enforces delay.
- **Robots.txt cache** with a TTL.
- **Radix tree for URL dedup** — compact, prefix-friendly, supports wildcards.

**Reference:** Heydon, A., Najork, M. "Mercator: A Scalable, Extensible Web Crawler." *World Wide Web* 2(4), 1999. The design survives because it separates the three concerns (priority, politeness, freshness) into orthogonal data structures rather than one mega-queue.

### 8.3 — Bingbot (Microsoft)

- **Active disclosure** via the Bing webmaster tools "Crawl Control" panel — operators can throttle Bingbot, and Bing exposes daily crawl graphs per host.
- Uses **connection pools per IP block**, not per host, to amortize TCP/TLS cost across many virtual hosts on the same origin.
- Runs an **opt-in "Bingbot Mobile"** crawler that uses mobile User-Agents to verify that mobile-rendered content is consistent with desktop.
- Operates a **dedicated JS-rendering pipeline** since ~2017 (powered by headless Chromium).

### 8.4 — Common Crawl

- Open, public web crawl dataset. Roughly 2.5–3 billion pages/month as of recent (2024) snapshots.
- Storage format is **WARC** (Web ARChive) — raw HTTP request/response pairs — which is more compact and faithful than normalized HTML.
- Politeness: honors robots.txt strictly; serves a crawl log per host so researchers can analyze what was / wasn't fetched.
- Operates as a non-profit; infrastructure is funded by foundations and donor compute. This is the closest thing the public has to a "shared Googlebot."

### 8.5 — Apache Nutch

- Open-source descendant of Mercator and the original Internet Archive crawler.
- Plug-in architecture for parser, fetcher, scoring (OPIC — Online Page Importance Computation).
- Production users are mostly vertical search (price comparison, scientific literature, intranets).
- Provides the canonical implementation of distributed crawl on Hadoop, which is useful as a reference for the **sharded URL frontier** part of the design.

### 8.6 — Amazon product crawler

Public disclosures from Amazon's job postings and academic papers (e.g., "Lessons Learned at Building a Product Catalog Crawler") suggest:

- **Distributed across many accounts** to avoid per-IP throttling.
- **Per-ASIN scheduling** rather than per-host, since the same hostname serves millions of product pages.
- **Strong dedup** — same product can have many URL variants (search-result, ASIN-direct, marketplace-specific).
- **Refresh tier separate from discovery tier** — discovery explores categories, refresh walks known SKU lists on a daily cadence.

---

## Part 9: Common Pitfalls and Failure Modes

### 9.1 — The "DNS bottleneck" trap

Symptom: crawler throughput flat-lines at 100–300 QPS regardless of worker count.

Cause: every cold hostname triggers a synchronous DNS lookup. A central recursive resolver becomes the chokepoint; DNS-over-HTTPS or slow upstream resolvers add 200–1000 ms per cold miss.

Fix: aggressive in-process DNS cache (LRU ≥ 10M entries), distributed DNS cache (e.g., unbound cluster), keep-alive connection pools, and pre-warm DNS for top-N hostnames before scheduling. The chapter mentions DNS caching but understates it; **DNS is the single most common cause of "crawler is slow and we don't know why"**.

### 9.2 — Politeness collapse from virtual hosting

Symptom: polite to one site, accidentally DDoS'ing the shared origin that fronts 50,000 virtual hosts.

Cause: per-host rate limiting but per-IP connection pooling means all the polite hosts pile onto the same IP. Worse with CDNs (Cloudflare, Fastly) where one IP fronts millions of sites.

Fix: per-IP **and** per-host rate limits with a precedence rule; CDN-aware politeness (use `Host` header to bucket, not IP); honor `Retry-After`; expose crawl-delay overrides.

### 9.3 — Spider traps and infinite URL spaces

Symptom: a single host monopolizes 30%+ of queue depth after a few hours.

Cause: calendar pages with infinite pagination, session IDs in URLs, soft-404 link generators.

Fix: max URL length (typ. 2,048 bytes), max per-host URL count cap, soft-404 detection (page says "not found" but returns 200), pattern-based blacklist with manual review queue. This is one of the few areas where a single bug can silently inflate storage costs by 10×.

### 9.4 — Robots.txt mis-parsing

Symptom: accidentally crawling disallowed paths, or refusing to crawl allowed ones.

Cause: longest-match semantics, case sensitivity for `Disallow`, support for `$` end-of-line anchors, wildcards (`*`), and explicit `Allow` precedence — all are common footguns. A wrong parser can get the company IP-blocked or sued.

Fix: use a battle-tested parser (Google's `google/robots.txt` is the gold standard, written by the spec author). Add conformance tests. Cache the parsed representation, not the raw bytes.

### 9.5 — Content-shifting and partial parses

Symptom: index contains the same page with different fingerprints on every recrawl, breaking dedup.

Cause: timestamps in body, ad rotation, session-bound content, A/B tested copy.

Fix: extract main content (Boilerpipe / Readability / Trafilatura style) before fingerprinting; hash on canonicalized main content, not full HTML. Allow fingerprint collisions as long as canonicalized text matches.

### 9.6 — Storage cost explosion from "we'll filter later"

Symptom: storage bill doubles every quarter; nobody is filtering.

Cause: every crawl runs at full throughput and writes everything before dedup, parsing, or filtering.

Fix: filter inline (URL filter + content filter before write); keep raw WARC for X days only; store canonicalized HTML thereafter; index only what survives filtering.

### 9.7 — Clock skew and "freshness" illusions

Symptom: recrawl claims to refresh page X daily, but content is stale for weeks.

Cause: per-host timestamps on pages are unreliable; `Last-Modified` and `If-Modified-Since` work but require careful handling of timezones and HTTP-date parsing.

Fix: rely on `ETag` and `Last-Modified` where available; track per-host change rate empirically; never trust a single `Last-Modified` to mean "this page changed now."

---

## Part 10: Interview Q&A

### Q1. "How many pages per second is this system actually fetching, and what hardware do you need?"

**Answer sketch:**
At the chapter's 1B/month baseline, ~400 pages/s average, ~800 peak. With 1,000 workers each fetching ~1 page/s (after politeness, DNS, parse), you need ~1,000 crawler nodes. Each node is a modest box: 8 vCPU, 16 GB RAM (10 KB per URL frontier slot × 1M slots, plus OS + page cache), 1 Gbps NIC. Cluster-wide bandwidth: ~5 Gbps peak including retries and overhead. Move to Google-scale (10K pages/s) and you're at 10,000+ nodes and tens of Gbps — a real datacenter problem, not a server problem.

### Q2. "How do you make the crawler polite without making it slow?"

**Answer sketch:**
Three layers:
1. **robots.txt cache** with TTL — usually 24h — so we re-read at most once per host per day.
2. **Per-host delay** enforced at the queue level — one worker per host queue sleeping `1 / max_qps_for_host` between fetches.
3. **Adaptive backoff** on 5xx / 429 / connection timeouts — exponential with jitter.

The key insight: politeness is a **scheduling property**, not a fetch property. Pushing it into the queue selector means fetchers stay simple and the SLA is centralized. Politeness never slows the **cluster**, only the **per-host ceiling**.

### Q3. "Walk me through deduplication. Bloom filter vs hash set — when do you pick each?"

**Answer sketch:**
At 10B URLs, a hash set is ~150 GB of RAM with poor cache locality; a Bloom filter at 1% FPR is ~12 GB and one network round trip. The Bloom filter is the membership test for "should I even fetch this?" — a 1% FPR means we over-fetch 1% of URLs (wasted bandwidth, no correctness loss because the next layer — content fingerprint — still rejects exact duplicates). The persistent layer (RocksDB / LevelDB on disk) is the source of truth for "what have we ever seen?" and supports deletes, compactions, and exact lookups. Bloom filter in front, hash table behind. Don't pick one — they're a stack.

### Q4. "What breaks when we 10× the crawl rate?"

**Answer sketch:**
At 10× you discover three new bottlenecks:
1. **DNS** — global recursive resolvers won't keep up. You need a dedicated resolver cluster and aggressive prefetching.
2. **TCP/TLS handshakes** — becomes the dominant per-request cost. Mitigate with persistent connections, TLS session resumption, and HTTP/2 multiplexing.
3. **URL frontier contention** — a single queue broker is now the bottleneck. Shard the frontier by host hash, with per-shard workers and a global coordination layer (ZooKeeper / etcd) only for cross-shard state.

Architecturally the system stays the same; you add capacity and sharding. The hard part is avoiding **state explosion** in the priority queues — keep priority weights stable across shards.

### Q5. "What if we go global — crawl from every region?"

**Answer sketch:**
Two failure modes:
1. **Geo-IP mistakes** — crawler exits in Virginia hitting a website in Tokyo adds 200 ms RTT and triggers the site's "is this a DDoS?" heuristics.
2. **Legal exposure** — GDPR (Europe), PIPL (China), CCPA (California). Crawling and storing personal data triggers obligations.

Mitigations:
- Place crawlers in regions **near the hosts they crawl**, with assignment by IP geo + ccTLD + language.
- Honor `robots.txt` per jurisdiction and accept a global geo-policy layer that blocks scraping of regulated categories in regulated regions.
- Treat user-agent, IP, and crawl-delay as contractual; respect opt-outs via a global suppression list.

Operational: separate **crawl clusters per region**, sharing only the URL frontier state via a CRDT or a regional master with global replication.

### Q6. "How do you keep the index fresh when pages change at different rates?"

**Answer sketch:**
This is the freshness problem and it's not a crawler problem — it's a **scheduling problem** at the URL frontier. Three knobs:
1. **Per-host change rate estimation** — track the empirical change frequency using 304 responses over the last N crawls.
2. **Priority mixing** — dedicate, say, 80% of capacity to incremental refresh and 20% to discovery. Within the 80%, weight by 1 / estimated change interval (so frequently-changing hosts get crawled more often).
3. **Sitemap-driven override** — when a host publishes a `sitemap.xml`, treat new `lastmod` timestamps as a strong signal and crawl those URLs first, regardless of normal priority.

This is one of the few places where a small model — `expected_change_interval(host)` — outperforms clever ML; the signal is sparse and the bias is large.

---

## Part 11: Glossary

| Term | Definition | Common misconception |
|---|---|---|
| **URL Frontier** | The data structure holding URLs awaiting fetch, partitioned for politeness and priority. | "A single FIFO queue" — this is the naive BFS design; production systems use a two-level queue. |
| **Bloom Filter** | Probabilistic data structure for set membership; supports inserts and lookups, no deletes (without counting variant), tunable FPR. | "False positives mean duplicates leak through." They mean you *might* fetch again, but you still dedup content by exact hash on arrival. |
| **robots.txt** | The Robots Exclusion Protocol — a per-host text file that declares which paths crawlers may fetch. | "It's legally binding." It's not a contract, but ignoring it can lead to lawsuits (hiQ v. LinkedIn) or blacklisting. |
| **Crawl-delay** | Optional robots.txt directive requesting a delay between fetches. | "All bots honor it." Many bots do not — it is advisory. |
| **Politeness** | The principle of constraining request rate to avoid overloading target hosts. | "Politeness = a polite tone." It is a quantitative SLA on request rate and concurrency. |
| **WARC** | Web ARChive file format — ISO 28500 — used to store raw HTTP request/response pairs. | "Same as HTML." WARC preserves headers, status codes, and metadata, enabling re-parsing and audit. |
| **Spider Trap** | A URL pattern that generates infinite new URLs (e.g., calendar pagination). | "Just blacklist known ones." New traps appear weekly; defensive coding (max URL length, max depth) is the real defense. |
| **Freshness** | The recency of content in the index relative to its live version. | "Real-time means milliseconds." Search freshness targets are typically days for the broad web, minutes for news. |
| **PageRank** | A link-analysis scoring algorithm that assigns importance based on the link graph. | "Google still uses it." Yes, but as one of hundreds of signals; raw PageRank hasn't been the dominant ranking factor for over a decade. |
| **DNS Resolver** | Service that resolves hostnames to IP addresses. | "It's instant." Cold DNS lookups are 50–200 ms; the single biggest cause of slow crawlers. |