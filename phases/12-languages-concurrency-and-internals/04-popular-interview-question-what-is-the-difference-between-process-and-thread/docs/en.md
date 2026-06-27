# Popular interview question: What is the difference between Process and Thread?

> Three nested concepts — program, process, thread — that together explain how software actually runs on a computer.

**Type:** Learn
**Prerequisites:** Basic operating systems, programming experience
**Time:** ~15 minutes

---

## The Problem

"Process vs. thread" is one of the most common interview questions, and for good reason. The distinction reveals whether you understand how software actually executes on a computer. It also has direct practical consequences: how you parallelize work, how you share state, and how you debug concurrency issues.

The terms are often confused because they relate to each other. This lesson draws the distinction clearly, walks through the relationship between program, process, and thread, and gives you the working knowledge to answer the question — and to reason about parallelism in practice.

---

## The Concept

### Three nested concepts

```
   Program
     │  passive: a file on disk containing instructions
     │  loaded into memory
     ▼
   Process
     │  active: a running instance of a program
     │  has its own memory, resources, state
     │  contains one or more threads
     ▼
   Thread
        smallest unit of execution within a process
        shares the process's memory with sibling threads
        has its own stack and registers
```

The hierarchy: programs become processes when loaded; processes contain threads that actually run code.

---

### Program

A **program** is an executable file containing a set of instructions, stored passively on disk. It is not running; it is a file. You can copy it, move it, delete it; while it sits on disk, it consumes no CPU and no memory beyond its file size.

```
   /usr/bin/firefox          ← program (file on disk)
   /usr/bin/python3          ← program (file on disk)
   ~/my-app/server          ← program (file on disk)
```

One program can correspond to many processes. When you run `python3 script.py`, you create a process from the program. Run it again, another process.

---

### Process

A **process** is a program that is loaded into memory and actively running. It has:

- Its own virtual address space (memory)
- Its own file descriptors, sockets, and other OS resources
- One or more threads of execution
- A process ID (PID)

```
   $ ps aux | grep python
   alice   1234  python3 script.py       ← process (PID 1234)
   alice   5678  python3 other.py       ← process (PID 5678)
```

When the Chrome browser creates a different process for every tab, that is multiple processes from one program (the chrome executable). Each tab has its own memory, its own cookies, its own crash profile. One tab crashing does not affect others.

**Properties of processes:**

- **Isolation.** Each process has its own memory; one process cannot directly read another's memory (without OS-mediated IPC).
- **Heavy.** Creating a process requires allocating memory, loading the executable, setting up the runtime. Context-switching between processes is expensive.
- **Independent failure.** A crash in one process does not affect others.

---

### Thread

A **thread** is the smallest unit of execution within a process. A process always has at least one thread (the main thread). Most modern applications use multiple threads.

Threads within a process:

- Share the process's memory (heap, code, data segments)
- Have their own stack, registers, and program counter
- Are scheduled independently by the OS
- Can run in parallel on multi-core CPUs

```
   Process: Chrome tab
     │
     ├── Thread 1: render UI
     ├── Thread 2: handle network
     ├── Thread 3: execute JavaScript
     ├── Thread 4: decode video
     └── Thread 5: ...
```

**Properties of threads:**

- **Shared memory.** Threads in the same process share the heap; one thread can read what another wrote (no IPC needed).
- **Lightweight.** Creating a thread is cheaper than creating a process; context-switching is faster.
- **Synchronization required.** Because threads share memory, concurrent access requires locks, atomics, or other synchronization primitives to avoid data corruption.
- **No isolation.** A crash in one thread can take down the entire process.

---

### Side-by-side comparison

| Dimension | Process | Thread |
|---|---|---|
| Definition | A running instance of a program | A unit of execution within a process |
| Memory | Own virtual address space | Shares heap with other threads in the process |
| Isolation | Strong (one crash does not affect others) | Weak (one crash can take down all threads) |
| Creation cost | Heavy (allocate memory, load executable) | Light (allocate stack, registers) |
| Context switch | Expensive | Cheaper |
| Communication | IPC (pipes, sockets, shared memory, message queues) | Direct (shared variables); requires synchronization |
| When to use | Isolation, fault tolerance, security boundaries | Parallelism within a single program, shared state |

---

### Coroutines vs. threads

Coroutines (also called goroutines, async functions, fibers, or green threads) are functions that can suspend and resume their execution. They are cooperatively scheduled, not preemptively like OS threads.

| Dimension | OS thread | Coroutine |
|---|---|---|
| Scheduling | Preemptive (OS decides) | Cooperative (the coroutine yields) |
| Memory | ~1–8 MB stack (default) | ~1 KB stack (typical) |
| Count | Hundreds to thousands | Millions |
| Context switch | Kernel (slow) | User space (fast) |
| Blocking I/O | Blocks the thread | Yields without blocking |
| When to use | CPU-bound parallelism | I/O-bound concurrency |

**Practical examples:**

- **Goroutines** (Go) — millions of coroutines, scheduled onto a small thread pool
- **async/await** (Python, JavaScript, C#, Rust) — coroutines for I/O-bound work
- **Kotlin coroutines, Swift async/await, Rust async** — same idea, different syntax

Coroutines are great for I/O-bound work (network calls, database queries) because they let one thread handle many concurrent operations without the cost of OS threads. They are not great for CPU-bound work, which still needs real threads to use multiple cores.

---

## Build It / In Depth

### A concrete example: loading a webpage

```
   Browser process
     │
     ├── Main thread: UI event loop
     │
     ├── Network thread:
     │     Sends HTTP GET request
     │     Receives response
     │     Hands bytes to parser thread
     │
     ├── Parser thread:
     │     Parses HTML
     │     Dispatches subrequests (CSS, JS, images)
     │     Builds DOM
     │
     ├── Renderer thread:
     │     Layouts the page
     │     Paints pixels
     │
     └── JavaScript engine threads:
           Parses and executes JS
           Runs event loop
           Handles callbacks
```

All these threads share the same heap (the page's data structures). They are coordinated with locks, atomics, and message-passing within the process. If the renderer thread crashes, the entire tab crashes — because threads do not have isolation.

If the renderer thread instead were its own process (as it is for some browser features), a crash in renderer would kill just the renderer process, and the rest of the tab would survive.

---

### How to list processes and threads in Linux

```bash
# List all running processes
ps aux

# List threads of a process
ps -L -p <pid>

# Show threads in real time (similar to top but per-thread)
top -H

# Inspect process state from /proc
cat /proc/<pid>/status
```

In `top -H`, the `Threads:` line shows how many threads a process has. A Chrome tab might have 10–30 threads; a Java application server might have 100+.

---

### When to use multiple processes vs. multiple threads

**Use multiple processes when:**

- You need strong isolation (one component crashing should not affect others)
- You are running untrusted code (sandboxing)
- Your workload benefits from distribution (processes can run on different machines)
- You want to scale by adding machines (processes are units of horizontal scaling)

**Use multiple threads when:**

- You need shared state between concurrent tasks
- The work is I/O-bound (network, disk) and you want to overlap waits
- The work is CPU-bound and you want to use multiple cores
- You are building a single application with internal concurrency

**Use coroutines when:**

- You have many I/O-bound operations (thousands of network calls)
- Thread overhead is too high (e.g., millions of concurrent operations)
- You want simpler concurrency than explicit thread management

---

## Common Pitfalls

- **Confusing processes with threads.** They are nested concepts, not alternatives. Every process contains threads.

- **Using threads for isolation.** Threads share memory; a bug in one thread corrupts the whole process. Use processes for isolation.

- **Using processes when threads suffice.** For CPU-bound parallelism within one application, threads are simpler and faster than IPC between processes.

- **Forgetting that threads share state.** Two threads writing to the same variable without synchronization produce undefined behavior. Use locks, atomics, or thread-safe data structures.

- **Over-counting cores.** A 4-core CPU can run 4 CPU-bound threads in parallel. Beyond that, threads spend time waiting. Coroutines or processes are better for higher concurrency.

- **Assuming threads are cheap.** Each thread has a default 1–8 MB stack. 10,000 threads = 10–80 GB of stack memory. Plan accordingly.

---

## Exercises

1. **Easy** — Define program, process, and thread in one sentence each. Give a concrete example of each.

2. **Medium** — Choose a real product (e.g., a chat app, a web browser, a database). Identify where it uses processes vs. threads vs. coroutines. Justify each choice.

3. **Hard** — You are designing a server that handles 10,000 concurrent connections. Choose your concurrency model (processes, threads, coroutines, async/await). Justify the choice and describe the memory implications.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Program | An app | An executable file on disk; passive; instructions stored for later execution |
| Process | A running program | A program loaded into memory and actively executing; has its own memory, resources, and one or more threads |
| Thread | A lightweight process | The smallest unit of execution within a process; shares memory with sibling threads |
| Coroutine | A thread | A cooperatively scheduled function that can suspend and resume; lightweight (kilobytes vs megabytes for OS threads); used for I/O concurrency |
| Goroutine | A Go thing | Go's specific implementation of coroutines; millions can run on a small thread pool |
| async/await | A syntax | Language syntax for coroutines; Python, JavaScript, C#, Rust, Kotlin all support it |
| Context switch | A pause | The OS saving one thread's state and loading another's; cheap for threads, expensive for processes |
| Parallelism vs concurrency | The same thing | Parallelism = running tasks at the same instant on multiple cores; concurrency = dealing with multiple tasks at once, even if not simultaneously |

---

## Further Reading

- **"Operating Systems: Three Easy Pieces"** — the free, canonical OS textbook: https://pages.cs.wisc.edu/~remzi/OSTEP/
- **"The Linux Programming Interface"** — Michael Kerrisk; the definitive guide to Linux system calls, processes, threads: https://man7.org/tlpi/
- **Go Concurrency Patterns** — the canonical patterns for goroutines: https://go.dev/blog/pipelines
- **Python asyncio documentation** — the standard reference for asyncio coroutines: https://docs.python.org/3/library/asyncio.html
- **Rust Async Book** — async programming in Rust: https://rust-lang.github.io/async-book/