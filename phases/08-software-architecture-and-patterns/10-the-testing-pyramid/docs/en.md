# The Testing Pyramid

> A shape for your test suite that maximizes signal and minimizes cost — most tests at the bottom, fewest at the top, with clear responsibilities at each layer.

**Type:** Learn
**Prerequisites:** Basic software testing
**Time:** ~20 minutes

---

## The Problem

Every team needs tests, but most teams have the *wrong mix*. Two common failure modes:

1. **The ice-cream cone** — mostly end-to-end tests, a few integration tests, almost no unit tests. Every change triggers a fragile test suite; CI takes hours; debugging failures is guesswork.
2. **The hourglass** — heavy unit tests, almost no integration tests, lots of E2E. Individual pieces work in isolation, but the system as a whole is never tested; bugs slip through at component boundaries.

The **Testing Pyramid** is the shape that has emerged from decades of practice as the right balance. Many tests at the bottom (fast, cheap, focused), fewer at the middle (slower, more realistic), fewest at the top (slowest, most realistic, most expensive).

This lesson walks through the three layers, what each is for, what it costs, and how to apply the pyramid to a real codebase.

---

## The Concept

### The pyramid

```
                        ╱╲
                       ╱  ╲             E2E Tests
                      ╱ few ╲            - Slow, expensive, brittle
                     ╱────────╲           - Full system, real users
                    ╱          ╲        - Last line of defense
                   ╱Integration ╲
                  ╱   Tests     ╲      Integration Tests
                 ╱  moderate      ╲      - Verify component interactions
                ╱──────────────────╲    - Database, API, services
               ╱                    ╲
              ╱     Unit Tests       ╲   Unit Tests
             ╱       many, fast        ╲  - Verify functions/classes in isolation
            ╱                          ╲ - Fast feedback, easy to debug
           ╱____________________________╲
```

Three layers, each with different cost, speed, and purpose.

| Layer | Count | Speed | Cost to write | Cost to maintain | What it tests |
|---|---|---|---|---|---|
| Unit | Many (thousands) | Milliseconds | Low | Low | Individual functions, classes |
| Integration | Moderate (hundreds) | Seconds | Medium | Medium | Component interactions, APIs, DB |
| E2E | Few (dozens) | Seconds to minutes | High | High | Full user flows |

The pyramid is a *shape*, not a number. The exact ratio depends on the codebase, but the principle holds: more tests at the bottom, fewer at the top.

---

### Layer 1: Unit Tests (the foundation)

A unit test exercises a single piece of behavior in isolation. "Unit" usually means a function or a class, but the principle is the same: test one thing, with no dependencies on other systems.

```python
# A simple unit test
def test_apply_discount_reduces_price_by_percentage():
    cart = Cart(items=[Item(price=100)])
    cart.apply_discount(percent=20)
    assert cart.total == 80

def test_apply_discount_with_zero_percent_keeps_price():
    cart = Cart(items=[Item(price=100)])
    cart.apply_discount(percent=0)
    assert cart.total == 100

def test_apply_discount_with_negative_percent_raises():
    cart = Cart(items=[Item(price=100)])
    with pytest.raises(ValueError):
        cart.apply_discount(percent=-5)
```

**Properties:**

- **Fast.** Milliseconds. The entire test suite runs in seconds.
- **Isolated.** No database, no network, no filesystem. Just code.
- **Focused.** One test verifies one behavior. Failures point to a specific function.
- **Easy to write.** No setup, no teardown, no mocks (usually).
- **Deterministic.** The same input always produces the same output.

**What to unit-test:**

- Business logic (pricing, validation, state transitions)
- Pure functions (data transformations, calculations)
- Edge cases and error paths
- Boundary conditions (empty inputs, large inputs, null)

**When you should not unit-test:**

- Code that just delegates to a library (testing `db.save()` calls the database library's code, not yours)
- Trivial getters and setters
- Configuration loading (test it once at the integration layer)

---

### Layer 2: Integration Tests (the middle)

An integration test verifies that multiple components work together correctly. The components can be your code (services, repositories) or external systems (databases, message queues, third-party APIs).

```python
# An integration test
def test_create_user_persists_to_database(test_db):
    repo = UserRepository(test_db)

    user = repo.create(email="alice@example.com", name="Alice")

    found = repo.find_by_id(user.id)
    assert found.email == "alice@example.com"

def test_create_user_emits_user_created_event(test_db, test_bus):
    repo = UserRepository(test_db, event_bus=test_bus)

    user = repo.create(email="alice@example.com", name="Alice")

    assert test_bus.published == [UserCreatedEvent(user_id=user.id)]
```

**Properties:**

- **Slower than unit tests.** Each test sets up real components (in-memory database, test broker, mock HTTP server).
- **More realistic.** Tests how your code actually behaves with real dependencies.
- **More brittle.** Database schema changes break tests; third-party API changes break tests.
- **More valuable for interfaces.** Tests that your repository talks to the database correctly, that your service emits the right events.

**What to integration-test:**

- Database access (repositories, migrations)
- Service-to-service API calls
- Event publishing and consumption
- Authentication and authorization flows
- Caching behavior (with a real or in-memory cache)
- File I/O

**Test isolation patterns:**

- **Test database per test** — slow but isolated
- **Transactional rollback** — wrap each test in a transaction; rollback at the end
- **Truncate-tables-between-tests** — fast, simple
- **Test containers** — spin up real databases/queues in Docker

---

### Layer 3: E2E Tests (the top)

An end-to-end test simulates a real user flow through the entire system: UI, API, database, third-party services. It is the only test that verifies the whole system works together.

```python
# A Playwright E2E test
def test_user_can_sign_up_and_see_dashboard(page):
    page.goto("https://app.example.com/signup")
    page.fill("input[name=email]", "alice@example.com")
    page.fill("input[name=password]", "correct horse battery staple")
    page.click("button[type=submit]")

    # Now we should be on the dashboard
    expect(page).to_have_url("https://app.example.com/dashboard")
    expect(page.locator("h1")).to_contain_text("Welcome, alice@example.com")
```

**Properties:**

- **Slow.** Seconds to minutes per test.
- **Expensive.** Requires the full system running, plus a browser or API client.
- **Brittle.** UI changes break tests; flaky network conditions cause false failures.
- **Most realistic.** This is the closest test to what real users do.
- **Last line of defense.** Catches the bugs that unit and integration tests miss.

**What to E2E-test:**

- Critical user journeys (signup, checkout, primary workflow)
- Cross-service workflows that cannot be verified at lower levels
- Authentication and session management
- Anything with significant business value where a regression would be catastrophic

**How many E2E tests to have:**

The classic answer: a handful of the most critical paths. Not every page; not every feature. E2E tests are expensive and slow. If you have hundreds, you have an ice-cream cone.

**Tools:**

- **Playwright** (preferred) — fast, reliable, multi-browser
- **Cypress** — popular for web apps
- **Selenium** — the classic, more verbose
- **k6 / Gatling** — for API load testing
- **Postman / Newman** — for API E2E without a browser

---

### The cost of each layer

```
   Unit test:
     Time to write: 5–15 minutes
     Time to run: <100ms
     Time to debug on failure: minutes
     Maintenance cost: low

   Integration test:
     Time to write: 30–90 minutes
     Time to run: 1–10 seconds
     Time to debug on failure: tens of minutes
     Maintenance cost: medium

   E2E test:
     Time to write: 1–4 hours
     Time to run: 30 seconds – several minutes
     Time to debug on failure: hours
     Maintenance cost: high
```

A 1000-test unit suite runs in seconds. A 100-test integration suite runs in minutes. A 50-test E2E suite runs in an hour. Pick the ratio that matches your team's iteration speed.

---

### What goes wrong when the pyramid is inverted

**Ice-cream cone (mostly E2E):**

```
                        ╱╲
                       ╱  ╲            ← Hundreds of E2E tests
                      ╱ E2E ╲
                     ╱────────╲           Few integration tests
                    ╱          ╲
                   ╱ Integration ╲
                  ╱   Tests     ╲
                 ╱────────────────╲
                ╱                  ╲
               ╱   Unit Tests      ╲    ← Almost no unit tests
              ╱______________________╲
```

Symptoms:

- CI takes hours
- Developers stop running tests locally before pushing
- Flaky tests cause "rerun until green" culture
- Bugs slip through because no one can run the full suite
- Refactoring is impossible because changing one thing breaks dozens of E2E tests

**Hourglass (lots of unit, lots of E2E, no integration):**

```
                        ╱╲
                       ╱  ╲
                      ╱ E2E ╲            Many E2E tests
                     ╱────────╲
                    ╱          ╲
                   ╱            ╲        Few integration tests
                  ╱              ╲        ← The "narrow waist"
                 ╱────────────────╲
               ╱                  ╲
              ╱   Unit Tests      ╲    Many unit tests
             ╱______________________╲
```

Symptoms:

- Individual classes work in isolation
- Components fail when wired together (database schema mismatch, API contract mismatch, event format mismatch)
- E2E tests catch the integration bugs that nothing else did
- Tests pass but production fails

**The right shape:** a true pyramid with broad unit base, narrower integration, narrow E2E top.

---

## Build It / In Depth

### A test plan for a real feature

Suppose you are building a "user can reset their password" feature. Here is the right way to allocate tests:

```
   Unit tests (~15):
     - Password validation (strong password rules)
     - Token generation (secure random, no collisions)
     - Token expiry calculation
     - Password hashing and verification
     - Email template formatting (if templated in code)

   Integration tests (~5):
     - Password reset request writes token to DB
     - Reset with valid token updates password
     - Reset with expired token fails
     - Reset with used token fails
     - Reset event is published to the event bus

   E2E tests (~1):
     - User requests reset → receives email → clicks link → enters new password → can log in
```

15 unit tests run in milliseconds. 5 integration tests run in seconds. 1 E2E test runs in tens of seconds. The pyramid is intact: broad base, narrow top.

---

### Test naming conventions

Good test names tell you what is being tested without reading the test body.

**Three common patterns:**

1. **`test_<unit>_<scenario>_<expected>`**
   - `test_apply_discount_with_negative_percent_raises`
   - `test_user_creation_with_duplicate_email_returns_409`

2. **`should_<expected>_when_<condition>`**
   - `should_reject_negative_discount`
   - `should_return_409_when_email_already_exists`

3. **`given_<precondition>_when_<action>_then_<outcome>`** (BDD style)
   - `given_a_user_with_a_pending_reset, when_they_submit_a_new_password, then_they_can_log_in`

Pick one convention for the project. Consistency makes the test suite readable.

---

### What to test at each layer

| Bug type | Best layer to catch it |
|---|---|
| Off-by-one error in a calculation | Unit |
| Wrong password validation rule | Unit |
| SQL query has a bug | Integration |
| Database migration lost data | Integration |
| API endpoint returns wrong status code | Integration |
| Two services disagree on event format | Integration |
| Login form does not submit | E2E |
| OAuth flow breaks after provider change | E2E |
| Production-only environment bug (config, secrets) | E2E |

Different bugs live at different layers. The pyramid ensures each is caught at the cheapest layer that can catch it.

---

### Mocking and test doubles

Tests often need to substitute real dependencies with test doubles. Four types:

| Type | What it is | When to use |
|---|---|---|
| **Dummy** | Object passed but never used | Fill parameter lists |
| **Stub** | Object with hardcoded responses | Test the caller's logic |
| **Spy** | Stub that records how it was called | Verify interactions |
| **Mock** | Spy with built-in assertions | Verify expected interactions |

**Mocking guidelines:**

- Mock at the boundary (database, HTTP, third-party APIs), not in the middle of your code.
- Too many mocks means the test is coupled to implementation, not behavior.
- If a unit test needs five mocks, it is not really a unit test — consider it an integration test.

---

### When to break the pyramid

The pyramid is a default, not a law.

| Situation | Adjustment |
|---|---|
| Frontend-heavy app | More component tests, more E2E (UI is hard to test in isolation) |
| Backend-heavy distributed system | More integration tests, contract tests between services |
| Library / SDK | Heavy on unit tests, fewer integration (the consumer does the integration testing) |
| ML model | More data quality tests, fewer pure unit tests (the model is the unit) |
| Embedded / hardware | Heavy on hardware-in-the-loop (similar to E2E) |

---

## Use It

### Quick decision guide

| When you find yourself… | Consider… |
|---|---|
| Testing a single function's logic | Unit test |
| Testing a function with the database | Integration test |
| Testing the API contract | Integration test |
| Testing the database schema and migrations | Integration test |
| Testing what the user sees | E2E test |
| Testing critical user journeys | E2E test |
| Mocking many collaborators | You may be testing the wrong layer |
| Test runs > 10 seconds | It is probably an integration or E2E test |
| Test fails only in CI | Often flaky E2E or environment-specific integration |
| Adding tests to old code | Bring it up to standard incrementally |

### Coverage targets

- **80% line coverage** is a reasonable target. It is not enough on its own (you can have 80% coverage with no real assertions), but it is a useful floor.
- **Branch coverage** is more meaningful than line coverage.
- **Mutation testing** (Stryker, mutmut) catches tests that pass for the wrong reasons — it modifies your code and verifies your tests fail.

---

### Common tools

| Layer | Tools |
|---|---|
| **Unit** | pytest, JUnit, Jest, Go testing, RSpec |
| **Integration** | Testcontainers (Docker-based), pytest with fixtures, JUnit + Spring Test |
| **E2E** | Playwright, Cypress, Selenium |
| **Coverage** | coverage.py, JaCoCo, Istanbul, gcov |
| **Mutation** | Stryker (JS/TS), mutmut (Python), PIT (Java) |

---

## Common Pitfalls

- **Testing implementation, not behavior.** A test that asserts `cart._internal_state == "discounted"` is brittle; a test that asserts `cart.total == 80` is robust. Test what the code does, not how.

- **Too many mocks.** A unit test with five mocks is really an integration test. Either accept that and rename it, or refactor the code to have fewer collaborators.

- **E2E tests for everything.** The CI suite takes four hours. No one runs it locally. It is always red. Bugs slip through anyway. Move tests down the pyramid.

- **Skipping integration tests.** Unit tests pass; production fails. Add the missing layer.

- **Flaky E2E tests.** Marked as "known issue." Eventually ignored. Then no one trusts any E2E result. Fix the flakiness; quarantine tests that cannot be fixed; remove tests that are not worth the maintenance.

- **No test isolation.** Tests pass alone; fail together. Each test must set up and tear down its own state.

- **Coverage as a goal.** 100% coverage does not mean 100% tested. Aim for meaningful tests, not percentage points.

- **Skipping tests on "trivial" code.** The bug is always in the code nobody thought to test.

---

## Exercises

1. **Easy** — Pick a small feature you have built. Design one unit test, one integration test, and one E2E test for it. Explain what each catches that the others would miss.

2. **Medium** — Audit your current test suite (or a sample one). What is the ratio of unit / integration / E2E? Is it pyramid-shaped, ice-cream-cone-shaped, or hourglass-shaped? Identify the most expensive test to maintain and propose a refactor.

3. **Hard** — A team has 2000 unit tests, 20 integration tests, and 500 E2E tests. CI takes 5 hours. The team ships once a week because they cannot run the full suite faster. Design a restructuring plan: what tests to keep at each layer, what to delete, what to refactor, and how to bring CI under 30 minutes.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Unit test | A test | A test that verifies a single function or class in isolation; no external dependencies |
| Integration test | A test | A test that verifies multiple components work together (database, API, message queue) |
| E2E test | A test | A test that verifies a full user flow through the entire system; slow and expensive |
| Testing pyramid | A shape | A distribution where unit tests are most numerous, integration tests fewer, E2E tests fewest |
| Test double | A mock | A stand-in for a real dependency in tests (dummy, stub, spy, or mock) |
| Flaky test | A bad test | A test that sometimes passes and sometimes fails without code changes; usually environmental |
| Coverage | A percentage | The fraction of lines (or branches) executed by the test suite; useful as a floor, not as a goal |
| Contract test | A test | A test that verifies the API contract between two services; catches breaking changes before deployment |

---

## Further Reading

- **"The Practical Test Pyramid"** — Martin Fowler's classic post on the shape and intent: https://martinfowler.com/articles/practical-test-pyramid.html
- **"Testing Strategies in a Microservice Architecture"** — patterns for distributed systems: https://martinfowler.com/articles/microservice-testing/
- **Playwright Documentation** — the modern E2E framework: https://playwright.dev/
- **Testcontainers** — Docker-based integration tests for any language: https://testcontainers.com/
- **"xUnit Test Patterns"** — Gerard Meszaros's encyclopedia of testing patterns: https://xunitpatterns.com/
- **Google Testing Blog** — Google's perspective on testing at scale: https://testing.googleblog.com/