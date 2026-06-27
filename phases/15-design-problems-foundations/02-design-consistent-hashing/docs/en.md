# Design Consistent Hashing

## Chapter Overview
This chapter explores consistent hashing as a solution for distributing requests and data efficiently across servers in horizontally scaled systems. It addresses problems with traditional modulo-based hashing and presents a scalable alternative.

## The Rehashing Problem

### Traditional Hash Distribution
The basic load balancing formula:
```
serverIndex = hash(key) % N
```
where N represents the total number of servers in the pool.

### Example Distribution (4 Servers)
The chapter provides a table showing 8 keys with their hash values and modulo results:
- key0: hash=18358617, hash%4=1
- key1: hash=26143584, hash%4=0
- key2: hash=18131146, hash%4=2
- key3: hash=35863496, hash%4=0
- key4: hash=34085809, hash%4=1
- key5: hash=27581703, hash%4=3
- key6: hash=38164978, hash%4=2
- key7: hash=22530351, hash%4=3

### Critical Problem: Server Removal
When server 1 goes offline, the pool shrinks to 3 servers. Using `hash % 3` instead:
- Most keys require remapping to different servers
- The same hash values produce different server indices
- Cache clients connect to incorrect servers
- Results in widespread cache misses ("storm of cache misses")

This illustrates why traditional modulo hashing fails in dynamic environments.

---

## Consistent Hashing Foundation

### Definition
Per Wikipedia, consistent hashing is "a special kind of hashing such that when a hash table is re-sized and consistent hashing is used, only k/n keys need to be remapped on average, where k is the number of keys, and n is the number of slots."

**Key Advantage:** Unlike traditional hash tables where most keys must be remapped during resizing, consistent hashing minimizes redistribution.

### Hash Space Concept
- Uses SHA-1 as the hash function
- Output range: 0 to 2^160 - 1
- Denoted as: x0, x1, x2, x3, …, xn
- Creates a continuous space of possible hash values

### Hash Ring Structure
The linear hash space is transformed into a circular ring by "collecting both ends." This creates a continuous structure where:
- Values wrap around (0 follows 2^160 - 1)
- Positions on the ring are uniform
- Enables the clockwise lookup mechanism

---

## Core Implementation: Three Mapping Steps

### Step 1: Map Servers to Ring
Using SHA-1 hash function, place servers onto the ring:
- Server 0, Server 1, Server 2, Server 3 each get positions
- Positions determined by `hash(server_IP_or_name)`
- No modulo operation applied

### Step 2: Map Keys to Ring
Similarly hash cache keys:
- key0, key1, key2, key3 get positions on the same ring
- Uses same hash function as servers
- No modulo operation

### Step 3: Server Lookup (Clockwise Traversal)
To find a key's location:
1. Start at the key's position on the ring
2. Move clockwise around the ring
3. Stop at the first server node encountered
4. That server stores the key

**Example from text:** "Going clockwise, key0 is stored on server 0; key1 is stored on server 1; key2 is stored on server 2 and key3 is stored on server 3."

---

## Dynamic Server Operations

### Adding a Server
When server 4 is added:
- Only affected keys are those between the new server and the previous server (going counter-clockwise)
- In the example: only key0 needs redistribution
- key0 moves from server 0 to server 4
- key1, key2, key3 remain unchanged

**Benefit:** Minimal data movement compared to traditional hashing

### Removing a Server
When server 1 is removed:
- Affected range: keys between the removed server and the previous server (counter-clockwise)
- In the example: only key1 needs redistribution
- key1 moves from server 1 to server 2
- key0, key2, key3 remain on original servers

**Benefit:** Only small fraction of keys require remapping

---

## Two Critical Problems in Basic Approach

### Problem 1: Unbalanced Partition Sizes
**Issue:** Cannot maintain uniform partition sizes when servers are added/removed. A partition is the hash space between adjacent servers.

**Example:** If server 1 is removed, server 2's partition becomes twice as large as server 0 and server 3's partitions.

**Impact:** Uneven load distribution and resource utilization

### Problem 2: Non-Uniform Key Distribution
**Issue:** Keys may not distribute evenly across servers on the ring.

**Example:** Most keys concentrate on server 2, while server 1 and server 3 have no data.

**Impact:** Creates "hotspot" scenarios with uneven server loads

**Solution:** Virtual nodes (replicas) address both problems.

---

## Virtual Nodes / Replicas

### Concept
Instead of one position per server, each server is represented by multiple virtual nodes (replicas) on the ring.

### Implementation Details
- Each real server gets multiple virtual node positions
- Server 0 represented as: s0_0, s0_1, s0_2 (example uses 3 replicas)
- Server 1 represented as: s1_0, s1_1, s1_2
- Each server manages partitions labeled with its identity

### Key Lookup with Virtual Nodes
To find where key0 is stored:
1. Start from key0's position
2. Move clockwise
3. Find first virtual node (example: s1_1)
4. Determine associated server (server 1)

### Impact on Distribution

The text notes that with virtual nodes, "the standard deviation gets smaller with more virtual nodes, leading to balanced data distribution."

**Research findings:**
- 100 virtual nodes: 10% standard deviation from mean
- 200 virtual nodes: 5% standard deviation from mean
- Higher virtual node counts produce more balanced distribution

### Tradeoff Analysis
**Advantages:** More balanced key distribution, improved load distribution

**Disadvantage:** Increased memory overhead for storing virtual node metadata

**Resolution:** Tune the number based on system requirements

---

## Finding Affected Keys During Changes

### Adding a New Server
Process for identifying keys to redistribute:
1. Start at the newly added server position
2. Move counter-clockwise around the ring
3. Stop when encountering another server
4. All keys between these two points are affected

**Example:** When server 4 is added, keys between s3 and s4 must move to server 4.

### Removing an Existing Server
Process for identifying keys to redistribute:
1. Start at the removed server position
2. Move counter-clockwise around the ring
3. Stop when encountering another server
4. Redistribute those keys to the next server clockwise

**Example:** When server 1 is removed, keys between s0 and s1 are redistributed to server 2.

---

## Benefits Summary

### Minimal Key Redistribution
"Minimized keys are redistributed when servers are added or removed."

### Horizontal Scalability
"It is easy to scale horizontally because data are more evenly distributed."

### Hotspot Mitigation
The text explains that "excessive access to a specific shard could cause server overload. Imagine data for Katy Perry, Justin Bieber, and Lady Gaga all end up on the same shard. Consistent hashing helps to mitigate the problem by distributing the data more evenly."

---

## Real-World Applications

### Industry Implementations
- **Amazon Dynamo:** Partitioning component of the key-value store
- **Apache Cassandra:** Data partitioning across clusters
- **Discord:** Chat application infrastructure
- **Akamai:** Content delivery network
- **Maglev:** Google's software network load balancer

---

## Key Takeaways

1. **Problem Solved:** Consistent hashing reduces key redistribution from O(n) to O(n/m) operations, where n is keys and m is servers

2. **Ring Structure:** Converting hash space to a ring enables elegant clockwise traversal for server lookup

3. **Virtual Nodes:** Essential for achieving balanced distribution in production systems

4. **Scalability:** Supports dynamic server addition/removal with minimal data movement

5. **Industry Standard:** Proven approach used by major infrastructure companies
