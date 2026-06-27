# The HTTP Mindmap

> HTTP is not just a protocol — it is the connective tissue of every distributed system you will ever design.

**Type:** Learn
**Prerequisites:** How the Internet Works, TCP/IP Fundamentals
**Time:** ~35 minutes

---

## The Problem

You open a browser, type a URL, and a webpage appears. Behind that interaction is a chain of protocols, infrastructure components, security layers, and data-exchange formats — all of which must work together without you thinking about them. When something breaks — a timeout, a 502, a response that is inexplicably stale — you need a mental model that tells you exactly which layer failed and why.

Without a holistic map of HTTP and the ecosystem around it, you make dangerous assumptions: that HTTPS just "happens", that your CDN is always a cache hit, that HTTP/2 multiplexing solves all latency problems. These assumptions lead to slow APIs, misconfigured proxies, security vulnerabilities, and debugging sessions that consume entire afternoons.

This lesson builds that map. You will not memorize RFCs. You will instead understand how every major HTTP-adjacent technology — from TCP sockets to GraphQL to Wireshark — fits into a single coherent picture, and why each piece exists.

---

## The Concept

### The Seven Zones of the HTTP Ecosystem

Think of HTTP as living at the center of seven concentric zones. From lowest to highest abstraction:

```
┌─────────────────────────────────────────────────────────────────┐
│  7. OBSERVABILITY  (Wireshark · tcpdump · OpenTelemetry)        │
│  6. DATA FORMATS   (REST/JSON · GraphQL · gRPC · SOAP)          │
│  5. EDGE LAYER     (CDN · DNS · Reverse Proxy · API Gateway)    │
│  4. SECURITY       (TLS/HTTPS · Certs · mTLS · CORS)            │
│  3. HTTP VERSIONS  (HTTP/1.1 → HTTP/2 → HTTP/3/QUIC)           │
│  2. REAL-TIME EXT  (WebSockets · SSE · Long-Polling)            │
│  1. TRANSPORT      (TCP/IP · UDP · Unix Sockets · QUIC)         │
└─────────────────────────────────────────────────────────────────┘
```

Each zone was created to solve a problem introduced by the zone below it. HTTPS exists because bare TCP carries data in plaintext. HTTP/2 exists because HTTP/1.1 head-of-line blocking caused latency under concurrency. QUIC exists because TCP's kernel-level handshake made HTTP/2 multiplexing impossible over lossy networks. Understanding the **why** at each layer is what separates architects from copy-pasters.

---

### Zone 1: Transport

HTTP is an application-layer protocol. It needs a transport underneath.

| Transport | Used by | Why |
|-----------|---------|-----|
| TCP over IPv4/IPv6 | HTTP/1.1, HTTP/2 | Reliable, ordered delivery |
| UDP (via QUIC) | HTTP/3 | Lower handshake overhead, no head-of-line blocking |
| Unix Domain Socket | Local services (Nginx ↔ app) | Zero network overhead for same-host IPC |
| TLS over TCP | HTTPS (any version) | Encrypted TCP before HTTP bytes land |

Key insight: HTTP/3 is HTTP semantics (methods, headers, status codes) carried over QUIC, not TCP. QUIC re-implements reliability in userspace over UDP, which means it can be updated faster than TCP (which lives in the OS kernel).

---

### Zone 2: Real-Time Extensions

HTTP's request-response model is pull-based. A client asks; a server answers. Real-time use cases — live dashboards, chat, collaborative editing — require the server to push without waiting for a poll.

```
HTTP request/response (pull)
  Client ──GET /data──► Server
  Client ◄──200 OK───── Server
  (connection closed or kept alive, but silent until next request)

WebSocket (full duplex)
  Client ──GET /ws Upgrade: websocket──► Server
  Client ◄──101 Switching Protocols──── Server
  Client ◄══ message ══════════════════ Server  ← server push
  Client ══ message ═══════════════════► Server ← client push
  (single TCP connection, both directions, indefinitely)

Server-Sent Events (half duplex, server→client only)
  Client ──GET /stream──► Server
  Client ◄── event: … ─── Server  (text/event-stream, open forever)
```

WebSockets suit bidirectional real-time use cases. SSE suits unidirectional server-to-client streams (news feeds, live metrics). Long-polling — the client immediately re-requests after each response — is the legacy fallback that works everywhere but wastes connections.

---

### Zone 3: HTTP Versions

This is the most misunderstood zone. Engineers know the names but not the actual trade-offs.

```
HTTP/1.1 (1997)
  Client → Server: GET /a  (wait)
  Client ← Server: 200 /a
  Client → Server: GET /b  (wait)
  Client ← Server: 200 /b
  Problem: sequential — later requests are blocked by earlier ones
  Workaround: open 6 parallel TCP connections per browser (wasteful)

HTTP/2 (2015)
  Single TCP connection, multiple "streams" multiplexed
  Client → Server: stream 1 GET /a │ stream 3 GET /b (same TCP)
  Client ← Server: stream 3 200 /b │ stream 1 200 /a (any order)
  New features: header compression (HPACK), server push (deprecated), binary frames
  Problem: TCP head-of-line blocking — one lost packet stalls ALL streams

HTTP/3 (2022, RFC 9114)
  QUIC over UDP replaces TCP
  Each QUIC stream is independent — one lost packet only stalls that stream
  0-RTT or 1-RTT handshake (vs TCP's 1-RTT + TLS 1-RTT = 2-RTT minimum)
  Connection migration: switch from Wi-Fi to LTE without reconnecting
```

| Feature | HTTP/1.1 | HTTP/2 | HTTP/3 |
|---------|----------|--------|--------|
| Transport | TCP | TCP | QUIC/UDP |
| Multiplexing | No (workaround: 6 conns) | Yes (1 TCP conn) | Yes (true stream isolation) |
| Header compression | No | HPACK | QPACK |
| Handshake RTTs | TCP(1) + TLS(1-2) = 2-3 | Same | 0–1 RTT |
| HOL blocking | TCP + HTTP | TCP only | None |
| Adoption (2024) | ~25% | ~40% | ~32% |

---

### Zone 4: Security

HTTPS = HTTP + TLS. TLS (Transport Layer Security) establishes an encrypted, authenticated channel before a single HTTP byte is exchanged.

```
TLS 1.3 Handshake (1-RTT)

Client                              Server
  │─── ClientHello (key_share) ────►│
  │◄── ServerHello + Certificate ───│
  │◄── EncryptedExtensions ─────────│
  │◄── Finished ────────────────────│
  │─── Finished ────────────────────►│
  │═══════ Encrypted HTTP data ═════│
```

Critical concepts beyond basic HTTPS:

- **Certificate pinning**: hardcode expected server certificate or CA in client; prevents MITM even with a compromised CA.
- **mTLS (mutual TLS)**: both client and server present certificates. Used in service meshes (Istio, Linkerd) for zero-trust network security.
- **HSTS (HTTP Strict Transport Security)**: header that tells browsers to refuse plaintext HTTP for a domain for N seconds. Prevents SSL stripping attacks.
- **CORS (Cross-Origin Resource Sharing)**: not an encryption concern but a browser security policy. A server must opt in to cross-origin requests via `Access-Control-Allow-Origin`; a missing header produces the infamous "CORS error" that is never a client bug.

---

### Zone 5: The Edge Layer

Between clients and your application servers sits a layer of infrastructure that most developers ignore until something breaks.

```
Internet Client
      │
      ▼
   DNS Resolver  ←── "api.example.com → 104.21.x.x"
      │
      ▼
  CDN PoP (e.g., Cloudflare edge node in Frankfurt)
  ├── Cache hit? → return cached response (latency ~5ms)
  └── Cache miss? → forward to origin
             │
             ▼
     Reverse Proxy / Load Balancer (e.g., Nginx, HAProxy)
     ├── TLS termination
     ├── Rate limiting
     ├── Health-check routing
     └── Forward to app instances
             │
             ▼
      Application Servers
```

| Component | Primary job | Example products |
|-----------|-------------|-----------------|
| DNS | Name → IP resolution | Route53, Cloudflare DNS |
| CDN | Cache static/dynamic content at edge | Cloudflare, Fastly, AWS CloudFront |
| Reverse Proxy | TLS termination, routing, load balancing | Nginx, HAProxy, Envoy |
| API Gateway | Auth, rate limiting, request transformation | Kong, AWS API GW, Apigee |
| Forward Proxy | Client-side traffic filtering/routing | Squid, corporate egress proxies |

**DNS is not just lookup.** DNS TTLs, anycast routing, GeoDNS, and health-checked failover are all tools for availability and latency. A misconfigured TTL (too high) delays failover; too low floods DNS resolvers.

---

### Zone 6: Data Exchange Formats

HTTP carries payloads. What format those payloads take determines your API's ergonomics, performance, and coupling.

| Style | Transport | Schema | Best for |
|-------|-----------|--------|----------|
| REST/JSON | HTTP | None (or OpenAPI) | Public APIs, simple CRUD |
| GraphQL | HTTP POST (usually) | Schema required | Flexible client queries, mobile |
| gRPC | HTTP/2 | Protobuf (strict) | Internal services, high throughput |
| SOAP | HTTP POST | WSDL (XML) | Enterprise/legacy integrations |

REST is not a protocol — it is an architectural style. It gives you HTTP verbs (GET, POST, PUT, PATCH, DELETE), status codes as semantic signals, and stateless interactions. The common mistake is treating REST as "JSON over HTTP" without honoring HTTP's contract (idempotency of GET, meaning of 404 vs 400, etc.).

gRPC's use of HTTP/2 is not incidental: it gets true multiplexing, binary framing, and bidirectional streaming for free, which is why it dominates inter-service communication at companies like Google and Netflix.

---

### Zone 7: Observability

When something goes wrong between zones 1 and 6, you need tools to see the actual bytes.

| Tool | What it shows | When to use |
|------|--------------|-------------|
| `curl -v` | HTTP request/response headers, status | Quick sanity check |
| `tcpdump` | Raw packets at kernel level | Confirming TCP connection, TLS handshake timing |
| Wireshark | Packet capture with GUI and HTTP decode | Deep debugging, TLS session key export |
| OpenTelemetry | Distributed traces across services | End-to-end latency breakdown in production |
| `robots.txt` | Not observability — access rules for crawlers | Preventing indexing of internal paths |

OpenTelemetry propagates context via HTTP headers (`traceparent`, `tracestate`) defined in the W3C Trace Context spec. Every hop — CDN, proxy, app server — can add a span, giving you a complete latency waterfall.

---

## Build It / In Depth

### Walking a Real Request Through the Full Stack

Scenario: a mobile client calls `https://api.example.com/v1/users/42`.

**Step 1 — DNS Resolution**
```bash
dig api.example.com
# Returns A record: 104.21.55.12  (Cloudflare CDN PoP)
# TTL: 300s (5 min failover window)
```

**Step 2 — TLS Handshake (HTTP/2 negotiation via ALPN)**
```
Client Hello → ALPN extension: ["h2", "http/1.1"]
Server selects "h2" → HTTP/2 on this connection
TLS 1.3 completes in 1-RTT
```

**Step 3 — HTTP/2 Request (binary frames)**
```
HEADERS frame (stream 1):
  :method  GET
  :path    /v1/users/42
  :scheme  https
  :authority api.example.com
  authorization: Bearer eyJ...
  accept: application/json
```

**Step 4 — CDN Cache Check**
```
CDN checks: GET /v1/users/42, Cache-Control from last response?
If "Cache-Control: public, max-age=60" → return cached, add Age: 23 header
If "Cache-Control: private" or "Authorization present" → forward to origin
```

**Step 5 — Reverse Proxy (Nginx)**
```nginx
# /etc/nginx/conf.d/api.conf
upstream api_backend {
    server 10.0.1.10:8080;
    server 10.0.1.11:8080;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    ssl_certificate     /etc/ssl/api.crt;
    ssl_certificate_key /etc/ssl/api.key;

    location /v1/ {
        proxy_pass http://api_backend;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Request-Id   $request_id;
    }
}
```

**Step 6 — Application Response**
```python
# Flask example — the actual user service
@app.route("/v1/users/<int:user_id>")
def get_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({"error": "not found"}), 404
    response = jsonify(user.to_dict())
    response.headers["Cache-Control"] = "private, max-age=60"
    response.headers["ETag"] = f'"{user.updated_at.timestamp()}"'
    return response
```

**Step 7 — Response travels back**
```
HTTP/2 200
content-type: application/json
cache-control: private, max-age=60
etag: "1719436800.0"
x-request-id: a3f2...

{"id": 42, "name": "Alice", "email": "alice@example.com"}
```

**Step 8 — Client caches, next request uses conditional GET**
```
GET /v1/users/42
If-None-Match: "1719436800.0"

Server: 304 Not Modified  ← no body sent, saves bandwidth
```

---

### Inspecting HTTP/2 Frames with curl

```bash
# See HTTP/2 frames (requires curl with nghttp2)
curl -v --http2 https://api.example.com/v1/users/42 2>&1 | head -40

# Force HTTP/1.1 for comparison
curl -v --http1.1 https://api.example.com/v1/users/42

# Measure timing breakdown
curl -w "dns:%{time_namelookup}s  connect:%{time_connect}s  tls:%{time_appconnect}s  ttfb:%{time_starttransfer}s  total:%{time_total}s\n" \
     -o /dev/null -s https://api.example.com/v1/users/42
```

---

## Use It

### Choosing the Right Layer to Solve Performance Problems

| Problem | Wrong answer | Right answer |
|---------|-------------|-------------|
| API responses too slow globally | Scale up app servers | Add CDN with appropriate Cache-Control |
| Latency spike on first request from mobile | Nothing | Enable HTTP/3/QUIC; reduces handshake RTTs |
| Chat app needs server push | Polling every 1s | WebSockets or SSE |
| Internal microservice latency | REST/JSON | gRPC over HTTP/2 with Protobuf |
| 502 errors under load | Debug app code | Check upstream timeout config in reverse proxy |
| Inter-service auth in K8s | API key headers | mTLS via service mesh (Istio/Linkerd) |

### Technology Landscape

**CDN**: Cloudflare (free tier + Workers for edge compute), AWS CloudFront (deep AWS integration), Fastly (real-time purge, popular with media companies).

**Reverse Proxy / Load Balancer**: Nginx (HTTP proxy, static files, TLS termination), HAProxy (L4/L7 TCP+HTTP, battle-tested at scale), Envoy (dynamic config via xDS API, built for service meshes).

**API Gateway**: Kong (plugin ecosystem, on-prem/cloud), AWS API Gateway (tight Lambda integration), Apigee (Google Cloud, enterprise features).

**Observability**: Wireshark for local packet inspection; Datadog APM / Jaeger / Tempo for distributed tracing using OpenTelemetry.

---

## Common Pitfalls

- **Ignoring `Cache-Control` semantics at the CDN layer.** Sending `Cache-Control: no-cache` when you mean `no-store` is the most common CDN misconfiguration. `no-cache` means "revalidate before serving"; `no-store` means "never cache". An API that leaks user data to other users via a shared CDN cache almost always traces back to this distinction.

- **Assuming HTTP/2 eliminates all latency.** HTTP/2 multiplexing solves HTTP-layer head-of-line blocking but TCP-layer packet loss still stalls all streams. On mobile networks with 2–5% loss, HTTP/2 can perform *worse* than HTTP/1.1 with 6 parallel connections. Enable HTTP/3 where possible.

- **Forgetting that WebSocket connections are persistent and stateful.** A horizontal scale-out behind a load balancer will route the WebSocket upgrade to one server, then subsequent frames to a different server. You need sticky sessions or a pub/sub broker (Redis, Kafka) to fan out messages across servers.

- **Setting DNS TTL too high before a migration.** If you plan to change IPs (new CDN, new region), set TTL to 60s at least 48 hours in advance. A 24-hour TTL means some resolvers will keep the old IP for 24 hours after you change the record.

- **Treating CORS errors as a server bug to suppress.** Adding `Access-Control-Allow-Origin: *` to silence a CORS error on a credentialed endpoint is a security vulnerability, not a fix. CORS with credentials requires a specific allowed origin, not a wildcard, and the cookie `SameSite` and `Secure` attributes must also be set correctly.

---

## Exercises

1. **Easy** — Run `curl -w` against any public HTTPS API and record the DNS lookup time, TCP connect time, TLS handshake time, and time to first byte. Then explain which of these values would change if the server supported HTTP/3, and which would stay the same.

2. **Medium** — Design the edge layer for a global e-commerce API that has both public product catalog endpoints (cacheable) and authenticated cart endpoints (never cacheable). Write out the `Cache-Control` headers you would set for each endpoint type, the CDN configuration rules, and explain what happens when a user updates their cart.

3. **Hard** — A streaming video startup runs HTTP/2 between their CDN and origin. During high-traffic events, users in regions with >3% packet loss report buffering despite the origin having capacity. Diagnose the root cause, propose a solution at each of the relevant layers (transport, HTTP version, edge), and explain the trade-offs of each approach.

---

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|----------------------|
| HTTPS | HTTP with a padlock | HTTP over a TLS-encrypted TCP connection; authenticates the server and encrypts all data |
| HTTP/2 multiplexing | Multiple requests in parallel | Multiple logical streams over a *single* TCP connection; still one packet queue at the TCP level |
| CDN | Makes things faster | A geographically distributed cache network; only helps if your content is actually cacheable |
| Reverse Proxy | Just a router | A server that terminates client connections, optionally terminates TLS, and opens a new connection to upstreams |
| REST | JSON over HTTP | An architectural style using HTTP verbs, status codes, and stateless interactions; JSON is one possible body format |
| CORS error | The server is blocking me | The browser is enforcing the same-origin policy; the server must explicitly opt in to cross-origin requests |
| WebSocket | A different protocol | An upgrade negotiated over HTTP/1.1 (101 Switching Protocols) that reuses the TCP connection for full-duplex messaging |

---

## Further Reading

- [MDN Web Docs — HTTP](https://developer.mozilla.org/en-US/docs/Web/HTTP) — Authoritative reference for HTTP methods, headers, status codes, and caching; covers HTTP/1.1 through HTTP/3.
- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114) — The official spec; the introduction section alone is worth reading for understanding the motivation behind QUIC.
- [High Performance Browser Networking — Ilya Grigorik](https://hpbn.co/) — Free online book; chapters on HTTP/1.1, HTTP/2, QUIC, and WebSockets are industry-standard references.
- [Cloudflare Blog — HTTP/3 Explained](https://blog.cloudflare.com/http3-the-past-present-and-future/) — Practical, non-RFC explanation of QUIC and HTTP/3 from engineers who deployed it at scale.
- [OpenTelemetry W3C Trace Context](https://www.w3.org/TR/trace-context/) — The spec for distributed tracing propagation over HTTP headers; essential for understanding how `traceparent` links spans across service boundaries.
