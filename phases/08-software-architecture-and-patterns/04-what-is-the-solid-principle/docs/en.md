# What is the SOLID Principle?

> Five rules that keep software readable, changeable, and safe to grow — because code that can't change safely, can't survive.

**Type:** Learn
**Prerequisites:** Object-Oriented Design Basics, Design Patterns Overview
**Time:** ~35 minutes

---

## The Problem

Imagine you inherit a 3,000-line `UserService` class. It validates user input, hashes passwords, sends welcome emails, writes to a PostgreSQL database, generates PDF invoices, and pushes events to a Kafka topic. Every feature request touches this file. Every bug fix risks breaking three unrelated things. Deploying a typo fix in the email template forces a full regression run on billing logic. The class is impossible to unit-test in isolation because it requires a live database, a running Kafka broker, and an SMTP server just to instantiate.

This is the reality of software that grew without design principles. The code isn't wrong in the sense that it crashes — it works, until it doesn't. The real damage is invisible: velocity slows to a crawl because developers are afraid to change anything, defect rates creep up because side-effects are impossible to predict, and onboarding new engineers takes weeks because the implicit rules of what can touch what are undocumented.

SOLID is a set of five object-oriented design principles, named and popularized by Robert C. Martin (Uncle Bob), that address exactly this failure mode. They do not guarantee perfect software. They give you a vocabulary and a decision procedure for structuring code so that changes are localized, dependencies are explicit, and modules can be tested, swapped, and extended without fear. Used together, they produce systems where the cost of change stays roughly constant over time instead of compounding.

---

## The Concept

SOLID is an acronym. Each letter maps to one principle:

| Letter | Principle | One-Line Summary |
|--------|-----------|-----------------|
| **S** | Single Responsibility Principle (SRP) | A class has one reason to change |
| **O** | Open/Closed Principle (OCP) | Open for extension, closed for modification |
| **L** | Liskov Substitution Principle (LSP) | Subtypes must be drop-in replacements for base types |
| **I** | Interface Segregation Principle (ISP) | Clients should not depend on interfaces they don't use |
| **D** | Dependency Inversion Principle (DIP) | High-level modules depend on abstractions, not concretions |

The five principles are not independent — they reinforce each other. DIP requires you to introduce abstractions (interfaces). ISP shapes those interfaces. SRP keeps the implementing classes focused. OCP lets you extend the system by adding new implementations. LSP ensures those implementations are interchangeable. In practice you apply them together.

### S — Single Responsibility Principle

A class should have **one, and only one, reason to change**. "Reason to change" is the key phrase. It maps to an *actor* — a stakeholder or system whose requirements could force an edit to this code. A `UserService` that both sends emails and writes to the database has two actors: the team that owns email delivery policy and the team that owns the data schema. If either changes their requirements, the same file changes.

```
BEFORE                            AFTER (SRP)
──────────────────────────        ─────────────────────────
UserService                       UserRepository
  + validateInput()                 + save(user)
  + hashPassword()                  + findById(id)
  + save(user)                   
  + sendWelcomeEmail()           UserAuthService
  + generateInvoice()              + hashPassword()
  + publishEvent()                 + validateInput()

                                  EmailService
                                   + sendWelcomeEmail()

                                  InvoiceService
                                   + generateInvoice()
```

The payoff: each class can be tested in isolation, can be deployed independently (in a microservices context), and can be maintained by a different team without coordination.

### O — Open/Closed Principle

Software entities should be **open for extension but closed for modification**. When new behavior is needed, you add new code — you do not change existing, working code.

The mechanism is usually polymorphism: define an abstraction, implement it, and the calling code never changes when you add a new implementation.

```
# Violation — every new payment type requires editing this class
class PaymentProcessor:
    def process(self, payment_type, amount):
        if payment_type == "credit_card":
            ...
        elif payment_type == "paypal":
            ...
        elif payment_type == "crypto":    # NEW: must edit existing code
            ...

# OCP-compliant — adding CryptoPayment never touches existing code
class PaymentProcessor:
    def process(self, provider: PaymentProvider, amount):
        provider.charge(amount)

class CreditCardProvider(PaymentProvider): ...
class PayPalProvider(PaymentProvider): ...
class CryptoProvider(PaymentProvider): ...   # NEW: zero edits elsewhere
```

### L — Liskov Substitution Principle

If `S` is a subtype of `T`, then objects of type `T` may be replaced with objects of type `S` without altering any of the desirable properties of the program. Practically: a subclass must honor the *behavioral contract* of its parent, not just its interface.

The classic violation is the `Rectangle`/`Square` example:

```
class Rectangle:
    def set_width(self, w): self.width = w
    def set_height(self, h): self.height = h
    def area(self): return self.width * self.height

class Square(Rectangle):
    def set_width(self, w):
        self.width = w
        self.height = w   # "helpfully" keeps it square

# Caller assumes Rectangle contract:
r = get_shape()           # could be Square at runtime
r.set_width(5)
r.set_height(3)
assert r.area() == 15     # FAILS if r is a Square (area = 9)
```

`Square` is mathematically a `Rectangle`, but it violates the behavioral contract. LSP says: if substituting a subclass breaks a caller that worked correctly with the base class, the inheritance hierarchy is wrong. Fix by flattening the hierarchy or using composition.

### I — Interface Segregation Principle

Clients should not be forced to depend on methods they do not use. A fat interface couples unrelated consumers together. When the interface changes for one consumer's needs, all other consumers are recompiled and potentially broken.

```
# FAT interface — forces every implementor to handle all methods
class Machine:
    def print(self, doc): ...
    def scan(self, doc): ...
    def fax(self, doc): ...

class OldPrinter(Machine):
    def fax(self, doc):
        raise NotImplementedError   # forced to implement something it doesn't do

# ISP-compliant — separate, focused interfaces
class Printer:
    def print(self, doc): ...

class Scanner:
    def scan(self, doc): ...

class MultiFunctionDevice(Printer, Scanner): ...
class OldPrinter(Printer): ...     # only implements what it actually does
```

### D — Dependency Inversion Principle

**High-level modules should not depend on low-level modules. Both should depend on abstractions.** Additionally, abstractions should not depend on details — details (concrete implementations) should depend on abstractions.

Without DIP, your business logic is entangled with infrastructure. Swapping a PostgreSQL database for DynamoDB requires editing your core domain classes.

```
# Violation — high-level OrderService is coupled to low-level MySQLDB
class OrderService:
    def __init__(self):
        self.db = MySQLDB()   # concrete dependency baked in

    def place_order(self, order):
        self.db.save(order)


# DIP-compliant — both depend on the abstraction
class OrderRepository:          # abstraction
    def save(self, order): ...

class MySQLOrderRepository(OrderRepository): ...
class DynamoOrderRepository(OrderRepository): ...

class OrderService:
    def __init__(self, repo: OrderRepository):  # injected, not instantiated
        self.repo = repo

    def place_order(self, order):
        self.repo.save(order)
```

Now `OrderService` can be tested with a fake in-memory repository. Swapping the database technology requires zero changes to business logic.

---

## Build It / In Depth

The following example builds a notification system from scratch, applying all five principles step by step.

### Step 1 — Start with the violation

```python
class NotificationService:
    def notify(self, user_id: int, message: str, channel: str):
        # fetch user from DB (low-level detail mixed into business logic)
        import psycopg2
        conn = psycopg2.connect("postgresql://localhost/mydb")
        cur = conn.cursor()
        cur.execute("SELECT email, phone FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()

        if channel == "email":
            import smtplib
            # ... send email directly
        elif channel == "sms":
            import twilio
            # ... send SMS directly
        elif channel == "push":
            import firebase_admin
            # ... send push notification directly
        # Adding Slack requires editing this class (OCP violation)
        # Testing requires a live DB and real credentials (DIP violation)
        # One class does everything (SRP violation)
```

### Step 2 — Extract the abstraction (DIP + ISP)

```python
# abstractions.py
from abc import ABC, abstractmethod

class UserRepository(ABC):
    @abstractmethod
    def get_contact_info(self, user_id: int) -> dict:
        ...

class NotificationChannel(ABC):
    @abstractmethod
    def send(self, contact: str, message: str) -> None:
        ...
```

### Step 3 — Implement focused, single-responsibility classes (SRP)

```python
# repositories.py
class PostgresUserRepository(UserRepository):
    def __init__(self, connection_string: str):
        self._conn_str = connection_string

    def get_contact_info(self, user_id: int) -> dict:
        # actual DB logic isolated here
        ...

# channels.py
class EmailChannel(NotificationChannel):
    def send(self, contact: str, message: str) -> None:
        # SMTP logic isolated here
        ...

class SMSChannel(NotificationChannel):
    def send(self, contact: str, message: str) -> None:
        # Twilio logic isolated here
        ...

class SlackChannel(NotificationChannel):      # OCP: new channel, zero edits to NotificationService
    def send(self, contact: str, message: str) -> None:
        # Slack webhook logic isolated here
        ...
```

### Step 4 — Compose in the high-level service (DIP + SRP)

```python
# notification_service.py
class NotificationService:
    def __init__(
        self,
        user_repo: UserRepository,
        channel: NotificationChannel,
    ):
        self._user_repo = user_repo
        self._channel = channel

    def notify(self, user_id: int, message: str) -> None:
        contact_info = self._user_repo.get_contact_info(user_id)
        self._channel.send(contact_info["email"], message)
```

### Step 5 — Wire it up (composition root)

```python
# main.py
if __name__ == "__main__":
    repo = PostgresUserRepository("postgresql://localhost/mydb")
    email_channel = EmailChannel(smtp_host="smtp.example.com")

    service = NotificationService(repo, email_channel)
    service.notify(user_id=42, message="Your order has shipped.")
```

### Step 6 — Unit test without infrastructure

```python
# test_notification_service.py
class FakeUserRepository(UserRepository):
    def get_contact_info(self, user_id: int) -> dict:
        return {"email": "test@example.com"}

class FakeChannel(NotificationChannel):
    def __init__(self):
        self.sent_messages = []

    def send(self, contact: str, message: str) -> None:
        self.sent_messages.append((contact, message))

def test_notify_sends_correct_message():
    repo = FakeUserRepository()
    channel = FakeChannel()
    service = NotificationService(repo, channel)

    service.notify(user_id=1, message="Hello")

    assert channel.sent_messages == [("test@example.com", "Hello")]
```

No database. No network. Runs in milliseconds. This is the concrete payoff of applying SOLID together.

---

## Use It

### Where SOLID appears in real systems

| Context | Principle most relevant | Example |
|---------|------------------------|---------|
| Django / Spring | DIP via framework DI containers | `@Autowired` in Spring injects concrete beans behind interfaces |
| gRPC / Protobuf | ISP | Service definitions split into fine-grained `rpc` methods; clients only import what they call |
| Plugin architectures (VS Code extensions) | OCP | Extension APIs are stable; new extensions never modify core |
| Event-driven systems (Kafka consumers) | SRP | One consumer per event type, each deployed and scaled independently |
| AWS SDK / cloud SDKs | DIP | Code against `S3Client` interface; swap LocalStack in tests |
| Repository pattern (ORMs) | DIP + SRP | `UserRepository` hides SQLAlchemy or Prisma details from business logic |
| Strategy pattern | OCP + DIP | Sorting, pricing, routing algorithms swapped at runtime via injected strategy |
| Microservices decomposition | SRP | Each service owns one business capability ("one reason to change") |

### Language-specific DI tooling

| Language | DI Framework | Notes |
|----------|-------------|-------|
| Java / Kotlin | Spring, Dagger, Guice | Annotation-driven; production standard |
| Python | `dependency_injector`, FastAPI `Depends` | Lightweight; manual wiring also common |
| TypeScript | InversifyJS, NestJS | NestJS is opinionated full-stack DI |
| Go | Wire (Google), manual | Go favors explicit wiring over magic |
| C# | ASP.NET Core built-in | First-class DI in the framework |

---

## Common Pitfalls

- **Applying SRP too granularly.** A class with a single public method is not always better. "One reason to change" maps to one *business actor or concern*, not one line of code. Over-splitting produces an explosion of micro-classes with anemic behavior and high coupling through excessive collaborators.

- **Treating OCP as "never edit old code."** OCP means don't break existing callers by modifying tested behavior. Fixing a bug or refactoring internals is not an OCP violation. The principle targets the *public interface and behavior contract*, not the implementation internals.

- **Using inheritance to satisfy LSP instead of questioning the hierarchy.** When a subclass needs to throw `NotImplementedError` for a base class method, that is a hierarchy design failure, not a coding problem. Prefer composition over inheritance in ambiguous cases.

- **Creating one giant interface to avoid "too many small interfaces."** ISP violations are common when teams treat interfaces as documentation. If a consumer only calls three methods on a ten-method interface, the interface is too fat — regardless of how convenient it feels to have everything in one place.

- **Implementing DIP with constructor injection but wiring dependencies in the wrong place.** Dependencies should be composed at the *application root* (main, bootstrap, container), not inside domain classes. If a service instantiates its own dependencies (even behind an interface), you still have tight coupling — it just moved one level deeper.

---

## Exercises

1. **Easy — SRP audit.** Take any class in a codebase you work in. List every import at the top of the file. Group those imports by the external concern they represent (database, HTTP, email, auth, etc.). If you have more than two groups, the class likely violates SRP. Write down what classes you would split it into.

2. **Medium — OCP extension.** You have a `ReportExporter` class with an `export_to_csv` method. A new requirement needs `export_to_pdf` and `export_to_excel`. Refactor the class to satisfy OCP: define an `Exporter` interface, implement `CSVExporter`, `PDFExporter`, and `ExcelExporter`, and update `ReportExporter` so it delegates to an injected `Exporter`. Confirm that adding a fourth format (`XMLExporter`) requires zero edits to existing classes.

3. **Hard — LSP + DIP combined.** Design a `PaymentGateway` abstraction for an e-commerce system that must support Stripe, PayPal, and a "test mode" gateway that logs transactions to stdout without hitting any real API. Write the interface, three implementations, and a `CheckoutService` that depends only on the abstraction. Then write a test for `CheckoutService` using the test-mode gateway. Finally, identify one behavioral contract (beyond the method signature) that all implementations must honor, and write a shared contract test that all three implementations must pass.

---

## Key Terms

| Term | What people think | What it actually means |
|------|------------------|----------------------|
| Single Responsibility | "One method per class" | One *reason to change* — one actor whose requirements could force an edit |
| Open/Closed | "Never edit existing code" | Extend behavior by adding code, not by modifying the public contract of existing working code |
| Liskov Substitution | "Subclasses are always safe" | Subtypes must preserve the behavioral contract of the base type, not just the method signatures |
| Interface Segregation | "Small interfaces are always better" | Interfaces should be cohesive around a *client's needs*, not arbitrarily small |
| Dependency Inversion | "Use interfaces everywhere" | High-level policy modules must not import low-level detail modules; both depend on an abstraction owned by the high-level layer |
| Composition Root | (often unknown) | The single place in an application where concrete dependencies are wired together; everything else receives abstractions |
| Behavioral Contract | "Same as method signature" | The set of pre-conditions, post-conditions, and invariants a type guarantees to callers — the thing LSP actually enforces |

---

## Further Reading

- **Clean Architecture — Robert C. Martin (Uncle Bob):** The canonical text on SOLID and its application to layered architecture. Chapters 7–11 cover each principle with detailed examples. https://www.oreilly.com/library/view/clean-architecture-a/9780134494272/
- **SOLID Principles of Object Oriented Design (Pluralsight course):** Hands-on C# walkthroughs of each principle with before/after refactoring. https://www.pluralsight.com/courses/principles-oo-design
- **Martin Fowler — Inversion of Control Containers and the Dependency Injection pattern:** The definitive reference on DI patterns (constructor, setter, interface injection) and when to use a container vs. manual wiring. https://martinfowler.com/articles/injection.html
- **Python Design Patterns — Brandon Rhodes (PyCon):** Practical application of OCP and DIP in a dynamically-typed language where interfaces are implicit. https://python-patterns.guide/
- **Refactoring Guru — SOLID:** Visual, language-agnostic explanations of all five principles with before/after code examples in multiple languages. https://refactoring.guru/solid
