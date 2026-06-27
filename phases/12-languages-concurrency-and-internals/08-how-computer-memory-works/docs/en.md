# How Computer Memory Works?

> Memory is not one thing — it is a pyramid of speed-size trade-offs, and the gap between levels determines most of your application's latency.

**Type:** Learn
**Prerequisites:** Operating Systems Basics, CPU Architecture Overview, Processes and Threads
**Time:** ~35 minutes

---

## The Problem

You write a tight inner loop in C or Java, profile it, and find that 90% of wall time is spent waiting — not computing. The CPU is idle most of the time. You add more cores, but throughput barely improves. You're baffled because algorithmic complexity looks fine.

The real culprit is the memory subsystem. Modern CPUs execute billions of instructions per second, but accessing main RAM takes ~100 ns — roughly 300 CPU cycles on a 3 GHz chip. If your working set does not fit in cache, the CPU literally sits idle waiting for data to arrive from DRAM. This is called a **cache miss**, and at scale it kills performance.

Beyond raw speed, misunderstanding memory leads to other production incidents: heap exhaustion causing OOM kills, stack overflows from deep recursion, virtual-address space exhaustion in 32-bit processes, cache-line false sharing that serializes threads on different cores, and memory leaks that slowly degrade long-running services. Every system designer needs a working mental model of how memory is structured, how the CPU navigates it, and where the performance cliffs are.

---

## The Concept

### The Memory Hierarchy

Memory is organized as a pyramid. Each tier is faster but smaller and more expensive than the one below it.

```
            ┌────────────────────────────┐
            │        CPU Registers       │  ~0.3 ns   |  ~1 KB total
            ├────────────────────────────┤
            │        L1 Cache            │  ~1 ns     |  32-64 KB per core
            ├────────────────────────────┤
            │        L2 Cache            │  ~4 ns     |  256 KB – 1 MB per core
            ├────────────────────────────┤
            │        L3 Cache            │  ~10-40 ns |  4-64 MB shared
            ├────────────────────────────┤
            │        DRAM (RAM)          │  ~60-100 ns|  4-512 GB
            ├────────────────────────────┤
            │   SSD / NVMe Storage       │  ~50-100 µs|  100s of GB – TBs
            ├────────────────────────────┤
            │   HDD / Network Storage    │  ~5-10 ms  |  Practically unlimited
            └────────────────────────────┘
```

The numbers above are approximate but order-of-magnitude correct. The jump from L3 to DRAM (roughly 10×) and from DRAM to SSD (roughly 1000×) are the two most consequential cliffs for application performance.

---

### Registers

Registers live inside the CPU die itself. A modern x86-64 core has 16 general-purpose 64-bit registers (`rax`, `rbx`, `rsp`, `rip`, …) plus SIMD registers (XMM/YMM/ZMM). Operands must be in registers before the ALU can operate on them. Register access has zero latency from the CPU's perspective — they are part of the execution pipeline.

---

### CPU Caches (L1 / L2 / L3)

Caches are SRAM — faster, more power-hungry, and physically larger per bit than DRAM. The hardware manages them transparently; you never address cache directly.

**Cache lines** are the unit of transfer. On x86 and ARM, one cache line is 64 bytes. When the CPU reads a single byte from DRAM, the entire 64-byte line containing that byte is pulled into cache. This is why **spatial locality** matters: if you access `array[0]`, the hardware also loads `array[1]` through roughly `array[7]` (for 8-byte elements) for free.

**Cache lookup flow:**

```
CPU requests address X
│
├─ L1 hit?  ──YES──► return data (~1 ns)
│
├─ L2 hit?  ──YES──► promote to L1, return (~4 ns)
│
├─ L3 hit?  ──YES──► promote to L1/L2, return (~10-40 ns)
│
└─ DRAM fetch ──────► ~60-100 ns, fill cache line, promote
```

**Set-associative mapping:** Caches are divided into sets and ways. An 8-way set-associative cache means each set can hold 8 cache lines. When a new line evicts an old one, the hardware uses a replacement policy (usually LRU or pseudo-LRU). Cache conflicts (multiple hot addresses mapping to the same set) cause thrashing even when the total working set fits in cache.

**Write policies:**
- **Write-through:** Every write goes to DRAM immediately — simple, but slow for write-heavy workloads.
- **Write-back:** Writes go to cache first; DRAM is updated only when the dirty line is evicted. Higher performance, but requires careful coherence logic in multi-core chips.

---

### Cache Coherence (Multi-Core)

In a multi-core system, each core has its own L1 and L2. If core 0 and core 1 both cache the same memory location and core 0 writes it, core 1 must see the updated value — this is the **cache coherence problem**.

Modern CPUs implement the **MESI protocol** (Modified, Exclusive, Shared, Invalid). A cache line is tagged with its state:

| State    | Meaning                                         |
|----------|-------------------------------------------------|
| Modified | Only this core has it; DRAM is stale            |
| Exclusive| Only this core has it; matches DRAM             |
| Shared   | Multiple cores have a clean read-only copy      |
| Invalid  | Line is stale; must be re-fetched               |

When core 0 writes a Shared line, it broadcasts an **invalidate** message. All other cores set their copy to Invalid. The next read from another core triggers a cache miss and a coherence fetch. This is why **false sharing** is devastating: two threads modifying different variables that happen to live in the same 64-byte cache line are constantly invalidating each other's cache lines even though they never touch the same logical data.

---

### DRAM — Main Memory

DRAM stores data as charge in capacitors, which must be refreshed thousands of times per second. This refresh cycle, combined with row activation overhead, explains why DRAM is slow compared to SRAM.

DRAM is organized as **rows and columns**. Accessing data in the same DRAM row (a "row hit") is faster than crossing a row boundary (a "row conflict" requiring row precharge + activate). This is why sequential memory access patterns are significantly faster than random access even within DRAM — the memory controller can optimize row-hit sequences.

**Typical DRAM parameters (DDR5 example):**
- Bandwidth: ~50–80 GB/s per channel
- Latency: CL40 @ 4800 MT/s ≈ ~17 ns best-case; effective latency with controller overhead ≈ 60–100 ns
- Capacity: 8–64 GB per DIMM

---

### Virtual Memory

Physical addresses are what the hardware DRAM controller understands. Virtual addresses are what every user-space process uses. The OS and MMU (Memory Management Unit) translate between them.

**Why virtual addresses?**
1. Isolation: process A's virtual address `0x7fff1000` maps to a different physical page than process B's `0x7fff1000`.
2. Overcommit: the virtual address space can exceed physical RAM; unused pages stay on disk.
3. Contiguous illusion: a process sees a flat address space even though its physical pages are scattered.

**Page tables** store the virtual→physical mapping. A page is typically 4 KB. A 64-bit process with a 48-bit virtual address space has ~256 TB of addressable space, mapped via a 4-level (or 5-level on newer x86-64) radix tree.

```
Virtual Address (48-bit x86-64)
┌──────────┬──────────┬──────────┬──────────┬────────────────┐
│  PML4 (9)│  PDPT (9)│   PD (9) │   PT (9) │  Offset (12)   │
└──────────┴──────────┴──────────┴──────────┴────────────────┘
     ↓           ↓          ↓          ↓
  4 table walks × ~4ns each = up to 16 ns just for address translation
```

**TLB — Translation Lookaside Buffer:** A small hardware cache (typically 64–4096 entries) that caches recent virtual→physical translations. A TLB hit costs ~1 ns; a TLB miss triggers a full page-table walk. A process with a working set covering thousands of 4 KB pages suffers frequent TLB misses. Using **huge pages** (2 MB or 1 GB) drastically reduces TLB pressure.

---

### Stack vs Heap

Every thread has a **stack** — a contiguous region of memory used for function call frames, local variables, and return addresses. The OS allocates it at thread creation (default 8 MB on Linux). The stack grows downward on x86. Allocation is `O(1)`: just decrement the stack pointer.

The **heap** is a large pool managed by the allocator (`malloc`/`free`, `new`/`delete`, or language runtime GC). Heap allocation involves finding a suitable free block, potentially merging or splitting blocks, and updating allocator metadata — orders of magnitude more expensive than stack allocation. It also produces fragmentation over time.

```
High address  ┌────────────────────────┐
              │      Stack             │ ← grows downward
              │       ↓                │
              │  (unmapped guard page) │
              │       ↑                │
              │      Heap              │ ← grows upward
              │   (mmap / brk)         │
              │  BSS / Data / Text     │
Low address   └────────────────────────┘
```

---

### Memory Alignment

CPUs read aligned addresses faster, and some architectures (e.g., ARM before v8) raise a bus error on unaligned access. An 8-byte `int64` at address `0x8` is aligned (divisible by 8); at `0x5` it is not.

Compilers insert **padding** into structs to maintain alignment:

```c
// Naive layout: 14 bytes of fields → 24 bytes due to padding
struct Bad {
    char   a;    // 1 byte + 7 padding
    double b;    // 8 bytes
    char   c;    // 1 byte + 7 padding
    int32_t d;   // 4 bytes
};

// Reordered: 14 bytes of fields → 16 bytes
struct Good {
    double  b;   // 8 bytes
    int32_t d;   // 4 bytes
    char    a;   // 1 byte
    char    c;   // 1 byte
                 // 2 bytes padding to align struct size to 8
};
```

---

### NUMA — Non-Uniform Memory Access

Servers with multiple CPU sockets have NUMA topology. Each socket has local DRAM attached directly to it. Accessing remote DRAM (across the inter-socket interconnect, e.g., Intel UPI or AMD Infinity Fabric) adds 30–100% latency.

An application that allocates memory on node 0 but runs threads on node 1 is NUMA-distant and suffers hidden latency. Linux exposes `numactl` and `mbind()` to control affinity.

---

## Build It / In Depth

### Observing Cache Behavior in Practice

**Step 1 — Sequential vs random access latency:**

```c
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#define N (1 << 26)   // 64 MB — larger than L3 on most laptops

int main() {
    int *arr = (int *)malloc(N * sizeof(int));
    for (int i = 0; i < N; i++) arr[i] = i;

    // Sequential — hardware prefetcher helps; mostly L3/DRAM hits along cache lines
    clock_t t0 = clock();
    long sum = 0;
    for (int i = 0; i < N; i++) sum += arr[i];
    clock_t t1 = clock();

    // Random — defeats prefetcher; nearly every access is a DRAM round-trip
    // Build a random permutation to avoid compiler tricks
    int *perm = (int *)malloc(N * sizeof(int));
    for (int i = 0; i < N; i++) perm[i] = i;
    for (int i = N - 1; i > 0; i--) {
        int j = rand() % (i + 1);
        int tmp = perm[i]; perm[i] = perm[j]; perm[j] = tmp;
    }

    clock_t t2 = clock();
    long sum2 = 0;
    for (int i = 0; i < N; i++) sum2 += arr[perm[i]];
    clock_t t3 = clock();

    printf("Sequential: %ld ms  sum=%ld\n", (t1-t0)*1000/CLOCKS_PER_SEC, sum);
    printf("Random:     %ld ms  sum=%ld\n", (t3-t2)*1000/CLOCKS_PER_SEC, sum2);
    return 0;
}
```

Compile with `gcc -O2 -o mem mem.c && ./mem`. Typical output:

```
Sequential: 55 ms   sum=2251799780352000
Random:     850 ms  sum=2251799780352000
```

The 15× difference is almost entirely cache miss latency.

**Step 2 — Measuring cache size boundaries:**

```bash
# valgrind's cachegrind tool reports L1/L2/L3 miss rates per function
valgrind --tool=cachegrind --cache-sim=yes ./your_binary

# Linux perf for hardware cache miss counters
perf stat -e cache-references,cache-misses,instructions ./your_binary
```

**Step 3 — False sharing example:**

```c
// Two threads increment adjacent counters — false sharing hurts
typedef struct { long val; } Counter;
Counter c[2];   // c[0] and c[1] share a cache line → contention

// Fix: pad to 64-byte cache line size
typedef struct { long val; char pad[56]; } PaddedCounter;
PaddedCounter pc[2];   // each in its own cache line
```

**Step 4 — Virtual memory page walk, observed:**

```bash
# Show TLB miss rate for a process
perf stat -e dTLB-loads,dTLB-load-misses ./your_binary

# Enable huge pages to reduce TLB pressure
echo madvise > /sys/kernel/mm/transparent_hugepage/enabled
# In code:
madvise(ptr, size, MADV_HUGEPAGE);
```

---

## Use It

### How Real Systems Apply This

| System / Tool | Memory Technique | Why |
|---|---|---|
| **Redis** | All data in DRAM, sequential data structures (listpack) | Sub-millisecond latency requires avoiding disk |
| **Linux kernel** | SLAB/SLUB allocator with per-CPU caches | Avoids lock contention; keeps hot objects in L1 |
| **JVM G1GC** | Region-based heap, card table dirty tracking | Minimizes full-heap scans; uses write barriers |
| **PostgreSQL** | Shared buffer pool (8 KB pages), bgwriter | Minimizes DRAM→disk flushes; sequential write patterns |
| **Apache Arrow / columnar formats** | Column-contiguous layout | Sequential SIMD-friendly access; high cache utilization |
| **Nginx** | Arena allocators per request | Avoids heap fragmentation; bulk-free per connection |
| **DPDK / io_uring** | Huge pages + pinned memory, zero-copy | Eliminates TLB misses and kernel copies in hot path |
| **NumPy / PyTorch** | Contiguous C-order arrays, BLAS | Exploits spatial locality and SIMD |

**When to use which technique:**

- **Small, fixed-size objects with high allocation rate** → slab/arena allocator, avoid `malloc` per object.
- **Large read-mostly datasets** → memory-map with `mmap`, let the OS page in on demand.
- **Multi-threaded shared counters** → pad to cache-line size or use per-thread counters with periodic aggregation.
- **Huge working sets (>4 GB)** → huge pages (2 MB) to reduce TLB pressure.
- **NUMA servers** → bind threads and their memory to the same NUMA node with `numactl --localalloc`.

---

## Common Pitfalls

- **Ignoring cache line boundaries in concurrent code.** Two threads writing to fields that share a 64-byte cache line suffer false sharing. The symptom is low CPU utilization with high `cache-misses` in `perf stat`. Fix: pad hot fields to 64 bytes or use thread-local state aggregated periodically.

- **Assuming `malloc` is free.** `malloc` is typically 50-200 ns on an uncontended path and much more under thread contention (glibc ptmalloc uses per-arena locks). In hot paths — parsers, network packet handlers — use pool/arena allocators or pre-allocated rings.

- **Treating virtual memory as infinite.** The OS may overcommit, but writing to overcommitted pages triggers physical allocation. On a heavily loaded machine, this causes **OOM kills** with no warning. In production, set realistic `vm.overcommit_ratio` and monitor RSS, not VSZ.

- **Forgetting TLB pressure with many small pages.** A service that mmap-s hundreds of small files or allocates millions of 4 KB pages will TLB-thrash. Use huge pages for large, long-lived allocations (JVM heap, Redis AOF buffer).

- **NUMA-blind deployment on multi-socket servers.** Running a latency-sensitive service that allocates memory on socket 0 but gets migrated to socket 1 adds ~30 ns per DRAM access. Pin processes with `numactl -N 0 -m 0 ./service` and profile with `numastat`.

---

## Exercises

1. **Easy:** Write a program that allocates a 128 MB array and reads it sequentially vs. with a stride of 64 elements. Measure the time difference and explain it using the cache-line and prefetcher concepts from this lesson.

2. **Medium:** Design a struct layout for a packet-processing loop that handles 10 million packets per second. Each packet needs: a 6-byte destination MAC, a 4-byte source IP, a 2-byte VLAN tag, a 64-byte payload pointer, and a 4-byte timestamp. Arrange the fields to minimize wasted space and maximize cache efficiency for the hot-path read (MAC + IP + VLAN). Show the before and after layout with byte sizes.

3. **Hard:** A Redis-like in-memory store on a 2-socket NUMA machine (64 cores total, 512 GB RAM) is handling 1M ops/sec but shows ~40% CPU spent in `__memcpy_avx_unaligned` with high remote NUMA access counts in `numastat`. Diagnose the root cause, propose two architectural changes (one at the OS level, one at the application level), and estimate the expected latency improvement for each.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Cache hit** | "Data is in memory" | Data was found in L1/L2/L3 cache; the CPU did not need to go to DRAM |
| **Virtual memory** | "Extra RAM using disk (swap)" | An OS abstraction giving each process its own isolated address space; swap is just one optional backing store |
| **Cache line** | "A unit of cache storage" | The minimum transfer unit between DRAM and cache — 64 bytes on x86/ARM; the whole line is fetched even for a 1-byte read |
| **TLB** | "Part of RAM" | A small hardware cache inside the MMU that holds recent virtual→physical address translations to avoid full page-table walks |
| **False sharing** | "A threading bug" | Two threads accessing different variables that occupy the same 64-byte cache line, causing unnecessary coherence traffic between cores |
| **Heap** | "Where dynamic memory lives" | A managed region of process address space where the allocator (`malloc`, GC, etc.) satisfies dynamic allocation requests |
| **NUMA** | "A server memory type" | A hardware topology where each CPU socket has local DRAM; remote access crosses the inter-socket interconnect at higher latency |

---

## Further Reading

- [What Every Programmer Should Know About Memory — Ulrich Drepper](https://people.freebsd.org/~lstewart/articles/cpumemory.pdf) — the definitive deep-dive; ~100 pages but worth it
- [Linux `perf` tutorial — Brendan Gregg](https://www.brendangregg.com/perf.html) — practical tooling for measuring cache, TLB, and memory events
- [Intel® 64 and IA-32 Architectures Optimization Reference Manual](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html) — authoritative source for cache behavior, prefetcher hints, and memory ordering
- [NUMA-Aware Data Structures — LWN.net](https://lwn.net/Articles/569879/) — practical patterns for NUMA-aware allocation in Linux userspace
- [False Sharing in Java — JEP 142 & JVM internals](https://shipilev.net/talks/jvmls-2013-cache-false-sharing.pdf) — Aleksey Shipilev's slides on false sharing, padding, and JVM `@Contended`
