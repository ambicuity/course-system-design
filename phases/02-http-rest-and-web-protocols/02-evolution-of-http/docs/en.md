# Evolution of HTTP

> Every HTTP version exists because the previous one hit a wall at production scale.

**Type:** Learn
**Prerequisites:** How the Internet Works, TCP/IP Fundamentals
**Time:** ~25 minutes

---

## The Problem

You're loading a modern web page. The browser needs the HTML document, a dozen CSS files, thirty JavaScript bundles, two hundred image assets, several JSON API calls, and a persistent WebSocket for live updates — all as fast as possible. Now imagine trying to do that with a protocol designed in 1989 to fetch a single HTML file from a university server.

The core tension in HTTP's history is simple: every resource on a page is a separate request, yet the underlying network has limited connections and each connection has latency overhead. At HTTP/1.0, each request required establishing a brand-new TCP connection — a three-way handshake adding one full round-trip before a single byte of useful data moves. A page with 50 assets = 50 handshakes. On a 100ms RTT link, that's 5 seconds of pure overhead before accounting for transfer time.

Successive versions of HTTP attacked exactly this bottleneck from different angles: reusing connections, compressing headers, multiplexing streams, and ultimately replacing TCP entirely. Understanding *why* each version was designed the way it was — and what trade-offs each introduced — is essential for making good decisions about protocol selection, CDN configuration, reverse proxy tuning, and API design.

---

## The Concept

### HTTP/0.9 — The One-Liner (1991)

The original protocol had no version number, no headers, no status codes. Exactly one method: `GET`. The entire request was one line and the response was raw HTML, followed by a connection close.

```
GET /index.html\r\n
```

The server streamed back HTML and closed the socket. That was it. This was adequate for Tim Berners-Lee's CERN document server. It was catastrophically inadequate for anything else.

---

### HTTP/1.0 — Headers Arrive (1996)

RFC 1945 added:
- **Request and response headers** — content type, encoding, authorization, caching metadata
- **Status codes** — 200, 301, 404, 500, etc.
- Additional methods: `POST`, `HEAD`
- Version negotiation (`HTTP/1.0` on the request line)

But the fatal flaw: **every request opened a new TCP connection**. The sequence was:

```
Client                          Server
  |-- SYN ---------------------->|
  |<-- SYN-ACK ------------------|
  |-- ACK + GET /style.css ----->|
  |<-- 200 OK + body ------------|
  |-- FIN ---------------------->|   connection closed
  |-- SYN ---------------------->|   new connection for next asset
  ...
```

On a page with N assets, you pay N × (1 RTT for TCP handshake + 1 RTT for TLS if HTTPS) before data flows. Browsers worked around this by opening 4–8 parallel connections per host — a blunt instrument that wastes server file descriptors and doesn't compose well.

---

### HTTP/1.1 — Persistent Connections (1997, revised 2014)

RFC 2616 (later RFC 7230–7235) solved the "connection per request" problem:

| Feature | What it does |
|---|---|
| **Keep-Alive** | Reuse the TCP connection across multiple requests |
| **Pipelining** | Send multiple requests without waiting for each response |
| **Chunked transfer encoding** | Stream responses of unknown length |
| **Host header** (mandatory) | Enables virtual hosting — many domains on one IP |
| **Cache-Control** | Fine-grained caching directives |
| **Range requests** | Fetch partial content (resumable downloads, video scrubbing) |

Keep-Alive solved the handshake-per-request problem. But pipelining introduced a new one: **head-of-line (HOL) blocking**. Responses must be returned in the order requests were sent. If request #1 is a 10 MB image, requests #2–#10 wait behind it on the same connection — even if their responses are 1 KB each.

Browsers mitigated HOL blocking by opening 6 parallel connections per origin (the RFC-recommended cap). Developers countered with domain sharding — splitting assets across `cdn1.example.com`, `cdn2.example.com`, etc. to get more parallel connections. This works but adds DNS lookups and prevents connection reuse.

```
HTTP/1.1 timeline (6 parallel connections, 18 assets):

Conn 1: [asset1][asset7][asset13]
Conn 2: [asset2][asset8][asset14]
Conn 3: [asset3][asset9][asset15]
Conn 4: [asset4][asset10][asset16]
Conn 5: [asset5][asset11][asset17]
Conn 6: [asset6][asset12][asset18]
         ^-- HOL blocking within each connection
```

---

### HTTP/2 — Multiplexing (2015)

RFC 7540 (now RFC 9113) tackled HOL blocking at the protocol level without breaking the HTTP semantics layer.

**Key architectural change: binary framing layer.**

HTTP/1.1 is plaintext. HTTP/2 introduces a binary framing layer between the TCP socket and the HTTP message. Every message is broken into **frames**, tagged with a **stream ID**. Frames from different streams are interleaved freely on a single TCP connection.

```
HTTP/2 single connection, multiplexed streams:

TCP connection
├── Stream 1 frames: [HEADERS][DATA][DATA][DATA]
├── Stream 3 frames: [HEADERS][DATA]
├── Stream 5 frames: [HEADERS][DATA][DATA]
└── Stream 7 frames: [HEADERS]
      ↑ All interleaved on one TCP connection, no HOL blocking between streams
```

Core HTTP/2 features:

| Feature | Mechanism | Benefit |
|---|---|---|
| **Multiplexing** | Binary frames with stream IDs | Multiple requests in parallel over 1 connection |
| **Header compression** | HPACK (Huffman + static/dynamic tables) | Repeated headers (cookies, UA) cost almost nothing after first request |
| **Server push** | Server proactively sends resources | Client gets CSS/JS before it knows it needs them |
| **Stream prioritization** | Weight and dependency tree | Critical-path resources delivered first |
| **Single connection** | One TLS session per origin | Eliminates domain sharding hacks |

**HPACK in practice:** On a typical page, `Cookie` and `User-Agent` headers are hundreds of bytes, sent on every request. HPACK builds a shared header table on both sides. After the first request, subsequent requests reference table entries rather than resending the string. Header overhead drops from ~800 bytes to ~50 bytes per request.

**The remaining problem:** HTTP/2 still sits on TCP. TCP is an ordered byte stream — if a single packet is lost, the OS kernel stalls *all* streams on that connection until the missing packet is retransmitted. TCP's HOL blocking is worse for HTTP/2 than HTTP/1.1 because HTTP/1.1 spread risk across 6 connections while HTTP/2 concentrates everything on one. On lossy networks (mobile, satellite, WiFi), HTTP/2 can be slower than HTTP/1.1.

---

### HTTP/3 — QUIC (2022)

RFC 9114 replaces TCP with **QUIC** (Quick UDP Internet Connections), a transport protocol built on UDP and standardized by the IETF.

Why UDP? Because QUIC implements its own reliability, ordering, and congestion control *per stream*. A lost packet for stream 3 only stalls stream 3 — streams 1, 2, and 4 keep flowing. This eliminates TCP HOL blocking entirely.

```
HTTP/3 / QUIC architecture:

  Application layer:   HTTP/3 (frames, streams, headers)
  ─────────────────────────────────────────────────────
  QUIC transport:      stream multiplexing, reliability,
                       congestion control (per-stream)
  ─────────────────────────────────────────────────────
  TLS 1.3:             encryption (baked into QUIC)
  ─────────────────────────────────────────────────────
  UDP:                 raw packet delivery
```

Additional QUIC benefits:

| Feature | HTTP/1.1+TCP | HTTP/2+TCP | HTTP/3+QUIC |
|---|---|---|---|
| HOL blocking | Per-connection | TCP level (worse) | None |
| Connection setup | 1 RTT (TCP) + 1-2 RTT (TLS 1.2) | Same | 1 RTT first visit, **0-RTT resumption** |
| Connection migration | Breaks on IP change | Breaks on IP change | Connection ID survives IP change |
| Packet loss impact | Stalls connection | Stalls ALL streams | Stalls only affected stream |

**0-RTT resumption** is significant for mobile users constantly switching between WiFi and cellular — the QUIC connection survives the IP address change because it is identified by a Connection ID, not the 4-tuple (src IP, src port, dst IP, dst port).

The trade-off: QUIC on UDP is frequently throttled or blocked by enterprise firewalls and some ISPs that only allow TCP. HTTP/3 clients always negotiate a fallback to HTTP/2. Roughly 26% of web traffic is served over HTTP/3 today (mostly Google and Meta properties), but support is now ubiquitous in major browsers and CDNs.

---

## Build It / In Depth

### Inspecting HTTP versions in practice

```bash
# Check what version a server negotiates
curl -sI --http1.1 https://nghttp2.org | head -5
curl -sI --http2   https://nghttp2.org | head -5
curl -sI --http3   https://cloudflare.com | head -5

# Verbose TLS + ALPN negotiation (shows h2 or h3 in protocol list)
curl -v --http2 https://example.com 2>&1 | grep -E 'ALPN|HTTP/'
```

ALPN (Application-Layer Protocol Negotiation) is the TLS extension that lets client and server agree on HTTP/1.1 vs h2 vs h3 during the TLS handshake — zero extra round trips.

### Simulating HOL blocking

The following Python snippet demonstrates the HOL blocking effect visible in HTTP/1.1 vs HTTP/2:

```python
import httpx
import time

urls = [f"https://httpbin.org/delay/{i % 2}" for i in range(10)]

# HTTP/1.1: sequential per connection
start = time.perf_counter()
with httpx.Client(http2=False) as client:
    for url in urls:
        client.get(url)
print(f"HTTP/1.1 sequential: {time.perf_counter() - start:.2f}s")

# HTTP/2: multiplexed
import asyncio

async def fetch_all():
    async with httpx.AsyncClient(http2=True) as client:
        await asyncio.gather(*[client.get(url) for url in urls])

start = time.perf_counter()
asyncio.run(fetch_all())
print(f"HTTP/2 multiplexed:  {time.perf_counter() - start:.2f}s")
```

### Nginx configuration: enabling HTTP/2 and HTTP/3

```nginx
server {
    listen 443 ssl;
    listen 443 quic reuseport;   # HTTP/3 on UDP
    http2 on;

    ssl_certificate     /etc/ssl/cert.pem;
    ssl_certificate_key /etc/ssl/key.pem;
    ssl_protocols       TLSv1.3;  # QUIC requires TLS 1.3

    # Advertise HTTP/3 to browsers
    add_header Alt-Svc 'h3=":443"; ma=86400';
}
```

The `Alt-Svc` header is how a server advertises HTTP/3 support. On the first visit the browser uses HTTP/2; the response header tells it "I also speak h3 on port 443" and subsequent visits use QUIC.

---

## Use It

| Protocol | When to use it | Real-world examples |
|---|---|---|
| HTTP/1.1 | Legacy clients; debugging tools; simple internal services where latency is irrelevant | Most internal microservice mesh traffic; `curl` defaults |
| HTTP/2 | Any HTTPS API or web page; the current production baseline | gRPC (uses HTTP/2 exclusively); all major browsers; Nginx, Apache |
| HTTP/3 | High-latency or lossy networks; CDN edge; mobile-first products | Cloudflare (all edge), Google (search, YouTube), Meta, Fastly |
| WebSockets (over HTTP/1.1) | Full-duplex persistent channels for chat, gaming, live feeds | Slack, Twitch, multiplayer games |
| HTTP/2 Server Push (deprecated) | Was used for critical CSS/JS — now replaced by `<link rel=preload>` and 103 Early Hints | Removed from Chrome 106+ |

**gRPC specifically mandates HTTP/2** because it requires stream multiplexing for bidirectional streaming RPCs. If you're exposing a gRPC service behind a load balancer, the LB must understand HTTP/2 at L7, not just pass through TCP — otherwise it can't distribute individual streams across backends.

**CDN configuration:** Cloudflare, Fastly, and AWS CloudFront all negotiate HTTP/3 at the edge and can downgrade to HTTP/2 or HTTP/1.1 for origin connections. It's common and correct to run HTTP/2 between CDN and origin even when clients use HTTP/3 at the edge.

---

## Common Pitfalls

- **Leaving HTTP/2 off on your origin.** CDNs add HTTP/2 at the edge, so your site *looks* like it serves HTTP/2 to the world — but origin-to-CDN connections still use HTTP/1.1 unless you configure it. This wastes connection capacity on high-traffic origins.

- **Optimizing for HTTP/1.1 when you're actually on HTTP/2.** Bundling all JS into one file, inlining CSS, and domain sharding were HTTP/1.1 workarounds. On HTTP/2, small granular files are better — the multiplexer can interleave them and the browser can cache individual modules. Bundling everything together invalidates the whole cache on any change.

- **Assuming HTTP/3 is available.** About 5–10% of enterprise networks block UDP port 443. Always ensure HTTP/2 fallback is configured and working. Test with `--http2-prior-knowledge` after deliberately blocking UDP to verify the fallback path.

- **Ignoring HOL blocking at the TCP level in HTTP/2.** On high-packet-loss links (>2%), HTTP/2 can perform worse than HTTP/1.1 because it concentrates all traffic on one connection. Monitor real-user connection types; consider H3 or adaptive protocols for mobile-heavy products.

- **Misunderstanding gRPC keepalives vs HTTP/2 PING frames.** gRPC uses HTTP/2 PING frames for keepalives. Misconfiguring `KEEPALIVE_TIME` and `KEEPALIVE_TIMEOUT` on gRPC channels leads to silent connection drops behind NAT/firewalls that time out idle TCP connections in 30–60 seconds.

---

## Exercises

1. **Easy:** Use `curl -v --http2 https://www.google.com` and `curl -v --http1.1 https://www.google.com`. Compare the output — identify the ALPN negotiation, the response headers, and any differences in the number of connections opened. Write down what you observe.

2. **Medium:** Configure a local Nginx instance to serve a static directory over HTTP/2. Use the browser DevTools Network tab to verify multiplexing is active (look for the "Protocol" column showing `h2`). Then artificially disable HTTP/2 (`--http1.1` in curl) and measure the difference in total load time for a directory with 20+ small files.

3. **Hard:** Implement a simple HTTP/2 server in Python using the `h2` library that multiplexes 10 concurrent streams and responds with the stream ID and a 50ms artificial delay per stream. Compare its wall-clock completion time against an equivalent HTTP/1.1 server handling the same 10 requests sequentially. Calculate the theoretical speedup and explain why your measured speedup may differ.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Multiplexing** | Sending many requests at once | Interleaving binary frames from different streams on a single TCP (or QUIC) connection so responses can arrive out-of-order |
| **HOL blocking** | A bug in early HTTP | A structural property of ordered streams: a stalled item at the head of a queue prevents all items behind it from progressing |
| **QUIC** | HTTP/3 | A general-purpose transport protocol built on UDP; HTTP/3 is one application that runs on QUIC |
| **HPACK** | HTTP/2 compression | A header-specific compression scheme using Huffman coding plus a shared dynamic table of previously seen headers on both sides of the connection |
| **ALPN** | Part of HTTP | A TLS extension that negotiates the application protocol (h2, h3, http/1.1) during the TLS handshake with no extra round trips |
| **0-RTT** | Zero latency connection | A QUIC feature where a resuming client can send application data in the first packet using a session ticket from a previous connection; trades some replay-attack risk for latency |
| **Server Push** | HTTP/2 pushing notifications | A now-deprecated HTTP/2 feature where the server proactively sends resources the client hasn't requested yet; superseded by `<link rel=preload>` and HTTP 103 Early Hints |

---

## Further Reading

- [HTTP/2 RFC 9113](https://www.rfc-editor.org/rfc/rfc9113) — The current HTTP/2 specification; Section 5 on streams and Section 6 on frame types are the core.
- [HTTP/3 RFC 9114](https://www.rfc-editor.org/rfc/rfc9114) — The HTTP/3 spec; read alongside the QUIC transport RFC 9000.
- [High Performance Browser Networking — Ilya Grigorik](https://hpbn.co) — Free online book with deep chapters on HTTP/1.1, HTTP/2, and QUIC with real latency measurements.
- [Cloudflare Learning: What is HTTP/3?](https://www.cloudflare.com/learning/performance/what-is-http3/) — Accessible explanation of QUIC's HOL blocking solution with diagrams.
- [QUIC RFC 9000](https://www.rfc-editor.org/rfc/rfc9000) — The IETF QUIC transport specification; Section 2 on streams is directly relevant to understanding HTTP/3's multiplexing model.
