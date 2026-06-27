# Design a Notification System

A notification system is the connective tissue of a modern product: order confirmations, security alerts, marketing blasts, social interactions. The hard parts are not "send one message" — they are reliability at scale (millions of messages), integrating heterogeneous third-party channels you don't control, and doing it all without spamming users or losing critical alerts.

---

## Step 1 — Understand the Problem & Establish Scope

### Clarifying questions

- Which **channels**? Mobile push, SMS, email — at minimum. Possibly in-app, web push, chat (Slack/WhatsApp).
- Is it **real-time / soft real-time**? Deliver promptly but a few seconds of delay is acceptable.
- What **platforms** for push? iOS, Android, web.
- What **triggers** a notification? Client app events, server-side events, scheduled jobs.
- Can users **opt out**? Yes — opt-out must be respected per channel.
- **Volume**? E.g., 10M push + 1M SMS + 5M emails per day.
- Do we need **ordering, dedup, and at-least-once delivery** guarantees? Generally yes.

### Functional requirements

1. Support **push notifications, SMS, and email**.
2. Notifications can be triggered by **client apps or server-side services**.
3. Soft real-time delivery (deliver ASAP, small delay acceptable).
4. Respect user **opt-out / preferences** per channel.
5. Support **templates** for consistent, parameterized messages.

### Non-functional requirements

- **Reliability** — do not lose notifications, especially critical ones (at-least-once delivery).
- **Scalability** — handle millions to billions of messages/day; add channels easily.
- **High availability** — the system stays up; provider failures are isolated.
- **Low latency** for time-sensitive alerts.
- **Extensibility** — adding a new channel shouldn't require rearchitecting.

### Back-of-envelope estimation

Assume daily volumes:

| Channel | Volume/day | Avg/sec | Notes |
|---|---|---|---|
| Push | 10,000,000 | ~115 | Spiky around marketing pushes |
| SMS | 1,000,000 | ~12 | Expensive per message |
| Email | 5,000,000 | ~58 | Cheapest, highest fanout |

Peak traffic can be 10–100× average during campaigns, so the system must **absorb bursts** — a strong argument for message queues and async workers.

---

## Step 2 — Propose High-Level Design & Get Buy-In

### Third-party channels & how delivery actually works

Notifications mostly hand off to providers we don't own. Understanding the handoff is core to the design.

- **iOS push — APNs (Apple Push Notification service).** The app registers with APNs and obtains a **device token**. We send a payload + token to APNs; APNs delivers to the device.
- **Android push — FCM (Firebase Cloud Messaging).** Analogous flow with an FCM **registration token**.
- **SMS — providers like Twilio, Nexmo/Vonage.** We call their API with phone number + text.
- **Email — providers like SendGrid, Amazon SES, Mailgun.** We call their API with recipient, subject, body; they handle deliverability, DKIM/SPF, etc.

Key consequence: **device tokens, phone numbers, and email addresses are the "contact info"** we must gather and store, keyed by user.

### Contact info gathering flow

The system can only notify a user it can reach. Contact info is collected as users install apps and sign up:

1. User installs the mobile app / signs up.
2. The app requests a push token from APNs/FCM and sends `(userId, deviceToken, platform)` to our API servers.
3. Our servers store device tokens, phone numbers, and emails in a database keyed by user.
4. A user can have **multiple devices** → one-to-many user-to-token relationship.

### Naive design and why it fails

A first cut: a single notification server that gathers contact info, calls APNs/FCM/SMS/email directly, and returns.

**Problems:**

- **Single point of failure** — one server down means no notifications.
- **Hard to scale** — everything (DB access, template rendering, provider calls) in one process.
- **Performance bottleneck** — provider calls are slow/blocking; one slow provider stalls everything.

### Improved high-level architecture

Break it into stages connected by **message queues** so each stage scales independently and bursts are absorbed.

```
[Services / Clients / Cron]
          │  (trigger event)
          ▼
   [Notification Servers]  ── auth, validate, rate-limit, render template,
          │                    fetch contact info & preferences
          ▼
   [Message Queues]  (one logical queue per channel: push / SMS / email)
          │
          ├──► [Push Workers]  ──► APNs / FCM ──► devices
          ├──► [SMS Workers]   ──► Twilio/Nexmo ──► phones
          └──► [Email Workers] ──► SendGrid/SES ──► inboxes
```

Supporting stores/services:

- **Notification servers** — the entry point. Provide APIs to send notifications; validate input, authenticate callers, apply rate limits, look up user contact info and preferences, render templates, and enqueue work.
- **Cache** — hot user contact info, device tokens, and settings.
- **Databases** — user data, contact info, notification templates, and settings.
- **Message queues** — decouple producers from channel workers; **one queue per channel** so a slow/failing provider in one channel doesn't block others.
- **Workers** — pull from queues and call the corresponding third-party provider.

### API design (sample)

`POST /v1/notifications`

```json
{
  "userIds": ["u_123", "u_456"],
  "channel": "PUSH",            // PUSH | SMS | EMAIL (or "ALL")
  "templateId": "order_shipped",
  "params": { "orderId": "A-998", "eta": "Jun 28" },
  "priority": "HIGH",          // HIGH (transactional) | LOW (marketing)
  "idempotencyKey": "evt_8f2c..."  // for dedup
}
```

The **idempotency key** is crucial for at-least-once pipelines (see dedup below).

---

## Step 3 — Design Deep Dive

### Reliability: not losing notifications

The central guarantee is usually **at-least-once delivery**.

- **Persist before acknowledging.** When a notification request arrives, write it to a durable store / durable queue *before* returning success. If a worker crashes mid-send, the message is still in the queue and is retried.
- **Notification log.** Keep a record of every notification (id, user, channel, status, timestamps) for auditing, debugging, and to power retries and dedup.
- **Trade-off:** at-least-once means occasional **duplicates** — which we mitigate with dedup rather than risk losing critical alerts (exactly-once across third parties is effectively impossible).

### Retry handling

Provider calls fail transiently (timeouts, 5xx, rate limits).

- On failure, the worker **retries with exponential backoff and jitter**.
- After N failed attempts, move the message to a **dead-letter queue (DLQ)** for inspection/alerting rather than retrying forever.
- Distinguish **retryable** errors (timeouts, 429, 503) from **permanent** ones (invalid token, unsubscribed) — don't retry permanent failures.
- On "invalid/expired token" responses from APNs/FCM, **prune the dead token** so future sends skip it.

### Deduplication

Because the pipeline is at-least-once and events can be emitted more than once upstream, the same logical notification may appear multiple times.

- Use an **idempotency key / event ID** per logical notification.
- Before sending, check a **dedup store** (e.g., Redis with TTL): if the key was already processed, drop the duplicate.
- This guards against double-sends from retries, queue redelivery, and duplicate upstream events.

### Rate limiting

Two distinct concerns:

1. **Provider-side limits** — APNs/SMS/email providers throttle us. Workers must respect provider quotas (token bucket per provider) to avoid being blocked.
2. **User-facing limits** — don't spam a user. Cap notifications per user per channel per time window (e.g., max N marketing pushes/day). Critical/transactional messages can bypass marketing caps.

This keeps users happy (fewer opt-outs) and keeps us in good standing with providers.

### Notification templates

Most messages share structure. A **template** is a pre-formatted, parameterized message body.

- Benefits: **consistency**, less duplication, faster authoring, easy localization, and centralized A/B testing.
- A template stores the channel-specific layout (push title/body, email subject/HTML, SMS text) with placeholders filled from request `params`.
- Templates are versioned so changes don't break in-flight sends.

### Notification settings / preferences

Before sending, check the user's preferences:

- Per-channel opt-in/opt-out (`push_enabled`, `sms_enabled`, `email_enabled`).
- Category-level controls (marketing vs transactional vs security).
- Quiet hours / time-zone-aware delivery windows.

A row might look like: `(userId, channel, optIn, category, quietHours)`. The notification server filters recipients against these settings **before** enqueuing, so we never send to users who opted out.

### Security

- **Authenticate API callers** — only verified internal services / signed clients (e.g., `appKey`/`appSecret` or mTLS) can trigger notifications, to prevent abuse and spam.
- Validate and authorize that a caller may notify the requested users.
- Protect device tokens and PII (phone/email) at rest and in transit.

### Events tracking & analytics

Notification effectiveness is a product metric. Instrument the funnel:

- **Sent → Delivered → Opened → Clicked → Converted**, plus **Bounced / Failed / Unsubscribed**.
- Providers send delivery/bounce/open webhooks (especially email); ingest these into an analytics pipeline.
- Use this data to tune send times, prune bad addresses, measure campaign ROI, and detect deliverability problems early.

### Monitoring

- Queue depth (a growing backlog signals workers can't keep up).
- Per-provider error rates and latency.
- DLQ size and age.
- Delivery success rate per channel.

---

## Step 4 — Wrap Up

### Final architecture recap

1. Triggers (services, clients, cron) call **notification servers**.
2. Servers authenticate, validate, apply **rate limits** and **dedup**, check **user preferences**, render **templates**, fetch **contact info** (cache + DB), and enqueue per-channel messages.
3. **Per-channel message queues** absorb bursts and decouple stages.
4. **Channel workers** pull messages and call **APNs / FCM / SMS / email** providers, with **retries**, backoff, and a **DLQ**.
5. A **notification log** and **analytics pipeline** track every message end to end.

### Why this design holds up

- **Reliability:** durable queues + at-least-once + retries + DLQ ⇒ no lost critical notifications.
- **Scalability:** independent horizontal scaling of servers and per-channel workers; queues absorb spikes.
- **Availability:** per-channel isolation means one failing provider doesn't take down the others.
- **User experience:** preferences, rate limiting, and dedup prevent spam and respect opt-outs.
- **Extensibility:** adding a channel = new queue + new worker + new template type; the core flow is unchanged.

### Additional talking points

- **Priority queues** — separate high-priority (transactional/security) from low-priority (marketing) so a marketing blast never delays a 2FA code.
- **Scheduled / batched sends** — for campaigns and time-zone-aware delivery.
- **Fan-out for large campaigns** — pre-expand recipient lists in batches to avoid one giant request.
- **Idempotency end to end** — keys threaded from trigger through workers to providers.
- **Token lifecycle** — continuously prune invalid device tokens reported by APNs/FCM to keep delivery rates high.

---

## Step 5 — Back-of-the-Envelope Math

### Volumes and rates (chapter baseline, then 10×)

```
Baseline (chapter):
  Push:  10M / day  →  ~10^7 / 86,400 ≈ 116 / s    (avg)
  SMS:    1M / day  →  ~1.0×10^6 / 86,400 ≈  12 / s
  Email:  5M / day  →  ~5.0×10^6 / 86,400 ≈  58 / s

Peak (10× average during campaigns):
  Push:  ~1,160 / s
  SMS:    ~120 / s
  Email:  ~580 / s
```

10× growth brings push to 1.2K/s, which is still tiny compared to industry leaders but exercises the burst behavior.

### Industry scale (Slack, Discord, WhatsApp) — for orientation only

```
Slack (SREcon 2023 disclosure):
  ~1.5B push notifications / week   ≈ 2.4×10^3 / s avg,  peak ~10× higher
  Peak: ~25K notifications / s

Discord (Discord Engineering blog, 2022–2023):
  ~3B platform push notifications / month  ≈ 1.2×10^3 / s avg
  Plus hundreds of millions of in-app messages

WhatsApp (Meta quarterly disclosures):
  ~100B messages / day  ≈ 1.2×10^6 / s  (chat, not push — but shows scale)
```

### Provider quota math

```
APNs (Apple-published HTTP/2 guidelines):
  Per-topic throughput: no fixed limit; Apple recommends a queue and uses
  HTTP status codes to indicate backpressure.
  Cold-token rate: throttle to ~10–50 new tokens/s per connection to avoid 429.

FCM (Firebase docs):
  HTTP v1: default per-project quota is 250K–500K messages / min depending on tier.
  Per-device: no hard cap, but recommend chunking fanout at 500 devices / batch.
  ≈ 5K / s sustained,  ~20K / s burst per project.

Twilio SMS (public docs):
  Standard tier: 1 msg/s per number (US long-code).
  Short-code: 100–400 msg/s.
  Toll-free: ~3 msg/s.
  Throughput ceiling = Σ per-number caps. To send 1M SMS in 1h: need ~300 short-codes
  or one short-code + 1h time window.

SendGrid / SES:
  SendGrid: 10K emails/s on Pro tier; throttled by reputation over time.
  SES: 50 msgs/s default (production access can lift to thousands/s).
```

### Storage and dedup sizing

```
Per-notification record:
  Fields: id (16 B), user (16 B), channel (4 B), template (16 B),
          priority (4 B), status (4 B), timestamps (16 B), payload (~200 B)
  ≈ 300 B raw, compressed ~150 B

10M push/day × 300 B = 3 GB / day  ≈ 1.1 TB / year
1M SMS/day  × 300 B = 300 MB / day ≈ 110 GB / year
5M email/day × 300 B = 1.5 GB / day ≈ 550 GB / year

Total logs over 1 year: ~1.8 TB / year.  Cheap; keep hot for 30 days, archive 7 years.

Dedup store:
  Idempotency keys live in Redis with 24h TTL.
  16M unique events / day × 50 B key + value = 800 MB resident.
  → Single Redis node adequate up to ~50M / day before sharding.
```

### Cost shape (rough)

```
SMS at $0.01 / msg:  1M / day = $10K / day   = $3.6M / year
Email at $0.0001:    5M / day = $500 / day    = $180K / year
Push at $0 (provider) but compute: 10M × ~50 ms = 500K CPU·s/day ≈ 5–10 EC2 m5.large equiv

Push is by far the cheapest *provider-side*; SMS is the cost driver.
This is why campaigns default to push and SMS is gated behind transactional triggers.
```

---

## Step 6 — ASCII Architecture Diagrams

### 6.1 — End-to-end notification flow (logical)

```
   ┌────────────────────────┐
   │   Trigger Sources      │
   │  (Services / Client /  │
   │    Scheduled Jobs)     │
   └────────────┬───────────┘
                │  notification.requested
                ▼
   ┌──────────────────────────────────────────────────────────┐
   │                  Notification API / Servers              │
   │  ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐  │
   │  │ Auth / AuthZ│  │ Rate-limit  │  │ Idempotency dedup│  │
   │  └──────┬──────┘  └──────┬──────┘  └────────┬─────────┘  │
   │         └────────────────┴──────────────────┘            │
   │  ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐  │
   │  │ Preferences │  │ Template    │  │ Recipient lookup │  │
   │  │ (opt-out,   │  │ render      │  │ (cache + DB)     │  │
   │  │  quiet hrs) │  │             │  │                  │  │
   │  └──────┬──────┘  └──────┬──────┘  └────────┬─────────┘  │
   └─────────┼────────────────┼──────────────────┼────────────┘
             │                │                  │
             ▼                ▼                  ▼
   ┌──────────────────────────────────────────────────────────┐
   │   Per-Channel Priority Queues                            │
   │   ┌──────────────────┐  ┌─────────────────────────────┐  │
   │   │ push.tx.q  (high)│  │ push.mkt.q  (low)           │  │
   │   │ sms.tx.q   (high)│  │ sms.mkt.q   (low)           │  │
   │   │ email.tx.q (high)│  │ email.mkt.q (low)           │  │
   │   └──────────────────┘  └─────────────────────────────┘  │
   └─────┬──────────┬──────────┬──────────┬──────────┬─────────┘
         │          │          │          │          │
         ▼          ▼          ▼          ▼          ▼
   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
   │ Push     │ │ Push     │ │ SMS      │ │ Email    │ │ Email    │
   │ workers  │ │ workers  │ │ workers  │ │ workers  │ │ workers  │
   │ (tx)     │ │ (mkt)    │ │          │ │ (tx)     │ │ (mkt)    │
   └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
        │            │            │            │            │
        ▼            ▼            ▼            ▼            ▼
   ┌──────────────────────────────────────────────────────────┐
   │                Third-Party Providers                     │
   │      APNs / FCM      Twilio / Vonage     SES / SendGrid  │
   └──────────────────────┬───────────────────────────────────┘
                          │
                          ▼
   ┌──────────────────────────────────────────────────────────┐
   │              Devices / Phones / Inboxes                  │
   └──────────────────────────────────────────────────────────┘
                          │  webhooks (delivered, opened, bounced)
                          ▼
   ┌──────────────────────────────────────────────────────────┐
   │   Analytics Ingest   ──►   Analytics / BI / Monitoring  │
   └──────────────────────────────────────────────────────────┘
```

### 6.2 — Sequence: transactional push with retry

```
  Trigger    Notif.API    Dedup     Prefs    Template     Queue      PushWorker     APNs      Device
    │            │          │         │         │            │           │            │          │
    │ POST       │          │         │         │            │           │            │          │
    │───────────►│          │         │         │            │           │            │          │
    │            │ SETNX    │         │         │            │           │            │          │
    │            │─────────►│         │         │            │           │            │          │
    │            │ OK       │         │         │            │           │            │          │
    │            │◄─────────│         │         │            │           │            │          │
    │            │ GET prefs│         │         │            │           │            │          │
    │            │──────────────────►│         │            │           │            │          │
    │            │ optIn=true,        │         │            │           │            │          │
    │            │ quiet=false       │         │            │           │            │          │
    │            │◄──────────────────│         │            │           │            │          │
    │            │ render(template, params)   │            │           │            │          │
    │            │────────────────────────────►│            │           │            │          │
    │            │ payload                    │            │           │            │          │
    │            │◄─────────────────────────── │            │           │            │          │
    │            │ enqueue(payload)            │            │           │            │          │
    │            │───────────────────────────────────────► │           │            │          │
    │  202       │                              │           │           │            │          │
    │◄───────────│                              │           │           │            │          │
    │            │                              │   dequeue │            │            │          │
    │            │                              │──────────►│            │            │          │
    │            │                              │           │ POST push  │            │          │
    │            │                              │           │───────────►│            │          │
    │            │                              │           │  500      │            │          │
    │            │                              │           │◄───────────│            │          │
    │            │                              │           │ backoff+retry          │          │
    │            │                              │           │───────────►│            │          │
    │            │                              │           │  200      │            │          │
    │            │                              │           │◄───────────│            │          │
    │            │                              │           │          deliver       │          │
    │            │                              │           │            │──────────►│          │
    │            │                              │           │            │            │ visible  │
    │            │                              │           │            │            │ on phone │
```

### 6.3 — Fanout for large marketing campaign

```
       Campaign Trigger
              │
              ▼
    ┌──────────────────┐
    │  Audience        │   select 10M users from user table
    │  selection job   │   partition into 1K chunks of 10K users
    └────────┬─────────┘
             │  chunk_id, user_ids[]
             ▼
    ┌──────────────────┐
    │  Fanout workers  │   many workers, each handles some chunks
    └────┬───┬───┬─────┘
         │   │   │
         ▼   ▼   ▼
   ┌──────────────────────┐
   │ Per-user: enqueue to │   one message per (user, channel, template)
   │ channel queues       │   → tens of millions of queue messages
   └──────────────────────┘

   Use:
     • SQS / Kafka with multiple partitions
     • Rate limit per user (token bucket) so 1 user doesn't get 100 alerts
     • Throttle per provider to stay under SES / Twilio quotas
     • Priority: marketing = LOW, transactional = HIGH
```

---

## Step 7 — Trade-off Tables

### 7.1 — Message queue choices

| Queue | Throughput | Durability | Ordering | Ops complexity | Best fit |
|---|---|---|---|---|---|
| **Kafka** | Very high | Replicated, durable | Per-partition order | High (ZooKeeper/KRaft) | High-volume event streams |
| **SQS** | High | At-least-once, durable | None | Very low | AWS-native, simplest ops |
| **RabbitMQ** | Medium-high | Durable with publisher confirms | Per-queue FIFO | Medium | Mixed protocols, low-latency |
| **NATS / JetStream** | Very high | Optional durable streams | Per-stream | Low–medium | Lightweight, multi-region |
| **Redis Streams** | High | Optional | Per-stream | Low | Low-latency, small scale |
| **In-process channel** | Highest | None | n/a | Trivial | Worker-internal handoff only |

### 7.2 — Channel selection for a given notification type

| Channel | Latency | Cost / msg | Reach | Reliability | Use case |
|---|---|---|---|---|---|
| **WebSocket / in-app** | < 100 ms | Compute only | App open | High when connected | Live updates |
| **Mobile push (APNs/FCM)** | Seconds | ≈ $0 | High (smartphone owners) | High (best-effort delivery) | Default for most |
| **Email** | Minutes | ~$0.0001 | Universal | High w/ proper DKIM/SPF | Receipts, digests |
| **SMS** | Seconds | ~$0.01 | Near-universal on mobile | Highest per recipient | 2FA, OTP, urgent alerts |
| **Voice call** | Seconds | ~$0.05 | High | Highest | Critical, urgent, fall-back |
| **Web push (browser)** | Seconds | ≈ $0 | Desktop / laptop browsers | Medium | Re-engagement for web users |
| **Slack / Teams / WhatsApp** | Seconds | ≈ $0 (API rate limits) | Opt-in business users | High | B2B notifications |

### 7.3 — Push vs pull for fanout

| Approach | Latency | Cost | Read-side scaling | Best fit |
|---|---|---|---|---|
| **Fanout-on-write (push to inbox)** | Low (pre-computed) | High write | Easy | Active users, social feed, alerts |
| **Fanout-on-read (pull at read time)** | Higher (compute on read) | Low write | Hard (must scale reads) | Inactive users, infrequent engagement |
| **Hybrid (push for normal, pull for celebs)** | Medium | Balanced | Medium | Most real systems |

### 7.4 — Idempotency key strategies

| Strategy | Granularity | Storage | Trade-off |
|---|---|---|---|
| **Per-event UUID** | One key per logical event | Redis SETNX w/ TTL | Simple; requires caller discipline |
| **Per-(user, template, day) hash** | One key per user per template per day | Same | Reduces storage; can't distinguish events |
| **Two-tier (event UUID + content hash)** | Highest precision | Higher storage | Eliminates duplicates from both upstream + retries |
| **Provider-side dedup (SendGrid dedup-id)** | Per-message ID | At provider | Belt-and-suspenders; provider must support |

---

## Step 8 — Real-World Case Studies

### 8.1 — Slack notifications (multi-channel)

Public talks from Slack engineering (SREcon, Conf) and Slack's status-page history reveal:

- **Per-workspace routing.** Each workspace has its own notification pipeline and message store. Cross-workspace scale achieved by sharding workspaces onto notification clusters.
- **Channel-specific throttling.** Slack enforces a per-channel rate limit (typ. ~50 messages / 10 s per channel) to avoid spam in active channels; this is enforced in the server tier before dispatch to FCM/APNs.
- **Push fallbacks.** Email digest is the always-available fallback when push fails or the user is offline; "Mark all as read" works even when push delivery is delayed because the source of truth is the Slack server, not the device.
- **Service-side rendering of push body.** Slack generates push previews server-side because the device may not have fetched the message yet (offline / slow network).

### 8.2 — Discord's push pipeline

Discord publishes extensively on their notification architecture:

- **Per-user notification settings** stored as a bitfield (which channel categories produce notifications, per-channel overrides, mute durations). Bitfield fits in a few bytes so the user cache is hot.
- **Ratelimit push notifications per user** with a token bucket per (user, type) so a single high-activity channel can't drive all push slots.
- **Use of platform push (APNs/FCM) for "you have a new message" only.** The actual content is fetched when the user opens the app. This minimizes push payload and bandwidth.
- **Backpressure to clients** — when a guild is "spammy" the client receives a batched summary instead of individual pushes.

### 8.3 — Instagram's fan-out and notifications

From Instagram Engineering blog:

- **Async fanout-on-write** for "follower got a new post" notifications. The post service writes a tombstone record to a per-user "notifications inbox" keyed in a key-value store.
- **Aggregation rules:** if a celebrity you follow posts N times in M minutes, you get *one* digest push, not N. Implemented as a stream-aggregation step between the post service and the notifier.
- **TTL on inbox items** so old unread notifications fall off without explicit GC.

### 8.4 — Apple's APNs

APNs is one of the largest push systems in the world. Public docs and WWDC talks reveal:

- **HTTP/2 connection multiplexing** with persistent connections to APNs; providers maintain one or more long-lived HTTP/2 streams per environment (sandbox vs production).
- **Status codes as backpressure.** `410 Gone` (uninstall), `400 BadDeviceToken`, `429 TooManyRequests` (with `Retry-After`). Providers must read and prune accordingly.
- **Collapse key (legacy) / apns-collapse-id.** Multiple messages with the same collapse ID are delivered as one. Useful for "score updated" notifications where only the latest matters.
- **VoIP push** uses a separate topic and a different payload format; misuse of VoIP for non-call notifications is grounds for App Store rejection.

### 8.5 — Google's FCM

- **Topic messaging** (subscribe by topic; FCM fans out) vs **token messaging** (one device). Topic messaging is convenient but only suitable for public broadcast (sports scores) — never for per-user content because topic subscriptions are visible to other apps.
- **Data messages vs notification messages.** Data messages are handled by the app; notification messages are auto-rendered by the OS. Most teams send both: notification for instant visible alert, data payload for the app to fetch context.
- **Web push (W3C Push API)** uses FCM as the relay when running in Chrome on Android; this is the only stable Web push path on mobile.

### 8.6 — Pinterest's notification infrastructure

From Pinterest Engineering blog (2017–2021):

- **Three-stage pipeline:** trigger → enrichment (merge user prefs, recommendation model output) → dispatch (multi-channel send). Enrichment is the largest stage and is fully async with retry.
- **ML-driven send-time optimization** — instead of pushing a notification immediately, score (user, notification, send_time) and defer if predicted engagement is low at this hour.
- **Channel selection as an ML prediction.** Push vs email vs SMS is itself an output of a model — the system chooses the channel most likely to drive the user back.

---

## Step 9 — Common Pitfalls and Failure Modes

### 9.1 — Lost notifications on worker crash (no durable ack)

Symptom: a transactional "order shipped" email never arrives after a deploy.

Cause: the worker calls the provider, gets a slow response, the provider eventually delivers — but the queue already retried because we didn't ack. OR: worker crashes after the provider accepted the message but before we logged "sent". The retry causes a duplicate, OR the worker was holding the message in memory and it dies.

Fix: ack the queue message **only after** the provider returns success AND we persist a "sent" record. Use a transactional outbox: write the "to-send" record to a DB row in the same transaction as the queue insert, then update status to "sent" after the provider acks. This survives crashes between provider call and ack.

### 9.2 — APNs "BadDeviceToken" sprawl

Symptom: 30% of push sends fail with 400 BadDeviceToken; aggregate stats look bad.

Cause: tokens aren't being pruned when APNs returns 410 Gone or 400 BadDeviceToken. New app installs get new tokens but old tokens linger in the DB forever.

Fix: aggressively prune on every 400 / 410 response. Run a daily background sweep that posts a single test push per token to detect zombies; expect to prune 5–15% of tokens per quarter.

### 9.3 — Provider outage cascades

Symptom: when Twilio has an outage, the whole notification service becomes unhealthy because health checks hit Twilio, and timeouts block the workers.

Fix: **circuit breaker** per provider; **bulkhead** (separate thread pool per provider); queue isolation so an SMS outage doesn't back up the push queue; explicit provider failover where the contract allows (e.g., two SMS providers, route by region).

### 9.4 — User spam and "notification fatigue"

Symptom: open rates drop from 40% to 5% over six months; users opt out en masse.

Cause: no per-user rate limit; marketing team over-sends because the cost is low and the click attribution is generous.

Fix: per-user token bucket per category (marketing / social / transactional). Transactional always passes through. Add a dashboard showing opt-out rate per campaign so PMs see the cost.

### 9.5 — Quiet hours / timezone bugs

Symptom: a user in Tokyo gets a "good morning" push at 3 PM their time.

Cause: server sends in UTC and the device shows it in local time, OR the quiet-hours preference is in the user's timezone but the server uses the org's timezone.

Fix: store preferences with explicit timezone; evaluate quiet hours server-side in the user's timezone using a library like `zoneinfo` / Luxon; never trust device-local interpretation of a server timestamp.

### 9.6 — Template regression breaks production sends

Symptom: a Jinja typo in `{{ order.eta }}` (undefined variable) causes every transactional email to throw and dead-letter.

Fix: template compilation step on save (catch errors before deploy); template version pinning (callers specify `templateId + version`); staged rollout of new template versions to a sample of users first.

### 9.7 — PII in logs and analytics

Symptom: phone numbers and email addresses show up in error logs and analytics pipelines; a leak becomes a GDPR / CCPA incident.

Cause: developers log the full notification payload during debugging; analytics ingests the raw event without scrubbing.

Fix: structured logging with explicit allowlist fields; PII is hashed before analytics; rate-limit raw payload access; audit log shows who accessed PII fields.

### 9.8 — Idempotency key collision

Symptom: two unrelated events share the same idempotency key; second event is dropped as a duplicate.

Cause: idempotency key is generated from `(templateId, userId)` only; collision is easy when both events use the same template for the same user.

Fix: include a high-entropy caller-supplied ID, or generate a UUIDv4 per logical event. Reject empty / too-short keys.

---

## Step 10 — Interview Q&A

### Q1. "Walk me through what happens when a user gets 100 notifications in one minute because of a misconfigured cron job."

**Answer sketch:**
Two protections: **per-user rate limit** at the notification API (token bucket — default e.g. 10 notifications / minute / user / category), and **per-provider rate limit** at the worker (token bucket against APNs/FCM/SES). The cron job emits, the API applies the per-user cap and drops or aggregates the rest. Even if the API is bypassed (e.g., direct DB write), the provider cap at the worker layer prevents IP-level throttling. Aggregation rule: "if > 3 notifications to same user in 5 minutes, send one digest with a count." This is the same pattern Slack and Discord use to prevent the "channel went crazy" notification storm.

### Q2. "How do you guarantee that a 2FA code delivered via push reaches the user even if APNs is degraded?"

**Answer sketch:**
Multi-channel redundancy. The same event flows into a priority queue with **two or more providers**: push first; if APNs doesn't ack within 2 s (or returns a throttling response), the system falls over to SMS. If both fail, the code is held in the queue with retries; the API returns "still working" and the client polls. The fallback is **bounded** — we don't burn SMS budget for marketing — but for 2FA / OTP, push → SMS → voice is a tiered escalation. This is what banks do.

### Q3. "Capacity estimation — we have 50M users, each gets on average 5 push notifications per day. How big is the queue infrastructure?"

**Answer sketch:**
50M × 5 = 250M notifications / day = 250 × 10^6 / 86,400 ≈ 2,900 / s average. Peak: 5× ≈ 15K / s. Each notification enqueues one Kafka message (typ. 1 KB) — that's 15 MB/s at peak. A 3-broker Kafka cluster with replication factor 3 and modest brokers handles this easily (target broker throughput ~50 MB/s each). On the worker side: each push call to APNs/FCM takes ~30 ms; 15K / s ÷ (1000 ms / 30 ms) = 450 concurrent workers needed. So ~500 workers with headroom. Total infra: 3 Kafka brokers + 500 worker pods = small.

### Q4. "Why use message queues instead of calling APNs/FCM directly?"

**Answer sketch:**
Three reasons:
1. **Burst absorption.** A campaign trigger can emit 10M notifications in 30 seconds; calling APNs directly means 333K QPS for 30 seconds — most providers throttle this. A queue spreads the spike over minutes.
2. **Retry semantics.** If a worker crashes mid-send, the queue holds the message; a direct call loses it.
3. **Backpressure decoupling.** If a provider degrades, the queue grows but the API tier stays healthy; operators see the backlog as a metric.

The cost is operational complexity (Kafka cluster, partition strategy, ordering guarantees). For a small system (sub-1M notifications / day) the queue may be overkill — a Postgres-backed job queue (Sidekiq, Celery) is simpler and adequate.

### Q5. "How do you handle template localization across i18n?"

**Answer sketch:**
Templates are keyed by `(templateId, locale, channel)`. The notification server looks up the user's locale preference, picks the right template, and renders. Locale lookup happens in the cache layer, not per-render. For SMS (160 chars / segment), localization is critical because machine translation can break a brand name; some teams ban auto-translation and require human-approved templates per locale.

### Q6. "What's the difference between fan-out-on-write and fan-out-on-read here?"

**Answer sketch:**
**Fan-out-on-write:** when event X is published, fan it out to all recipient inboxes immediately. Latency on read is zero, but a viral event (10M recipients) writes 10M inbox rows. **Fan-out-on-read:** don't fan out at write; when user U opens the app, compute their inbox by querying the events from everyone they follow. Write is cheap; read is expensive. Most notification systems use **fan-out-on-write** because notifications are time-sensitive — a notification that arrives an hour late is a bug. The chapter's hybrid pattern (push for normal, pull for celebs) is the right answer for social feeds but **not** for transactional alerts — those should always push.

### Q7. "How do you A/B test notification content?"

**Answer sketch:**
Templates are versioned. Each version is a bucket; users are hashed into a bucket by `(userId, experimentId)`. The notification server picks the version per user at render time and tags the resulting notification with `(experimentId, bucket)`. Analytics join delivery / open / click back to bucket and compute the lift. Stop conditions: pre-registered sample size and minimum detectable effect; if a version wins, promote it as default. Same pattern as web A/B testing; the only nuance is that notifications have to **fall back gracefully** if the experiment platform is down — never let A/B plumbing block a transactional send.

---

## Step 11 — Glossary

| Term | Definition | Common misconception |
|---|---|---|
| **APNs** | Apple Push Notification service — Apple's gateway for delivering pushes to iOS/macOS devices. | "Apple delivers to the app." APNs delivers to the OS; the OS routes to the app via the device token + topic. |
| **FCM** | Firebase Cloud Messaging — Google's push gateway for Android, Chrome, and iOS apps. | "Replaces APNs." No — you still need APNs for iOS; FCM is a thin wrapper that integrates with APNs. |
| **Device Token** | Opaque identifier assigned by APNs/FCM to a (device, app) pair. | "Permanent." Tokens rotate on OS upgrade, app reinstall, or device restore. |
| **Idempotency Key** | A unique identifier attached to a logical notification to prevent duplicate sends. | "Optional." Without it, every retry produces a user-visible duplicate. |
| **At-Least-Once Delivery** | Delivery guarantee that a message is delivered one or more times; never zero times. | "Equals exactly-once." No — duplicates are possible; consumers must dedupe. |
| **Dead-Letter Queue (DLQ)** | A holding queue for messages that failed after N retries, for human inspection. | "Automatically fixed." DLQ is a triage mechanism; nothing auto-resolves from it. |
| **Token Bucket** | A rate-limiting algorithm that refills tokens at a fixed rate up to a cap; each request consumes one. | "Smooth." It's not smooth — it allows bursts up to the cap, then enforces steady-state. |
| **Soft Real-Time** | Delivery target measured in seconds, not milliseconds; a small delay is acceptable. | "Best-effort." Soft real-time is still a *requirement*; the system must be tuned to meet it, even if not as strict as hard real-time. |
| **Provider** | A third-party service (APNs, FCM, Twilio, SES) that ultimately delivers the message. | "We own delivery." We almost never own last-mile delivery; we own the contract and retry semantics. |
| **Circuit Breaker** | A pattern that trips open after a threshold of failures and short-circuits subsequent calls until a cooldown. | "Replaces retries." It's complementary: retry transient errors inside the closed breaker, fail fast when the breaker is open. |
| **Collapse Key** | An identifier that allows APNs to deliver only the most recent of a group of messages (e.g., live score updates). | "Standard across providers." APNs-specific concept; FCM equivalent is `collapse_key`. |
| **Webhook** | An HTTP callback the provider invokes to notify us of delivery events (delivered, bounced, opened). | "Reliable." Webhooks are at-most-once from the provider side; we must sign and dedupe. |