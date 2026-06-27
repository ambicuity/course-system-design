# Things Every Developer Should Know: Concurrency is NOT Parallelism

> Rob Pike's distinction that changed how the industry thinks about writing programs — concurrency is structure, parallelism is execution.

**Type:** Learn
**Prerequisites:** Basic programming
**Time:** ~15 minutes

---

## The Problem

The words "concurrency" and "parallelism" are often used interchangeably, but they mean different things. Conflating them produces designs that are harder than they need to be (over-parallelizing I/O-bound work) or that miss opportunities (sequential code that could be concurrent).

Rob Pike, co-creator of Go, made the distinction famous in 2012: *"Concurrency is about dealing with lots of things at once. Parallelism is about doing lots of things at once."* The quote captures a real difference that affects how you structure programs.

This lesson explains the distinction, shows when each matters, and gives you the working knowledge to choose the right model for the right problem.

---

## The Concept

### The one-sentence distinction

```
   Concurrency  is a property of the program's STRUCTURE.
                 The program is composed of independently executing
                 pieces that can make progress without waiting for
                 each other.

   Parallelism  is a property of the program's EXECUTION.
                 The program runs multiple operations at the exact
                 same instant, typically on multiple CPU cores.
```

A concurrent program may or may not be parallel. A parallel program may or may not be concurrent. The two are orthogonal; you can have either, both, or neither.

---

### A picture

```
   Concurrent, not parallel:
   ┌──────────┐         ┌──────────┐
   │  Task A  │         │  Task B  │
   │          │         │          │
   │ ░░░██░░░ │         │ ███░░░░░ │
   │ ░░░██░░░ │         │ ███░░░░░ │
   │ ███░░░░░ │         │ ░░░██░░░ │
   │ ███░░░░░ │         │ ░░░██░░░ │
   └──────────┘         └──────────┘
   Single core. Tasks A and B take turns.

   Parallel, not concurrent:
   ┌──────────┐    ┌──────────┐
   │  Task A  │    │  Task B  │   Each task runs on its own core.
   │  ████    │    │  ████    │   Tasks are independent and do
   │  ████    │    │  ████    │   not interact — there is no
   │  ████    │    │  ████    │   coordination.
   │  ████    │    │  ████    │
   └──────────┘    └──────────┘

   Concurrent AND parallel:
   ┌──────────┐    ┌──────────┐
   │  Task A  │    │  Task B  │   Multiple cores, AND the tasks
   │  ░██░░   │    │  ████    │   coordinate via channels, locks,
   │  ██░░░   │    │  █░░██   │   or shared state.
   │  ░██░░   │    │  ████    │
   │  ██░░░   │    │  ░██░░   │
   └──────────┘    └──────────┘
```

Concurrency is about *how you write* the program. Parallelism is about *how it runs*.

---

### Why the distinction matters

A program that is concurrent but not parallel can run on a single core and still be more responsive than a sequential program. The tasks take turns; while one is waiting on I/O, another runs.

A program that is parallel but not concurrent is multiple independent computations. There is no coordination between them; they happen to use multiple cores at the same time.

Most modern programs want both. A web server is concurrent (it handles many requests, each in its own task) and parallel (those tasks run on multiple cores). The two properties are not in tension; they are complementary.

---

### Concurrency in practice

Concurrency is most useful for **I/O-bound work** — programs that spend most of their time waiting on external systems.

```
   Without concurrency (sequential):
     Total time: 3 seconds

     ├── Fetch URL 1 (1s)
     ├── Fetch URL 2 (1s)
     └── Fetch URL 3 (1s)

   With concurrency (overlapped):
     Total time: 1 second

     ├── Fetch URL 1 ──────► (waiting)
     ├── Fetch URL 2 ──────► (waiting)
     └── Fetch URL 3 ──────► (waiting)
            │
            ▼
       All return within 1 second
```

The concurrent version does not do more work — it just does not waste time waiting. The actual CPU usage is similar; what changes is the wall-clock time.

**Examples of concurrent code:**

- An async web server handling thousands of HTTP requests at once
- A database client that issues many queries and processes results as they arrive
- A chat application that maintains connections to many users

**Implementation patterns:**

- async/await (Python, JavaScript, C#, Rust, Kotlin)
- Goroutines (Go)
- Callbacks / event loops (Node.js)
- Reactive streams (RxJava, Project Reactor)

---

### Parallelism in practice

Parallelism is most useful for **CPU-bound work** — programs that spend most of their time computing.

```
   Without parallelism (sequential):
     Total time: 30 seconds (single core)

     └── Image processing (30s)

   With parallelism (4 cores):
     Total time: ~8 seconds

     ├── Image processing (core 1) ─────► (8s)
     ├── Image processing (core 2) ─────► (8s)
     ├── Image processing (core 3) ─────► (8s)
     └── Image processing (core 4) ─────► (8s)
```

The parallel version does more work in the same wall-clock time because multiple cores are active.

**Examples of parallel code:**

- Image or video processing (each frame on a different core)
- Numerical simulations (each particle on a different core)
- Batch data processing (each chunk on a different core)
- ML model training (data parallel or model parallel)

**Implementation patterns:**

- Thread pools
- Process pools (multiprocessing)
- GPU / TPU programming (CUDA, ROCm)
- Distributed computing (Spark, Ray, Dask)

---

### The overlap

Many real problems are both:

```
   Web server:
     - Concurrent: handles many requests at once (overlap I/O waits)
     - Parallel: requests run on multiple cores (handle CPU work per request)

   Data pipeline:
     - Concurrent: reads from many sources in parallel
     - Parallel: processes partitions of data on multiple cores

   ML training:
     - Concurrent: many workers load data and train simultaneously
     - Parallel: gradients computed on multiple GPUs in sync
```

A well-designed concurrent program can scale up (use more cores for parallel work) without changing the structure of the code. A well-designed parallel program is also concurrent (coordinated, not racing). They are complementary goals.

---

### Mapping to languages

| Model | Languages | Example |
|---|---|---|
| Concurrency via async/await | Python, JS, C#, Rust, Kotlin | `await fetch(url)` |
| Concurrency via goroutines | Go | `go fetchURL(url)` |
| Parallelism via threads | All major languages | `ThreadPoolExecutor` |
| Parallelism via processes | Python (multiprocessing) | `multiprocessing.Pool` |
| Parallelism via GPU | CUDA, ROCm | `cudaKernel<<<...>>>` |
| Distributed parallelism | Spark, Ray, Dask | `sc.parallelize(data)` |

---

## Build It / In Depth

### Worked example: downloading 100 URLs

**Sequential code:**

```python
import requests

def fetch_all(urls):
    results = []
    for url in urls:
        response = requests.get(url)
        results.append(response.text)
    return results

# Total time: 100 * 0.5s = 50 seconds
```

**Concurrent (async/await) code:**

```python
import asyncio
import aiohttp

async def fetch_all(urls):
    async with aiohttp.ClientSession() as session:
        tasks = [session.get(url) for url in urls]
        responses = await asyncio.gather(*tasks)
        return [await r.text() for r in responses]

# Total time: ~1 second (overlapped I/O)
```

**Parallel (threads) code:**

```python
from concurrent.futures import ThreadPoolExecutor
import requests

def fetch_all(urls):
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(requests.get, url) for url in urls]
        return [f.text() for f in futures]

# Total time: ~3 seconds (overlapped but GIL-limited)
```

**Parallel (processes) code:**

```python
from concurrent.futures import ProcessPoolExecutor
import requests

def fetch_all(urls):
    with ProcessPoolExecutor(max_workers=8) as executor:
        # Split work across processes (each gets ~12 URLs)
        chunks = [urls[i::8] for i in range(8)]
        futures = [executor.submit(fetch_chunk, c) for c in chunks]
        return [r for f in futures for r in f.result()]

# Total time: ~7 seconds (process startup overhead)
```

The async version is fastest because the work is I/O-bound, not CPU-bound. The CPU is idle most of the time; the bottleneck is network latency. Async overlaps the waits without using more CPU.

---

### Decision tree

```
   Is the work I/O-bound or CPU-bound?

   I/O-bound (network, disk, database):
     → Concurrency (async/await, goroutines, event loops)
     → One thread can handle thousands of I/O operations
     → Do NOT parallelize with threads/processes (waste)

   CPU-bound (image processing, computation, simulations):
     → Parallelism (multiple threads on multiple cores)
     → Or processes (if Python; for GIL reasons)
     → Or GPU (if massively parallel)
     → Concurrency alone does not help here

   Mixed:
     → Both: async for I/O; threads/processes for CPU work
     → Architecture: async event loop dispatches CPU work to a thread pool
```

---

### Common misconceptions

**"My code is parallel because it uses threads."**

Threads are a mechanism; parallelism is an outcome. If you have 4 threads on 1 core, they are concurrent (taking turns) but not parallel (never running simultaneously). The OS schedules them, but they cannot all make progress at the same time.

**"Async is the same as parallel."**

Async is for concurrency. Async overlaps I/O waits so that one thread can juggle many operations. The operations still execute serially within the thread. If you want parallelism, you need multiple threads, multiple processes, or multiple machines.

**"More threads = more performance."**

For I/O-bound work, threads mostly add overhead. One async task often outperforms ten threads. For CPU-bound work, threads help only up to the number of cores; beyond that, context-switching dominates.

**"I can make any program parallel by adding threads."**

Adding threads to sequential code introduces race conditions, requires synchronization, and may not improve performance if the bottleneck is I/O, not CPU. Parallelism is a redesign, not a tweak.

---

## Use It

### When to reach for each model

| Situation | Use |
|---|---|
| Network requests (hundreds at once) | async/await |
| Database queries (many concurrent) | async/await |
| Chat / live updates | async/await or WebSocket |
| Image processing (CPU-heavy) | thread pool, process pool, or GPU |
| Numerical simulation | multiprocessing, MPI, GPU |
| ML training | GPU + distributed framework (PyTorch DDP, Ray) |
| Real-time stream processing | Kafka + Flink |
| Map-reduce over big data | Spark, Dask, Ray |
| High-throughput API server | async/await (Node.js, FastAPI, etc.) |
| CPU-bound batch jobs | process pool, multiprocessing |

---

### Patterns that often go wrong

| Anti-pattern | What to do instead |
|---|---|
| Threads for I/O-bound work | Use async/await |
| Async for CPU-bound work | Use threads/processes/GPU |
| Process pool of 1 process | Run sequentially |
| Thread pool with 1000 threads for I/O | Use async |
| Locks everywhere | Use message passing or immutable data |
| Shared mutable state | Pass data via channels or queues |

---

## Common Pitfalls

- **Conflating the two words.** They are not synonyms. Use "concurrent" for structure, "parallel" for execution.

- **Choosing threads when async fits.** For I/O-bound work, async is dramatically simpler and faster.

- **Choosing async when threads fit.** For CPU-bound work, async does not help; you need real parallelism.

- **Believing parallel always means faster.** Parallelism has overhead (coordination, communication). For small workloads, sequential is faster.

- **Ignoring the GIL (Python).** Python threads are great for I/O but do not give parallelism for CPU. Use processes or native extensions.

- **Mixing paradigms without understanding.** Threads inside async, async inside threads — possible but tricky. Understand the model you are working in.

- **Premature optimization.** Most code does not need parallelism. Add it when measurement shows the bottleneck is CPU, not I/O.

---

## Exercises

1. **Easy** — In one sentence each, define concurrency and parallelism. Give one example where each matters more than the other.

2. **Medium** — Take a real piece of code (yours or open-source). Classify it as concurrent, parallel, both, or neither. Justify.

3. **Hard** — Design a web crawler that fetches 1 million URLs. Choose your concurrency model. Justify the choice and estimate the resources required.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Concurrency | Doing things in parallel | A property of program structure; tasks are composed to make progress independently |
| Parallelism | Doing things at once | A property of execution; multiple operations run at the exact same instant on multiple cores |
| I/O-bound | Slow code | Code that spends most of its time waiting on external systems (network, disk, database) |
| CPU-bound | Slow code | Code that spends most of its time computing; benefits from parallelism |
| Async/await | A syntax | Language syntax for writing concurrent code that overlaps I/O waits |
| GIL | A Python thing | Global Interpreter Lock — Python's mutex that prevents multiple threads from executing Python bytecode simultaneously; makes threads concurrent but not parallel for CPU work |
| Process pool | A parallelism tool | A fixed set of worker processes that execute tasks in parallel; bypasses the GIL in Python |
| Thread pool | A concurrency tool | A fixed set of worker threads that execute tasks; great for I/O-bound work, limited for CPU-bound |

---

## Further Reading

- **"Concurrency is not Parallelism"** — Rob Pike's original talk: https://go.dev/blog/waza-talk
- **"Go Concurrency Patterns"** — Rob Pike's patterns for goroutines: https://go.dev/blog/pipelines
- **"The Art of Concurrency"** — Clay Breshears; the canonical book on the topic: https://www.oreilly.com/library/view/the-art-of/9780596802424/
- **"Concurrency in Go"** — Katherine Cox-Buday: https://www.oreilly.com/library/view/concurrency-in-go/9781491941294/
- **"Python Concurrency with asyncio"** — Matthew Fowler: https://www.manning.com/books/python-concurrency-with-asyncio