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
