# Design Patterns Cheat Sheet

> Patterns are not code you copy — they are solutions you recognize.

**Type:** Learn
**Prerequisites:** Object-Oriented Design Principles, SOLID Principles, Software Architecture Fundamentals
**Time:** ~40 minutes

---

## The Problem

Every engineering team eventually hits the same wall: a codebase that started clean starts collecting brittle workarounds. Adding a new payment provider means touching seven files. Changing a notification channel cascades into unexpected side effects. The object that "holds global config" has become a hidden dependency magnet that makes unit tests impossible.

These are not bad-programmer problems — they are structural problems. The code lacks stable vocabulary for recurring design decisions: how to create objects without hard-coupling callers to concrete types; how to add behavior without modifying working classes; how to coordinate many objects without creating a spaghetti web of references.

Design patterns are named, proven solutions to these recurring structural problems. Knowing them gives you three things: a shared vocabulary with teammates ("let's use a Strategy here"), a blueprint that has already considered the trade-offs, and — critically — the judgment to know when *not* to use one.

---

## The Concept

Patterns are grouped into three families based on the kind of problem they solve.

| Family | Concern | Core question |
|---|---|---|
| **Creational** | Object construction | How and when do objects get created? |
| **Structural** | Class/object composition | How do we assemble parts into larger wholes? |
| **Behavioral** | Object communication | How do objects collaborate and distribute responsibility? |

### Creational Patterns

```
Caller             Factory             ConcreteProduct
  │                   │                      │
  │── create("pdf") ──▶                      │
  │                   │── new PdfExporter() ──▶
  │◀──────────────────│◀──────────────────────│
  │  (IExporter ref)  │
```

**Factory / Factory Method** — hides the `new` keyword behind an interface. Callers ask for an abstraction; the factory decides which concrete class to instantiate. Useful when the concrete type varies by config, environment, or runtime data.

**Abstract Factory** — a factory *of* factories. Groups related product families so swapping one family (e.g., dark-theme UI components vs. light-theme) requires changing only the factory, not every call site.

**Builder** — separates the *construction steps* of a complex object from its final form. The canonical sign you need it: a constructor that has grown beyond four parameters, especially with optional ones. A fluent builder makes legal states self-documenting.

```python
# Builder in action
query = (
    QueryBuilder()
    .select("id", "name")
    .from_table("users")
    .where("status = 'active'")
    .limit(100)
    .build()
)
```

**Prototype** — clone an existing object instead of constructing from scratch. Valuable when construction is expensive (e.g., object initialized from a DB call) and many similar instances are needed. Requires a disciplined `clone()` that performs a deep copy.

**Singleton** — ensures a class has exactly one instance and provides a global access point. Legitimately useful for connection pools, config registries, and loggers. Frequently abused — see Common Pitfalls.

### Structural Patterns

**Adapter** — wraps an incompatible interface so it matches the one callers expect. Classic use: integrating a third-party library whose interface differs from your domain abstraction, without modifying the library.

**Decorator** — adds behavior by wrapping an object, conforming to the same interface. Stackable without subclassing. HTTP middleware stacks (auth → rate-limit → logging → handler) are decorators.

```
Request ──▶ AuthMiddleware ──▶ RateLimitMiddleware ──▶ LoggingMiddleware ──▶ Handler
           (decorator)         (decorator)              (decorator)
```

**Facade** — presents a simplified interface over a complex subsystem. A `PaymentService.charge()` call may internally coordinate fraud detection, ledger updates, notification dispatch, and audit logging — the facade hides all of that.

**Proxy** — a stand-in that controls access to the real object. Three flavors matter in system design: *virtual proxy* (lazy load), *protection proxy* (access control), and *remote proxy* (network call disguised as local call — think gRPC stubs).

**Composite** — treats individual objects and compositions of objects uniformly. A file-system tree where both `File` and `Directory` implement `size()` is the canonical example. Used heavily in UI frameworks and expression trees.

**Flyweight** — shares a pool of immutable objects to reduce memory. A text editor that stores one `Character` object per distinct glyph rather than one per character in the document. Useful when millions of fine-grained objects share state.

### Behavioral Patterns

**Strategy** — encapsulates interchangeable algorithms behind a common interface. Swap compression algorithms, sorting strategies, or pricing rules without changing the calling code.

```python
class Compressor:
    def __init__(self, strategy: CompressionStrategy):
        self._strategy = strategy

    def compress(self, data: bytes) -> bytes:
        return self._strategy.compress(data)
```

**Observer** — defines a one-to-many dependency: when one object changes state, its dependents are notified automatically. Event buses, reactive streams, and DOM events all implement this. The subject holds no knowledge of concrete observer types.

**Chain of Responsibility** — passes a request along a chain of handlers; each decides to handle it or forward it. Expense approval workflows, HTTP filter chains, and log level routing are everyday examples.

```
Request ──▶ Handler1 ──▶ Handler2 ──▶ Handler3 ──▶ (unhandled)
            (skip)       (handle)
```

**Command** — encapsulates a request as an object. Enables queuing, logging, undo/redo, and deferred execution. A "job" in a task queue is a Command object.

**Template Method** — defines the skeleton of an algorithm in a base class, deferring specific steps to subclasses. The hook points are explicit; the overall sequence is fixed. Common in frameworks (e.g., Django's class-based views).

**State** — lets an object alter behavior when its internal state changes, appearing to change its class. An order that behaves differently when `pending`, `paid`, or `shipped` is a State machine.

**Mediator** — centralizes complex communications between objects. Instead of objects referencing each other directly, they talk through a mediator. Air traffic control is the textbook analogy; message brokers (Kafka topics) are real-world mediators.

**Iterator** — provides sequential access to a collection's elements without exposing the underlying structure. Python's `for` loop protocol (`__iter__`, `__next__`) and Java's `Iterable` are language-level iterator patterns.

**Memento** — captures and externalizes an object's internal state so it can be restored later, without violating encapsulation. Undo history, save-game states, and snapshot-based rollback use this.

---

## Build It / In Depth

### Worked Example: Payment Processing Pipeline

Suppose you're building a payment service that must support multiple gateways (Stripe, PayPal, Braintree), apply fraud checks, log every transaction, and allow retrying failed payments.

**Step 1 — Factory selects the gateway at runtime**

```python
class GatewayFactory:
    _registry: dict[str, type[PaymentGateway]] = {}

    @classmethod
    def register(cls, name: str, klass: type):
        cls._registry[name] = klass

    @classmethod
    def create(cls, name: str, config: dict) -> PaymentGateway:
        if name not in cls._registry:
            raise ValueError(f"Unknown gateway: {name}")
        return cls._registry[name](config)

GatewayFactory.register("stripe", StripeGateway)
GatewayFactory.register("paypal", PayPalGateway)

gateway = GatewayFactory.create(settings.PAYMENT_GATEWAY, settings.GATEWAY_CONFIG)
```

**Step 2 — Decorator stack adds cross-cutting concerns**

```python
gateway = LoggingDecorator(
    RetryDecorator(
        FraudCheckDecorator(
            gateway,
            fraud_model=ml_model,
        ),
        max_retries=3,
    ),
    logger=audit_logger,
)
```

Every decorator conforms to `PaymentGateway`; callers see only the interface. Adding a new concern (e.g., currency conversion) means wrapping with one more decorator.

**Step 3 — Command object enables queuing and undo**

```python
@dataclass
class ChargeCommand:
    gateway: PaymentGateway
    amount_cents: int
    currency: str
    customer_id: str

    def execute(self) -> ChargeResult:
        return self.gateway.charge(self.amount_cents, self.currency, self.customer_id)

    def undo(self, result: ChargeResult) -> None:
        self.gateway.refund(result.transaction_id)
```

Wrap `ChargeCommand` in a job queue for async processing. The `undo()` method enables automated rollback on downstream failure.

**Step 4 — Observer notifies downstream systems**

```python
class PaymentService:
    def __init__(self):
        self._observers: list[PaymentObserver] = []

    def subscribe(self, observer: PaymentObserver):
        self._observers.append(observer)

    def _notify(self, event: PaymentEvent):
        for obs in self._observers:
            obs.on_payment(event)

    def charge(self, cmd: ChargeCommand) -> ChargeResult:
        result = cmd.execute()
        self._notify(PaymentEvent(result))
        return result

service = PaymentService()
service.subscribe(LedgerUpdater())
service.subscribe(EmailNotifier())
service.subscribe(FraudAuditLogger())
```

The `PaymentService` knows nothing about concrete subscribers. Adding a new downstream consumer requires zero changes to existing code.

---

## Use It

| Pattern | Real system / framework | When to reach for it |
|---|---|---|
| Factory | AWS SDK (`boto3.client("s3")`) | Object type driven by config or string key |
| Builder | Elasticsearch Query DSL, SQL query builders, `requests.Request` | Complex object with many optional parameters |
| Singleton | Database connection pool, app config, logger | Exactly one instance needed; beware in tests |
| Adapter | `psycopg2` over DB-API 2.0, `requests` adapter layer | Integrating third-party code without modifying it |
| Decorator | Django middleware, FastAPI dependencies, Python `@functools.lru_cache` | Stackable cross-cutting behavior (auth, caching, logging) |
| Facade | AWS SDK high-level resource API vs. low-level client | Simplifying a complex subsystem for common use cases |
| Proxy | gRPC stubs, Hibernate lazy-loaded entities, nginx reverse proxy | Intercept, control, or defer access to an object |
| Strategy | Sort algorithms, compression codecs, ML model backends | Swap algorithms at runtime without changing callers |
| Observer | Kafka consumers, DOM `addEventListener`, Spring `ApplicationEvent` | Broadcast state changes to multiple, decoupled listeners |
| Chain of Responsibility | Express.js middleware, Apache Shiro filter chains | Sequential handlers where each may or may not process a request |
| Command | Celery tasks, AWS SQS messages, CQRS write-side commands | Deferred execution, queuing, undo, audit trails |
| State | Order FSM, TCP connection states, workflow engines | Object behavior that changes discretely with internal state |
| Mediator | Kafka topics, Redux store, message brokers | Decouple many objects that would otherwise cross-reference each other |

---

## Common Pitfalls

- **Singleton as global variable.** Singletons are often an anti-pattern in disguise. They make tests order-dependent (shared mutable state), prevent parallelism, and create invisible coupling. Prefer dependency injection — pass the single instance explicitly rather than accessing it globally.

- **Over-engineering with patterns.** Applying Factory, Abstract Factory, and Builder simultaneously to solve a problem that two classes and a config dict would handle. Start with the simplest structure that works; introduce patterns when the actual pain arrives.

- **Deep decorator stacks with no escape hatch.** Wrapping an object six levels deep makes debugging a stack trace nightmare. Document the stack order, log at each boundary, and ensure each decorator's behavior is independently testable.

- **Observer memory leaks.** Subjects hold strong references to observers. If observers are short-lived objects (e.g., request-scoped components), they won't be garbage-collected until explicitly unsubscribed. Always pair `subscribe` with a `unsubscribe` lifecycle.

- **Treating Template Method as a replacement for composition.** Template Method locks the algorithm skeleton into an inheritance hierarchy. When the skeleton itself needs to vary across contexts, Strategy (composition) is more flexible and testable than Template Method (inheritance).

---

## Exercises

1. **Easy** — Given a logging system that currently hardcodes `print()` statements, refactor it so that the log destination (console, file, remote HTTP endpoint) is swappable at runtime. Which pattern do you use, and why? Sketch the interface and two concrete implementations.

2. **Medium** — You are building a document export service that must produce PDF, HTML, and CSV from the same data model. The export steps are: validate → transform → render → package. The validate and transform steps are identical across formats; render and package differ. Design the class hierarchy using Template Method for the shared skeleton and Strategy for the varying steps. Draw the class diagram with ASCII art.

3. **Hard** — Design an undo/redo system for a collaborative text editor (think Google Docs). Users can type, delete, and format text. Multiple users may be editing simultaneously. Which patterns would you combine (Command, Memento, Observer, others)? Describe how you handle conflict resolution when two users' undo operations affect the same region of text. What data structure holds the command history?

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Design Pattern** | A reusable code snippet or library | A named, abstract solution template for a recurring structural problem — not copy-paste code |
| **Singleton** | "The right way to share state" | One instance per process; often a testing anti-pattern because it hides dependencies |
| **Factory** | Any function that creates objects | Specifically: hiding concrete type selection behind an interface so callers depend on abstractions |
| **Decorator** | Python's `@` syntax | A structural pattern that wraps an object in another with the same interface to add behavior — the `@` syntax is one implementation |
| **Observer** | A callback function | A publish-subscribe relationship where a subject notifies many decoupled listeners on state change |
| **Strategy** | A config flag that changes behavior | An encapsulated, swappable algorithm behind a common interface — runtime polymorphism over conditional branching |
| **Facade** | A simplified API | A structural pattern that hides an entire subsystem behind a single entry point — not the same as a thin wrapper |

---

## Further Reading

- **"Design Patterns: Elements of Reusable Object-Oriented Software"** (GoF) — Gamma, Helm, Johnson, Vlissides. The original 23 patterns with intent, motivation, and applicability. Dense but authoritative. https://www.oreilly.com/library/view/design-patterns-elements/0201633612/

- **Refactoring.Guru Design Patterns** — Visual, language-agnostic explanations of all 23 GoF patterns with UML diagrams and code examples in multiple languages. https://refactoring.guru/design-patterns

- **"Head First Design Patterns"** (Freeman & Robson) — Approachable, example-heavy introduction to the most commonly used patterns. Better first read than the GoF book for most engineers. https://www.oreilly.com/library/view/head-first-design/9781492077992/

- **Martin Fowler — Catalog of Patterns of Enterprise Application Architecture** — Extends beyond GoF into data source, domain logic, and web presentation patterns used in real backend systems. https://martinfowler.com/eaaCatalog/

- **Python Design Patterns (Real Python)** — Practical, idiomatic Python implementations of creational, structural, and behavioral patterns with working code. https://realpython.com/tutorials/patterns/
