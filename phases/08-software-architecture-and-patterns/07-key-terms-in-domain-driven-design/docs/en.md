# Key Terms in Domain-Driven Design

> Model the business, not the database — the domain is the heart of the software.

**Type:** Learn
**Prerequisites:** Microservices Architecture, Bounded Contexts, Event-Driven Architecture
**Time:** ~25 minutes

---

## The Problem

Consider a mid-size e-commerce platform with hundreds of engineers working across checkout, inventory, shipping, and customer accounts. Each team adds tables and endpoints independently. Months later, `Order` has grown into a 60-column table shared by seven services. Business rules like "an order cannot ship if any item is back-ordered" are scattered across three services, two stored procedures, and a cron job. There is no single authoritative place where the word "Order" means exactly one thing.

This is the **anemic domain model** trap: code organized around data shapes rather than business concepts. Classes become property bags. Business logic migrates into service layers that grow without bound. Teams cannot talk to domain experts because the code no longer maps to how the business actually works.

Eric Evans' book *Domain-Driven Design* (2003) introduced a vocabulary and a set of building blocks that keep complex business logic coherent. The terms are not arbitrary jargon — each one answers a specific design question that emerges in any sufficiently complex system. Understanding them precisely is the prerequisite for designing maintainable microservices, event-driven pipelines, and CQRS systems.

---

## The Concept

DDD building blocks fall into three categories: **what things are** (structural), **how they live** (lifecycle), and **what they do** (behavioral).

### Structural: Entity, Value Object, Aggregate

#### Entity

An **Entity** is a domain object whose identity persists over time, independent of its attribute values. Two customers can have the same name and address and still be different customers because they have different IDs.

Key rules:
- Identity is stable even as attributes change (`Order` status changes from `PENDING` to `SHIPPED` — same order).
- Equality is based on identity, not attribute values.
- Entities have a lifecycle: they are created, mutated, and eventually archived or deleted.

```
Customer
────────────────────────
+ id: CustomerId        ← identity
+ name: string          ← can change
+ email: Email          ← can change
────────────────────────
+ changeName(name)
+ changeEmail(email)
```

#### Value Object

A **Value Object** describes a property or measurement. It has no identity — two `Money` objects representing $5.00 USD are completely interchangeable.

Key rules:
- Equality is based on all attributes (`Money(5, "USD") == Money(5, "USD")`).
- **Immutable**: instead of mutating, you replace. `price.add(tax)` returns a new `Money`.
- Rich with domain behavior: `Money.convertTo(Currency)`, `Address.isInRegion(Region)`.

```python
@dataclass(frozen=True)       # frozen = immutable
class Money:
    amount: Decimal
    currency: str

    def add(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError("Currency mismatch")
        return Money(self.amount + other.amount, self.currency)
```

Using `frozen=True` enforces immutability at the language level and lets you use value objects as dict keys or set members.

#### Aggregate

An **Aggregate** is a cluster of Entities and Value Objects treated as a single unit for data changes. One Entity inside the cluster is designated the **Aggregate Root** — the only entry point through which the outside world interacts.

```
                ┌─────────────────────────────┐
                │        Order (Root)          │
                │  id: OrderId                 │
                │  status: OrderStatus         │
                │  ┌──────────────────────┐   │
                │  │   OrderLine (Entity) │   │
                │  │   quantity: int      │   │
                │  │   price: Money (VO)  │   │
                │  └──────────────────────┘   │
                │  ┌─────────────────────┐    │
                │  │  ShippingAddress(VO)│    │
                │  └─────────────────────┘    │
                └─────────────────────────────┘
                          ▲
              Outside world only holds
              a reference to OrderId
```

Critical rules:
1. **Only the root is referenced externally.** Other services hold an `OrderId`, not a direct reference to `OrderLine`.
2. **All writes go through the root.** `order.addLine(...)`, not `orderLine.setQuantity(...)`.
3. **Aggregate is the unit of consistency.** Every invariant ("total cannot exceed customer credit limit") is enforced within the aggregate boundary.
4. **Aggregate is the unit of persistence.** You load and save the entire aggregate together — not individual inner entities.

Aggregate boundaries define your transaction scope. A single database transaction should never span two aggregates. If you need to coordinate two aggregates, use **Domain Events**.

---

### Lifecycle: Repository, Factory

#### Repository

A **Repository** provides a collection-like interface for loading and saving Aggregates, hiding all persistence details. It is not a generic CRUD layer — each repository is scoped to one Aggregate type.

```python
class OrderRepository(ABC):
    @abstractmethod
    def find_by_id(self, order_id: OrderId) -> Optional[Order]: ...

    @abstractmethod
    def save(self, order: Order) -> None: ...

    @abstractmethod
    def find_by_customer(self, customer_id: CustomerId) -> list[Order]: ...
```

The domain layer defines the interface; the infrastructure layer (SQLAlchemy, DynamoDB, Postgres) provides the implementation. Domain code never imports database libraries. This is the **Dependency Inversion Principle** applied at the architectural layer.

#### Factory

A **Factory** encapsulates complex object construction logic. When creating an Aggregate requires coordinating multiple pieces of information, applying invariants during creation, or building up child entities and value objects, a factory keeps the root's constructor clean.

```python
class OrderFactory:
    def create_from_cart(
        self,
        cart: Cart,
        customer: Customer,
        shipping: ShippingAddress,
    ) -> Order:
        if not cart.items:
            raise EmptyCartError()
        lines = [
            OrderLine(item.product_id, item.quantity, item.price)
            for item in cart.items
        ]
        return Order.new(
            id=OrderId.generate(),
            customer_id=customer.id,
            lines=lines,
            shipping=shipping,
        )
```

Factories are especially useful when the same aggregate can be created from multiple sources (API request, message queue event, database reconstruction).

---

### Behavioral: Domain Service, Domain Event

#### Domain Service

A **Domain Service** performs domain logic that doesn't naturally belong to any single entity or value object. It is stateless and operates on domain objects.

When to reach for a Domain Service:
- The operation involves multiple aggregates.
- The concept exists in the domain language ("Transfer funds between accounts") but doesn't fit inside any single aggregate.
- The logic requires an external integration (e.g., a tax calculation service) but still expresses a domain rule.

```python
class FundsTransferService:
    def transfer(
        self,
        source: Account,
        destination: Account,
        amount: Money,
    ) -> None:
        if source.balance < amount:
            raise InsufficientFundsError()
        source.debit(amount)
        destination.credit(amount)
```

Do not confuse Domain Services with Application Services. **Application Services** orchestrate use cases (load from repo, call domain service, save, publish event). **Domain Services** contain business rules.

#### Domain Event

A **Domain Event** is an immutable record of something that happened in the domain. It is named in the past tense and belongs to the Aggregate that produced it.

```python
@dataclass(frozen=True)
class OrderPlaced:
    order_id: OrderId
    customer_id: CustomerId
    total: Money
    occurred_at: datetime
```

Events serve two key purposes:
1. **Cross-aggregate coordination**: instead of a Domain Service reaching directly into two aggregates, each aggregate publishes events that drive the other's reaction.
2. **Event sourcing**: the full history of state changes is stored as a sequence of domain events, not a snapshot.

The Aggregate collects events internally during a business operation, and the Application Service dispatches them after saving:

```
Order.place() → appends OrderPlaced to internal list
Repository.save(order)
EventBus.publish(order.pull_events())
```

---

## Build It / In Depth

Walk through a concrete **Order placement** scenario for an e-commerce system.

**Step 1 — Create the Value Objects**

```python
@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str

@dataclass(frozen=True)
class ShippingAddress:
    street: str
    city: str
    country: str
    postal_code: str
```

**Step 2 — Define the inner Entity**

```python
class OrderLine:
    def __init__(self, product_id: str, qty: int, unit_price: Money):
        if qty <= 0:
            raise ValueError("Quantity must be positive")
        self._product_id = product_id
        self._qty = qty
        self._unit_price = unit_price

    @property
    def subtotal(self) -> Money:
        return Money(self._unit_price.amount * self._qty, self._unit_price.currency)
```

**Step 3 — Build the Aggregate Root with invariants**

```python
class Order:
    MAX_LINES = 50

    def __init__(self, order_id: str, customer_id: str):
        self._id = order_id
        self._customer_id = customer_id
        self._lines: list[OrderLine] = []
        self._status = "DRAFT"
        self._events: list = []

    def add_line(self, product_id: str, qty: int, unit_price: Money) -> None:
        if self._status != "DRAFT":
            raise ValueError("Cannot modify a placed order")
        if len(self._lines) >= self.MAX_LINES:
            raise ValueError("Order exceeds maximum line limit")
        self._lines.append(OrderLine(product_id, qty, unit_price))

    def place(self, shipping: ShippingAddress) -> None:
        if not self._lines:
            raise ValueError("Cannot place empty order")
        self._shipping = shipping
        self._status = "PLACED"
        self._events.append(OrderPlaced(
            order_id=self._id,
            customer_id=self._customer_id,
            total=self.total,
            occurred_at=datetime.utcnow(),
        ))

    @property
    def total(self) -> Money:
        total = Decimal("0")
        for line in self._lines:
            total += line.subtotal.amount
        return Money(total, "USD")

    def pull_events(self):
        events, self._events = self._events, []
        return events
```

**Step 4 — Application Service wiring it all together**

```python
class PlaceOrderUseCase:
    def __init__(self, repo: OrderRepository, event_bus: EventBus):
        self._repo = repo
        self._event_bus = event_bus

    def execute(self, cmd: PlaceOrderCommand) -> None:
        order = self._repo.find_by_id(cmd.order_id)
        if order is None:
            raise OrderNotFoundError(cmd.order_id)
        order.place(cmd.shipping_address)
        self._repo.save(order)                        # persist first
        self._event_bus.publish(order.pull_events())   # then publish
```

Notice the boundary: the Application Service knows about infrastructure (`repo`, `event_bus`) while the `Order` aggregate knows nothing outside the domain model.

---

## Use It

| Concept | Where it shows up in the real world |
|---|---|
| **Entity** | JPA `@Entity` with `@Id`; Mongoose documents with `_id`; DynamoDB items with a partition key |
| **Value Object** | Kotlin data classes; Java record types; Python frozen dataclasses; Protobuf messages for money/address |
| **Aggregate** | Axon Framework enforces single-aggregate transactions; NestJS CQRS module aggregate root base class |
| **Repository** | Spring Data `JpaRepository`; SQLAlchemy `Session`; AWS DynamoDB single-table design patterns |
| **Factory** | Builder pattern in Lombok; factory methods in Go constructors; Abstract Factory for test doubles |
| **Domain Service** | Calculation engines (tax, shipping cost); fraud scoring services in payment systems |
| **Domain Event** | Kafka topics named `order.placed`; AWS EventBridge event buses; Axon `@EventHandler`; Debezium CDC |

**When to apply full DDD rigor:** Systems with complex, frequently-changing business rules and multiple collaborating domain experts. Avoid the overhead in CRUD-heavy services (a `UserPreferences` service doesn't need aggregates).

---

## Common Pitfalls

- **Making everything an Entity.** If an object has no meaningful lifecycle or identity — like a price, a range, or a coordinate — make it a Value Object. Entities carry overhead: identity management, lifecycle tracking, and harder equality checks.

- **Anemic aggregates.** Aggregates that are just data bags with public setters and all logic in services defeat the purpose of DDD. The aggregate should enforce its own invariants. If `order.status = "SHIPPED"` can be called from anywhere, you have an anemic model.

- **Aggregates that span transaction boundaries.** Putting `Customer` and all their `Orders` in one aggregate creates a single massive lock. Keep aggregates small. Use Domain Events to coordinate across boundaries asynchronously.

- **Repositories returning inner entities.** `orderRepository.findLineById(lineId)` breaks encapsulation. External code should only query and receive Aggregate Roots. If you frequently need to query inner entities, it often signals a missing aggregate boundary.

- **Confusing Domain Events with integration events.** A Domain Event is an in-process signal (business fact); an Integration Event is its serialized, versioned form published to a message broker for other services. They look similar but serve different purposes. Convert Domain Events to Integration Events in the Application Service layer, not inside the aggregate.

---

## Exercises

1. **Easy** — In an online library system, decide whether `Book`, `ISBN`, `BorrowRecord`, and `Author` are Entities or Value Objects. Justify each decision in one sentence.

2. **Medium** — Design the `Payment` aggregate for a checkout flow. Identify the root, inner entities, value objects, invariants it must enforce, and the domain events it produces. Draw an ASCII diagram of the structure.

3. **Hard** — A `Shipment` service must listen for `OrderPlaced` events and create a `Shipment` aggregate. A `Notification` service must also listen and send a confirmation email. Design the full event flow: what aggregate publishes what events, how each downstream service consumes them, and how you ensure the notification is sent even if the notification service is temporarily down. Consider at-least-once delivery and idempotency.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Entity** | Any object that maps to a database table | A domain object whose identity persists across time, regardless of attribute changes |
| **Value Object** | A simple DTO or struct | An immutable domain object defined entirely by its attributes, with no identity |
| **Aggregate** | A folder of related classes | A consistency boundary with a single root through which all external interactions must pass |
| **Aggregate Root** | The "main" entity in a group | The guardian of invariants — the only entity externally referenceable within the aggregate |
| **Repository** | A generic CRUD data access layer | A collection-like abstraction scoped to one aggregate type, hiding all persistence details |
| **Domain Service** | Any service class in the domain layer | Stateless logic that expresses a domain concept requiring multiple aggregates or external inputs |
| **Domain Event** | A message sent over a queue | An immutable record of a meaningful state change, raised by an aggregate and consumed in-process or after persistence |

---

## Further Reading

- **Eric Evans — *Domain-Driven Design: Tackling Complexity in the Heart of Software*** (Addison-Wesley, 2003) — the canonical reference; chapters 5–6 cover all terms in this lesson.
- **Vaughn Vernon — *Implementing Domain-Driven Design*** (Addison-Wesley, 2013) — practical guidance with Java code examples: https://vaughnvernon.co/?page_id=168
- **Martin Fowler — *Patterns of Enterprise Application Architecture***, specifically the Repository and Value Object patterns: https://martinfowler.com/eaaCatalog/
- **DDD Community resources and pattern index**: https://www.domainlanguage.com/ddd/reference/
- **Microsoft .NET Architecture Guide — DDD chapter**: https://docs.microsoft.com/en-us/dotnet/architecture/microservices/microservice-ddd-cqrs-patterns/
