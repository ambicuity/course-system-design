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
- **Worker Threads**: Download one page at a time per host with a delay between requests

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
