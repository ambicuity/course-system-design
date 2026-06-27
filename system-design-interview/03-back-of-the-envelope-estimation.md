# Back-of-the-Envelope Estimation

## Overview

Back-of-the-envelope estimation involves creating rough calculations using thought experiments and standard performance metrics to evaluate whether system designs meet requirements.

The skill is less about arithmetic and more about choosing which number to anchor on. A senior engineer hearing "10 million users" does not run — they reach for the right constants (QPS, storage-per-user, cache hit rate), state their assumptions, and produce a workload shape in under two minutes. The interview signal is the chain of reasoning, not the last digit.

## Core Concepts

### Power of Two

Understanding data volume units is essential for accurate calculations in distributed systems.

| Power | Approximate Value | Full Name | Short Name |
|-------|-------------------|-----------|-----------|
| 10 | 1 Thousand | 1 Kilobyte | 1 KB |
| 20 | 1 Million | 1 Megabyte | 1 MB |
| 30 | 1 Billion | 1 Gigabyte | 1 GB |
| 40 | 1 Trillion | 1 Terabyte | 1 TB |
| 50 | 1 Quadrillion | 1 Petabyte | 1 PB |

A byte consists of 8 bits; one ASCII character uses 1 byte of memory.

#### Why Power-of-Two Mental Math Matters

Hardware addresses and sizes are powers of two. A 32-bit pointer can address 2^32 = ~4 billion values. A 64-bit pointer can address 2^64. SSDs are sold in "GB" but the actual byte count is `1000^3` (decimal GB) while the OS reports `1024^3` (GiB). Memory pages are 4 KB = 2^12. Network MTUs are typically 1500 bytes. Internalizing these numbers lets you sanity-check estimates quickly without reaching for a calculator.

#### Useful Sanity Numbers

- 2^10 = ~1 thousand (K, Ki, Kilo)
- 2^20 = ~1 million (M, Mi, Mega)
- 2^30 = ~1 billion (G, Gi, Giga)
- 2^32 = ~4 billion (the "4G boundary")
- 2^40 = ~1 trillion (T, Ti, Tera)
- 2^50 = ~1 quadrillion (P, Pi, Peta)

A common trick: `2^10 ≈ 10^3`, so `2^30 ≈ 10^9`. Good enough for back-of-envelope; bad enough that you should state your conversion out loud.

### Latency Numbers Every Programmer Should Know

Key operation timing reference (as of 2010, updated perspectives shown in 2020 visualization):

| Operation | Time |
|-----------|------|
| L1 cache reference | 0.5 ns |
| Branch mispredict | 5 ns |
| L2 cache reference | 7 ns |
| Mutex lock/unlock | 100 ns |
| Main memory reference | 100 ns |
| Compress 1K bytes with Zippy | 10 µs |
| Send 2K bytes over 1 Gbps network | 20 µs |
| Read 1 MB sequentially from memory | 250 µs |
| Round trip within same datacenter | 500 µs |
| Disk seek | 10 ms |
| Read 1 MB from network | 10 ms |
| Read 1 MB sequentially from disk | 30 ms |
| Send packet CA→Netherlands→CA | 150 ms |

#### Time Unit Conversions
- 1 ns = 10⁻⁹ seconds
- 1 µs = 10⁻⁶ seconds = 1,000 ns
- 1 ms = 10⁻³ seconds = 1,000 µs = 1,000,000 ns

#### Key Insights from Latency Analysis

- Memory operations are significantly faster than disk operations
- Disk seeks should be avoided when possible
- Simple compression algorithms execute quickly
- Data compression before network transmission improves efficiency
- Data centers located in different regions experience noticeable transmission delays

### Updated Latency Numbers (2010 → 2020 → 2024)

The classic Jeff Dean "Numbers Every Programmer Should Know" table has been refreshed multiple times. The 2020 update adjusted several entries downward as commodity hardware improved:

| Operation | 2010 | 2020 | Trend |
|---|---|---|---|
| L1 cache reference | 0.5 ns | ~1 ns | CPU clocks got slower in absolute terms; cache larger |
| Main memory reference | 100 ns | ~100 ns | DDR5 latency flat — bandwidth grew, latency didn't |
| SSD random read | (n/a) | ~100 µs | NVMe SSDs replaced spinning disks |
| 1 Gbps network send (2 KB) | 20 µs | 20 µs | Stable for a decade |
| 10 Gbps network send (2 KB) | (n/a) | ~2 µs | Now common on commodity NICs |
| Round trip within datacenter | 500 µs | ~500 µs | Light speed in fiber is the floor |
| Disk seek | 10 ms | n/a | Spinning disks no longer the default |
| SSD random read | n/a | 100 µs | New baseline |
| CA→Netherlands→CA | 150 ms | ~150 ms | Constrained by geography and the speed of light |
| CA→Sydney→CA | (n/a) | ~200 ms | Adds ~50 ms for trans-Pacific fiber |

The single most important takeaway: **main memory latency has not improved in 15 years**. Bandwidth has exploded; latency has barely moved. Anything that touches memory at scale (caches, indexes, in-memory stores) wins on bandwidth, not on reducing that 100 ns.

### Availability Numbers

High availability represents the percentage of time a system operates continuously. Range typically spans 99% to 100%.

#### Service Level Agreements (SLAs)

SLAs formally define uptime guarantees between service providers and customers. Major cloud providers (Amazon, Google, Microsoft) target 99.9% or higher availability.

#### Availability Metrics

| Availability % | Downtime per Day | Downtime per Week | Downtime per Month | Downtime per Year |
|---|---|---|---|---|
| 99% | 14.40 minutes | 1.68 hours | 7.31 hours | 3.65 days |
| 99.99% | 8.64 seconds | 1.01 minutes | 4.38 minutes | 52.60 minutes |
| 99.999% | 864 milliseconds | 6.05 seconds | 26.30 seconds | 5.26 minutes |
| 99.9999% | 86.40 milliseconds | 604.80 seconds | 2.63 seconds | 31.56 seconds |

#### Why "Five Nines" Is a Marketing Number

"99.999% availability" sounds aspirational but is rarely measured end-to-end. Realistic numbers:
- A single EC2 instance: ~99.9% per AWS SLA.
- A multi-AZ service: ~99.99%.
- A well-designed multi-region active-active product: ~99.999% in absolute best case, with several minutes per year of dependency-induced outage (third-party APIs, DNS, certificates).

The interview lesson: when a product says "five nines," ask which component. A 99.999% database in front of a 99.9% identity provider is a 99.9% system.

#### The Math of "nines"

```
Downtime per year = (1 - availability) * 365 * 24 * 3600 seconds

99%    → 3.65 days/year
99.9%  → 8.77 hours/year
99.99% → 52.6 minutes/year
99.999%→ 5.26 minutes/year
99.9999% → 31.6 seconds/year
```

This is the conversion you should be able to do in your head during an interview.

## Practical Example: Twitter QPS and Storage Estimation

### Assumptions
- 300 million monthly active users
- 50% daily active users
- Average 2 tweets per user daily
- 10% of tweets contain media
- 5-year data retention

### QPS Calculations

**Daily Active Users:** 300 million × 50% = 150 million

**Standard QPS:** 150 million × 2 tweets ÷ 86,400 seconds ≈ 3,500

**Peak QPS:** 2 × Standard QPS ≈ 7,000

### Storage Requirements

**Per-tweet average sizes:**
- Tweet ID: 64 bytes
- Text: 140 bytes
- Media: 1 MB

**Daily media storage:** 150 million × 2 × 10% × 1 MB = 30 TB

**Five-year retention:** 30 TB × 365 days × 5 years ≈ 55 PB

---

## Best Practices for Estimation

### Rounding and Approximation
Simplify complex arithmetic during interviews. Example: "99,987 ÷ 9.1" becomes "100,000 ÷ 10." Precision matters less than demonstrating sound reasoning.

### Documentation Strategy
- Write down all assumptions for later reference
- Include units with all numerical values to prevent confusion
- Use clear labels (e.g., "5 MB" rather than ambiguous "5")

### Common Estimation Categories
Practice calculating:
- Queries per second (QPS)
- Peak QPS
- Storage requirements
- Cache requirements
- Number of servers needed

### Estimation Hygiene

1. **State assumptions out loud** before computing. "Assuming 50% of MAU are DAU, that gives us 150 M daily active users."
2. **Anchor on at most three numbers** — QPS, storage/day, and bytes/second. Everything else is derivative.
3. **Sanity-check orders of magnitude.** If your estimate says "10 GB/day for a photo-heavy product," you have missed a zero somewhere.
4. **Round aggressively.** Three significant figures is plenty. The interviewer is grading reasoning, not arithmetic.
5. **Use a worked-example pattern.** Write `100 M users × 10 req/day / 86_400 s/day ≈ 11 K QPS`. The structure of the equation is the deliverable.
6. **Always compute both average and peak.** Peak is usually 2x average for consumer products and 10x average for B2B SaaS with batch patterns.

---

## Back-of-the-Envelope Math — Worked Examples

### Example 1: 3.2 PB/day Write Throughput

> Question: "If a system writes 3.2 PB per day, what is the average write throughput?"

```
3.2 PB/day = 3.2 * 10^15 bytes/day
Seconds per day = 86_400
Write throughput = 3.2e15 / 86_400 ≈ 3.7e10 B/s
                            = 37 GB/s
                            = ~296 Gbps (assuming 8/10 encoding)
```

That is roughly the bandwidth of a saturated 400 GbE link, sustained 24/7. Three implications for the design:
- A single writer is unrealistic. You need fan-in across hundreds of nodes, or you write directly to object storage with multiple parallel uploads.
- A single 1 Gbps NIC cannot carry this. 40 Gbps NICs minimum, and likely 100 Gbps.
- The receiving storage must be horizontally scalable (S3, HDFS, custom blob store).

### Example 2: Image-Sharing Service, 10 M DAU

**Assumptions:**
- 10 M DAU
- Each user uploads 2 images/day, fetches 30 images/day
- Average image: 500 KB upload, 200 KB served (with CDN compression)
- 10-year retention

**Storage:**

```
Uploads/day = 10e6 * 2 = 20 M images/day
Bytes/day   = 20e6 * 500 KB = 10 TB/day raw
10 years     = 10 * 365 * 10 TB ≈ 36.5 PB raw
With 2x replication                       ≈ 73 PB
```

**QPS:**

```
Read  QPS = 10e6 * 30 / 86_400 ≈ 3,500 (avg)  → 7,000 peak
Write QPS = 10e6 *  2 / 86_400 ≈   230 (avg)  →   500 peak
```

**Bandwidth (assuming 70% CDN hit rate):**

```
Origin egress = 30% * 3,500 * 200 KB ≈ 210 MB/s = 1.7 Gbps
CDN egress    = 100% * 3,500 * 200 KB ≈ 700 MB/s = 5.6 Gbps
```

**Object store requests (GETs):** ~3,500/s sustained — most CDNs do this easily.

### Example 3: Search Engine, 1 B Documents

```
Average document = 10 KB
Total corpus     = 1e9 * 10 KB = 10 TB
With 3x replication across data centers   ≈ 30 TB

Inverted index ≈ 30-50% of raw text size (rough heuristic)
                ≈ 10 TB of index

QPS at 100 M DAU, 10 searches/day each:
100e6 * 10 / 86_400 ≈ 11.5 K QPS avg
Peak (3x) ≈ 35 K QPS

Per query cost: ~5-10 disk seeks or ~50 MB scanned from inverted index.
35 K QPS * 5 seeks = 175 K IOPS — well within a modern SSD cluster.
```

The point is not the specific answer; it is the shape: corpus size sets storage, query volume sets QPS, IOPS is the bottleneck for search.

### Example 4: URL Shortener, 100 M URLs/month

```
Writes/month = 100 M
Writes/day   = ~3.3 M
Writes/sec   = ~38 average, ~100 peak

Storage per URL: 500 bytes (original + short + metadata + expiry)
Storage/year     = 1.2 B URLs * 500 B = 600 GB/year
Read:write ratio ~ 100:1 for short URLs
Reads/sec       = ~3,800 avg, ~10,000 peak
```

Tiny system by modern standards. Single Postgres with read replicas and a Redis cache. The interview answer is "this is small enough that you should call it out — don't over-engineer."

### Example 5: Video Streaming, 50 M DAU

**Assumptions:**
- 50 M DAU, 2 hours/day average watch time
- 5 Mbps average bitrate (1080p H.264)

**Egress bandwidth:**

```
Total minutes/day = 50e6 * 120 = 6e9 minutes
Total bytes/day   = 6e9 * 60s * 5 Mbps / 8 = 2.25e15 bytes ≈ 2.25 PB/day
Average bps       = 2.25e15 / 86_400 ≈ 26 TB/s ≈ 208 Tbps
```

At 208 Tbps of egress, you do not even consider building this yourself — you sign with a CDN (Cloudflare, Akamai, Fastly, Cloudfront) and pay per-GB egress. The interview lesson: when the math exceeds the capacity of any single vendor's offering, your architecture is "use the vendor."

---

## ASCII Architecture Diagrams

### 1. Estimation-Driven Capacity Plan

```
                  ┌──────────────────────────────────────────┐
                  │       Inputs (state assumptions)          │
                  │  DAU, req/user/day, payload size,        │
                  │  read:write ratio, retention             │
                  └──────────────────┬───────────────────────┘
                                     │
                  ┌──────────────────┼───────────────────────┐
                  ▼                  ▼                       ▼
          ┌──────────────┐   ┌──────────────┐        ┌──────────────┐
          │  QPS model   │   │ Storage model│        │ Bandwidth    │
          │ avg / peak   │   │ raw / rep /  │        │ ingress /   │
          │              │   │ index / arch │        │ egress      │
          └──────┬───────┘   └──────┬───────┘        └──────┬───────┘
                 │                  │                       │
                 └──────────────────┼───────────────────────┘
                                    ▼
                  ┌──────────────────────────────────────────┐
                  │        Topology decision                  │
                  │  web nodes / DB sharding / cache size    │
                  │  CDN strategy / queue partitions         │
                  └──────────────────────────────────────────┘
```

The diagram is a reminder that every architectural decision is downstream of three numbers.

### 2. Latency Budget Allocation Across One Request

```
       Total budget: 200 ms (p99) for a typical web request

       ┌──────────────────────────────────────────────────────────┐
       │ TLS handshake       30 ms   ████                          │
       │ L4 LB               1 ms    █                             │
       │ L7 gateway          5 ms    █                             │
       │ App server          10 ms   █                             │
       │ Cache lookup        2 ms    █                             │
       │ DB query (cache hit)   20 ms   ███                       │
       │ DB query (cache miss) 80 ms   ████████                  │
       │ Service B call      15 ms   ██                           │
       │ Response serialization 5 ms  █                          │
       │ Other overhead      ~30 ms (network, GC, jitter)        │
       └──────────────────────────────────────────────────────────┘
       Total: ~200 ms p99
```

When an interviewer asks "where does latency come from?", draw this and argue which numbers to cut first. The answer is almost always "the DB cache miss path" or "the cross-service call."

### 3. Storage Growth Curve (Linear vs Compaction)

```
       Cumulative bytes
            ▲
            │
   100 PB ─ │                                            X  ← raw (10y retention, 2x replication)
            │                                         ╱
            │                                      ╱
    50 PB ─ │                                   ╱  X  ← after 50% compression
            │                                ╱
            │                             ╱
    25 PB ─ │                          ╱ X     ← after dedup & compaction
            │                       ╱
            │                    ╱
            │                 ╱
            │              ╱
            │           ╱
            │        ╱
            │     ╱
            │  ╱
       0   └──────────────────────────────────────────────► time
            Y0      Y2      Y4      Y6      Y8     Y10
```

Storage estimates should always show three lines: raw, after compression, after compaction/dedup. Real systems hit the bottom curve because of repeated content (images of cats are remarkably redundant).

---

## Trade-off Tables

### Estimation Approach: Top-Down vs Bottom-Up

| Dimension | Top-Down (assume DAU, derive capacity) | Bottom-Up (sum per-feature capacity) |
|---|---|---|
| Speed | Fast — answers in 90 seconds | Slow — every feature needs a number |
| Accuracy | Medium — depends on assumption quality | High when done thoroughly, garbage if any feature is wrong |
| Right for | Interviews, executive summaries | Final design docs, capacity planning before launch |
| Risk | Missing a major workload (a single hot feature may dwarf everything else) | Doubly-counting shared infrastructure, or missing dependencies |
| Interview signal | Shows you can reason from a single number | Shows you can decompose a system but can run out of time |

### Storage Format Choices (Cost vs Performance vs Operational)

| Format | $/GB-month | Read perf | Write perf | Operational | Best for |
|---|---|---|---|---|---|
| Local NVMe SSD | ~$0.10 | Excellent | Excellent | Medium | Hot working set |
| EBS gp3 (AWS) | ~$0.08 | Good | Good | Low | Persistent block storage |
| S3 Standard | ~$0.023 | Slow per-object | Slow per-object | Very low | Object storage, large blobs |
| S3 IA | ~$0.0125 | Slow, retrieval fee | Slow | Very low | Infrequently read |
| S3 Glacier | ~$0.004 | Minutes to hours | Slow | Very low | Backups, archives |
| HDFS on commodity | ~$0.02-0.05 | Good (sequential) | Good (large writes) | High | Hadoop-era analytics |
| Tape (offline) | ~$0.001 | Minutes | Slow | Very high | Compliance archival |

A real cost optimization story is "tier by access pattern": hot in SSD, warm in standard object storage, cold in archival. The interview version is "move data to cheaper tiers as it ages."

### Caching Strategy Trade-offs

| Strategy | Stale-read risk | Cache size | Origin load | Latency |
|---|---|---|---|---|
| No cache | None | 0 | 100% | DB-bound |
| Read-through with TTL | Yes, until TTL | Working set | Reduced by hit rate | Cache-bound (fast) |
| Write-through | None (cache reflects DB) | Same as DB rows | Same as DB | Cache + DB latency |
| Write-behind | Higher (loss window) | Same as DB rows | Batched | Fast writes, slower durability |
| Refresh-ahead | Low | Working set + headroom | Smoothed | Pre-warmed |

---

## Real-World Case Studies

### 1. Google's Original "Numbers Every Programmer Should Know"

Jeff Dean's 2010 talk at Stanford ("Designs, Lessons and Advice from Building Large-Scale Distributed Systems") is the canonical source of the latency table. The talk was honest about the limits of his measurements: numbers were on specific hardware at a specific point in time. The 2020 refresh by Dean and others adjusted the table for modern hardware (NVMe SSDs replaced spinning disks; 10 GbE became standard). For an interview, the value of citing this table is showing that you understand the order-of-magnitude gap between memory (100 ns) and disk (10 ms) — about five orders of magnitude. Source: Jeff Dean, "Designs, Lessons and Advice from Building Large Distributed Systems," LADIS 2009; Peter Norvig, "Teach Yourself Programming in Ten Years."

### 2. Twitter's Storage Estimation at IPO

When Twitter filed its S-1 in 2013, it disclosed serving ~2 billion timeline deliveries per day from ~150 million monthly actives. The math:
- 200 M monthly → ~100 M daily (50% DAU/MAU ratio)
- 20 timeline fetches per DAU per day = 2 B deliveries/day
- QPS = 2e9 / 86_400 ≈ 23 K avg, ~70 K peak (3x multiplier)

This roughly matches what Twitter publicly discussed in their "frozen dessert" timeline architecture talk from 2012 — fanout-on-write for celebrities, fanout-on-read for normal users. The estimation exercise is useful because it grounds the abstract numbers in a real public company. Source: Twitter IPO S-1, 2013; Raffi Krikorian, "Timelines @ Scale," QCon 2012.

### 3. WhatsApp's "Two Dozen Engineers, 7 Trillion Messages"

WhatsApp reportedly handled 7 trillion messages per year with ~50 engineers at the time of the Facebook acquisition (2014). That is ~220 K messages per second on average, peak around 11 M messages per second during New Year's Eve. Their trick was FreeBSD + Erlang + a custom message routing system that pushed everything to in-memory queues with eventual persistence to disk. The estimation lesson: a workload that looks impossible can be handled by a tiny team if the architecture is radically simple and the constants (messages/second, latency budget) are honestly accounted for. Source: WhatsApp engineering blog posts, 2012-2014; Anton Lavrik, "WhatsApp: 1 Million Tcp Connections," 2012.

### 4. Cloudflare's Edge Bandwidth Math

Cloudflare's 2020 transparency report disclosed roughly 15-20% of all HTTP traffic on the internet flowing through their network. With ~400 Tbps of edge capacity at the time, they could quantify the cost of a single DDoS attack in TBs per second. The estimation story: when you operate at internet scale, your capacity planning is "capacity of the entire internet minus what we already sell." Source: Cloudflare transparency reports and quarterly shareholder letters.

### 5. Uber's "Schemaless" Datastore Estimation

Uber's Schemaless (built on top of MySQL with sharding) was reported (in their 2014 engineering blog) to be storing tens of TB per shard and serving hundreds of thousands of QPS. The estimation lesson is that sharding brings operational complexity that pays off only at this scale, and that even at Uber's growth, the storage layer was MySQL — not a fancy NewSQL engine. Source: Uber Engineering, "The Architecture of Schemaless," 2014; "Project Mezzanine: Rebuilding Uber's Largest Data Infrastructure for Scale," 2019.

---

## Common Pitfalls & Failure Modes

### Pitfall 1: Confusing MAU with DAU with Concurrent Users

Most consumer products have:
- MAU ≈ 30-50% of total registered users
- DAU ≈ 20-30% of MAU (so ~10% of registered)
- CCU (concurrent users) ≈ 5-10% of DAU at any given second

If you anchor on MAU for QPS, your answer will be off by an order of magnitude. If you anchor on CCU, your answer will be off by 10x in the other direction. State which one you mean explicitly.

### Pitfall 2: Forgetting Peak vs Average

Average QPS is the answer to "what does the system do all day." Peak QPS is the answer to "what must the system survive." The ratio is usually 2x for consumer social, 5-10x for live-event workloads (sports, elections, breaking news), and 10-100x for batch or scheduled workloads (end-of-day payroll, midnight backups). Capacity planning that uses only the average will melt under the first traffic spike.

### Pitfall 3: Ignoring Replication and Index Overhead

Raw data is a small fraction of total storage. Replication (2-3x), secondary indexes (1.3-2x), write-ahead logs and binlogs (10-30%), backups (depends on retention), and operational overhead (typically 30%) all stack. The easy mistake is "we need 10 TB" turning into "we need 30 TB" surprises at procurement time.

### Pitfall 4: Treating Bandwidth as Symmetric

Most cloud egress is charged; ingress is usually free. So bandwidth planning must distinguish ingress from egress, and bytes-per-second from bytes-per-day (because some charging is per-second-burst). A system that uploads 1 GB/day but also serves 100 GB/day has very different network cost implications.

### Pitfall 5: Estimating with the Wrong Time Window

"3.2 PB/day" looks like an exotic number. "37 GB/s" is what your network engineer needs to know. Both are correct, but only the second is actionable. Converting between time windows (per second, per minute, per hour, per day) is the single most common estimation step. Forget it and the answer is wrong by 86,400x.

### Pitfall 6: Choosing the Wrong Constants

The latency numbers table has specific values on specific hardware. Quoting "L1 cache reference = 0.5 ns" as gospel in 2026 is technically outdated. The right approach is to anchor on the *gap* between tiers — L1 vs main memory is ~200x regardless of the absolute numbers. Interviewers usually accept order-of-magnitude reasoning; they do not accept missing a factor of 10.

---

## Interview Q&A

### Q1: "How many requests per second does Twitter see?"

**Answer sketch:** Anchor on MAU. ~300 M MAU. ~50% DAU = 150 M. Each DAU does ~5 reads (timeline fetches) and ~0.5 writes (tweets, likes, retweets) per day. So write QPS = 150 M × 0.5 / 86_400 ≈ 870 avg, ~2 K peak. Read QPS is dominated by timeline fanout — far larger, but the calculation is "DAU × timelines fetched per day." Always state assumptions out loud and round.

### Q2: "How much storage does a photo-sharing service need for 100 M users?"

**Answer sketch:** State retention (5 years?), photos per user (50?), average size (300 KB?). Then: `100 M × 50 × 300 KB = 1.5 PB raw`. With 2x replication, 3 PB. After compression (assume 30%): ~2 PB. Present a range: "1.5 PB raw to 3 PB replicated, depending on retention." End with the operational implication: "this needs object storage, not a single database."

### Q3: "If we 10x the DAU overnight, what changes?"

**Answer sketch:** Identify the bottleneck. For most products it is the database (write QPS scales linearly; read replicas help only if the cache absorbs the extra). For read-heavy products it is the CDN or the egress bill. For write-heavy products it is the message queue or the sharded database. Always end with "and the monitoring resolution becomes useless because the dashboards were sized for 1x traffic."

### Q4: "What does 'five nines' actually mean in operational terms?"

**Answer sketch:** 99.999% uptime = 5.26 minutes of downtime per year. That is the *total* allowed budget across all dependencies. So if you run on three services each with 99.9% SLA, your composite is ~99.7%, not 99.999%. The interview lesson: SLA numbers compose multiplicatively for dependencies. State the composition out loud.

### Q5: "Convert 3.2 PB/day into something my networking team can use."

**Answer sketch:** `3.2 × 10^15 bytes / 86_400 s = 37 GB/s`. For wire sizing: `37 × 8 = 296 Gbps`. So roughly three 100 GbE links, or one 400 GbE link, sustained 24/7. This is what tells you whether your design is feasible on your existing network.

### Q6: "Your disk does 200 IOPS. How many requests per second can a database on it serve?"

**Answer sketch:** If every request needs a disk read, 200 QPS. If the working set fits in cache and only 1% of requests hit disk, 20,000 QPS. So the answer depends entirely on cache hit rate. This is why "database QPS" without "cache hit rate" is a meaningless number in interviews.

### Q7: "How many web servers do I need for 50 K peak QPS?"

**Answer sketch:** A single modern web server (NGINX on a 4-core box) handles ~5-10 K QPS for typical JSON responses. So 50 K peak / 7 K per node ≈ 7 nodes. Always add headroom: 2x for rolling deploys and spikes → 14 nodes minimum. Always state the per-node QPS assumption.

---

## Key Terms / Glossary

| Term | What people say | What it actually means |
|---|---|---|
| QPS | "Queries per second." | The number of requests a system handles per second. Distinct from RPS (same thing, different name) and distinct from concurrent connections. Always state whether you mean average or peak. |
| DAU | "Daily active users." | Unique users who performed a qualifying action in a 24-hour window. Definition varies — a logged-in page view? A specific API call? Always pin down which. |
| MAU | "Monthly active users." | Unique users in a 30-day window. Roughly 2-5x DAU for healthy consumer products. |
| QPS / RPS / TPS | "The same thing." | They overlap but have nuance: QPS often refers to queries (reads + writes), RPS to HTTP requests, TPS to database transactions. Pin down which one you mean. |
| p99 / p50 / p95 | "Percentile latency." | p50 is the median — half the requests are faster. p99 is the long-tail tail: 1 in 100 requests is slower. p99.9 is the worst tail. Always specify which percentile you mean. |
| SLA | "Service Level Agreement." | A contractual uptime commitment. Major clouds promise 99.9% (8.77 hours/year) for a single instance, 99.99% for multi-AZ services. SLAs compose multiplicatively for dependencies. |
| SLO | "Service Level Objective." | An internal target, often stricter than the SLA. Lets you catch problems before they breach the SLA. |
| Replication factor | "How many copies." | The number of physical copies of each piece of data. RF=3 is the default for most production systems. RF=1 is a single point of failure. |
| Bandwidth | "How fast the pipe is." | The capacity of a network link, measured in bits per second. Distinct from throughput (how much is actually flowing) and latency (how long any individual byte takes). |
| Working set | "Hot data." | The subset of data that accounts for the vast majority of accesses — typically 1-10% of total data. Determines how much cache you need. |
| Cardinality | "How many distinct values." | The number of unique values in a column or key. High-cardinality columns are poor choices for indexes that fit in memory; low-cardinality columns (status, country) make good partition keys. |
| Fanout | "Distribute to many." | The cost of delivering one piece of content to N recipients. Fanout-on-write (push) costs at write time; fanout-on-read (pull) costs at read time. Choice depends on read:write ratio. |
| Hot key / hotspot | "A key that gets all the traffic." | A single key or shard that receives a disproportionate share of traffic, defeating the benefits of sharding or partitioning. Requires explicit mitigation (dedicated shard, caching, async aggregation). |

---

## Learning Objectives Achievement

This section emphasizes that the estimation process itself demonstrates problem-solving ability to interviewers—arriving at precise answers matters less than showing methodical reasoning and clear assumptions.

The single most common interview mistake in this section is treating the answer as the goal. It is not. The answer is downstream of:
- A clear statement of assumptions (DAU, retention, payload, peak multiplier)
- A consistent set of constants (QPS calculation, storage per entity)
- An explicit conversion between time windows (per second, per day)
- A sanity check on the magnitude (does this number make sense?)

If your interview answer walks through those four steps clearly, the precision of the final number is irrelevant. If your answer jumps to "I think it is 5 K QPS" without the chain of reasoning, even an exact number will not save you.