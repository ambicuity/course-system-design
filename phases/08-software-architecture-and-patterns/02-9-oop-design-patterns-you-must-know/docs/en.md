# 9 OOP Design Patterns You Must Know

> Nine patterns that recur in every non-trivial object-oriented codebase — categorized, explained, and grounded in real problems.

**Type:** Learn
**Prerequisites:** Object-oriented programming basics
**Time:** ~30 minutes

---

## The Problem

Every non-trivial codebase hits the same problems: how do I create objects without coupling to concrete classes? How do I add behavior without breaking what already works? How do I let algorithms vary independently from the code that uses them? How do I notify many objects about a change without tangling them together?

Design patterns are the named solutions to these recurring problems. The original "Gang of Four" catalog (Gamma, Helm, Johnson, Vlissides, 1994) describes 23. Most codebases use 5–10 regularly. Knowing the patterns — what they are, when to reach for them, and what they cost — is part of the vocabulary of professional software engineering.

This lesson walks through nine patterns that come up constantly in real codebases, organized into the three canonical categories: creational, structural, and behavioral. For each, you get the problem it solves, the structure, and a concrete example.

---

## The Concept

### The four pillars, before the patterns

Patterns are useless without the underlying OOP principles. Quick refresher:

```
   Abstraction        Hide implementation details; expose only what callers need.
                      Example: a Vehicle class with an abstract stop() method.

   Encapsulation      Bundle data and behavior in a class; restrict outside access.
                      Example: private fields with public methods that control access.

   Inheritance        Create a new class that reuses fields/methods from an existing one.
                      Example: Car extends Vehicle.

   Polymorphism       Same interface, different behavior depending on the actual type.
                      Example: Dog.speak() returns "Woof"; Cat.speak() returns "Meow";
                      both called via animal.speak().
```

Patterns build on these. They are not separate from OOP — they are OOP, applied to recurring problems.

---

### The three categories

```
   Creational          Structural           Behavioral
   (how to create)     (how to compose)     (how objects interact)

   - Factory           - Adapter            - Strategy
   - Singleton         - Decorator          - Observer
   - Builder           - Proxy              - Command
```

**Creational patterns** abstract the instantiation process, so client code does not depend on concrete classes. They hide *which* class is being created and *how*.

**Structural patterns** compose classes and objects into larger structures while keeping them flexible and efficient. They describe *how* things are connected.

**Behavioral patterns** manage algorithms, responsibilities, and communication between objects. They describe *how* objects talk to each other and divide work.

---

## Creational Patterns

### 1. Factory Pattern

**Problem:** client code needs to create objects of different types based on input, but should not be coupled to the concrete classes.

**Without factory:**

```python
# BAD: client code knows about every concrete class
def create_notification(method):
    if method == "email":
        return EmailNotification()
    elif method == "sms":
        return SMSNotification()
    elif method == "push":
        return PushNotification()
```

Every new notification type requires editing the client code. The client is coupled to all concrete classes.

**With factory:**

```python
class NotificationFactory:
    _registry = {
        "email": EmailNotification,
        "sms": SMSNotification,
        "push": PushNotification,
    }

    @classmethod
    def create(cls, method: str) -> Notification:
        if method not in cls._registry:
            raise ValueError(f"Unknown method: {method}")
        return cls._registry[method]()

# Client code:
notification = NotificationFactory.create("email")
notification.send("Hello!")
```

The client knows only the factory and the method name. New types register themselves; the factory code does not change.

**When to use:** when you have a family of related objects that share an interface but differ in implementation, and you want to add new types without modifying existing code.

---

### 2. Singleton Pattern

**Problem:** exactly one instance of a class should exist, accessible globally.

```python
class Config:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        # Load config from disk/env
        self.settings = {...}

# Client code:
config = Config()
config2 = Config()
assert config is config2  # Same instance
```

**When to use:** sparingly. Singletons are usually a code smell — they introduce global state, make testing harder, and create hidden coupling. Legitimate uses: configuration objects, logging services, connection pools.

**Modern alternative:** dependency injection. Pass the single instance explicitly rather than reaching for it globally.

---

### 3. Builder Pattern

**Problem:** constructing a complex object with many optional fields is awkward with constructors or setters.

**Without builder:**

```python
# BAD: confusing positional arguments, lots of None
user = User("Alice", 30, "alice@example.com", None, None, True, False, "premium")
```

**With builder:**

```python
user = (UserBuilder()
    .name("Alice")
    .age(30)
    .email("alice@example.com")
    .newsletter(True)
    .plan("premium")
    .build())
```

The builder pattern separates *how to construct* from *what to construct*. Each method returns `self` so calls chain. `build()` produces the final object.

**When to use:** objects with many optional fields, complex construction steps, or when the same construction logic produces different representations.

---

## Structural Patterns

### 4. Adapter Pattern

**Problem:** you need to use an existing class, but its interface does not match what your code expects.

```python
# Old logger with a different interface
class OldLogger:
    def write_log(self, level, msg):
        ...

# Your code expects a Logger interface
class Logger(Protocol):
    def log(self, level: str, message: str) -> None: ...

# Adapter makes OldLogger compatible
class OldLoggerAdapter:
    def __init__(self, old_logger: OldLogger):
        self._old = old_logger

    def log(self, level: str, message: str) -> None:
        self._old.write_log(level, message)
```

The adapter translates calls from the new interface to the old one. Existing code can use OldLogger through the Logger interface.

**When to use:** when integrating with a third-party library whose interface does not match yours, or when refactoring legacy code that you cannot change all at once.

---

### 5. Decorator Pattern

**Problem:** you need to add behavior to an object dynamically, without modifying its class.

```python
class Coffee(Protocol):
    def cost(self) -> float: ...
    def description(self) -> str: ...

class SimpleCoffee:
    def cost(self): return 5.0
    def description(self): return "Coffee"

class MilkDecorator:
    def __init__(self, coffee: Coffee):
        self._coffee = coffee
    def cost(self): return self._coffee.cost() + 1.5
    def description(self): return self._coffee.description() + ", milk"

class SugarDecorator:
    def __init__(self, coffee: Coffee):
        self._coffee = coffee
    def cost(self): return self._coffee.cost() + 0.5
    def description(self): return self._coffee.description() + ", sugar"

# Usage:
coffee = SimpleCoffee()
coffee = MilkDecorator(coffee)
coffee = SugarDecorator(coffee)
print(coffee.description())  # "Coffee, milk, sugar"
print(coffee.cost())          # 7.0
```

Each decorator wraps the object and adds its own behavior. Decorators can be stacked.

**When to use:** when you need to add optional features to objects in a flexible, composable way. Also the basis of Python's `@decorator` syntax for functions.

**Note:** Python's `@decorator` syntax on functions is unrelated to this OOP pattern, despite the shared name. They solve the same conceptual problem (wrapping with additional behavior) but at different layers.

---

### 6. Proxy Pattern

**Problem:** you need to control access to an object — lazy loading, access control, caching, remote invocation — without changing the object's interface.

```python
class ImageProxy:
    def __init__(self, filename: str):
        self._filename = filename
        self._real_image = None  # lazy-loaded

    def display(self):
        if self._real_image is None:
            self._real_image = RealImage(self._filename)  # load on demand
        self._real_image.display()
```

**Variants:**

- **Virtual proxy** — lazy load expensive resources
- **Protection proxy** — check permissions before delegating
- **Remote proxy** — represent an object in another process (gRPC clients, database connections)
- **Caching proxy** — return cached results when appropriate

**When to use:** when you need to add a layer of control between the client and the real object without changing either.

---

## Behavioral Patterns

### 7. Strategy Pattern

**Problem:** you have a family of algorithms (sorting strategies, pricing rules, validation rules) and want to choose between them at runtime.

```python
from typing import Protocol

class PricingStrategy(Protocol):
    def calculate(self, base_price: float, quantity: int) -> float: ...

class NoDiscount:
    def calculate(self, base_price, quantity):
        return base_price * quantity

class PercentageDiscount:
    def __init__(self, percent: float):
        self.percent = percent
    def calculate(self, base_price, quantity):
        return base_price * quantity * (1 - self.percent / 100)

class BulkDiscount:
    def calculate(self, base_price, quantity):
        if quantity >= 100:
            return base_price * quantity * 0.7
        return base_price * quantity

class Order:
    def __init__(self, pricing: PricingStrategy):
        self.pricing = pricing

    def total(self, base_price, quantity):
        return self.pricing.calculate(base_price, quantity)

# Swap strategies at runtime
order = Order(PercentageDiscount(20))
order.total(100, 10)  # 800.0

order = Order(BulkDiscount())
order.total(100, 200)  # 7000 * 0.7 = 14000... wait, 100*200 = 20000, * 0.7 = 14000
```

**When to use:** when you have multiple algorithms for the same task, when you want to isolate algorithm logic from the code that uses it, or when a class has too many conditional branches choosing between variants.

---

### 8. Observer Pattern

**Problem:** many objects need to be notified when one object changes state, without the source object knowing about each observer.

```python
class EventEmitter:
    def __init__(self):
        self._listeners = {}

    def on(self, event: str, callback):
        self._listeners.setdefault(event, []).append(callback)

    def emit(self, event: str, *args, **kwargs):
        for callback in self._listeners.get(event, []):
            callback(*args, **kwargs)

# Usage:
emitter = EventEmitter()
emitter.on("user_registered", lambda u: send_welcome_email(u))
emitter.on("user_registered", lambda u: track_signup(u))
emitter.on("user_registered", lambda u: notify_admin(u))

emitter.emit("user_registered", User("Alice"))  # triggers all three
```

**When to use:** when a state change in one object needs to trigger actions in many others, when you do not know in advance how many objects need to be notified, or when you want to decouple the source from the observers.

**Modern equivalents:** event emitters, pub/sub systems, message queues, observer hooks in frameworks (Django signals, Vue reactivity, React state libraries).

---

### 9. Command Pattern

**Problem:** you need to encapsulate a request as an object — so you can queue it, log it, undo it, or send it over the network.

```python
from abc import ABC, abstractmethod

class Command(ABC):
    @abstractmethod
    def execute(self) -> None: ...
    @abstractmethod
    def undo(self) -> None: ...

class AddItemCommand(Command):
    def __init__(self, cart, item):
        self.cart = cart
        self.item = item

    def execute(self):
        self.cart.add(self.item)

    def undo(self):
        self.cart.remove(self.item)

class RemoveItemCommand(Command):
    def __init__(self, cart, item):
        self.cart = cart
        self.item = item

    def execute(self):
        self.cart.remove(self.item)

    def undo(self):
        self.cart.add(self.item)

class CartController:
    def __init__(self):
        self.history = []

    def run(self, command: Command):
        command.execute()
        self.history.append(command)

    def undo_last(self):
        if self.history:
            self.history.pop().undo()
```

**When to use:** when you need undo/redo, transactional behavior, queueing of operations, audit logging of actions, or remote command execution.

---

## Build It / In Depth

### The patterns in real codebases

| Pattern | Where you see it |
|---|---|
| **Factory** | `LoggerFactory.create()`, ORM session factories, payment provider selection |
| **Singleton** | Database connection pools, configuration objects, thread pools (often via DI) |
| **Builder** | HTTP request builders (OkHttp, requests), test data builders, complex query construction |
| **Adapter** | Database driver wrappers, third-party API clients, legacy code integration |
| **Decorator** | Middleware stacks (Express, Django, Flask), retry/timeout wrappers, instrumentation |
| **Proxy** | gRPC clients, lazy-loading image components, caching layers |
| **Strategy** | Pricing engines, sorting algorithms, compression selection, validation rules |
| **Observer** | Event emitters, pub/sub systems, UI frameworks (React/Vue reactivity), message queues |
| **Command** | Task queues (Celery, Sidekiq), undo/redo, audit logs, transactional scripts |

### Anti-patterns to avoid

| Anti-pattern | What goes wrong |
|---|---|
| **Pattern fever** | Applying patterns when a simple function would do |
| **Singleton everywhere** | Hidden global state; testing nightmares |
| **Deep inheritance** | Fragile base-class problem; prefer composition |
| **Decorator explosion** | Too many layers; hard to debug which one misbehaved |
| **Strategy via flag** | Passing a string where you should pass a strategy object |

---

## Use It

### Decision cheat sheet

| When you find yourself… | Consider… |
|---|---|
| Choosing between many concrete classes based on input | Factory |
| Needing exactly one shared instance | Singleton (or DI) |
| Constructing an object with many optional fields | Builder |
| Wrapping an object to add behavior | Decorator |
| Integrating with an incompatible interface | Adapter |
| Controlling access to an expensive or remote object | Proxy |
| Selecting an algorithm at runtime | Strategy |
| Notifying many objects about state changes | Observer |
| Queuing, logging, or undoing operations | Command |

---

### How patterns combine

In a real codebase, patterns rarely appear alone:

```
   Web request
       │
       ▼
   [Adapter] wraps an SDK
       │
       ▼
   [Factory] creates the right adapter based on config
       │
       ▼
   [Strategy] selects the algorithm (rate limiter, validator, etc.)
       │
       ▼
   [Decorator] adds cross-cutting concerns (retry, logging, metrics)
       │
       ▼
   [Command] encapsulates the request for the queue
       │
       ▼
   [Observer] notifies downstream services
```

Each layer applies a pattern that fits its problem. Knowing the patterns lets you read and write this kind of layered architecture fluently.

---

## Common Pitfalls

- **Applying patterns before understanding the problem.** A factory for two types is over-engineering. A singleton when DI would do is a hidden global. Use patterns when the problem justifies the complexity.

- **Confusing similar patterns.** Factory vs Builder, Adapter vs Proxy, Strategy vs State. The differences matter when reasoning about alternatives.

- **Cargo-culting the GoF book.** The 1994 catalog was written for C++ and Smalltalk. Modern languages have features (first-class functions, generics, pattern matching) that make some patterns less necessary.

- **Singleton abuse.** Singletons are usually a code smell. Reach for dependency injection instead.

- **Decorator chains that are too long.** A 10-layer decorator chain is impossible to debug. Keep chains shallow.

- **Pattern-driven naming.** Calling something a `CommandFactoryProvider` does not make the design right. Names follow from behavior, not vice versa.

---

## Exercises

1. **Easy** — Pick three of the nine patterns. For each, give a concrete real-world example (not code) of where you have seen it or where you would use it.

2. **Medium** — Pick a non-trivial library you use regularly (an HTTP client, an ORM, a UI framework). Identify three patterns from this lesson used in its design. For each, explain which problem it solves and how the library uses it.

3. **Hard** — Design a notification system (email, SMS, push, in-app) that needs to: (a) support new notification types without modifying the dispatcher, (b) allow composing multiple channels (e.g., email + SMS for critical alerts), (c) record every notification for audit, (d) retry failed notifications with exponential backoff. Identify which pattern fits each requirement and sketch the classes.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Design pattern | A code template | A named, proven solution to a recurring design problem; emphasizes intent and trade-offs over code |
| Factory pattern | A class that creates things | A pattern that abstracts object creation so client code depends on interfaces, not concrete classes |
| Singleton pattern | A global variable | A pattern that ensures exactly one instance exists; often replaced by dependency injection in modern code |
| Builder pattern | A constructor with setters | A pattern that separates the construction of a complex object from its representation, allowing optional fields and step-by-step assembly |
| Adapter pattern | A wrapper | A pattern that translates one interface into another the client expects; used to integrate incompatible code |
| Decorator pattern | Wrapping an object | A pattern that adds behavior to an object dynamically by wrapping it; composable for stacking behaviors |
| Proxy pattern | A stand-in | A pattern that controls access to another object — lazy loading, caching, access control, remote invocation |
| Strategy pattern | A flag for behavior | A pattern that encapsulates a family of algorithms and makes them interchangeable at runtime |
| Observer pattern | An event listener | A pattern where many objects subscribe to events from a source; the source does not know about specific observers |
| Command pattern | A function as an object | A pattern that encapsulates a request as an object, enabling queuing, logging, undo, and remote execution |

---

## Further Reading

- **"Design Patterns: Elements of Reusable Object-Oriented Software"** — the original Gang of Four book: https://en.wikipedia.org/wiki/Design_Patterns
- **Refactoring Guru** — an excellent free online catalog of patterns with examples in multiple languages: https://refactoring.guru/design-patterns
- **"Head First Design Patterns"** — a more approachable introduction: https://www.oreilly.com/library/view/head-first-design/9781492077992/
- **Source Making** — patterns and anti-patterns explained with code: https://sourcemaking.com/design_patterns
- **Patterns of Enterprise Application Architecture** — Martin Fowler's catalog of larger-scale patterns: https://martinfowler.com/eaaCatalog/