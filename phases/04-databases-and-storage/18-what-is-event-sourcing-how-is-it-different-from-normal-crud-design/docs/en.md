# What is Event Sourcing? How is it different from normal CRUD design?

> Store what happened, not what is — and turn every state change into a reconstructible event.

**Type:** Learn
**Prerequisites:** Basic database design, distributed systems familiarity
**Time:** ~25 minutes

---

## The Problem

CRUD design — create, read, update, delete — is the default mental model for persistent state. A row in a table represents the current state of an entity; an UPDATE changes it; a DELETE removes it. This works for most applications. It breaks down in three cases:

1. **Audit.** "What did this entity look like last Tuesday?" "Who changed it and when?" "Show me the state before this bug."
2. **Debugging.** "The customer says their order was wrong yesterday. What happened?"
3. **Integration.** "The same business event triggers a database write, an email, a webhook, and an analytics event."

CRUD stores only the latest state. The history is gone the moment an UPDATE commits. Event sourcing takes the opposite approach: store every state change as an event, derive the current state by replaying events.

This lesson explains event sourcing, contrasts it with CRUD design, identifies when each fits, and shows what changes in your architecture when you adopt it.

---

## The Concept

### CRUD vs. event sourcing, at a glance

```
   CRUD design:           store state           query state
                          ────────────          ────────────
                          orders table          SELECT * FROM orders

   Event sourcing:        store events          derive state from events
                          ────────────          ──────────────────────
                          OrderCreated event    fold over events to
                          OrderModified event   reconstruct current state
                          OrderShipped event
```

In CRUD, the database is the source of truth. In event sourcing, the **event log** is the source of truth; the current state (called the "view" or "projection") is a derived cache.

---

### An order, in two designs

**CRUD design:**

```
   ┌──────────────────────────────┐
   │ orders table                 │
   ├──────────────────────────────┤
   │ order_id: 42                 │
   │ customer: Bob                │
   │ quantity: 6                  │  ← current state
   │ status: SHIPPED              │
   │ created_at: 2024-12-01       │
   └──────────────────────────────┘
```

Each mutation overwrites the previous state. The history is lost.

**Event sourcing design:**

```
   ┌──────────────────────────────────────────────┐
   │ event_store (append-only)                    │
   ├──────────────────────────────────────────────┤
   │ event_id: 321, type: OrderCreated, ...       │
   │ event_id: 322, type: OrderModified, qty: 6   │
   │ event_id: 323, type: OrderShipped, ...       │
   │ event_id: 324, type: OrderDelivered, ...     │
   └──────────────────────────────────────────────┘

   Derived state (rebuilt from events):
   ┌──────────────────────────────┐
   │ order_view                   │
   ├──────────────────────────────┤
   │ order_id: 42                 │
   │ customer: Bob                │
   │ quantity: 6                  │  ← computed by folding
   │ status: DELIVERED            │     over events
   │ created_at: 2024-12-01       │
   └──────────────────────────────┘
```

The event log is the source of truth. The view is a derivation that can be rebuilt from the log at any time.

---

### The event store

The event store is an **append-only log**. Every event has:

```
   {
     "event_id": 321,           // unique, monotonic
     "event_type": "OrderCreated",
     "aggregate_id": "order-42", // the entity this event belongs to
     "timestamp": "2024-12-01T10:00:00Z",
     "version": 1,              // per-aggregate sequence number
     "data": {
       "customer": "Bob",
       "items": [...],
       "total": 1500
     }
   }
```

**Properties of the event store:**

- **Append-only** — events are never updated or deleted (only superseded by later events or archived by retention policy)
- **Ordered** — events for a given aggregate are numbered sequentially; this guarantees ordering
- **Immutable** — once written, an event is permanent
- **Queryable by aggregate** — you can fetch all events for a given entity quickly

**Implementation options:**

- **EventStoreDB** — purpose-built event store
- **Kafka** — append-only log with strong ordering guarantees per partition
- **Postgres with `LISTEN/NOTIFY` + append-only table** — pragmatic, less specialized
- **DynamoDB streams** — append-only on top of DynamoDB

---

### Events are facts, commands are intentions

A subtle but important distinction:

- **Command** — "Change quantity to 6" (an intention, may fail)
- **Event** — "Quantity changed to 6" (a fact, has happened)

In event sourcing, only successful commands produce events. Failed commands do not. The event log represents what actually happened, not what was attempted.

```
   Command: ChangeQuantity(order_id=42, qty=6)
      │
      ▼
   Validation: order exists? quantity valid? customer authorized?
      │
      ├── NO  → reject (no event written)
      │
      └── YES → emit event:
                OrderQuantityChanged {
                  order_id: 42,
                  old_qty: 5,
                  new_qty: 6,
                  timestamp: ...
                }
```

This separation matters because it keeps the event log clean: every event in the log is a fact that the system has confirmed.

---

### Projections: how state is derived

A **projection** is the derived current state, computed by folding over events.

```python
def project_order(events):
    """Fold over events to compute the current order state."""
    state = None
    for event in events:
        if event.type == "OrderCreated":
            state = {
                "order_id": event.aggregate_id,
                "customer": event.data["customer"],
                "quantity": event.data["quantity"],
                "status": "CREATED",
            }
        elif event.type == "OrderModified":
            state["quantity"] = event.data["new_quantity"]
        elif event.type == "OrderShipped":
            state["status"] = "SHIPPED"
        elif event.type == "OrderDelivered":
            state["status"] = "DELIVERED"
        elif event.type == "OrderCancelled":
            state["status"] = "CANCELLED"
    return state
```

The projection is **idempotent and re-derivable**. If the view is lost or corrupted, rebuild it by replaying all events. If new fields are needed, replay with an updated projection function.

This is the key advantage: the system can always reconstruct state from the event log, no matter what happens to the views.

---

### Why event sourcing

**1. Complete audit trail**

Every state change is recorded with who, when, and what. Compliance, debugging, and customer support all benefit.

```
   "Why was my order shipped to the wrong address?"
   → Replay events: see the address was changed 3 times before shipping
```

**2. Time travel**

You can query the state at any past moment.

```sql
-- "What was the order state at 2024-12-15?"
SELECT * FROM order_view
WHERE valid_from <= '2024-12-15'
  AND valid_to > '2024-12-15';
```

(Requires event sourcing + temporal projection.)

**3. Multiple views from one event stream**

The same events can produce different projections for different needs:

```
   events ─┬─► OrderView (for ops dashboard)
           ├─► OrderSummary (for analytics)
           ├─► ShippingQueue (for warehouse)
           └─► CustomerEmailHistory (for support)
```

**4. Event-driven integration**

Events become the integration contract. Other services subscribe to the event stream and react.

```
   order events ─┬─► email service (sends shipping confirmation)
                 ├─► analytics service (updates dashboards)
                 ├─► inventory service (restocks if cancelled)
                 └─► ML service (trains fraud model)
```

**5. Naturally replayable**

Need to migrate the projection schema? Replay all events through the new function. Need to add a new view? Create a new projection that consumes from the same stream.

---

### Why NOT event sourcing

Event sourcing is not a default. It adds real complexity.

| Cost | Why it hurts |
|---|---|
| **Eventual consistency** | Views lag behind events; reads may be slightly stale |
| **Schema evolution is hard** | Old events have old schemas; new code must handle both |
| **Querying is awkward** | Cannot easily "find all orders where status = SHIPPED" — must project first |
| **Tooling is immature** | Far less mature than CRUD frameworks; debugging is harder |
| **Mental model overhead** | Everyone on the team needs to think in events, not state |
| **Storage grows forever** | Append-only log; must archive or compact eventually |

---

### When event sourcing fits

| Use case | Why event sourcing helps |
|---|---|
| **Financial transactions** | Audit trail is non-negotiable; regulators require it |
| **Order management** | Order lifecycle is naturally event-based |
| **User activity logs** | Every action is an event; aggregation is the goal |
| **Multi-step workflows** | State machine transitions are events |
| **CQRS architectures** | Event sourcing pairs naturally with separate read models |
| **Integration hub** | One event stream feeds many downstream consumers |

### When CRUD is the right choice

| Use case | Why CRUD is simpler |
|---|---|
| **Simple CRUD apps** | Blogs, content management, basic CRUD apps — events are overkill |
| **High-volume transactional** | Where audit is not required and performance is |
| **Reporting-heavy** | Where SQL queries are the natural fit |
| **Standard SaaS apps** | Most SaaS fits CRUD; event sourcing is the exception |

---

## Build It / In Depth

### A minimal event store in 100 lines

```python
import json
import time
import threading
from collections import defaultdict

class EventStore:
    def __init__(self):
        self.events = []                # the append-only log
        self.lock = threading.Lock()
        self.versions = defaultdict(int)  # per-aggregate version counter

    def append(self, aggregate_id, event_type, data):
        with self.lock:
            version = self.versions[aggregate_id] + 1
            self.versions[aggregate_id] = version
            event = {
                "event_id": len(self.events) + 1,
                "aggregate_id": aggregate_id,
                "event_type": event_type,
                "version": version,
                "timestamp": time.time(),
                "data": data,
            }
            self.events.append(event)
            return event

    def get_events(self, aggregate_id):
        return [e for e in self.events if e["aggregate_id"] == aggregate_id]

    def get_all_events(self):
        return list(self.events)


class Order:
    def __init__(self):
        self.created = False
        self.quantity = 0
        self.status = None

    @classmethod
    def create(cls, customer, items, total):
        return ("OrderCreated", {"customer": customer, "items": items, "total": total})

    @classmethod
    def change_quantity(cls, new_quantity):
        return ("OrderQuantityChanged", {"new_quantity": new_quantity})

    @classmethod
    def ship(cls, tracking_id):
        return ("OrderShipped", {"tracking_id": tracking_id})


class OrderService:
    def __init__(self, store):
        self.store = store
        self.projection = {}  # aggregate_id -> derived state

    def handle_command(self, aggregate_id, command):
        # Load current state by replaying events
        state = Order()
        for event in self.store.get_events(aggregate_id):
            self._apply(state, event)

        # Generate new event(s) from the command
        new_events = []
        if command[0] == "create":
            new_events.append(self.store.append(aggregate_id, "OrderCreated", command[1]))
        elif command[0] == "change_quantity":
            if not state.created:
                raise ValueError("Order does not exist")
            new_events.append(self.store.append(aggregate_id, "OrderQuantityChanged", command[1]))
        elif command[0] == "ship":
            if not state.created:
                raise ValueError("Order does not exist")
            new_events.append(self.store.append(aggregate_id, "OrderShipped", command[1]))

        # Update projection
        for event in new_events:
            self._apply(state, event)
        self.projection[aggregate_id] = state

        return new_events

    def _apply(self, state, event):
        if event["event_type"] == "OrderCreated":
            state.created = True
            state.quantity = event["data"]["items"][0].get("quantity", 0)
        elif event["event_type"] == "OrderQuantityChanged":
            state.quantity = event["data"]["new_quantity"]
        elif event["event_type"] == "OrderShipped":
            state.status = "SHIPPED"

    def get_order(self, aggregate_id):
        return self.projection.get(aggregate_id)


# --- Usage ---------------------------------------------------------------

store = EventStore()
service = OrderService(store)

# Create an order
service.handle_command("order-42",
    ("create", {"customer": "Bob", "items": [{"sku": "X", "quantity": 5}],
                "total": 1500}))

# Modify
service.handle_command("order-42",
    ("change_quantity", {"new_quantity": 6}))

# Ship
service.handle_command("order-42",
    ("ship", {"tracking_id": "TRK-001"}))

# Inspect the log
for event in store.get_events("order-42"):
    print(event)
```

This is a complete event-sourced order service in ~100 lines. The event log is the truth; the projection is a cache that can be rebuilt.

---

### Event sourcing + CQRS

**CQRS (Command Query Responsibility Segregation)** often pairs with event sourcing.

```
   ┌────────────────────────────────────────────────────┐
   │                                                    │
   │   Command side                  Query side         │
   │                                                    │
   │   ┌─────────┐     ┌────────────┐    ┌──────────┐   │
   │   │ Command │ ──► │ Event Store│ ──► │ Projection│   │
   │   │ handler │     │ (append)   │    │ (read DB)│   │
   │   └─────────┘     └────────────┘    └──────────┘   │
   │        │                              ▲            │
   │        │            events flow       │            │
   │        └──────────────────────────────┘            │
   │                                                    │
   └────────────────────────────────────────────────────┘
```

The **command side** validates and writes events. The **query side** projects events into read-optimized views (often a separate read database: Postgres for queries, the event store for commands). This separation gives you:

- Independent scaling (writes are small; reads can be denormalized for fast queries)
- Multiple read models from one event stream
- No impedance mismatch between command and query needs

---

### Snapshotting for long-lived aggregates

An aggregate with thousands of events becomes slow to replay. **Snapshotting** solves this by periodically saving the projection state.

```
   events 1...1000  →  snapshot at version 1000
   events 1001...1500
   to load: snapshot(1000) + events(1001...1500) → state
```

Snapshots are not the source of truth; the event log is. A snapshot is just a cache of the projection. If the snapshot is lost or corrupted, rebuild it by replaying the events.

---

## Use It

### Schema evolution

The hardest problem in event sourcing: how do you change event schemas without breaking old events?

**Strategies:**

1. **Upcasting** — write a function that transforms old event schemas to new ones; run on replay.
2. **Weak schema** — store events as JSON with optional fields; new code reads old fields; new events add new fields.
3. **Versioned events** — include a schema version in the event; readers handle each version.
4. **New event type** — instead of changing existing events, create new ones; old events are still valid.

```
   Old event:  OrderCreated { customer, items }
   New event:  OrderCreated { customer, items, currency }

   Approach:  Read both, default currency to USD if missing.
```

---

### Tools and frameworks

| Tool | Role |
|---|---|
| **EventStoreDB** | Purpose-built event store database |
| **Kafka** | Append-only log; backbone for many event-sourced systems |
| **Axon Framework** (Java) | Event sourcing + CQRS framework |
| **Marten** (.NET) | Event sourcing on top of Postgres |
| **Eventuous** (.NET) | Event sourcing for .NET |
| **Akka Persistence** (Scala/Java) | Event sourcing for actor-based systems |
| **Sequelize / TypeORM event plugins** | Lightweight event sourcing for Node.js |

---

### When to introduce event sourcing

```
   Does the application need any of these?
     - Complete audit trail of all changes
     - Time-travel / "what was the state at X?"
     - Multiple downstream consumers of the same events
     - Complex workflows that benefit from event-driven modeling

   If yes, AND the team has bandwidth to learn the model:
     → Event sourcing is worth the complexity.

   If no, OR the team is small and CRUD-native:
     → Stick with CRUD. Add event sourcing later if needed.
```

---

## Common Pitfalls

- **Storing derived state in events.** Events should describe what happened, not the resulting state. If your events look like `{ "field": "value" }`, you are using events as a database, not as facts.

- **Mutating or deleting events.** The event log is append-only. If you need to "correct" an event, emit a compensating event. Never modify history.

- **Treating the projection as the source of truth.** The projection is a cache. If it disagrees with the events, the events are right.

- **Forgetting eventual consistency.** Reads from a projection may be milliseconds behind writes. Code that requires read-your-writes must wait for the projection or read from the event log.

- **No schema evolution plan.** Events will outlive your code. Plan for backward-compatible reads from day one.

- **Querying the event log directly.** It is tempting to "just query the events" for a report. The event log is optimized for sequential reads; queries need projections.

- **Skipping snapshots for long aggregates.** An aggregate with 10,000 events is slow to replay. Snapshot periodically.

---

## Exercises

1. **Easy** — In one sentence each, describe the CRUD approach and the event sourcing approach to persisting order state. List one advantage of each.

2. **Medium** — Design an event model for a banking transfer system (AccountCredited, AccountDebited, TransferInitiated, etc.). Specify the event schema for each, the validation rules, and how you would build a balance projection.

3. **Hard** — Migrate a CRUD-based order management system to event sourcing. Plan the phased rollout: what runs on event sourcing first, what stays on CRUD, how you keep them in sync during migration, and how you verify correctness at each step.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Event sourcing | A way to log things | A persistence model where every state change is recorded as an immutable event; the event log is the source of truth, current state is derived |
| Event | A log entry | An immutable fact that something happened, with a type, timestamp, aggregate ID, and data; append-only, never modified |
| Event store | A database | An append-only log optimized for event sourcing; supports per-aggregate ordering, fast event retrieval, and (usually) subscriptions |
| Projection | The current state | A derived view of the current state, computed by folding over events; rebuildable, replacable, eventually consistent |
| Command | An event | An intention to change state; may fail; only successful commands produce events |
| CQRS | A pattern | Command Query Responsibility Segregation — separate models for writes (commands) and reads (queries); often pairs with event sourcing |
| Snapshot | A backup | A periodic capture of the projection state, used to speed up replay for aggregates with many events |
| Upcasting | Schema migration | A transformation function that converts old event schemas to new ones; run during replay when schemas evolve |

---

## Further Reading

- **"Event Sourcing"** — Martin Fowler's canonical introduction: https://martinfowler.com/eaaDev/EventSourcing.html
- **"Versioning in an Event Sourced System"** — Greg Young's foundational post: https://leanpub.com/esversioning/read
- **EventStoreDB Documentation** — the leading purpose-built event store: https://developers.eventstore.com/
- **"CQRS"** — Martin Fowler's article on Command Query Responsibility Segregation: https://martinfowler.com/bliki/CQRS.html
- **Axon Framework** — the most-used event sourcing + CQRS framework for Java: https://axoniq.io/