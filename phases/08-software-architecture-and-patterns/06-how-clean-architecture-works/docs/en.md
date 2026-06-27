# How Clean Architecture Works?

> Dependencies always point inward — business logic must never know what framework, database, or UI surrounds it.

**Type:** Learn
**Prerequisites:** Layered Architecture, Dependency Inversion Principle, Repository Pattern
**Time:** ~25 minutes

---

## The Problem

Imagine you built an e-commerce checkout service. The business logic — calculating tax, validating coupons, deducting inventory — is scattered across Rails controllers and ActiveRecord models. One year later, the company decides to migrate from PostgreSQL to DynamoDB and expose a GraphQL API alongside REST. Every single business rule is now entangled with framework internals, so the migration costs six months and introduces regressions in places you never expected to touch.

The root cause is **high coupling at the wrong boundary**. When business logic depends directly on HTTP request objects, ORM models, or a specific database query syntax, it cannot be tested in isolation, ported to a new runtime, or reasoned about without understanding the full stack. You end up with the classic "big ball of mud" — a system where you can't change one thing without breaking three others.

Clean Architecture, introduced by Robert C. Martin, addresses this by enforcing a single structural rule: **source code dependencies can only point inward, toward higher-level policy**. The database, the web framework, and the UI are details. The business rules are the core. This inversion of control over dependencies is what makes the system independently testable, swappable, and long-lived.

---

## The Concept

### The Four Concentric Layers

Clean Architecture organizes code into four rings. The inner rings contain policy; the outer rings contain mechanism.

```
+--------------------------------------------------+
|           Frameworks & Drivers                   |
|   (HTTP server, ORM, message broker, UI)         |
|  +------------------------------------------+   |
|  |        Interface Adapters                |   |
|  |  (Controllers, Presenters, Gateways)     |   |
|  |  +------------------------------------+  |   |
|  |  |         Use Cases                 |  |   |
|  |  |  (Application business rules)     |  |   |
|  |  |  +--------------------------+     |  |   |
|  |  |  |       Entities           |     |  |   |
|  |  |  | (Enterprise rules,       |     |  |   |
|  |  |  |  domain models)          |     |  |   |
|  |  |  +--------------------------+     |  |   |
|  |  +------------------------------------+  |   |
|  +------------------------------------------+   |
+--------------------------------------------------+

Arrow: Outer → Inner (allowed dependency direction)
```

**Entities** — Pure domain objects and rules. An `Order` entity knows that it cannot be paid if it has zero items. It has no import of Flask, Spring, or Express. It is the most stable code in the system.

**Use Cases** — Orchestrate one application workflow. A `PlaceOrderUseCase` calls entity methods, reads from a repository interface, publishes a domain event — all through interfaces it defines itself. It does not know whether the repository is PostgreSQL or Redis.

**Interface Adapters** — Translate between the use-case world and the outside world. A REST controller converts an `HttpRequest` into a plain data struct the use case understands. A repository adapter converts the use case's repository interface into actual SQL. A presenter converts a use-case response object into a JSON payload.

**Frameworks & Drivers** — The outermost ring: Express, Django, Spring Boot, PostgreSQL, Kafka, React. These are configuration and wiring. They import everything inward but nothing inward imports them.

---

### The Dependency Rule (The Only Rule That Matters)

```
Entities       — may import: nothing outside themselves
Use Cases      — may import: Entities
Adapters       — may import: Use Cases, Entities
Frameworks     — may import: Adapters, Use Cases, Entities
```

If any code in an inner ring imports from an outer ring, the architecture is broken. This rule is what enables substitution: swap the outer ring and the inner rings never need to change.

---

### Crossing Boundaries: The Dependency Inversion Trick

The tricky part is that data must still flow from inner to outer (e.g., a use case must trigger a database write). Clean Architecture solves this with **interfaces at the boundary**.

```
                Use Case Layer
+---------------------------------------------+
|  PlaceOrderUseCase                          |
|    calls → IOrderRepository (interface)     |
|    calls → IEventPublisher  (interface)     |
+---------------------------------------------+
         ▲                  ▲
         |                  |
+----------------+   +------------------+
| PostgresRepo   |   | KafkaPublisher   |  ← Interface Adapters
| implements     |   | implements       |
| IOrderRepository   IEventPublisher   |
+----------------+   +------------------+
```

The use case *defines* the interface it needs. The adapter in the outer ring *implements* that interface. At runtime, a dependency-injection container wires them together. This is the Dependency Inversion Principle applied at the architectural level.

---

### Data Transfer Objects (DTOs) at Every Boundary

Raw domain entities must not cross layer boundaries. Each boundary has its own data structure:

| Boundary crossing | Data format |
|---|---|
| HTTP → Controller | `HttpRequest` (framework object) |
| Controller → Use Case | Input DTO (plain struct/data class) |
| Use Case → Repository | Domain Entity / value object |
| Repository → DB | ORM model / raw SQL |
| Use Case → Presenter | Output DTO |
| Presenter → HTTP | JSON / XML response |

Mixing these leads to domain entities carrying serialization annotations or HTTP status codes — a sign that boundaries have been violated.

---

## Build It / In Depth

### Concrete Example: User Registration Flow

Below is a minimal implementation in Python that shows each layer. It is deliberately framework-free until the outermost wiring.

**Step 1 — Entity (pure domain logic)**

```python
# entities/user.py
import re
from dataclasses import dataclass

@dataclass(frozen=True)
class Email:
    value: str

    def __post_init__(self):
        if not re.match(r"[^@]+@[^@]+\.[^@]+", self.value):
            raise ValueError(f"Invalid email: {self.value}")

@dataclass
class User:
    id: str
    email: Email
    hashed_password: str

    def change_email(self, new_email: Email) -> "User":
        # Returns new instance — immutable update
        return User(id=self.id, email=new_email,
                    hashed_password=self.hashed_password)
```

**Step 2 — Use Case (application logic + interfaces it owns)**

```python
# use_cases/register_user.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from entities.user import User, Email
import uuid, hashlib

# ── Interfaces defined BY the use case ──────────────────────────
class IUserRepository(ABC):
    @abstractmethod
    def find_by_email(self, email: str) -> User | None: ...
    @abstractmethod
    def save(self, user: User) -> None: ...

class IPasswordHasher(ABC):
    @abstractmethod
    def hash(self, plain: str) -> str: ...

# ── DTOs ────────────────────────────────────────────────────────
@dataclass
class RegisterUserInput:
    email: str
    password: str

@dataclass
class RegisterUserOutput:
    user_id: str

# ── Use Case ─────────────────────────────────────────────────────
class RegisterUserUseCase:
    def __init__(self, repo: IUserRepository, hasher: IPasswordHasher):
        self._repo = repo
        self._hasher = hasher

    def execute(self, inp: RegisterUserInput) -> RegisterUserOutput:
        email = Email(inp.email)                     # domain validation
        if self._repo.find_by_email(inp.email):
            raise ValueError("Email already registered")
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            hashed_password=self._hasher.hash(inp.password),
        )
        self._repo.save(user)
        return RegisterUserOutput(user_id=user.id)
```

**Step 3 — Interface Adapters (implement the interfaces; translate data)**

```python
# adapters/postgres_user_repo.py
from use_cases.register_user import IUserRepository
from entities.user import User, Email

class PostgresUserRepository(IUserRepository):
    def __init__(self, db_conn):
        self._conn = db_conn

    def find_by_email(self, email: str) -> User | None:
        row = self._conn.execute(
            "SELECT id, email, hashed_password FROM users WHERE email=%s",
            (email,)
        ).fetchone()
        if not row:
            return None
        return User(id=row[0], email=Email(row[1]), hashed_password=row[2])

    def save(self, user: User) -> None:
        self._conn.execute(
            "INSERT INTO users (id, email, hashed_password) VALUES (%s,%s,%s)",
            (user.id, user.email.value, user.hashed_password)
        )

# adapters/bcrypt_hasher.py
import bcrypt
from use_cases.register_user import IPasswordHasher

class BcryptHasher(IPasswordHasher):
    def hash(self, plain: str) -> str:
        return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()
```

**Step 4 — Frameworks & Drivers (wiring and HTTP layer)**

```python
# frameworks/flask_app.py  ← only this file imports Flask
from flask import Flask, request, jsonify
from adapters.postgres_user_repo import PostgresUserRepository
from adapters.bcrypt_hasher import BcryptHasher
from use_cases.register_user import RegisterUserUseCase, RegisterUserInput
import psycopg2

app = Flask(__name__)
conn = psycopg2.connect("postgresql://localhost/mydb")

@app.post("/users")
def register():
    body = request.get_json()
    use_case = RegisterUserUseCase(
        repo=PostgresUserRepository(conn),
        hasher=BcryptHasher(),
    )
    try:
        out = use_case.execute(RegisterUserInput(
            email=body["email"],
            password=body["password"],
        ))
        return jsonify({"user_id": out.user_id}), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
```

Notice that `RegisterUserUseCase` has zero imports from Flask, psycopg2, or bcrypt. You can test it with an in-memory mock repository in milliseconds, no database required.

---

## Use It

### Where Clean Architecture Shows Up in Practice

| Context | How Clean Architecture applies |
|---|---|
| Microservices | Each service is its own Clean Architecture scope; domain events cross service boundaries as DTOs |
| Hexagonal Architecture (Ports & Adapters) | Essentially the same idea; "ports" = interfaces in use-case ring; "adapters" = implementations |
| Domain-Driven Design (DDD) | Entities and Value Objects map to the entity layer; Aggregates guard consistency; Application Services are use cases |
| Android (Google's recommendation) | `ViewModel` → Use Case → Repository interface → Room/Retrofit adapters |
| NestJS / Spring Boot | Modules enforce layer separation; DI containers wire adapters to interfaces at startup |
| CQRS | Command handlers = use cases for writes; Query handlers = use cases for reads with thin read models |

**When to reach for it:** Projects with a 3+ year lifespan, multiple delivery mechanisms (REST + gRPC + CLI), or domain logic complex enough to warrant independent testing. For a simple CRUD API with one database and no logic, Clean Architecture is over-engineered.

---

## Common Pitfalls

- **Entities importing framework types.** Annotating a domain entity with `@Column` (JPA) or `db.Model` (SQLAlchemy) violates the dependency rule. Use separate ORM models in the adapter layer and map explicitly.

- **Use cases knowing about HTTP status codes.** A use case should throw a domain exception (`DuplicateEmailError`). The controller decides whether that maps to 409 or 400 — that is presentation logic, not business logic.

- **Skipping the Input/Output DTO.** Passing the raw framework request object directly into the use case couples business logic to the HTTP layer. If you ever add a CLI entry point, the use case should work without modification.

- **One giant use case per feature.** Use cases should represent a single, named business action. Putting `register`, `login`, and `update_profile` into one `UserService` file that grows to 800 lines recreates the service layer anti-pattern inside the use-case ring.

- **Treating the architecture as layers in a monorepo, not in the imports.** Organizing folders as `controllers/`, `services/`, `repositories/` does not enforce the dependency rule — the rule is about import direction, not folder naming. Use static analysis tools (Dependency Cruiser, ArchUnit, py-depend) to enforce it in CI.

---

## Exercises

1. **Easy** — Take a `Product` class in your codebase (or invent one) and strip it of all imports from any framework or database library. Add one validation rule directly on the entity. Write a unit test that exercises the rule with no infrastructure setup.

2. **Medium** — Model a `TransferFunds` use case: define the input DTO, output DTO, and the two repository interfaces it needs (`IAccountRepository`, `ITransactionLog`). Implement in-memory fakes for both interfaces and write three unit tests covering success, insufficient-funds, and account-not-found scenarios.

3. **Hard** — Build a simple task management API with two delivery mechanisms: a REST controller and a CLI script. Both must call the same `CreateTaskUseCase` without any modification to the use case. Add a second repository implementation backed by a SQLite file and demonstrate swapping it in at the wiring layer while all use-case tests continue to pass.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Clean Architecture** | A specific folder structure for MVC | A set of dependency rules; the folder structure is a consequence, not the goal |
| **Entity** | A database row or ORM model | A pure domain object encapsulating enterprise business rules with no infrastructure dependencies |
| **Use Case** | A service class or controller action | A single named application workflow that orchestrates domain objects; defines the interfaces it needs |
| **Dependency Rule** | A style preference | A hard constraint: no inner ring may import from an outer ring; enforced via static analysis |
| **Interface Adapter** | A design pattern | Any code whose job is to convert data between the use-case world and the outside world (HTTP, DB, queue) |
| **Port** | A network port | In Hexagonal Architecture, a synonym for the interface a use case defines — the "plug" the adapter connects to |
| **DTO (Data Transfer Object)** | An unnecessary boilerplate class | A plain data container that crosses a layer boundary, preventing domain objects from leaking details about adjacent layers |

---

## Further Reading

- [Clean Architecture (book) — Robert C. Martin](https://www.oreilly.com/library/view/clean-architecture-a/9780134494272/) — the primary source; chapters 22-28 cover the layered model in detail
- [The Clean Architecture (blog post) — Robert C. Martin, 2012](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html) — original article that codified the pattern
- [Hexagonal Architecture — Alistair Cockburn](https://alistair.cockburn.us/hexagonal-architecture/) — the complementary formulation ("ports and adapters") worth reading alongside
- [ArchUnit — Java architecture testing library](https://www.archunit.org/) — enforce dependency rules as automated tests in CI; Python equivalent: `import-linter`
- [Dependency Cruiser](https://github.com/sverweij/dependency-cruiser) — visualize and enforce module dependency rules in JavaScript/TypeScript projects
