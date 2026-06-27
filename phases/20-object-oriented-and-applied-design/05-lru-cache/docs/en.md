# Design an LRU Cache

> A canonical object-oriented design kata — combining a doubly-linked list with a hash map for O(1) operations.

**Type:** Design kata
**Prerequisites:** Object-oriented programming, basic data structures
**Time:** ~25 minutes

---

## The Problem

The LRU (Least Recently Used) cache is one of the most common data structure design questions. It appears in interview prep books, system design lessons, and the source code of half the production caches ever written. Understanding how it works — and why each design choice is made — is foundational for any systems engineer.

The requirements are simple on the surface, but the design forces you to combine multiple data structures and reason about operations in constant time. This lesson walks through the problem, the standard solution, and the design rationale — and shows the full implementation.

---

## The Concept

### The problem

Design a cache that supports two operations in **O(1)**:

- `get(key)` — return the value for the key if present, mark as recently used
- `set(key, value)` — store the key-value pair, mark as recently used; evict the least recently used item if at capacity

**Constraints:**

- Both operations must be O(1)
- When the cache is at capacity, set must evict the least recently used item

The "recently used" requirement means we need to track usage order. The O(1) requirement means we cannot use a list-search-and-remove. The combination is the puzzle.

---

### Why a single data structure is not enough

A hash map alone gives O(1) get/set but does not track usage order.

A linked list alone tracks order but find-by-key is O(n).

A binary search tree could give O(log n) for both but is more complex than necessary.

The standard solution combines a **hash map** (for O(1) key lookup) with a **doubly-linked list** (for O(1) insertion, deletion, and reordering). The hash map points to nodes in the list; the list maintains the usage order.

```
   Hash Map                Doubly-Linked List (usage order)

   ┌──────────┐
   │ "foo"  ──┼──┐         HEAD <-> [B: x] <-> [A: y] <-> [C: z] <-> TAIL
   └──────────┘  │         most recent ────►──────────►──── least recent
   ┌──────────┐  │
   │ "bar"  ──┼──┼──►  [B: x]   prev: HEAD,  next: [A: y]
   └──────────┘  │    [A: y]   prev: [B],   next: [C: z]
                 │    [C: z]   prev: [A],   next: TAIL
                 │
   ┌──────────┐  │
   │ "baz"  ──┼──┘
   └──────────┘

   When "foo" is accessed:
     1. Find the node via the hash map (O(1))
     2. Remove it from its current position (O(1))
     3. Insert it at the head (O(1))
     4. Both the hash map and the list are updated
```

---

### The data structures

**Doubly-linked list:**

```python
class Node:
    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.prev = None
        self.next = None
```

The list has head and tail sentinels. The most recently used item is near the head; the least recently used is at the tail. Removing a node and adding it to the front are both O(1) operations when you have pointers to the node and its neighbors.

**Hash map:**

```python
self.lookup: dict[key, Node] = {}
```

Maps keys to their corresponding nodes in the list. Enables O(1) lookup of any item.

---

### The operations

**get(key):**

```python
def get(self, key):
    node = self.lookup.get(key)
    if node is None:
        return None
    # Move to front (most recently used position)
    self._remove(node)
    self._add_to_front(node)
    return node.value
```

The lookup is O(1) via the hash map. The move-to-front is O(1) because we have pointers to the node and its neighbors.

**set(key, value):**

```python
def set(self, key, value):
    node = self.lookup.get(key)
    if node is not None:
        # Key exists; update value and move to front
        node.value = value
        self._remove(node)
        self._add_to_front(node)
    else:
        # New key
        if len(self.lookup) >= self.capacity:
            # Evict least recently used (at the tail)
            lru = self.tail.prev
            self._remove(lru)
            del self.lookup[lru.key]
        # Insert new node
        new_node = Node(key, value)
        self._add_to_front(new_node)
        self.lookup[key] = new_node
```

If the key exists, update the value and move to front. If not, evict the LRU if at capacity, then insert.

---

### Helper methods

```python
def _remove(self, node):
    """Remove a node from the doubly-linked list. O(1)."""
    node.prev.next = node.next
    node.next.prev = node.prev

def _add_to_front(self, node):
    """Insert a node at the front (head) of the list. O(1)."""
    node.next = self.head.next
    node.prev = self.head
    self.head.next.prev = node
    self.head.next = node
```

Both helpers are O(1) because we operate on pointers, not by searching.

---

### Complete implementation

```python
class Node:
    def __init__(self, key=None, value=None):
        self.key = key
        self.value = value
        self.prev = None
        self.next = None


class LRUCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.lookup = {}  # key -> Node

        # Doubly-linked list with sentinel head and tail
        self.head = Node()
        self.tail = Node()
        self.head.next = self.tail
        self.tail.prev = self.head

    def get(self, key):
        node = self.lookup.get(key)
        if node is None:
            return None
        # Mark as recently used
        self._remove(node)
        self._add_to_front(node)
        return node.value

    def set(self, key, value):
        node = self.lookup.get(key)
        if node is not None:
            node.value = value
            self._remove(node)
            self._add_to_front(node)
        else:
            if len(self.lookup) >= self.capacity:
                # Evict the least recently used (just before tail)
                lru = self.tail.prev
                self._remove(lru)
                del self.lookup[lru.key]
            new_node = Node(key, value)
            self._add_to_front(new_node)
            self.lookup[key] = new_node

    def _remove(self, node):
        node.prev.next = node.next
        node.next.prev = node.prev

    def _add_to_front(self, node):
        node.next = self.head.next
        node.prev = self.head
        self.head.next.prev = node
        self.head.next = node
```

The implementation is clean: about 50 lines of code, O(1) for all operations, no corner cases left to handle.

---

### Why the sentinel nodes

The `head` and `tail` are sentinel nodes — they do not hold real data; they exist to simplify edge cases. Without them, "remove the only node" or "add to an empty list" would require special-case code. With them, every operation is uniform:

- Add to front: insert after `head`
- Remove from end: remove the node before `tail`
- Remove from middle: bridge `node.prev` to `node.next`

Sentinel nodes eliminate the need for null checks at the boundaries of the list.

---

### Complexity analysis

| Operation | Time | Space |
|---|---|---|
| `get(key)` | O(1) — hash map lookup + list reinsertion | O(1) |
| `set(key, value)` existing key | O(1) — hash map + list reinsertion | O(1) |
| `set(key, value)` new key, capacity not full | O(1) — insertion | O(1) |
| `set(key, value)` new key, at capacity | O(1) — eviction + insertion | O(1) |
| Total space | O(capacity) for both the hash map and the list | |

All operations are O(1). The total space is O(capacity) regardless of how many items have been seen.

---

## Build It / In Depth

### Variations and extensions

**1. Thread-safety.** The implementation above is not thread-safe. Add a lock:

```python
import threading

class ThreadSafeLRUCache(LRUCache):
    def __init__(self, capacity):
        super().__init__(capacity)
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            return super().get(key)

    def set(self, key, value):
        with self.lock:
            return super().set(key, value)
```

Better: use `threading.RLock` for reentrant access, or shard the lock across multiple LRUs.

**2. TTL-based expiration.** Add a timestamp to each node; evict items older than N seconds:

```python
class TTLCache(LRUCache):
    def __init__(self, capacity, ttl_seconds):
        super().__init__(capacity)
        self.ttl = ttl_seconds

    def get(self, key):
        node = self.lookup.get(key)
        if node is None:
            return None
        if time.time() - node.timestamp > self.ttl:
            self._remove(node)
            del self.lookup[key]
            return None
        # ...
```

**3. Size-based eviction (LFU).** Instead of "least recently used," evict "least frequently used." Track an access count per node and pick the lowest.

**4. Concurrent LRU.** Use a sharded design — N independent LRUs, each with its own lock. Hash the key to a shard. This trades some hit rate for parallelism.

---

### Why this design matters in real systems

LRU caches show up everywhere:

- **Operating systems** — page replacement, buffer cache
- **Databases** — buffer pool for hot pages
- **Web servers** — in-memory cache for hot responses
- **CDNs** — edge cache with LRU eviction
- **CPU caches** — hardware L1/L2/L3 use approximations of LRU

The pattern is universal: a fixed-size cache that holds the most recently used items. Once you understand the doubly-linked-list + hash-map design, you understand every LRU implementation.

---

### Testing the implementation

```python
def test_lru_basic():
    cache = LRUCache(2)
    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.get("a") == 1       # a is now MRU
    cache.set("c", 3)               # evicts "b" (LRU)
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3

def test_lru_capacity():
    cache = LRUCache(1)
    cache.set("a", 1)
    cache.set("b", 2)               # evicts "a"
    assert cache.get("a") is None
    assert cache.get("b") == 2

def test_lru_update():
    cache = LRUCache(2)
    cache.set("a", 1)
    cache.set("a", 100)             # updates without evicting
    assert cache.get("a") == 100

def test_lru_recency():
    cache = LRUCache(2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")                  # a is now MRU; b is LRU
    cache.set("c", 3)               # evicts "b"
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3
```

---

## Use It

### When to use LRU cache in production

| Use case | Why LRU |
|---|---|
| In-memory cache of hot data | Fast access; bounded memory; simple eviction |
| Query result cache | Avoid recomputing expensive queries |
| API response cache | Avoid redundant calls to upstream |
| Page replacement | OS-level memory management |
| Database buffer pool | Keep hot pages in memory |

### When NOT to use LRU

| Situation | Better choice |
|---|---|
| Access patterns are scan-like (no locality) | Random eviction is fine; LRU adds overhead |
| Some items are very hot (long-tail distribution) | LFU (least frequently used) |
| Need TTL semantics | TTL cache (LRU + expiration) |
| Need thread safety | Sharded LRU or external library |
| Need persistence | Use an external cache (Redis, Memcached) |

---

## Common Pitfalls

- **Using only a hash map.** Without ordering, you cannot determine which item to evict.

- **Using only a list.** Without a hash map, lookup is O(n), not O(1).

- **Forgetting to update on get.** A get that does not mark the item as recently used defeats the purpose of "least recently used."

- **Not handling the empty case.** When the cache is empty and capacity is 0, operations should not crash.

- **Mixing up the direction.** Some implementations put MRU at the head, some at the tail. Be consistent; document the choice.

- **Forgetting to clean up the hash map on eviction.** When you evict a node from the list, remove its entry from the hash map too, or memory will leak.

---

## Exercises

1. **Easy** — Implement the LRU cache in your language of choice. Verify that all operations are O(1).

2. **Medium** — Extend the implementation to support TTL: each item has an expiration time; expired items are not returned by `get` and are evicted lazily on access.

3. **Hard** — Design a thread-safe, sharded LRU cache for a high-throughput service. Specify the locking strategy, the sharding function, and the trade-offs you accept.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| LRU cache | A cache | A fixed-size cache that evicts the least recently used item when full |
| Doubly-linked list | A list | A linked list where each node has pointers to both its predecessor and successor; enables O(1) insertion and deletion at any position |
| Hash map | A lookup | A data structure that maps keys to values in expected O(1) time |
| Sentinel node | A dummy | A placeholder node at the head or tail of a linked list used to eliminate edge-case null checks |
| O(1) | Constant time | A performance characteristic where the operation takes the same amount of time regardless of input size |
| Eviction | Removal | The act of removing an item from a cache to make room for a new one |
| TTL | Time to live | A duration after which an item is considered expired and should be removed from a cache |
| Cache locality | Access pattern | The property that recently accessed items are likely to be accessed again; LRU exploits this |

---

## Further Reading

- **"Cache" chapter in "Designing Data-Intensive Applications"** — Martin Kleppmann: https://dataintensive.net/
- **Python's `functools.lru_cache`** — the standard library implementation: https://docs.python.org/3/library/functools.html#functools.lru_cache
- **Java's `LinkedHashMap`** — an LRU-friendly Map implementation: https://docs.oracle.com/javase/8/docs/api/java/util/LinkedHashMap.html
- **Caffeine** — a high-performance Java caching library: https://github.com/ben-manes/caffeine
- **Redis as LRU** — Redis uses approximate LRU eviction: https://redis.io/docs/reference/eviction/