# How Python Works

> CPython doesn't run your source code — it compiles it to bytecode, then walks that bytecode through a stack-based virtual machine protected by a single mutex.

**Type:** Learn
**Prerequisites:** Operating System Processes and Threads, How Memory Works
**Time:** ~35 minutes

---

## The Problem

You hire a Python engineer who insists that adding more threads to a CPU-bound data-processing job will speed it up. You know instinctively it won't, but you can't explain *why* in a job-interview or architecture review. You ship the multi-threaded version, it's actually slower, and now you've lost two sprints.

A second scenario: you deploy a Python service and memory creeps up by 50 MB every hour. There is no obvious leak in the application logic. If you don't know that Python uses reference counting with a generational garbage collector on top, and that cyclic garbage can linger across collection cycles, you'll spend days grepping for the wrong thing.

A third scenario: your team switches a hot path from pure Python to a C extension expecting a 10× speedup. You get 2×. You never suspected that benchmark-level gains vanish once the GIL re-engage costs, interpreter startup overhead, and Python-object marshalling costs are factored in.

Understanding how CPython actually executes your code — from source file to bytecode to the virtual machine to memory reclamation — turns these mysteries into predictable engineering tradeoffs.

---

## The Concept

### The CPython Execution Pipeline

CPython (the reference implementation written in C) runs Python code through five distinct stages:

```
  your_script.py
       │
       ▼
  ┌─────────────┐
  │  Lexer /    │  tokenize source text into a stream of tokens
  │  Tokenizer  │
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  Parser     │  build a Concrete Syntax Tree (CST), then an AST
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  Compiler   │  walk the AST, emit bytecode instructions
  └──────┬──────┘
         ▼
  ┌─────────────┐  stored in __pycache__/*.pyc (PEP 3147)
  │  .pyc file  │  re-used on subsequent runs if mtime/hash unchanged
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  CPython VM │  frame-by-frame execution on a value stack
  │  (ceval.c)  │  one thread holds the GIL at any moment
  └─────────────┘
```

### Bytecode and the Value Stack

The CPython VM is a **stack machine**. Each function call produces a *frame* object that contains:

- a reference to the code object (bytecode + constants + names)
- a value stack for operands
- a pointer to the enclosing frame
- local variable slots

The `dis` module exposes the bytecode directly:

```python
import dis

def add(a, b):
    return a + b

dis.dis(add)
```

Output:
```
  2           0 RESUME          0

  3           2 LOAD_FAST       0 (a)
              4 LOAD_FAST       1 (b)
              6 BINARY_OP      0 (+)
             10 RETURN_VALUE
```

Each opcode is one or two bytes. The VM executes a tight `switch`/`goto` loop in `ceval.c`, dispatching each opcode to a C handler. That handler may call back into Python (e.g., `__add__`), which pushes a new frame.

### The GIL (Global Interpreter Lock)

The GIL is a mutex inside CPython that ensures **only one thread executes Python bytecode at a time**. It exists because CPython's reference counting is not thread-safe: without the GIL, two threads could race on the same object's refcount and corrupt it.

```
  Thread A        Thread B
  ─────────       ─────────
  acquire GIL ──▶
  run 100 bytecodes
  release GIL ──▶
                  acquire GIL ──▶
                  run 100 bytecodes
                  release GIL ──▶
```

Key implications:

| Workload | Threads help? | Why |
|---|---|---|
| I/O-bound (network, disk) | Yes | GIL released during syscalls |
| CPU-bound (math, parsing) | No | GIL held the entire time |
| C extensions that release GIL | Yes | NumPy, hashlib release GIL in hot loops |

The GIL is dropped automatically during blocking I/O and whenever a C extension explicitly calls `Py_BEGIN_ALLOW_THREADS`. That is why `asyncio` and `threading` work perfectly fine for web servers — waiting for a socket releases the GIL immediately.

### Memory Management: Refcounting + Cyclic GC

Every Python object carries a `ob_refcnt` field. CPython increments it when a reference is created and decrements it when a reference is deleted. When `ob_refcnt` hits zero, the object is deallocated *immediately* — no GC pause.

```
  x = []          # refcount 1
  y = x           # refcount 2
  del x           # refcount 1
  del y           # refcount 0 → freed immediately
```

**The cycle problem**: if object A holds a reference to object B and B holds one back to A, neither refcount ever reaches zero even if nothing else references them. CPython's cyclic garbage collector (the `gc` module) runs periodically and uses a tri-generation scheme to detect and collect such cycles.

```python
import gc, sys

a = []
b = [a]
a.append(b)       # cycle: a ↔ b

del a, del b
print(gc.collect())  # forces a collection cycle; prints objects freed
```

The default collection thresholds (`gc.get_threshold()` → `(700, 10, 10)`) mean generation 0 triggers every 700 net object allocations.

### The Import System

When Python executes `import foo`, it:

1. Checks `sys.modules` — if already imported, returns the cached module object (no re-execution).
2. Searches `sys.meta_path` finders in order (e.g., `BuiltinImporter`, `FrozenImporter`, `PathFinder`).
3. Calls the finder's `find_spec()` to locate the module.
4. The loader compiles and executes the module's code in a fresh namespace, then stores it in `sys.modules`.

This is why **circular imports** cause `AttributeError` or `ImportError`: when module A imports module B and B tries to import A, Python finds an *incomplete* `A` in `sys.modules` (it's there, but only partially initialized).

---

## Build It / In Depth

### Step 1 — Inspect Bytecode

```python
# file: demo.py
import dis

def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

dis.dis(factorial)
```

Run it and study the `CALL` opcode. In CPython 3.12+, function calls were significantly optimized (`CALL` replaced many `CALL_FUNCTION*` variants). Bytecode evolves across minor versions — never serialize `.pyc` files across Python releases.

### Step 2 — Observe Reference Counts

```python
import sys

x = object()
print(sys.getrefcount(x))   # 2: one for x, one for getrefcount's argument

y = x
print(sys.getrefcount(x))   # 3

del y
print(sys.getrefcount(x))   # 2 again
```

`sys.getrefcount` always adds 1 because the call itself creates a temporary reference.

### Step 3 — GIL in Action: CPU-Bound Threading

```python
import threading, time

COUNT = 50_000_000

def countdown(n):
    while n > 0:
        n -= 1

# single-threaded
start = time.perf_counter()
countdown(COUNT)
print("single:", time.perf_counter() - start, "s")

# two threads — expect similar or WORSE time due to GIL contention
t1 = threading.Thread(target=countdown, args=(COUNT // 2,))
t2 = threading.Thread(target=countdown, args=(COUNT // 2,))
start = time.perf_counter()
t1.start(); t2.start()
t1.join(); t2.join()
print("two threads:", time.perf_counter() - start, "s")
```

On a multi-core machine, two threads are frequently *slower* than one because of GIL acquisition contention and OS scheduling overhead. Replace threads with `multiprocessing.Process` and each process gets its own GIL; you'll see near-linear speedup.

### Step 4 — Force a GC Cycle

```python
import gc

gc.disable()          # turn off automatic collection
gc.collect()          # still works on demand

class Node:
    def __init__(self, name):
        self.name = name
        self.next = None

a = Node("a")
b = Node("b")
a.next = b
b.next = a            # cycle

del a, del b
print("before collect:", gc.get_count())   # objects pending
print("freed:", gc.collect())              # trigger collection
print("after collect:", gc.get_count())
```

### Complete Flow Diagram

```
  source.py
    │
    ├─── Lexer ──▶ tokens
    │
    ├─── Parser ──▶ AST
    │
    ├─── Compiler ──▶ code object (bytecode + consts + names)
    │                        │
    │                   cached as .pyc
    │
    └─── CPython VM (ceval.c)
              │
              ├── per-thread: frame stack
              │         frame: locals[], value_stack[], code_obj*
              │
              ├── GIL: one thread holds at a time
              │
              └── Memory: ob_refcnt dec → 0 = immediate free
                          cyclic GC: generational sweep for cycles
```

---

## Use It

### CPython vs Alternative Runtimes

| Runtime | How it differs | Best for |
|---|---|---|
| **CPython** | Bytecode + VM, GIL | General purpose; the default |
| **PyPy** | JIT compiler, no traditional GIL | Long-running CPU-bound pure Python |
| **Cython** | Transpiles Python-like code to C | Numeric kernels, C interop |
| **Jython** | Runs on JVM, no GIL | Java ecosystem integration |
| **GraalPy** | GraalVM JIT, polyglot | Experimental; multi-language interop |

### When Threads vs Processes vs Asyncio

| Pattern | Module | Use when |
|---|---|---|
| Concurrency, I/O-bound | `threading` / `asyncio` | Web requests, DB queries, disk I/O |
| Parallelism, CPU-bound | `multiprocessing` | Image processing, ML inference, parsing |
| Cooperative multitasking | `asyncio` + `await` | Thousands of concurrent I/O operations |
| Offload to C | NumPy, Pillow, etc. | Numeric work; GIL released in C code |

### Real Systems

- **Django/Flask/FastAPI** run behind multi-worker servers (Gunicorn with `--workers`) — each worker is a separate OS process with its own GIL, bypassing the threading limitation entirely.
- **Celery** spawns worker processes for CPU-intensive background tasks.
- **NumPy** releases the GIL in C for matrix operations, which is why `np.dot` benefits from threading in some scientific libraries.
- **CPython 3.13** introduced an **experimental free-threaded build** (`--disable-gil`) — the GIL becomes optional, trading some single-thread overhead for true CPU parallelism.

---

## Common Pitfalls

- **Assuming threads parallelize CPU work.** The GIL serializes Python bytecode execution. Use `multiprocessing` or C extensions that release the GIL for CPU-heavy tasks. Profiling with `py-spy` will show all threads idle except one.

- **Mutating a container while iterating it.** Python's `for` loop holds an iterator that doesn't freeze the container. Adding or removing items mid-iteration causes skipped or duplicated elements. Iterate over a copy: `for item in list(my_list):`.

- **Circular imports.** Module A imports B; B imports A at module scope. Python partially executes A, puts the incomplete module in `sys.modules`, then B gets an empty namespace. Fix: move imports inside functions, use lazy imports, or refactor to break the cycle.

- **Trusting `.pyc` cache across Python versions.** The `.pyc` magic number encodes the Python version. A `.pyc` built on 3.11 will be rejected by 3.12 and recompiled. Never include `__pycache__` in version-control artifacts expected to run on a different Python version.

- **Ignoring cyclic reference leaks.** `del` on an object involved in a cycle doesn't free it immediately. In long-running services, large cyclic object graphs accumulate until the generational GC sweeps them. Use weak references (`weakref.ref`) for back-links in caches and parent-child graphs.

---

## Exercises

1. **Easy** — Run `python -m dis yourscript.py` on a file containing a simple `for` loop. Identify the `GET_ITER`, `FOR_ITER`, and `JUMP_BACKWARD` opcodes and explain what each does in the context of the value stack.

2. **Medium** — Write a benchmark that sums 100 million integers using (a) a single thread, (b) two threads, and (c) two processes (`multiprocessing`). Record wall-clock time and CPU time for each. Explain the results in terms of the GIL and process isolation.

3. **Hard** — Create a small caching decorator that stores results in a module-level dictionary. Then deliberately introduce a cyclic reference between cache entries (e.g., the cached value holds a reference back to the cache dict). Use `gc.set_debug(gc.DEBUG_LEAK)` and `gc.collect()` to detect the cycle. Refactor the decorator to use `weakref.WeakValueDictionary` and confirm the leak disappears.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **GIL** | A bug that should be removed | A mutex protecting CPython's non-thread-safe C internals; being made optional in 3.13 |
| **Bytecode** | Machine code for Python | Compact integer opcodes interpreted by the CPython VM; not native CPU instructions |
| **PVM** | A JVM-style Just-In-Time compiler | A simple interpreter loop (`ceval.c`) that dispatches bytecodes; no JIT in standard CPython |
| **`.pyc` file** | A compiled binary, like a `.class` file | Serialized bytecode with a version magic number; skips re-parsing, but still interpreted |
| **Reference counting** | Python's only GC mechanism | The *primary* reclamation strategy; the cyclic GC handles the cycles it cannot reach |
| **`sys.modules`** | A read-only index | A mutable dict; you can inject or delete entries to control import resolution at runtime |
| **Frame** | A call stack entry | A C struct holding locals, the value stack, and the current bytecode offset for one function call |

---

## Further Reading

- [CPython source — `ceval.c`](https://github.com/python/cpython/blob/main/Python/ceval.c) — the main interpreter loop; reading even 200 lines gives deep intuition.
- [Python `dis` module docs](https://docs.python.org/3/library/dis.html) — complete opcode reference for the version you run.
- [PEP 703 — Making the GIL Optional](https://peps.python.org/pep-0703/) — the design rationale and tradeoffs behind CPython's free-threaded mode.
- [Python `gc` module docs](https://docs.python.org/3/library/gc.html) — cyclic garbage collector controls, thresholds, and debug flags.
- *CPython Internals* by Anthony Shaw (Real Python) — a guided tour of the CPython source, with chapters on the compiler, frame evaluation, and memory allocator.
