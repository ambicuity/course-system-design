# Top 6 most commonly used Server Types

> Every request you've ever made touched at least three of these — knowing which one is doing what changes how you design everything.

**Type:** Learn
**Prerequisites:** Client-Server Architecture, HTTP Fundamentals, DNS Basics
**Time:** ~25 minutes

---

## The Problem

You're asked to design a system that lets users upload videos, share them via a public URL, and receive email notifications when someone comments. Simple enough on paper — but which machines handle which responsibility? If you drop a single server type, your architecture breaks in ways that aren't obvious until production.

Without a clear mental model of server roles, engineers routinely route the wrong traffic to the wrong tier. They send file uploads through a web server that was never meant to hold data at rest, or they let an origin server absorb millions of CDN-bypass requests because nobody configured a proxy in front of it. Costs spike, latency explodes, and security boundaries blur.

This lesson builds a precise vocabulary. You need to know not just what each server type does, but why it exists as a distinct role, what happens when you collapse roles onto one machine, and when to separate them again.

---

## The Concept

### The Six Roles at a Glance

| # | Server Type | Core Job | Primary Protocol |
|---|-------------|----------|-----------------|
| 1 | Web Server | Serve HTTP responses (static + dynamic gateway) | HTTP/HTTPS |
| 2 | Mail Server | Send, receive, and route email | SMTP / IMAP / POP3 |
| 3 | DNS Server | Resolve domain names to IP addresses | UDP/TCP port 53 |
| 4 | Proxy Server | Mediate connections between clients and backends | HTTP, SOCKS |
| 5 | FTP Server | Transfer files between hosts | FTP / SFTP / FTPS |
| 6 | Origin Server | Hold the authoritative copy of content (often behind a CDN) | HTTP/HTTPS |

These are *roles*, not necessarily physical machines. A single EC2 instance can play web server + origin server simultaneously. A large company might run thousands of DNS servers. Role clarity matters; physical topology is a separate concern.

### How a Typical Request Flows Through Multiple Server Types

```
Client Browser
    │
    ▼
[1] DNS Server         ← "What IP is api.example.com?" → returns 203.0.113.42
    │
    ▼
[2] Proxy / Load Balancer  ← optional forward/reverse proxy, TLS termination
    │
    ▼
[3] Web Server         ← handles HTTP, routes to app logic or returns static files
    │          │
    ▼          ▼
[4] Origin Server   App Logic / DB
    │
    ▼
CDN Edge Nodes      ← cached copy served closer to users next time
```

Every click on a public website exercises steps 1-3 at minimum.

---

### 1. Web Server

A web server accepts HTTP/HTTPS connections and returns responses. It does two things well:

- **Serves static assets** (HTML, CSS, JS, images) directly from disk with minimal CPU.
- **Acts as a reverse proxy** to application servers (Django, Node.js, Rails), handling connection management so the app doesn't have to.

Popular implementations: **Nginx**, **Apache httpd**, **Caddy**, **LiteSpeed**.

Nginx's event-driven, non-blocking architecture handles tens of thousands of concurrent connections in a single process. Apache's thread-per-connection model trades memory for compatibility. For most new systems, Nginx or Caddy wins.

**What a web server is NOT:** It is not where business logic lives. It should not touch the database. Keep it thin.

---

### 2. Mail Server

Email looks simple. Under the hood it's a pipeline of at least three protocols:

```
Sender MUA → [SMTP Submission] → Sender MTA → [SMTP Relay] → Receiver MTA
                                                                    │
                                                          [IMAP/POP3 Access]
                                                                    │
                                                          Recipient MUA (inbox)
```

- **MTA (Mail Transfer Agent):** Routes email between domains. Examples: **Postfix**, **Exim**, **Microsoft Exchange**.
- **MDA (Mail Delivery Agent):** Deposits mail into the recipient's mailbox (Dovecot, Procmail).
- **MUA (Mail User Agent):** The email client (Outlook, Thunderbird, Gmail web UI).

When you send from Gmail to a corporate Outlook inbox, you're crossing two MTAs that have never met, authenticated by SPF/DKIM DNS records, spam-filtered, and delivered over IMAP — all transparently.

**Key insight:** Mail delivery is eventually consistent by design. SMTP retries failed deliveries for up to 4-5 days before bouncing.

---

### 3. DNS Server

DNS is the phone book of the internet. Without it, every application would hardcode IP addresses — brittle, unmaintainable, unscalable.

**Hierarchy:**

```
Root Servers (13 clusters globally)
    │
TLD Servers (.com, .org, .io)
    │
Authoritative Name Servers  ← you configure these (Route 53, Cloudflare DNS)
    │
Recursive Resolvers          ← your ISP or 8.8.8.8 queries on your behalf
    │
Client DNS Cache / OS Cache
```

**Resolution walk for `api.example.com`:**
1. Client checks local cache → miss
2. Asks recursive resolver (e.g., 8.8.8.8)
3. Resolver asks root: "who handles `.com`?" → gets TLD server address
4. Resolver asks TLD: "who handles `example.com`?" → gets authoritative NS address
5. Resolver asks authoritative NS: "what's the A record for `api.example.com`?" → returns IP
6. Resolver caches result for TTL seconds; client gets IP

**TTL is a levers**: Low TTL (60s) lets you cut over quickly during incidents. High TTL (86400s) reduces resolver load and speeds up repeat lookups. Choose deliberately.

---

### 4. Proxy Server

Two subtypes with completely different trust models:

| | Forward Proxy | Reverse Proxy |
|---|---|---|
| **Sits between** | Clients and the internet | The internet and backend servers |
| **Who configures it** | The client / corporate IT | The server operator |
| **Hides** | Client identity from servers | Server identity/count from clients |
| **Use cases** | Content filtering, anonymization, corp egress | Load balancing, TLS termination, caching, WAF |
| **Examples** | Squid, corporate firewalls | Nginx, HAProxy, AWS ALB, Cloudflare |

A reverse proxy is the cornerstone of horizontal scaling: clients talk to one address; the proxy fans requests across N backend instances transparently.

---

### 5. FTP Server

FTP (File Transfer Protocol) was designed in 1971 for reliable, bulk file transfer between machines. It predates the web.

**Why it still exists:**
- Batch file ingestion pipelines (banking, EDI, legacy ERP)
- Large binary upload workflows where HTTP multipart is awkward
- Managed file transfer (MFT) compliance requirements

**Protocol variants:**

| Variant | Port | Encryption | Notes |
|---------|------|-----------|-------|
| FTP | 21 | None (plaintext) | Never use on public internet |
| FTPS | 21 / 990 | TLS (explicit/implicit) | FTP + TLS wrapper |
| SFTP | 22 | SSH (always) | Different protocol entirely; most common today |

**Key gotcha:** FTP uses two channels — a control channel (port 21) and a data channel (ephemeral port). This breaks NAT and firewalls unless passive mode or special handling is configured.

For new systems, prefer **SFTP** or **S3-compatible object storage with pre-signed URLs** over plain FTP entirely.

---

### 6. Origin Server

The origin server holds the **single authoritative copy** of content. CDN edge nodes cache copies, but when the cache misses or the TTL expires, edge nodes fetch from the origin.

```
User (Tokyo) → CDN Edge (Tokyo) ──cache hit──▶ Response
                                 ──cache miss─▶ Origin Server (US-East) → Response
                                                        │
                                               CDN caches it for next request
```

**Why "origin" matters as a distinct concept:**
- Origin servers must be protected from direct public access — if your CDN URL is `assets.example.com` but the origin is `origin.example.com` and both are public, adversaries can bypass your CDN (and your WAF, rate limits, and DDoS protection) entirely.
- Origin health directly determines CDN cache-fill latency; an overloaded origin makes the entire CDN feel slow during cache cold starts.

Popular origins: **S3** (static), **EC2 / ECS / Lambda** behind an ALB (dynamic), **GCS**, **Azure Blob Storage**.

---

## Build It / In Depth

### Worked Example: Designing the Video Platform

**Scenario:** 1 million users/day upload and stream short videos. Notifications sent on comments.

**Step 1 — Map responsibilities to server types:**

```
User Upload Flow:
  Browser → [DNS] → [Proxy/LB] → [Web Server (Nginx)] → [Origin Server (S3)]

Stream / Playback:
  Browser → [DNS] → [CDN Edge (CloudFront)] → [Origin (S3)] on miss

Notification:
  Comment service → [Mail Server (SES/Postfix)] → User Inbox (IMAP)

API Calls:
  Mobile App → [DNS] → [Reverse Proxy (HAProxy)] → App Backend (Node.js)
```

**Step 2 — Nginx config sketch for a reverse proxy in front of an app:**

```nginx
upstream app_servers {
    least_conn;
    server 10.0.1.10:3000;
    server 10.0.1.11:3000;
    server 10.0.1.12:3000;
}

server {
    listen 443 ssl;
    server_name api.example.com;

    ssl_certificate     /etc/ssl/certs/example.crt;
    ssl_certificate_key /etc/ssl/private/example.key;

    location / {
        proxy_pass         http://app_servers;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_connect_timeout 5s;
        proxy_read_timeout    30s;
    }

    location /static/ {
        root /var/www;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

Nginx terminates TLS, forwards `X-Real-IP` so the app sees the real client address, serves `/static/` directly without hitting app servers, and load-balances using least-connections across three app instances.

**Step 3 — DNS record setup (Route 53 / Cloudflare syntax):**

```
api.example.com.    60    A     203.0.113.42    ; low TTL for failover agility
assets.example.com. 86400 CNAME d1abc.cloudfront.net.  ; CDN, long TTL fine
mail.example.com.   3600  MX    10 inbound-smtp.us-east-1.amazonaws.com.
```

---

## Use It

| Technology | Server Role | When to Reach for It |
|------------|------------|----------------------|
| **Nginx** | Web + Reverse Proxy | Default choice for reverse proxy, static serving, TLS termination |
| **Caddy** | Web + Reverse Proxy | Automatic HTTPS, simpler config than Nginx; great for smaller teams |
| **HAProxy** | Reverse Proxy / LB | TCP-level load balancing, advanced health checks, high-throughput L4/L7 |
| **AWS ALB** | Reverse Proxy / LB | Managed, path-based routing, native Lambda/ECS targets |
| **Route 53 / Cloudflare DNS** | DNS | Managed authoritative DNS; Route 53 adds latency/failover routing |
| **Amazon SES / Postfix** | Mail | SES for transactional at scale; Postfix for self-hosted pipelines |
| **SFTP (OpenSSH sshd)** | FTP | Secure file ingestion; works through corporate firewalls via port 22 |
| **S3 + CloudFront** | Origin + CDN | Static asset delivery at global scale with near-zero ops overhead |
| **Squid** | Forward Proxy | Corporate egress filtering, caching outbound requests |

---

## Common Pitfalls

- **Exposing your origin server's IP address.** Putting your CDN in front of `origin.example.com` but leaving it publicly routable lets anyone bypass it. Lock down your origin's security group/firewall to accept traffic only from CDN IP ranges.

- **Conflating web server with application server.** Nginx is not where your Python or Node.js app runs. It proxies to your app. Running app code inside Nginx (via obscure modules) creates a maintenance and security nightmare; keep the layers separate.

- **Setting DNS TTL too high before a migration.** If you plan to change an IP, lower TTL to 60–300 seconds at least 24 hours before the cut-over (to flush old caches). Changing TTL at the same time as the IP change leaves old resolvers pointing at dead addresses for hours.

- **Using FTP (plaintext) on any internet-facing endpoint.** Credentials transit in the clear. Use SFTP (SSH-based) or pre-signed S3 URLs instead. This is non-negotiable.

- **Treating mail servers as fire-and-forget.** SMTP failures silently queue and retry. If your MTA queue depth grows and you don't monitor it, you'll discover a backlog only when users report missing emails days later. Always monitor queue depth and bounce rates.

---

## Exercises

1. **Easy:** Draw a sequence diagram for the DNS resolution of `www.github.com` from a fresh browser with an empty cache. Label every server type involved and the protocol used at each hop.

2. **Medium:** A startup is running Nginx as a web server on the same instance as their Django app. Traffic is growing. Propose a new architecture that separates these roles correctly, adds a CDN for static assets, and uses managed DNS with a low TTL for the API endpoint. Justify each change.

3. **Hard:** Your company's origin server IP leaked in a public GitHub commit three weeks ago. Design a mitigation plan that protects the origin without downtime. Include DNS changes, CDN configuration, firewall rules, and how you'd rotate to a new IP over the following week while keeping traffic flowing.

---

## Key Terms

| Term | What people think | What it actually means |
|------|------------------|------------------------|
| **Web Server** | The machine running your entire backend | The process that handles HTTP connections; separate from your app logic |
| **Origin Server** | Any backend server | Specifically the authoritative source a CDN pulls from when its cache is cold |
| **Reverse Proxy** | A VPN or anonymizer | A server that receives external requests and forwards them to backend servers — it hides backends, not clients |
| **Forward Proxy** | Same as a reverse proxy | A proxy configured on the client side to mediate its outbound requests — hides client identity |
| **DNS TTL** | How long the domain "lasts" | How long resolvers cache the record; controls how fast a DNS change propagates |
| **MTA** | The email server | Specifically the Mail Transfer Agent that routes messages between mail servers via SMTP |
| **SFTP** | Secure FTP (FTP + TLS) | A completely different protocol layered over SSH; not FTP at all |

---

## Further Reading

- [Nginx Documentation — Reverse Proxy Guide](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)
- [RFC 5321 — Simple Mail Transfer Protocol](https://datatracker.ietf.org/doc/html/rfc5321) — the authoritative spec for how email moves between servers
- [AWS — Restricting Access to Your Origin](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html) — how to lock your S3 origin to CloudFront only
- [Cloudflare Learning Center — What is DNS?](https://www.cloudflare.com/learning/dns/what-is-dns/) — best visual walkthrough of the DNS resolution chain
- [SFTP vs FTPS — IBM Developer](https://developer.ibm.com/articles/sftp-vs-ftps/) — clear comparison of the two secure file transfer protocols
