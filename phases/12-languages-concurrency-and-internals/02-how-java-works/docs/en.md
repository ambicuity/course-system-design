# How Java Works

> Java's portability promise is kept by a virtual machine that interprets bytecode, then compiles the hot paths to native code at runtime.

**Type:** Learn
**Prerequisites:** How the OS Executes a Program, Memory Management Basics
**Time:** ~25 minutes

---

## The Problem

You've deployed a Java service to production. On the first few requests, latency is 300 ms. By the tenth minute, the same requests take 18 ms. You haven't changed anything. What happened?

Or: a teammate adds a new JAR to the classpath. Suddenly the application throws `NoClassDefFoundError` at startup despite the class existing in three different JARs. You spent two hours debugging a ClassLoader hierarchy you didn't know existed.

Or: you profile a service and discover that 40% of CPU time is spent in the garbage collector. The heap is 8 GB, but GC still pauses every few seconds. You don't know why because you've never modelled what the JVM does with memory.

All three scenarios trace back to the same root cause: Java does not run directly. It compiles to an intermediate representation and then executes inside a managed runtime that handles class loading, bytecode verification, JIT compilation, and garbage collection. Understanding that pipeline turns these mysteries into predictable, fixable problems.

---

## The Concept

### The Compilation Pipeline

Java separates compilation into two distinct phases.

**Phase 1 — Static compilation (`javac`).** The Java compiler reads `.java` source files and emits `.class` files containing *bytecode* — a compact, platform-neutral instruction set defined by the JVM specification. Bytecode is not machine code; it targets an abstract stack-based virtual machine, not any real CPU.

**Phase 2 — Runtime execution (JVM).** The Java Virtual Machine is a platform-specific binary that interprets or compiles bytecode into native instructions for the host CPU. You ship the same `.class` files everywhere; the JVM per platform handles the rest. This is the "Write Once, Run Anywhere" guarantee.

```
Source (.java)
     │
     ▼  javac (static compiler)
Bytecode (.class)
     │
     ▼  JVM (platform-specific runtime)
  ┌──────────────────────────────────────────┐
  │  1. Class Loader Subsystem               │
  │  2. Bytecode Verifier                    │
  │  3. Execution Engine                     │
  │       ├── Interpreter (slow start)       │
  │       └── JIT Compiler (hot paths)       │
  │  4. Garbage Collector                    │
  └──────────────────────────────────────────┘
     │
     ▼
  Native machine code executed by the CPU
```

### The Class Loader Subsystem

Classes are loaded lazily — on first reference, not at startup. Three built-in loaders form a strict parent-delegation hierarchy:

| Loader | Loads | Source |
|---|---|---|
| Bootstrap | `java.lang`, `java.util`, core JDK | `$JAVA_HOME/lib/rt.jar` (or modules in Java 9+) |
| Platform (Extension) | JDK extension modules | `$JAVA_HOME/lib/ext` or named modules |
| Application | Your code and third-party JARs | `-classpath` / `-cp` |

When a class is requested, the loader asks its *parent* first. Only if the parent can't find it does the child attempt to load. This prevents user code from shadowing `java.lang.String`. Frameworks that break this contract (OSGi, some app servers) use custom loaders and are the source of most `ClassNotFoundException` / `NoClassDefFoundError` confusion.

### Bytecode Verification

Before any bytecode runs, the verifier checks structural correctness: operand stack never overflows/underflows, local variable types are consistent, jumps land inside valid instructions. This pass eliminates whole classes of security vulnerabilities and is why the JVM can safely run untrusted code.

### The Execution Engine: Interpreter + JIT

The JVM starts by **interpreting** bytecode — one instruction at a time. Slow, but safe and zero warm-up cost. Simultaneously, the HotSpot runtime profiles execution:

- It counts how many times each method is called and how many times each loop back-edge is taken.
- Methods that cross an invocation threshold (~1,000–10,000 calls by default) are flagged as *hot*.
- Hot code is handed to the **JIT compiler**, which emits optimised native machine code for that specific method.

HotSpot uses **tiered compilation** (default since Java 8):

| Tier | Compiler | Characteristics |
|---|---|---|
| 0 | Interpreter | No compilation, profiling starts |
| 1–3 | C1 (client) | Fast compile, light optimisation, profiling data collected |
| 4 | C2 (server) | Slow compile, aggressive inlining, loop unrolling, dead-code elimination |

This explains the initial latency spike: the service is running interpreted code. After a few hundred requests, the hottest methods reach tier 4 and run near C++ speed.

C2 can also perform *speculative optimisations* (e.g., devirtualise a polymorphic call if only one implementation has been seen). If a new class later violates the assumption, the JVM *deoptimises* back to interpretation — you may occasionally see this in heap dumps or async-profiler output as "trap" events.

### JVM Memory Layout

```
┌─────────────────────────────────────────────┐
│  Heap (shared across all threads)           │
│  ┌─────────────────┐  ┌──────────────────┐  │
│  │  Young Gen      │  │   Old Gen        │  │
│  │  Eden │ S0 │ S1 │  │  (tenured objs)  │  │
│  └─────────────────┘  └──────────────────┘  │
├─────────────────────────────────────────────┤
│  Metaspace (off-heap, replaces PermGen)     │
│  Class metadata, method bytecode, statics  │
├─────────────────────────────────────────────┤
│  Per-thread stacks (one per Java thread)    │
│  Frames → local vars, operand stack, PC    │
├─────────────────────────────────────────────┤
│  Native / Code Cache (JIT output)           │
└─────────────────────────────────────────────┘
```

- **Young Gen** holds short-lived objects. Minor GC runs frequently and is cheap — it collects Eden + one survivor space.
- **Old Gen** holds objects that survived several minor GCs. Major (full) GC is slow and causes stop-the-world pauses.
- **Metaspace** grows dynamically by default. Unlimited class generation (reflection, proxies, JSP compilation) causes Metaspace OOM.
- **Code Cache** stores JIT-compiled native code. If it fills up, the JVM falls back to interpretation — a surprising performance cliff.

---

## Build It / In Depth

### Step 1 — Write and compile

```java
// Counter.java
public class Counter {
    private int count = 0;

    public int increment() {
        return ++count;
    }

    public static void main(String[] args) {
        Counter c = new Counter();
        for (int i = 0; i < 1_000_000; i++) {
            c.increment();
        }
        System.out.println(c.count);
    }
}
```

```bash
javac Counter.java      # emits Counter.class
```

### Step 2 — Inspect the bytecode

```bash
javap -c Counter.class
```

Partial output for `increment()`:

```
public int increment();
  Code:
     0: aload_0
     1: dup
     2: getfield      #7   // Field count:I
     5: iconst_1
     6: iadd
     7: dup_x1
     8: putfield      #7   // Field count:I
    11: ireturn
```

`aload_0` pushes `this` onto the operand stack. `getfield` reads `count`. `iconst_1` + `iadd` increments it. `putfield` writes it back. `ireturn` returns the new value. This stack-based bytecode is exactly what the interpreter executes instruction-by-instruction before JIT kicks in.

### Step 3 — Observe JIT in action

Run with `-XX:+PrintCompilation` to see real-time JIT decisions:

```bash
java -XX:+PrintCompilation Counter
```

Sample output (abbreviated):

```
     72    1       3       java.lang.String::hashCode (55 bytes)
    104   14       4       Counter::increment (9 bytes)
    104   13       3       Counter::increment (9 bytes)   made not entrant
```

`Counter::increment` first compiled at tier 3 (C1), then recompiled at tier 4 (C2), with the tier-3 version marked `made not entrant` (threads migrate to C2 code on next call).

### Step 4 — Verify class loading order

```bash
java -verbose:class Counter 2>&1 | head -30
```

You'll see bootstrap classes loaded first (`java.lang.Object`, `java.lang.String`, …), then your application classes. The output confirms the loading sequence and which loader was responsible.

---

## Use It

| Technology | How Java internals apply |
|---|---|
| **Spring Boot** | Application loader scans the fat JAR; Spring creates a custom loader for child contexts. ClassLoader isolation is why you can have multiple bean definitions with the same name in different modules. |
| **GraalVM Native Image** | Performs AOT compilation ahead of time, producing a self-contained native binary. No JVM at runtime, no JIT warm-up, startup in milliseconds — at the cost of some dynamic features (reflection must be declared). Ideal for CLI tools and serverless cold starts. |
| **Kotlin / Scala / Clojure** | Compile to JVM bytecode. Kotlin's `data class` desugars to Java bytecode with `equals`/`hashCode`; Scala's tail-call optimisation rewrites the bytecode loop. They all share the same JIT and GC infrastructure. |
| **JVM flags for production** | `-Xms`/`-Xmx` (heap bounds), `-XX:+UseG1GC` or `-XX:+UseZGC` (collector choice), `-XX:ReservedCodeCacheSize` (JIT cache), `-XX:MetaspaceSize` (initial Metaspace). |
| **Profilers (async-profiler, JFR)** | Sample at the native-code level, correlating C2-compiled frames back to Java method names. Essential for finding where JIT spent CPU. |
| **Containerised Java** | Java <8u191 didn't read cgroup limits; JVM sized heap to host RAM and fork-bombed itself. Modern JVMs use `-XX:+UseContainerSupport` (default on) to read cgroup memory/CPU limits correctly. |

---

## Common Pitfalls

- **Cold-start SLAs in prod.** JIT hasn't warmed up, so the first N requests to a freshly deployed service are slow. Mitigate with staged rollouts, request warm-up scripts, or GraalVM Native Image for latency-sensitive paths.

- **ClassLoader leaks in long-running servers.** Every dynamically loaded class retains a reference to its ClassLoader. If you create a new ClassLoader per request (JSP hot-reload, plugin systems), old ones accumulate in Metaspace. Watch `jstat -gc` for Metaspace growth and cap it with `-XX:MaxMetaspaceSize`.

- **Trusting `-Xmx` as the total memory footprint.** The JVM consumes heap *plus* Metaspace *plus* thread stacks *plus* the Code Cache *plus* direct buffers (NIO). A container with 1 GB limit and `-Xmx768m` can still OOMKill if off-heap usage is not accounted for. Use `-XX:+AlwaysPreTouch` in tests to catch this early.

- **Misdiagnosing GC pauses as CPU bottlenecks.** High GC CPU time looks like an application hotspot in coarse profilers. Use JFR (`-XX:StartFlightRecording`) or GC logs (`-Xlog:gc*`) to separate GC work from application work before optimising the wrong thing.

- **Disabling JIT for "reproducibility".** Running with `-Xint` (interpreter-only) to get deterministic benchmarks is legitimate in micro-benchmark harnesses, but deploying to production with it will give you 10–50× worse throughput. Always benchmark with JIT enabled in a warmed-up state.

---

## Exercises

1. **Easy.** Compile any small Java file with `javac` and run `javap -c` on the output. Find the bytecode instruction that corresponds to an addition operation (`iadd`, `ladd`, `fadd`, or `dadd`). What does the surrounding instruction sequence look like?

2. **Medium.** Write a Java method that is intentionally *not* JIT-compiled (call it only once). Then write a second version that calls the same logic 100,000 times. Run both with `-XX:+PrintCompilation` and compare outputs. What threshold triggers compilation? Try changing `-XX:CompileThreshold` and observe.

3. **Hard.** Build a program that generates synthetic classes at runtime using `java.lang.reflect.Proxy` or a bytecode generation library (ASM or ByteBuddy) in a loop. Monitor Metaspace with `jstat -gcmetacapacity <pid>`. Observe the growth. Then add a proper ClassLoader lifecycle (load → use → discard) and confirm Metaspace stabilises.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **JVM** | A runtime that interprets Java | A specification for a virtual machine; HotSpot, OpenJ9, and GraalVM are different *implementations* |
| **Bytecode** | Compiled machine code for Java | Platform-neutral intermediate instructions targeting an abstract stack machine, not any real CPU |
| **JIT** | Compiles all Java to native code on first run | Compiles only *hot* paths — methods that exceed invocation/back-edge thresholds — and uses profiling data to guide optimisations |
| **ClassLoader** | One global class loader for all code | A hierarchy of loaders with parent-delegation; frameworks often add custom loaders, creating isolated namespaces |
| **Garbage Collector** | Automatically frees memory for you | Reclaims heap memory on a schedule that may pause all threads (stop-the-world), with frequency and pause length tunable via flags |
| **PermGen** | Where class metadata lives | Removed in Java 8; replaced by **Metaspace**, which is off-heap and grows dynamically by default |
| **Native Image (GraalVM)** | A way to make Java faster at runtime | AOT compilation that eliminates the JVM entirely — no ClassLoader, no JIT, no GC warm-up — a different trade-off, not a strict upgrade |

---

## Further Reading

- [JVM Specification (SE 21)](https://docs.oracle.com/javase/specs/jvms/se21/html/index.html) — the authoritative definition of bytecode, the class file format, and the execution model.
- [HotSpot JVM Deep Dive — JIT Compilation](https://openjdk.org/groups/hotspot/docs/HotSpotGlossary.html) — glossary of HotSpot internals including tiered compilation terms.
- [GraalVM Native Image Docs](https://www.graalvm.org/latest/reference-manual/native-image/) — official guide to AOT compilation, reflection configuration, and trade-offs.
- [Java Flight Recorder & JDK Mission Control](https://docs.oracle.com/javacomponents/jmc-5-4/jfr-runtime-guide/about.htm) — production-safe low-overhead profiling built into the JVM.
- *"Java Performance: The Definitive Guide"* by Scott Oaks (O'Reilly) — covers GC tuning, JIT profiling, and benchmarking methodology in depth.
