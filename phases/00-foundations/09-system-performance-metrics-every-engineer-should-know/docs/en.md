# System Performance Metrics Every Engineer Should Know

> You can't optimize what you can't measure — and you can't debug what you don't understand.

**Type:** Learn
**Prerequisites:** Fundamentals of distributed systems, Client-server model basics
**Time:** ~25 minutes

---

## The Problem

Your API is slow. But how slow, exactly? "It feels sluggish" is not a root cause. Without a shared vocabulary of quantitative metrics, your on-call conversation devolves into "it's getting slower" vs. "it's fine on my end." You can't set alerts, capacity-plan, or write SLAs without concrete numbers.

Consider a real scenario: Black Friday hits. Your e-commerce service starts returning errors for 2% of checkout requests. Is that bad? It depends entirely on whether you're handling 10 QPS or 50,000 QPS. An engineer who knows metrics knows that 2% error rate at 50,000 QPS means 1,000 failed transactions per second — each one a lost sale. One who doesn't know metrics just says "error rate is low, let's monitor."

The same confusion shows up in capacity planning. A junior engineer reports: "Our database handles 500 queries per second." A senior engineer immediately asks: "What's the average response time? What's the p99 latency? What's the concurrent connection count?" These aren't pedantic questions — they're the only way to know whether the system will hold or collapse under load.

---

## The Concept

### The Four Core Throughput Metrics

**Queries Per Second (QPS)** — also called Requests Per Second (RPS) — measures how many incoming requests arrive at your system per unit time. It is a measure of *demand*, not capacity. QPS spikes during peak hours regardless of whether your system can handle it.

**Transactions Per Second (TPS)** measures how many completed operations your system processes per second. A transaction is a full round-trip: request in → processing → database → response out. TPS tells you about *work completed*, not just requests received. If your checkout flow involves 3 database writes and 2 cache lookups, one checkout is one transaction even though it may generate dozens of internal queries.

> Rule of thumb: QPS ≥ TPS always. The gap widens when requests fail, queue, or time out.

**Concurrency** measures how many requests are *simultaneously in-flight* at any instant. A system handling 100 QPS where each request takes 5 seconds has 500 concurrent requests at any moment. Concurrency drives resource consumption: threads, connections, file descriptors, memory.

**Response Time (RT)** / **Latency** measures the elapsed wall-clock time from when a request is sent until the response is fully received. Measured at the client, this includes network round-trip time. Measured at the server, it excludes network transit.

### Little's Law — The Equation Tying Them Together

These metrics are not independent. **Little's Law** from queuing theory gives the relationship:

```
Concurrency (L) = QPS (λ) × Average Response Time (W)
```

Or equivalently: `QPS = Concurrency ÷ Average Response Time`

**Example:**

| Scenario | QPS | Avg RT | Concurrency Required |
|----------|-----|--------|----------------------|
| Fast API | 1,000 | 10 ms | 10 concurrent |
| Slow API | 1,000 | 500 ms | 500 concurrent |
| Very slow | 1,000 | 5,000 ms | 5,000 concurrent |

At 1,000 QPS with 5-second average response time, your system must sustain 5,000 concurrent requests. If your thread pool has 256 threads, you will queue and eventually reject. Little's Law turns "it feels slow" into "we need N times more capacity."

### Latency Percentiles — The Most Important Metric You're Probably Ignoring

Average latency lies. If 99% of requests take 10 ms and 1% take 10,000 ms, your average looks fine at ~110 ms. But 1% of 100,000 daily users is 1,000 people per day experiencing 10-second hangs.

Use **percentile latency** (also called quantile latency):

| Percentile | Meaning | Typical Use |
|------------|---------|-------------|
| p50 (median) | Half of requests are faster than this | Baseline "happy path" |
| p90 | 90% of requests are faster than this | Common SLO target |
| p95 | 95% of requests faster | Tighter SLO target |
| p99 | 99% of requests faster | Catches the long tail |
| p999 | 99.9% of requests faster | Critical for financial/real-time systems |

**Tail latency** (p99, p999) disproportionately matters in microservices. If you chain 10 services and each has 1% chance of a slow response, the probability of at least one slow hop is `1 - 0.99^10 ≈ 9.6%`. Your end-to-end p99 is far worse than any individual service's p99.

### Throughput vs. Latency — The Fundamental Trade-off

Throughput and latency are often in tension:

```
       High Throughput
            ▲
            │
    Batch   │   Streaming
   Systems  │   Pipelines
            │
────────────┼─────────────────►
            │              Low Latency
    Quiet   │   Interactive
   Periods  │   APIs / Games
            │
       Low Throughput
```

Batching increases throughput (amortize overhead across many requests) but increases latency (requests wait to be batched). Real-time systems prioritize latency at the cost of throughput efficiency.

### Error Rate and Availability

**Error rate** = (failed requests / total requests) × 100%.

A 0.1% error rate at 1 QPS is one error every 17 minutes. At 10,000 QPS it's 10 errors per second. Always reason about error rates in the context of absolute QPS.

**Availability** is the flip side: uptime as a percentage of total time. "Five nines" (99.999%) allows ~5 minutes downtime per year. It's a derived metric from error rate and failure duration.

| Availability | Downtime per year | Downtime per month |
|---|---|---|
| 99% ("two nines") | ~3.65 days | ~7.3 hours |
| 99.9% ("three nines") | ~8.77 hours | ~43.8 minutes |
| 99.99% ("four nines") | ~52.6 minutes | ~4.4 minutes |
| 99.999% ("five nines") | ~5.26 minutes | ~26 seconds |

### SLI, SLO, SLA — The Hierarchy

These three terms are often conflated. They are distinct layers:

- **SLI (Service Level Indicator):** The raw measurement. "p99 latency measured at the load balancer."
- **SLO (Service Level Objective):** The internal target. "p99 latency must be < 200 ms for 99.9% of requests in any 30-day window."
- **SLA (Service Level Agreement):** The contractual commitment to customers, with financial penalties for breach. Always looser than your SLO (you need headroom).

---

## Build It / In Depth

### Step 1 — Instrument Your Service

Any meaningful analysis starts with measurement. Using Python + `time` module as the simplest example:

```python
import time
import random
from collections import deque

# Sliding window for the last 60 seconds of request times
request_log = deque()

def record_request(duration_ms: float, success: bool):
    now = time.time()
    request_log.append((now, duration_ms, success))
    # Evict entries older than 60 seconds
    while request_log and request_log[0][0] < now - 60:
        request_log.popleft()

def compute_metrics():
    now = time.time()
    window = [r for r in request_log if r[0] >= now - 60]
    if not window:
        return {}

    durations = sorted(r[1] for r in window)
    total = len(durations)
    errors = sum(1 for r in window if not r[2])

    def percentile(data, p):
        idx = int(len(data) * p / 100)
        return data[min(idx, len(data) - 1)]

    return {
        "qps":        total / 60,
        "p50_ms":     percentile(durations, 50),
        "p95_ms":     percentile(durations, 95),
        "p99_ms":     percentile(durations, 99),
        "error_rate": errors / total * 100,
    }
```

### Step 2 — Apply Little's Law to Capacity Plan

Scenario: You expect a product launch to drive peak load of 5,000 QPS. Your current p95 response time is 120 ms.

```
Concurrency = QPS × Avg_RT
            = 5,000 × 0.120 s
            = 600 concurrent requests
```

If each server thread handles one concurrent request and you want 20% headroom:

```
Threads needed = 600 × 1.2 = 720 threads
Servers needed = ceil(720 / threads_per_server)
```

With 64 threads per server: `ceil(720 / 64) = 12 servers`. This is a back-of-envelope calculation — but it's grounded in real numbers, not guesswork.

### Step 3 — Identify Tail Latency with a Percentile Profile

Load test your service and capture a latency histogram:

```
Latency Distribution (10,000 samples)
─────────────────────────────────────
  0-10ms   ████████████████████ 62%
 10-50ms   ████████             24%
 50-100ms  ███                   8%
100-500ms  █                     4%
 500ms+    ▌                     2%

p50:  8 ms
p90: 42 ms
p95: 80 ms
p99: 380 ms   ← The tail
```

The p99 is 47x higher than p50. Without percentile analysis, your "average of 23 ms" masks a serious problem. Investigate the 2% of requests taking 500 ms+ first — they are almost always caused by GC pauses, lock contention, or missing database indexes.

### Step 4 — Compute Error Budget

If your SLO is "99.9% of requests succeed":

```bash
# Given: 1 million requests/day
TOTAL_REQUESTS=1000000
SLO_PERCENT=99.9
ERROR_BUDGET_PERCENT=$(echo "100 - $SLO_PERCENT" | bc)  # 0.1%
MAX_ERRORS=$(echo "$TOTAL_REQUESTS * $ERROR_BUDGET_PERCENT / 100" | bc)  # 1000
echo "You may have at most $MAX_ERRORS errors per day before burning your error budget"
```

Error budgets make the conversation concrete: "We burned 80% of this month's error budget in the last deploy. We should roll back and investigate before shipping more features."

---

## Use It

### Where These Metrics Show Up in Real Systems

| System / Tool | Metric Focus | Notes |
|---|---|---|
| **Prometheus + Grafana** | All metrics via scraping | Histogram metrics give you p50/p95/p99 natively with `histogram_quantile()` |
| **AWS CloudWatch** | QPS, Error Rate, Latency | API Gateway and ALB surface these automatically |
| **Datadog APM** | Latency percentiles, TPS | Distributed tracing correlates tail latency to specific spans |
| **Nginx / HAProxy** | QPS, Concurrency, RT | `ngx_http_stub_status_module` for active connections and request rate |
| **PostgreSQL** | TPS | `pg_stat_database.xact_commit + xact_rollback` per second |
| **Redis** | Ops/sec, latency | `INFO stats` and `INFO latencystats` expose these directly |
| **k6 / Locust** | Load test all metrics | Generate controlled load; measure system response |
| **Google SRE Workbook** | SLI/SLO/SLA framework | The canonical reference for error budget management |

**When to focus on which metric:**

- **QPS/TPS** — capacity planning, scaling decisions, cost estimation
- **Latency percentiles** — user experience, SLO definition, identifying hot spots
- **Concurrency** — thread/connection pool sizing, deadlock risk
- **Error rate** — reliability measurement, error budget consumption
- **Availability** — contractual commitments, on-call escalation policies

---

## Common Pitfalls

- **Averaging latency.** Averages hide bimodal distributions. A system with p50=5 ms and p99=5,000 ms has an "average" of ~55 ms, which means nothing. Always report percentiles. If you can only have one number, use p95 or p99.

- **Confusing QPS with TPS.** A single user checkout triggers 20 database queries. Your DB sees 20,000 QPS; your application processes 1,000 TPS. Quoting QPS when someone asks about business throughput gives a misleading 20x inflation.

- **Ignoring Little's Law.** Engineers frequently optimize latency in isolation ("we got p99 down from 500 ms to 200 ms!") without recalculating concurrency requirements. At the same QPS, lower latency means fewer concurrent requests, which directly reduces resource pressure. Make this explicit.

- **Setting SLAs tighter than SLOs.** Your SLO must have headroom above your SLA. If your SLA commits to 99.9% availability, your internal SLO should target 99.95% or better so you catch degradation before customers feel it.

- **Measuring at the wrong boundary.** Server-side latency excludes network transit, DNS, TLS handshake, and client-side rendering. Always measure latency from the customer's perspective (Real User Monitoring) and from the server's perspective separately. They will differ dramatically on mobile networks.

---

## Exercises

1. **Easy:** A service handles 2,000 QPS with an average response time of 50 ms. Using Little's Law, calculate how many concurrent requests the system must support. If the average response time degrades to 200 ms under load, what does concurrency become?

2. **Medium:** You are given these latency samples from a load test (in ms): `[5, 8, 12, 9, 6, 450, 7, 10, 11, 600]`. Calculate the p50, p90, and p99 latency. Explain why reporting only the average would be misleading for SLO definition.

3. **Hard:** Your SLO is "p99 latency < 100 ms for 99.9% of requests." You have two microservices in your critical path: Service A (p99 = 40 ms) and Service B (p99 = 40 ms). What is the worst-case composite p99 for a request that must call both services serially? What if they are called in parallel? Design an alerting strategy that catches end-to-end SLO violations before customers report them, given that each service only exposes its own p99.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **QPS** | Total requests the system can handle | Rate of *incoming* requests — a demand metric, independent of whether the system is keeping up |
| **Latency** | How slow the server is | Elapsed time from request initiation to full response receipt, including all network hops, queuing, and processing |
| **p99 latency** | An edge case for extreme situations | The latency experienced by 1 in 100 users — on a high-traffic service, this is thousands of people per minute |
| **Concurrency** | The number of users online | The number of requests *simultaneously in-flight* inside the system; derived from QPS × avg RT via Little's Law |
| **Availability** | Whether the site is "up" | The fraction of time a system successfully serves requests, usually expressed as a percentage over a rolling time window |
| **SLO** | A promise to customers | An *internal* target for a service metric; intentionally stricter than the customer-facing SLA to create a safety buffer |
| **Error budget** | A tolerance for failures | The maximum allowable failure rate within a compliance window; when exhausted, new feature releases should pause in favor of reliability work |

---

## Further Reading

- [Google SRE Book — Chapter 4: Service Level Objectives](https://sre.google/sre-book/service-level-objectives/) — The definitive treatment of SLI/SLO/SLA and error budgets, free online.
- [Brendan Gregg — Systems Performance (2nd ed.)](https://www.brendangregg.com/systems-performance-2nd-edition-book.html) — Deep-dive into latency analysis, utilization, saturation, and USE method for any resource.
- [Little's Law Wikipedia](https://en.wikipedia.org/wiki/Little%27s_law) — Mathematical proof and worked examples of the queuing theory relationship.
- [Prometheus Histograms and Summaries](https://prometheus.io/docs/practices/histograms/) — Official guidance on capturing latency percentiles correctly in a time-series monitoring system.
- [High Scalability — Latency Numbers Every Programmer Should Know](http://highscalability.com/blog/2011/1/26/google-pro-tip-use-back-of-the-envelope-calculations-to-choo.html) — Jeff Dean's canonical latency reference table for CPU cache, RAM, disk, and network operations.
