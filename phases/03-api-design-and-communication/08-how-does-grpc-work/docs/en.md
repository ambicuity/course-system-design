# How does gRPC work?

> gRPC turns cross-service calls into typed, binary, multiplexed function calls — REST with the fat trimmed off.

**Type:** Learn
**Prerequisites:** REST APIs and HTTP, Protocol Buffers basics, Microservices overview
**Time:** ~20 minutes

---

## The Problem

REST over JSON is everywhere, and it works. But once you operate at scale — hundreds of microservices, millions of calls per second, tight latency budgets — the cracks show fast. JSON is text: every integer, boolean, and enum is serialized as human-readable characters, then parsed back on the other end. That parsing is CPU-expensive and the payloads are large. HTTP/1.1 compounds the pain: one request per connection means head-of-line blocking; HTTP headers repeat on every call even when they haven't changed.

Consider an e-commerce platform where the Order Service calls the Payment Service, Inventory Service, and Notification Service for every checkout. If each call takes 10ms of JSON serialization overhead plus 15ms of network round-trip, those costs multiply across every user action. Worse, the REST contract between teams is implicit — a field renamed in the Payment Service's response silently breaks the Order Service at runtime, weeks after the change was deployed.

gRPC was designed to solve exactly this. It enforces a typed, versioned contract through a `.proto` file; uses Protocol Buffers for compact binary serialization; and runs over HTTP/2 for multiplexed, low-latency transport. The result is inter-service calls that behave like strongly typed local function calls — from both a developer ergonomics and a performance standpoint.

---

## The Concept

### The Three-Layer Stack

gRPC is built on three technologies that each do one job:

```
┌─────────────────────────────────────────────────────────────┐
│                   Your Application Code                      │
│           (calls a method like a local function)            │
├─────────────────────────────────────────────────────────────┤
│               gRPC Framework (generated stubs)              │
│   - Client stub: marshals args → binary, sends, awaits      │
│   - Server skeleton: receives, unmarshals, dispatches        │
├─────────────────────────────────────────────────────────────┤
│              Protocol Buffers (serialization)               │
│   - Compact binary encoding (~3-10x smaller than JSON)      │
│   - Schema-first: .proto file is the source of truth        │
├─────────────────────────────────────────────────────────────┤
│                   HTTP/2 (transport)                        │
│   - Multiplexed streams over one TCP connection             │
│   - Header compression (HPACK), binary framing             │
│   - Bidirectional streaming                                 │
└─────────────────────────────────────────────────────────────┘
```

### Protocol Buffers: The Contract

Before writing any application code, you define a `.proto` file. This file is the single source of truth for what messages are exchanged and what procedures can be called.

```proto
syntax = "proto3";

package payments;

service PaymentService {
  rpc ProcessPayment (PaymentRequest) returns (PaymentResponse);
  rpc StreamTransactions (TransactionFilter) returns (stream Transaction);
}

message PaymentRequest {
  string order_id   = 1;
  int64  amount_cents = 2;
  string currency   = 3;
}

message PaymentResponse {
  string transaction_id = 1;
  bool   success        = 2;
  string error_message  = 3;
}
```

The numbers (`= 1`, `= 2`, `= 3`) are **field tags** — they become the field identifiers in the binary encoding. They must never change once a service is in production because the binary format uses them, not the field names. Renaming a field is safe; renumbering is not.

The `protoc` compiler reads this file and generates:
- A **client stub** in the language of your choice (Go, Python, Java, Rust, etc.) with fully typed method calls
- A **server interface** that your implementation must satisfy

This code generation is why gRPC is "schema-first." There is no "send whatever JSON you like" escape hatch.

### Binary Encoding — Why It's Faster

A Protocol Buffers message is encoded as a sequence of `(tag, wire_type, value)` tuples. There are no field names in the wire format — only numbers. Consider this comparison for a small response:

| Representation | Bytes (approx.) |
|---|---|
| `{"success":true,"transaction_id":"txn_abc123","error_message":""}` JSON | 62 bytes |
| Same message in protobuf binary | ~14 bytes |

Beyond size, the binary format is parsed with a single memory scan. JSON parsers must handle unicode, escape sequences, number coercion, and whitespace — protobuf has none of that ambiguity.

### HTTP/2: The Transport Multiplexer

REST services typically use HTTP/1.1, which means each request needs its own connection (or at best, pipelining with no true parallelism). HTTP/2 introduces **streams** — lightweight logical channels multiplexed over a single TCP connection.

```
HTTP/1.1 (one request per connection slot)
Client ──[REQ1]──────────[REQ2]──────────[REQ3]──► Server
       ◄─────[RES1]──────────[RES2]──────────[RES3]─

HTTP/2 (multiple streams over one connection)
Client ──[STREAM 1: REQ]──[STREAM 3: REQ]──[STREAM 5: REQ]──► Server
       ◄─[STREAM 2: RES]──[STREAM 4: RES]──[STREAM 6: RES]──
```

HTTP/2 also compresses headers using HPACK. In service-to-service calls where headers like `Content-Type`, `Authorization`, and `User-Agent` repeat on every request, this compression alone saves meaningful bandwidth.

### Four RPC Types

gRPC supports four call patterns, not just request/response:

| Pattern | Client sends | Server sends | Use case |
|---|---|---|---|
| **Unary** | 1 message | 1 message | Standard request/response (e.g., process payment) |
| **Server streaming** | 1 message | N messages (stream) | Live feeds, large dataset pagination |
| **Client streaming** | N messages (stream) | 1 message | File upload, telemetry batching |
| **Bidirectional streaming** | N messages | N messages | Chat, real-time collaboration, game state sync |

Streaming types are defined in the `.proto` with the `stream` keyword:

```proto
// Unary
rpc GetUser (UserRequest) returns (UserResponse);

// Server streaming
rpc WatchOrders (WatchRequest) returns (stream Order);

// Client streaming
rpc UploadChunks (stream Chunk) returns (UploadResult);

// Bidirectional streaming
rpc Chat (stream ChatMessage) returns (stream ChatMessage);
```

### End-to-End Request Flow

Here is how a single **unary** gRPC call travels from a frontend → Order Service → Payment Service:

```
Browser / Mobile Client
        │
        │  REST + JSON (external-facing)
        ▼
  Order Service (gRPC Client)
  ┌──────────────────────────────────────────────┐
  │ 1. Receives REST request from browser        │
  │ 2. Builds PaymentRequest protobuf message    │
  │ 3. Calls generated stub method:              │
  │    stub.ProcessPayment(req)                  │
  │ 4. Stub serializes to binary                 │
  │ 5. Stub wraps in HTTP/2 DATA frames          │
  └──────────────────────────────────────────────┘
        │
        │  HTTP/2 binary frames (TLS)
        ▼
  Payment Service (gRPC Server)
  ┌──────────────────────────────────────────────┐
  │ 6. HTTP/2 layer receives frames              │
  │ 7. gRPC runtime reassembles message          │
  │ 8. Deserializes binary → PaymentRequest      │
  │ 9. Dispatches to handler: ProcessPayment()   │
  │10. Handler executes business logic           │
  │11. Builds PaymentResponse protobuf           │
  │12. Serializes → binary → HTTP/2 frames       │
  └──────────────────────────────────────────────┘
        │
        │  HTTP/2 binary frames (TLS)
        ▼
  Order Service (receives response)
  ┌──────────────────────────────────────────────┐
  │13. Deserializes binary → PaymentResponse     │
  │14. Returns typed Go/Java/Python struct        │
  │15. Converts to JSON, responds to browser     │
  └──────────────────────────────────────────────┘
```

Steps 3-13 are invisible to your application code. You write `stub.ProcessPayment(req)` and get back a `PaymentResponse` — the binary encoding, framing, and transport are handled by the generated stubs and the gRPC runtime.

---

## Build It / In Depth

Let's walk through a complete minimal example in Python using the official `grpcio` library.

**1. Write the contract (`payment.proto`)**

```proto
syntax = "proto3";

package payment;

service PaymentService {
  rpc ProcessPayment (PaymentRequest) returns (PaymentResponse);
}

message PaymentRequest {
  string order_id    = 1;
  int64  amount_cents = 2;
}

message PaymentResponse {
  bool   success        = 1;
  string transaction_id = 2;
}
```

**2. Generate Python code**

```bash
pip install grpcio grpcio-tools

python -m grpc_tools.protoc \
  -I. \
  --python_out=. \
  --grpc_python_out=. \
  payment.proto
```

This produces `payment_pb2.py` (message classes) and `payment_pb2_grpc.py` (stubs and servicers).

**3. Implement the server**

```python
# server.py
import grpc
from concurrent import futures
import uuid
import payment_pb2
import payment_pb2_grpc

class PaymentServicer(payment_pb2_grpc.PaymentServiceServicer):
    def ProcessPayment(self, request, context):
        # Business logic here
        if request.amount_cents <= 0:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("Amount must be positive")
            return payment_pb2.PaymentResponse()

        return payment_pb2.PaymentResponse(
            success=True,
            transaction_id=f"txn_{uuid.uuid4().hex[:8]}"
        )

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    payment_pb2_grpc.add_PaymentServiceServicer_to_server(PaymentServicer(), server)
    server.add_insecure_port("[::]:50051")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
```

**4. Call it from the client**

```python
# client.py
import grpc
import payment_pb2
import payment_pb2_grpc

def run():
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = payment_pb2_grpc.PaymentServiceStub(channel)
        response = stub.ProcessPayment(
            payment_pb2.PaymentRequest(order_id="ord_001", amount_cents=4999)
        )
        print(f"Success: {response.success}, TxnID: {response.transaction_id}")

if __name__ == "__main__":
    run()
```

```bash
# Terminal 1
python server.py

# Terminal 2
python client.py
# Output: Success: True, TxnID: txn_3a7f9e2c
```

**5. Inspecting what travels on the wire**

gRPC sends a 5-byte frame header followed by the binary protobuf body. For the request above, the binary payload for `{order_id: "ord_001", amount_cents: 4999}` is roughly 16 bytes versus ~46 bytes as JSON. You can inspect live gRPC traffic with `grpcurl` (a curl equivalent for gRPC):

```bash
grpcurl -plaintext \
  -d '{"order_id": "ord_001", "amount_cents": 4999}' \
  localhost:50051 \
  payment.PaymentService/ProcessPayment
```

---

## Use It

| Technology / Context | How gRPC applies |
|---|---|
| **Google internal (Stubby)** | gRPC is the open-source successor to Google's internal Stubby RPC system used across all production services |
| **Kubernetes / Envoy** | Envoy proxy natively understands gRPC; Istio service meshes route gRPC traffic with fine-grained load balancing on individual HTTP/2 streams |
| **gRPC-Gateway** | Translates REST/JSON requests to gRPC at the edge — lets you publish one `.proto` service and get both REST and gRPC for free |
| **Cloud providers** | AWS App Mesh, GCP's Cloud Endpoints, and Azure API Management all support gRPC traffic natively |
| **Mobile clients** | gRPC is common for mobile-to-backend calls where bandwidth and battery efficiency matter (Protocol Buffers compress well on constrained networks) |
| **Streaming ML inference** | TensorFlow Serving and Triton Inference Server expose gRPC endpoints for high-throughput inference with streaming support |

**When to choose gRPC over REST:**

- Internal service-to-service calls where you control both sides
- High-throughput paths (>1,000 RPS) where serialization CPU matters
- Bidirectional or server-push streaming requirements
- Strong typing and contract enforcement across multiple teams or languages

**When REST is still the right call:**

- Public APIs consumed by third parties (JSON is universally understood)
- Browser clients without a gRPC-Web proxy
- Simple CRUD services with infrequent calls and low throughput
- Teams unfamiliar with protobuf tooling and the code-generation workflow

---

## Common Pitfalls

- **Renumbering field tags in production.** Changing a field number (`amount = 2` → `amount = 3`) breaks binary compatibility silently — the old client will misread the field. Add new fields with new tags; never reuse or renumber existing ones.

- **Using `insecure_channel` outside of local development.** The examples above use no TLS. In production, always configure mutual TLS (mTLS) with certificates. gRPC's credential system makes this straightforward, but it is easy to forget when moving from local to staging.

- **Ignoring status codes and error details.** gRPC has a rich set of status codes (`NOT_FOUND`, `DEADLINE_EXCEEDED`, `RESOURCE_EXHAUSTED`, etc.). Many teams return `UNKNOWN` for everything or worse — return `OK` with an error flag in the response body — losing observability and making error handling on the client fragile.

- **No deadline / timeout propagation.** Every gRPC call should carry a deadline: `stub.ProcessPayment(req, timeout=2.0)`. Without it, a slow downstream call holds the upstream thread indefinitely. Deadlines should also be propagated — if the outer call has 500ms left, the inner call should inherit that budget, not start a fresh 2-second window.

- **Blocking the event loop with streaming RPC.** When consuming a server-streaming RPC, teams often iterate the stream synchronously and block the thread for the entire duration. For high-concurrency servers, use async gRPC (`grpc.aio` in Python, `grpc-go` goroutines, or reactive streams in Java) to avoid starving the thread pool.

---

## Exercises

1. **Easy** — Write a `.proto` file defining a `GreeterService` with one unary RPC `SayHello` that accepts a `name` (string) and returns a `greeting` (string). Generate the code stubs using `protoc` and verify the generated files.

2. **Medium** — Extend the `PaymentService` example with a server-streaming RPC `ListTransactions` that accepts a `user_id` and streams back a sequence of `Transaction` messages. Implement the server to yield 5 dummy transactions and write a client that prints each one as it arrives.

3. **Hard** — Set up a gRPC-Gateway proxy in front of the `PaymentService` so that a `POST /v1/payment` REST request is translated to the `ProcessPayment` gRPC call. Verify that both `grpcurl` and `curl` can reach the same backend handler. Then measure the per-call latency difference between the REST-over-JSON path and the native gRPC path using `hey` or `ghz` and explain the results.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **RPC** | A network protocol | A programming model — "call a function on another machine." The protocol (gRPC) is one implementation. |
| **Stub** | A placeholder / mock | The generated client-side code that marshals arguments, sends the request over the wire, and returns the response. It hides all transport details. |
| **Protocol Buffers** | The same thing as gRPC | A language-neutral binary serialization format. gRPC uses it by default, but protobuf can be used without gRPC, and gRPC supports other codecs (e.g., JSON for debugging). |
| **Field tag** | A label or annotation | An integer identifier embedded in the binary payload to identify each field. Must never change after deployment. |
| **Streaming RPC** | WebSockets | HTTP/2 streams managed by the gRPC runtime. Unlike WebSockets, they are typed, multiplexed, and flow-controlled. |
| **Deadline** | A timeout you set once | A point-in-time absolute deadline propagated across the entire call chain. Differs from a local timeout, which resets at each hop. |
| **Channel** | A TCP connection | An abstraction over one or more HTTP/2 connections to a target, with built-in connection pooling and load balancing. |

---

## Further Reading

- [gRPC official documentation — Core concepts](https://grpc.io/docs/what-is-grpc/core-concepts/) — The authoritative reference for service definitions, RPC types, metadata, and error handling.
- [Protocol Buffers Language Guide (proto3)](https://protobuf.dev/programming-guides/proto3/) — Complete reference for `.proto` syntax, field rules, and wire format.
- [gRPC-Gateway](https://grpc-ecosystem.github.io/grpc-gateway/) — How to expose a gRPC service as a RESTful JSON API simultaneously.
- [HTTP/2 RFC 9113](https://httpwg.org/specs/rfc9113.html) — The underlying transport spec; understanding frames, streams, and flow control explains why gRPC performs as it does.
- [ghz — gRPC benchmarking tool](https://ghz.sh/) — The de facto standard for load-testing gRPC services; useful for validating latency and throughput claims against your own services.
