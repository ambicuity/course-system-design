# 16 Coding Patterns That Make Interviews Easy

> Recognize the pattern first — the code writes itself.

**Type:** Learn
**Prerequisites:** Big-O Notation Basics, Array and Hash Table Fundamentals
**Time:** ~40 minutes

---

## The Problem

Every coding interview problem looks unique on first read. You see "given an array…" and your brain starts searching for something you memorized. This approach breaks at scale: there are thousands of problems, but only about sixteen underlying algorithmic patterns. Without knowing the patterns, you spend your limited interview time reinventing solutions rather than adapting known templates.

Imagine you get asked "find two numbers in a sorted array that sum to a target". If you only know brute force, you try every pair — O(n²). If you recognize the **Two-Pointer** pattern, you converge from both ends in O(n). The insight that unlocks O(n) is not cleverness; it's pattern recognition applied to the constraint "sorted array with opposite pointers moving toward each other".

This lesson catalogs all sixteen patterns, explains the structural cue that triggers each one, shows the core template, and maps patterns to the families of problems they solve. Internalizing these transforms interviews from a memory test into an engineering exercise.

---

## The Concept

### How to Identify a Pattern

Before diving into each pattern, internalize this diagnostic flow:

```
Read the problem
       │
       ▼
Is the input sorted or can we exploit ordering? ──► Two Pointers / Sliding Window / Binary Search
       │ No
       ▼
Is there repetition or fast lookup needed? ──────► HashMap / Prefix Sum
       │ No
       ▼
Is it a sequence with next/prev dependencies? ──► Stack / Linked List
       │ No
       ▼
Is it a top-K or priority problem? ─────────────► Heap
       │ No
       ▼
Is it a tree or graph traversal? ────────────────► Trees / Tries / Graphs / Backtracking
       │ No
       ▼
Does it have overlapping subproblems? ───────────► DP / Greedy
       │ No
       ▼
Are intervals or ranges involved? ───────────────► Intervals
```

---

### The 16 Patterns

#### 1. Two-Pointer Technique
**Trigger:** Sorted array or string, searching for pairs/triplets, removing duplicates.

Use two indices that move toward each other (or in the same direction at different speeds). Eliminates a nested loop, reducing O(n²) to O(n).

```
arr = [1, 3, 5, 7, 9]  target = 10
       L              R
       L  →           ← R   1+9=10 ✓
```

**Template:**
```python
def two_sum_sorted(arr, target):
    L, R = 0, len(arr) - 1
    while L < R:
        s = arr[L] + arr[R]
        if s == target:
            return [L, R]
        elif s < target:
            L += 1
        else:
            R -= 1
    return []
```

---

#### 2. HashMaps
**Trigger:** "Find if X exists", frequency counting, grouping, O(1) lookup.

Trade memory for speed. Store values you've seen so each new element can be checked in constant time.

```python
# Anagram grouping: group words by sorted characters
from collections import defaultdict
def group_anagrams(words):
    groups = defaultdict(list)
    for w in words:
        groups[tuple(sorted(w))].append(w)
    return list(groups.values())
```

---

#### 3. Linked Lists
**Trigger:** Dynamic insertion/deletion, no random access needed, stream of nodes.

Key operations: reverse in-place (prev/curr/next pointers), merge two sorted lists, detect cycles. The trick is always drawing the pointer state before writing code.

```
Reverse: None ← 1 ← 2 ← 3 ← 4
                              ^
                            head
```

---

#### 4. Fast and Slow Pointers (Floyd's Algorithm)
**Trigger:** Cycle detection, finding middle of a list, detecting start of a cycle.

`slow` moves one step; `fast` moves two. If a cycle exists, they meet inside it.

```
slow: 1 → 2 → 3 → 4
fast: 1 → 3 → 5 → 3   ← they meet → cycle confirmed
```

---

#### 5. Sliding Window
**Trigger:** Contiguous subarray/substring with a constraint (max sum, longest unique, minimum size).

Expand the right edge; shrink the left edge when the constraint is violated. O(n) instead of O(n²) for subarray problems.

```python
def max_sum_subarray(arr, k):
    window_sum = sum(arr[:k])
    best = window_sum
    for i in range(k, len(arr)):
        window_sum += arr[i] - arr[i - k]
        best = max(best, window_sum)
    return best
```

Fixed-size vs. variable-size window: fixed slides by dropping the leftmost element; variable shrinks the left pointer until valid again.

---

#### 6. Binary Search
**Trigger:** Sorted input, "find the minimum/maximum X that satisfies Y", search space that halves.

Beyond simple element search, binary search applies to any monotonic decision function. If you can write `is_feasible(mid)` → True/False with a threshold, binary search finds the boundary.

```python
def binary_search(arr, target):
    lo, hi = 0, len(arr) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1
```

---

#### 7. Stacks
**Trigger:** Matching brackets/parentheses, "next greater element", undo operations, DFS iteratively.

Last-In-First-Out. The classic cue: you need to track things in reverse order of when you saw them.

```python
def is_valid_brackets(s):
    stack, pairs = [], {')': '(', ']': '[', '}': '{'}
    for c in s:
        if c in '([{':
            stack.append(c)
        elif not stack or stack[-1] != pairs[c]:
            return False
        else:
            stack.pop()
    return not stack
```

---

#### 8. Heaps (Priority Queues)
**Trigger:** Top-K elements, median of a stream, task scheduling by priority, merge K sorted lists.

Python's `heapq` is a min-heap. For a max-heap, negate values. Two-heap trick for running median: one max-heap for the lower half, one min-heap for the upper half.

```python
import heapq
def top_k_frequent(nums, k):
    from collections import Counter
    freq = Counter(nums)
    return heapq.nlargest(k, freq, key=freq.get)
```

---

#### 9. Prefix Sum
**Trigger:** Range sum queries, subarray sum equals K, multiple queries on static array.

Precompute cumulative sums so any range [i, j] is answered in O(1): `prefix[j+1] - prefix[i]`.

```
arr    =  [3,  1,  4,  1,  5]
prefix =  [0,  3,  4,  8,  9, 14]

sum(arr[1..3]) = prefix[4] - prefix[1] = 9 - 3 = 6
```

---

#### 10. Trees
**Trigger:** Hierarchical data, "lowest common ancestor", path sums, tree diameter, BST validation.

Three DFS traversals (preorder, inorder, postorder) and BFS (level-order). Recursive structure maps cleanly: handle the base case (null node), recurse left, recurse right, combine.

```python
def max_depth(root):
    if not root:
        return 0
    return 1 + max(max_depth(root.left), max_depth(root.right))
```

---

#### 11. Tries (Prefix Trees)
**Trigger:** Autocomplete, spell check, word search, prefix matching on a large dictionary.

A trie stores characters at each node. Lookup is O(L) where L is word length, independent of dictionary size. Far faster than storing words in a hash set when prefix queries are needed.

```
insert("cat"), insert("car"), insert("dog")

root
├── c
│   └── a
│       ├── t (end)
│       └── r (end)
└── d
    └── o
        └── g (end)
```

---

#### 12. Graphs
**Trigger:** Network connectivity, shortest path, dependency resolution, island counting, course scheduling (cycle detection).

Choose the right traversal:
- **BFS** → shortest path in unweighted graph, level-by-level exploration
- **DFS** → cycle detection, topological sort, connected components
- **Dijkstra** → shortest path in weighted (non-negative) graph
- **Union-Find** → dynamic connectivity, Kruskal's MST

```python
from collections import deque
def bfs(graph, start):
    visited, queue = {start}, deque([start])
    while queue:
        node = queue.popleft()
        for neighbor in graph[node]:
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
```

---

#### 13. Backtracking
**Trigger:** "Generate all combinations/permutations/subsets", constraint satisfaction (N-Queens, Sudoku), path exploration.

Build a candidate solution incrementally; abandon ("backtrack") as soon as a constraint is violated. The search tree is pruned, not fully explored.

```python
def subsets(nums):
    result = []
    def dfs(start, path):
        result.append(path[:])
        for i in range(start, len(nums)):
            path.append(nums[i])
            dfs(i + 1, path)
            path.pop()           # backtrack
    dfs(0, [])
    return result
```

---

#### 14. Dynamic Programming
**Trigger:** Optimization ("max/min/count X"), overlapping subproblems, optimal substructure.

Two forms: **top-down** (memoized recursion) and **bottom-up** (iterative tabulation). The critical step is defining the state: `dp[i]` means "answer for the first i elements".

Classic problems and their DP states:

| Problem | State Definition |
|---|---|
| Coin change | `dp[amount]` = min coins to make amount |
| Longest Common Subsequence | `dp[i][j]` = LCS of s1[:i] and s2[:j] |
| 0/1 Knapsack | `dp[i][w]` = max value using i items, capacity w |
| Climbing Stairs | `dp[i]` = ways to reach step i |

---

#### 15. Greedy Algorithms
**Trigger:** "Minimum intervals to cover", scheduling, always picking the locally optimal choice works globally.

Greedy works when the problem has the **greedy-choice property**: a locally optimal choice leads to a globally optimal solution. No backtracking, no subproblem overlap needed. Prove correctness with an exchange argument (assume greedy is wrong, show swapping to greedy doesn't make things worse).

Classic greedy: **interval scheduling maximization** — always pick the activity that ends earliest.

```python
def max_non_overlapping(intervals):
    intervals.sort(key=lambda x: x[1])  # sort by end time
    count, end = 0, float('-inf')
    for s, e in intervals:
        if s >= end:
            count += 1
            end = e
    return count
```

---

#### 16. Intervals
**Trigger:** "Merge overlapping intervals", "insert interval", "meeting rooms", "minimum platforms".

Sort by start time. Then sweep: if the current interval overlaps the last merged one, extend it; otherwise push it.

```python
def merge_intervals(intervals):
    intervals.sort(key=lambda x: x[0])
    merged = [intervals[0]]
    for s, e in intervals[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return merged
```

---

## Build It / In Depth

### Worked Example: Diagnosing a Problem End-to-End

**Problem:** "Given a string, find the length of the longest substring without repeating characters."

**Step 1 — Identify structural cues:**
- Contiguous substring → **Sliding Window**
- Need to track seen characters → **HashMap**
- Two patterns combine.

**Step 2 — Define window invariant:**
The window `[L, R]` must contain no duplicate characters. When `arr[R]` is already in the window, advance `L` past the previous occurrence.

**Step 3 — Implement:**

```python
def length_of_longest_substring(s: str) -> int:
    last_seen = {}   # char -> last index
    L = 0
    best = 0

    for R, ch in enumerate(s):
        if ch in last_seen and last_seen[ch] >= L:
            L = last_seen[ch] + 1   # shrink window
        last_seen[ch] = R
        best = max(best, R - L + 1)

    return best

# Trace on "abcabcbb"
# R=0 ch=a  window=[a]          len=1
# R=1 ch=b  window=[ab]         len=2
# R=2 ch=c  window=[abc]        len=3
# R=3 ch=a  L→1  window=[bca]   len=3
# R=4 ch=b  L→2  window=[cab]   len=3
# R=5 ch=c  L→3  window=[abc]   len=3
# R=6 ch=b  L→5  window=[cb]    len=2
# R=7 ch=b  L→6  window=[b]     len=1
# Result: 3
```

Time: O(n) — each character is added and removed from the window at most once.
Space: O(min(n, |alphabet|)) — hash map bounded by alphabet size.

**Step 4 — Edge cases:**
- Empty string → return 0 (loop never executes, `best` stays 0).
- All same characters → window never grows past 1.
- All unique → entire string is the window.

---

## Use It

| Pattern | Real-world system use | Common problems |
|---|---|---|
| Two Pointers | Partition step in merge sort, collision detection | 3Sum, Remove Duplicates, Container With Most Water |
| HashMap | Database hash joins, compiler symbol tables | Two Sum, Group Anagrams, LRU Cache |
| Sliding Window | TCP congestion window, time-series anomaly detection | Max Sum Subarray, Longest Unique Substring |
| Binary Search | B-tree page search, `git bisect`, feature flags rollout | Search in Rotated Array, Find Peak Element |
| Heap | OS process scheduler, Dijkstra's open set, log aggregation | K Closest Points, Merge K Sorted Lists, Task Scheduler |
| Prefix Sum | Database window functions (`SUM() OVER`), image integral | Range Sum Query, Subarray Sum Equals K |
| Graphs + BFS | Distributed system topology, package dependency resolution | Word Ladder, Shortest Path, Clone Graph |
| DP | Compiler optimization, sequence alignment in bioinformatics | Edit Distance, Longest Increasing Subsequence |
| Greedy | Network routing (Dijkstra step), Huffman coding | Jump Game, Gas Station, Activity Selection |
| Intervals | Calendar scheduling, IP range lookups, OS memory allocator | Meeting Rooms, Insert Interval, Minimum Meeting Rooms |
| Tries | Search engine autocomplete, IP routing tables | Word Search II, Implement Trie, Replace Words |
| Backtracking | SAT solvers, game AI (chess move generation) | N-Queens, Sudoku Solver, Generate Parentheses |

---

## Common Pitfalls

- **Misidentifying the pattern under time pressure.** Practice stating the pattern name out loud before writing any code. This forces explicit recognition rather than jumping to implementation on instinct.

- **Using a HashMap when a sorted array + Two Pointers is sufficient.** Both work for Two Sum, but if the array is already sorted, Two Pointers is O(1) space. Know when the hash table's extra space is worth it.

- **Off-by-one in Sliding Window.** Window length is `R - L + 1`, not `R - L`. Maintain a small invariant comment in your code to self-check.

- **Forgetting to handle the cycle start in Fast/Slow Pointers.** Detecting a cycle is step one. Finding *where* the cycle starts requires resetting one pointer to head and advancing both by one until they meet again.

- **Greedy without a proof.** Greedy fails on 0/1 Knapsack but works on Fractional Knapsack. Always verify with an exchange argument or a small counterexample before committing to greedy over DP.

- **DP state definition is wrong.** If your recurrence feels forced or your base cases are inconsistent, redefine the state. Most DP bugs trace back to a vague or incorrect state definition, not the recurrence itself.

---

## Exercises

1. **Easy — Sliding Window:** Given an integer array and window size `k`, return the maximum sum of any contiguous subarray of length `k`. Solve in O(n) time and O(1) space.

2. **Medium — Heap + HashMap:** Given an array of integers, return the top-K most frequent elements. If two elements have the same frequency, either order is acceptable. Solve in O(n log k) time.

3. **Hard — DP + Backtracking combination:** Given a string `s` and a dictionary of words, determine if `s` can be segmented into a space-separated sequence of dictionary words (Word Break). Extend the solution to return all possible segmentations (Word Break II). Analyze the time complexity difference between the two variants.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Sliding Window | A physical window that slides over an array | A two-pointer technique where one pointer expands and another contracts to maintain a constraint on the subarray between them |
| Memoization | Caching anything | Specifically: storing the result of a recursive call indexed by its input parameters to avoid recomputation — the top-down form of DP |
| Backtracking | Brute force | Depth-first exploration with early termination when a partial solution violates constraints — often exponentially faster than true brute force |
| Greedy | Always optimal | Optimal only when the problem has the greedy-choice property; counterexamples exist and must be checked |
| Prefix Sum | A sum you compute before something | A precomputed array where `prefix[i]` = sum of all elements from index 0 to i−1, enabling O(1) range queries |
| Trie | Just another tree | A tree where edges represent characters, enabling O(L) lookup and prefix search independent of dictionary size |
| Two Heaps | Two separate sorted structures | A pair of a max-heap (lower half) and min-heap (upper half) used together to find the running median in O(log n) per insertion |

---

## Further Reading

- **LeetCode Patterns** — https://seanprashad.com/leetcode-patterns/ — curated problem list organized by the exact 16 patterns in this lesson; work through it in pattern order, not random order.
- **Grokking the Coding Interview** (Educative.io) — https://www.educative.io/courses/grokking-the-coding-interview — the original course that popularized pattern-based interview prep; the sliding window and two-pointer modules are especially strong.
- **CLRS Introduction to Algorithms, 4th Ed.** — https://mitpress.mit.edu/books/introduction-algorithms-fourth-edition — the authoritative reference for DP, greedy correctness proofs, and graph algorithms; read the chapter introductions for the "why".
- **CP-Algorithms** — https://cp-algorithms.com/ — free, rigorous writeups of graph algorithms, prefix structures, and advanced DP techniques with complexity proofs.
- **Competitive Programmer's Handbook (Antti Laaksonen)** — https://cses.fi/book/book.pdf — free PDF; chapters 2–12 map directly to patterns 1–16 and show worked examples in C++ that translate cleanly to Python.
