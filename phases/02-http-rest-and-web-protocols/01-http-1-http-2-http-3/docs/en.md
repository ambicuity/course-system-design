# HTTP/1 -> HTTP/2 -> HTTP/3

> Every HTTP revision exists to solve one problem: stop the protocol from being the bottleneck between your server and the user.

**Type:** Learn
**Prerequisites:** TCP/IP basics, TLS handshake fundamentals
**Time:** ~35 minutes

---

## The Problem

You're loading a modern web page. The browser needs to fetch an HTML document, 40 CSS rules, 12 fonts, 80 JavaScript chunks, and 150 images. Each of those is a separate HTTP request. Under HTTP/1.1, a browser is limited to roughly six parallel TCP connections per domain. The rest of the requests queue. Each connection burns a full TCP three-way handshake plus a TLS handshake — between 1-3 round-trips of pure latency before a single byte of payload moves. On a mobile network with 100 ms RTT, that overhead dominates.

Engineers worked around this with domain sharding (spreading assets across `cdn1.example.com`, `cdn2.example.com`, etc.) and inlining critical CSS. These are hacks that add operational complexity without addressing the root cause.

The root cause is that HTTP was designed in 1996 for fetching academic documents over fast university LANs, then patched rather than redesigned for twenty years. HTTP/2 redesigned the framing layer without changing the semantics. HTTP/3 replaced the transport layer entirely. Understanding the progression — what each version fixed and what it deliberately left broken — directly informs every caching, CDN, load-balancer, and API-design decision you will make.

---

## The Concept

### HTTP/1.0 and HTTP/1.1

HTTP/1.0 (RFC 1945, 1996) opened a new TCP connection for every request-response pair and closed it immediately. The overhead was brutal on high-latency links.

HTTP/1.1 (RFC 2616, 1999; revised RFC 7230, 2014) introduced:

| Feature | What it does |
|---|---|
| **Persistent connections** | Keep-alive by default. One TCP connection reused for multiple requests. |
| **Pipelining** | Client sends N requests without waiting for N responses. |
| **Chunked transfer encoding** | Server streams a response body without knowing the total size up front. |
| **Host header** | Multiple virtual hosts on a single IP. Mandatory in HTTP/1.1. |
| **Conditional requests** | `If-Modified-Since`, `ETag` for cache validation. |

**The pipelining catch.** Responses must be returned in the exact order they were requested. If request #1 is slow (a database query), it blocks requests #2, #3, … even if they are already complete. This is **head-of-line (HOL) blocking at the application layer**.

```
HTTP/1.1 pipelining — HOL blocking

Client          Server
  |── GET /html  ──>|
  |── GET /css   ──>|   (pipelined, no wait)
  |── GET /js    ──>|   (pipelined, no wait)
  |                 | [/html is slow — DB query]
  |                 | [/css and /js ready but BLOCKED]
  |<── /html ───────|   (returns after DB query)
  |<── /css ────────|   (returns immediately after)
  |<── /js  ────────|
```

Browsers never enabled pipelining by default because server and proxy support was inconsistent. Instead they opened 6 parallel TCP connections per origin to get concurrency — multiplying connection overhead sixfold.

**Text-based protocol.** HTTP/1.x headers are human-readable ASCII. That's great for debugging, terrible for throughput. A single `Cookie` header routinely adds 800–1200 bytes to every request, sent uncompressed every single time.

---

### HTTP/2

HTTP/2 (RFC 7540, 2015) kept HTTP semantics — methods, status codes, headers, URIs — identical. What changed was everything below the semantics: the **binary framing layer**.

#### Binary framing

Every HTTP/2 message is sliced into **frames**. Each frame carries a stream identifier. Frames from different streams can be interleaved on the wire and reassembled independently.

```
HTTP/2 multiplexing on a single TCP connection

   TCP stream (single connection)
   ┌────────────────────────────────────────┐
   │ HEADERS frame  (stream 1)              │
   │ DATA frame     (stream 3, chunk 1)     │
   │ HEADERS frame  (stream 5)              │
   │ DATA frame     (stream 1, chunk 1)     │
   │ DATA frame     (stream 3, chunk 2)     │
   │ DATA frame     (stream 5, chunk 1)     │
   │ RST_STREAM     (stream 3, cancel)      │
   └────────────────────────────────────────┘

   Three concurrent HTTP requests — one TCP connection.
   Stream 3 cancelled without affecting streams 1 or 5.
```

**Key HTTP/2 features:**

| Feature | Mechanism | Benefit |
|---|---|---|
| **Multiplexing** | Multiple streams over one TCP connection | Eliminates application-layer HOL blocking |
| **Stream prioritization** | Each stream has a weight (1–256) and can depend on another stream | Server sends critical resources (CSS) before lower-priority ones (analytics JS) |
| **HPACK header compression** | Static table (61 common header/value pairs) + dynamic table + Huffman encoding | Compresses repeated headers by 85–90% |
| **Server push** | Server sends responses the client has not requested yet | Eliminates a round-trip for known dependencies (push CSS before browser parses HTML) |
| **Binary framing** | All frames are binary, not ASCII | More efficient to parse; less ambiguity |

#### HPACK in brief

HPACK maintains a **static table** shared by all connections (e.g., entry 2 = `method: GET`) and a **dynamic table** built per-connection. After the first request, a header like `content-type: application/json` is stored in the dynamic table at index, say, 62. Subsequent requests send just `62` instead of the full string.

#### The TCP problem HTTP/2 did not fix

HTTP/2 eliminated application-layer HOL blocking. It did not eliminate **transport-layer HOL blocking**. TCP delivers bytes in order. If one TCP segment is lost, every frame waiting behind it — regardless of which HTTP stream it belongs to — is held until retransmission arrives.

```
HTTP/2 over TCP — TCP HOL blocking

   TCP segment lost ──────────────────────────────────┐
                                                       ↓
   [ seg 1 ]  [ seg 2 ]  [ LOST ]  [ seg 4 ]  [ seg 5 ]
                         ↑
                         TCP retransmit waits here.
                         Streams 1, 3, 5 all blocked.
```

On a reliable LAN this is invisible. On mobile networks with 1–2% packet loss, it kills latency for all streams simultaneously.

---

### HTTP/3

HTTP/3 (RFC 9114, 2022) replaced TCP with **QUIC** (RFC 9000, 2021). QUIC runs over UDP and reimplements reliable delivery, congestion control, and multiplexing at the application layer, per stream.

#### Why UDP?

UDP is unordered and unreliable by design. QUIC builds reliability on top of UDP with its own ACKs, retransmission, and flow control — **but per stream**. A lost UDP datagram only blocks the QUIC stream that owned it. Other streams continue uninterrupted.

```
HTTP/3 / QUIC — independent stream delivery

   QUIC connection (over UDP)
   ┌──────────────────────────────────────────────────┐
   │ Stream 1: [ chunk 1 ] [ LOST ] [ chunk 3 ]       │
   │ Stream 3: [ chunk 1 ] [ chunk 2 ] [ chunk 3 ]    │  <- unaffected
   │ Stream 5: [ chunk 1 ] [ chunk 2 ]                │  <- unaffected
   └──────────────────────────────────────────────────┘

   Only Stream 1 waits for retransmit.
   Streams 3 and 5 deliver immediately.
```

#### 0-RTT and 1-RTT handshakes

TLS 1.3 is mandatory and baked into QUIC itself — there is no separate TLS layer.

```
HTTP/1.1 (new connection):
  RTT 1: TCP SYN / SYN-ACK / ACK
  RTT 2: TLS ClientHello / ServerHello / ...
  RTT 3: TLS Finished / First request
  → 2-3 RTT before first byte

HTTP/2 (new connection, TLS 1.3):
  RTT 1: TCP SYN / SYN-ACK / ACK
  RTT 2: TLS 1.3 combined (1-RTT TLS)
  RTT 3: First request
  → 2 RTT before first byte

HTTP/3 QUIC (first visit):
  RTT 1: QUIC Initial (crypto + transport params combined)
  RTT 2: First request
  → 1 RTT before first byte

HTTP/3 QUIC (returning visitor, 0-RTT):
  RTT 0: Send data in first packet using cached session ticket
  → 0 RTT before first byte (with replay-attack caveats)
```

#### Connection migration

QUIC uses **connection IDs** instead of the four-tuple (src IP, src port, dst IP, dst port) that TCP uses to identify a connection. When a mobile user switches from Wi-Fi to LTE, their IP address changes. A TCP connection is destroyed — new handshake required. A QUIC connection survives IP change transparently using the same connection ID.

#### Summary comparison

| Property | HTTP/1.1 | HTTP/2 | HTTP/3 |
|---|---|---|---|
| Transport | TCP | TCP | QUIC (UDP) |
| Protocol format | Text | Binary frames | Binary frames |
| Connections per origin | 6 (browser default) | 1 | 1 |
| App-layer HOL blocking | Yes (pipelining) | No | No |
| Transport-layer HOL blocking | N/A (separate conns) | Yes | No |
| Header compression | None | HPACK | QPACK |
| Server push | No | Yes (deprecated in practice) | Yes (rarely used) |
| TLS | Optional | Required (browsers) | Mandatory (built-in) |
| Connection migration | No | No | Yes |
| Handshake RTT (new) | 2-3 | 2 | 1 |
| Handshake RTT (returning) | 1 | 1 | 0 |

---

## Build It / In Depth

### Observing the difference with curl

```bash
# HTTP/1.1 — note the connection reuse header
curl -v --http1.1 https://httpbin.org/get 2>&1 | grep -E "< HTTP|connection"

# HTTP/2 — note the stream ID in verbose output
curl -v --http2 https://httpbin.org/get 2>&1 | grep -E "< HTTP|h2"

# HTTP/3 — requires curl built with QUIC support (e.g., quiche or ngtcp2)
curl -v --http3 https://cloudflare.com 2>&1 | grep -E "< HTTP|QUIC"
```

### Checking negotiated protocol in a browser

All modern browsers negotiate HTTP/2 or HTTP/3 via **ALPN** (Application-Layer Protocol Negotiation), a TLS extension. The browser includes its supported protocols (`h2`, `h3`) in the TLS ClientHello. The server selects one and responds.

For HTTP/3 specifically, a server signals HTTP/3 support via the `Alt-Svc` response header:

```
Alt-Svc: h3=":443"; ma=86400
```

The browser upgrades to HTTP/3 on the next connection attempt.

### Setting up HTTP/2 in Nginx

```nginx
# Nginx >= 1.9.5 — HTTP/2 is enabled per listen directive
server {
    listen 443 ssl;
    http2 on;                           # Nginx >= 1.25.1 syntax
    # listen 443 ssl http2;             # older syntax, still works

    ssl_certificate     /etc/ssl/cert.pem;
    ssl_certificate_key /etc/ssl/key.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    server_name example.com;
    root /var/www/html;
}
```

HTTP/2 requires TLS in all browser implementations. A plaintext `h2c` cleartext mode exists in the spec but no browser supports it.

### Measuring HOL blocking impact

```python
import asyncio, time, aiohttp

# Simulate 20 parallel requests. Under HTTP/1.1 with 6-connection limit,
# 14 requests queue immediately. Under HTTP/2 or HTTP/3 all 20 multiplex.

async def fetch(session, url):
    async with session.get(url) as r:
        return await r.read()

async def bench(connector):
    urls = ["https://httpbin.org/delay/0.1"] * 20
    start = time.monotonic()
    async with aiohttp.ClientSession(connector=connector) as s:
        await asyncio.gather(*[fetch(s, u) for u in urls])
    return time.monotonic() - start

# HTTP/1.1: expect ~0.4–0.6 s (three batches of 6 + one of 2)
t1 = asyncio.run(bench(aiohttp.TCPConnector(limit_per_host=6, ssl=False)))
print(f"HTTP/1.1-like: {t1:.2f}s")
```

The benchmark illustrates why every browser opens six connections: without multiplexing, serial processing dominates.

---

## Use It

### Nginx / Caddy / Apache

- **Nginx**: Enable `http2 on;` and HTTP/3 via the `quic` module (available in Nginx 1.25+).
- **Caddy**: HTTP/2 and HTTP/3 are enabled by default — zero configuration required.
- **Apache**: `mod_http2` for HTTP/2. HTTP/3 support via `mod_quic` (experimental as of 2024).

### CDN and cloud

| Provider | HTTP/2 | HTTP/3 |
|---|---|---|
| Cloudflare | Default ON | Default ON (QUIC) |
| AWS CloudFront | Default ON | Opt-in |
| Fastly | Default ON | Available |
| Google Cloud CDN | Default ON | Default ON |
| Akamai | Default ON | Available |

If you terminate TLS at a CDN, HTTP version between origin and CDN is separate from the version between CDN and user. Many origins still speak HTTP/1.1 to the CDN even when the CDN presents HTTP/3 to browsers. This is a common architecture.

### gRPC

gRPC mandates HTTP/2 for its streaming and multiplexing features. Running gRPC behind an HTTP/1.1 proxy silently breaks streaming calls. Use an HTTP/2-aware proxy (Envoy, Nginx with `grpc_pass`) or ensure end-to-end HTTP/2.

### When HTTP/3 matters most

- **Mobile users on lossy networks**: QUIC's per-stream retransmission cuts latency under 1–2% packet loss dramatically.
- **Long-distance or satellite links**: 0-RTT saves one full round trip on each new session.
- **High-churn connections**: Connection migration prevents reconnection overhead as users move between networks.

HTTP/3 gives minimal benefit on a fast, reliable LAN (corporate intranet, data center). Do not enable it unless you serve real users on real internet connections.

---

## Common Pitfalls

- **Assuming HTTP/2 removes the need for a CDN.** Multiplexing reduces connection count but not round-trip latency. A CDN's edge POP close to the user still eliminates the physics problem. HTTP/2 and a CDN are complementary, not alternatives.

- **Leaving domain sharding in place after enabling HTTP/2.** Domain sharding was a workaround for HTTP/1.1's six-connection limit. Under HTTP/2, each additional origin requires a separate connection with its own TLS handshake. Sharding on HTTP/2 is an anti-pattern that hurts performance.

- **Over-relying on HTTP/2 server push.** Server push sends bytes the client may already have cached. The browser has no way to tell the server "I already have this" before the push starts. Unused pushed bytes waste bandwidth. In practice, preload hints (`<link rel="preload">`) achieve the same goal without wasted transfers. Chrome removed server push support in 2022.

- **Forgetting that gRPC requires HTTP/2 end-to-end.** Load balancers that downgrade HTTP/2 to HTTP/1.1 when forwarding to backends silently break bidirectional and server-streaming gRPC calls.

- **Treating 0-RTT as unconditionally safe.** QUIC 0-RTT data can be replayed by a network attacker. Never process non-idempotent requests (POST, PUT, DELETE that mutate state) using 0-RTT data. Restrict 0-RTT to safe, idempotent reads.

---

## Exercises

1. **Easy** — Open Chrome DevTools (Network tab → right-click column headers → add "Protocol"). Load three different websites and record whether each uses `http/1.1`, `h2`, or `h3`. Identify which assets on an HTTP/2 page are still fetched over HTTP/1.1 (hint: third-party embeds often are).

2. **Medium** — Take an Nginx configuration serving a React SPA over HTTP/1.1 and upgrade it to HTTP/2. Measure the number of TCP connections before and after using `ss -tn | grep :443` while the page loads. Then disable domain sharding if present and re-measure. Explain the change in connection count.

3. **Hard** — Implement a small HTTP/2 server in Go using `net/http` (which enables HTTP/2 by default over TLS). Add a `/slow` endpoint that sleeps 2 seconds. Use `h2load` (nghttp2 suite) to fire 10 concurrent requests where 5 target `/slow` and 5 target `/fast`. Compare throughput and latency with a pure HTTP/1.1 server under the same load. Explain any remaining HOL blocking you observe and how HTTP/3 would change the picture.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Multiplexing** | Sending multiple requests at once | Interleaving frames from different request/response pairs on a single connection so responses can arrive out of order |
| **HOL blocking** | A general networking slowdown | A specific problem where a delayed item at the head of a queue prevents all items behind it from being processed, even when those items are ready |
| **QUIC** | A faster version of TCP | A transport protocol built on UDP that reimplements reliable delivery, flow control, and congestion control per stream, with TLS 1.3 mandatory |
| **HPACK** | Just gzip for headers | A stateful compression scheme using a shared static table, a per-connection dynamic table, and Huffman encoding — stateful means it cannot be used across independent connections |
| **0-RTT** | Sending data with zero latency | Sending encrypted data in the very first packet using a session ticket from a prior connection — valid only for idempotent requests due to replay risk |
| **ALPN** | Automatic protocol selection | A TLS extension where client lists supported application protocols (`h2`, `h3`) in the ClientHello and server picks one, avoiding an extra round-trip for protocol negotiation |
| **Server push** | The server proactively sends useful data | The server sends a response to a request the client has not made yet; useful in theory, abandoned in practice due to cache-unawareness and bandwidth waste |

---

## Further Reading

- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114) — The authoritative specification. Section 2 (connection establishment) and Section 4 (expressing HTTP semantics) are the most instructive for practitioners.
- [RFC 9000 — QUIC Transport Protocol](https://www.rfc-editor.org/rfc/rfc9000) — The QUIC transport spec. Read alongside RFC 9114. Section 12 (packets and frames) explains the multiplexing model.
- [High Performance Browser Networking — HTTP/2 chapter](https://hpbn.co/http2/) by Ilya Grigorik — A deep, readable treatment of binary framing, HPACK, and stream prioritization with real packet traces.
- [Cloudflare blog: HTTP/3 — the past, the present, and the future](https://blog.cloudflare.com/http3-the-past-present-and-future/) — Engineering perspective on real-world QUIC deployment, measured performance gains on mobile, and 0-RTT security considerations.
- [Mozilla MDN — Evolution of HTTP](https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/Evolution_of_HTTP) — Concise reference covering each version's changes, good for quick lookup of specific features.
