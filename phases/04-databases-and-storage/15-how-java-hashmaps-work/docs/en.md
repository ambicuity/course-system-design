# How Java HashMaps Work?

> A HashMap trades a little memory and a hash function for O(1) average-time key lookup — understanding the internals tells you exactly when that promise holds and when it breaks.

**Type:** Learn
**Prerequisites:** Basic Java Collections, Hash Functions, Big-O Notation
**Time:** ~25 minutes

---

## The Problem

You need to store a user session cache: millions of session tokens, each mapping to a user record. Iterating a plain array to find a matching token is O(n) — at a million entries that's already painfully slow, and at ten million it's unusable. You need O(1) lookup.

A naive sorted array with binary search gives O(log n), which is better, but still means roughly 20 comparisons per lookup at a million entries, and insertion becomes expensive because you have to maintain sorted order. A database index helps in persistent storage, but in-memory you need something faster.

Java's `HashMap` solves this by turning the lookup problem into arithmetic: apply a hash function to the key, jump directly to a small list of candidates, and confirm identity. With a good hash function and a properly sized table, you read one or two memory locations per lookup regardless of how many entries are in the map. But if you choose the wrong initial capacity, a poor key implementation, or you hit adversarial inputs, `HashMap` degrades to O(n). Knowing the internals lets you keep it in the fast path.

---

## The Concept

### Core Structure: Array of Buckets

A `HashMap` is backed by an array called the **table**. Each slot in the array is a **bucket**. A bucket holds zero or more key-value entries.

```
table (array, length = capacity)
 ┌───┬───┬───┬───┬───┬───┬───┬───┐
 │ 0 │ 1 │ 2 │ 3 │ 4 │ 5 │ 6 │ 7 │
 └─┬─┴───┴─┬─┴───┴───┴─┬─┴───┴───┘
   │       │           │
  [A→B]  [C→D]→[E→F]  [G→H]
```

When you call `put(key, value)`:
1. Call `key.hashCode()` to get a 32-bit integer.
2. Apply a secondary mixing step (called **perturbation** in OpenJDK) to spread bits.
3. Mask to the current table length: `index = (n - 1) & hash`.
4. If the bucket at `index` is empty, write the entry there.
5. If the bucket is occupied, **walk the chain** to find a matching key (replace) or append a new node.

On `get(key)`:
1. Recompute the same index.
2. Walk the chain comparing `hash == e.hash && (key == e.key || key.equals(e.key))`.
3. Return the value or `null`.

### Hash Perturbation (Java 8+)

Java's raw `hashCode()` often has weak high bits. The JDK spreads them down:

```java
static final int hash(Object key) {
    int h;
    return (key == null) ? 0 : (h = key.hashCode()) ^ (h >>> 16);
}
```

XOR-ing the upper 16 bits into the lower 16 bits ensures that high-bit differences still affect the bucket index when the table is small.

### Collision Resolution: Linked List → Red-Black Tree

When multiple keys land in the same bucket you have a **collision**. Java resolves it with **separate chaining**.

| Table size / load     | Bucket structure used |
|-----------------------|-----------------------|
| Bucket length < 8     | Singly linked list    |
| Bucket length ≥ 8 **and** table capacity ≥ 64 | Red-black tree (TreeNode) |
| After removal drops below 6 | Converts back to linked list |

The threshold of 8 was chosen statistically: with a good hash function, the probability that any bucket gets 8 entries follows a Poisson distribution with λ ≈ 0.5, so hitting 8 is roughly a one-in-a-million event. When it does happen (adversarial inputs or a broken `hashCode`), the tree gives O(log n) worst-case instead of O(n).

### Load Factor and Resizing

**Load factor** (`default = 0.75`) is the ratio of entries to buckets at which the table doubles:

```
resize threshold = capacity × loadFactor
default: 16 × 0.75 = 12  → resize at 13th entry
```

Resizing **doubles the table** and **rehashes every entry**:

```
Old capacity: 16   (mask: 0b00001111)
New capacity: 32   (mask: 0b00011111)

An entry whose hash bit 4 is 0 stays in the same index.
An entry whose hash bit 4 is 1 moves to (old_index + 16).
```

This is why Java 8 optimizes rehashing: rather than recomputing `(n-1) & hash` for every entry, it checks a single bit and either keeps the entry or moves it `oldCapacity` positions forward.

Resizing is O(n) and creates GC pressure. A `HashMap` that is resized many times will have caused O(n log n) total work and produced a lot of short-lived node arrays.

### Key Requirements: `hashCode` and `equals`

The **contract** Java relies on:

1. If `a.equals(b)`, then `a.hashCode() == b.hashCode()` (mandatory).
2. If `a.hashCode() == b.hashCode()`, `a` and `b` may or may not be equal (collision is allowed).
3. `hashCode` must be consistent: same object, same value across multiple calls (within a JVM session).

Violating rule 1 causes `get` to miss entries that `put` stored. Violating rule 3 with a mutable key causes lookups to fail silently after the key mutates.

---

## Build It / In Depth

### Step 1 — Default construction and first puts

```java
Map<String, Integer> freq = new HashMap<>();
// Initial capacity: 16, load factor: 0.75, threshold: 12

freq.put("apple", 3);
// hash("apple") → some int h
// index = (16-1) & h  → 0..15
// Bucket[index] is empty → create Node{hash, "apple", 3, next=null}

freq.put("banana", 1);
freq.put("cherry", 5);
```

### Step 2 — Collision scenario

```java
// Suppose hash("aa") and hash("BB") both produce the same bucket index
// (happens with Objects whose hashCode has the same lower bits)

Map<String, Integer> m = new HashMap<>(4);  // capacity 4, threshold 3
m.put("aa", 1);   // → bucket 1: [aa→1]
m.put("BB", 2);   // → bucket 1: [aa→1] → [BB→2]  (collision, chained)

// get("BB"):
// 1. compute index → 1
// 2. walk chain: aa.equals("BB")? No. BB.equals("BB")? Yes → return 2
```

### Step 3 — Pre-sizing to avoid resizing

If you know you will insert N entries, set initial capacity to avoid resize:

```java
// Target: insert 1000 entries, no resize
// capacity needed = ceil(N / loadFactor) = ceil(1000 / 0.75) = 1334
// HashMap rounds up to next power-of-two: 2048

Map<String, String> cache = new HashMap<>(2048);
```

Or use the Guava helper pattern that handles the math:

```java
// Equivalent pattern:
int expectedSize = 1000;
int capacity = (int) Math.ceil(expectedSize / 0.75) + 1;
Map<String, String> cache = new HashMap<>(capacity);
```

### Step 4 — Observing tree conversion (conceptual)

```java
// Craft keys that all hash to the same bucket (break the hash contract intentionally)
// Java will convert the bucket to a red-black tree after 8 entries

// Real-world indicator: a HashMap with millions of entries where a few
// String keys share the same String.hashCode() → those buckets become trees.
// Performance stays O(log k) not O(k) — Java 8 saved you here.
```

### Internal node anatomy

```
// LinkedList node (Java 8 HashMap.Node)
class Node<K,V> {
    final int hash;      // cached hash — avoids recomputing on rehash
    final K key;
    V value;
    Node<K,V> next;      // pointer to next node in bucket chain
}

// Tree node (HashMap.TreeNode extends LinkedHashMap.Entry)
// Adds: parent, left, right, red/black flag
// Size overhead per node: ~48 bytes vs. ~32 bytes for plain Node
```

---

## Use It

### Where HashMaps appear in real systems

| System / layer        | Typical HashMap usage                          | Key concern                              |
|-----------------------|------------------------------------------------|------------------------------------------|
| JVM method dispatch   | Virtual method table lookup by descriptor      | Must never resize at runtime             |
| DNS / routing caches  | IP → record TTL                                | Expiry; ConcurrentHashMap preferred      |
| Spring bean registry  | Bean name → bean instance                      | Read-heavy after startup; safe           |
| Kafka consumer state  | Partition offset map                           | Small map, frequent updates              |
| Redis (C equivalent)  | Underlying dict uses same design               | Incremental rehash avoids O(n) spikes    |

### When to use alternatives

| Need                                    | Use instead of HashMap    |
|-----------------------------------------|---------------------------|
| Thread safety                           | `ConcurrentHashMap`       |
| Maintain insertion order                | `LinkedHashMap`           |
| Natural key order                       | `TreeMap`                 |
| Primitives (avoid boxing overhead)      | Eclipse Collections `IntIntHashMap` or Agrona `Int2IntHashMap` |
| Memory-critical, millions of entries    | Custom open-addressing map (e.g., `HashObjIntMap` from Koloboke) |

`ConcurrentHashMap` uses **segment-level locking** (Java 7) and later **CAS + synchronized on the bucket head** (Java 8) — it does not lock the whole table, so reads are usually lock-free.

---

## Common Pitfalls

- **Using mutable objects as keys.** If you mutate a key after insertion, its `hashCode` changes and you can never retrieve the value again. The entry is still in the map — consuming memory — but it's effectively lost. Use immutable keys (String, Integer, record classes).

- **Not overriding both `hashCode` and `equals`.** If you override `equals` without `hashCode`, two logically-equal keys will land in different buckets and the map stores duplicates. The JVM gives you no warning.

- **Ignoring initial capacity on bulk inserts.** Creating a `HashMap()` and inserting 100,000 entries triggers ~13 resize operations (16 → 32 → ... → 131072). Each resize copies and rehashes every entry. Pre-size with `new HashMap<>(initialCapacity)`.

- **Treating `HashMap` as thread-safe.** Concurrent `put` from two threads can corrupt the internal linked list (infinite loop in Java 6 during resize — the notorious "HashMap death loop"). Always use `ConcurrentHashMap` in multi-threaded contexts.

- **Assuming iteration order is insertion order.** `HashMap` makes zero guarantees about iteration order and can change it across JVM versions. Use `LinkedHashMap` if order matters. Never write code whose correctness depends on HashMap iteration order.

---

## Exercises

1. **Easy** — Create a `HashMap<Character, Integer>` that counts the frequency of each character in the string `"mississippi"`. Print the entries. Explain which bucket each character lands in if the table capacity is 16.

2. **Medium** — Implement a simple cache with a maximum of 100 entries using `LinkedHashMap` with access-order mode (`accessOrder = true`). Override `removeEldestEntry` so the least-recently-used entry is evicted automatically. Compare this to using a plain `HashMap` for the same job.

3. **Hard** — Write a class `BadKey` whose `hashCode` always returns `42` and `equals` compares by field value. Insert 10,000 `BadKey` instances into a `HashMap`. Measure and compare get-time latency versus a `HashMap` with well-distributed keys. Then explain at what bucket size Java switches to a red-black tree and what effect that has on your latency measurements.

---

## Key Terms

| Term            | What people think                               | What it actually means                                                                                   |
|-----------------|-------------------------------------------------|----------------------------------------------------------------------------------------------------------|
| **Bucket**      | A row in the HashMap                            | One slot in the backing array; holds the head of a linked list or tree of entries sharing the same index |
| **Load factor** | How "full" the map is right now                 | A threshold ratio (default 0.75) that triggers a resize when `size / capacity` exceeds it               |
| **Collision**   | A bug or failure condition                      | A normal, expected event when two keys hash to the same bucket index; handled by chaining               |
| **Rehashing**   | Recomputing `hashCode()`                        | Recomputing bucket indices for every entry after the table doubles in size                               |
| **TreeNode**    | Something exotic / rarely used                  | The node type Java uses in a bucket once it exceeds 8 entries; enables O(log n) worst-case per bucket    |
| **`hashCode`**  | A unique ID for an object                       | A 32-bit integer that need not be unique; two different objects can share the same value                 |
| **Capacity**    | The number of entries in the map                | The length of the backing array (number of buckets), always a power of two in Java's implementation     |

---

## Further Reading

- [OpenJDK HashMap source (Java 21)](https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/util/HashMap.java) — read the class-level Javadoc comment; it explicitly states the threshold logic, load factor rationale, and tree conversion rules.
- [JEP 180: Handle Frequent HashMap Collisions with Balanced Trees](https://openjdk.org/jeps/180) — the original proposal that introduced TreeNode in Java 8, with the Poisson distribution justification for the threshold of 8.
- [Java Collections Framework official docs](https://docs.oracle.com/en/java/docs/books/tutorial/collections/index.html) — Oracle's canonical tutorial covering HashMap, LinkedHashMap, and ConcurrentHashMap with use-case guidance.
- [Effective Java, 3rd Edition — Item 11: "Always override hashCode when you override equals"](https://www.oreilly.com/library/view/effective-java-3rd/9780134686097/) — Joshua Bloch's definitive treatment of the hashCode/equals contract with worked examples.
- [ConcurrentHashMap internals (Java 8+)](https://docs.oracle.com/en/java/docs/books/tutorial/essential/concurrency/collections.html) — explains the shift from segment locking to CAS-based bucket-head synchronization and why most reads are lock-free.
