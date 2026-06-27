# What happens when you type google.com into a browser?

> Every web request is a coordinated sprint across a dozen independent systems — knowing each leg is how you design the fast ones.

**Type:** Learn
**Prerequisites:** None
**Time:** ~25 minutes

---

## The Problem

You open Chrome and type `google.com`. The page loads in 200 ms. Now imagine you're the engineer on-call at 2 a.m. and that same page is taking 4 seconds. Where do you even start?

Without a precise mental model of the full request path, you're guessing. Is it DNS? The TCP handshake? A slow database query behind the load balancer? TLS negotiation overhead? Latency you misattribute to the server could actually be sitting in a browser-level cache miss, or a misrouted DNS query crossing an extra continent. Each stage has its own failure modes, its own tools for inspection, and its own leverage points for optimization.

This lesson builds a complete, numbered picture of the path from keypress to pixels. Every subsequent system-design topic — CDNs, load balancers, caching, HTTP/2, service workers — is a knob on one specific stage of this flow. Know the flow, and the rest becomes obvious.

---

## The Concept

The journey has eight logical stages. They happen in under a second on a warm path; understanding why they sometimes don't is what system design is about.

### Stage 1 — URL Parsing

Before anything hits the network, the browser dissects what you typed.

```
https://www.google.com/search?q=cats
└─┬──┘ └──┬──────────┘└──┬──┘└───┬──┘
 scheme  hostname        path   query
```

If you omit the scheme (as you usually do), the browser heuristically prepends `https://`. It also checks whether the string is a search query instead of a hostname — if it contains spaces or no dots, the browser routes it to your default search engine.

### Stage 2 — DNS Resolution

The browser needs an IP address for `www.google.com`. It checks four caches in order, stopping at the first hit:

| Cache level | Where | Typical TTL |
|---|---|---|
| Browser cache | In-process memory | Per-record TTL (often 60 s) |
| OS resolver cache | `/etc/hosts` + OS stub resolver | Per-record TTL |
| Recursive resolver | Your ISP or 8.8.8.8 | Per-record TTL |
| Authoritative DNS | Google's own nameservers | Set by Google |

On a cold path, the OS stub resolver forwards the query to a **recursive resolver** (e.g., `8.8.8.8`). That resolver walks the DNS tree:

```
Recursive resolver
   │
   ├─► Root nameserver (.)
   │       "I don't know google.com, ask a .com TLD server"
   │
   ├─► .com TLD nameserver
   │       "I don't know www.google.com, ask ns1.google.com"
   │
   └─► Authoritative nameserver (ns1.google.com)
           "www.google.com → 142.250.80.36, TTL=300"
```

The recursive resolver caches the result. Future queries from any client on that resolver skip the tree walk. This is why DNS TTL is a performance and operational knob — a TTL of 300 s means a change propagates to end users in at most 5 minutes; a TTL of 3600 s means an hour of stale cache.

**Google runs Anycast DNS**: the same IP (`8.8.8.8`) is announced from dozens of points of presence worldwide. Your query routes to the nearest one via BGP, so Google's DNS lookup is fast even for users in Asia or South America.

### Stage 3 — TCP Connection (Three-Way Handshake)

With an IP in hand, the browser opens a TCP connection to port 443 (HTTPS).

```
Client                          Server
  │──── SYN (seq=x) ───────────►│
  │◄─── SYN-ACK (seq=y, ack=x+1)│
  │──── ACK (ack=y+1) ──────────►│
        Connection established
```

This costs **one round-trip time (RTT)** before a single byte of application data is exchanged. On a 50 ms RTT link (e.g., cross-country US), you've spent 50 ms just saying hello — before TLS even starts.

**Connection reuse** is the primary mitigation: HTTP keep-alive (HTTP/1.1 default) and connection multiplexing (HTTP/2) avoid paying this cost on every request.

### Stage 4 — TLS Handshake (HTTPS)

After TCP, the client and server negotiate encryption. TLS 1.3 (current standard) costs **one additional RTT**:

```
Client                             Server
  │──── ClientHello ──────────────►│  (supported cipher suites, random)
  │◄─── ServerHello + Certificate ─│  (chosen suite, public key)
  │◄─── EncryptedExtensions ───────│
  │──── Finished (session key) ────►│
        Encrypted channel open
```

TLS 1.3 reduced this from the two RTTs required by TLS 1.2. **TLS session resumption** (0-RTT) can eliminate the cost entirely for returning visitors, at a small risk of replay attacks.

Total cost so far before the first HTTP byte: **1 RTT (TCP) + 1 RTT (TLS) = 2 RTTs**.

### Stage 5 — HTTP Request

The browser sends an HTTP GET:

```
GET / HTTP/2
Host: www.google.com
User-Agent: Mozilla/5.0 ...
Accept: text/html,application/xhtml+xml,...
Accept-Encoding: gzip, br
Cookie: SID=...
```

With HTTP/2, this request travels over a single multiplexed connection. Multiple requests (for HTML, CSS, JS, images) can be in-flight simultaneously over the same TCP connection — eliminating the head-of-line blocking of HTTP/1.1.

### Stage 6 — Server-Side Processing

Google's edge is not a single machine. The request hits a **load balancer**, which routes it to one of thousands of frontend servers based on health, capacity, and geographic proximity. That frontend server may:

- Return a cached response from an in-memory store (Memcached/Redis layer)
- Call downstream services (search index, ads, personalization)
- Assemble the final HTML

For google.com's homepage, most of this is cached — the RTT budget for dynamic generation is often under 20 ms.

### Stage 7 — HTTP Response

The server replies:

```
HTTP/2 200 OK
Content-Type: text/html; charset=UTF-8
Content-Encoding: br
Cache-Control: private, max-age=0
Transfer-Encoding: chunked

<!doctype html>...
```

The browser begins parsing before the full response arrives. This is **streaming HTML parsing** — the browser doesn't wait for the final byte.

### Stage 8 — Browser Rendering Pipeline

Once HTML bytes start arriving, the browser runs a multi-stage pipeline:

```
Bytes → Characters → Tokens → Nodes → DOM
                                         \
CSS Bytes → Tokens → Rules → CSSOM        \
                                          Render Tree → Layout → Paint → Composite
```

| Stage | What happens |
|---|---|
| **Tokenization** | Raw bytes parsed into HTML tokens (open tags, text, close tags) |
| **DOM construction** | Tokens assembled into the Document Object Model tree |
| **CSSOM construction** | CSS parsed in parallel into the CSS Object Model |
| **Render tree** | DOM + CSSOM merged; invisible nodes (display:none) excluded |
| **Layout (reflow)** | Browser computes geometry: position and size of every element |
| **Paint** | Elements rasterized into pixels on layers |
| **Composite** | GPU assembles layers in the correct order onto screen |

JavaScript execution can **block** DOM construction. A `<script>` tag without `async` or `defer` pauses HTML parsing until the script downloads, parses, and executes. This is why render-blocking JS is a primary performance problem and why `defer` exists.

---

## Build It / In Depth

Let's trace a real request using command-line tools you can run right now.

### Step 1 — Inspect DNS

```bash
# Full recursive resolution trace
dig +trace www.google.com

# Check what your OS resolver returns and its TTL
dig www.google.com A
```

Look at the `ANSWER SECTION` — the TTL on the A record tells you how long the recursive resolver will cache this result.

### Step 2 — Measure TCP + TLS timing

```bash
curl -o /dev/null -s -w "\
  DNS lookup:    %{time_namelookup}s\n\
  TCP connect:   %{time_connect}s\n\
  TLS handshake: %{time_appconnect}s\n\
  TTFB:          %{time_starttransfer}s\n\
  Total:         %{time_total}s\n" \
  https://www.google.com
```

Sample output:
```
  DNS lookup:    0.010s
  TCP connect:   0.025s
  TLS handshake: 0.058s
  TTFB:          0.095s
  Total:         0.187s
```

The TLS handshake adds ~33 ms on top of the 25 ms TCP handshake. The difference between `time_connect` and `time_appconnect` is your TLS cost.

### Step 3 — Observe the HTTP request/response headers

```bash
curl -I https://www.google.com
```

Key response headers to examine:
- `Content-Encoding: br` — Brotli compression is active
- `Cache-Control` — dictates browser and CDN caching behavior
- `alt-svc: h3=":443"` — tells the browser Google supports HTTP/3 (QUIC) for next time

### Step 4 — Render pipeline in DevTools

Open Chrome DevTools → **Performance** tab → record a page load. The **Waterfall** view maps exactly onto stages 2–8 above: you can see DNS time, TCP connect, TLS, waiting (TTFB), and content download as separate colored bands per resource.

```
Resource: www.google.com
├── DNS:          10 ms   ← Stage 2
├── TCP Connect:  25 ms   ← Stage 3
├── TLS:          33 ms   ← Stage 4
├── Request sent:  1 ms   ← Stage 5
├── TTFB:         95 ms   ← Stages 5-6
└── Content:      12 ms   ← Stage 7
```

---

## Use It

| Technology | Which stage it optimizes | How |
|---|---|---|
| **CDN** (Cloudflare, Fastly, Akamai) | Stage 2, 3, 6 | DNS Anycast routes users to nearby PoP; TCP + TLS terminate close to the user; edge caches serve responses without hitting origin |
| **HTTP/2** | Stage 5 | Multiplexes multiple requests over one TCP connection; eliminates head-of-line blocking |
| **HTTP/3 / QUIC** | Stage 3, 5 | Replaces TCP with UDP-based QUIC; combines TCP + TLS handshake into one RTT; eliminates TCP head-of-line blocking |
| **DNS prefetch / preconnect** | Stage 2, 3 | `<link rel="preconnect">` starts TCP+TLS before the browser needs the resource |
| **Service Workers** | Stage 2–6 | Intercept requests in the browser; serve responses from cache with zero network cost |
| **TLS session resumption / 0-RTT** | Stage 4 | Eliminates the TLS handshake RTT for returning clients |
| **Brotli / gzip compression** | Stage 7 | Reduces response bytes; shrinks content download time at the cost of CPU |
| **`defer` / `async` on scripts** | Stage 8 | Prevents JS from blocking DOM construction |

**When to reach for a CDN**: Any time your users are geographically distributed and your content has some cacheable portion. The RTT reduction alone (e.g., 200 ms → 20 ms to nearest PoP) dwarfs almost any backend optimization.

**When HTTP/3 matters most**: High-packet-loss networks (mobile, satellite). QUIC's per-stream loss recovery prevents a single lost packet from stalling all in-flight requests, unlike TCP.

---

## Common Pitfalls

- **Assuming DNS is free.** A cold DNS lookup crosses three or four server hops and takes 10–100 ms depending on location. High DNS TTLs reduce this cost for users but slow down rollbacks. Low TTLs increase flexibility but amplify load on resolvers. Pick TTL based on how quickly you need to reroute traffic, not as an afterthought.

- **Counting TLS as "slow."** TLS 1.3 with session resumption adds near-zero marginal cost. Engineers who disabled HTTPS "for performance" in the past were using TLS 1.0/1.2 without resumption. Never trade security for perceived TLS speed gains on modern stacks.

- **Ignoring render-blocking resources.** Even after a fast server response, a single synchronous `<script src="...">` in the `<head>` can freeze DOM construction for hundreds of milliseconds. Use `defer`, `async`, or move scripts to the end of `<body>`.

- **Conflating TTFB with server latency.** Time To First Byte includes DNS + TCP + TLS + request transmission + server processing. A high TTFB could be slow DNS (fix: preconnect, CDN), not a slow backend. Always decompose with `curl -w` or DevTools before optimizing the wrong layer.

- **Forgetting that HTTP/2 still uses TCP.** HTTP/2 multiplexing eliminates application-level head-of-line blocking, but a single dropped TCP packet still stalls all streams until retransmit. If you're on a lossy network, HTTP/3/QUIC's per-stream recovery is the real fix.

---

## Exercises

1. **Easy:** Run `curl -o /dev/null -s -w "%{time_namelookup} %{time_connect} %{time_appconnect} %{time_total}\n" https://www.github.com` and identify which number represents DNS lookup time and which is the TLS handshake cost. Explain what the delta between `time_connect` and `time_appconnect` tells you.

2. **Medium:** Pick a website that loads slowly for you. Use Chrome DevTools' Network waterfall to identify which stage (DNS, TCP, TLS, TTFB, content download) accounts for the most latency. Propose one specific infrastructure change that would reduce it.

3. **Hard:** A startup's API is hosted in `us-east-1`. Their users are in Europe and latency complaints are rising. Sketch the full request path changes if they add a CDN with an EU PoP. For each stage (DNS, TCP, TLS, HTTP request, server processing, response), state whether the latency improves, stays the same, or depends — and why.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **DNS** | "Just a phone book" | A globally distributed, hierarchical, cached database with TTLs, multiple record types (A, CNAME, MX, TXT), and Anycast routing — failure here takes down the whole site |
| **TCP handshake** | "Negligible overhead" | A mandatory one-RTT round-trip before any data flows; at 100 ms RTT that's 100 ms of dead time on every new connection |
| **TLS** | "Slow encryption layer" | A one-RTT negotiation (TLS 1.3) that adds encryption, authentication, and integrity — with session resumption it's effectively free for repeat visitors |
| **TTFB** | "Server response time" | Time To First Byte includes DNS + TCP + TLS + network transit + server processing — it's a composite metric, not purely server speed |
| **CDN** | "A cache for static files" | A globally distributed network that terminates TCP/TLS near the user, caches at the edge, and can route dynamic requests to the nearest origin — it optimizes multiple stages, not just caching |
| **DOM** | "The HTML of the page" | The browser's in-memory tree of objects representing parsed HTML; JavaScript manipulates the DOM, not the raw HTML string |
| **Render-blocking resource** | "A slow resource" | A CSS or synchronous JS resource that pauses the browser's ability to construct or render the DOM until it fully downloads and processes |

---

## Further Reading

- **MDN — How browsers work** — https://developer.mozilla.org/en-US/docs/Web/Performance/How_browsers_work — The canonical reference for the full rendering pipeline, with diagrams.
- **High Performance Browser Networking (Ilya Grigorik)** — https://hpbn.co — Free online book. Chapters 2–4 cover TCP, TLS, and HTTP in the precise depth this lesson summarizes.
- **RFC 9114 — HTTP/3** — https://www.rfc-editor.org/rfc/rfc9114 — The spec that defines HTTP/3 over QUIC; Section 1 is a readable motivation for why QUIC replaces TCP.
- **Chrome DevTools Network Analysis reference** — https://developer.chrome.com/docs/devtools/network/reference — Official guide to reading the waterfall, understanding timing phases, and diagnosing real requests.
- **Cloudflare Learning — What is DNS?** — https://www.cloudflare.com/learning/dns/what-is-dns/ — Readable, accurate, and illustrated walk-through of the DNS resolution process.
