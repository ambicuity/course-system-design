# How Git Reset Works?

> Git reset doesn't erase history — it moves a pointer and optionally syncs two other layers to match it.

**Type:** Learn
**Prerequisites:** Git basics (commits, branches, staging area), Git log and diff
**Time:** ~20 minutes

---

## The Problem

You just committed three "WIP" commits while prototyping a feature. Now you want to squash them into one clean commit before pushing. Or you staged a file by accident and want to unstage it without touching the actual file content. Or worse: you committed a debugging block you forgot to remove, and you want the commit gone entirely.

Without understanding `git reset`, you might reach for hacks: reverting and re-committing, force-deleting branches, or copying and pasting diffs by hand. Every one of those workarounds is slower and more error-prone than three characters: `--soft`, `--mixed`, or `--hard`.

The bigger problem is that `git reset` is one of Git's most powerful commands and one of its most misunderstood. Engineers confuse it with `git revert`, run `--hard` when they meant `--soft`, and lose work. This lesson gives you the mental model to use it confidently and safely.

---

## The Concept

### Git's Three Trees

Git manages your project through three distinct data structures, often called the "three trees":

```
┌─────────────────────────────────────────────────────────────┐
│  1. HEAD (pointer)                                          │
│     └─► points to the tip of the current branch            │
│         └─► that branch points to a specific commit        │
├─────────────────────────────────────────────────────────────┤
│  2. Index (Staging Area)                                    │
│     └─► a flat snapshot of what the next commit will look  │
│         like. Lives in .git/index                           │
├─────────────────────────────────────────────────────────────┤
│  3. Working Directory                                       │
│     └─► the actual files on disk you can read and edit     │
└─────────────────────────────────────────────────────────────┘
```

When you run `git add`, you copy files from the Working Directory into the Index.
When you run `git commit`, you turn the Index into a new commit object and advance HEAD.
`git reset` works by moving HEAD backward and — depending on the flag — syncing the Index and Working Directory to match.

### The Three Modes

Each mode controls how far "down" the reset propagates:

| Mode | Moves HEAD | Resets Index | Resets Working Dir | Data at risk |
|------|:----------:|:------------:|:------------------:|:------------:|
| `--soft` | Yes | No | No | None |
| `--mixed` (default) | Yes | Yes | No | None |
| `--hard` | Yes | Yes | Yes | **Yes — uncommitted changes are gone** |

A useful mnemonic: each mode affects one more tree than the previous one.

### Mode 1: `--soft` — Move the Pointer Only

```
BEFORE:
  A ── B ── C   ← HEAD (main)

git reset --soft HEAD~1

AFTER:
  A ── B ── C   (C still exists as an object in .git)
        ↑
      HEAD (main)

Index:     still contains C's changes  ← staged, ready to recommit
WorkDir:   unchanged
```

Use `--soft` when you want to undo the last commit(s) but keep all the changes staged. This is the safe "oops, wrong commit message" or "let me squash these two" operation.

### Mode 2: `--mixed` — Move Pointer and Unstage

```
BEFORE:
  A ── B ── C   ← HEAD (main)
  Index: matches C
  WorkDir: has C's files

git reset --mixed HEAD~1   (or just: git reset HEAD~1)

AFTER:
  A ── B ── C   (C still exists)
        ↑
      HEAD (main)

Index:     reset to B's snapshot  ← C's changes appear as unstaged
WorkDir:   unchanged               ← files on disk untouched
```

`--mixed` is the default when you omit a flag entirely. Use it to unstage everything from the last commit while keeping your edits on disk. It's also the right tool for `git reset HEAD <file>` to unstage a single file.

### Mode 3: `--hard` — Discard Everything

```
BEFORE:
  A ── B ── C   ← HEAD (main)
  Index: matches C
  WorkDir: may have uncommitted edits

git reset --hard HEAD~1

AFTER:
  A ── B ── C   (C orphaned — will be GC'd eventually)
        ↑
      HEAD (main)

Index:     reset to B
WorkDir:   reset to B  ← any uncommitted changes ARE GONE
```

`--hard` is a destructive operation on uncommitted work. Committed work survives as an orphan object for ~30 days (until `git gc` runs), so you can rescue it with `git reflog`. **Unstaged or untracked changes have no such safety net.**

### Under the Hood: What HEAD Actually Is

`HEAD` is a file at `.git/HEAD`. On a branch it contains:

```
ref: refs/heads/main
```

And `.git/refs/heads/main` contains the SHA-1 of the latest commit. When you reset, Git rewrites that SHA-1. The commit object at the old SHA remains in `.git/objects` — nothing is immediately deleted.

```
.git/
├── HEAD                  ← "ref: refs/heads/main"
├── refs/
│   └── heads/
│       └── main          ← "d4f9a2b..."  ← this SHA gets rewritten
└── objects/
    └── d4/
        └── f9a2b...      ← commit object stays here until GC
```

This is why `git reflog` can recover from a bad reset: the commit object still physically exists.

---

## Build It / In Depth

Walk through a realistic scenario: you have three messy WIP commits and you want to rewrite them into one clean commit.

### Setup

```bash
git log --oneline
# d4f9a2b (HEAD -> main) WIP: fix edge case
# 8e1c3fa WIP: add validation
# 3a7b0d1 WIP: initial feature skeleton
# 1f0e9c2 feat: previous clean commit
```

### Step 1 — Collapse three commits into staged changes with `--soft`

```bash
git reset --soft HEAD~3
```

```bash
git log --oneline
# 1f0e9c2 (HEAD -> main) feat: previous clean commit

git status
# Changes to be committed:
#   modified:   src/feature.py
#   modified:   tests/test_feature.py
```

All three commits' changes are now staged. The commits themselves are gone from the branch tip but the objects still live in `.git/objects`.

### Step 2 — Commit cleanly

```bash
git commit -m "feat: add validation with edge case handling"
```

### Alternative: Unstage selectively with `--mixed`

Say you staged two files by accident:

```bash
git add config.yml src/secret_debug.py
git status
# Changes to be committed:
#   new file: config.yml
#   new file: src/secret_debug.py
```

Unstage only the debug file:

```bash
git reset HEAD src/secret_debug.py
# (equivalent to: git restore --staged src/secret_debug.py in Git 2.23+)
```

```bash
git status
# Changes to be committed:
#   new file: config.yml
# Changes not staged for commit:
#   new file: src/secret_debug.py
```

`config.yml` stays staged. The debug file is unstaged but still on disk.

### Rescue After an Accidental `--hard`

```bash
git reset --hard HEAD~2   # oops — lost work

git reflog
# 1f0e9c2 HEAD@{0}: reset: moving to HEAD~2
# d4f9a2b HEAD@{1}: commit: the commit I wanted
# 8e1c3fa HEAD@{2}: commit: earlier commit

git reset --hard d4f9a2b   # restore to the lost commit's SHA
```

`git reflog` records every position HEAD has been at, making this recovery possible within the GC window (default 90 days for reachable objects, 30 for unreachable).

---

## Use It

### When Engineers Reach for Each Mode

| Scenario | Command |
|---|---|
| Fix last commit message (no code change) | `git reset --soft HEAD~1` then `git commit -m "new msg"` |
| Squash N WIP commits into one | `git reset --soft HEAD~N` then `git commit` |
| Unstage a file accidentally staged | `git reset HEAD <file>` |
| Pull a file from a specific commit | `git reset HEAD~1 -- path/to/file` |
| Nuke local experiment, restore clean state | `git reset --hard origin/main` |
| Rewind a local branch to a specific SHA | `git reset --hard <sha>` |

### `git reset` vs. `git revert`

This is one of the most common sources of confusion:

| Property | `git reset` | `git revert` |
|---|---|---|
| Changes history | Yes — rewrites branch tip | No — adds a new undo commit |
| Safe on shared/pushed branches | **No** — causes force-push problems | Yes — non-destructive |
| Use case | Local cleanup before push | Undoing already-pushed commits |
| Recoverable | Via `git reflog` | Always — new commit is permanent |

**Rule of thumb:** Never reset commits that exist on a remote that others have already pulled. Use `git revert` there instead.

### `git reset` vs. `git restore` (Git 2.23+)

Git 2.23 split `git checkout` and some `git reset` semantics into dedicated commands:

- `git restore --staged <file>` — unstages a file (replaces `git reset HEAD <file>`)
- `git restore <file>` — discards working directory changes (replaces `git checkout -- <file>`)

Both `git reset HEAD <file>` and `git restore --staged <file>` work today; the latter is more explicit about intent.

---

## Common Pitfalls

- **Using `--hard` on a dirty working directory.** Uncommitted edits and untracked files are wiped with no recovery path. Always run `git status` and `git stash` before a `--hard` reset if you have anything you care about.

- **Resetting a commit that has already been pushed.** The remote still has the commit. Pushing afterward requires `git push --force`, which rewrites shared history and breaks every teammate who has fetched since. Use `git revert` for pushed commits.

- **Confusing `git reset HEAD <file>` with discarding file changes.** `git reset HEAD <file>` unstages the file but leaves the working directory untouched. If you also want to throw away the file's edits, follow up with `git restore <file>` (or `git checkout -- <file>`).

- **Expecting `--hard` to remove untracked files.** `git reset --hard` only touches tracked files. Untracked files (files that have never been `git add`-ed) are unaffected. Use `git clean -fd` to remove those.

- **Forgetting that `git reflog` is your safety net.** Many engineers panic after a bad reset when `git log` shows commits are "gone." Run `git reflog` first — the SHA is almost certainly still there. The window to recover is typically 30–90 days depending on `gc.reflogExpire` settings.

---

## Exercises

1. **Easy — Understand the modes.** In a fresh repo, create three commits. Run `git log --oneline`. Then run `git reset --soft HEAD~2`. Check `git status` and `git log`. Describe exactly what changed and why. Repeat with `--mixed` and `--hard` on fresh history each time.

2. **Medium — Squash a feature branch.** Create a branch with five small commits that all belong to the same logical change. Use `git reset --soft` to collapse them into a single commit with a well-written message. Confirm with `git log` that only one new commit is visible, and that the diff against the original branch tip is identical.

3. **Hard — Recover a lost commit.** Create a commit, then run `git reset --hard HEAD~1` to "lose" it. Use `git reflog` to find the orphaned commit's SHA. Recover it by either resetting back to that SHA or by creating a new branch pointing to it (`git branch recovery <sha>`). Then investigate: what happens after you run `git gc --prune=now`? Can you still recover?

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| HEAD | "The latest commit" | A pointer to the current branch ref, which points to a commit. Can be "detached" when pointing directly to a SHA. |
| Index | "A list of staged changes" | A binary snapshot file (`.git/index`) representing the exact state of the next commit, updated by `git add`. |
| `--soft` | "A gentle reset that does nothing destructive" | Moves HEAD (and its branch ref) to a new commit; leaves the Index and Working Directory exactly as they were. |
| `--mixed` | "Unstages everything" | Moves HEAD and resets the Index to match the target commit; leaves files on disk unchanged. This is the default. |
| `--hard` | "Clears my local changes" | Moves HEAD, resets the Index, and rewrites the Working Directory to match the target commit. Destroys uncommitted edits irreversibly. |
| Orphan commit | "A deleted commit" | A commit object in `.git/objects` that is no longer reachable from any branch or tag. GC will prune it after the reflog window expires. |
| `git reflog` | "Git's undo history" | A local log of every position HEAD has occupied, stored in `.git/logs/HEAD`. Not pushed to remotes; used for local recovery only. |

---

## Further Reading

- [Git Tools — Reset Demystified (Pro Git book, Chapter 7)](https://git-scm.com/book/en/v2/Git-Tools-Reset-Demystified) — the canonical deep-dive; covers the three trees in exhaustive detail.
- [git-reset reference manual](https://git-scm.com/docs/git-reset) — authoritative flag-by-flag reference with behavior tables.
- [git-reflog reference manual](https://git-scm.com/docs/git-reflog) — how to navigate reflog output and configure expiry windows.
- [Atlassian Git Tutorial — Undoing Changes](https://www.atlassian.com/git/tutorials/undoing-changes) — practical scenarios comparing reset, revert, and restore side by side.
- [git-restore reference manual](https://git-scm.com/docs/git-restore) — covers the modern replacement for the file-level use cases of `git reset` and `git checkout`.
