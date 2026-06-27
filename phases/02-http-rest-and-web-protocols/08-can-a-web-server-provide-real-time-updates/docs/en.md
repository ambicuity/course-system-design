# Can a web server provide real-time updates?

> HTTP is pull-based by default — but four techniques let you bend it into push.

**Type:** Learn
**Prerequisites:** How HTTP works, REST API fundamentals, Client-server model
**Time:** ~25 minutes

---

## The Problem

The standard HTTP model is strictly request-response: a browser sends a request, the server replies, and the connection closes (or is reused via keep-alive for the next request the browser chooses to make). The server can never initiate a message to the browser on its own.

This works perfectly for loading a page or fetching a list of orders. It breaks down the moment your product needs to feel alive. Imagine you're building a stock trading dashboard: prices change dozens of times per second. If a trader has to hit Refresh to see the latest bid price, you don't have a trading platform — you have a static spreadsheet. The same problem surfaces in chat applications, live sports scores, collaborative document editing, operational dashboards, and delivery tracking.

The root constraint is this: **TCP connections are initiated by clients, and HTTP rides on top of TCP without adding any server-push primitive.** Everything in this lesson is a strategy to work around or evolve beyond that constraint, each with different latency, resource, and complexity trade-offs.

---

## The Concept

There are four mainstream approaches, split by who does the work and whether the channel is bidirectional.

```
┌─────────────────────────────────────────────────────────┐
│               Four Real-Time Techniques                  │
│                                                         │
│  Client carries the burden          Server cooperates   │
│  ─────────────────────────          ─────────────────   │
│  Short Polling    Long Polling      SSE    WebSocket    │
│  (request loop)   (held request)   (HTTP  (TCP frame    │
│                                    push)   protocol)    │
│                                                         │
│  Directionality:                                        │
│  Short / Long Polling → Client can always send          │
│  SSE                  → Server → Client only            │
│  WebSocket            → Fully bidirectional             │
└─────────────────────────────────────────────────────────┘
```

### Short Polling

The client sends a regular HTTP request on a timer (every 1 s, 5 s, etc.) and the server responds immediately — even if nothing has changed.

```
Client          Server
  │──── GET /updates ────►│
  │◄─── 200 (no change) ──│
  │   (wait 5 s)          │
  │──── GET /updates ────►│
  │◄─── 200 (new data) ───│
```

- **Latency**: Up to one full polling interval behind real-time.
- **Server load**: Constant, regardless of whether data changed.
- **Simplest to implement**: Plain HTTP, works with any infrastructure.

Use short polling only when stale data for N seconds is acceptable and you want zero infrastructure complexity (e.g., a dashboard that refreshes every 30 s).

### Long Polling

The client sends a request; the server holds the connection open until it has something new to say, then responds. The client immediately re-issues the request after receiving the response.

```
Client          Server
  │──── GET /updates ────►│
  │    (server holds)      │
  │    (server holds)      │
  │    (new data arrives)  │
  │◄─── 200 (new data) ───│
  │──── GET /updates ────►│  ← immediately re-requests
  │    (server holds)      │
```

- **Latency**: Near-zero (response sent the moment data is ready).
- **Server load**: Each waiting client occupies a connection and a thread/goroutine/async handler.
- **Works over plain HTTP**: No protocol upgrade needed.

Long polling was the gold standard before SSE and WebSocket matured. It still works well when you need real-time delivery without infrastructure changes and request frequency is low.

### Server-Sent Events (SSE)

The client opens a single HTTP connection using `Accept: text/event-stream`. The server keeps the response stream open and pushes newline-delimited event frames whenever data is available.

```
Client                     Server
  │──── GET /stream ───────►│
  │◄─── 200 (stream open) ──│
  │◄─── data: {"price":42} ─│
  │◄─── data: {"price":43} ─│
  │◄─── data: {"price":41} ─│
  │      (connection live)   │
```

The wire format is simple plain text:

```
data: {"price": 42, "symbol": "AAPL"}\n\n
data: {"price": 43, "symbol": "AAPL"}\n\n
```

Optional fields: `id:` (last-event-id for reconnect), `event:` (named event type), `retry:` (reconnect delay ms).

- **Directionality**: Server → Client only. The client cannot send data over the event stream itself (it uses separate HTTP requests for that).
- **Built-in reconnect**: Browsers automatically reconnect on disconnect, resuming from the last `id` they saw.
- **HTTP/1.1 limit**: Browsers allow only 6 connections per origin; each SSE stream consumes one. HTTP/2 eliminates this (streams are multiplexed).

SSE is the right default for dashboards, notification feeds, live logs, and any use case where the client mostly listens.

### WebSocket

WebSocket starts with an HTTP GET that includes an `Upgrade: websocket` header. The server responds with `101 Switching Protocols`, and from that point on the TCP connection speaks the WebSocket framing protocol — not HTTP.

```
Client                          Server
  │──── GET /ws (Upgrade) ─────►│
  │◄─── 101 Switching Protocols ─│
  │                              │
  │◄═══ frame (server push) ════│  ← any time
  │═══► frame (client msg)  ════►│  ← any time
  │◄═══ frame (server push) ════│
```

Messages are binary frames or UTF-8 text frames. The protocol is symmetric: either side can send at any time, and either side can initiate a close handshake.

- **Full-duplex**: The only option where both sides send without a new HTTP request.
- **Lower overhead per message**: After the handshake, frames have a 2–14 byte overhead vs. full HTTP headers on every polling request.
- **Not pure HTTP**: Load balancers, proxies, and CDNs must be WebSocket-aware.

WebSocket is the right choice for collaborative editing, multiplayer games, trading terminals, and any scenario where the client also streams data to the server at high frequency.

---

## Build It / In Depth

### Short Polling (JavaScript)

```javascript
// client: poll every 3 seconds
async function pollUpdates() {
  const res = await fetch('/api/updates?since=' + lastSeenId);
  const data = await res.json();
  if (data.items.length) {
    renderUpdates(data.items);
    lastSeenId = data.items.at(-1).id;
  }
}
setInterval(pollUpdates, 3000);
```

### Long Polling (Python / FastAPI)

```python
import asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()
pending: list[asyncio.Event] = []
messages: list[dict] = []

@app.get("/poll")
async def poll():
    event = asyncio.Event()
    pending.append(event)
    try:
        await asyncio.wait_for(event.wait(), timeout=30)
    except asyncio.TimeoutError:
        return JSONResponse({"messages": []})  # empty heartbeat
    finally:
        pending.remove(event)
    return JSONResponse({"messages": messages[-10:]})

@app.post("/publish")
async def publish(msg: dict):
    messages.append(msg)
    for e in pending:
        e.set()   # wake all waiting clients
    return {"ok": True}
```

Key detail: always set a server-side timeout (here 30 s) and return an empty heartbeat. Without it, idle connections accumulate and load balancers may kill them with a TCP RST.

### SSE (Node.js / Express)

```javascript
app.get('/stream', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');

  // Send a heartbeat every 15 s to prevent proxy timeouts
  const heartbeat = setInterval(() => res.write(': ping\n\n'), 15000);

  const unsubscribe = eventBus.on('update', (data) => {
    res.write(`id: ${data.id}\n`);
    res.write(`data: ${JSON.stringify(data)}\n\n`);
  });

  req.on('close', () => {
    clearInterval(heartbeat);
    unsubscribe();
  });
});
```

Client-side (browser):

```javascript
const es = new EventSource('/stream');
es.onmessage = (e) => renderUpdate(JSON.parse(e.data));
es.onerror   = () => console.warn('SSE reconnecting…');
// Browser reconnects automatically
```

### WebSocket (Python / websockets library)

```python
import asyncio, websockets, json

connected: set = set()

async def handler(ws):
    connected.add(ws)
    try:
        async for msg in ws:
            data = json.loads(msg)
            # broadcast to all other clients
            websockets.broadcast(connected - {ws}, json.dumps(data))
    finally:
        connected.remove(ws)

async def main():
    async with websockets.serve(handler, "0.0.0.0", 8765):
        await asyncio.Future()  # run forever

asyncio.run(main())
```

---

## Use It

| Technique | Typical latency | Infra complexity | Best for |
|---|---|---|---|
| Short polling | ≥ interval (1–60 s) | None | Status badges, dashboard that refreshes every 30 s |
| Long polling | ~0 ms after event | Moderate (async server) | Notifications, low-frequency updates, legacy infra |
| SSE | ~0 ms after event | Low (HTTP only) | Live feeds, log tails, AI streaming responses |
| WebSocket | ~0 ms, full-duplex | High (WS-aware proxy) | Chat, collaborative editing, gaming, trading |

**Real-world usage:**

- **GitHub**: Commit status checks use long polling via its REST API fallback.
- **Twitter/X**: Home timeline Live updates use SSE.
- **Slack**: Uses WebSocket for message delivery; falls back to long polling on restrictive networks.
- **Figma**: WebSocket for real-time multiplayer cursor and edits.
- **ChatGPT (OpenAI API streaming)**: SSE — the `text/event-stream` response streams tokens as they are generated.
- **Binance / crypto exchanges**: WebSocket streams for order book ticks.

**Cloud / framework support:**

- **AWS API Gateway**: Supports WebSocket APIs natively.
- **Cloudflare Workers**: Supports both SSE (streaming responses) and WebSocket (via Durable Objects).
- **Next.js / Vercel**: SSE via Route Handlers; WebSocket requires an external server (e.g., Ably, Pusher, or a dedicated Node process).
- **Socket.io**: Abstraction that starts with WebSocket and falls back to long polling automatically — useful when you cannot guarantee WebSocket support.

---

## Common Pitfalls

- **Polling at too high a frequency.** Polling every 200 ms is not "near real-time" — it is 300 unnecessary requests per minute per client, burning server CPU and mobile battery. Use SSE or WebSocket when sub-second latency matters.

- **Not sending heartbeats.** Most load balancers and proxies have idle-connection timeouts (AWS ALB default: 60 s). Long-polling and SSE connections that stay quiet will be silently killed. Send a comment line (`: ping`) or empty event every 15–30 s.

- **Forgetting WebSocket reconnect logic.** WebSocket connections drop. Mobile clients lose signal. If your client has no reconnect loop with exponential backoff, users silently go stale. Never assume a WebSocket connection lasts forever.

- **Hitting browser SSE connection limits on HTTP/1.1.** Each open `EventSource` consumes one of the browser's 6 connections per origin. Open three SSE streams per page and you've used half the budget. Either serve over HTTP/2 (multiplexed) or consolidate streams by using named event types.

- **Deploying WebSockets behind a non-aware load balancer.** Classic Layer-4 load balancers pass TCP through fine. Layer-7 (HTTP) load balancers must be explicitly configured to not buffer the body and to forward the `Upgrade` header. Missing this causes the handshake to fail with a `426 Upgrade Required` or a hung connection.

---

## Exercises

1. **(Easy)** Implement short polling in a browser that fetches `/api/notifications` every 5 seconds and displays a badge count. Add a `since` query parameter so the server can return only new items.

2. **(Medium)** Rewrite the short-polling example above to use SSE. Compare the number of HTTP requests generated over 10 minutes with 100 simultaneous users. Which uses fewer connections total?

3. **(Hard)** Design a collaborative cursor-tracking feature (like Figma's live cursors) for a whiteboard app. Should you use SSE or WebSocket, and why? Sketch the protocol: what messages does the client send, what does the server broadcast, and how do you handle a client that disconnects mid-session? Consider what happens when a user joins a session already in progress — how do you send them the current cursor positions of everyone else?

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Real-time | Data arrives in microseconds | Data arrives fast enough for the use case; "real-time" for a chat app might mean < 200 ms |
| WebSocket | A new internet protocol | An upgrade to an existing HTTP/TCP connection that switches to a binary framing protocol after a standard HTTP handshake |
| SSE | A WebSocket alternative that is worse | A unidirectional push mechanism over plain HTTP with built-in browser reconnect; simpler to deploy and sufficient for the majority of push use cases |
| Long polling | Just a slower short poll | The server deliberately holds the response until new data arrives, achieving near-zero latency without a persistent stream |
| Full-duplex | Both sides can send at the same time | With WebSocket, client and server frames are independent; neither side has to wait for the other to finish sending |
| `101 Switching Protocols` | A rare error code | The success response to a WebSocket upgrade request; the connection transitions from HTTP to WebSocket framing after this response |
| Backpressure | Not relevant to web push | When the server generates events faster than the client can consume them; SSE and WebSocket both need flow control strategies for high-throughput streams |

---

## Further Reading

- [MDN — Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events) — authoritative reference for the SSE API and wire format.
- [RFC 6455 — The WebSocket Protocol](https://datatracker.ietf.org/doc/html/rfc6455) — the actual spec; sections 1 and 4 are worth reading to understand the handshake and framing.
- [HTML Living Standard — EventSource](https://html.spec.whatwg.org/multipage/server-sent-events.html) — specifies browser reconnect behavior and the `Last-Event-ID` header.
- [Ably Blog — WebSockets vs Long Polling](https://ably.com/topic/websockets-vs-long-polling) — practical comparison with latency measurements and infrastructure cost analysis.
- [Cloudflare Durable Objects — WebSocket Hibernation](https://developers.cloudflare.com/durable-objects/examples/websocket-hibernation-server/) — shows how to scale WebSockets to millions of connections on serverless infrastructure.
