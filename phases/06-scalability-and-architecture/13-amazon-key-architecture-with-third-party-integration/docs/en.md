# Amazon Key Architecture with Third Party Integration

> Reliable physical-world delivery at scale requires a trust boundary, not just an API boundary.

**Type:** Learn
**Prerequisites:** Microservices Architecture Fundamentals, IoT System Design, API Gateway Patterns
**Time:** ~35 minutes

---

## The Problem

Your IoT platform works perfectly in the lab. Every device responds in milliseconds, partner APIs return 200s, and the integration tests all pass. Then you ship it to 10 million homes.

Now a delivery driver in Denver is standing in a driveway at 2 p.m. They press "unlock." Your service sends a command. But the homeowner's WiFi router rebooted an hour ago and the smart lock lost its connection. The partner cloud (Chamberlain, Kwikset, Yale) is responsive but can't reach the device. The driver waits. The package goes back to the station. The customer is furious.

This is the physical-world reliability problem: unlike a web page that can retry silently, a failed unlock has real-world consequences — a missed delivery, a wasted truck route, a damaged customer relationship. And unlike a pure-software system, you do not own the full stack. The hardware is made by Kwikset. The cloud that bridges to it belongs to Yale. The garage opener runs on Chamberlain's myQ platform. You are orchestrating third parties you cannot control.

Amazon Key was a small internal side project that became a global platform powering **over 100 million secure door unlocks per year**. The engineers who built it — including Kaushik Mani and Vijayakrishnan Nagarajan — had to solve exactly this problem: build a secure, resilient, partner-extensible platform where the happy path involves three independent cloud systems all functioning at the same moment, and where failure is both common and unacceptable.

---

## The Concept

### The Three-Tier Trust Boundary

Amazon Key sits at the intersection of three actors with fundamentally different trust models:

```
  ┌─────────────────────────────────────────────────────────────┐
  │                     AMAZON KEY PLATFORM                     │
  │                                                             │
  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
  │  │  Delivery    │  │  Access      │  │  Device Mgmt     │  │
  │  │  Orchestrator│  │  Control Svc │  │  Service         │  │
  │  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
  │         │                 │                    │            │
  │         └─────────────────┴────────────────────┘            │
  │                           │                                 │
  │                   ┌───────▼────────┐                        │
  │                   │  Command Bus   │                        │
  │                   └───────┬────────┘                        │
  └───────────────────────────┼─────────────────────────────────┘
                              │
              ┌───────────────┴────────────────┐
              │       PARTNER INTEGRATION       │
              │                                 │
              │  ┌──────────┐  ┌─────────────┐  │
              │  │ Kwikset  │  │ Chamberlain │  │
              │  │ Adapter  │  │ myQ Adapter │  │
              │  └────┬─────┘  └──────┬──────┘  │
              └───────┼───────────────┼──────────┘
                      │               │
             ┌────────▼──┐   ┌────────▼──────┐
             │ Kwikset   │   │ myQ Cloud     │
             │ Cloud     │   │               │
             └────┬──────┘   └───────┬───────┘
                  │                  │
             ┌────▼──────┐   ┌───────▼───────┐
             │  Lock     │   │  Garage Door  │
             │  Device   │   │  Opener       │
             └───────────┘   └───────────────┘
```

**Layer 1: Amazon's Core Services** handle delivery scheduling, access token generation, and audit logging. They own the business logic.

**Layer 2: The Partner Integration Layer** translates between Amazon's standardized internal command model and each partner's proprietary API surface. This is an Adapter pattern at cloud scale.

**Layer 3: The Physical Device** sits behind the partner's cloud and communicates via MQTT or a proprietary IoT protocol. Amazon never talks to it directly.

### The Access Token Model

The central security primitive is a **time-bounded, single-use access grant**, not a persistent credential:

| Property | Value |
|---|---|
| Scope | Specific delivery ID + specific device ID |
| Window | ~4-hour delivery window |
| Actions permitted | unlock once, then auto-lock |
| Revocable | Yes, by delivery cancellation event |
| Cryptographic | Signed HMAC or JWT with short expiry |

This means if a token leaks, it is useless outside its window and useless for any other device or delivery. The blast radius of a compromise is bounded by design, not by runtime detection.

### Event-Driven State Machine

Each delivery follows a strict state machine. State transitions are emitted as events to an event bus (internally, Amazon uses EventBridge or Kinesis-equivalent infrastructure):

```
SCHEDULED → DRIVER_APPROACHING → UNLOCK_REQUESTED
    → UNLOCK_CONFIRMED → DELIVERY_IN_PROGRESS
    → LOCK_REQUESTED → LOCK_CONFIRMED → DELIVERY_COMPLETE
```

Every state change is durable — written to an event store before the next transition. This matters because:
- The homeowner's app reads from the event store, not from live device state
- Retry logic replays the command on the current state rather than re-issuing blind retries
- Audit logs are immutable and complete

### Cold Start and Connectivity Handling

Devices go offline. WiFi drops. Partner clouds have maintenance windows. Amazon Key's resilience strategy has three layers:

1. **Pre-unlock health check**: Before dispatching the driver to the address, verify device reachability. If unreachable → flag the stop, route driver elsewhere, notify customer.
2. **Command queuing with TTL**: Commands are queued with a time-to-live equal to the delivery window. If the device comes back online within that window, the command executes. After TTL, the command is discarded and delivery is aborted.
3. **Graceful degradation**: If the unlock cannot be confirmed within a timeout (typically 30–60 seconds), the driver is instructed to leave the package at the door. The customer is notified with the reason.

---

## Build It / In Depth

### Step 1: The Partner Adapter Contract

Every hardware partner — Kwikset, Yale, Schlage, Chamberlain myQ — implements a different API. The partner integration layer normalizes them behind a single internal interface:

```python
# Internal interface every adapter must implement
class LockAdapter(ABC):
    def unlock(self, device_id: str, token: str, ttl_seconds: int) -> CommandResult:
        """Send unlock command. Returns immediately; poll for confirmation."""
        ...

    def lock(self, device_id: str, token: str) -> CommandResult:
        ...

    def get_status(self, device_id: str) -> DeviceStatus:
        """Returns ONLINE | OFFLINE | UNKNOWN and last-seen timestamp."""
        ...

    def register_webhook(self, device_id: str, callback_url: str) -> None:
        """Partner calls back when device state changes."""
        ...
```

A concrete adapter wraps the partner's SDK or REST API:

```python
class ChamberlainMyQAdapter(LockAdapter):
    def __init__(self, api_key: str, base_url: str):
        self._client = MyQClient(api_key, base_url)

    def unlock(self, device_id: str, token: str, ttl_seconds: int) -> CommandResult:
        # Chamberlain calls it "open" not "unlock"
        response = self._client.set_door_state(
            device_serial=device_id,
            state="open",
            auth_token=token,
        )
        return CommandResult(
            command_id=response["request_id"],
            status="PENDING",    # myQ is async; result comes via webhook
        )

    def get_status(self, device_id: str) -> DeviceStatus:
        raw = self._client.get_door_state(device_id)
        # Normalize Chamberlain's state model to Amazon Key's internal model
        mapping = {"open": "UNLOCKED", "closed": "LOCKED", "unknown": "UNKNOWN"}
        return DeviceStatus(
            device_id=device_id,
            state=mapping.get(raw["door_state"], "UNKNOWN"),
            last_seen=raw["last_update"],
        )
```

The key design decision: **adapters are stateless**. State lives in Amazon Key's own data stores, not in partner systems. The adapter is purely a translation layer.

### Step 2: The Command Bus and Confirmation Loop

Sending an unlock command is fire-and-check, not fire-and-forget:

```
1. Write command to durable queue (SQS FIFO)
2. Adapter sends to partner API → receives PENDING
3. Start polling loop (or await webhook callback):
   while elapsed < TTL:
       status = adapter.get_status(device_id)
       if status == UNLOCKED:
           emit(UNLOCK_CONFIRMED)
           break
       sleep(exponential_backoff(attempt))
   else:
       emit(UNLOCK_FAILED)
       trigger_fallback_flow()
```

Polling vs. webhooks: partners vary. myQ supports webhooks; some lock vendors only support polling. The adapter hides this distinction from the command bus.

### Step 3: Pre-Delivery Health Check

Before routing a driver, the Delivery Orchestrator checks device reachability:

```python
def route_delivery(delivery: Delivery) -> RoutingDecision:
    status = adapter_registry.get(delivery.device_type).get_status(delivery.device_id)

    if status.state == "UNKNOWN" or is_stale(status.last_seen, threshold_minutes=30):
        # Do not send the driver; escalate
        return RoutingDecision(
            action="SKIP_KEY_DELIVERY",
            reason="DEVICE_UNREACHABLE",
            fallback="STANDARD_DOORSTEP",
        )

    return RoutingDecision(action="PROCEED_WITH_KEY_DELIVERY")
```

This single check eliminates the majority of failed unlocks before a driver ever leaves the station.

### Step 4: Homeowner Notification and Video

Each delivery event triggers a notification pipeline:

```
UNLOCK_CONFIRMED event
    → Notification Service → push notification to homeowner app
    → Video Service → start recording on in-garage camera
    → (driver enters, places package)
LOCK_CONFIRMED event
    → Video Service → stop recording, clip saved to S3
    → Notification Service → "Your delivery is complete. View video."
```

The video recording is a security and trust feature, not an afterthought. It is what makes customers willing to give delivery access to their garage. The recording must be started *after* unlock confirmation and stopped *after* lock confirmation — not before, not after. This requires the event bus to be the single source of truth for timing.

---

## Use It

### Technology Stack Decisions

| Concern | Chosen Approach | Why |
|---|---|---|
| Device command delivery | MQTT via AWS IoT Core | Low overhead, bidirectional, scales to millions of devices |
| Partner integration | REST adapters with webhook callbacks | Partners are REST-native; webhooks reduce polling |
| Internal event bus | Amazon Kinesis / EventBridge | Durable, ordered, replayable |
| Command queue | SQS FIFO | Exactly-once delivery critical for physical actions |
| Device state storage | DynamoDB | Low-latency point lookups by device_id |
| Audit log | Append-only S3 + Athena | Compliance, forensics; query occasionally |
| Video clips | S3 + CloudFront | Large binary objects; homeowner retrieves on demand |

### When to Apply This Pattern

This architecture — internal normalized interface + partner-specific adapters + event-driven state machine — is applicable whenever you are building a platform that:

- Orchestrates physical or irreversible actions (smart locks, payment settlements, shipment pickups)
- Integrates third-party systems you cannot modify or fully trust
- Must maintain audit trails for compliance or dispute resolution
- Needs to degrade gracefully when partners are unavailable

Examples outside Amazon Key: hospital bed management systems, fleet dispatch with third-party telematics vendors, e-commerce checkout integrating multiple payment gateways.

---

## Common Pitfalls

- **Skipping the pre-flight health check.** Sending a driver to an offline device is expensive and damaging. Always verify reachability before committing routing. The cost of one API call is negligible compared to a failed delivery.

- **Treating partner APIs as synchronous.** Most IoT partner APIs are async — they return a request ID, not a result. Building synchronous callers results in timeouts and incorrect "failure" signals when the device actually succeeded later.

- **State stored in the partner system, not yours.** If you rely on partner systems as the source of truth for device state, you inherit their reliability as your own. Store your own state, use the partner as a command channel only.

- **No TTL on queued commands.** A command queued at 2 p.m. for a delivery window that has already passed must not execute at 9 p.m. Every command in the queue must carry a TTL and be discarded after expiry.

- **Expanding the access token scope creep.** Tokens that are too broad (device-level vs. delivery-level, or no expiry) are the root cause of most access control vulnerabilities in IoT delivery platforms. Keep tokens narrow: one token, one device, one delivery, one window.

---

## Exercises

1. **Easy — Token Model:** Sketch the fields of a delivery access token (as a JSON object). What fields would you include to satisfy: single-use, time-bounded, device-scoped, and revocable? What would make each field cryptographically verifiable?

2. **Medium — Adapter Extension:** A new partner (August Smart Lock) has an API that uses GraphQL mutations instead of REST. Their state changes are delivered via SSE (Server-Sent Events) rather than webhooks. Extend the `LockAdapter` interface and write a stub `AugustAdapter` that handles both differences without changing the Command Bus.

3. **Hard — Reliability Analysis:** The system described achieves reliability by composing three potentially-unreliable systems (Amazon Key cloud, partner cloud, physical device). Calculate the worst-case end-to-end unlock success rate if each layer has 99.5% availability. Then redesign the pre-flight check and TTL retry strategy to bring the experienced failure rate under 0.1%. What additional instrumentation would you need to measure this in production?

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Third-party integration** | Calling a partner's REST API | Owning the full reliability contract across a system you cannot control, including adapter normalization, retry, and fallback |
| **IoT command** | A fire-and-forget API call | An async request with a TTL, confirmation loop, and required state transition — not fire-and-forget |
| **Access token** | An API key or session token | A narrow, time-bounded, cryptographically signed grant scoped to one action on one resource |
| **Cold start (IoT)** | The device isn't provisioned yet | The device is provisioned but offline or unreachable — the most common failure mode in field-deployed IoT |
| **Adapter pattern** | A design pattern from a textbook | A production-critical boundary that isolates third-party churn from internal business logic |
| **Event-driven state machine** | A queue of events | A durable, ordered sequence of state transitions that is the single source of truth for a physical-world process |
| **Device shadow / digital twin** | An academic concept | The local cached copy of device state in your cloud, used when direct device queries are unavailable |

---

## Further Reading

- [AWS IoT Core Developer Guide — MQTT and Device Shadow](https://docs.aws.amazon.com/iot/latest/developerguide/what-is-aws-iot.html) — The infrastructure Amazon Key runs on; the Device Shadow pattern is the production answer to the "offline device" problem.
- [Amazon Key for Business — How It Works](https://www.amazon.com/b?node=17608448011) — Customer-facing description that reveals the architecture constraints (delivery window, camera, auto-lock).
- [Building Resilient IoT Systems — AWS Architecture Blog](https://aws.amazon.com/blogs/architecture/) — Covers MQTT-based command patterns, retry strategy, and the offline-device problem at scale.
- [Enterprise Integration Patterns — Hohpe & Woolf](https://www.enterpriseintegrationpatterns.com/) — The canonical reference for adapter, command bus, and event-driven patterns used throughout this lesson.
- [Designing Data-Intensive Applications — Kleppmann, Chapter 11: Stream Processing](https://dataintensive.net/) — Deep treatment of event logs and exactly-once delivery semantics, which underpin the command bus design.
