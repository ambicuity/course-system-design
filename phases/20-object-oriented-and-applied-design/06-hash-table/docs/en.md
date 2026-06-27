# Design a Hash Table

> A canonical object-oriented design kata — implementing a hash table with separate chaining, O(1) average operations.

**Type:** Design kata
**Prerequisites:** Object-oriented programming, basic hashing
**Time:** ~25 minutes

---

## The Problem

The hash table is the most-used data structure in computing. Every dictionary, every set, every cache lookup, every database index ultimately depends on a hash table. Understanding how it works — and what makes it O(1) average — is foundational.

This kata walks through designing a hash table from scratch: the hash function, the bucket array, separate chaining for collision resolution, and the operations. The implementation here uses integer keys and chained lists; the same pattern generalizes to any key type with a hash function.

---

## The Concept

### The problem

Design a data structure that supports:

- `set(key, value)` — store a value for a key; if the key exists, update the value
- `get(key)` — retrieve the value for a key; return null if not present
- `remove(key)` — delete the key-value pair

**Constraints:**

- All operations should be O(1) on average
- Keys are integers (in this version)
- Collisions are resolved by separate chaining
- No load factor handling — assume inputs fit in memory

The hash table uses a hash function to map keys to array indices. Each array slot (bucket) holds a list of (key, value) pairs that hashed to that index.

---

### Why a hash table works

The hash function maps a key to an array index. If the function distributes keys uniformly across the array, then with N keys in an array of M buckets, the average bucket has N/M items. As long as M grows with N, the average lookup is O(1).

```
   Hash function: h(key) = key % size

   Insert key=42:
     bucket = 42 % 10 = 2
     Append (42, value) to bucket 2

   Insert key=17:
     bucket = 17 % 10 = 7
     Append (17, value) to bucket 7

   Insert key=12:
     bucket = 12 % 10 = 2
     Append (12, value) to bucket 2  ← collision with 42

   Lookup key=42:
     bucket = 42 % 10 = 2
     Search bucket 2: [42, value] → return value

   Lookup key=99:
     bucket = 99 % 10 = 9
     Search bucket 9: empty → return null
```

The hash function is the heart. A good function distributes keys uniformly; a bad function clusters them, degrading performance to O(n).

---

### Collision resolution: separate chaining

When two keys hash to the same bucket, we have a collision. Two main strategies:

**Separate chaining** (what we implement): each bucket is a list; colliding keys go into the same list.

```
   Array of buckets:
     [0] -> null
     [1] -> (11, "a") -> null
     [2] -> (42, "b") -> (12, "c") -> null       ← collision handled
     [3] -> null
     ...
     [9] -> null
```

**Open addressing** (alternative): on collision, probe to the next bucket. Variants: linear probing, quadratic probing, double hashing.

Separate chaining is simpler and degrades more gracefully under load. Open addressing has better cache locality but is more sensitive to load factor.

---

### The implementation

```python
class Item:
    """A single key-value pair stored in a bucket's chain."""
    def __init__(self, key, value):
        self.key = key
        self.value = value


class HashTable:
    """Hash table with separate chaining."""

    def __init__(self, size):
        self.size = size
        self.table = [[] for _ in range(self.size)]   # array of empty lists

    def _hash_function(self, key):
        return key % self.size

    def set(self, key, value):
        """Insert or update a key-value pair. O(1) average."""
        hash_index = self._hash_function(key)
        bucket = self.table[hash_index]
        for item in bucket:
            if item.key == key:
                item.value = value      # update existing
                return
        bucket.append(Item(key, value))  # insert new

    def get(self, key):
        """Retrieve the value for a key. O(1) average."""
        hash_index = self._hash_function(key)
        for item in self.table[hash_index]:
            if item.key == key:
                return item.value
        raise KeyError(f"Key {key} not found")

    def remove(self, key):
        """Delete a key-value pair. O(1) average."""
        hash_index = self._hash_function(key)
        bucket = self.table[hash_index]
        for index, item in enumerate(bucket):
            if item.key == key:
                del bucket[index]
                return
        raise KeyError(f"Key {key} not found")
```

The structure is straightforward:

- An array of buckets, each bucket initialized as an empty list
- A hash function that maps keys to bucket indices
- `set` walks the bucket looking for an existing key; updates or appends
- `get` walks the bucket looking for the key; raises if not found
- `remove` walks the bucket looking for the key; deletes from the list if found

---

### Why this is O(1) average

The performance depends on the **load factor**: `load = N / M`, where N is the number of keys and M is the number of buckets.

- When `load` is small (few items per bucket), lookups are fast.
- When `load` grows (many items per bucket), lookups slow down — but only linearly with load.
- **Resizing** (growing the array and rehashing) keeps `load` bounded.

For this kata, we do not implement resizing. In production, every real hash table resizes when load exceeds a threshold (typically 0.75 for Java's `HashMap`, 2/3 for Python's dict).

With resizing, the amortized cost of operations is O(1):

- Most operations are O(1)
- Occasionally an operation triggers a resize, which is O(N)
- Amortized over many operations, the cost is O(1) per operation

---

### The hash function

For integer keys, `key % size` works. For arbitrary keys, you need a hash function that distributes them uniformly.

**For strings:**

```python
def hash_string(s, table_size):
    hash_value = 0
    for char in s:
        hash_value = (hash_value * 31 + ord(char)) % table_size
    return hash_value
```

**For tuples or objects:**

```python
def hash_object(obj, table_size):
    # Combine hashes of attributes
    return hash((obj.attr1, obj.attr2)) % table_size
```

**Properties of a good hash function:**

- **Deterministic** — same key always produces the same hash
- **Uniform** — distributes keys evenly across buckets
- **Fast** — O(1) to compute
- **Avalanche** — small changes in input produce large changes in output

Cryptographic hash functions (SHA-256) have these properties but are slow. Non-cryptographic hash functions (FNV, Murmur, CityHash) are used in most hash table implementations.

---

## Build It / In Depth

### Why each design choice

**Separate chaining over open addressing:**

- Simpler implementation
- Degrades gracefully under high load (chains grow but operations stay O(chain length))
- Easier to delete (open addressing requires careful tombstoning)

**Buckets as lists:**

- Dynamic size — no fixed bucket capacity
- Easy to append, search, delete
- Python lists are array-backed, so iteration is fast

**Integer modulo as the hash:**

- Simple, O(1)
- Distributes keys reasonably uniformly when `size` is chosen well (typically a prime)
- Allows negative keys in Python (`-1 % 10 == 9`)

**No load factor handling:**

- Simplifies the kata
- In production, resizing is essential for performance

---

### Testing the implementation

```python
def test_hash_table_basic():
    ht = HashTable(10)
    ht.set(1, "one")
    ht.set(2, "two")
    assert ht.get(1) == "one"
    assert ht.get(2) == "two"

def test_hash_table_update():
    ht = HashTable(10)
    ht.set(1, "one")
    ht.set(1, "uno")                # update
    assert ht.get(1) == "uno"

def test_hash_table_collisions():
    ht = HashTable(10)
    ht.set(1, "a")                  # bucket 1
    ht.set(11, "b")                 # bucket 1 (collision)
    ht.set(21, "c")                 # bucket 1 (collision)
    assert ht.get(1) == "a"
    assert ht.get(11) == "b"
    assert ht.get(21) == "c"

def test_hash_table_remove():
    ht = HashTable(10)
    ht.set(1, "one")
    ht.set(2, "two")
    ht.remove(1)
    with pytest.raises(KeyError):
        ht.get(1)
    assert ht.get(2) == "two"

def test_hash_table_missing_key():
    ht = HashTable(10)
    with pytest.raises(KeyError):
        ht.get(99)
```

---

### Resizing for production

In production, you would add resizing:

```python
class ResizableHashTable(HashTable):
    def __init__(self, initial_size=16):
        super().__init__(initial_size)
        self.threshold = int(initial_size * 0.75)

    def set(self, key, value):
        super().set(key, value)
        # Check if we need to resize
        if sum(len(bucket) for bucket in self.table) > self.threshold:
            self._resize()

    def _resize(self):
        old_table = self.table
        self.size = self.size * 2
        self.table = [[] for _ in range(self.size)]
        for bucket in old_table:
            for item in bucket:
                self.set(item.key, item.value)   # rehash into new buckets
```

When the load factor exceeds 0.75, double the array size and rehash all existing keys. Amortized cost is O(1) per operation.

---

### Comparison with other data structures

| Operation | Hash table | Sorted array | Balanced BST | Linked list |
|---|---|---|---|---|
| Insert | O(1) avg | O(n) | O(log n) | O(1) |
| Lookup | O(1) avg | O(log n) | O(log n) | O(n) |
| Delete | O(1) avg | O(n) | O(log n) | O(1) |
| Ordered iteration | ❌ | ✅ | ✅ | ✅ |
| Memory overhead | High | Low | Medium | Low |

Hash tables trade memory and lack of ordering for O(1) operations. They are the right choice when you need fast lookup and do not need ordered iteration.

---

## Use It

### When to use a hash table

| Situation | Use hash table |
|---|---|
| Need fast lookup by key | Yes |
| Need to store key-value pairs | Yes |
| Need ordered iteration | No — use a sorted structure |
| Need range queries | No — use a tree |
| Memory-constrained | Maybe — hash tables have overhead |

### Where hash tables show up

| Use case | Implementation |
|---|---|
| Python `dict` and `set` | Open-addressed hash table with perturbation |
| Java `HashMap` | Separate chaining (now) with tree fallback for long chains |
| JavaScript `Map` and `Object` | Hash table |
| C++ `unordered_map` | Hash table |
| Redis keys | Hash table |
| Database indexes | B+ tree (not hash — for range queries), but hash indexes exist |
| Caches | Hash table for fast lookup |
| Sets / membership testing | Hash table |

---

## Common Pitfalls

- **Bad hash function.** A hash function that clusters keys destroys performance. Use a well-known function.

- **Ignoring load factor.** Without resizing, performance degrades as items are added. Always resize.

- **Mutable keys.** If a key's hash changes after insertion (e.g., the object is modified), the item becomes unreachable. Use immutable keys.

- **Hash collisions as a security issue.** Adversarial inputs can exploit bad hash functions to cause O(n) lookups. Use randomized hash seeds (Python's `PYTHONHASHSEED`) or cryptographic hash functions.

- **Confusing identity with equality.** Two equal keys should hash to the same bucket. Define `__hash__` and `__eq__` consistently in custom objects.

---

## Exercises

1. **Easy** — Implement the hash table in your language of choice. Test with collisions, updates, and removals.

2. **Medium** — Add resizing to your implementation. Trigger a resize when load factor exceeds 0.75. Verify that operations remain O(1) amortized.

3. **Hard** — Design a thread-safe hash table. Specify the locking strategy and how it interacts with resizing.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Hash table | A lookup | A data structure that maps keys to values in expected O(1) time using a hash function and an array of buckets |
| Hash function | A sum | A function that maps keys to array indices; should be deterministic, uniform, fast, and have avalanche properties |
| Collision | A bug | When two keys hash to the same bucket; resolved by chaining (list per bucket) or open addressing (probe to next slot) |
| Load factor | A number | The ratio of items to buckets (N/M); high load factor degrades hash table performance; resize when it exceeds a threshold |
| Separate chaining | A strategy | A collision resolution strategy where each bucket is a list; colliding keys are stored in the same list |
| Open addressing | A strategy | A collision resolution strategy where collisions are resolved by probing to other buckets (linear, quadratic, double hashing) |
| Resizing | A rehash | The act of growing (or shrinking) the bucket array and rehashing all keys; amortized O(1) per operation |
| Amortized cost | Average cost | The total cost of a sequence of operations divided by the number of operations; resizing's cost is amortized over many operations |

---

## Further Reading

- **"Introduction to Algorithms" (CLRS)** — the canonical hash table chapter: https://mitpress.mit.edu/9780262033848/
- **Python's dict implementation** — a beautifully compact hash table: https://github.com/python/cpython/blob/main/Objects/dictobject.c
- **"The Mighty Hash"** — a deep dive into hash function design: https://github.com/jamesroutley/algorithms-and-data-structures
- **Swiss Tables (absl::flat_hash_map)** — Google's modern hash table design: https://abseil.io/docs/cpp/guides/container