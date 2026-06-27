# 9 Clean Code Principles To Keep In Mind

> Nine rules that turn code from "it works" to "I can read this in six months" — distilled from Robert Martin's Clean Code and a decade of production experience.

**Type:** Learn
**Prerequisites:** Writing code in any language
**Time:** ~25 minutes

---

## The Problem

Code is read more often than it is written. The person reading it six months from now is usually you, and you will not remember what you were thinking. Clean code is the discipline of writing code that minimizes the cognitive load on the next reader — including future you.

The principles below are not arbitrary style rules. They emerged from decades of production experience and are documented in Robert Martin's *Clean Code* and elsewhere. They are the difference between codebases that age well and codebases that become unmaintainable after two years.

This lesson walks through nine principles that have the highest signal-to-noise ratio. None are about tabs vs. spaces. All are about how code communicates intent.

---

## The Concept

### The nine principles

```
   Naming & Expression
     1. Meaningful Names
     2. Self-Explanatory Code
     3. Comment Why, Not What

   Function Design
     4. One Function, One Responsibility
     5. Limit Function Arguments
     6. Avoid Deep Nesting

   Code Quality
     7. Avoid Magic Numbers
     8. Use Descriptive Booleans
     9. Keep Code DRY
```

These are not independent. They reinforce each other. A well-named function with clear arguments rarely needs comments. A function that does one thing rarely has deep nesting. Together, they turn "it works" into "I understand it."

---

### 1. Meaningful Names

Names should reveal purpose, not just value. Compare:

```python
# BAD: names describe the type or value, not the intent
d = 7                          # what is 7?
elapsed = days                 # what unit? since when?
the_list = get_them()          # them what?
```

```python
# GOOD: names describe what the variable holds
MAX_RETRIES = 7
DAYS_SINCE_LAST_LOGIN = days
active_users = get_active_users()
```

**Rules:**

- A name should answer "why does this exist?" or "what does this hold?"
- Avoid abbreviations unless universally understood (URL, ID are fine; `usr_nm` is not).
- Boolean names should be questions: `is_active`, `has_children`, `should_retry`.
- Class names are nouns. Method names are verbs.
- Names should be searchable: `MAX_RETRIES` is searchable; `7` is not.

---

### 2. One Function, One Responsibility

A function should do one thing, do it well, and do only it.

```python
# BAD: this function does four things
def process_user_registration(request):
    # 1. Validate
    if not request.email or "@" not in request.email:
        return {"error": "invalid email"}
    # 2. Hash password
    hashed = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt())
    # 3. Save to DB
    user = User(email=request.email, password=hashed, created_at=datetime.now())
    db.session.add(user)
    db.session.commit()
    # 4. Send welcome email
    send_email(request.email, "Welcome!", template="welcome")
    return {"success": True, "user_id": user.id}
```

```python
# GOOD: each step is its own function
def register_user(request):
    validate_registration(request)
    user = create_user(request)
    send_welcome_email(user)
    return user

def validate_registration(request):
    if not is_valid_email(request.email):
        raise ValidationError("invalid email")
    if not is_strong_password(request.password):
        raise ValidationError("weak password")

def create_user(request):
    hashed = hash_password(request.password)
    user = User(email=request.email, password_hash=hashed)
    db.session.add(user)
    db.session.commit()
    return user
```

**Why:** single-responsibility functions are easier to test (one thing to verify), easier to reuse (no hidden dependencies), and easier to refactor (changing one thing does not break others).

**Heuristic:** if you can extract a meaningful name for what your function does at a higher level, you have more than one responsibility.

---

### 3. Avoid Magic Numbers

Replace hardcoded values with named constants.

```python
# BAD: 86400 — what is it?
if elapsed > 86400:
    send_reminder()

# BAD: 0.2 — what threshold? what unit?
if similarity < 0.2:
    return "no match"

# BAD: 3 — why three?
for i in range(3):
    attempt_request()
```

```python
# GOOD: named constants explain the meaning
SECONDS_PER_DAY = 86400
SIMILARITY_THRESHOLD = 0.2
MAX_RETRY_ATTEMPTS = 3

if elapsed > SECONDS_PER_DAY:
    send_reminder()

if similarity < SIMILARITY_THRESHOLD:
    return "no match"

for attempt in range(MAX_RETRY_ATTEMPTS):
    attempt_request()
```

**Why:** the number does not change, but its *meaning* does. When you read `86400` a year from now, you have no idea what it represents. `SECONDS_PER_DAY` is self-documenting. When the threshold changes from 0.2 to 0.25, you change one constant — and you cannot miss it in code review.

**Exception:** numbers whose meaning is obvious from context (`for i in range(10): print(i)` is fine because the loop is trivial).

---

### 4. Use Descriptive Booleans

Boolean names should describe a condition, not its value.

```python
# BAD: ambiguous or tautological
def update(open, read, write):
    ...

user = get_user(open=True)  # open what?

if read:                    # read what?
    do_something()
```

```python
# GOOD: the name states a question or condition
def update(is_open, has_unread, can_write):
    ...

user = get_user(is_open=True)

if has_unread:
    mark_as_read()
```

**Conventions:**

- `is_*` for state: `is_active`, `is_admin`, `is_deleted`
- `has_*` for possession: `has_children`, `has_permission`
- `should_*` for action: `should_retry`, `should_notify`
- `can_*` for capability: `can_edit`, `can_delete`
- `*_enabled` or `is_*` for flags: `notifications_enabled` or `is_notifications_enabled`

---

### 5. Keep Code DRY (Don't Repeat Yourself)

Duplicate code means duplicate bugs. When you fix the bug in one place, you forget to fix it in the other.

```python
# BAD: same calculation in three places
def calculate_price_a(items):
    total = sum(item.price for item in items)
    tax = total * 0.08
    return total + tax

def calculate_price_b(items):
    total = sum(item.price for item in items)
    tax = total * 0.08
    shipping = 5.99 if total < 50 else 0
    return total + tax + shipping

def calculate_price_c(items):
    total = sum(item.price for item in items)
    tax = total * 0.08
    discount = 0.1 if total > 100 else 0
    return (total + tax) * (1 - discount)
```

```python
# GOOD: one function for the shared logic
def price_with_tax(items):
    total = sum(item.price for item in items)
    tax = total * TAX_RATE
    return total + tax

def calculate_price_a(items):
    return price_with_tax(items)

def calculate_price_b(items):
    return price_with_tax(items) + shipping_cost(items)

def calculate_price_c(items):
    return price_with_tax(items) * discount_factor(items)
```

**When NOT to DRY:** two pieces of code that look similar but represent different concepts. Forcing them into one abstraction couples unrelated logic. Rule of three: extract a shared abstraction when you see the pattern three times.

---

### 6. Avoid Deep Nesting

Deep nesting makes code hard to read because the reader must hold the entire context stack in their head.

```python
# BAD: nested 5 levels deep
def process_order(order, user, inventory):
    if order.is_valid():
        if user.is_authenticated():
            if inventory.has_stock(order.items):
                if payment.can_charge(user, order.total):
                    if not order.is_flagged():
                        order.fulfill()
                        return {"success": True}
                    else:
                        return {"error": "flagged"}
                else:
                    return {"error": "payment failed"}
            else:
                return {"error": "out of stock"}
        else:
            return {"error": "unauthenticated"}
    else:
        return {"error": "invalid order"}
```

```python
# GOOD: early returns flatten the code
def process_order(order, user, inventory):
    if not order.is_valid():
        return {"error": "invalid order"}
    if not user.is_authenticated():
        return {"error": "unauthenticated"}
    if not inventory.has_stock(order.items):
        return {"error": "out of stock"}
    if not payment.can_charge(user, order.total):
        return {"error": "payment failed"}
    if order.is_flagged():
        return {"error": "flagged"}

    order.fulfill()
    return {"success": True}
```

**Heuristic:** more than 3 levels of nesting is a code smell. Refactor with early returns, extract helper functions, or use guard clauses.

---

### 7. Comment Why, Not What

Comments should explain intent and trade-offs, not mechanics that the code already shows.

```python
# BAD: comment describes what the code obviously does
i = i + 1  # increment i by 1

return user  # return the user

# GOOD: comment explains why
# Use case-insensitive comparison because legacy users may have mixed-case emails
if email.lower() == stored_email.lower():
    ...

# We retry up to 3 times because the upstream API occasionally returns 503
# under load. Beyond that, surface the error to the caller.
for attempt in range(3):
    ...

# TODO: Replace this workaround once the upstream fixes their timezone bug
# (tracked in JIRA-1234)
user.created_at = user.created_at.replace(tzinfo=timezone.utc)
```

**Good comments:**

- Explain *why* this approach was chosen
- Document non-obvious constraints or invariants
- Reference tickets, papers, or external context
- Warn about edge cases or known issues

**Bad comments:**

- Describe what the code does (`# increment i`)
- Restate the function name
- Get out of date (worse than no comment)

The best code needs few comments because the code itself reads like a story.

---

### 8. Limit Function Arguments

Functions with many parameters are hard to call correctly. Group related data into objects.

```python
# BAD: 6 positional arguments, easy to mix up
def create_user(name, email, age, country, plan, is_admin):
    ...

create_user("Alice", "alice@example.com", 30, "US", "premium", True)
# Which position is "premium"? Which is True?
```

```python
# GOOD: a single options object
@dataclass
class UserSpec:
    name: str
    email: str
    age: int
    country: str
    plan: str
    is_admin: bool

def create_user(spec: UserSpec):
    ...

create_user(UserSpec(
    name="Alice",
    email="alice@example.com",
    age=30,
    country="US",
    plan="premium",
    is_admin=True,
))
```

**Heuristic:**

- 0–2 arguments: ideal
- 3 arguments: fine
- 4 arguments: smell; consider grouping
- 5+ arguments: definite smell; refactor

Exceptions: functions that take (self, *args) by design, or that pass through to another function.

---

### 9. Code Should Be Self-Explanatory

The best code reads like a story. If you need a comment to explain what the code does, the code can usually be rewritten to be clearer.

```python
# BAD: cryptic + needs a comment
# Get the active user's cart items after applying regional discounts
items = [i for i in c.items if i.status == 1 and (r := get_r(i.region)) and i.price * (1 - r) > 0]
```

```python
# GOOD: the code reads like the comment
def get_discounted_active_items(user, region):
    return [
        item for item in user.cart.items
        if item.is_active
        and discount_for(item.region) > 0
    ]
```

**Techniques:**

- Replace magic numbers with named constants
- Extract sub-expressions into helper functions
- Use guard clauses instead of nested conditionals
- Name intermediate variables instead of chaining operations
- Use data classes or named tuples for related fields

**Rule of thumb:** if you find yourself writing a comment to explain what a line does, rewrite the line so the comment is unnecessary.

---

## Build It / In Depth

### Refactoring a function, step by step

Starting from a poorly written function:

```python
def proc(u, t):
    # Validate user
    if not u or not u.get('email') or '@' not in u['email']:
        return None
    # Get items
    items = db.query("SELECT * FROM items WHERE user_id = %s" % u['id'])
    # Calculate total
    total = 0
    for i in items:
        if i['status'] == 1:
            price = i['price']
            if i.get('discount'):
                price = price * (1 - i['discount'] / 100)
            total = total + price
    # Apply tax
    total = total * 1.08
    # Save transaction
    db.execute("INSERT INTO transactions (user_id, amount, type, created_at) VALUES (%s, %s, %s, NOW())" % (u['id'], total, t))
    return total
```

**Step 1: Better names.**

```python
def process_transaction(user, transaction_type):
    if not is_valid_user(user):
        return None
    ...
```

**Step 2: Extract helpers.**

```python
def is_valid_user(user):
    return user and user.get('email') and '@' in user['email']

def get_user_items(user_id):
    return db.query("SELECT * FROM items WHERE user_id = %s", user_id)

def calculate_item_price(item):
    if item['status'] != 1:
        return 0
    discount = item.get('discount', 0)
    return item['price'] * (1 - discount / 100)
```

**Step 3: Compose.**

```python
TAX_RATE = 0.08

def process_transaction(user, transaction_type):
    if not is_valid_user(user):
        return None

    items = get_user_items(user['id'])
    subtotal = sum(calculate_item_price(item) for item in items)
    total_with_tax = subtotal * (1 + TAX_RATE)

    save_transaction(user['id'], total_with_tax, transaction_type)
    return total_with_tax
```

The result reads like a story: validate, get items, sum, apply tax, save. No comments needed because the names explain the intent.

---

### The principles in code review

When reviewing code, watch for these red flags:

```
   ❌ Function > 30 lines
   ❌ Function > 3 arguments
   ❌ Nested conditionals > 3 levels
   ❌ Magic numbers (numeric literals that aren't 0, 1, or -1)
   ❌ Comments explaining what (vs why)
   ❌ Names that require a comment to explain
   ❌ Duplicated logic across functions
   ❌ Boolean variables named after their value (flag, status, mode)
```

Most of these are caught by a thoughtful review; tools like linters catch the rest.

---

## Use It

### Tools that enforce clean code

| Tool | What it checks |
|---|---|
| **Linters** (pylint, eslint, rubocop) | Style, naming, complexity |
| **Formatters** (black, prettier, gofmt) | Consistent formatting |
| **Type checkers** (mypy, TypeScript) | Type correctness |
| **Complexity analyzers** (radon, SonarQube) | Cyclomatic complexity, deep nesting |
| **Pre-commit hooks** | Run checks before code is committed |

### When to break the rules

Rules are defaults, not laws. Breaking them deliberately is fine; breaking them by accident is not.

| Rule | When to break |
|---|---|
| DRY | Two pieces of code that look similar but represent different concepts |
| Short functions | Algorithms that are inherently sequential and clearer as one block |
| Few arguments | Wrappers that pass through to other functions |
| Self-explanatory code | Domain-specific terminology that has no plain-English equivalent |

---

## Common Pitfalls

- **Naming as decoration.** Renaming variables to be longer does not make code cleaner if the names are still meaningless. `user_data` is not better than `u` if it just means "the user data."

- **DRY without abstraction.** Forcing three similar code blocks into one shared function can produce a worse design than three separate functions. Wait for the abstraction to emerge naturally.

- **Over-commenting obvious code.** Comments that restate what the code does are noise. They get out of date and become lies.

- **Short functions at the cost of readability.** Breaking every 5-line block into a function named `step1`, `step2`, `step3` makes code harder to follow, not easier.

- **Naming everything `data`, `value`, `result`.** These are placeholders, not names. If you cannot find a real name, you probably do not understand the data yet.

- **Ignoring team conventions.** Personal style preferences can be set aside for the team. Argue about the rules once; then follow them.

---

## Exercises

1. **Easy** — Pick three principles. For each, give a concrete example (from your code or invented) of code that violates the principle, and show the fix.

2. **Medium** — Take a function you have written that is longer than 30 lines. Refactor it using the principles above: extract helpers, rename, remove magic numbers, replace nested conditionals with guard clauses. Compare before and after.

3. **Hard** — Audit a real codebase (yours or an open-source one). For each of the nine principles, find one example of a violation and one example of good practice. Present the findings as a code review.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Clean code | Style preferences | A set of principles for writing code that minimizes cognitive load on the reader; primarily about intent and structure, not formatting |
| DRY | No duplicated code | Don't Repeat Yourself — every piece of logic should have a single source of truth; but two similar-looking code blocks are not automatically duplication |
| Magic number | A bad number | A numeric literal whose meaning is not obvious from context; replace with named constants |
| Self-documenting code | Code without comments | Code whose names and structure make comments unnecessary; comments are still useful for explaining *why*, not *what* |
| Single responsibility | One function per file | Each function or class should have one reason to change; a function doing multiple things is harder to test and refactor |
| Cyclomatic complexity | A number | A measure of the number of independent paths through code; lower is simpler; high values (>10) suggest the function should be split |
| Guard clause | A defensive check | An early return that handles an edge case before the main logic; flattens nesting |
| Code review | A check for bugs | The discipline of having another engineer read your code before it merges; catches naming, structure, and clarity issues that automated tools miss |

---

## Further Reading

- **"Clean Code"** — Robert C. Martin's book; the source of most of these principles: https://www.oreilly.com/library/view/clean-code-a/9780136083238/
- **"The Pragmatic Programmer"** — Hunt and Thomas; timeless advice on writing maintainable code: https://pragprog.com/titles/tpp20/the-pragmatic-programmer-20th-anniversary-edition/
- **"Refactoring"** — Martin Fowler's catalog of code transformations: https://martinfowler.com/books/refactoring.html
- **"A Philosophy of Software Design"** — John Ousterhout's shorter, opinionated take: https://web.stanford.edu/~ouster/cgi-bin/book.php
- **Google Engineering Practices — Code Review Guide** — what good review comments look like: https://google.github.io/eng-practices/review/