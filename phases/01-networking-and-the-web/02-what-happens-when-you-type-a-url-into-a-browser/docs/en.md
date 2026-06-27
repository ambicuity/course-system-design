# What happens when you type a URL into a browser?

> Every millisecond a request spends in transit is a millisecond users are waiting — know the pipeline to own the latency.

**Type:** Learn  
**Prerequisites:** How the Internet Works, OSI Model  
**Time:** ~25 minutes

## The Problem

You ship a new feature and reports come in: "The site is slow." Your servers show sub-5ms response times. Your database query logs look clean. But users in Frankfurt are waiting 800ms before they see anything on screen. You don't know where to start because you don't know what's happening between the browser and your server.

This isn't hypothetical — it's the most common blind spot for engineers new to system design. The client-server model is often described as "browser sends request, server responds," but that description hides six distinct phases, each of which can independently add hundreds of milliseconds of latency or fail completely. Cache-busting DNS misconfigurations, missing preconnect hints, outdated TLS versions, absent HTTP/2 support — all of these are invisible if you treat the browser as a black box.

Understanding this pipeline is the foundation for most of the trade-offs you'll encounter in system design: why CDNs exist, why TCP connection pooling matters, why HTTP/3 is being adopted, and why some pages feel instant while technically similar ones feel sluggish.

## The Concept

When you type `https://example.com` and press Enter, six distinct phases happen in sequence before any pixels appear:

```
[1] URL Parse & Cache Check
[2] DNS Resolution
[3] TCP Three-Way Handshake
[4] TLS Handshake
[5] HTTP Request / Response
[6] Browser Rendering
```

### Phase 1 — URL Parsing and DNS Cache Lookup

The browser first parses the URL into its components:

| Component | Value in `https://example.com/courses?id=1` |
|-----------|------------------------------------------------|
| Scheme    | `https`                                        |
| Host      | `example.com`                               |
| Path      | `/courses`                                     |
| Query     | `id=1`                                         |
| Port      | `443` (implied by https)                       |

Before doing any networking, the browser checks a series of **DNS caches** for a cached `hostname → IP` mapping. The lookup order is:

1. **Browser DNS cache** (Chrome: `chrome://net-internals/#dns`) — TTL typically seconds to a few minutes
2. **OS DNS cache** — the `hosts` file (`/etc/hosts` on Linux/macOS) and the system resolver cache
3. **Local router cache**
4. **ISP or enterprise DNS cache**

A cache hit at any level skips Phase 2 entirely — the single biggest optimization available at this layer.

### Phase 2 — Recursive DNS Resolution

On a cache miss, the OS hands the query to a **recursive resolver** (often your ISP's or a public resolver like `8.8.8.8`). The resolver walks the DNS hierarchy:

```
Browser → Recursive Resolver → Root Name Server
                                      │
                              TLD Name Server (.com)
                                      │
                          Authoritative Name Server
                                      │
                            A record: 104.21.x.x (TTL 300)
```

The authoritative name server is the source of truth for the domain. It returns an **A record** (IPv4) or **AAAA record** (IPv6) along with a TTL that controls how long each layer caches the result.

Key insight: a full recursive lookup costs three separate network round trips in the worst case. At 20–40ms per hop for a nearby resolver, that's 60–120ms before any HTTP conversation starts — just to find out which IP to talk to.

### Phase 3 — TCP Three-Way Handshake

TCP is connection-oriented. Before any application data flows, client and server must synchronize sequence numbers to enable reliable, ordered delivery:

```
Client                              Server
  │──── SYN (seq=x) ───────────────▶ │
  │ ◀── SYN-ACK (seq=y, ack=x+1) ─── │
  │──── ACK (ack=y+1) ──────────────▶ │
  │          (connection established) │
```

This exchange costs **one full round-trip time (RTT)**. On a cross-continent connection (e.g., client in Frankfurt, server in us-east-1), that RTT is ~100ms. On a same-datacenter connection, it is under 1ms.

HTTP/3 eliminates this cost by using QUIC over UDP, which merges connection establishment with the first data exchange.

### Phase 4 — TLS Handshake (HTTPS only)

TLS establishes an encrypted channel with authentication. TLS 1.3 (the current standard) achieves this in **one RTT**:

```
Client                                         Server
  │──── ClientHello (TLS 1.3, key share) ────▶ │
  │ ◀── ServerHello, Certificate,               │
  │     CertificateVerify, Finished ─────────── │
  │──── Finished ─────────────────────────────▶ │
  │              (encrypted tunnel open)        │
```

What this accomplishes:
- **Authentication**: the server's X.509 certificate proves its identity, signed by a trusted CA
- **Key exchange**: both sides derive a shared session key via ECDHE (forward secrecy)
- **Confidentiality + integrity**: all HTTP traffic that follows is encrypted with AES-GCM or ChaCha20-Poly1305

TLS 1.2 required **two RTTs**, which is one reason upgrading to 1.3 or enabling HTTP/3's 0-RTT session resumption produces measurable performance gains.

### Phase 5 — HTTP Request and Response

With an encrypted connection open, the browser sends an HTTP request:

```
GET /courses?id=1 HTTP/2
Host: example.com
Accept: text/html,application/xhtml+xml
Accept-Encoding: gzip, br
Cache-Control: max-age=0
Cookie: session=abc123
```

The server processes the request — checking caches, querying databases, rendering templates — and responds:

```
HTTP/2 200
Content-Type: text/html; charset=utf-8
Content-Encoding: br
Cache-Control: public, max-age=3600
```

Followed by the response body (Brotli-compressed HTML).

**Status codes that matter in system design:**

| Code | Meaning | Implication |
|------|---------|-------------|
| 200  | OK | Normal success |
| 301  | Permanent redirect | Cached by browsers; changing it later is painful |
| 304  | Not Modified | Browser used its cache; no body transferred |
| 429  | Too Many Requests | Rate limit hit; client must implement backoff |
| 502  | Bad Gateway | Proxy reached origin but got an invalid response |
| 503  | Service Unavailable | Origin is down or overloaded; proxy couldn't connect |

### Phase 6 — Browser Rendering

The browser streams HTML rather than waiting for the full document. The rendering pipeline:

```
HTML bytes ──▶ Tokenizer ──▶ DOM tree ──┐
CSS bytes  ──▶ Tokenizer ──▶ CSSOM tree ──┤
                                          ▼
                                   Render tree
                                   (visible nodes only)
                                          │
                                     Layout pass
                                   (compute geometry)
                                          │
                                       Paint
                                   (rasterize pixels)
                                          │
                                     Composite
                                   (GPU layer merge)
```

**Critical rendering path**: the browser cannot render anything until it has both the DOM and the CSSOM. A `<link rel="stylesheet">` in `<head>` is **render-blocking** — the browser pauses rendering until that CSS file is fully downloaded and parsed. A `<script>` without `async` or `defer` is **parser-blocking** and **render-blocking**.

## Build It / In Depth

Use common command-line tools to observe each phase directly.

### Step 1 — Measure DNS Resolution Time

```bash
# Walk the full DNS hierarchy step by step
dig +trace example.com

# Measure just the DNS lookup time with curl
curl -w "dns: %{time_namelookup}s\n" -o /dev/null -s https://example.com
```

### Step 2 — Inspect the TCP and TLS Layers

```bash
# Show the full TLS negotiation (version, cipher, certificate chain)
curl -v https://example.com 2>&1 | grep -E "TLS|SSL|Connected|Certificate"

# Confirm TLS 1.3 is being used
openssl s_client -connect example.com:443 -tls1_3 2>&1 | grep "Protocol"
```

### Step 3 — Full Per-Phase Latency Breakdown

```bash
curl -w @- -o /dev/null -s https://example.com <<'EOF'
    dns_lookup:  %{time_namelookup}s
   tcp_connect:  %{time_connect}s
 tls_handshake:  %{time_appconnect}s
  pre_transfer:  %{time_pretransfer}s
          TTFB:  %{time_starttransfer}s
         total:  %{time_total}s
EOF
```

Sample output for a CDN-served site vs. a direct-to-origin request:

```
                  CDN edge (5ms RTT)    Origin (100ms RTT)
dns_lookup:             0.003s               0.021s
tcp_connect:            0.008s               0.121s
tls_handshake:          0.013s               0.222s
TTFB:                   0.031s               0.350s
total:                  0.089s               0.981s
```

The same HTML, the same server processing time — a 10x difference entirely explained by RTT and where TCP/TLS connections are terminated.

### End-to-End Latency Budget

For a cache-miss request from Frankfurt to a US-East origin (~100ms RTT):

```
Phase                   Typical latency
-----------------------|---------------
DNS resolution          |  20–80ms
TCP handshake           | ~100ms (1 RTT)
TLS 1.3 handshake       | ~100ms (1 RTT)
HTTP request + response | ~100ms + server time
Browser rendering       |  50–200ms
-----------------------|---------------
Total (cold start)      | ~400–600ms before first pixel
```

This budget makes clear why CDNs are the single highest-leverage optimization for geographically dispersed users.

## Use It

### CDNs (Cloudflare, Fastly, AWS CloudFront)

CDNs terminate TCP and TLS at an edge node close to the user, collapsing RTT from 100ms to 5ms. The CDN forwards cache-miss requests to origin over a persistent, pre-warmed connection. This compresses Phases 2–4 down to near-zero for cached content.

### Browser Resource Hints

Tell the browser to resolve DNS and open a connection before it discovers it needs to:

```html
<!-- Resolve DNS + TCP + TLS before the resource is requested -->
<link rel="preconnect" href="https://fonts.googleapis.com" crossorigin>

<!-- Resolve DNS only (lower cost, less benefit) -->
<link rel="dns-prefetch" href="https://api.example.com">

<!-- Tell the browser the next page the user is likely to visit -->
<link rel="prefetch" href="/courses/next-lesson">
```

### HTTP/2 vs HTTP/3 Comparison

| Feature | HTTP/1.1 | HTTP/2 | HTTP/3 (QUIC/UDP) |
|---------|----------|--------|-------------------|
| Connections per host | 6 (browser limit) | 1 (multiplexed streams) | 1 (QUIC streams) |
| Head-of-line blocking | Per connection | At TCP layer | Eliminated per stream |
| RTT cost (new connection) | 1 (TCP) + 1 (TLS) | 1 (TCP) + 1 (TLS) | 0 (merged) |
| Packet loss impact | Stalls connection | Stalls all streams | Stalls only affected stream |
| TLS required | No | Effectively yes | Always |

### Service Workers for Offline / Sub-Zero-RTT

A service worker can intercept fetch events and return a cached response from the browser's Cache API, bypassing Phases 2–5 entirely:

```js
// sw.js
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(cached => cached ?? fetch(event.request))
  );
});
```

## Common Pitfalls

- **DNS TTL too high before a migration**: A TTL of 86400s (24 hours) means any IP change takes up to 24 hours to propagate globally. Lower it to 300s at least 48 hours before a planned cutover, then restore it after the migration stabilizes.

- **Letting TLS certificates expire silently**: An expired certificate causes a hard failure for all users with no graceful degradation. Use automated renewal (Let's Encrypt + ACME client like Certbot or cert-manager) and add monitoring that alerts when a certificate is within 14 days of expiry.

- **Render-blocking third-party scripts**: Loading `<script src="https://analytics.example.com/tracker.js">` synchronously in `<head>` blocks the browser's HTML parser until the script downloads, parses, and executes. Always add `async` or `defer` to third-party scripts. Run Chrome Lighthouse to surface offenders.

- **Disabling TCP keep-alive or connection reuse**: Some server configs close the TCP connection after each response, forcing a fresh TCP+TLS handshake for every subsequent request. Ensure `keep-alive` is enabled in your HTTP/1.1 server config, or migrate to HTTP/2 where connection reuse is the default.

- **Conflating 502 and 503**: A `502 Bad Gateway` means the reverse proxy reached the origin server but received an invalid or incomplete response (origin process crashed, returned garbage). A `503 Service Unavailable` means the proxy could not reach the origin at all (overloaded, failing health check). The mitigation is different: 502 → check origin process logs; 503 → check upstream capacity and health check configuration.

## Exercises

1. **Easy**: Open Chrome DevTools → Network tab → navigate to `https://github.com`. Identify one request served from cache (look for `304` or `(disk cache)`), find the request with the longest DNS lookup time, and record the TTFB for the main document. What does the TTFB tell you about server-side processing?

2. **Medium**: Use the `curl -w` format string from the "Build It" section to measure per-phase latency for two sites: one served behind Cloudflare (check with `curl -I https://site.com | grep CF-Ray`) and one served directly from an origin server. Explain the latency difference for each phase in terms of the pipeline.

3. **Hard**: A startup's marketing site must achieve a p95 page-load time under 200ms for users across North America, Europe, and Southeast Asia. The origin server is a single VM in us-east-1. Design the full delivery architecture. Specify your DNS strategy (anycast vs. latency-based routing), CDN configuration, TLS version policy, HTTP protocol version, caching headers, and browser resource hints. Justify each decision with a latency number from the budget table above.

## Key Terms

| Term | What people think | What it actually means |
|------|------------------|------------------------|
| DNS | A phone book that returns IP addresses | A distributed, hierarchical, cached database of typed resource records (A, AAAA, CNAME, MX, TXT) each with their own TTL |
| TCP Handshake | A formality before real data flows | A three-message synchronization that costs one full RTT and is unavoidable for connection-oriented, reliable delivery |
| TLS | Just encryption | A protocol that provides authentication, key exchange, confidentiality, and integrity — all negotiated in a handshake that costs at minimum one RTT |
| TTFB | How long the page takes to load | Time to First Byte — the interval from sending the request to receiving the first byte of the response; it covers DNS + TCP + TLS + server processing, but not download or rendering |
| CDN | A content cache | A globally distributed network of edge servers that terminate TCP/TLS connections near users, reducing RTT across every phase that involves a network round trip |
| Render-blocking | Something that makes the site feel slow | A resource (CSS file or synchronous script) that prevents the browser from advancing past the Render tree construction step until it is fully downloaded and parsed |
| HTTP/3 | A small HTTP upgrade | A ground-up redesign replacing TCP with QUIC (UDP-based), eliminating connection-level head-of-line blocking and reducing connection setup to 0 RTT for returning visitors |

## Further Reading

- [MDN: Populating the page: how browsers work](https://developer.mozilla.org/en-US/docs/Web/Performance/How_browsers_work) — canonical reference for the full rendering pipeline from network bytes to pixels
- [High Performance Browser Networking — Ilya Grigorik](https://hpbn.co/) — free online book; chapters on TCP, TLS, HTTP/1.1, HTTP/2, and QUIC are directly applicable to every phase covered here
- [RFC 8446: TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446) — the protocol specification; Section 2 gives a clear handshake overview with message diagrams
- [Chrome DevTools Network Analysis](https://developer.chrome.com/docs/devtools/network/) — official guide to reading the waterfall chart and timing breakdown for each request
- [RFC 9114: HTTP/3](https://www.rfc-editor.org/rfc/rfc9114) — the HTTP/3 specification; the motivation section explicitly compares the protocol to HTTP/2 and explains how QUIC addresses its limitations
