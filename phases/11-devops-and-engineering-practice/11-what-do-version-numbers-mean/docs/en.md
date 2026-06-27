# What do version numbers mean?

> A version number is a promise — break the promise, break your users.

**Type:** Learn
**Prerequisites:** API Design Basics, Dependency Management, Release Pipelines
**Time:** ~20 minutes

---

## The Problem

Imagine you ship a popular HTTP client library. Hundreds of teams depend on it. You fix a bug in how cookies are parsed — tiny change, one line. You bump the version and push. The next morning you wake up to 47 GitHub issues: half your users' apps are failing in production because you silently changed the method signature everyone called most.

Without a shared versioning contract, every release is a gamble. Consumers can't know whether upgrading is safe. Package managers can't automate dependency resolution. CI pipelines can't decide when to auto-update. Teams end up pinning to exact versions forever and never getting security patches, or they auto-upgrade and randomly break.

The same problem appears at the API level. Your mobile app calls `/api/users`. You "improve" the response shape — add a required field, rename a key — and now every client older than two days is broken. Without a version signal in the URL or header, there is no way to run old and new logic side by side.

Version numbers solve one thing: communicating the *nature* of a change, not just the fact that one happened.

---

## The Concept

### Semantic Versioning (SemVer)

The dominant standard is **SemVer**, defined at [semver.org](https://semver.org). A version has three integers separated by dots:

```
MAJOR . MINOR . PATCH
  2   .   4   .   1
```

Each integer encodes a specific promise to consumers:

| Segment | Incremented when… | Backward compatible? |
|---------|-------------------|----------------------|
| **MAJOR** | You make an incompatible API change | No — callers must adapt |
| **MINOR** | You add functionality in a compatible way | Yes — old callers still work |
| **PATCH** | You make a compatible bug fix | Yes — behavior only gets more correct |

Rules that govern incrementing:

- When MAJOR bumps, reset MINOR and PATCH to 0 (`1.9.4` → `2.0.0`).
- When MINOR bumps, reset PATCH to 0 (`1.9.4` → `1.10.0`).
- MAJOR `0` (`0.y.z`) is a special zone: anything may change at any time. The public API is not yet stable.
- Once a version is released, its contents are immutable. If something is wrong, release a new version.

### Version 0.x — Pre-Stability

While a project is still finding its shape, keep MAJOR at 0. This signals to consumers: "We are still designing the API; do not build production systems on this yet." Many open-source projects stay at `0.x` for months or years. `0.1.0` → `0.2.0` may contain breaking changes even though only MINOR bumped — that is explicitly allowed before `1.0.0`.

### Pre-Release Labels

Append a hyphen and dot-separated identifiers to mark non-final builds:

```
1.0.0-alpha
1.0.0-alpha.1
1.0.0-beta
1.0.0-rc.1      ← release candidate 1
1.0.0            ← final stable
```

Pre-release versions have **lower precedence** than the associated normal version: `1.0.0-rc.1 < 1.0.0`.

Identifiers are compared left to right, numerically when both sides are numbers, lexicographically otherwise:

```
1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-alpha.beta < 1.0.0-beta < 1.0.0-beta.2 < 1.0.0-rc.1 < 1.0.0
```

### Build Metadata

Append `+` followed by dot-separated identifiers for build-time information:

```
1.0.0+20240615.sha.a3f9c12
```

Build metadata is **ignored** when determining version precedence — two versions that differ only in build metadata are considered equal for comparison purposes. This is purely informational (CI build number, git SHA, timestamp).

### Version Ranges — How Package Managers Consume SemVer

Consumers rarely pin exact versions in their manifests. They express *ranges*:

| Syntax (npm/cargo style) | Meaning |
|--------------------------|---------|
| `^1.2.3` | `>=1.2.3 <2.0.0` — any compatible MINOR/PATCH |
| `~1.2.3` | `>=1.2.3 <1.3.0` — only compatible PATCH |
| `1.2.3` | Exactly `1.2.3` — no flexibility |
| `>=1.2.0 <2.0.0` | Explicit range |
| `*` | Any version (dangerous in production) |

The caret (`^`) is the most common default in npm. It trusts that the library author honours SemVer — that is, `^1.2.3` will never pull in a `2.x` version that could break you.

### ASCII Diagram — Lifecycle of a Library

```
Initial dev
  0.1.0  →  0.2.0  →  0.3.0          (anything can change)
              |
              ↓
         1.0.0    ← first stable public API
              |
    ┌─────────┼─────────┐
    ↓         ↓         ↓
  1.0.1     1.1.0     2.0.0
 (bug fix) (new feat) (breaking)
    ↓         ↓
  1.0.2     1.1.1
            (bug fix in new feat)
```

Semantic versioning does **not** say anything about:
- The size of the change (a one-liner can be a MAJOR bump)
- The importance of the change (a PATCH can fix a critical security hole)
- Internal implementation details — only the public API contract matters

---

## Build It / In Depth

### Walking a Library Through Its First Year

**Scenario:** You are building `httpkit`, a Python HTTP client library.

#### Step 1 — Initial Development

```
version = "0.1.0"
```

You publish to PyPI. The API is experimental. Users who adopt it now know they are on shifting ground.

#### Step 2 — Bug Fix (PATCH)

A user finds that `httpkit.get()` raises `UnicodeDecodeError` on Latin-1 responses. Fix it:

```
0.1.0 → 0.1.1
```

The fix is internal; callers do not need to change anything.

#### Step 3 — New Feature (MINOR)

You add `httpkit.session()` for connection pooling — a new function, existing code is unaffected:

```
0.1.1 → 0.2.0   (pre-stable, MINOR still gets reset here)
```

#### Step 4 — First Stable Release

After three months of feedback, you commit to the API surface:

```
0.2.0 → 1.0.0
```

Now the SemVer contract is in full force.

#### Step 5 — PATCH Release After Stable

Bug reported: `httpkit.get()` does not follow 301 redirects:

```
1.0.0 → 1.0.1
```

Consumers running `^1.0.0` or `~1.0.0` get this automatically on next install.

#### Step 6 — MINOR Release

You add `httpkit.get(timeout=30)` — a new optional keyword argument. Existing calls without `timeout` still work:

```
1.0.1 → 1.1.0
```

Consumers on `^1.0.0` get this. Consumers on `~1.0.0` do not (tilde only follows PATCH).

#### Step 7 — Breaking Change (MAJOR)

You rename `httpkit.get()` to `httpkit.request('GET', ...)` for consistency. Old callers break:

```
1.1.0 → 2.0.0
```

Consumers on `^1.x.x` are **not** automatically pulled to `2.0.0`. They must opt in explicitly by updating their manifest.

#### Dependency Manifest Example (pyproject.toml)

```toml
[project]
dependencies = [
    "httpkit>=1.1.0,<2.0.0",   # equivalent to ^1.1.0
]
```

Or in a `package.json`:

```json
{
  "dependencies": {
    "httpkit": "^1.1.0"
  }
}
```

#### Lock Files

Range specifications allow flexibility; lock files pin reality:

```
# requirements.txt (lock)
httpkit==1.1.4

# package-lock.json records exact resolved version tree
```

The manifest defines acceptable versions; the lock file records what was actually installed. Both are necessary — the manifest for flexibility between teams, the lock file for reproducible CI/CD builds.

---

## Use It

### Ecosystem Adoption

| Ecosystem | Tool | Range Format | Notes |
|-----------|------|-------------|-------|
| Node.js | npm / yarn / pnpm | `^`, `~`, `>=` | Caret default; `package-lock.json` pins |
| Python | pip / Poetry | `^` (Poetry), `>=,<` (pip) | `poetry.lock` / `requirements.txt` |
| Rust | Cargo | `^` default | `Cargo.lock` always committed for binaries |
| Java | Maven / Gradle | `[1.0,2.0)` interval notation | POMs rarely use ranges; BOMs preferred |
| Go | Go Modules | `v1.2.3` exact in `go.mod` | Breaking changes require new import path (`v2/...`) |
| Docker | Registry tags | `nginx:1.25.3` / `nginx:1.25` | `latest` is an anti-pattern for production |

### API Versioning (URL & Header)

SemVer is for library releases. For HTTP APIs, a simpler scheme is common:

```
/api/v1/users      ← URL path versioning
/api/v2/users      ← breaking change gets a new major path
```

Or via header:

```
Accept: application/vnd.myapp.v2+json
```

Most public APIs only surface the MAJOR version externally — they do not expose PATCH or MINOR in the URL because those changes are transparent to callers.

### Cloud Services

AWS, GCP, and Azure version their APIs by date (`2023-11-01`) rather than SemVer. Date versioning is common for REST services that release on fixed schedules and cannot use automated range resolution.

---

## Common Pitfalls

- **Treating MINOR as "safe to break"** — The most common real-world violation. Removing a field from a response, changing a default, making an optional argument required — these are all MAJOR changes even if they feel small. When in doubt, it is a MAJOR bump.

- **Staying at `0.x` forever to avoid commitment** — Projects that live at `0.y.z` for years lose credibility. Consumers either avoid them or pin exact versions. When your API is stable enough that you would feel bad breaking it, it is `1.0.0` time.

- **Using `latest` or `*` in production dependencies** — This is equivalent to saying "give me whatever exists right now." It breaks reproducible builds and lets a new upstream MAJOR silently pull in breaking changes.

- **Not committing lock files for applications** — Applications (servers, CLIs, deployed services) must commit their lock files. Libraries should not commit lock files (it interferes with consumers' dependency resolution). The rules are opposite and matter.

- **Conflating build metadata with release ordering** — Build metadata after `+` is ignored for precedence comparisons. `1.0.0+build.1` and `1.0.0+build.2` are considered equal by resolvers. Do not embed critical ordering information in the build metadata field.

---

## Exercises

1. **Easy** — Given these releases in chronological order: `1.0.0`, `1.0.1`, `1.1.0`, `1.1.1`, `2.0.0`. For a consumer whose manifest says `^1.0.0`, which versions are acceptable? Which is the latest they would receive?

2. **Medium** — You maintain a REST API at `v1`. You need to: (a) fix a bug in the response body of `GET /users/{id}`, (b) add an optional `?include_deleted=true` query parameter, (c) rename the field `user_name` to `username`. Which of these requires a new API version? Justify each decision.

3. **Hard** — Your team manages a shared internal library used by 12 services. The library is at `3.2.1`. You need to refactor the authentication module in a backward-incompatible way, but three of the twelve services cannot be migrated for at least six months due to freezes. Design a versioning and release strategy that lets you ship the breaking change without blocking the three frozen services, and without maintaining an indefinitely-forked codebase.

---

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|------------------------|
| **SemVer** | Just a numbering format | A versioning *contract* defining what each number communicates about compatibility |
| **MAJOR bump** | A big, important release | Any change that breaks the existing public API surface, regardless of size |
| **MINOR bump** | A small or medium change | Backward-compatible new functionality — old callers must continue to work unchanged |
| **PATCH bump** | Trivial change | Backward-compatible bug fix — nothing the caller relied on should behave differently (except the bug) |
| **`^` (caret range)** | Latest version | Any version `>=` the specified one and `<` the next MAJOR — e.g., `^1.2.3` means `>=1.2.3 <2.0.0` |
| **Lock file** | Optional safety net | The exact resolved dependency tree, required for reproducible builds of deployable artifacts |
| **Pre-release** | Beta / test label | A formally defined version ordering: `1.0.0-rc.1 < 1.0.0`; resolvers respect this ordering |

---

## Further Reading

- [SemVer Specification (semver.org)](https://semver.org) — The authoritative specification, short and readable.
- [npm Documentation — About semantic versioning](https://docs.npmjs.com/about-semantic-versioning) — How npm's resolver interprets range syntax in practice.
- [Go Modules Reference — Module version numbering](https://go.dev/ref/mod#versions) — How Go's module system adapts SemVer with import-path versioning for MAJOR bumps.
- [Cargo Book — Specifying Dependencies](https://doc.rust-lang.org/cargo/reference/specifying-dependencies.html) — Rust's take on version ranges with clear explanations of caret and tilde.
- [The Twelve-Factor App — Dependencies](https://12factor.net/dependencies) — Why explicit, isolated dependency declarations and lock files matter for production deployability.
