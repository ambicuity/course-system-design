# 18 Key Design Patterns Every Developer Should Know

> Patterns are named solutions to recurring design problems — know the name, and you know the trade-off.

**Type:** Learn
**Prerequisites:** Object-Oriented Design Principles, SOLID Principles, UML Basics
**Time:** ~35 minutes

---

## The Problem

Every non-trivial codebase accumulates the same categories of friction: objects that are expensive to construct so you end up with too many of them, components so tightly coupled that changing one breaks three others, or event flows so tangled that adding a new subscriber requires editing a central dispatcher.

Imagine a payment service that creates a new database connection on every transaction. Or a notification system where adding email alerts requires modifying the SMS module. Or a document editor where undo/redo is bolted on as a special case rather than a first-class citizen. Each of these is a solved problem — but only if you recognize it and reach for the right tool.

Design patterns are that vocabulary. They are not library functions you import; they are structural templates that shape how classes and objects relate. Without them, every developer on a team independently invents slightly different wheels, producing code that is hard to read, reason about, and extend.

---

## The Concept

The canonical 23 Gang-of-Four (GoF) patterns fall into three families. The 18 patterns covered here map cleanly across all three:

```
┌─────────────────────────────────────────────────────────────┐
│                  Design Pattern Families                    │
├─────────────────┬───────────────────┬───────────────────────┤
│   CREATIONAL    │    STRUCTURAL     │     BEHAVIORAL        │
│ (how objects    │ (how objects      │ (how objects          │
│  are built)     │  are composed)    │  communicate)         │
├─────────────────┼───────────────────┼───────────────────────┤
│ Abstract Factory│ Adapter           │ Chain of Resp.        │
│ Builder         │ Bridge            │ Command               │
│ Prototype       │ Composite         │ Iterator              │
│ Singleton       │ Decorator         │ Mediator              │
│                 │ Facade            │ Memento               │
│                 │ Flyweight         │ Observer              │
│                 │ Proxy             │ Visitor               │
└─────────────────┴───────────────────┴───────────────────────┘
```

### Creational Patterns — controlling object construction

| Pattern | One-line role | Typical trigger |
|---|---|---|
| **Abstract Factory** | Produces families of related objects without specifying concrete classes | You need interchangeable UI kits (dark/light theme) or database drivers (MySQL/Postgres) |
| **Builder** | Assembles a complex object step-by-step, separating construction from representation | Objects with many optional parts: HTTP requests, SQL queries, test fixtures |
| **Prototype** | Clones an existing instance rather than constructing from scratch | Object initialization is expensive (deep graph, I/O); you need many similar copies |
| **Singleton** | Guarantees a class has exactly one instance with a global access point | Logger, config registry, connection pool manager |

### Structural Patterns — composing objects and classes

| Pattern | One-line role | Typical trigger |
|---|---|---|
| **Adapter** | Translates one interface into another that clients expect | Integrating a third-party library or legacy API without changing its source |
| **Bridge** | Decouples an abstraction from its implementation so both can vary independently | Shape + renderer; remote control + device |
| **Composite** | Lets clients treat individual objects and compositions uniformly via a tree | File-system trees, UI widget hierarchies, org charts |
| **Decorator** | Attaches additional responsibilities to an object dynamically | Middleware stacks, I/O stream wrappers, logging/auth layers |
| **Facade** | Provides a simplified interface over a complex subsystem | SDK entry points, service clients, framework bootstrappers |
| **Flyweight** | Shares fine-grained objects to reduce memory when huge numbers are needed | Text characters in a document editor, particles in a game engine |
| **Proxy** | Controls access to another object — lazy init, caching, access control, logging | Virtual proxy for lazy loading images; protection proxy for ACL checks |

### Behavioral Patterns — defining communication between objects

| Pattern | One-line role | Typical trigger |
|---|---|---|
| **Chain of Responsibility** | Passes a request along a chain until an object handles it | Middleware pipelines, event bubbling, authorization guards |
| **Command** | Encapsulates a request as an object, enabling undo/redo, queuing, and logging | GUI actions, job queues, transactional operations |
| **Iterator** | Provides sequential access to a collection without exposing its internals | `for...of` in JS, Python's `__iter__`, Java's `Iterable` |
| **Mediator** | Centralizes complex many-to-many communication between objects | Chat rooms, air traffic control, UI forms with many interdependent controls |
| **Memento** | Captures and restores an object's internal state without violating encapsulation | Undo/redo, snapshot/rollback, save-game checkpointing |
| **Observer** | Defines a one-to-many dependency so dependents are notified on state change | Event systems, reactive UI, pub/sub, data binding |
| **Visitor** | Lets you add operations to objects without modifying their classes | AST traversal in compilers, report generation across heterogeneous node types |

---

## Build It / In Depth

Five representative patterns, each built from first principles:

### 1. Singleton — the double-checked lock

```python
import threading

class Config:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:               # acquire only on first call
                if cls._instance is None: # second check inside lock
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, path: str = "config.yaml"):
        if not hasattr(self, "_loaded"):
            self._data = self._load(path)
            self._loaded = True

    def _load(self, path): ...
```

The double-checked lock avoids acquiring the mutex on every call once the instance exists — important in hot paths.

### 2. Builder — constructing HTTP requests

```python
class RequestBuilder:
    def __init__(self, url: str):
        self._url = url
        self._headers: dict = {}
        self._body = None
        self._timeout = 30

    def header(self, key: str, value: str) -> "RequestBuilder":
        self._headers[key] = value
        return self                      # fluent interface

    def json_body(self, payload: dict) -> "RequestBuilder":
        import json
        self._body = json.dumps(payload)
        self._headers["Content-Type"] = "application/json"
        return self

    def timeout(self, seconds: int) -> "RequestBuilder":
        self._timeout = seconds
        return self

    def build(self) -> dict:
        return {"url": self._url, "headers": self._headers,
                "body": self._body, "timeout": self._timeout}

# Usage
req = (RequestBuilder("https://api.example.com/pay")
       .header("Authorization", "Bearer token")
       .json_body({"amount": 100})
       .timeout(10)
       .build())
```

### 3. Observer — decoupled event dispatch

```python
from abc import ABC, abstractmethod
from typing import List

class EventBus:
    def __init__(self):
        self._listeners: dict[str, List] = {}

    def subscribe(self, event: str, listener):
        self._listeners.setdefault(event, []).append(listener)

    def publish(self, event: str, payload=None):
        for listener in self._listeners.get(event, []):
            listener(payload)

# Publishers and subscribers know only the bus — not each other
bus = EventBus()
bus.subscribe("order.created", lambda o: print(f"Email: {o}"))
bus.subscribe("order.created", lambda o: print(f"Inventory: {o}"))
bus.publish("order.created", {"id": 42, "amount": 99.0})
```

### 4. Decorator — layered middleware

```python
from functools import wraps
import time

def log_calls(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        print(f"CALL {fn.__name__}")
        result = fn(*args, **kwargs)
        print(f"DONE {fn.__name__}")
        return result
    return wrapper

def retry(times=3):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(1, times + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    if attempt == times:
                        raise
                    print(f"Retry {attempt}/{times}: {e}")
        return wrapper
    return decorator

@log_calls
@retry(times=3)
def charge_card(amount: float): ...
```

Decorators compose: each wraps the next without any knowing about the others.

### 5. Command — undo-able operations

```python
from abc import ABC, abstractmethod
from collections import deque

class Command(ABC):
    @abstractmethod
    def execute(self): ...
    @abstractmethod
    def undo(self): ...

class InsertText(Command):
    def __init__(self, doc: list, pos: int, text: str):
        self._doc, self._pos, self._text = doc, pos, text

    def execute(self):
        self._doc.insert(self._pos, self._text)

    def undo(self):
        self._doc.pop(self._pos)

class History:
    def __init__(self):
        self._stack: deque[Command] = deque()

    def execute(self, cmd: Command):
        cmd.execute()
        self._stack.append(cmd)

    def undo(self):
        if self._stack:
            self._stack.pop().undo()
```

The Command pattern makes every operation a first-class object — trivially queued, logged, retried, or reversed.

---

## Use It

Real systems apply these patterns extensively:

| Pattern | Where it lives in production |
|---|---|
| **Singleton** | `logging.getLogger()` in Python stdlib; Spring's `@Bean` default scope; Redis connection pool |
| **Builder** | AWS SDK's `S3Client.builder()`, `StringBuilder` in Java, SQLAlchemy's query builder |
| **Abstract Factory** | JDBC drivers, React's `createContext` + Provider, Terraform providers |
| **Prototype** | JavaScript's prototype chain; `Object.clone()` in Java; Redux initial-state copying |
| **Adapter** | ORM models adapting SQL to objects; Kafka's `Converter` interface for Serde; Stripe SDK wrapping REST |
| **Facade** | Django's ORM (`User.objects.filter(...)`); boto3 `s3.upload_file()` hiding multipart |
| **Decorator** | Python `@functools.lru_cache`, Flask/FastAPI middleware, Java's `BufferedReader(FileReader(...))` |
| **Proxy** | Spring AOP proxies for `@Transactional`; Hibernate lazy-loading proxies; Nginx as reverse proxy |
| **Observer** | React's `useState` + effect hooks; RxJS Observables; Kafka consumers; DOM `addEventListener` |
| **Command** | CQRS command buses (Axon, MediatR); Celery task queue; database WAL entries |
| **Chain of Resp.** | Express.js middleware chain; Java Servlet filters; AWS Lambda authorizers |
| **Iterator** | Python generators (`yield`), Java `Stream`, Go channels |
| **Composite** | React component tree, HTML DOM, Kubernetes manifest hierarchies |
| **Mediator** | Event-driven microservices via a message broker; chat servers; Redux store |
| **Memento** | Git commits, database savepoints, Photoshop history palette |
| **Strategy** *(adjacent)* | Sorting algorithms in Java's `Comparator`, payment processors |
| **Visitor** | Babel AST plugins, JSON Schema validators, GraphQL type visitors |

---

## Common Pitfalls

- **Singleton overuse.** Singleton is global mutable state with extra steps. In a concurrent system, every shared singleton needs thread-safety analysis. Prefer dependency injection so tests can swap implementations without monkey-patching.

- **Decorator order blindness.** `@retry @log` and `@log @retry` behave differently. `@retry @log` logs only the final attempt; `@log @retry` logs every retry. Define and document the canonical order.

- **Observer memory leaks.** If subscribers never unsubscribe and the event bus is long-lived, subscribers accumulate indefinitely. Always pair `subscribe` with a teardown path — `removeEventListener`, `subscription.unsubscribe()`, or WeakRef.

- **Chain of Responsibility that never terminates.** A handler chain with no terminal handler silently drops requests. Always include a catch-all at the end that logs or errors loudly.

- **Misapplying Builder for simple objects.** If an object has two or three fields, a plain constructor or dataclass is clearer. Builder is justified when optional combinations grow beyond 4-5 parameters and the object is immutable after construction.

---

## Exercises

1. **Easy** — Implement a `Logger` Singleton in a language of your choice. Verify that two variables assigned `Logger()` in different modules reference the same instance. Add a `log(level, msg)` method that prepends a timestamp.

2. **Medium** — Build a minimal HTTP middleware pipeline using the Chain of Responsibility pattern: implement three handlers — `AuthHandler`, `RateLimitHandler`, and `RouterHandler`. Each handler either short-circuits with a 401/429 or passes to the next. Write unit tests covering each path.

3. **Hard** — Design a text editor's undo/redo system using Command + Memento together. Commands mutate the document; Memento snapshots are used for complex multi-step operations (paste with reformat). Decide where the boundary between the two patterns lies and justify it in comments.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Design Pattern** | A library or framework feature you install | A named, reusable solution template for a class of structural problems — no code is shipped |
| **Singleton** | A global variable | A class that enforces at most one instance and provides a controlled access point — thread-safety and testability are non-trivial concerns |
| **Decorator** | Python's `@` syntax | A structural pattern that wraps an object to add behaviour — Python decorators implement it, but the pattern predates Python |
| **Observer** | A pub/sub message broker | A direct object-to-object notification mechanism — the subject holds references to observers; a broker is an external mediator |
| **Facade** | An abstraction layer (generic) | Specifically a simplified interface over a subsystem — it does not change behaviour, only the interface surface |
| **Proxy** | A network proxy (Nginx) | An object that controls access to another object, potentially adding caching, ACL, logging, or lazy initialization |
| **Composite** | A data collection | A tree structure where leaf nodes and composite nodes share the same interface — enables recursive processing without type checks |

---

## Further Reading

- **"Design Patterns: Elements of Reusable Object-Oriented Software"** — Gamma, Helm, Johnson, Vlissides (Gang of Four). The canonical source. Read the intent and applicability sections for each pattern. https://www.amazon.com/Design-Patterns-Elements-Reusable-Object-Oriented/dp/0201633612
- **Refactoring Guru — Design Patterns** — pattern-by-pattern walkthroughs with real-code examples in multiple languages, UML diagrams, and applicability checklists. https://refactoring.guru/design-patterns
- **"Head First Design Patterns"** — Freeman & Robson. Best entry point if the GoF book feels dense; each chapter builds intuition before introducing the formal pattern. https://www.oreilly.com/library/view/head-first-design/9781492077992/
- **SourceMaking Design Patterns** — concise reference with UML and code for all 23 GoF patterns. https://sourcemaking.com/design_patterns
- **Martin Fowler's Catalog of Patterns of Enterprise Application Architecture** — extends GoF into service layers, data mapping, and distributed systems. https://martinfowler.com/eaaCatalog/
