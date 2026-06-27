# Back-of-the-Envelope Estimation

## Overview

Back-of-the-envelope estimation involves creating rough calculations using thought experiments and standard performance metrics to evaluate whether system designs meet requirements.

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

## Learning Objectives Achievement

This section emphasizes that the estimation process itself demonstrates problem-solving ability to interviewers—arriving at precise answers matters less than showing methodical reasoning and clear assumptions.
