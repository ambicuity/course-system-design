# Hotel Reservation System

## Step 1: Understand the Problem and Establish Design Scope

### Requirements Clarification

**System Scale:**
- 5,000 hotels with 1 million total rooms
- Payment collected at reservation time
- Booking via website/app only
- Cancellations allowed
- 10% overbooking supported

**Feature Scope:**
- Display hotel-related pages
- Show room detail pages
- Reserve rooms
- Admin panel for hotel/room management
- Support overbooking feature
- Dynamic pricing by date

### Non-Functional Requirements

- High concurrency support (peak seasons and events)
- Moderate latency acceptable (a few seconds acceptable)

### Back-of-the-Envelope Estimation

**Reservation Calculations:**
- 70% occupancy rate
- 3-day average stay duration
- Daily reservations: (1M × 0.7) / 3 ≈ 233,333
- Reservation TPS: ~3 transactions per second

**User Flow Funnel (10% conversion between steps):**
- View hotel/room detail: 300 QPS
- Order confirmation page: 30 QPS
- Reserve rooms: 3 QPS

*A funnel diagram shows decreasing QPS across booking stages.*

---

## Step 2: High-Level Design and Buy-In

### API Design

**Hotel-Related APIs:**
| API | Purpose |
|-----|---------|
| GET /v1/hotels/ID | Retrieve hotel details |
| POST /v1/hotels | Add hotel (staff only) |
| PUT /v1/hotels/ID | Update hotel (staff only) |
| DELETE /v1/hotels/ID | Delete hotel (staff only) |

**Room-Related APIs:**
| API | Purpose |
|-----|---------|
| GET /v1/hotels/ID/rooms/ID | Get room details |
| POST /v1/hotels/ID/rooms | Add room (staff only) |
| PUT /v1/hotels/ID/rooms/ID | Update room (staff only) |
| DELETE /v1/hotels/ID/rooms/ID | Delete room (staff only) |

**Reservation-Related APIs:**
| API | Purpose |
|-----|---------|
| GET /v1/reservations | User reservation history |
| GET /v1/reservations/ID | Reservation details |
| POST /v1/reservations | Create reservation |
| DELETE /v1/reservations/ID | Cancel reservation |

**Reservation Request Example:**
```json
{
  "startDate": "2021-04-28",
  "endDate": "2021-04-30",
  "hotelID": "245",
  "roomID": "U12354673389",
  "reservationID": "13422445"
}
```

The `reservationID` serves as an idempotency key preventing double booking.

### Data Model Selection Rationale

**Relational Database chosen because:**

1. Read-heavy workflow suits relational databases well (visitors >> bookers)
2. ACID guarantees prevent negative balance, double charges, double reservations
3. Clear business data structure and stable entity relationships
4. Easier to reason about system consistency

**Query Patterns:**
- View hotel details
- Find available room types by date range
- Record reservations
- Look up reservations and history

### Initial Schema Design

**Key Tables:**
- `hotel`: hotel_id (PK), name, address, location
- `room_type_rate`: hotel_id (PK), date (PK), rate
- `guest`: guest_id (PK), first_name, last_name, email
- `reservation`: reservation_id (PK), hotel_id, room_id, start_date, end_date, status, guest_id

**Reservation Status States:**
- Pending
- Paid
- Refunded
- Canceled
- Rejected

*A state machine shows transitions: Pending → Canceled/Paid/Rejected; Paid → Refunded.*

### Critical Design Issue Identified

Users reserve **room types** (standard, king-size, queen-bed), not specific room numbers. Room numbers are assigned at check-in, not reservation. The initial schema incorrectly conflates room instances with room types.

### High-Level Microservice Architecture

**External Components:**
- Mobile/desktop users
- CDN for static assets
- Public API Gateway (rate limiting, authentication, routing)

**Core Services:**
- **Hotel Service**: Hotel/room information, static data, cacheable
- **Rate Service**: Dynamic room pricing by date
- **Reservation Service**: Handle reservations, track inventory
- **Payment Service**: Execute payments, update reservation status
- **Hotel Management Service**: Internal staff operations

**Key Architectural Characteristic:** Services are stateless and horizontally scalable; the database contains all state.

---

## Step 3: Design Deep Dive

### Improved Data Model

**Updated Reservation API Request:**
```json
{
  "startDate": "2021-04-28",
  "endDate": "2021-04-30",
  "hotelID": "245",
  "roomTypeID": "12354673389",
  "roomCount": "3",
  "reservationID": "13422445"
}
```

Key change: `roomTypeID` replaces `roomID`, and a `roomCount` parameter is added.

**Critical New Table: room_type_inventory**

Stores inventory tracking with composite primary key `(hotel_id, room_type_id, date)`:
- **hotel_id**: Hotel identifier
- **room_type_id**: Room type identifier
- **date**: Single date
- **total_inventory**: Available units minus maintenance holds
- **total_reserved**: Units booked for the specified date

**Sample Data:**
| hotel_id | room_type_id | date | total_inventory | total_reserved |
|----------|-------------|------|-----------------|-----------------|
| 211 | 1001 | 2021-06-01 | 100 | 80 |
| 211 | 1001 | 2021-06-02 | 100 | 82 |
| 211 | 1002 | 2021-06-01 | 200 | 16 |

**Inventory Pre-Population:**
Rows pre-populated for a 2-year future window. A daily scheduled job extends the data further.

**Storage Estimation:**
- 5,000 hotels × 20 room types × 2 years × 365 days = 73 million rows
- Single database sufficient; replication across regions/zones for high availability

**Availability Check Logic:**

1. Select the date range:
```sql
SELECT date, total_inventory, total_reserved
FROM room_type_inventory
WHERE room_type_id = ${roomTypeId} AND hotel_id = ${hotelId}
AND date BETWEEN ${startDate} AND ${endDate}
```

2. Validation check:
```
if (total_reserved + numberOfRoomsToReserve) <= total_inventory
  → Available
```

With 10% overbooking:
```
if (total_reserved + numberOfRoomsToReserve) <= 110% * total_inventory
  → Available with overbooking
```

**Scaling Strategies if Data Exceeds Single Database:**

1. Archive historical data (not frequently accessed)
2. Database sharding by hotel_id (natural choice for query patterns)
   - Shard key: `hash(hotel_id) % number_of_servers`

### Concurrency Issues

#### Problem 1: User Double-Clicks Reservation

Two INSERT operations from the same user create duplicate reservations.

**Solution: Idempotent APIs with Idempotency Key**

**Process:**
1. User enters reservation details, clicks "continue"
2. System generates a unique `reservation_id` via a globally unique ID generator
3. UI displays confirmation page with `reservation_id` shown
4. User clicks "Complete my booking" with `reservation_id` included
5. Second click attempts insertion with same `reservation_id`
6. Unique constraint on `reservation_id` (primary key) prevents duplicate

#### Problem 2: Race Condition - Multiple Users Booking Last Room

**Scenario:**
- Total inventory: 100 rooms
- Total reserved: 99 rooms
- User 1 and User 2 attempt simultaneous booking

Without isolation, both see 1 room available and successfully book (violating integrity).

**Root Cause:** A non-serializable isolation level allows dirty reads between transactions.

#### Solution Option 1: Pessimistic Locking

Locks records immediately when the transaction starts.

**MySQL Implementation:** `SELECT ... FOR UPDATE`

**Advantages:**
- Prevents stale data updates
- Easy implementation
- Effective with heavy contention
- Updates serialized by design

**Disadvantages:**
- Deadlocks possible with multiple resource locks
- Poor scalability: long-lived transactions block others
- Significant database performance impact
- **Not recommended for reservation system**

#### Solution Option 2: Optimistic Locking

Allows concurrent reads, validates version numbers during write.

**Implementation Steps:**
1. Add a "version" column to the table
2. Application reads row including version number
3. Application increments version by 1 on update
4. Database validates new_version = old_version + 1
5. Transaction aborts if validation fails; user retries

**Advantages:**
- No database locks required
- Faster than pessimistic locking
- Good for low-contention scenarios

**Disadvantages:**
- Performance degrades dramatically under high concurrency
- Many failed validations cause repeated retries
- **Suitable for hotel reservations** (low QPS = ~3 TPS)

#### Solution Option 3: Database Constraints

```sql
CONSTRAINT `check_room_count` CHECK((total_inventory - total_reserved >= 0))
```

**Advantages:**
- Simple implementation
- Works well with minimal contention
- Constraint enforced by database

**Disadvantages:**
- High failure rate during peak load
- Users see "available" then receive "unavailable" error
- Not version-controlled like application code
- Database portability issues
- **Acceptable option** (works with low QPS)

#### Recommended Approach

**Optimistic locking preferred** due to low average QPS (~3 transactions/second), minimal concurrent attempts on the same room type, acceptable UX with occasional retries, simpler implementation, and no deadlock risk.

### Scalability Considerations

#### Database Sharding Strategy

When load increases 1000x (booking.com / expedia.com scale):
- Sharding key: `hotel_id % 16`
- Example: hotel_id=17 → 17 % 16 = 1 → Shard 1
- Load distribution: 30,000 QPS ÷ 16 shards = 1,875 QPS/shard

#### Caching Strategy

**Cache Choice: Redis** — TTL expires old data automatically, LRU eviction optimizes memory, in-memory performance for fast reads.

**Cache Architecture:**
- **Inventory Cache (Redis):** Key = `hotelID_roomTypeID_{date}`, Value = number of available rooms
- **Inventory Database:** Source of truth, updated first on booking, changes propagated asynchronously to cache

**Cache Update Flow:**
1. Reservation request received
2. Query inventory → consult Redis cache
3. If available in cache → attempt reservation
4. Update database first (source of truth)
5. Asynchronously propagate change to cache

**Asynchronous Propagation Options:**
- Application code updates cache after database commit
- Change Data Capture (CDC) via Debezium reads database changes and applies them to a Redis sink

**Consistency Trade-Off Analysis:** Data inconsistency between cache and database is acceptable because the database performs final validation regardless of cache state.
- **Scenario 1:** Cache shows available, DB shows unavailable → booking fails, user refreshes (sees accurate state)
- **Scenario 2:** Cache shows unavailable, DB shows available → pessimistic UX but correct outcome

### Data Consistency in Microservice Architecture

#### Hybrid Approach (Recommended)

Reservation Service owns both the reservation and inventory tables in the same relational database, leveraging ACID within a single database to simplify concurrency handling.

#### Pure Microservice Approach (Not Recommended)

Each microservice has its own database (Reservation DB, Inventory DB, Payment DB). Logically atomic operations span services without transaction boundaries, risking inconsistency.

**Industry Solutions for Consistency:**

1. **Two-Phase Commit (2PC)** — atomic commit across nodes, but blocking protocol with poor performance; a single node failure blocks the system. Not recommended for distributed systems.
2. **Saga Pattern** — sequence of local transactions; each step publishes a message triggering the next; compensating transactions undo changes on failure; relies on eventual consistency.

**Complexity vs. Value:** Pure microservice consistency mechanisms greatly increase complexity. The pragmatic hybrid approach is preferable here.

---

## Step 4: Wrap Up

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Relational DB | ACID properties, read-heavy workload, clear schema |
| Room types not rooms | Users reserve categories; specific room assigned at check-in |
| Idempotent API | Prevents double-booking from client double-clicks |
| Optimistic locking | Low QPS allows occasional retries |
| Database sharding | Scales read/write beyond single server |
| Redis cache | Reduces database load, improves read latency |
| Hybrid microservices | Balances scalability with consistency guarantees |

### Reference Materials
- Microservices; gRPC; Serializability; Optimistic/pessimistic record locking; Change data capture; Debezium; Two-phase commit protocol; Saga pattern.

---

## Deep Enrichment: Hotel Reservation System

### Back-of-the-Envelope Math (Detail)

Worked numbers, step by step, using the chapter's headline assumptions (5,000 hotels, 1M total rooms, 70% occupancy, 3-day average stay).

**Step 1 — Daily reservations.**
- Rooms occupied/day = 1,000,000 × 0.70 = 700,000 room-nights.
- Stay duration = 3 days → reservations/day = 700,000 / 3 ≈ 233,333.
- Average reservation TPS = 233,333 / 86,400 ≈ 2.7 → round to ~3 TPS (chapter figure).

**Step 2 — Peak QPS for reservation writes.**
- A hotel/region may concentrate demand (Taylor Swift concert, citywide convention). Assume 10× burst during peaks: ~30 TPS for reservations. The bottleneck is not raw TPS; it is concurrent contention on a single `(hotel_id, room_type_id, date)` row.

**Step 3 — Read funnel.**
- Reservation page views: 300 QPS average → 3,000 QPS peak.
- Booking confirmations: 30 QPS → 300 QPS peak.
- Conversion 10% per stage; conversion variance during marketing campaigns is 2–3× higher (estimate; observe via A/B tests).

**Step 4 — Inventory row count.**
- 5,000 hotels × 20 room types × 2 years × 365 days = 73 million rows.
- Add 1 year of historical (read-only) rows → ~110 million rows.
- Plus reservation rows: ~233K/day × 365 ≈ 85M/year × 3 years retention = ~250M rows.

**Step 5 — Storage.**
- Inventory row ~64 bytes → 110M × 64 B ≈ 7 GB.
- Reservation row ~256 bytes → 250M × 256 B ≈ 64 GB.
- With indexes and overhead ×3: ~210 GB. A single modern Postgres / MySQL primary handles this trivially with replicas for HA.

**Step 6 — Sharded by hotel_id.**
- 30,000 QPS ÷ 16 shards = 1,875 QPS/shard. Comfortable headroom on commodity hardware.
- A single hot hotel (e.g., a Las Vegas casino) might still saturate one shard; mitigation: split very large chains across multiple shard buckets by `(hotel_chain_id, hotel_id)`.

**Step 7 — Cache hit ratio and staleness budget.**
- 90%+ cache hit ratio for hotel/room metadata is realistic at this scale (estimate; Booking.com has historically reported ~85–90% in similar architectures).
- Cache invalidation must be event-driven (CDC), not TTL-only, otherwise stale availability shows.

**Step 8 — Pricing rate rows.**
- `room_type_rate` rows = 5,000 × 20 × 730 days ≈ 73M. Same shape as inventory. Co-locate on the same shard.

### ASCII Architecture Diagrams

#### 1) End-to-end booking flow (sequence)

```
Guest      Web/App      API GW     Hotel Svc     Rate Svc   Reservation Svc   Payment Svc   Postgres   Redis
  |            |            |           |            |              |               |             |          |
  | Search     |            |           |            |              |               |             |          |
  |----------->|            |           |            |              |               |             |          |
  |            | GET /search|            |            |              |               |             |          |
  |            |----------->|            |            |              |               |             |          |
  |            |            | GET hotels|            |              |               |             |          |
  |            |            |----------->|            |              |               |             |          |
  |            |            | cache hit?|            |              |               |             |          |
  |            |            |----------- |-->         |              |               |             |          |
  |            |            |<---list---|            |              |               |             |          |
  |            |            | GET rates |             |              |               |             |          |
  |            |            |----------------------->|               |               |             |          |
  |            |            |<---rates--|             |              |               |             |          |
  |            |<--200------|            |            |              |               |             |          |
  |            |            |            |            |              |               |             |          |
  | Click book|             |            |            |              |               |             |          |
  |----------->| POST /resv |            |            |              |               |             |          |
  |            |----------->|------------|------------|--------------->|               |             |          |
  |            |            |            |            | check avail  |               |             |          |
  |            |            |            |            |------------->|               |             |          |
  |            |            |            |            |              |  SELECT FOR UPDATE           |
  |            |            |            |            |              |------------------------------> |
  |            |            |            |            |              | UPDATE inventory             |
  |            |            |            |            |              |------------------------------> |
  |            |            |            |            |              | INSERT reservation (Pending) |
  |            |            |            |            |              |------------------------------> |
  |            |            |            |            |              |      |                       |
  |            |            |            |            |              |      |  call charge           |
  |            |            |            |            |              |<-----|                       |
  |            |            |            |            |              | Payment Svc -> Stripe         |
  |            |            |            |            |              | 200 ok                        |
  |            |            |            |            |              | UPDATE status=Paid           |
  |            |            |            |            |              |------------------------------> |
  |            |            |            |            |              | async CDC -> Redis evict     |
  |            |            |            |            |              |-----------------------------|->|
  |<--200 OK---|            |            |            |              |               |             |          |
```

#### 2) Inventory contention (the "last room" race)

```
User A            Reservation Svc            Postgres                 User B
  |                       |                      |                       |
  | POST /reservations    |                      |                       |
  |---------------------->|                      |                       |
  |                       | BEGIN                |                       |
  |                       | SELECT ... FOR UPDATE|                       |
  |                       |--------------------->|                       |
  |                       | (99 reserved of 100)|                       |
  |                       | UPDATE +1            |                       |
  |                       | COMMIT               |                       |
  |                       |<------------------   |                       |
  |                       | 200 OK (User A got it)                      |
  |                       |                      |   POST /reservations  |
  |                       |                      |<----------------------|
  |                       |                      | BEGIN                 |
  |                       |                      | SELECT ... FOR UPDATE |
  |                       |                      | (100 reserved of 100) |
  |                       |                      | UPDATE would violate |
  |                       |                      | ROLLBACK              |
  |                       |                      | 409 Conflict          |
```

Alternative (optimistic locking) avoids the long lock; see Q3.

#### 3) Sharded DB layout (16 shards by hotel_id)

```
+------------------ API Gateway ------------------+
|  Hotel Svc       Rate Svc       Reservation Svc  |
+--------+---------+-----------------+-------------+
         |                   |                 |
         |  Shard router (hotel_id % 16)        |
         +---+---+---+---+---+---+---+---+---+---+
             |   |   |   |   |   |   |   |   |
             v   v   v   v   v   v   v   v   v
            S0  S1  S2  S3  S4  S5  S6  S7  S8  ... S15
          (each shard: Postgres primary + 2 replicas + Redis cache)
```

### Trade-off Tables

#### 1) Concurrency-control strategy

| Strategy | Throughput | Latency | Failure UX | Ops burden | Best fit |
|----------|------------|---------|-----------|------------|----------|
| Pessimistic `SELECT ... FOR UPDATE` | Low–medium (locks held) | Higher (lock wait) | Clean (single winner) | Low | High-contention, low TPS |
| Optimistic (version column) | High (no locks) | Low (fast path) | User retry on conflict | Medium | Low-contention, read-heavy |
| DB CHECK constraint | High (DB enforces) | Low | Fail fast with DB error | Low | Already-correct schemas |
| Application semaphore per (hotel, type, date) | Medium | Medium | Retry | High (stateful lock service) | Distributed reservations across DB shards |
| Saga over multi-service writes | High (no global lock) | Medium | Compensating actions | High | Microservices with separate DBs |

#### 2) Microservices vs. monolith

| Approach | Time to ship | Consistency | Operational cost | When to use |
|----------|--------------|-------------|------------------|-------------|
| Single monolith | Days | Easy (single DB transaction) | Low | Early stage, single team |
| Hybrid (Reservation owns its DB) | Weeks | Strong (ACID) | Medium | Chapter recommendation |
| Pure microservices | Months | Eventual (Saga) | High | Independent deploys, very large orgs |
| Modular monolith (separate modules, single deploy) | Days | Strong | Low | Mid-stage with one team |

#### 3) Cache update mechanism

| Mechanism | Latency | Consistency | Failure mode | Ops burden |
|-----------|---------|-------------|--------------|------------|
| TTL only | High (stale up to TTL) | Stale | TTL drift, hot keys | Lowest |
| App writes DB then Redis (write-through) | Low | Strong if both succeed | Crash between → drift | Medium |
| CDC (Debezium) -> Redis sink | ~1s | Strong, eventually | CDC lag > 5 min → drift | Higher (Kafka + connector) |
| Read-through with single-flight | Low | Strong on read | Cache stampede risk | Medium |

#### 4) Payment integration patterns

| Pattern | Latency | Failure handling | Cost | Notes |
|---------|---------|------------------|------|-------|
| Synchronous (charge inline) | 1–3 s | Simple rollback | Standard | Most common |
| Async with pre-auth + capture | < 200 ms (hold) + capture later | Two-phase, more states | Slightly higher (auth fee) | Hotels with late modification |
| Third-party wallet (PayPal, Apple Pay) | ~1 s | Provider-managed | Standard | Web/mobile only |
| Tokenized card vault (Stripe) | < 500 ms | Vault-managed PCI | Reduced PCI scope | Industry default |

### Real-World Case Studies

#### 1) Booking.com
Booking.com operates one of the largest transactional reservation systems in the world, processing millions of room-nights per day at peak. They famously **run thousands of A/B tests simultaneously** and treat their platform as an experimentation engine — every variant, every price, every UI string is a hypothesis tested against a control. The infrastructure uses a heavily sharded relational core for inventory and reservations, with extensive caching of hotel metadata. Their engineering org has published talks (e.g., "Booking.com: Growing Without Losing Focus") emphasizing sharded Postgres, idempotent booking flows, and the operational cost of double-booking incidents. (Sources: Booking.com engineering blog; QCon talks.)

#### 2) Expedia / Hotels.com
Expedia Group runs a multi-brand stack (Expedia, Hotels.com, Vrbo, Trivago) with a shared inventory/reservation core. Historically they standardized on a service-oriented architecture with sharded MySQL and an event bus for cross-service state propagation. Their public talks (e.g., at AWS re:Invent) describe using **DynamoDB** for some reservation metadata and **RDS MySQL** for inventory, with Kafka as the event backbone.

#### 3) Airbnb
Airbnb's reservation system design has been published in detail ("Scaling Airbnb's Reservation System", 2018-ish). The key idea: **decouple inventory** from reservations by maintaining a per-night availability counter in a fast key-value store and serializing writes through a leader-elected per-inventory-unit actor. The reservation service publishes committed bookings to a Kafka topic, and downstream services (pricing, search ranking, analytics) consume asynchronously. This trades strict inventory consistency for **throughput and availability** during traffic spikes. (Sources: Airbnb engineering blog.)

#### 4) Marriott / IHG / Hilton (chain CRMs)
Large hotel chains historically ran on-premises PMS (Property Management Systems) like **Opera** (Oracle) and **Sabre Hospitality** for property-level inventory. Cloud transformation moved guest profile and loyalty data into central CRMs, with reservation flows integrated via APIs. The relevant interview lesson: **legacy integration with GDS / PMS systems** is a non-trivial constraint — design must include adapters and event translation.

#### 5) Amadeus / Sabre / Galileo (GDS)
Global Distribution Systems (Amadeus, Sabre, Travelport/Galileo) power **inter-agency** bookings between hotels, airlines, and travel agents. Their reservation systems must handle long-running holds ("option" bookings) with TTLs of hours, complex rate negotiations, and OTA (Online Travel Agency) integrations. Architectural lessons: state machines for hold → confirm → cancel, idempotency keys, and partial-confirm compensation flows.

#### 6) OYO Rooms
OYO scaled reservation engineering rapidly during 2018–2021 and published blogs on sharding strategies and inventory snapshots. Their system uses **per-hotel pre-allocated inventory snapshots** rebuilt nightly and adjusted transactionally — a hybrid between pre-allocation (fast reads) and on-write adjustments (correct writes).

#### 7) HotelEngine / corporate housing platforms
B2B hotel platforms face bulk reservations (15+ rooms per booking, multi-month stays). They typically pre-negotiate block inventory with hotels and use a **block inventory** model — pre-allocated inventory that can be released back if not used. Architecturally similar to airline seat inventory systems.

### Common Pitfalls & Failure Modes

#### 1) Overbooking math is wrong by 1%
**Scenario:** A 1% misconfiguration on `overbooking_factor` (e.g., 110% instead of 105%) compounds across a property for a year. During a peak week, every booking arrives to a fully overbooked hotel; the hotel must walk guests. Cost: relocation + reputation.
**Mitigation:** encode the overbooking factor in **policy** (per-hotel, per-season), not in code; expose it as a configuration with audit trail; alert when overbookings actually trigger walkings.

#### 2) Inventory timezone bug
**Scenario:** A hotel in Tokyo, a guest in New York. Server stores dates in UTC; UI shows "June 2" in JST. The check-in date at the Tokyo hotel is June 2 JST = June 1 18:00 UTC. The reservation system treats "June 1" as a stay, blocking June 1 inventory that the hotel expected to sell. Guest shows up June 2 JST and the hotel is overbooked for June 1.
**Mitigation:** store dates as **local civil dates anchored to the property's timezone**; convert at display and comparison edges only; use a `property_id -> timezone` mapping table; review with property staff quarterly.

#### 3) Idempotency key reuse on retried payment
**Scenario:** Payment gateway times out, client retries with the **same `reservation_id`**. First call actually succeeded server-side; second call sees a `Pending` reservation, attaches a second payment authorization, and the user gets double-charged when both auths capture.
**Mitigation:** store `payment_id` on the reservation row; on retry, look up the existing payment and **idempotently call the gateway with the gateway's own idempotency key** (not just your `reservation_id`).

#### 4) Pessimistic lock across many date rows
**Scenario:** A 7-night stay locks 7 rows. Two long stays (14 nights each) on overlapping dates block each other because the lock ordering differs. Deadlock detected, transactions roll back, user sees a 500 error.
**Mitigation:** always lock rows in **date ascending order** to avoid cycle deadlocks; or use optimistic locking which doesn't take row locks; or use a single coarse lock per `(hotel_id, room_type_id)` per write — fewer locks but lower concurrency.

#### 5) Sharding hotspot on a single hotel
**Scenario:** A famous hotel chain (e.g., one Vegas property) accounts for 30% of global reservations. All reservations route to shard `hash(hotel_id) % 16 == X`. That shard saturates.
**Mitigation:** composite shard key `(chain_id, hotel_id)` so a single property can fan out across multiple shards; or shard by `(region, hotel_id)` for geographic spread; or allocate dedicated shards to "VIP" properties.

#### 6) Cache stampede on a popular search
**Scenario:** A celebrity tweets a hotel; search QPS spikes 100×. Redis cache misses for "rooms available in 3 nights"; all requests fall through to the database. DB CPU pegged.
**Mitigation:** single-flight / request coalescing (only one process per key recomputes, others wait); **stale-while-revalidate**; pre-warm cache on trending events; use a CDN for static hotel data.

#### 7) Rate service and inventory service disagree on price
**Scenario:** Rate Service says $200/night based on dynamic pricing; Reservation Service commits inventory at $200; the next minute, the Rate Service refreshes from a slower upstream and returns $180; user sees inconsistent prices.
**Mitigation:** **snapshot the price into the reservation row at booking time**; never re-derive price after booking for display; rate quotes must be timestamped and locked into the reservation.

### Interview Q&A

**Q1 — Clarifications before designing.**
Sketch: ask about scale (hotels, room count, peak QPS), whether check-in/check-out happens in-system or off-system (PMS), overbooking policy (per-hotel, per-season), dynamic pricing source (in-house ML, vendor, manual), payment provider (Stripe/Adyen/Braintree), refund policy (full/partial/non-refundable), and currency/multi-region support. Confirm cancellation policy states (full refund window, partial refund window, no refund).

**Q2 — Capacity estimation.**
Sketch: 233K reservations/day ≈ 3 TPS average, ~30 TPS peak. Inventory rows ≈ 73M for 2 years; 250M reservation rows over 3 years. Storage ~210 GB including indexes. Cache hit rate target ~90%. Sharding by `hotel_id % 16` distributes 30K QPS → ~1.9K QPS/shard. Pricing and rate rows co-locate on the inventory shard.

**Q3 — Last-room race: pessimistic vs. optimistic vs. constraint.**
Sketch: with ~3 TPS average and modest contention per room-type, **optimistic locking** wins — no long locks, retries are rare, no deadlock surface. Pessimistic is appropriate only if a single property can see >100 concurrent offers/sec. CHECK constraints are simple but produce user-visible failures; combine with optimistic retry.

**Q4 — Why not pure microservices with a Saga?**
Sketch: each step (reserve inventory → charge payment → send confirmation) is a separate service with its own DB. Sagas require compensating transactions (cancel inventory, refund payment) and eventual consistency. For a 3 TPS system, the operational overhead of orchestrating Sagas far exceeds the cost of a single-DB transaction. Revisit Saga only when write QPS exceeds ~1,000 TPS or teams need independent deploys.

**Q5 — "What if we 10×?"**
Sketch: shard the relational DB; move the rate service to a streaming pipeline (Kafka + Flink) that recomputes prices nightly and pushes to the read replicas; cache aggressively with CDC-driven invalidation. Consider moving from MySQL to a distributed SQL (CockroachDB, Spanner) if global by then.

**Q6 — "What if we go global?"**
Sketch: regional sharding by continent; each region owns its reservations; cross-region reads via read replicas or a materialized aggregator. Cross-region bookings (guest in Asia books a US hotel) write to the US region's DB and publish to the user's home region via Kafka. Watch for **timezone** (dates stored at property) and **currency** (FX snapshot at booking). Payment is per-region via a local PSP.

**Q7 — How do you handle dynamic pricing without breaking availability?**
Sketch: pricing is **read-side**: Rate Service computes per-night rates from a pricing engine; Reservation Service snapshots the rate into the reservation row at booking time. Availability is **write-side** and authoritative in the DB. Decoupling keeps the rate engine pluggable and the reservation system simple.

**Q8 — Idempotency under retry.**
Sketch: client sends `reservation_id` (UUID v7 with timestamp + randomness). Reservation Service begins transaction; checks `reservation_id` in a unique index; if exists, returns the prior result; else inserts. Payment call uses the **gateway's** idempotency key, not the reservation ID, so the gateway deduplicates on its side.

### Key Terms / Glossary

| Term | Precise definition | Common misconception |
|------|---------------------|----------------------|
| **Room type vs. room instance** | A category (King, Queen) vs. a physical room (#412). Inventory is tracked per room type; assignment to instances happens at check-in. | Treating a `room_id` as inventory causes "all rooms of this type are sold" miscounts. |
| **Overbooking factor** | Maximum `total_reserved / total_inventory` (e.g., 1.10 = 10% overbooking). | A global factor is wrong; it should be per-property and per-season. |
| **Idempotency key** | A client-generated UUID that lets the server safely retry the same logical operation. | "Same request body" is not an idempotency key — only a unique client-generated token. |
| **Pessimistic locking** | `SELECT ... FOR UPDATE` takes a row-level lock for the duration of the transaction. | Long-held locks cause contention and deadlocks; not idempotent across crashes. |
| **Optimistic locking** | Read with a version; write only if the version still matches; otherwise abort and retry. | Doesn't prevent lost updates without the version column. |
| **Saga** | A sequence of local transactions with compensating actions for failures. | Not a global transaction; the system can be in an inconsistent intermediate state. |
| **Two-phase commit (2PC)** | A coordinator asks all participants to "prepare", then "commit". | Blocking protocol; coordinator failure stalls all participants. |
| **Change Data Capture (CDC)** | Reading database change logs (binlog, WAL) to publish events without app changes. | Without ordering guarantees, downstream caches can be inconsistent. |
| **Soft reservation / hold** | A temporary inventory decrement with a TTL; released if not confirmed. | Without TTL enforcement, holds leak inventory. |
| **No-show** | A confirmed reservation where the guest doesn't arrive; the property keeps the payment and may resell the room. | Different from cancellation; affects revenue and overbooking math. |
| **Walk** | When a hotel has to relocate a confirmed guest due to overbooking; compensated by the property. | The cost of bad overbooking math is measured in walks per month. |
| **Property Management System (PMS)** | On-property software that tracks rooms, guests, check-in/out. | Cloud platforms must integrate with the PMS via APIs; reservation ≠ check-in. |
| **GDS** | Global Distribution System (Amadeus, Sabre, Travelport); the wholesale reservation backbone for travel agents. | GDS rate/availability formats are different from OTA APIs. |