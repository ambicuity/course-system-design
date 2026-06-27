# A Simplified Git Workflow

> Version control is only as useful as the discipline behind it — a consistent workflow turns Git from a backup tool into a collaboration superpower.

**Type:** Learn
**Prerequisites:** None
**Time:** ~25 minutes

---

## The Problem

Imagine three engineers working on the same codebase without any coordination protocol. Engineer A refactors the authentication module on her laptop. Engineer B fixes a bug in the same file on his machine. Engineer C adds a feature that depends on the old structure of both. By Friday, they try to combine their work and spend six hours resolving conflicts they do not fully understand — and two weeks later a regression ships because a partially-merged change was never tested.

This is not a Git problem. It is a workflow problem. Git provides the primitives — snapshots, branches, pointers, remote refs — but it imposes no process. Teams that treat `git push` as "sync everything to the cloud" end up with a history that is impossible to audit, revert, or bisect. A hotfix and a half-finished feature end up in the same commit. The `main` branch breaks every other Friday.

A simplified Git workflow solves this by defining exactly four things: where code lives at any moment (the four areas), which commands move it between areas, how branching maps to team intent, and what the history should look like for a future reader. Master the mental model and every Git command becomes a one-liner you never need to look up.

---

## The Concept

### The Four Areas

Git tracks code in four distinct locations. Understanding this is the single most important mental model in the entire tool.

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  Working          Staging           Local           Remote  │
│  Directory   ──►  Area (Index)  ──►  Repository  ──►  Repo  │
│  (Untracked /     (Staged)           (HEAD/refs)    (origin)│
│   Modified)                                                  │
│                                                              │
│  git add ──────►                                             │
│                  git commit ───────►                         │
│                                      git push ─────────────►│
│◄─────────────────────────────────── git pull / git fetch    │
└──────────────────────────────────────────────────────────────┘
```

| Area | Lives On | What It Contains |
|------|----------|-----------------|
| Working Directory | Your disk | Actual files you edit right now |
| Staging Area (Index) | `.git/index` | A binary snapshot of what the next commit will look like |
| Local Repository | `.git/objects/` | Immutable commit DAG; all your history |
| Remote Repository | GitHub / GitLab / etc. | A shared mirror of the local repo |

The staging area is the piece most developers skip over. It is not a "temporary save" button — it is a **composition layer**. You can stage specific lines (not whole files) and craft atomic commits that describe one logical change, even if your working directory has three half-finished ideas in it.

### What a Commit Actually Is

A commit is a **snapshot**, not a diff. Internally, Git stores a tree object (directory structure), blob objects (file contents), and a commit object pointing to the tree plus parent commit(s). When you run `git diff`, Git computes the diff on demand; nothing diff-shaped is stored.

```
commit  a1b2c3d
├── tree  f4e5d6a
│   ├── blob  (src/auth.ts)  hash-abc
│   └── blob  (src/main.ts) hash-def
└── parent  9f8e7d6
```

This means:
- Reverting a commit is O(1): just point HEAD at the parent.
- Bisecting works even on a repo with 10,000 commits.
- Branches are free — they are just a 41-byte file holding a commit hash.

### Branch Strategy: Feature Branch Flow

The simplest team workflow that works at any size:

```
main      ──●──────────────────────────●── (always deployable)
              \                       /
feature/x   ──●──●──●──●  (squash or merge)
```

Rules:
1. `main` (or `master`) is always deployable — never commit directly to it.
2. Every change starts on a short-lived feature branch named after a ticket or intent (`feature/auth-refresh`, `fix/login-redirect`).
3. A Pull Request (or Merge Request) is the gate: a human reviews it, CI runs on it, then it merges.
4. Delete the branch after merge to keep the repo clean.

### `git pull` vs `git fetch`

This is the most commonly confused pair:

| Command | What it does | Safe? |
|---------|-------------|-------|
| `git fetch` | Downloads remote refs and objects; does NOT touch your working directory | Always safe |
| `git pull` | `git fetch` + `git merge` (or `git rebase`) in one step | Can cause a merge commit |
| `git pull --rebase` | `git fetch` + `git rebase`; rewrites your local commits on top of remote | Preferred for clean history |

In a team setting, `git fetch` followed by a deliberate `git merge` or `git rebase` gives you control. `git pull` is a shortcut, but it can silently create unwanted merge commits.

---

## Build It / In Depth

### Daily Workflow: Step by Step

**1. Start fresh from `main`**

```bash
git checkout main
git pull --rebase origin main   # grab any upstream changes
git checkout -b feature/add-rate-limiter
```

**2. Write code, then stage selectively**

```bash
# Stage the whole file
git add src/rate_limiter.py

# Stage only specific lines (interactive patch mode)
git add -p src/rate_limiter.py
```

Interactive patch mode (`-p`) lets you review each "hunk" and decide `y` (stage it), `n` (skip), or `s` (split into smaller hunks). Use this to avoid accidentally committing debug `print` statements or half-finished ideas.

**3. Commit with intent**

```bash
git commit -m "feat: add token-bucket rate limiter with Redis backend"
```

Follow [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `refactor:`, `test:`, `chore:`. Tools like `semantic-release` parse these to auto-generate changelogs and version bumps.

**4. Inspect before pushing**

```bash
git diff HEAD         # working dir vs last commit
git diff --staged     # staged vs last commit (what will be committed)
git log --oneline -10 # last 10 commits
```

**5. Push and open a PR**

```bash
git push -u origin feature/add-rate-limiter
# Then open a Pull Request via GitHub UI or gh CLI:
gh pr create --title "feat: token-bucket rate limiter" --fill
```

**6. After PR is merged, clean up**

```bash
git checkout main
git pull --rebase origin main
git branch -d feature/add-rate-limiter
```

### Recovering from Mistakes

| Situation | Safe Command |
|-----------|-------------|
| Unstage a file | `git restore --staged <file>` |
| Discard local changes in working dir | `git restore <file>` |
| Amend the last commit message | `git commit --amend --no-edit` (only before pushing) |
| Undo last commit but keep changes | `git reset --soft HEAD~1` |
| Find a lost commit | `git reflog` — Git keeps everything for 30+ days |

**Never use `git reset --hard` on shared branches.** It rewrites history that others have already pulled.

### Visualizing the State Machine

```
            ┌──── git restore ────────────────────────┐
            │                                         │
  Modified  ──── git add ───►  Staged  ──── git restore --staged ──► Modified
                                 │
                                 ├──── git commit ───► Committed (local HEAD)
                                 │                          │
                                 │                     git push
                                 │                          │
                                 │                          ▼
                                 │                    Remote (origin)
                                 │
                            git stash (side pocket for WIP)
```

---

## Use It

### Real-World Workflow Variants

| Workflow | Best For | Branching Model |
|----------|----------|----------------|
| **GitHub Flow** | Continuous deployment, small teams | `main` + short feature branches |
| **GitFlow** | Versioned releases, enterprise software | `main`, `develop`, `release/*`, `hotfix/*` |
| **Trunk-Based Development** | High-velocity teams with strong CI | Single `main`, feature flags gate incomplete work |
| **Forking Workflow** | Open-source projects | Each contributor works in their own fork |

For most product teams building web services: **GitHub Flow** is sufficient. GitFlow is often over-engineered; its `develop` branch adds friction without meaningful benefit unless you manage multiple live versions simultaneously.

### Tooling That Enforces the Workflow

- **`pre-commit` hooks** — run linters, formatters, or secret-scanners before `git commit` completes. Install with [pre-commit.com](https://pre-commit.com/).
- **Branch protection rules** (GitHub/GitLab) — require PR review + passing CI before merging to `main`.
- **`commitlint`** — enforces Conventional Commits format in a hook.
- **`gh` CLI** — create PRs, review code, and merge branches without leaving the terminal.
- **`git bisect`** — binary search through commit history to find which commit introduced a bug; only works when commits are atomic.

---

## Common Pitfalls

- **Committing to `main` directly.** Even with good intentions, this bypasses code review and breaks the deployability guarantee. Enforce branch protection rules on day one.

- **Giant commits that mix concerns.** A commit titled "fix auth, refactor DB layer, update README, bump deps" is untestable and impossible to revert cleanly. Use `git add -p` to build atomic commits — one logical change per commit.

- **Using `git pull` when branches have diverged without understanding the merge commit it creates.** `git pull --rebase` keeps history linear. Teams should agree on which one to use and set it as the default: `git config --global pull.rebase true`.

- **Ignoring `git stash`.** Developers often commit half-finished work just to switch branches. `git stash` saves your working directory state, lets you switch context, and `git stash pop` restores it. Use `git stash push -m "wip: half-done auth refactor"` so stashes are labeled.

- **Force-pushing to shared branches.** `git push --force` rewrites remote history. Anyone who has pulled will have a divergent history and will be confused. If you must force-push (e.g., after a rebase on your own feature branch before anyone else has pulled it), use `git push --force-with-lease` which fails if the remote has changed since your last fetch.

---

## Exercises

1. **Easy** — Create a new local Git repository, make three commits each touching a different file, then use `git log --oneline --graph` to visualize the history. Observe that HEAD points to the latest commit.

2. **Medium** — Simulate a conflict: create branch `feature/a` and `feature/b` both from `main`. In each branch, edit the same line in the same file differently. Merge `feature/a` into `main`, then try to merge `feature/b`. Resolve the conflict manually and complete the merge. Inspect the resulting graph with `git log --all --oneline --graph`.

3. **Hard** — Set up a repository with a `pre-commit` hook (using the `pre-commit` framework) that runs `black` (Python formatter) and `pytest` before every commit. Commit a file with a failing test and observe the hook blocking the commit. Fix the test, commit successfully, and push. Then enable branch protection on GitHub so that the branch `main` requires the CI check to pass before merging.

---

## Key Terms

| Term | What People Think | What It Actually Means |
|------|------------------|----------------------|
| **HEAD** | "The current file on disk" | A pointer to the currently checked-out commit (or branch ref); it is just a 41-byte file in `.git/HEAD` |
| **Staging Area / Index** | "A temporary save before committing" | A binary snapshot of the next commit's tree; you can compose it from partial file changes |
| **Branch** | "A copy of the codebase" | A 41-byte file containing a commit hash; Git creates and deletes branches in microseconds |
| **`git pull`** | "Download latest changes" | `git fetch` + `git merge` (or `git rebase`); can create unwanted merge commits if not configured |
| **Merge Commit** | "A sign something went wrong" | A commit with two parents; perfectly valid for integrating long-lived branches, but noisy for short feature branches |
| **`git rebase`** | "Dangerous command to avoid" | Replays commits onto a new base, producing a linear history; safe on private branches, destructive on shared ones |
| **Conflict** | "Git failed" | Two branches made incompatible changes to overlapping lines; Git stops and asks you — the human — to decide the correct version |

---

## Further Reading

- [Pro Git Book (free)](https://git-scm.com/book/en/v2) — the canonical reference; Chapters 2–3 cover everything in this lesson in depth.
- [Conventional Commits Specification](https://www.conventionalcommits.org/en/v1.0.0/) — the widely-adopted standard for structured commit messages.
- [GitHub Flow Guide](https://docs.github.com/en/get-started/using-github/github-flow) — GitHub's own documentation on the simple branching model used by most SaaS teams.
- [Atlassian Git Tutorials — Merging vs. Rebasing](https://www.atlassian.com/git/tutorials/merging-vs-rebasing) — an excellent visual explanation of the trade-offs between `merge` and `rebase`.
- [pre-commit Framework](https://pre-commit.com/) — official docs for the hook manager that enforces code quality standards before every commit.
