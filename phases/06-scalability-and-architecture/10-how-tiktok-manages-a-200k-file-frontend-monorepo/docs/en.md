# How TikTok Manages a 200K File Frontend MonoRepo?

> At scale, a monorepo does not fail because of bad architecture — it fails because Git was never designed for 200,000 files.

**Type:** Learn
**Prerequisites:** Version Control Fundamentals, Dependency Management in Large Codebases, Build Systems at Scale
**Time:** ~25 minutes

---

## The Problem

A monorepo sounds like a clean solution: one repository, one version graph, shared libraries, atomic cross-project changes. That promise holds for repositories up to roughly 10,000–30,000 files. Beyond that, the cracks appear — not in your architecture, but in Git itself.

TikTok's frontend TypeScript monorepo crossed 200,000 files. At that size, `git clone` took **40 minutes**, a routine `git status` took **7 seconds**, and `git checkout` between branches took **1.5 minutes**. On a team with hundreds of engineers doing dozens of these operations per day, this is not an inconvenience — it is an engineering bottleneck. Engineers stop doing `git pull` before every build. They avoid creating branches. CI pipelines that clone fresh on every run become prohibitively expensive.

The core tension is that Git's object model was designed for correctness and history, not for partial, lazy, or profile-scoped access. When you clone, Git downloads every object ever committed. When you run `git status`, Git stat-calls every tracked file in the working tree. When you checkout a branch, Git unpacks every file. None of this was a problem when repositories held thousands of files, but the failure modes become acute in the hundreds-of-thousands range.

---

## The Concept

### Why Git Gets Slow at Scale

Git's performance degrades along two independent axes: **object store size** and **working tree size**.

| Git Operation | Bottleneck | Root Cause |
|---|---|---|
| `git clone` | Network + disk I/O | Downloads entire pack file of all blobs |
| `git status` | Syscall volume | `lstat()` on every tracked file |
| `git checkout` | Disk I/O + index update | Writes every file, updates index entry per file |
| `git commit` | Index serialization | Rebuilds index over entire working tree |
| `git fetch` | Network | Resolves all remote refs |

A repository with 200K files means Git issues ~200K `lstat()` system calls on every `git status`. On a network-mounted filesystem (common in cloud dev environments) or a filesystem with slow metadata access (some macOS configurations), each call can take microseconds, and 200K of them add up to seconds of wall-clock time.

### The Three-Layer Solution

TikTok's approach, embodied in the open-source **Sparo** tool, attacks this problem at three layers simultaneously:

```
┌─────────────────────────────────────────────────────┐
│                   Developer UX Layer                │
│           sparo checkout, sparo status              │
│   (profile-based, transparent wrapper over git)     │
└───────────────────┬─────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────┐
│              Git Optimization Layer                  │
│  ┌────────────────┐  ┌────────────────────────────┐ │
│  │ Sparse Checkout│  │  Partial Clone (treeless / │ │
│  │ (cone mode)    │  │  blobless)                 │ │
│  └────────────────┘  └────────────────────────────┘ │
│  ┌────────────────┐  ┌────────────────────────────┐ │
│  │ Git Protocol v2│  │  FSMonitor (fsmonitor-     │ │
│  │  (efficient    │  │  watchman)                 │ │
│  │   negotiation) │  │                            │ │
│  └────────────────┘  └────────────────────────────┘ │
└───────────────────┬─────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────┐
│           Workspace Management Layer                 │
│         Rush Stack + profile.json manifests          │
│   (declares which projects a developer works on)    │
└─────────────────────────────────────────────────────┘
```

### Layer 1: Sparse Checkout (Cone Mode)

Sparse checkout tells Git: "only materialize a subset of the working tree on disk." The older, pattern-based sparse checkout was slow because Git had to evaluate every file against a pattern list. **Cone mode**, introduced in Git 2.25, works differently — it operates on directory prefixes, which Git can evaluate in O(1) with a hashmap rather than O(n) pattern matching.

```
Full repository tree (all 200K files):
/
├── packages/
│   ├── video-player/        ← you need this
│   ├── analytics-sdk/       ← you need this
│   ├── live-streaming/      ← you don't need this
│   ├── creator-tools/       ← you don't need this
│   └── ... (180 more packages)
├── apps/
│   ├── web/
│   └── mobile-web/
└── tooling/

With cone-mode sparse checkout, only the declared directories
are written to disk. Git tracks the rest as "absent" entries.
```

The working tree shrinks from 200K files to perhaps 5K–20K files depending on the developer's declared profile. All Git operations that scale with working tree size — `status`, `checkout`, `commit` — become proportionally faster.

### Layer 2: Partial Clone

Sparse checkout reduces what is on disk. Partial clone reduces what is downloaded during `git clone`. Git supports two partial clone modes relevant here:

- **Blobless clone** (`--filter=blob:none`): Downloads all commits and trees, but defers downloading file contents (blobs) until they are needed. The object graph is complete; only content is lazy.
- **Treeless clone** (`--filter=tree:0`): Downloads only commits upfront, deferring both trees and blobs. Even more aggressive; best for CI pipelines that only need specific files.

For interactive developer use, blobless clone is the right balance: `git log` and `git blame` work without additional fetches because commit and tree metadata is present. File content is fetched on demand when you actually check out or diff specific files.

```
Traditional clone timeline:
t=0  ──── negotiate refs ───────────────── t=0.5s
t=0.5 ─── download pack (all blobs) ────── t=38m
t=38m ─── unpack + index ───────────────── t=40m

Blobless clone timeline:
t=0  ──── negotiate refs ───────────────── t=0.5s
t=0.5 ─── download commits + trees only ── t=90s
t=90s ─── sparse checkout (subset files) ─ t=120s
                                            ≈ 2 minutes  ✓
```

### Layer 3: FSMonitor Integration

`git status` is expensive because Git must verify that every tracked file's content matches the index. Without help, it calls `lstat()` on every tracked file. **FSMonitor** (via the `core.fsmonitor` config pointing to Watchman or the built-in `fsmonitor--daemon`) registers a kernel-level file-system watcher. Git queries the daemon: "which files changed since timestamp T?" and only stat-calls those files.

The result: `git status` drops from O(working-tree-size) syscalls to O(changed-files-since-last-status) syscalls. In a developer session where only a handful of files are actively edited, `git status` becomes nearly instant regardless of how large the working tree is.

### Layer 4: Profile-Based Workspace Management

The above Git features are powerful but require precise configuration. Sparo introduces a **profile** abstraction — a declarative JSON manifest that specifies which packages a developer works on. Profiles compose naturally: a developer working on both the video player and the analytics SDK declares both.

```
┌─────────────┐     sparo checkout         ┌──────────────────────┐
│  Developer  │  ─────────────────────────▶ │  profile.json        │
│  declares   │                             │  {                   │
│  profile:   │                             │    "includeFolders": │
│  "player"   │                             │     ["packages/      │
└─────────────┘                             │      video-player",  │
                                            │     "tooling/"]      │
                                            │  }                   │
                                            └──────────┬───────────┘
                                                       │
                                            ┌──────────▼───────────┐
                                            │  Sparo computes      │
                                            │  transitive deps,    │
                                            │  writes sparse-      │
                                            │  checkout config,    │
                                            │  runs git checkout   │
                                            └──────────────────────┘
```

This means a developer never manually edits `.git/info/sparse-checkout`. Sparo manages that file as a derived output of the profile, including transitive workspace dependencies resolved via Rush's `rush.json` package graph.

---

## Build It / In Depth

### Setting Up Sparo on a Rush Monorepo

Sparo is designed for Rush Stack monorepos, but the underlying Git techniques apply anywhere.

**Step 1 — Install Sparo globally**

```bash
npm install -g @tiktok/sparo
```

**Step 2 — Initialize Sparo in the repository**

```bash
# Run once at the repository root (alongside rush.json)
sparo init
```

This writes `.sparo/profiles/` directory structure and configures `.gitconfig` entries for FSMonitor and protocol v2.

**Step 3 — Define a developer profile**

```json
// .sparo/profiles/video-team.json
{
  "$schema": "https://tiktok.github.io/sparo/schemas/sparo-profile.schema.json",
  "includeFolders": [
    "packages/video-player",
    "packages/video-core",
    "apps/web"
  ]
}
```

**Step 4 — Clone with Sparo instead of Git**

```bash
# Instead of: git clone https://github.com/org/repo
sparo clone https://github.com/org/repo --profile video-team
```

Sparo translates this into:

```bash
# What Sparo actually runs under the hood:
git clone \
  --filter=blob:none \
  --no-checkout \
  --sparse \
  https://github.com/org/repo

git sparse-checkout set --cone \
  packages/video-player \
  packages/video-core \
  apps/web \
  common/config \
  tooling

git checkout main
```

**Step 5 — Switch profiles or add packages**

```bash
# Switch to a different profile
sparo checkout --profile creator-tools

# Add a single package to your current sparse checkout
sparo checkout --add-project @org/analytics-sdk
```

**Step 6 — Verify the performance improvement**

```bash
# Measure status time before/after
time git status          # Baseline
time sparo status        # With FSMonitor-aware wrapper
```

### Measuring the Impact

TikTok's published benchmarks on their 200K-file repository:

| Operation | Before Sparo | After Sparo | Improvement |
|---|---|---|---|
| `git clone` | 40 min | 2 min | 20× faster |
| `git checkout` | 1.5 min | 30 sec | 3× faster |
| `git status` | 7 sec | 1 sec | 7× faster |
| `git commit` | 15 sec | 11 sec | 1.4× faster |

The commit improvement is modest because commit does not download blobs (it only reads staged changes) and the index size remains large. The clone and status improvements are dramatic because those operations directly scale with blob count and working-tree file count respectively.

### How Cone Mode Compares to Pattern-Based Sparse Checkout

```bash
# Old pattern-based (slow — O(n) per file):
git sparse-checkout set
echo "packages/video-player/**" >> .git/info/sparse-checkout

# New cone mode (fast — O(1) directory hash lookup):
git sparse-checkout set --cone packages/video-player
```

Cone mode enforces a structural constraint: you can only include entire directory subtrees, not arbitrary file globs. This sounds restrictive but matches how monorepos are actually structured — packages are directories, and you want all files in a package, not a curated subset.

---

## Use It

### When to Reach for Each Technique

| Technique | Best For | When NOT to Use |
|---|---|---|
| Blobless clone (`--filter=blob:none`) | Developer workstations, interactive use | When you need full `git blame` without extra fetches |
| Treeless clone (`--filter=tree:0`) | CI pipelines, shallow analysis jobs | Interactive dev — `git log --stat` requires tree data |
| Sparse checkout (cone mode) | Monorepos with clear package boundaries | Single-package repos or repos without directory structure |
| FSMonitor / Watchman | Any repo > 5K files on local disk | Remote/network filesystems (Watchman unreliable over NFS) |
| Sparo | Rush Stack TypeScript monorepos at scale | Repos not using Rush; better to configure Git directly |

### Alternative Tooling at Scale

| Tool | Approach | Strength |
|---|---|---|
| **Sparo** (TikTok) | Wraps Git + Rush profile manifests | Deep Rush integration, profile composition |
| **VFS for Git** (Microsoft) | Virtual filesystem driver (GVFS) | Virtualizes the working tree at OS level; works for any language |
| **Sapling** (Meta) | Alternative VCS built on Mercurial DNA | Column-style history, EdenFS virtual filesystem |
| **Google Piper / CitC** | Cloud-based virtual filesystem | Never clones; files served on demand from cloud storage |
| **Nx** | Build task graph + affected-file analysis | Does not solve Git slowness; solves *what to build* efficiently |
| **Turborepo** | Build caching + task graph | Same scope as Nx — build-time, not VCS-time |

The key distinction: Nx and Turborepo solve "which packages need to be rebuilt" — they operate at the build graph layer. Sparo, VFS for Git, and Sapling solve "how to interact with the repository efficiently" — they operate at the VCS layer. A production-grade monorepo at scale needs solutions at both layers.

### Cloud Development Environments

In cloud IDEs (GitHub Codespaces, Gitpod, Google Cloud Workstations), network filesystem latency makes Watchman unreliable. The right approach is combining partial clone with **background prefetch**:

```bash
# Prefetch objects in background to reduce on-demand fetch latency
git config fetch.writeCommitGraph true
git maintenance start   # Schedules background gc, commit-graph, prefetch
```

---

## Common Pitfalls

- **Forgetting transitive dependencies in sparse checkout.** If your package imports a shared utility in `packages/core`, and you do not include `packages/core` in your sparse checkout, TypeScript compilation fails. Sparo resolves this by walking the Rush dependency graph. If you manage sparse checkout manually, you must enumerate transitive deps explicitly.

- **Running `git add .` or `git commit -a` with cone mode active.** These commands only stage changes in the materialized (checked-out) part of the tree. Files outside your sparse cone are invisible to these commands. Engineers coming from polyrepos instinctively use `-a` and are confused when their changes appear incomplete on other machines.

- **Mixing partial clone with scripts that assume full history.** CI scripts using `git log --all --follow` or `git describe` may trigger on-demand fetches for missing tree/blob objects, silently re-downloading large amounts of data and eliminating the speed benefit. Audit CI scripts for history-traversal commands when adopting partial clone.

- **FSMonitor on network filesystems.** Watchman relies on OS-level filesystem events (inotify on Linux, FSEvents on macOS). These events are not delivered for files on NFS or CIFS mounts. Enabling FSMonitor on a network drive does not crash Git, but it also does not help — Git falls back to full stat scans silently.

- **Not updating the profile when adding new cross-package dependencies.** A developer adds a `package.json` dependency on a sibling package but does not run `sparo checkout --add-project` or update their profile. The new package is absent from the working tree, TypeScript's path resolution fails, and the error message ("cannot find module") looks like a TypeScript bug rather than a sparse checkout issue.

---

## Exercises

1. **Easy — Understand the model.** Clone any public GitHub monorepo with 1,000+ files using `--filter=blob:none --sparse`. Run `git sparse-checkout set --cone packages/<one-package>`. Verify that only that directory is checked out with `find . -type f | wc -l`. Then run `git checkout` on a file outside the cone and observe what happens.

2. **Medium — Benchmark sparse checkout.** Take a monorepo you have access to (or create a synthetic one with `dd` and a script that generates 50,000 small files across 100 directories). Measure `git status` time with and without cone-mode sparse checkout using `time`. Add Watchman and `core.fsmonitor` and re-measure. Document the relationship between file count and wall-clock status time.

3. **Hard — Design a profile system.** Design a profile management system for a monorepo that does not use Rush. Your system should: (a) read a `workspace.json` that declares inter-package dependencies, (b) accept a profile name as input, (c) compute the transitive closure of required directories, (d) write `git sparse-checkout set --cone <dirs>`. Implement it as a CLI tool in any language. Bonus: handle the case where a developer has local uncommitted changes in a directory that would be removed by switching profiles.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **MonoRepo** | One giant repo with everything jammed in | A single repository where multiple independently deployable projects coexist with a shared dependency graph and tooling |
| **Sparse Checkout** | A partial clone — you don't download everything | A working tree filter that controls which files are materialized on disk; the full object store is still (eventually) local |
| **Partial Clone** | You checked out fewer files | A Git transport optimization where blob (file content) objects are not downloaded at clone time; fetched lazily on demand |
| **Cone Mode** | A strict version of sparse checkout | A directory-prefix–only mode of sparse checkout that enables O(1) file-membership lookup vs. O(n) pattern matching |
| **FSMonitor** | A fancy `inotify` wrapper | A Git daemon that receives kernel filesystem events and answers "which files changed since timestamp T," replacing O(n) stat scans with O(changed) lookups |
| **Sparo** | TikTok's internal secret tool | An open-source CLI wrapper around Git + Rush Stack that automates sparse checkout profile management, partial clone setup, and FSMonitor configuration |
| **Blobless Clone** | A clone without files | A partial clone variant that downloads all commits and directory trees but defers blob (file content) objects until they are accessed |

---

## Further Reading

- **Sparo official documentation and source** — [https://tiktok.github.io/sparo/](https://tiktok.github.io/sparo/) — The authoritative reference for Sparo's CLI, profile schema, and Rush integration.
- **Git partial clone design document** — [https://git-scm.com/docs/partial-clone](https://git-scm.com/docs/partial-clone) — The official Git documentation covering `--filter` modes, lazy fetching behavior, and protocol extensions.
- **GitHub Engineering: Scaling Git** — [https://github.blog/engineering/scaling-git-at-github/](https://github.blog/engineering/scaling-git-at-github/) — GitHub's own experience managing large repositories, covering pack file strategies and protocol v2.
- **Microsoft's VFS for Git (GVFS)** — [https://github.com/microsoft/VFSForGit](https://github.com/microsoft/VFSForGit) — An alternative approach to the same problem using a virtual filesystem driver; useful contrast to Sparo's profile-based model.
- **Rush Stack documentation** — [https://rushjs.io/pages/maintainer/](https://rushjs.io/pages/maintainer/) — The Rush monorepo manager that Sparo builds on; understanding Rush's project graph model is necessary to understand how Sparo resolves transitive profile dependencies.
