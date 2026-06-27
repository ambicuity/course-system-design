# Design A Rate Limiter

## Overview

A rate limiter controls traffic flow by restricting the number of client requests within specified time periods. This foundational system design component prevents service abuse and ensures equitable resource distribution.

## Key Benefits

- **DoS Prevention**: Blocks excessive requests from intentional or unintentional attacks
- **Cost Reduction**: Limits expensive third-party API calls and reduces infrastructure expenses
- **Server Protection**: Filters bot traffic and prevents overload from misbehaving clients

## Step 1: Problem Understanding & Design Scope

### Requirements Clarification

The design focuses on server-side API rate limiting in distributed environments with these capabilities:

- Accurately limit excessive requests
- Maintain low latency without degrading HTTP response times
- Minimize memory consumption
- Support multiple servers/processes (distributed rate limiting)
- Provide clear exception handling with HTTP 429 responses
- Maintain high fault tolerance despite component failures

### Use Case Examples

- Maximum 2 posts per second per user
- Up to 10 accounts per day from single IP address
- 5 reward claims per week per device

## Step 2: High-Level Design

### Implementation Location

**Server-side placement** is preferred over client-side because clients cannot be trusted—requests can be forged by malicious actors.

**Rate limiter middleware** acts as a gatekeeper between clients and API servers, intercepting requests before they reach backend services.

### Request Flow

1. Client sends HTTP request through rate limiter middleware
2. Middleware evaluates if request count exceeds threshold
3. Under threshold → request routed to API servers
4. Over threshold → HTTP 429 response returned to client

**Deployment options include**:
- Embedded in application code
- Standalone middleware layer
- API Gateway component (increasingly common in microservices architecture)

## Rate Limiting Algorithms

### 1. Token Bucket Algorithm

**Mechanism**: Tokens accumulate in a container at fixed rates; each request consumes one token.

**Parameters**:
- Bucket capacity (maximum tokens)
- Refill rate (tokens added per second)

**Operation**:
- Tokens refill at preset intervals until capacity reached
- Excess tokens overflow and are discarded
- Request proceeds if tokens available; otherwise rejected
- Each request consumes exactly one token

**Use case example**: Capacity of 4 tokens, 2 added per second. Three requests arrive within one second; first two pass (2 tokens consumed), third rejected (insufficient tokens).

**Advantages**:
- Simple implementation
- Memory efficient
- Allows controlled traffic bursts when tokens available

**Disadvantages**:
- Two parameters require careful tuning
- Finding optimal bucket size and refill rate can be challenging

**Real-world adoption**: Amazon and Stripe use this algorithm.

### 2. Leaking Bucket Algorithm

**Mechanism**: Requests queue in FIFO structure and process at fixed rates.

**Parameters**:
- Queue size (bucket size)
- Outflow rate (fixed request processing rate)

**Operation**:
- New request arrives → system checks queue fullness
- Queue not full → request added to queue
- Queue full → request discarded
- Requests drain from queue at consistent intervals

**Advantages**:
- Memory efficient with bounded queue
- Ensures stable, predictable outflow rate
- Suits systems requiring consistent throughput

**Disadvantages**:
- Burst traffic fills queue with older requests, potentially blocking newer ones
- Two parameters require tuning
- Less responsive to sudden traffic spikes

**Real-world adoption**: Shopify employs this approach.

### 3. Fixed Window Counter

**Mechanism**: Timeline divided into equal-sized windows; counter increments per request within window.

**Operation**:
- Each time window has associated counter
- Requests increment counter by one
- Counter exceeds threshold → new requests rejected
- Counter resets when new time window begins

**Example**: 1-second windows allow 3 requests maximum. Window at 1:00:00-1:00:01 permits 3 requests; excess blocked.

**Critical limitation**: "Requests at window boundaries can cause twice the allowed traffic to pass through during edge transitions."

**Example of edge case problem**: System allows 5 requests per minute. At 2:00:30-2:01:30 boundary, 10 total requests pass (5 from previous window + 5 from current), doubling the intended limit.

**Advantages**:
- Very simple to implement
- Minimal memory requirements
- Easy to understand logic

**Disadvantages**:
- Spike vulnerability at window boundaries
- Can permit double the quota during edge transitions

### 4. Sliding Window Log

**Mechanism**: Maintains timestamps of all requests; removes outdated entries when evaluating new requests.

**Implementation detail**: "Timestamp data is usually kept in cache, such as sorted sets of Redis."

**Operation**:
- Request arrives → remove timestamps older than current window start
- Add new request timestamp to log
- If log size ≤ allowed count → request accepted
- If log size > allowed count → request rejected

**Example scenario** (2 requests per minute allowed):
- 1:00:01 → log empty, request allowed (log size: 1)
- 1:00:30 → timestamp added, request allowed (log size: 2)
- 1:00:50 → timestamp added, request rejected (log size: 3 exceeds limit)
- 1:01:40 → remove timestamps before 1:00:40, request allowed (log size: 2 after cleanup)

**Advantages**:
- Highly accurate rate limiting
- Requests never exceed limit within any rolling window
- Prevents edge case problems of fixed window

**Disadvantages**:
- High memory consumption
- Stores timestamps even for rejected requests
- Expensive for systems with very high request volumes

### 5. Sliding Window Counter

**Mechanism**: Hybrid approach combining fixed window simplicity with sliding window accuracy.

**Implementation**: Calculates current window requests plus weighted previous window requests.

**Formula**: Current requests + (Previous window requests × Overlap percentage)

**Example**: 7 requests per minute limit. Current minute has 3 requests, previous minute had 5 requests. New request arrives at 30% into current minute:
- Calculation: 3 + (5 × 0.7) = 6.5 requests
- Rounded to 6 → request allowed (under 7-limit)

**Advantages**:
- Smooths traffic spikes using average rates
- Memory efficient compared to sliding window log
- Good balance of accuracy and performance

**Disadvantages**:
- Approximation method assuming even request distribution
- Not suitable for very strict lookback windows
- Minor inaccuracy (0.003% wrong per Cloudflare testing on 400M requests)

## Step 3: Detailed Design

### Rate Limiting Rules Architecture

**Rule definition example** (Lyft open-source component):
```
domain: messaging
descriptors:
  - key: message_type
    value: marketing
    rate_limit:
      unit: day
      requests_per_unit: 5
```

This allows maximum 5 marketing messages daily.

**Storage approach**: Rules stored on disk, pulled into cache by worker processes.

### Handling Rate-Limited Requests

**HTTP 429 Response**: Standard status code indicating "too many requests" violation.

**Request disposition options**:
- Drop request immediately
- Enqueue for later processing (useful for critical operations like orders)

### Rate Limiter Headers

Clients receive three key HTTP headers:

- **X-Ratelimit-Limit**: Maximum calls allowed per time window
- **X-Ratelimit-Remaining**: Remaining allowed requests within window
- **X-Ratelimit-Retry-After**: Seconds to wait before retrying without throttling

### Detailed System Architecture

**Component responsibilities**:

1. **Rules Layer**: Persisted rate limiting configurations
2. **Worker Processes**: Periodically fetch rules from disk into cache
3. **Rate Limiter Middleware**: Intercepts requests, checks cache rules
4. **Redis Cache**: Stores counters and request tracking data
5. **Decision Point**: Routes based on limit status
   - Within limit → forward to API Servers
   - Exceeded → return 429 or queue for later processing

**Data flow**:
- Middleware loads rules from cache
- Fetches current counters from Redis
- Evaluates against limit threshold
- Updates Redis counter if request allowed
- Returns 429 if limit exceeded

### Redis Implementation Commands

**INCR**: Increments stored counter by one

**EXPIRE**: Sets automatic timeout for counter deletion after specified duration

These commands enable stateless, distributed rate limiting without database bottlenecks.

## Distributed Environment Challenges

### Race Condition Problem

**Scenario**: Multiple concurrent requests access same counter simultaneously.

**Problem sequence**:
1. Request 1 reads counter value (3)
2. Request 2 reads counter value (3) - simultaneously
3. Request 1 increments and writes back (4)
4. Request 2 increments and writes back (4)
5. Final value is 4, but should be 5 after two increments

This non-atomic operation causes counter inaccuracy.

**Solutions**:
- **Lua scripts**: Atomic operations at Redis level
- **Sorted sets**: Redis data structure enabling atomic increment-and-check operations

### Synchronization Across Multiple Rate Limiters

**Problem**: Stateless web tier routes clients to different rate limiter servers; each server unaware of other server's tracking data.

**Example**: Client 1 connects to Rate Limiter 1, Client 2 to Rate Limiter 2. If Client 1 later connects to Rate Limiter 2, no data exists about Client 1's prior requests.

**Solution - Centralized Redis**: All rate limiters query same Redis instance for counter state, enabling consistency regardless of which server handles request.

**Anti-pattern**: Sticky sessions (routing client to same server) are not recommended—lacks scalability and flexibility.

## Performance Optimization

### Multi-Data Center Strategy

"Most cloud service providers build many edge server locations around the world" to reduce latency.

**Implementation**: Geographically distributed edge servers automatically route traffic to nearest location.

**Example**: Cloudflare operates 194 edge servers globally as of 2020, minimizing user latency.

### Eventual Consistency Model

Data synchronization across distributed rate limiters uses eventual consistency—acceptable temporary inconsistencies resolve over time rather than requiring immediate synchronization.

## Monitoring & Analytics

**Key metrics to track**:
- Algorithm effectiveness
- Rule effectiveness

**Monitoring purpose**: Identify whether rate limiting rules are appropriately tuned.

**Example interventions**:
- Overly strict rules → many false positives → relax thresholds
- Ineffectiveness during traffic spikes (flash sales) → consider token bucket for burst handling
- Rules not preventing actual abuse → strengthen thresholds

## Advanced Considerations

### Hard vs Soft Rate Limiting

- **Hard**: Requests strictly cannot exceed threshold
- **Soft**: Requests may exceed threshold briefly before enforcement

### Multi-Layer Rate Limiting

Rate limiting applicable at multiple OSI model layers:

- **Layer 3 (Network)**: IP address-based using Iptables
- **Layer 4 (Transport)**: TCP/UDP connection limiting
- **Layer 7 (Application)**: HTTP-level limiting (focus of this design)

### Client Best Practices for Avoiding Rate Limiting

- Implement client-side caching to reduce API calls
- Understand published limits before sending requests
- Catch exceptions and implement graceful error handling
- Use exponential backoff in retry logic with adequate delays
- Monitor remaining quota using response headers

## Bucket Selection Strategy

**Number of buckets depends on rule granularity**:

- Different API endpoints require separate buckets
- IP-based limiting requires bucket per IP address
- User-based limiting requires bucket per user ID
- Global limits may share single bucket across system

**Example**: User with three rate limit rules (1 post/sec, 150 friends/day, 5 likes/sec) requires 3 buckets.

## Summary of Algorithm Comparison

| Algorithm | Accuracy | Memory | Burst Support | Complexity |
|-----------|----------|--------|---------------|------------|
| Token Bucket | Good | Low | Excellent | Low |
| Leaking Bucket | Good | Low | Poor | Low |
| Fixed Window | Poor | Low | Terrible | Very Low |
| Sliding Window Log | Excellent | High | Good | Medium |
| Sliding Window Counter | Good | Low | Good | Medium |

## Key Takeaways

1. Server-side implementation provides security; client-side cannot be trusted
2. Token bucket offers best balance of simplicity and practical effectiveness
3. Centralized Redis enables distributed consistency without sticky sessions
4. Atomic operations critical for race condition prevention
5. Multi-data center edge deployment minimizes global latency
6. Monitoring and tuning ensure rules match business requirements
7. HTTP headers provide client feedback on limit status and retry timing
