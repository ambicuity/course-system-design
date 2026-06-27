# What are some of the most popular versioning strategies?

> Version numbers are a contract: they tell consumers exactly how much risk they're absorbing when they upgrade.

**Type:** Learn
**Prerequisites:** API Design Fundamentals, Dependency Management, Release Engineering
**Time:** ~25 minutes

---

## The Problem

Imagine you maintain a payment library used by forty internal services. You push a fix that renames a required field in the request object. Three teams upgrade immediately, their CI pipelines pass because they never tested the renamed field path, and then production breaks at 2 AM on a Friday. No one expected a "bug fix" release to introduce a breaking change — because you gave it the same version bump as a typo correction.

The inverse is equally painful. Your team exposes a REST API consumed by mobile clients you cannot force-update. You need to evolve the API — add required fields, remove deprecated endpoints, restructure response shapes. Without a versioning contract, every change is a gamble: you either freeze the API in amber forever or silently break the apps sitting on users' phones.

Versioning strategies are the answer to both problems. They impose a shared vocabulary for "how much did this change?" so that producers and consumers can negotiate upgrades with confidence. Picking the wrong strategy — or applying the right one inconsistently — erases that guarantee and recreates the chaos you were trying to prevent.

---

## The Concept

### Semantic Versioning (SemVer)

The most widely adopted scheme for software libraries and CLIs. A SemVer version has three numeric components:

```
MAJOR . MINOR . PATCH
  2   .   4   .  11
```

| Component | Increment when… | Example trigger |
|-----------|-----------------|-----------------|
| **MAJOR** | You break backwards compatibility | Rename or remove a public function, change a required argument's type |
| **MINOR** | You add functionality in a backwards-compatible way | New optional parameter, new public method |
| **PATCH** | You make a backwards-compatible bug fix | Fix an off-by-one error, correct a wrong HTTP status code |

SemVer also defines pre-release identifiers and build metadata:

```
2.4.11-rc.1+build.2847
       ^^^^  ^^^^^^^^^^
       pre-  build metadata (ignored in precedence)
       release
```

Pre-release labels follow alphabetical precedence: `alpha < beta < rc < (release)`.

**The SemVer promise:** A consumer who pins to `^2.4.0` (meaning "compatible with 2.4.0") knows they will never automatically receive a version with a changed MAJOR number. Package managers like npm and Cargo enforce this contract at the dependency-resolution layer.

**When SemVer works best:** Open-source libraries, internal SDKs, CLI tools, anything where the consumer controls when they upgrade.

**Where SemVer breaks down:** Products and services where "the product" itself doesn't have a clean notion of a public API surface. Ubuntu doesn't have a "public API" you can pin to in the same way a Go module does.

---

### Calendar Versioning (CalVer)

CalVer derives the version from the release date rather than from the semantics of the change. The most common formats:

| Format | Example | Who uses it |
|--------|---------|-------------|
| `YY.MM` | `22.04`, `24.10` | Ubuntu LTS releases |
| `YYYY.MM.DD` | `2024.03.15` | pip (Python package manager) |
| `YYYY.N` | `2024.1`, `2024.2` | Some enterprise products |
| `YY.MM.MICRO` | `22.04.3` | Ubuntu point releases |

The date communicates **when** — and implicitly **how old** — a release is. For operating systems and long-lived platforms this matters more than "was this change backwards-compatible?" A system administrator looking at Ubuntu `20.04` immediately knows it's an April 2020 release and can reason about end-of-life timelines without looking anything up.

**When CalVer works best:** Operating systems, firmware, products with time-boxed release cycles, anything where release cadence is as meaningful as change scope.

**Where CalVer breaks down:** Libraries consumed programmatically. Downstream tooling that pins `>=22.04` can't know whether the jump to `24.04` introduced breaking changes without reading a changelog.

---

### Sequential / Monotonic Versioning

A simple incrementing integer: `v1`, `v2`, `v3` — or just `1`, `2`, `3`. Used widely for:

- Internal build numbers (Jenkins build #4821)
- Database schema migrations (migration `0042_add_user_roles`)
- Terraform state serial numbers
- Kafka consumer group offsets

No semantic meaning is encoded beyond "later is newer." The advantage is simplicity and unambiguity — there is never a debate about whether a change is MINOR or MAJOR. The disadvantage is that consumers receive no signal about the scope of change.

---

### API Versioning Strategies

REST APIs face a distinct challenge: you can't force clients to upgrade. The four common approaches each make different trade-offs.

```
┌─────────────────────────────────────────────────────────────────┐
│                    API Versioning Approaches                      │
├────────────────────┬────────────────────────────────────────────┤
│ URL Path           │  GET /v1/users  →  GET /v2/users           │
├────────────────────┼────────────────────────────────────────────┤
│ Query Parameter    │  GET /users?version=2                       │
├────────────────────┼────────────────────────────────────────────┤
│ Custom Header      │  X-API-Version: 2                           │
├────────────────────┼────────────────────────────────────────────┤
│ Accept Header      │  Accept: application/vnd.myapi.v2+json      │
└────────────────────┴────────────────────────────────────────────┘
```

**URL Path versioning** is the most explicit and the most common in public APIs (Stripe, Twilio, GitHub). The version appears in the URL itself, making it visible in logs, caches, and CDN rules. The cost: you must maintain and route multiple URL trees in parallel, and moving clients between versions requires changing their URLs.

**Query parameter versioning** (`?api_version=2019-01-01`) is the approach Stripe uses for their date-based API versions. It keeps the base URL stable and lets you audit which clients are on which version from a single log stream. Caching is more complex because query params are part of the cache key.

**Custom header versioning** (`X-API-Version: 2`) keeps the URL entirely clean and is easy to route at the API gateway layer. The version is invisible to CDN caches by default and can be harder to test with simple curl commands.

**Accept header versioning** (`Accept: application/vnd.api+json;version=2`) is the most RESTful in a theoretical sense — content negotiation is what the Accept header is designed for. In practice, almost no major API does this because it's opaque in logs and confusing for developers to discover.

---

### Comparing All Strategies

```
Strategy         │ Encodes change scope? │ Human-readable date? │ Suits libraries? │ Suits APIs?
─────────────────┼───────────────────────┼──────────────────────┼──────────────────┼────────────
SemVer           │ Yes                   │ No                   │ Excellent        │ Good
CalVer           │ No                    │ Yes                  │ Poor             │ Moderate
Sequential       │ No                    │ No                   │ Poor             │ Moderate
URL Path         │ Coarse (v1/v2)        │ No                   │ N/A              │ Excellent
Query Param      │ Coarse or date        │ If date-based        │ N/A              │ Good
Header-based     │ Coarse                │ No                   │ N/A              │ Moderate
```

---

## Build It / In Depth

### Applying SemVer to a real change log

Suppose you maintain `payments-sdk` at version `1.3.2`. Walk through a backlog of changes and decide the correct next version for each:

**Change A:** Fix a crash when the currency code is `null`.
- This is a backwards-compatible bug fix.
- Bump: `PATCH` → `1.3.3`

**Change B:** Add an optional `idempotency_key` field to the charge request.
- New capability, old clients still work without it.
- Bump: `MINOR` → `1.4.0` (reset PATCH to 0)

**Change C:** Rename `charge()` to `createCharge()` to match the new API naming convention.
- Existing callers will get a `NoSuchMethodError` — this is a breaking change.
- Bump: `MAJOR` → `2.0.0` (reset MINOR and PATCH to 0)

**Pre-release sequence for Change C:**

```
2.0.0-alpha.1   ← internal testing
2.0.0-beta.1    ← partner preview
2.0.0-rc.1      ← final validation
2.0.0           ← general availability
```

---

### Designing a REST API versioning policy

A concrete decision procedure for a new public API:

```
1. Choose URL path versioning for a public API.
   - Simple to discover, simple to route, simple to deprecate.
   - Use /v1/, /v2/, /v3/

2. Version only at breaking-change boundaries.
   - Adding new optional fields → no new version
   - Removing fields or changing types → bump to /v2/

3. Run both versions in parallel during a migration window.
   - Announce deprecation of /v1/ with a sunset date in the response header:
     Deprecation: true
     Sunset: Sat, 01 Jun 2025 00:00:00 GMT
     Link: <https://api.example.com/v2/docs>; rel="successor-version"

4. Track per-version traffic in your API gateway.
   - Sunset /v1/ only when traffic drops below 1%.
```

**Nginx routing snippet for parallel versions:**

```nginx
location /v1/ {
    proxy_pass http://api-v1-service/;
}

location /v2/ {
    proxy_pass http://api-v2-service/;
}
```

**Response headers for deprecation signaling (Express.js):**

```javascript
// Middleware applied only to v1 routes
function deprecationHeaders(req, res, next) {
  res.set('Deprecation', 'true');
  res.set('Sunset', 'Sat, 01 Jun 2025 00:00:00 GMT');
  res.set('Link', '<https://api.example.com/v2/docs>; rel="successor-version"');
  next();
}
app.use('/v1', deprecationHeaders, v1Router);
```

---

### Database migration versioning

Sequential versioning is the right fit here. Each migration file gets a monotonically increasing prefix:

```
migrations/
├── 0001_create_users_table.sql
├── 0002_add_email_index.sql
├── 0003_add_roles_table.sql
└── 0042_add_user_roles_join_table.sql
```

The migration runner records the highest applied migration number in a `schema_migrations` table and runs only files with a higher number on the next deployment. The sequence is the contract; the content is the change.

---

## Use It

| Technology | Versioning Approach | Notes |
|------------|--------------------|----|
| **npm / Cargo / PyPI packages** | SemVer | Package managers enforce the MAJOR compat constraint via `^` and `~` ranges |
| **Ubuntu / Linux Mint** | CalVer (YY.MM) | LTS releases on `.04`, interim on `.10` |
| **Stripe API** | Date-based CalVer query param (`?api_version=2024-04-10`) | Freezes the API shape for each client at the version they enrolled with |
| **GitHub REST API** | URL path (`/v3/`) + preview header for beta features | Stable surface stays at `/v3/`; new features gated by `Accept` header previews |
| **Kubernetes** | `apiVersion: apps/v1` in manifests | Resource API group + version encoded in YAML; multiple versions coexist until a version is removed |
| **Terraform providers** | SemVer | `required_providers` block pins to a version constraint exactly like a library |
| **PostgreSQL / Flyway migrations** | Sequential (`V1__`, `V2__`) | Files are hashed and tracked; out-of-order detection throws an error |
| **GraphQL** | No versioning (field deprecation instead) | `@deprecated` directive signals clients; fields are never removed immediately |

GraphQL's approach deserves a note: because clients request exactly the fields they need, you can add new fields and deprecate old ones without a version bump. Removal is a breaking change and requires a coordinated migration, but you have fine-grained visibility into which clients still use which fields via query analytics.

---

## Common Pitfalls

- **Treating every release as a PATCH.** Teams under release pressure bump only PATCH to downplay the scope of a change. Consumers who upgrade trusting the SemVer contract then hit breaking changes. Be honest: if callers must change their code, it's MAJOR.

- **Bumping MAJOR for internal implementation changes.** If you refactor a private method, change a data structure that is not part of the public API, or improve performance — that is PATCH at most. MAJOR is for the public contract, not the internals.

- **Versioning every endpoint separately.** Some teams create `/v2/users` but leave `/payments` at v1. This creates a patchwork that is harder to document, route, and reason about than a single version namespace for the whole API surface.

- **No sunset dates on deprecated versions.** Announcing "v1 is deprecated" without a firm sunset date means clients never migrate. Set a date, communicate it via response headers, and enforce it. Traffic graphs are your source of truth — sunset when usage is negligible, not on a calendar.

- **Choosing CalVer for a library.** If you publish a library on npm and version it `24.06`, downstream tooling cannot apply `^` semantics because there is no meaningful MAJOR boundary. Developers can't know if `24.06` to `24.07` is safe to upgrade. Use SemVer for anything consumed as a dependency.

---

## Exercises

1. **Easy — Version bump identification.** You are at `3.1.5`. Classify each change and determine the next version number:
   - (a) Fix a typo in an error message string.
   - (b) Add a new optional `timeout` parameter to `connect()`.
   - (c) Remove the deprecated `connect_legacy()` function.

2. **Medium — API versioning design.** You run a public REST API at `/v1/`. Product wants to change the `GET /v1/orders` response from returning a flat list to returning a paginated object: `{ "orders": [...], "cursor": "..." }`. Design a versioning and migration plan. Which versioning approach do you use, how do you run both versions in parallel, and what sunset policy do you apply?

3. **Hard — Multi-consumer migration.** Your team maintains an internal gRPC service (proto-based) used by twelve downstream teams. You need to rename a required field in the most-used RPC's request message — a breaking Protobuf change. Design a zero-downtime migration strategy that does not require all twelve consumers to upgrade simultaneously. Consider the role of field numbers, the optional vs. required distinction, and how you communicate state to each consuming team.

---

## Key Terms

| Term | What people think | What it actually means |
|------|------------------|------------------------|
| **SemVer** | "Increment a number when you release" | A three-part contract (`MAJOR.MINOR.PATCH`) where each segment encodes a specific scope of change; the MAJOR boundary is a binary compatibility promise |
| **Breaking change** | "Anything that modifies existing behavior" | Specifically: any change that requires callers to update their code to keep working. Internal refactors and new optional features are not breaking changes. |
| **Deprecation** | "We removed it" | The opposite — a promise that the feature still works *now* but will be removed at a stated future date, giving consumers time to migrate |
| **CalVer** | "Just use the date as the version" | A versioning scheme where the date *is* the version, chosen deliberately because release cadence communicates more than change scope for that product |
| **Pre-release identifier** | "A label before the final version" | A version suffix (`-alpha.1`, `-rc.2`) that signals instability; SemVer specifies that pre-releases have *lower* precedence than the release they prefix |
| **Sunset header** | "A warning that something is going away" | A standardized HTTP response header (`Sunset: <HTTP-date>`) that tells API clients the exact date an endpoint or version will stop responding |
| **API version negotiation** | "Clients pick which version they want" | A scheme — usually via Accept headers — where the server selects the response format based on what the client declares it can handle; rarely used in practice |

---

## Further Reading

- [Semantic Versioning 2.0.0 specification](https://semver.org/) — The canonical SemVer spec; short, precise, and authoritative.
- [Calendar Versioning](https://calver.org/) — Overview of CalVer conventions with real-world examples and a format reference.
- [RFC 8594 — The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594) — The IETF standard for communicating API deprecation timelines via response headers.
- [Stripe API versioning blog post](https://stripe.com/blog/api-versioning) — How Stripe freezes the API shape per client using date-based versions and what they learned running that system for a decade.
- [Kubernetes API versioning design](https://kubernetes.io/docs/reference/using-api/#api-versioning) — How Kubernetes manages alpha, beta, and stable API groups, and the deprecation policy that governs them.
