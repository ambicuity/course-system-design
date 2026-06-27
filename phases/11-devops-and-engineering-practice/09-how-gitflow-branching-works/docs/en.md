# How Gitflow Branching Works?

> Gitflow imposes a strict branch topology so that every commit has a known intent — feature, release, or emergency fix — and can never contaminate the wrong stage of your pipeline.

**Type:** Learn
**Prerequisites:** Git basics (commits, branches, merges), CI/CD fundamentals, Semantic Versioning
**Time:** ~25 minutes

---

## The Problem

Imagine a team of fifteen engineers working on a SaaS product. Three features are in flight, a v2.4 release is being stabilized for QA, and a P0 security patch just landed from the penetration test. On a single shared `main` branch — or an ad-hoc branch-per-developer scheme — every one of these workstreams collides. Half-done features block the release. The security patch can't ship without dragging unfinished features into production. Developers start "hiding" work in long-lived personal branches, creating multi-week merge nightmares.

The core tension is that software teams simultaneously need **isolation** (work on feature A without breaking feature B) and **integration** (eventually everything must converge). Without a protocol for when branches are created, what can land on them, and where they are merged, the repository becomes an unreliable map of what is actually in production.

Gitflow, introduced by Vincent Driessen in 2010, solves this by assigning a **contractual role** to each type of branch. The rules are strict on purpose: they let your CI/CD pipeline, your reviewers, and your release automation make safe assumptions about what a branch contains. The cost is ceremony; the payoff is predictability at scale.

---

## The Concept

Gitflow defines **five branch types**, two of which are permanent and three of which are ephemeral.

### Permanent branches

| Branch | Purpose | Who merges into it |
|--------|---------|--------------------|
| `main` | Always reflects production-ready code; every commit is a released version | `release/*` and `hotfix/*` only |
| `develop` | Integration branch; represents the latest delivered development changes | `feature/*`, `release/*`, `hotfix/*` |

`main` and `develop` are never deleted. A tag (e.g., `v2.4.0`) is created on `main` for every merge.

### Ephemeral branches

| Branch | Branched from | Merged into | Naming convention |
|--------|--------------|-------------|-------------------|
| `feature/*` | `develop` | `develop` | `feature/user-auth`, `feature/payment-refund` |
| `release/*` | `develop` | `main` **and** `develop` | `release/2.4.0` |
| `hotfix/*` | `main` | `main` **and** `develop` | `hotfix/2.4.1` |

### The topology

```
main      ─────●─────────────────────────●──────●──────────►
                │ tag v2.3.0              │      │ tag v2.4.1
                │                    ┌───┘      │
develop   ──────┴──●──●──●──●──●─────┼────●──●──┴──►
                   │           │     │
feature/A ─────────┘           │     │
                               │     │
release/2.4.0 ─────────────────┘ (bug fix commits)
                                      │
hotfix/2.4.1 ─────────────────────────┘
```

### The flow, step by step

**Feature development**

1. Branch `feature/login-redesign` off `develop`.
2. Work in isolation; push commits; open a PR against `develop`.
3. After review and CI green, merge into `develop`. Delete the feature branch.

**Release stabilization**

1. When `develop` has enough features for a release, branch `release/2.4.0` off `develop`.
2. Only bug fixes, documentation, and version bumps land on the release branch. No new features.
3. When stable, merge into `main` (tag `v2.4.0`) **and** back into `develop` (so fixes aren't lost).
4. Delete the release branch.

**Hotfix**

1. A critical production bug is found. Branch `hotfix/2.4.1` off `main` (specifically off the `v2.4.0` tag).
2. Apply the minimal fix. No new features.
3. Merge into `main` (tag `v2.4.1`) **and** into `develop`. Delete the hotfix branch.

### Why the dual merge matters

Both release and hotfix branches must merge into **both** `main` and `develop`. If you skip the `develop` merge, the next release will re-introduce the bug you just fixed — a silent regression that is extremely hard to diagnose.

### Versioning contract

Gitflow is designed for **scheduled releases with version numbers**. It pairs naturally with Semantic Versioning:

- Feature branches → minor version bump at release time (`2.3.0 → 2.4.0`)
- Hotfix branches → patch version bump (`2.4.0 → 2.4.1`)
- Major API breaks → planned as features, bump major (`2.x → 3.0.0`)

---

## Build It / In Depth

### Setup

```bash
# Start a new repository
git init my-service && cd my-service

# Create the first commit on main
echo "# my-service" > README.md
git add README.md && git commit -m "chore: initial commit"

# Create the develop branch
git checkout -b develop
git push -u origin develop
git push -u origin main
```

### Feature workflow

```bash
# Start a feature
git checkout develop
git pull origin develop
git checkout -b feature/user-auth

# ... work, work, work ...
git add .
git commit -m "feat: add JWT authentication middleware"

# Open a PR from feature/user-auth → develop, then after approval:
git checkout develop
git merge --no-ff feature/user-auth   # --no-ff preserves branch history
git push origin develop
git branch -d feature/user-auth
git push origin --delete feature/user-auth
```

The `--no-ff` flag creates a merge commit even when a fast-forward is possible. This keeps the branch topology visible in `git log --graph`, which is important for auditing what went into a release.

### Release workflow

```bash
# Enough features are in develop; time to cut a release
git checkout develop
git pull origin develop
git checkout -b release/2.4.0

# Bump version, update changelog
echo "2.4.0" > VERSION
git add VERSION && git commit -m "chore: bump version to 2.4.0"

# Fix a last-minute bug found in QA
git add bugfix.py && git commit -m "fix: null pointer in payment handler"

# Merge into main and tag
git checkout main
git merge --no-ff release/2.4.0
git tag -a v2.4.0 -m "Release 2.4.0"
git push origin main --tags

# Back-merge into develop
git checkout develop
git merge --no-ff release/2.4.0
git push origin develop

# Cleanup
git branch -d release/2.4.0
git push origin --delete release/2.4.0
```

### Hotfix workflow

```bash
# Critical bug in production (v2.4.0)
git checkout main
git checkout -b hotfix/2.4.1

git add critical_fix.py
git commit -m "fix: prevent SQL injection in search endpoint"
echo "2.4.1" > VERSION
git commit -am "chore: bump version to 2.4.1"

# Merge into main and tag
git checkout main
git merge --no-ff hotfix/2.4.1
git tag -a v2.4.1 -m "Hotfix 2.4.1"
git push origin main --tags

# CRITICAL: also merge into develop
git checkout develop
git merge --no-ff hotfix/2.4.1
git push origin develop

git branch -d hotfix/2.4.1
git push origin --delete hotfix/2.4.1
```

### Using git-flow CLI (optional automation)

The `git-flow` CLI extension automates the above ceremony:

```bash
brew install git-flow-avh

git flow init          # prompts for branch names; accept defaults

git flow feature start user-auth
git flow feature finish user-auth   # merges to develop, deletes branch

git flow release start 2.4.0
git flow release finish 2.4.0       # merges to main + develop, tags, deletes

git flow hotfix start 2.4.1
git flow hotfix finish 2.4.1        # merges to main + develop, tags, deletes
```

---

## Use It

### When Gitflow is the right choice

Gitflow shines in a specific context:

- **Versioned, scheduled releases** — libraries, mobile apps, on-premise software, APIs with explicit version contracts.
- **Multiple versions in production simultaneously** — enterprise customers pinned to v2.3 while others are on v2.4.
- **Regulated environments** — financial systems, healthcare software that require a stable "release candidate" window before shipping.

### Comparison with alternative branching strategies

| Strategy | Release cadence | Complexity | CD-friendly | Best for |
|----------|----------------|------------|-------------|----------|
| **Gitflow** | Scheduled (days–weeks) | High | Moderate | Libraries, versioned APIs, enterprise |
| **GitHub Flow** | Continuous | Low | Yes | SaaS products, small–mid teams |
| **Trunk-Based Development** | Continuous / multiple per day | Low (with feature flags) | Yes | High-velocity SaaS, large teams |
| **GitLab Flow** | Continuous + environment branches | Medium | Yes | Teams that mirror environments in branches |

### Gitflow in real tooling

- **GitHub Actions** — branch protection rules on `main` and `develop`; separate CI jobs for `release/*` (run full regression) vs `feature/*` (run unit tests only).
- **Semantic Release** — reads commit history on `main` to auto-bump the version and write changelogs after a Gitflow merge.
- **Jira / Linear** — branch naming `feature/PROJ-123-user-auth` auto-links branches to tickets.
- **Artifactory / Nexus** — promote `SNAPSHOT` artifacts from develop to `RELEASE` artifacts when a `release/*` branch merges to `main`.

---

## Common Pitfalls

- **Forgetting the back-merge into `develop`** — When a release or hotfix branch merges to `main`, teams often skip the `develop` merge. The bug fix silently vanishes from the next release cycle. Automate this step in your CI pipeline or use the `git-flow` CLI to make it non-optional.

- **Allowing feature work on release branches** — A release branch is a stabilization zone; only bug fixes belong there. Feature creep on release branches defeats the isolation purpose and risks shipping half-finished work. Enforce this with branch protection rules and PR review checklists.

- **Long-lived feature branches** — A `feature/big-rewrite` branch open for three months accumulates massive merge debt against `develop`. Use feature flags to merge incrementally complete work behind a toggle, keeping branches short-lived.

- **Treating `develop` as a junk drawer** — Some teams merge everything to `develop` — broken experiments, abandoned prototypes, half-done migrations. `develop` should always build and deploy to a staging environment. Gate merges with mandatory CI green status.

- **Using Gitflow for continuous-deployment SaaS** — If you deploy to production thirty times a day, Gitflow's overhead is disproportionate. The release branch stabilization cycle doesn't map onto a deployment cadence measured in minutes. Use GitHub Flow or trunk-based development instead, and reach for Gitflow only when you genuinely have versioned release windows.

---

## Exercises

1. **Easy** — Draw (on paper or in a text diagram) the full branch history for a product that ships `v1.0.0`, then adds two features to produce `v1.1.0`, then immediately patches a production bug to produce `v1.1.1`. Label every branch, merge, and tag.

2. **Medium** — Set up a local Git repository following Gitflow conventions. Create a `develop` branch, add two feature branches (`feature/login` and `feature/dashboard`) and merge them independently into `develop`. Then cut a `release/1.0.0` branch, apply one bug-fix commit to it, and complete the full release lifecycle (merge to `main`, tag, back-merge to `develop`). Verify with `git log --all --graph --oneline` that the topology is correct.

3. **Hard** — Your team is halfway through Gitflow but your CTO wants to move to trunk-based development with feature flags. Write a migration plan: (a) identify which in-flight Gitflow branches need to be resolved first; (b) describe the feature-flag strategy that replaces `feature/*` branches; (c) explain how you will handle the "release stabilization" concern that Gitflow's `release/*` branches currently solve.

---

## Key Terms

| Term | What people think | What it actually means |
|------|------------------|------------------------|
| **`develop` branch** | A secondary backup of `main` | The single integration point where all completed feature work converges before a release; always deployable to staging |
| **`release` branch** | A branch for writing release notes | A time-boxed stabilization branch cut from `develop`; accepts only bug fixes, version bumps, and docs; no new features |
| **`hotfix` branch** | Any urgent fix on any branch | Specifically a branch cut from `main` (not develop) to patch a production defect without pulling in unfinished develop work |
| **`--no-ff` merge** | Just a merge option | Forces a merge commit even when fast-forward is possible, preserving the visual branch structure in `git log --graph` |
| **Tag on `main`** | Optional metadata | In Gitflow, a mandatory version marker (e.g., `v2.4.0`) placed on every merge commit to `main`; enables reproducible production builds |
| **Back-merge** | Redundant extra work | The mandatory merge of a `release/*` or `hotfix/*` branch back into `develop` to prevent bug regressions in future releases |
| **Trunk-Based Development** | Gitflow without release branches | A fundamentally different model where all developers commit directly to one integration branch (trunk/main), using feature flags for isolation |

---

## Further Reading

- [A successful Git branching model](https://nvie.com/posts/a-successful-git-branching-model/) — Vincent Driessen's original 2010 post introducing Gitflow, including his 2020 reflection on when *not* to use it.
- [git-flow AVH Edition documentation](https://github.com/petervanderdoes/gitflow-avh) — The maintained CLI extension that automates the Gitflow ceremony.
- [Atlassian: Gitflow Workflow](https://www.atlassian.com/git/tutorials/comparing-workflows/gitflow-workflow) — Detailed diagrams and a comparison against Feature Branch and Forking workflows.
- [Trunk Based Development](https://trunkbaseddevelopment.com/) — Paul Hammant's reference site; essential reading before choosing Gitflow vs. trunk-based for a new project.
- [Semantic Versioning 2.0.0](https://semver.org/) — The versioning contract that Gitflow's release and hotfix cadence is designed to produce and maintain.
