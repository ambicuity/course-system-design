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
