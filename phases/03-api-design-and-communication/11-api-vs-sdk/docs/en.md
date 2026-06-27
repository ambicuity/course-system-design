# API Vs SDK!

> An API is the contract; an SDK is the toolkit that makes honoring that contract easy.

**Type:** Learn
**Prerequisites:** REST APIs, HTTP fundamentals, Client-Server Architecture
**Time:** ~25 minutes

---

## The Problem

You are building a payments feature. You open the Stripe documentation and immediately hit a fork in the road: do you call the REST endpoints directly, or do you install the `stripe` Python package? Both let you charge a card. Neither choice is obviously wrong — until you start building and realize the consequences.

If you call the raw API, you must manually manage bearer tokens, build the correct `Content-Type: application/x-www-form-urlencoded` body, parse the JSON response, handle rate-limit `429` responses with exponential backoff, and verify webhook signatures yourself. That is a week of undifferentiated work that has nothing to do with your product.

If you reach for an SDK without understanding what it is doing, you end up shipping a 2 MB binary to a microservice that only ever calls one endpoint — and when the SDK version breaks on a new runtime, you have no idea what HTTP call to debug because the abstraction swallowed the details. You also risk being silently locked into one vendor's opinion of error handling, retry policy, and authentication flow.

Understanding the boundary between API and SDK lets you make that choice deliberately, not accidentally.

---

## The Concept

### Definitions

| Concept | What it is | What it is not |
|---------|-----------|----------------|
| **API** | A contract — a set of endpoints, data formats, and protocols that a service exposes | An implementation; the API does not care what language you use |
| **SDK** | A language- or platform-specific package of pre-built code (clients, models, helpers, docs) that speaks to one or more APIs on your behalf | The service itself; an SDK is always a consumer of an API |

The relationship is unidirectional:

```
  Your Code
      │
      ▼
  ┌─────────┐
  │   SDK   │  ← Optional layer (language-specific, vendor-supplied)
  └────┬────┘
       │  HTTP / gRPC / WebSocket
       ▼
  ┌─────────┐
  │   API   │  ← The contract (language-agnostic)
  └────┬────┘
       │
       ▼
  Backend Service (databases, logic, state)
```

An SDK always sits on top of an API. An API can exist without any SDK. The inverse is impossible.

---

### The API Side

An API defines three things:

1. **Surface** — which operations are available (`POST /charges`, `GET /customers/{id}`)
2. **Protocol** — how to communicate (HTTP/1.1, gRPC, WebSocket, GraphQL)
3. **Schema** — what data goes in and comes out (JSON shape, headers, status codes)

That is everything the API guarantees. It says nothing about retries, connection pooling, object mapping, or convenience wrappers. Those are your problem as the caller.

APIs are **language-agnostic**. A REST API does not know or care whether you call it from Python, Go, or a shell script with `curl`.

---

### The SDK Side

An SDK bundles several things around an API:

| Component | Purpose |
|-----------|---------|
| **HTTP Client** | Manages connections, timeouts, keep-alive |
| **Auth Helper** | Attaches API keys, signs requests, refreshes tokens |
| **Request Builder** | Converts method calls into correct HTTP bodies and headers |
| **Response Deserializer** | Maps raw JSON into typed objects |
| **Retry/Backoff Logic** | Re-sends on transient failures (429, 503) |
| **Pagination Helpers** | Iterates over multi-page result sets automatically |
| **Error Hierarchy** | Typed exceptions (`PaymentDeclinedError`, `RateLimitError`) |
| **Documentation** | In-editor type hints and docstrings |

An SDK is **platform-specific**. Stripe ships separate SDKs for Python, Ruby, Java, Node.js, Go, and iOS. Each targets the idioms of its ecosystem.

---

### The Core Trade-off

```
          Control ◄─────────────────────────► Convenience
              │                                      │
       Raw HTTP calls                        Full SDK usage
              │                                      │
       ✓ No extra deps                    ✓ Auth handled for you
       ✓ Full visibility                  ✓ Retries handled for you
       ✓ No version drift                 ✓ Typed response objects
       ✗ You write plumbing               ✓ Pagination handled for you
       ✗ You handle retries               ✗ Heavier dependency
       ✗ You parse every response         ✗ SDK may lag behind API
                                          ✗ Abstraction hides errors
```

Neither side of this axis is universally correct. The choice depends on what you are building.

---

## Build It / In Depth

Walk through the same task — creating a Stripe customer — using a raw API call and then using the Stripe Python SDK. This makes the relationship concrete.

### Option A: Raw API Call

```python
import requests
import os

API_KEY = os.environ["STRIPE_SECRET_KEY"]

response = requests.post(
    "https://api.stripe.com/v1/customers",
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/x-www-form-urlencoded",
    },
    data={
        "email": "alice@example.com",
        "name": "Alice",
    },
)

if response.status_code == 200:
    customer = response.json()
    print(customer["id"])  # cus_abc123
else:
    error = response.json()
    raise RuntimeError(error["error"]["message"])
```

Every decision is explicit: the URL, the header format, the status code check, the error path. Nothing is hidden, but you wrote all of it.

---

### Option B: Stripe Python SDK

```bash
pip install stripe
```

```python
import stripe
import os

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

customer = stripe.Customer.create(
    email="alice@example.com",
    name="Alice",
)

print(customer.id)  # cus_abc123
```

The SDK call is four lines against the raw call's twenty. Under the hood it does the same POST, but it also:

- Constructs the correct URL and headers
- Handles `429 Too Many Requests` with automatic exponential backoff
- Deserializes the response into a `stripe.Customer` object with typed attributes
- Raises `stripe.error.StripeError` (and subclasses) instead of making you parse the error JSON

---

### What the SDK is actually doing

Peek inside a simplified version of what `stripe.Customer.create` executes:

```
stripe.Customer.create(email=..., name=...)
        │
        ▼
APIRequestor.request("post", "/v1/customers", params)
        │
        ▼
Construct HTTP request:
  POST https://api.stripe.com/v1/customers
  Authorization: Bearer sk_live_...
  Content-Type: application/x-www-form-urlencoded
  Stripe-Version: 2023-10-16
        │
        ▼
Send with retry logic (up to 2 retries on 429/503)
        │
        ▼
Deserialize JSON → stripe.Customer(id="cus_abc123", email="alice@example.com", ...)
        │
        ▼
Return typed object to caller
```

The API contract did not change — the SDK just gave you a more ergonomic entry point into it.

---

### When to use each

```
Use raw API when:                       Use SDK when:
─────────────────────────────────────   ──────────────────────────────────────
• You call 1-2 endpoints total          • You use many features of the service
• Language has no official SDK          • Auth/retry logic would be painful
• You need absolute control             • You want typed objects + autocomplete
  over request shaping                  • SDK is actively maintained
• SDK is significantly out of date      • Onboarding speed matters
• Microservice with strict dep budget   • You are prototyping or shipping fast
```

---

## Use It

### AWS: API vs SDK at scale

AWS exposes every service through a REST/query API (`https://s3.amazonaws.com/`). AWS also ships **AWS SDKs** for 9+ languages (boto3 for Python, the JS SDK, the Java SDK, etc.).

Calling S3 via raw HTTP requires computing an AWS Signature Version 4 signature — a multi-step HMAC-SHA256 process involving canonical request formatting, string-to-sign construction, and derived signing keys. Almost no one does this manually. The SDK handles it invisibly.

```python
# Raw AWS S3 API: you must compute SigV4 yourself — dozens of lines
# AWS SDK (boto3): two lines
import boto3
s3 = boto3.client("s3")
s3.put_object(Bucket="my-bucket", Key="file.txt", Body=b"hello")
```

### Firebase

Firebase exposes a REST API and a Realtime Database REST endpoint. The Firebase SDK for JavaScript additionally provides real-time listeners, offline persistence, and automatic reconnection — none of which exist in the raw REST API. Here the SDK provides capabilities, not just convenience.

### OpenAI

OpenAI's Chat Completions API is a plain REST endpoint (`POST /v1/chat/completions`). The `openai` Python package is an SDK that wraps it, provides streaming helpers, and manages model-specific defaults. Because the API is simple and well-documented, many teams successfully use `requests` directly and skip the SDK.

### Comparison of major services

| Service | REST API | Official SDK adds |
|---------|----------|-------------------|
| Stripe | Yes | Retry, typed errors, pagination |
| AWS | Yes | SigV4 signing, service-specific helpers |
| Twilio | Yes | Webhook validation, TwiML builders |
| Firebase | Yes | Real-time sync, offline persistence |
| OpenAI | Yes | Streaming helpers, token counting |
| Slack | Yes | OAuth helpers, event dispatching |

---

## Common Pitfalls

- **Using an SDK to call a single endpoint.** If you only ever call `GET /status`, installing a 10 MB SDK introduces a dependency update burden and cold-start cost for essentially no benefit. Prefer a lightweight HTTP call.

- **Assuming the SDK is always up to date.** SDK versions often lag the API. A service can ship a new API field or endpoint months before the SDK exposes it. Always check the API changelog, not just the SDK changelog.

- **Hiding errors inside the abstraction.** SDKs can mask the underlying HTTP status code. When debugging, log the raw request and response — most SDKs have a debug/verbose mode or a `http_client` hook to capture this.

- **Treating the SDK as the source of truth for the contract.** The API documentation is canonical. The SDK is one implementation of a client against that API. If the SDK and the docs disagree, trust the docs, not the SDK source code.

- **Forgetting SDK version pinning.** Major SDK versions often introduce breaking changes (different exception class hierarchies, renamed methods). Pin your SDK version in `requirements.txt`, `package.json`, or `go.mod` and upgrade deliberately, not automatically.

---

## Exercises

1. **Easy — map the layers.** Pick any public REST API you have used (GitHub, OpenWeatherMap, etc.). Find its official SDK (if one exists). List three things the SDK does for you that you would need to write yourself if you used the raw API.

2. **Medium — swap layers.** Take an existing project that uses an SDK (e.g., `boto3` for S3, `stripe` for payments). Rewrite one operation (upload a file, create a customer) using only `requests` or `fetch` and the service's raw REST API. Document every header and auth step you had to add.

3. **Hard — design your own SDK layer.** Given a hypothetical `POST /v1/payments` and `GET /v1/payments/{id}` REST API that uses HMAC-SHA256 request signing, design a minimal Python SDK: a `PaymentsClient` class with `create()` and `get()` methods, automatic signing, retry logic on `429`, and typed response objects. Write the class skeleton with method signatures, docstrings, and a brief explanation of each component.

---

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|------------------------|
| **API** | A URL you send requests to | A contract defining how software components communicate — could be REST, gRPC, WebSocket, or a library interface |
| **SDK** | Just a library you install | A curated package of tools, clients, models, and helpers built for a specific language/platform to consume one or more APIs |
| **Client Library** | Synonym for SDK | Usually refers to the narrower HTTP-client portion of an SDK, without the extra tooling (code generation, CLI, emulators) |
| **Endpoint** | The whole API | A single callable address in an API (e.g., `POST /v1/charges`); an API is a collection of endpoints |
| **Wrapper** | Fully abstracted layer | A thin client that adds minimal logic on top of raw HTTP calls — lighter than a full SDK |
| **Abstraction Leak** | A sign the SDK is broken | When lower-level API details (HTTP status codes, raw JSON fields) bleed through the SDK's surface — usually a sign the error handling is incomplete |
| **Versioning** | Only matters for APIs | Critical for both: API versions affect contract; SDK versions affect behavior. They version independently and must be managed together |

---

## Further Reading

- [Stripe API Reference vs. Stripe Libraries](https://stripe.com/docs/api) — official docs that clearly distinguish the REST API from the SDK layer; a model for how good API + SDK documentation should be structured.
- [AWS SDK for Python (boto3) documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html) — one of the most complete SDK implementations; compare its S3 client to the [S3 REST API docs](https://docs.aws.amazon.com/AmazonS3/latest/API/Welcome.html) to see the abstraction gap in practice.
- [Google API Design Guide](https://cloud.google.com/apis/design) — explains how Google designs APIs to be consumed both raw and through generated client libraries; relevant background on what makes an API SDK-friendly.
- [OpenAI API Reference](https://platform.openai.com/docs/api-reference) — a clean example of a simple API where many teams intentionally skip the SDK; illustrates when the raw HTTP path is viable.
- [The Architecture of an API Client](https://www.robinwieruch.de/what-is-an-api-javascript/) — approachable breakdown of how HTTP clients, auth layers, and typed models stack up inside a real-world SDK.
