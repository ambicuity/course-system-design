# What are Modular Monoliths?

> A single deployable unit with multiple independent modules — the best of both worlds when microservices are too much and a monolith is too rigid.

**Type:** Learn
**Prerequisites:** Monolith vs microservices basics, OO design
**Time:** ~20 minutes

---

## The Problem

Two architectural extremes dominate the conversation: the **monolith** (one big deployment unit, simple but rigid) and **microservices** (many small services, flexible but operationally heavy). Teams often jump from one to the other without considering the middle.

A **modular monolith** is that middle. It is a single deployable unit — one codebase, one deployment pipeline, one database connection pool — but its internal structure is divided into independent modules with clear boundaries. Each module could be extracted into a microservice later if needed, but extracting is a deliberate decision rather than the starting architecture.

This lesson explains what a modular monolith is, how to structure one, when it is the right choice, and how it differs from both traditional monoliths and microservices.

---

## The Concept

### The three options, side by side

```
   Monolith                   Modular Monolith             Microservices
   ─────────                  ────────────────             ─────────────
   ┌─────────────────┐        ┌─────────────────┐         ┌──────┐ ┌──────┐
   │                 │        │ ┌─────┐ ┌─────┐ │         │      │ │      │
   │   Everything    │        │ │Mod A│ │Mod B│ │         │ Svc A│ │Svc B│
   │   together      │        │ └─────┘ └─────┘ │         │      │ │      │
   │                 │        │ ┌─────┐ ┌─────┐ │         └──────┘ └──────┘
   │                 │        │ │Mod C│ │Mod D│ │         ┌──────┐ ┌──────┐
   │                 │        │ └─────┘ └─────┘ │         │      │ │      │
   └─────────────────┘        └─────────────────┘         │Svc C│ │Svc D│
                                                          │      │ │      │
   1 deployment              1 deployment                 └──────┘ └──────┘
   shared DB                 shared DB                    N deployments
   tightly coupled           loosely coupled              N databases
                                                         distributed
```

A modular monolith is a single deployment unit that has been *refactored internally* into clear modules. The boundaries are enforced by code structure, not by network calls.

---

### The key properties

A modular monolith is more than "code organized into folders." It requires deliberate structural discipline.

**1. Each module is independent.**

A module owns its data, business logic, and public interface. Other modules cannot reach in and modify its internal state. They can only call its public API.

```
   Modular structure:
   ┌─────────────────────────────────────────────────────┐
   │  Billing Module                                     │
   │  ─────────────                                      │
   │  Public API:                                        │
   │    charge_customer(user_id, amount) -> Invoice      │
   │    get_invoice(invoice_id) -> Invoice               │
   │    list_invoices(user_id) -> List[Invoice]          │
   │                                                     │
   │  Internal (private):                                │
   │    _stripe_client                                   │
   │    _invoice_repository                              │
   │    _pricing_rules                                   │
   │                                                     │
   │  Other modules can only call the public API.        │
   │  They cannot import _stripe_client directly.        │
   └─────────────────────────────────────────────────────┘
```

**2. Each module provides a specific functionality.**

Modules map to bounded contexts in domain-driven design. Billing is a module. User management is a module. Search is a module. Each has one responsibility.

**3. Each module exposes a well-defined interface.**

The interface is the contract. Implementations can change without affecting other modules — as long as the interface is preserved.

---

### Why "monolith" gets a bad reputation

A traditional monolith becomes problematic because:

- **No boundaries.** Everything can call everything. A change in module A breaks module B.
- **Shared mutable state.** Global variables, shared singletons, common database tables.
- **Coupled deployments.** A one-line change in the auth module requires redeploying the entire system.
- **Scaling is all-or-nothing.** Either you scale the whole thing or nothing.

A *modular* monolith solves these problems within a single deployment unit. Boundaries are enforced by code structure (directories, packages, visibility modifiers). State is module-local. Deployments are unified, but changes are localized in their effect.

---

### How to enforce modularity

Three technical patterns enforce module boundaries:

**1. Package-by-feature (or package-by-component)**

Organize code by feature, not by technical layer.

```
   # BAD: package-by-layer
   src/
     controllers/
       user_controller.py
       billing_controller.py
       search_controller.py
     models/
       user.py
       invoice.py
     services/
       user_service.py
       billing_service.py
       search_service.py

   # GOOD: package-by-feature
   src/
     users/
       __init__.py          # public API
       api.py               # controllers
       domain.py            # business logic
       repository.py        # data access
       models.py            # data structures
       tests/
     billing/
       __init__.py          # public API
       api.py
       domain.py
       repository.py
       models.py
       tests/
     search/
       ...
```

When code is organized by feature, the module boundary is physical. You can see at a glance what belongs to which module.

**2. Visibility modifiers**

Most languages support some form of module-private visibility:

```python
# users/__init__.py — the public API
from .api import router as users_router
from .domain import get_user, create_user, update_user  # explicit re-exports

# Anything not in __init__.py is considered private.
# Other modules should not import from users.repository directly.
```

```java
// Java has package-private visibility built in.
// public: visible to everyone
// protected: visible to subclasses
// (default): visible within the package only — perfect for module-internal code
// private: visible within the class only
```

```typescript
// TypeScript: do not export internals from the module file
// users/index.ts
export { UserService } from './user-service';        // public
// (no export of repository, internal utilities, etc.)
```

**3. Architectural tests**

Some teams add automated tests that verify modules do not import each other's internals:

```python
# Python with import-linter or custom checks
def test_billing_does_not_import_users_repository():
    """Billing should access user data via the public API only."""
    billing_source = read_source("src/billing/")
    for forbidden in ["users.repository", "users.models"]:
        assert forbidden not in billing_source, \
            f"Billing must not import {forbidden}; use users public API"
```

```java
// ArchUnit (Java) lets you express architectural rules as tests
@ArchTest
static final ArchRule billing_should_not_access_users_internals =
    noClasses().that().resideInAPackage("..billing..")
        .should().dependOnClassesThat().resideInAPackage("..users.internal..");
```

These tests fail CI if a developer violates the boundary. Boundaries that are enforced by tools stay clean; boundaries that depend on discipline erode.

---

### Shared database vs. module-owned data

The trickiest design decision in a modular monolith is data ownership.

**Option A: Shared database, schema-per-module**

```
   one database, multiple schemas:
     users_schema (users, user_preferences)
     billing_schema (invoices, payments)
     search_schema (search_index)
```

Each module owns a schema. Other modules can read the schema if needed (read-only, with permission), but writes go through the owning module's API. This is the most common modular monolith pattern.

**Option B: Module-owned tables, no cross-module access**

Each module owns its tables; other modules have no access. Cross-module data access goes through APIs only. Strictest, closest to microservice-like boundaries.

**Option C: Shared tables, shared schema**

This is the traditional monolith. Avoid it in a modular monolith — it creates the coupling you are trying to eliminate.

**The pragmatic default:** Option A. Each module owns its tables; cross-module reads are allowed but discouraged; cross-module writes go through the API.

---

### When to use a modular monolith

| Situation | Why modular monolith fits |
|---|---|
| **Starting a new project** | Avoid premature microservice complexity; defer the decision |
| **Small to medium team (5–20 engineers)** | One deployable unit is operationally simpler; modules still provide structure |
| **Unclear domain boundaries** | Easier to refactor module boundaries inside one codebase than to extract services |
| **Need rapid iteration** | One deploy pipeline is faster than coordinating many |
| **Want to defer microservices** | Modular structure makes later extraction feasible |

---

### When NOT to use a modular monolith

| Situation | Better choice |
|---|---|
| Independent scaling per feature | Microservices or serverless |
| Independent deploy cadence per team | Microservices |
| Different tech stacks per module | Microservices or polyrepo |
| Strong fault isolation required | Microservices with proper bulkheads |
| Team > 50 engineers on same codebase | Probably needs decomposition into services |

---

## Build It / In Depth

### A reference architecture

```
   src/
     shared/                          # cross-cutting code
       __init__.py
       database.py
       auth.py
       events.py
       errors.py

     users/                           # user management module
       __init__.py                    # public API
       api.py                         # HTTP routes
       domain.py                      # User, UserCreated, etc.
       service.py                     # business logic
       repository.py                  # data access
       events.py                      # domain events
       tests/

     billing/                         # billing module
       __init__.py
       api.py
       domain.py                      # Invoice, Payment
       service.py
       repository.py
       events.py
       tests/

     search/                          # search module
       __init__.py
       api.py
       indexer.py                     # builds the search index
       query.py                       # search logic
       tests/

     main.py                          # composition root
                                     # imports each module's public API
                                     # wires routes to the app
```

Each `__init__.py` is the contract. Inside each module, code can be organized freely. Across modules, only the public API is touched.

---

### Migrating a monolith to modular, step by step

**Step 1: Identify module boundaries.**

Group existing code into bounded contexts. Look for natural seams: distinct data models, distinct teams, distinct change patterns.

**Step 2: Establish the public API for each module.**

For each module, write an `__init__.py` (or equivalent) that re-exports only the public types and functions.

**Step 3: Move shared infrastructure into `shared/`.**

Database connection, auth middleware, logging, event bus. None of these belong to any module.

**Step 4: Add architectural tests.**

Test that modules do not import each other's internals. Run them in CI.

**Step 5: Refactor incrementally.**

One module at a time. After each, run the architectural tests and the integration tests. The build should never be broken.

**Step 6: Document the modules.**

For each module, a short README: what it does, what its public API is, what events it publishes and consumes.

---

### When to extract a module into a microservice

A modular monolith is not the destination. It is a waypoint. Extract a module into a microservice when:

1. **Independent scaling.** One module is 10× the load of others; it deserves its own scaling budget.
2. **Independent deploy cadence.** One module ships daily; others ship weekly. The slow ones hold back the fast one.
3. **Different tech stack needed.** One module would benefit from a different language or runtime (e.g., a real-time module wants Elixir; the rest is Python).
4. **Strong fault isolation required.** One module's failure should not affect others.
5. **Different team owns it.** A team needs to own the entire service, including deployment and operations.

The modular structure makes extraction feasible: you know exactly what the module's API is, what data it owns, and what its dependencies are. The extraction becomes a deliberate refactoring, not a rewrite.

---

## Use It

### When to start with each architecture

```
   Greenfield project, small team, unclear domain?
   → Start with a modular monolith. Refactor to modules early.
   → Promote to microservices when concrete pressure appears.

   Greenfield project, large team, well-understood domain?
   → Start with services from the beginning — but be willing to merge
     too-fine-grained services into a modular monolith.

   Existing monolith, growing pains?
   → Refactor to a modular monolith first.
   → Extract the most painful modules into services later.

   Microservices in trouble?
   → Sometimes the right move is to merge them into a modular monolith.
     Microservices have a high coordination cost; not every team needs them.
```

---

### Common patterns inside a modular monolith

| Pattern | Use |
|---|---|
| **In-process event bus** | Modules communicate via events (e.g., `billing.paid` event consumed by `notifications`) |
| **Sync module-to-module API calls** | Simple, direct calls; fine for low-latency local calls |
| **Shared database with schemas** | Pragmatic data sharing; cross-module joins discouraged |
| **CQRS read models** | One module owns the write model; another module maintains a read-optimized view |
| **Saga / process manager** | Multi-module workflows with compensation logic |

---

## Common Pitfalls

- **Treating folder structure as the boundary.** A directory is not a boundary unless it is enforced. Without visibility modifiers and architectural tests, the boundary erodes.

- **Sharing too much through `shared/`.** `shared/` should be infrastructure (database, auth, logging). Business logic does not belong there; it belongs in a module.

- **Cross-module joins in SQL.** When module A joins module B's tables directly, the boundary is broken. Always go through the API.

- **No domain events.** Without events, modules must call each other synchronously for every state change. This creates tight coupling. Domain events let modules react asynchronously.

- **Premature extraction.** Pulling a module into a microservice before it has clear boundaries leads to a "distributed monolith" — the worst of both worlds.

- **Ignoring the team structure.** Conway's law: the system mirrors the communication structure of the organization. If two modules are owned by separate teams that need to ship independently, they will eventually need to be separate services.

- **Too many modules too early.** Premature modularity (a module per class) makes the codebase hard to navigate. Modules should map to meaningful business capabilities, not arbitrary file groupings.

---

## Exercises

1. **Easy** — In one sentence each, describe a traditional monolith, a modular monolith, and microservices. List one advantage of each.

2. **Medium** — Take a real codebase (yours or an open-source one). Identify three potential module boundaries. For each, describe what would move into the module, what its public API would expose, and what would stay in `shared/`.

3. **Hard** — You have a 200k-line monolith that has become hard to maintain. Design a phased plan to convert it to a modular monolith: which module to extract first, how to maintain backward compatibility during the migration, how to enforce boundaries, and when to know you are done.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Monolith | A single file or process | A single deployable unit; usually contrasted with microservices, which are many deployable units |
| Modular monolith | A monolith with packages | A single deployable unit with strict internal module boundaries enforced by code structure and visibility |
| Bounded context | A domain term | A domain-driven design concept — a boundary within which a particular model is consistent; modules often map to bounded contexts |
| Distributed monolith | Microservices | Microservices that are tightly coupled and require coordinated deployments; the worst of both worlds |
| Domain event | A log entry | A fact emitted by a module when its state changes; consumed by other modules for integration |
| Package-by-feature | A folder convention | Organizing code by business capability (users, billing) rather than technical layer (controllers, models) — enforces module boundaries physically |
| Architectural test | A meta-test | A test that verifies architectural rules (e.g., "billing cannot import users internals"); catches boundary violations in CI |
| Service extraction | Refactoring a module to a microservice | Promoting one module of a monolith to a separate deployable service; the modular structure makes this feasible |

---

## Further Reading

- **"Modular Monoliths"** — Simon Brown on the architectural middle ground: https://simonbrown.je/blog/building-modular-monoliths/
- **"Monolith First"** — Martin Fowler on starting with a monolith: https://martinfowler.com/bliki/MonolithFirst.html
- **"How to break a Monolith into Microservices"** — the canonical guide on incremental decomposition: https://martinfowler.com/articles/break-monolith-into-microservices.html
- **"Building Microservices"** — Sam Newman's book; includes a chapter on when *not* to use microservices: https://samnewman.io/books/building_microservices/
- **Domain-Driven Design** — Eric Evans; the source of the bounded-context concept: https://domainlanguage.com/ddd/