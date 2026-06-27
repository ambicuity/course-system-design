# How Java Virtual Threads Work?

> The JVM becomes the scheduler — blocking a virtual thread costs almost nothing because the OS thread never actually waits.

**Type:** Learn
**Prerequisites:** OS Threads and the Thread-Per-Request Model, Java Concurrency Basics, Event-Loop vs. Thread-Per-Request
**Time:** ~25 minutes

---

## The Problem

A traditional Java web server allocates one OS thread per request. Threads are expensive: on a typical JVM, each platform thread carries roughly **1–2 MB of stack space** and involves a kernel data structure. A machine with 4 GB of heap can practically sustain only a few thousand concurrent threads before memory runs out or context-switching overhead dominates.

The moment a thread calls a blocking operation — reading from a database, waiting for an HTTP response, sleeping in a scheduled job — it sits parked in the OS with no useful work to do. Scale that to 10,000 concurrent requests and you have 10,000 parked OS threads, most of them idle, burning memory and scheduler cycles. Teams worked around this with reactive programming (Project Reactor, RxJava) — asynchronous, non-blocking pipelines — but that imposes callback hell, complex error propagation, and makes stack traces nearly unreadable for debugging.

Java 21 (GA) delivers **Virtual Threads** (JEP 444) as the answer: threads you can spawn in the millions, where blocking an individual thread is as cheap as parking a user-space coroutine. The goal is to restore the simplicity of the thread-per-request mental model while delivering the throughput of reactive systems — without rewriting your code in a reactive style.

---

## The Concept

### Platform Threads vs. Virtual Threads

| Property | Platform Thread | Virtual Thread |
|---|---|---|
| Backed by | One OS thread (1:1) | JVM-managed scheduler (M:N) |
| Stack | Fixed ~1–2 MB in native memory | Heap-allocated, grows dynamically (starts ~few KB) |
| Creation cost | ~1 ms, heavyweight syscall | ~1 µs, pure JVM allocation |
| Practical limit | ~thousands per JVM | ~millions per JVM |
| Scheduling | OS kernel preemptive | JVM cooperative (continuation-based) |
| Blocking behavior | Blocks the OS thread | Unmounts from OS thread; OS thread freed |

Virtual threads do **not** replace platform threads — they run **on top of** them. The platform threads that carry virtual threads are called **carrier threads**.

### The Carrier Thread Pool

The JVM maintains a small `ForkJoinPool` of carrier threads, sized by default to the number of available CPU cores (`Runtime.getRuntime().availableProcessors()`). You can override it with `-Djdk.virtualThreadScheduler.parallelism=N`.

```
  JVM Virtual Thread Scheduler
  ┌──────────────────────────────────────────────────────────┐
  │  Virtual Thread 1 (running)                              │
  │  Virtual Thread 2 (blocked – unmounted, heap-parked)     │
  │  Virtual Thread 3 (runnable – queued to be mounted)      │
  │  Virtual Thread 4 (blocked – unmounted, heap-parked)     │
  │  ...                (potentially millions)               │
  └────────────────┬─────────────────────────────────────────┘
                   │ mounts / unmounts
       ┌───────────▼────────────────────────┐
       │  Carrier Thread Pool (ForkJoinPool) │
       │  ┌──────────┐  ┌──────────┐        │
       │  │ Carrier 1│  │ Carrier 2│  ...   │  (≈ CPU cores)
       │  │(OS Thread│  │(OS Thread│        │
       │  └──────────┘  └──────────┘        │
       └────────────────────────────────────┘
                   │
           OS Kernel Scheduler
```

### Mount and Unmount — The Core Mechanism

A virtual thread can be in one of three states from the scheduler's perspective:

- **Mounted** — currently executing on a carrier thread.
- **Unmounted (blocked)** — has encountered a blocking operation; its continuation is saved to the heap, and the carrier thread is returned to the pool.
- **Runnable** — the blocking operation completed; the virtual thread is queued and waiting to be mounted on any available carrier thread.

The JVM intercepts blocking calls in `java.io`, `java.net`, `java.nio`, `java.util.concurrent.locks`, `Thread.sleep()`, and many others. When such a call is made inside a virtual thread, the JVM:

1. Captures the current execution state as a **Continuation** object (stack frames, local variables, program counter).
2. Parks the Continuation on the heap.
3. Returns the carrier thread to the pool — the OS thread is now free to run another virtual thread.
4. When the blocking I/O or lock completes (the OS notifies via epoll/kqueue or a lock notifies via `unpark`), the scheduler picks up the Continuation.
5. The scheduler mounts it onto any available carrier thread, restoring the stack and resuming execution right where it left off.

The calling code sees a normal blocking call — no callbacks, no `CompletableFuture` chaining. The JVM handles the suspension and resumption invisibly.

### Continuations Under the Hood

The Continuation mechanism is the primitive that virtual threads are built on. A `Continuation` holds:

- **Stack frames** of every method on the virtual thread's call stack at the point of suspension.
- **Local variables** and operand stack state for each frame.
- A **yield point** indicating where to resume.

Continuations are heap objects, so their cost scales with the depth of the call stack, not with some fixed OS allocation. A shallow stack might need a few kilobytes; a deep recursive call might grow to hundreds of kilobytes — still far cheaper than 1–2 MB per OS thread.

### Pinning — The Critical Exception

A virtual thread is **pinned** to its carrier thread when it cannot be unmounted. This happens in two cases:

1. **Inside a `synchronized` block or method** — JVM object monitors are tied to OS threads; the JVM cannot yet unmount a virtual thread while it holds a monitor lock.
2. **Inside a native method or `Foreign Function` call** — native frames cannot be represented as heap continuations.

When pinned, the virtual thread still blocks, but now its carrier thread blocks with it — which is exactly the behavior you wanted to avoid. In practice, the JVM will expand the carrier pool temporarily if all carriers are pinned, but this is not guaranteed and can still cause thread starvation.

**Detection:** Run your JVM with `-Djdk.tracePinnedThreads=full` or `-Djdk.tracePinnedThreads=short` to log pinning events to stdout.

**Fix:** Replace `synchronized` blocks with `ReentrantLock` (or `ReentrantReadWriteLock`, `StampedLock`), which are virtual-thread-aware and allow unmounting.

---

## Build It / In Depth

### Step 1: Create a Virtual Thread (Simplest Form)

```java
// Java 21+
Thread vt = Thread.ofVirtual().start(() -> {
    System.out.println("Running in: " + Thread.currentThread());
    // Simulate blocking I/O
    try { Thread.sleep(100); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
    System.out.println("Resumed after sleep");
});
vt.join();
```

Output will show something like `VirtualThread[#21]/runnable@ForkJoinPool-1-worker-1` — the virtual thread ID and the carrier it was last mounted on.

### Step 2: Create Millions of Virtual Threads

```java
var latch = new java.util.concurrent.CountDownLatch(100_000);

for (int i = 0; i < 100_000; i++) {
    Thread.ofVirtual().start(() -> {
        try {
            Thread.sleep(1000); // blocked, but carrier thread freed
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } finally {
            latch.countDown();
        }
    });
}

latch.await();
System.out.println("All done");
```

100,000 virtual threads sleeping concurrently — each sleep unmounts from the carrier, so only a handful of OS threads are ever active. Try the same with `new Thread(...)` (platform threads) and you will likely hit OOM or OS limits before 10,000.

### Step 3: ExecutorService with Virtual Threads

```java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    var futures = IntStream.range(0, 10_000)
        .mapToObj(i -> executor.submit(() -> fetchUserFromDb(i)))  // blocking JDBC call
        .toList();

    for (var f : futures) {
        System.out.println(f.get());
    }
}
```

`Executors.newVirtualThreadPerTaskExecutor()` creates a new virtual thread for **every** submitted task. There is no pool size to tune — virtual threads are cheap enough that pooling them is unnecessary (and counterproductive, as it prevents the scheduler from freely creating and discarding them).

### Step 4: Replacing synchronized with ReentrantLock to Avoid Pinning

```java
// BAD: synchronized pins the virtual thread to its carrier
public synchronized void updateCounter() {
    counter++;
}

// GOOD: ReentrantLock allows unmounting
private final ReentrantLock lock = new ReentrantLock();

public void updateCounter() {
    lock.lock();
    try {
        counter++;
    } finally {
        lock.unlock();
    }
}
```

### Step 5: Structured Concurrency (Java 21 Preview, Java 23 GA)

Structured concurrency builds on virtual threads to give fork-join semantics with proper lifecycle management and cancellation:

```java
try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
    var user    = scope.fork(() -> fetchUser(userId));
    var account = scope.fork(() -> fetchAccount(userId));

    scope.join().throwIfFailed();

    return new Dashboard(user.get(), account.get());
}
// When the try block exits, all forked tasks are guaranteed to be done or cancelled
```

Both `fetchUser` and `fetchAccount` run concurrently in virtual threads. If either fails, `ShutdownOnFailure` cancels the other, and the scope's `close()` ensures no task outlives the parent.

### Lifecycle Diagram

```
Virtual Thread lifecycle:
                       blocking call detected
  NEW ──► RUNNABLE ──────────────────────────► WAITING (Continuation on heap)
              ▲                                          │
              │           carrier freed                  │ I/O complete / lock available
              │                                          ▼
              └──────────────── RUNNABLE (re-queued) ◄──┘
                  scheduler mounts on any carrier
```

---

## Use It

### Frameworks and Libraries

| Technology | Virtual Thread Support | Notes |
|---|---|---|
| **Spring Boot 3.2+** | `spring.threads.virtual.enabled=true` | Enables virtual threads for Tomcat, Jetty, Undertow request handling |
| **Tomcat 10.1.x** | Automatic when Java 21 detected | No config needed beyond JDK version |
| **Quarkus** | Virtual thread annotations (`@RunOnVirtualThread`) | Per-endpoint opt-in; reactive default still available |
| **Micronaut** | Supported via executor config | `micronaut.executors.default.type: virtual` |
| **Helidon Níma** | Built from the ground up for virtual threads | Server and client both use virtual threads natively |
| **JDBC drivers** | All major drivers (PostgreSQL, MySQL, HikariCP) | Blocking calls unmount; connection pools may need smaller sizes |
| **gRPC-Java** | Supported with virtual thread executor | Replace `directExecutor` with `newVirtualThreadPerTaskExecutor` |

### When to Use Virtual Threads

- **High-concurrency I/O-bound workloads**: web servers, REST API clients, database fan-out queries, message consumers.
- **Thread-per-request servers** where you want simple blocking code with reactive-level throughput.
- **Replacing thread pools** that were sized conservatively due to memory pressure.

### When NOT to Use Virtual Threads

- **CPU-bound workloads** (image processing, cryptography, compression): virtual threads offer no advantage; use platform threads or `ForkJoinPool.commonPool()`.
- **Code with heavy `synchronized` usage** that you cannot refactor: pinning negates the benefit.
- **Native code / JNI-heavy paths**: these pin and hold the carrier.
- **Thread-local abuse**: `ThreadLocal` values are inherited by virtual threads but each virtual thread gets its own copy, which can be unexpected if you are using thread-locals as connection or session affinity mechanisms.

---

## Common Pitfalls

- **Leaving `synchronized` on hot paths.** The most common trap after adopting virtual threads. Profile with `-Djdk.tracePinnedThreads=full` and replace synchronized blocks on I/O-touching code with `ReentrantLock`. Not every `synchronized` block needs replacing — only those where the thread blocks.

- **Over-sizing the connection pool.** With platform threads, you tuned HikariCP to 200 connections to match your thread pool. With virtual threads, you can submit 10,000 tasks concurrently but your database can still only handle 100 connections. The pool becomes the bottleneck in a different way. Tune `maximumPoolSize` to what your database supports, not to what your concurrency level is.

- **Treating virtual threads like coroutines / actors.** Virtual threads are still JVM threads. `Thread.currentThread()` works, `ThreadLocal` works, `InterruptedException` is still the cancellation mechanism, and stack traces are full and readable. Don't reach for a coroutine abstraction on top — you don't need it.

- **CPU-bound tasks blocking carriers.** Submitting heavy computation on a virtual thread does not help and may hurt, because a CPU-bound virtual thread is never voluntarily unmounted — it just occupies a carrier thread until the computation finishes, starving other virtual threads that need that carrier.

- **ThreadLocal for per-request context.** If 1 million virtual threads all inherit the same parent's `ThreadLocal`, you get 1 million copies of that context object. Use `ScopedValue` (Java 21 Preview, Java 23 GA) instead — it's designed for virtual-thread-scale propagation without per-thread copying.

---

## Exercises

1. **Easy** — Write a program that spawns 10,000 virtual threads, each sleeping for 2 seconds, and measures total wall-clock time. Repeat with platform threads. Compare and explain the difference.

2. **Medium** — Build a mini HTTP fan-out: given a list of 500 URLs, fetch each one in a separate virtual thread (use `java.net.http.HttpClient` in blocking mode) and collect status codes. Add a `CountDownLatch` to ensure all fetches complete. Introduce a single badly-synchronized shared counter inside the fetch loop and detect the pinning event using JVM flags.

3. **Hard** — Implement a connection-pool-backed task runner that limits concurrency to at most 50 active database connections, even when 5,000 virtual threads are submitted simultaneously. Use a `Semaphore` to gate access. Benchmark throughput and latency percentiles (p50, p99) and compare against a `ThreadPoolExecutor` with 50 platform threads doing the same work.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Virtual Thread** | A "lightweight coroutine" abstraction | A JVM-managed thread backed by a heap-stored Continuation; fully compatible with the `Thread` API |
| **Carrier Thread** | A dedicated thread assigned to one virtual thread | A platform (OS) thread in the ForkJoinPool that virtual threads mount and unmount on dynamically |
| **Continuation** | A callback or a promise | A heap object capturing a suspended virtual thread's entire call stack, locals, and program counter |
| **Pinning** | A performance hint or a scheduling preference | A hard constraint where the virtual thread cannot unmount from its carrier, causing the carrier OS thread to block |
| **Unmounting** | Pausing a thread | Saving the virtual thread's Continuation to the heap and returning the carrier to the pool — the OS thread is freed immediately |
| **Platform Thread** | The old, slow, deprecated thread type | A normal JVM thread backed 1:1 by an OS thread; still the right choice for CPU-bound or native-code-heavy work |
| **Structured Concurrency** | A fancy thread pool abstraction | A scoping mechanism that ties the lifetime of forked virtual threads to a lexical scope, enabling automatic cancellation and cleaner error propagation |

---

## Further Reading

- [JEP 444: Virtual Threads (Java 21)](https://openjdk.org/jeps/444) — the authoritative spec and design rationale from the OpenJDK team.
- [JEP 453: Structured Concurrency](https://openjdk.org/jeps/453) — how structured concurrency builds on top of virtual threads.
- [Inside Java Podcast #23 – Virtual Threads Deep Dive](https://inside.java/2023/02/06/podcast-023/) — Ron Pressler and Alan Bateman, the feature leads, explaining design decisions.
- [Spring Boot 3.2 Virtual Threads Migration Guide](https://docs.spring.io/spring-boot/docs/3.2.x/reference/html/features.html#features.spring-application.virtual-threads) — practical Spring-specific configuration and caveats.
- [Project Loom: Modern Scalable Concurrency for the Java Platform](https://cr.openjdk.org/~rpressler/loom/loom/sol1_part1.html) — Ron Pressler's detailed technical write-up on Loom's design philosophy and implementation strategy.
