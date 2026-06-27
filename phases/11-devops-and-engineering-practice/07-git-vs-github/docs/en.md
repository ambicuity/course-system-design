# Git vs GitHub

> Git is the engine; GitHub is the garage — one stores your work history locally, the other puts it on the internet so your team can collaborate.

**Type:** Learn
**Prerequisites:** Version Control Basics, CI/CD Fundamentals, DevOps Overview
**Time:** ~25 minutes

---

## The Problem

Imagine three engineers working on the same API service. Engineer A is building the auth endpoint, Engineer B is refactoring the database layer, and Engineer C is fixing a production bug. They share code by emailing zip archives. Within an hour, they have three divergent versions of the codebase. Nobody knows whose copy is authoritative. Engineer C's hotfix gets lost when A overwrites the folder. There is no record of *why* any change was made.

Version control solves this — but version control alone is not enough for a distributed team. You need a shared, canonical remote home for the repository. You also need tooling for code review, branch protection, CI triggers, and access control. These are two distinct problems, often conflated.

Most engineers starting out treat "Git" and "GitHub" as synonyms. This misunderstanding causes real pain: blaming "GitHub" for a merge conflict (a Git concept), assuming git commands talk directly to GitHub (they talk to any remote), or not knowing how to recover when GitHub has an outage (your local Git repository is self-contained and works fine offline). Clarity about where one ends and the other begins is a prerequisite for reasoning about your entire delivery pipeline.

---

## The Concept

### Git: A Distributed Version Control System

Git is a **local**, **open-source**, **distributed** version control system created by Linus Torvalds in 2005 to manage the Linux kernel source. It runs as a command-line program installed on your machine. It has no mandatory network dependency.

**Git's data model** is a directed acyclic graph (DAG) of content-addressed objects stored under `.git/`:

```
.git/
├── objects/          ← every blob, tree, commit, tag (content-addressed)
│   ├── 2e/
│   │   └── 8f3a...  ← SHA-1 hash of a blob or commit
│   └── pack/        ← packed objects for efficiency
├── refs/
│   ├── heads/        ← local branches (HEAD pointers)
│   └── remotes/      ← remote-tracking refs (e.g., origin/main)
├── HEAD              ← what branch/commit you're on right now
└── config            ← per-repo config (remotes, branch upstreams)
```

Four core object types:

| Object | What It Stores |
|--------|---------------|
| **blob** | Raw file contents (no filename, no metadata) |
| **tree** | Directory listing: filenames → blob/tree SHAs |
| **commit** | Tree SHA + parent SHA(s) + author + message |
| **tag** | Annotated pointer to a commit (with its own message) |

Every object is immutable and identified by the SHA-1 (or SHA-256 in newer Git) of its contents. Changing a file changes its blob hash, which changes the tree hash, which changes the commit hash — that chain of integrity is how Git detects corruption and enables verified history.

A **branch** is just a file in `.git/refs/heads/` containing a 40-character commit SHA. Moving a branch forward means overwriting that file. There is no heavyweight "branch object" — it costs 41 bytes.

```
main branch pointer: refs/heads/main → abc123
                                          │
                                    commit abc123
                                    ├── parent: def456
                                    ├── tree: 9a8b7c
                                    └── message: "add auth endpoint"
                                          │
                                    commit def456
                                    ├── parent: (none — root commit)
                                    ├── tree: 1f2e3d
                                    └── message: "initial commit"
```

Git is *distributed*: every clone contains the full object store and full history. No single node is inherently authoritative.

### GitHub: A Cloud Hosting and Collaboration Platform

GitHub is a **SaaS product** owned by Microsoft that hosts Git repositories on the internet and layers collaboration features on top:

| GitHub Feature | What It Does |
|---------------|-------------|
| Repository hosting | Serves `git push`/`git pull` over HTTPS or SSH |
| Pull Requests | Structured code-review workflow with comments and merge controls |
| Issues | Bug tracking and project planning |
| GitHub Actions | CI/CD pipeline triggered by repo events |
| Branch protection rules | Enforce required reviews, status checks before merge |
| Forks | Personal copies of a repo for open-source contribution |
| Access control | Per-repo permissions: read / write / admin, teams |
| GitHub Packages | Docker/npm/Maven package registry tied to a repo |
| Security scanning | Dependabot alerts, secret scanning, CodeQL |

GitHub does not invent new Git concepts. A Pull Request is *not* a Git primitive — it is a GitHub UI construct that represents "please merge this branch into that branch." Underneath, it is still `git merge` or `git rebase`.

### The Relationship

```
┌─────────────────────────────────────────────────────┐
│                    GitHub (cloud)                    │
│                                                     │
│  ┌────────────┐   Pull Requests   ┌─────────────┐  │
│  │  Remote    │ ◄────────────►   │   Actions   │  │
│  │ Git Repo   │                  │   (CI/CD)   │  │
│  └─────┬──────┘                  └─────────────┘  │
│        │  HTTPS / SSH                              │
└────────┼────────────────────────────────────────────┘
         │  git push / git pull / git fetch
┌────────▼────────────────────────────────────────────┐
│                 Developer Machine                    │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │  Local Git Repository  (.git/ directory)     │  │
│  │                                              │  │
│  │  Working Tree ──git add──► Staging ──git    │  │
│  │                             Index    commit  │  │
│  │                                      ▼       │  │
│  │                              Local commit    │  │
│  │                              history (DAG)   │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

**Key principle:** `git push` uploads your local commits to the remote. `git pull` (= `git fetch` + `git merge`) downloads remote commits and integrates them. At no point does GitHub *create* commits — it only stores and serves them.

---

## Build It / In Depth

### Step 1: Local Git workflow (no GitHub needed)

```bash
# Initialize a new repo — creates .git/
git init my-service
cd my-service

# Create a file and stage it
echo "print('hello')" > app.py
git add app.py          # copies file into the index (staging area)

# Commit — creates blob, tree, and commit objects in .git/objects/
git commit -m "feat: initial app skeleton"

# Inspect the commit object Git created
git cat-file -p HEAD
# tree 9fa3d2a...
# author Alice <alice@example.com> 1719360000 +0000
# committer Alice <alice@example.com> 1719360000 +0000
#
# feat: initial app skeleton

# See the tree it points to
git cat-file -p 9fa3d2a
# 100644 blob 2e8f3a...    app.py

# See the blob (raw file contents)
git cat-file -p 2e8f3a
# print('hello')
```

Everything above happened entirely on disk, with zero network activity.

### Step 2: Connect a local repo to GitHub

```bash
# Create a repo on GitHub (via UI or CLI)
gh repo create my-service --private --source=. --remote=origin

# What gh just did under the hood:
# git remote add origin git@github.com:alice/my-service.git

# Verify the remote is configured
git remote -v
# origin  git@github.com:alice/my-service.git (fetch)
# origin  git@github.com:alice/my-service.git (push)

# Upload local commits to GitHub
git push -u origin main
# -u sets origin/main as the upstream tracking branch for main
```

### Step 3: Team collaboration via GitHub Pull Requests

```bash
# Engineer B clones the repo (gets full history)
git clone git@github.com:alice/my-service.git
cd my-service

# Create a feature branch locally
git checkout -b feat/add-endpoint

# Make changes, commit
echo "def health(): return 'ok'" >> app.py
git add app.py
git commit -m "feat: add health endpoint"

# Push branch to GitHub (not to main)
git push -u origin feat/add-endpoint
```

On GitHub, B opens a Pull Request: `feat/add-endpoint → main`. The PR UI shows a diff, allows inline comments, enforces required reviewers, and can block merge until CI passes. When approved, GitHub calls `git merge` (or `git rebase`) on the server-side remote.

### Step 4: Remote-tracking branches explained

```bash
# What origin/main actually is:
cat .git/refs/remotes/origin/main
# abc123...  ← last known SHA on the GitHub side

# git fetch updates this WITHOUT touching your local main
git fetch origin
# origin/main advances to new commits, your main stays put

# git pull = git fetch + git merge (or --rebase)
git pull origin main
```

Remote-tracking refs (`origin/main`, `origin/feat/add-endpoint`) are Git's local read-only snapshots of what GitHub had last time you communicated. They are stored under `.git/refs/remotes/`.

---

## Use It

### GitHub vs Competing Platforms

| Feature | GitHub | GitLab | Bitbucket | Self-hosted Gitea |
|---------|--------|--------|-----------|-------------------|
| Ownership | Microsoft | GitLab Inc. | Atlassian | Open-source / you |
| CI/CD | GitHub Actions | GitLab CI | Bitbucket Pipelines | External or Drone |
| Free private repos | Yes | Yes | Yes (limit) | Yes (self-hosted) |
| Built-in container registry | Yes | Yes | No | No (add-on) |
| Enterprise SSO | Yes (GHEC) | Yes | Yes | Yes |
| Air-gapped deployment | GitHub Enterprise Server | GitLab Self-Managed | Bitbucket Data Center | Yes (natural fit) |
| Open source community | Largest ecosystem | Strong DevOps focus | Jira-integrated teams | Small teams |

**When to choose what:**
- **GitHub** — open-source projects, teams already in the Microsoft/Azure ecosystem, maximum third-party integration surface.
- **GitLab** — teams that want a single tool for full DevOps (planning → code → CI → deploy → monitoring) without stitching together separate services.
- **Bitbucket** — teams already paying for Jira and Confluence who want native Atlassian integration.
- **Self-hosted Gitea / Forgejo** — security-constrained environments, air-gapped networks, cost-sensitive teams with small repository counts.

### GitHub Actions as a collaboration layer

GitHub Actions is the most important feature GitHub adds *on top of* Git. A workflow file in `.github/workflows/ci.yml` is triggered by Git events (push, pull_request) but is 100% a GitHub concept — Git itself knows nothing about it.

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements.txt
      - run: pytest
```

This file is committed to Git, but the runner infrastructure, secrets vault, and log storage are all GitHub services.

---

## Common Pitfalls

- **Treating GitHub as Git's only remote.** Any server running `git-daemon` or `ssh` can be a remote. `git remote add staging ssh://deploy@10.0.0.5/srv/repo.git` is completely valid. Teams that internalize this recover faster when GitHub has an outage — local repos are intact and production can be deployed from them directly.

- **Confusing a Pull Request with a Git operation.** Pull Requests are a GitHub workflow mechanism. Nothing in the `git` binary knows about them. `git pull` is a completely different command (fetch + merge). Naming collisions here confuse junior engineers constantly.

- **Committing secrets and relying on GitHub to catch them.** GitHub's secret scanning runs *after* a push is already in the remote object store. Even after you delete the file in a follow-up commit, the secret remains accessible via the original commit SHA. Rotate credentials immediately; do not assume deletion removes them. Use `git filter-repo` for proper history rewriting.

- **Force-pushing to a shared branch.** `git push --force` rewrites the remote's history and can silently discard collaborators' committed work. Use `--force-with-lease` instead, which fails if the remote ref has moved since your last fetch. Better yet, protect `main` with a GitHub branch protection rule that disallows force pushes entirely.

- **Not understanding remote-tracking branch staleness.** After a teammate merges a PR, your local `origin/main` does not update automatically. Running `git status` and seeing "up to date" only means you are in sync with your *last fetched* snapshot. Run `git fetch --prune` before branching to get a fresh view of the remote state and remove stale remote-tracking refs for deleted branches.

---

## Exercises

1. **Easy — Git locally, no network.** Create a new directory, `git init` it, create three files, make three separate commits (one per file), then run `git log --oneline --graph` to see your history. Run `git cat-file -p HEAD` to inspect the commit object. Identify the blob SHA for one of the files.

2. **Medium — Branch and merge without GitHub.** In the same local repo, create a branch `feat/experiment`, make two commits on it, switch back to `main`, make one commit, then merge `feat/experiment` into `main`. Resolve any conflicts by hand. After the merge commit, draw (on paper) the DAG that `git log --all --graph --oneline` shows, and explain why there are two parent SHAs on the merge commit.

3. **Hard — Reproduce a GitHub PR locally.** Fork a public GitHub repository using `gh repo fork`. Clone your fork. Push a branch with a meaningful code change. Open a Pull Request via `gh pr create`. Configure a branch protection rule on your fork that requires at least one reviewer. Add a GitHub Actions workflow that runs a linter on every PR. Merge the PR using the squash strategy and explain what squash merging does to the commit graph compared to a regular merge commit.

---

## Key Terms

| Term | What people think | What it actually means |
|------|------------------|----------------------|
| **Git** | A synonym for GitHub | A free, open-source DVCS program installed locally; has no inherent network component |
| **GitHub** | Where code "lives" | A cloud SaaS that hosts Git remotes and adds collaboration features on top |
| **Remote** | GitHub | Any URI pointing to another Git repository (`https://`, `ssh://`, even a local path) |
| **Branch** | A copy of the codebase | A 41-byte file in `.git/refs/heads/` containing a single commit SHA |
| **Pull Request** | A Git feature | A GitHub UI concept — a request to merge one branch into another, with review workflow |
| **Fork** | A branch | A full independent clone of a repository on GitHub, with its own remote URL and permissions |
| **git pull** | Syncs with a Pull Request | `git fetch` followed by `git merge` (or `--rebase`); has nothing to do with GitHub PRs |

---

## Further Reading

- **Pro Git (free book):** https://git-scm.com/book/en/v2 — Chapters 1–3 for fundamentals, Chapter 10 for Git internals (object model, packfiles).
- **Git documentation:** https://git-scm.com/docs — Authoritative reference for every subcommand and config option.
- **GitHub Docs:** https://docs.github.com — Covers Actions, branch protection, security features, and the GitHub API.
- **GitHub CLI (gh) manual:** https://cli.github.com/manual — Scripting GitHub operations (PRs, releases, Actions) from the terminal.
- **"Git from the Bottom Up" by John Wiegley:** https://jwiegley.github.io/git-from-the-bottom-up/ — Short, precise walkthrough of the object model that makes the DAG mental model concrete.
