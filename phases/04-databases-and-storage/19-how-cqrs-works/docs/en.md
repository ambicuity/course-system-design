# How CQRS Works?

> Reads and writes have different shapes — stop forcing them through the same model.

**Type:** Learn
**Prerequisites:** Event Sourcing, Database Replication, CAP Theorem
**Time:** ~25 minutes

## The Problem

A single domain model optimised for writes is almost always a terrible fit for reads, and vice versa. Imagine an e-commerce order service. The write path validates business rules — inventory checks, payment holds, fraud scoring — and persists a normalized, integrity-constrained Order aggregate. Now a product page needs to display "orders placed by this customer in the last 30 days, grouped by category, with discount totals." That query joins five tables, aggregates rows, and applies presentation logic. Running it against the same write model means the query fights with write locks, and every schema change that improves write throughput risks breaking a dozen read-side queries.

The deeper issue is that reads and writes have fundamentally different scaling profiles. In most web applications reads outnumber writes by 10:1 to 100:1. Scaling a single database uniformly means over-provisioning for writes to accommodate read volume — or adding read replicas, which is just informal CQRS without the architecture to support it cleanly.

CQRS (Command Query Responsibility Segregation) makes the split explicit and formal. The write side owns state mutation; the read side owns query optimisation. Each can be scaled, deployed, and evolved independently.

## The Concept

CQRS is based on Bertrand Meyer's Command-Query Separation principle: a method should either change state (command) or return state (query), never both. CQRS applies this at the architectural level — entire subsystems, databases, and service entry points are partitioned by their role.

### Two Sides, Two Models

```
 CLIENT
   │
   ├─── Command (write intent) ──────────────────────────────────────────┐
   │                                                                      ▼
   │                                                          ┌──────────────────────┐
   │                                                          │   Command Handler    │
   │                                                          │  (validate, execute) │
   │                                                          └─────────┬────────────┘
   │                                                                    │
   │                                                          ┌─────────▼────────────┐
   │                                                          │    Domain Model      │
   │                                                          │  (business rules,    │
   │                                                          │   aggregates)        │
   │                                                          └─────────┬────────────┘
   │                                                                    │
   │                                          ┌─────────────────────────▼──────────────────────┐
   │                                          │              Write Database                    │
   │                                          │      (normalized, transactionally safe)        │
   │                                          └─────────────────────────┬──────────────────────┘
   │                                                                    │
   │                                                          Domain Events published
   │                                                                    │
   │                                          ┌─────────────────────────▼──────────────────────┐
   │                                          │           Event Bus / Message Broker           │
   │                                          └─────────────────────────┬──────────────────────┘
   │                                                                    │
   │                                          ┌─────────────────────────▼──────────────────────┐
   │                                          │            Projection / Read Model Builder     │
   │                                          │       (denormalize, aggregate, reshape)        │
   │                                          └─────────────────────────┬──────────────────────┘
   │                                                                    │
   │                                          ┌─────────────────────────▼──────────────────────┐
   │                                          │              Read Database                     │
   │                                          │   (denormalized, query-optimized projections)  │
   │                                          └─────────────────────────┬──────────────────────┘
   │                                                                    │
   └─── Query (read intent) ──────────► Query Handler ─────────────────┘
                                        (no domain logic, just fetching)
```

### Commands vs Queries

| Dimension         | Command                              | Query                                 |
|-------------------|--------------------------------------|---------------------------------------|
| Intent            | Change system state                  | Return data                           |
| Return value      | Acknowledgement or error             | Data payload                          |
| Side effects      | Required (that's the point)          | None (idempotent)                     |
| Validation        | Full business rule enforcement       | Input sanitization only               |
| Database access   | Write database, with transactions    | Read database, no locks needed        |
| Scaling strategy  | Scale via sharding / queue           | Scale via replicas / caches           |

### Consistency Model

The read model is **eventually consistent** with the write model. After a command succeeds, the domain event propagates through the bus, the projection builder processes it, and the read database updates — this lag is typically milliseconds to low seconds. Clients must design for this: a successful "place order" command does not mean the order immediately appears in a `GET /orders` response.

This is not a bug — it is the explicit trade made to enable independent scaling and read-model flexibility. When strong consistency is required for a specific flow (e.g., double-spend prevention), keep that logic on the write side and return the authoritative answer from the command response itself.

## Build It / In Depth

Let us trace an order placement through a CQRS system step by step.

### Step 1 — Issue a Command

```python
# Command is a plain data object — no behavior, just intent
@dataclass(frozen=True)
class PlaceOrderCommand:
    order_id: str
    customer_id: str
    items: list[OrderItem]
    payment_token: str
```

The command is dispatched to a command bus, which routes it to the correct handler.

### Step 2 — Command Handler Enforces Business Rules

```python
class PlaceOrderCommandHandler:
    def __init__(self, order_repo, payment_service, event_bus):
        self._repo = order_repo
        self._payments = payment_service
        self._bus = event_bus

    def handle(self, cmd: PlaceOrderCommand) -> None:
        # Load aggregate (from write DB or event store)
        order = Order.create(cmd.order_id, cmd.customer_id, cmd.items)

        # Domain rule: payment must be authorised before confirming
        auth = self._payments.authorise(cmd.payment_token, order.total)
        if not auth.success:
            raise PaymentDeclinedError(auth.reason)

        order.confirm(auth.transaction_id)

        # Persist state to write database (transactional)
        self._repo.save(order)

        # Publish domain events raised by the aggregate
        for event in order.uncommitted_events:
            self._bus.publish(event)
```

### Step 3 — Event Updates the Read Model

```python
class OrderPlacedProjection:
    """Listens for events and maintains the read-side orders_summary table."""

    def on_order_confirmed(self, event: OrderConfirmedEvent) -> None:
        self._read_db.execute(
            """
            INSERT INTO orders_summary
                (order_id, customer_id, status, total, placed_at)
            VALUES
                (:order_id, :customer_id, 'CONFIRMED', :total, :placed_at)
            ON CONFLICT (order_id) DO UPDATE
                SET status = EXCLUDED.status,
                    total  = EXCLUDED.total
            """,
            event.__dict__,
        )
```

The `orders_summary` table is a **projection** — a denormalized, pre-shaped view optimised for the exact query patterns the UI needs.

### Step 4 — Query Fetches Directly from the Projection

```python
class CustomerOrdersQueryHandler:
    def handle(self, query: GetCustomerOrdersQuery) -> list[OrderSummary]:
        rows = self._read_db.fetch_all(
            """
            SELECT order_id, status, total, placed_at
            FROM   orders_summary
            WHERE  customer_id = :customer_id
            ORDER  BY placed_at DESC
            LIMIT  :limit
            """,
            {"customer_id": query.customer_id, "limit": query.page_size},
        )
        return [OrderSummary(**row) for row in rows]
```

No joins. No locks. No domain model loaded. The query handler is deliberately thin — it is a database call with a schema mapping.

### Read Database Options

You are not limited to the same database engine on the read side:

```
Write DB:  PostgreSQL (normalized, ACID)
Read DB:   Elasticsearch  ──►  full-text search projections
           Redis           ──►  hot-path counters and sorted sets
           MongoDB         ──►  nested document projections
           ClickHouse      ──►  analytical aggregations
```

This is one of CQRS's most powerful properties: the read model can be rebuilt from events at any time by replaying the event log. Changing the shape of a projection means replaying events into a new schema — no migration required.

## Use It

### Where CQRS Appears in Real Systems

| System / Tool          | How CQRS Is Applied                                                        |
|------------------------|----------------------------------------------------------------------------|
| **Axon Framework**     | Java framework with first-class command bus, event bus, and query bus      |
| **EventStoreDB**       | Append-only event store; projections built in JavaScript or C#             |
| **AWS DynamoDB Streams** | Write to DynamoDB, stream changes to Lambda that updates an OpenSearch index |
| **Apache Kafka**       | Events on a topic act as the bridge; consumers build read-side projections |
| **Microsoft Azure**    | CQRS + Event Sourcing is a named pattern in Azure Architecture Center      |
| **NestJS CQRS module** | `@CommandHandler`, `@QueryHandler` decorators; built-in command/query buses|

### When to Reach for CQRS

Use CQRS when:
- Read and write traffic have very different volumes or scaling requirements.
- Query shapes are complex or numerous and don't map naturally to the write schema.
- You are already using event sourcing and want to derive multiple projections.
- Teams working on read and write paths need to deploy independently.

Avoid CQRS when:
- The domain is simple CRUD with no complex business rules.
- The team is small and the added operational overhead outweighs the benefit.
- Strong consistency across reads and writes is non-negotiable everywhere.

## Common Pitfalls

- **Returning write-model data from the command response.** Commands should return an acknowledgement, not a domain object. If the client needs data after a write, it should poll the query side or use a correlation ID to fetch the specific record once the projection has updated.

- **Sharing the same database for reads and writes.** Just using separate tables in one Postgres instance defeats the purpose — schema lock contention, competing workloads, and coupled deployments remain. The read store should be independently scalable.

- **Neglecting projection rebuild capability.** If your read database can not be rebuilt from the event log (because you store events nowhere), you lose CQRS's biggest safety valve. Always pair CQRS with an event log or event store, even if you are not doing full event sourcing.

- **Ignoring eventual consistency in the UI.** After a command succeeds, the UI that immediately re-fetches the same record may see stale data. Handle this with optimistic UI updates, polling with a version token, or a websocket notification once the projection updates.

- **Over-applying CQRS to every service.** CQRS adds operational complexity — separate models, projection infrastructure, eventual consistency handling. Apply it where the read/write asymmetry genuinely justifies it; keep simple services as simple CRUD.

## Exercises

1. **Easy** — Draw the data flow for a "cancel order" command in a CQRS system. Identify every component the command touches before the `orders_summary` read projection reflects the cancellation.

2. **Medium** — A product analytics team needs a projection showing "total revenue per product category per day" derived from the same `OrderConfirmedEvent`. Design the projection schema and the event handler that maintains it. How does this illustrate the benefit of multiple independent projections?

3. **Hard** — Your read database (Elasticsearch) has gone offline for two hours. Events were buffered in Kafka. Design the procedure for bringing the read model back into sync without losing events and without downtime to the write path. What guarantees does your approach provide, and where are the remaining gaps?

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|------------------------|
| **Command** | Any write request | A validated intent to mutate state; returns no domain data, only success/failure |
| **Query** | Any GET request | A side-effect-free request for data; never changes state |
| **Projection** | A database view | A denormalized read model actively maintained by processing domain events |
| **Eventual Consistency** | Data might be wrong | Data will converge to the correct state after a bounded propagation delay |
| **Event Bus** | A message queue | The transport layer carrying domain events from the write side to projection builders |
| **Command Handler** | A controller action | The single class responsible for validating one command and orchestrating its execution against the domain model |
| **Read Model** | A cached copy | A purpose-built data structure shaped for query performance, not for enforcing business rules |

## Further Reading

- [Microsoft Azure Architecture: CQRS Pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs) — Canonical reference with diagrams, consistency trade-offs, and implementation guidance.
- [Martin Fowler: CQRS](https://martinfowler.com/bliki/CQRS.html) — Original articulation of the pattern and when it is appropriate vs. overkill.
- [Greg Young: CQRS Documents](https://cqrs.files.wordpress.com/2010/11/cqrs_documents.pdf) — The source paper from the pattern's inventor; covers event sourcing integration in depth.
- [Axon Framework Documentation](https://docs.axoniq.io/axon-framework-reference/) — Production Java implementation showing command bus, query bus, and event sourcing wired together.
- [EventStoreDB: Projections](https://developers.eventstore.com/server/v22.10/projections/) — Practical guide to building read-side projections from an append-only event log.
