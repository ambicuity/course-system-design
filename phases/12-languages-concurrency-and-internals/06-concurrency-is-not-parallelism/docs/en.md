# Concurrency is NOT Parallelism

> Concurrency is about *dealing with* many things at once. Parallelism is about *doing* many things at once. Confusing the two leads to systems that scale on paper but crawl in production.

**Type:** Learn
**Prerequisites:** OS threads and processes, Event-driven I/O, CPU architecture basics
**Time:** ~25 minutes

---

## The Problem

You've just scaled your web service to 32 CPU cores. Traffic spikes, and you notice that adding more cores stops helping after a certain point. You look at flame graphs and see that threads spend most of their time blocked on network I/O — waiting for a database response, an external API call, or a disk read. Your code is technically "multithreaded," but it's not faster.

Alternatively, you write an async Python service using `asyncio`. It handles thousands of concurrent requests beautifully in testing. But the moment you add a CPU-intensive step — say, compressing images or computing a cryptographic hash — the whole event loop stalls. Tasks pile up. Latency spikes. Users see timeouts.

Both failures share the same root cause: the engineer treated concurrency and parallelism as synonyms. They are not. Concurrency is a **structural** property of a program — the way tasks are composed and interleaved. Parallelism is an **execution** property — tasks literally running simultaneously on separate hardware. A program can be concurrent without being parallel, parallel without being concurrent, both, or neither. Until you can articulate the difference clearly, you will keep misdiagnosing performance problems and reaching for the wrong tool.

---

## The Concept

### The Core Distinction

Rob Pike (co-creator of Go) gave the clearest definition in his 2012 talk:

- **Concurrency** — the *composition* of independently executing processes (or tasks). It is a design concern. It is about *structure*.
- **Parallelism** — the simultaneous *execution* of (possibly related) computations. It is a runtime concern. It is about *execution*.

Concurrency makes programs easier to reason about by breaking them into independent pieces. Parallelism is a runtime optimization that exploits multiple processing units. You can have one without the other.

```
CONCURRENCY (single core, time-sliced)
─────────────────────────────────────────────────────────
Core 0:  [Task A]──>[Task B]──>[Task A]──>[Task B]──>...
          ^ context   ^ switch   ^ context   ^ switch
          switch

Tasks interleave; only ONE runs at any instant.
Total elapsed time ≈ sum of all task times (minus I/O wait).

PARALLELISM (multiple cores, simultaneous)
─────────────────────────────────────────────────────────
Core 0:  [Task A]────────────────────────────────────>
Core 1:  [Task B]────────────────────────────────────>

Tasks run LITERALLY at the same time.
Total elapsed time ≈ max of individual task times.
```

### The Two-Axis Model

It is most useful to think of concurrency and parallelism as independent axes:

| | Not Parallel | Parallel |
|---|---|---|
| **Not Concurrent** | Single-threaded, sequential program | SIMD / GPU vector ops — same instruction on multiple data, no task structure |
| **Concurrent** | Node.js event loop, Python `asyncio` on 1 core | Go with `GOMAXPROCS=N`, Java thread pool on N cores, Rust `tokio` on a thread pool |

Most of the interesting systems engineering lives in the bottom two cells.

### Why Concurrency Without Parallelism Is Still Valuable

When a task blocks on I/O (reading from disk, waiting for a TCP response, sleeping), the CPU is idle. Concurrency lets the runtime switch to another ready task and keep the CPU busy. No extra cores needed.

```
Without concurrency (3 HTTP requests, sequential):
─────────────────────────────────────────────────────
Request 1: [compute][===network wait===][compute]
Request 2:                                          [compute][===network wait===][compute]
Request 3:                                                                                [compute][===network wait===][compute]
                                                                                                                                 ^done
Total time = 3 × (compute + wait)

With concurrency (3 HTTP requests, concurrent, single core):
─────────────────────────────────────────────────────
Request 1: [compute]─wait─────────────[compute]
Request 2:     [compute]─wait─────────────[compute]
Request 3:         [compute]─wait─────────────[compute]
                                                    ^done
Total time ≈ 1 × (compute + wait)  ← near 3× faster, zero extra CPUs
```

This is why Node.js can serve tens of thousands of connections on a single core. It is purely concurrent, not parallel. Its secret is that web servers spend 90%+ of time waiting on I/O.

### When You Actually Need Parallelism

If a task is CPU-bound — it never blocks, it just computes — concurrency buys you nothing. You need real parallelism: multiple cores running simultaneously.

Examples of CPU-bound work:
- Image/video encoding
- Cryptographic hashing
- Machine learning inference
- Sorting very large in-memory datasets
- Compression (gzip, zstd)

On a single core, running two CPU-bound tasks concurrently is strictly slower than running them sequentially, because context-switching adds overhead with no I/O idle time to recover.

### How Context Switching Works

The OS scheduler is the engine behind single-core concurrency. It uses a timer interrupt (typically every 1–10 ms) to preempt the running thread, save its register state (the "context"), and restore another thread's context. This is "preemptive multitasking."

Cooperative concurrency (used by `async/await`, Go goroutines, Python `asyncio`) works differently: tasks voluntarily yield control at explicit suspension points (`await`, channel operations, `select`). This has lower overhead but requires code to yield regularly — a CPU-bound coroutine that never yields will starve everything else.

```
Preemptive (OS threads):                Cooperative (async/green threads):
─────────────────────────────           ─────────────────────────────
Task A runs...                          Task A runs...
  [TIMER INTERRUPT]                       await io_operation()  ← yields here
  OS saves A's registers                Task B runs...
  OS restores B's registers               await io_operation()  ← yields here
Task B runs...                          Task A resumes...
  [TIMER INTERRUPT]
  ...
```

### Language-Level Implementations

Different languages make different choices about where they land on the concurrency/parallelism axes:

| Language / Runtime | Concurrency model | Parallelism across cores? | Key constraint |
|---|---|---|---|
| **Python (CPython)** | Threads (OS) + `asyncio` (cooperative) | No — GIL serializes threads | GIL prevents true parallel Python bytecode execution |
| **Node.js** | Single-threaded event loop (`libuv`) | No (main loop) + Yes (Worker Threads) | CPU-bound work blocks the loop |
| **Go** | Goroutines (M:N green threads) | Yes — `GOMAXPROCS` defaults to `runtime.NumCPU()` | Goroutines are preemptable since Go 1.14 |
| **Java / Kotlin** | OS threads + `CompletableFuture` + Virtual Threads (JDK 21) | Yes | Virtual Threads are cooperative, carrier threads are OS threads |
| **Rust** | `async/await` (`tokio`, `async-std`) | Yes — Tokio uses a thread pool | Futures are lazy; must be polled to make progress |
| **Erlang / Elixir** | Lightweight processes, actor model | Yes — BEAM runs schedulers on N OS threads | Shared-nothing; processes communicate via messages |

---

## Build It / In Depth

### Worked Example: I/O-Bound vs CPU-Bound in Python

This walkthrough makes the distinction concrete and exposes the GIL's effect.

**Setup: three tasks**

```python
import time
import threading
import multiprocessing
import hashlib

# --- I/O-bound task: simulate a network call ---
def io_task(name: str) -> None:
    print(f"{name}: start")
    time.sleep(1)          # sleeping releases the GIL
    print(f"{name}: done")

# --- CPU-bound task: heavy computation ---
def cpu_task(name: str) -> None:
    print(f"{name}: start")
    data = b"x" * 10_000_000
    hashlib.sha256(data).hexdigest()   # pure CPU, holds the GIL
    print(f"{name}: done")
```

**Test 1: I/O-bound with threading (concurrent, partially parallel due to GIL release)**

```python
def run_io_threaded():
    start = time.perf_counter()
    threads = [threading.Thread(target=io_task, args=(f"io-{i}",)) for i in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    print(f"Threaded I/O total: {time.perf_counter() - start:.2f}s")
    # Expected: ~1s  (all threads sleep concurrently)

run_io_threaded()
```

**Test 2: CPU-bound with threading (concurrent but NOT parallel — GIL serializes)**

```python
def run_cpu_threaded():
    start = time.perf_counter()
    threads = [threading.Thread(target=cpu_task, args=(f"cpu-{i}",)) for i in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    print(f"Threaded CPU total: {time.perf_counter() - start:.2f}s")
    # Expected: ~4× single-task time (serialized by GIL, plus context switch overhead)

run_cpu_threaded()
```

**Test 3: CPU-bound with multiprocessing (concurrent AND parallel)**

```python
def run_cpu_parallel():
    start = time.perf_counter()
    procs = [multiprocessing.Process(target=cpu_task, args=(f"proc-{i}",)) for i in range(4)]
    for p in procs: p.start()
    for p in procs: p.join()
    print(f"Multiprocessing CPU total: {time.perf_counter() - start:.2f}s")
    # Expected: ~1× single-task time (4 cores, truly parallel, no GIL across processes)

run_cpu_parallel()
```

**Expected results on a 4-core machine:**

```
Threaded I/O:           ~1.0s   ← concurrency wins for I/O
Threaded CPU:           ~4.0s   ← concurrency hurts CPU-bound (GIL + overhead)
Multiprocessing CPU:    ~1.0s   ← parallelism wins for CPU
```

### Decision Flowchart

```
Is the task mostly WAITING on external resources?
(disk, network, database, timers)
         │
         ├─ YES → Use CONCURRENCY
         │        async/await, event loops, green threads, goroutines
         │        Single-core is often sufficient.
         │
         └─ NO → Is the work CPU-intensive?
                        │
                        ├─ YES → Use PARALLELISM
                        │        multiprocessing, worker threads, goroutines on multiple cores
                        │        One OS thread per core (roughly).
                        │
                        └─ MIXED → Use BOTH
                                   Concurrent outer layer (async) + parallel inner layer
                                   (thread pool / process pool for CPU work)
                                   Example: asyncio + ProcessPoolExecutor in Python
                                            Tokio + rayon in Rust
                                            Go channels + goroutine pools
```

### Go: Concurrency and Parallelism Together

Go's goroutines are cheap green threads (~2KB stack). The Go runtime multiplexes them onto `GOMAXPROCS` OS threads — giving both concurrency (many goroutines) and parallelism (multiple OS threads on multiple cores).

```go
package main

import (
    "fmt"
    "runtime"
    "sync"
    "time"
)

func ioTask(id int, wg *sync.WaitGroup) {
    defer wg.Done()
    time.Sleep(time.Second) // yields goroutine, runtime runs others
    fmt.Printf("io-%d done\n", id)
}

func main() {
    fmt.Println("CPUs:", runtime.NumCPU())
    runtime.GOMAXPROCS(runtime.NumCPU()) // enable parallelism

    var wg sync.WaitGroup
    for i := 0; i < 1000; i++ { // 1000 goroutines, not 1000 OS threads
        wg.Add(1)
        go ioTask(i, &wg)
    }
    wg.Wait()
    // Completes in ~1s with 1000 concurrent I/O tasks
    // OS thread count stays low (GOMAXPROCS, not 1000)
}
```

---

## Use It

### Real Systems and Which Model They Use

| System / Tool | Concurrency model | Parallel? | Best for |
|---|---|---|---|
| **Nginx** | Event-driven, worker processes | Yes (N worker processes) | High-connection I/O serving |
| **Node.js** | Single-threaded event loop | Worker Threads for CPU tasks | API gateways, BFF layers |
| **Redis** | Single-threaded command loop | No (by default) | Low-latency key-value; avoids locking |
| **PostgreSQL** | Process per connection | Yes (N backend processes) | OLTP with parallel query plans |
| **Go (net/http)** | Goroutine per connection | Yes | Services with mixed I/O + compute |
| **Erlang/OTP** | Millions of lightweight actors | Yes (BEAM schedulers) | Telecom, distributed stateful systems |
| **Python `asyncio`** | Cooperative coroutines | No (GIL) | I/O-heavy microservices |
| **Python `concurrent.futures.ProcessPoolExecutor`** | Multiple processes | Yes | Data processing, ML preprocessing |
| **Rust `tokio`** | Async tasks on a thread pool | Yes | High-perf network services |
| **Java Virtual Threads (JDK 21+)** | Millions of virtual threads | Yes (carrier threads) | Drop-in replacement for thread-per-request |

### Choosing Concurrency Primitive by Problem Type

```
Problem                      Primitive to reach for
─────────────────────────    ──────────────────────────────────────────────
Many HTTP requests           Async I/O (asyncio, tokio, goroutines)
Fan-out/fan-in               Goroutines + channels; asyncio.gather(); CompletableFuture.allOf()
CPU parallelism              OS threads (Go, Rust, Java) or processes (Python)
Rate-limited external API    Semaphore + async tasks
Ordered pipeline             Channels with bounded buffer (Go, Rust)
Shared mutable state         Mutex + threads; prefer immutable + message passing
Long-running background job  Worker process / queue (Celery, Sidekiq, BullMQ)
```

---

## Common Pitfalls

- **Blocking an async event loop with CPU work.** Calling a CPU-bound function inside an `async def` in Python or inside a goroutine that never yields will stall every other coroutine. Fix: offload CPU work to a thread pool (`loop.run_in_executor`) or a separate process.

- **Assuming more threads always means more speed.** Adding threads to I/O-bound work helps up to a point (saturating I/O bandwidth). Adding threads to CPU-bound work in Python *hurts* due to the GIL. Profile before scaling thread counts.

- **Spawning one OS thread per connection.** An OS thread costs 1–8 MB of stack memory and a slow context switch. At 10,000 connections you've used 10–80 GB just for stacks. Use async I/O or green threads (goroutines, virtual threads) which are orders of magnitude cheaper.

- **Ignoring cooperative scheduling starvation.** In cooperative runtimes (asyncio, older Go), a tight CPU loop with no `await`/yield points starves all other tasks. In Go 1.14+, goroutines are preemptable by the runtime at function call boundaries — but a tight loop with no function calls can still cause lag. Always add yield points in long-running coroutines.

- **Using `asyncio` in Python and expecting it to bypass the GIL.** `asyncio` is concurrent but *not* parallel. Two coroutines cannot execute Python bytecode simultaneously. For true parallel Python, you must use `multiprocessing` or a C-extension that releases the GIL (NumPy, most I/O calls).

---

## Exercises

1. **Easy** — Write a script that fetches 5 URLs sequentially, then rewrites it using `asyncio.gather()`. Measure wall-clock time for each version. Explain the speedup in terms of concurrency, not parallelism.

2. **Medium** — Take a CPU-bound function (e.g., computing 10,000 SHA-256 hashes). Run it with (a) 4 threads, (b) 4 processes in Python. Record timings. Explain why threading is slower than sequential for this task and why multiprocessing is faster.

3. **Hard** — Design a Go service that accepts image upload requests concurrently (goroutine per connection) and compresses images in parallel using a worker pool of size `runtime.NumCPU()`. Sketch the channel topology: how does the request goroutine hand off work to a pool goroutine and receive the result? Where is the concurrency? Where is the parallelism?

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Concurrency** | "Running things at the same time" | Structuring a program as independently interleaving tasks; they may or may not run simultaneously |
| **Parallelism** | "Using multiple threads" | Literally executing multiple computations at the exact same instant on separate CPU cores |
| **Context switch** | "Slow OS overhead" | The act of saving one thread's register state and restoring another's; enables concurrency on a single core |
| **Green thread / goroutine** | "A lightweight OS thread" | A user-space cooperative/preemptable unit of execution; many map to few OS threads via an M:N scheduler |
| **GIL (Global Interpreter Lock)** | "Python's thread safety mechanism" | A CPython mutex that allows only one thread to execute Python bytecode at a time, preventing true thread parallelism |
| **Async / Await** | "Parallel execution" | Cooperative concurrency: marks suspension points where the event loop can switch to another task; single-threaded by default |
| **M:N threading** | "Complex internal detail" | N goroutines/green-threads multiplexed onto M OS threads; allows parallelism while keeping goroutine overhead low |

---

## Further Reading

- [Rob Pike — "Concurrency is not Parallelism" (Go Blog, 2013)](https://go.dev/blog/waza-talk) — The canonical 30-minute talk that coined the modern framing; watch the video, read the slides.
- [Python docs — `asyncio` — Coroutines and Tasks](https://docs.python.org/3/library/asyncio-task.html) — Official reference for Python's cooperative concurrency model; explains the event loop lifecycle.
- [Go docs — The Go Memory Model](https://go.dev/ref/mem) — Precise rules for what Go's scheduler guarantees about goroutine execution order and visibility.
- [Java 21 — Project Loom Virtual Threads (JEP 444)](https://openjdk.org/jeps/444) — How the JVM now supports millions of concurrent threads without M:N complexity in application code.
- [Tokio docs — "Async in depth"](https://tokio.rs/tokio/tutorial/async) — Rust's async model explained from the `Future` trait up through the runtime executor; excellent complement to the Go perspective.
