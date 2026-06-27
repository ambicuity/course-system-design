# How DNS Works

> The internet runs on IP addresses; DNS is what lets humans pretend otherwise.

**Type:** Learn
**Prerequisites:** IP Addresses and Subnets, HTTP Basics
**Time:** ~25 minutes

---

## The Problem

Every network packet on the internet is routed using IP addresses — not human-readable names. When you type `example.com` into your browser, nothing in the TCP/IP stack knows what that string means. Before a single byte of HTTP traffic can flow, your machine needs to resolve that name to an IP address like `172.67.21.11`.

Without DNS, you would need to memorize numeric addresses for every service you use, update those addresses yourself whenever a server moves, and coordinate globally every time a company migrated infrastructure. In practice, this is exactly the problem the internet faced before 1983, when the HOSTS.TXT file maintained by SRI International was the single source of truth for name-to-address mappings — and it was breaking under its own weight.

DNS replaces that single file with a globally distributed, hierarchical, eventually-consistent database. It handles hundreds of billions of queries per day, operates with sub-millisecond latency in the common case (thanks to caching), and supports hundreds of record types. Understanding how it works is essential for diagnosing latency spikes, deploying new services, configuring CDNs, and designing systems that depend on fast, reliable name resolution.

---

## The Concept

### The Hierarchy

DNS is organized as a tree. The root of the tree is a single unnamed node written as `.` (a trailing dot). Below it are the **Top-Level Domains** (TLDs) like `.com`, `.org`, `.io`, and country codes like `.uk`. Below each TLD are the **second-level domains** you register (`example`, `github`, `cloudflare`). Below those are subdomains you control (`api.example.com`, `blog.github.com`).

```
                    . (root)
                   / \
                .com  .io  .org  ...
               /    \
          example  github  ...
             |
            api
```

Each node in the tree is managed by different **authoritative nameservers** — servers that hold the definitive records for a zone. The root zone is managed by IANA and served by 13 root server clusters (A through M, each anycast across hundreds of physical machines). TLD zones are managed by registries (Verisign for `.com`). Your domain's zone is managed by whoever you configure as your nameserver (Cloudflare, Route 53, your own BIND server).

### The Actors

| Actor | Role | Example |
|---|---|---|
| **Stub resolver** | Tiny library inside the OS; just forwards queries | libc `getaddrinfo()` |
| **Recursive resolver** (a.k.a. recursor) | Does the hard work — walks the tree on your behalf | `8.8.8.8`, `1.1.1.1` |
| **Root nameservers** | Know where every TLD's nameservers live | `a.root-servers.net` |
| **TLD nameservers** | Know where each domain's authoritative NS lives | `a.gtld-servers.net` |
| **Authoritative nameserver** | Holds the actual records for your domain | `ns1.cloudflare.com` |

### Recursive vs. Iterative Queries

The **stub resolver** sends a *recursive* query to the recursor: "give me the answer, I'll wait." The **recursor** then fans out *iterative* queries: it asks each server "what do you know?" and follows referrals. This split keeps stub resolvers simple and lets the recursor cache results for many clients.

```
Client        Recursive Resolver       Root NS       .com TLD NS    Auth NS
  |                   |                   |               |              |
  |-- query example.com (recursive) -->|               |              |
  |                   |                   |               |              |
  |                   |--- who handles .com? (iterative)->|              |
  |                   |<-- ns for .com: a.gtld-servers.net|              |
  |                   |                                   |              |
  |                   |--- who handles example.com? -->|              |
  |                   |<-- ns: ns1.cloudflare.com --------|              |
  |                   |                                                  |
  |                   |--- what is the A record for example.com? ---->|
  |                   |<-- 172.67.21.11, TTL 300 ------------------------|
  |                   |
  |<-- 172.67.21.11 --|
```

### DNS Record Types

Every entry stored in a zone file is a **Resource Record (RR)**. The critical ones:

| Record | Purpose | Example |
|---|---|---|
| `A` | Maps hostname → IPv4 address | `example.com. 300 IN A 172.67.21.11` |
| `AAAA` | Maps hostname → IPv6 address | `example.com. 300 IN AAAA 2606:4700::1` |
| `CNAME` | Alias — points one name to another name | `www IN CNAME example.com.` |
| `NS` | Delegates a zone to nameservers | `example.com. IN NS ns1.cloudflare.com.` |
| `MX` | Routes email; priority number breaks ties | `example.com. IN MX 10 mail.example.com.` |
| `TXT` | Free-form text; used for SPF, DKIM, verification | `"v=spf1 include:sendgrid.net ~all"` |
| `SOA` | Zone metadata — serial, refresh, retry, expire | One per zone, mandatory |
| `PTR` | Reverse lookup: IP → hostname | `11.21.67.172.in-addr.arpa. IN PTR example.com.` |

### TTL and Caching

Every DNS record carries a **Time-To-Live (TTL)** measured in seconds. Caching happens at every layer: the authoritative server sets the TTL, the recursor respects it, the OS caches the result, the browser has its own cache.

- A TTL of **300** (5 minutes) means the recursor can serve the record from cache for 5 minutes before re-querying.
- A TTL of **86400** (24 hours) is common for stable records and reduces resolver load dramatically.
- A TTL of **0** forces every query to hit the authoritative server — useful during migrations, expensive at scale.

Lower TTL = faster propagation of changes, but higher query load and latency. Higher TTL = faster lookups from cache, but slower propagation when you change records.

### Negative Caching

When a domain or record does not exist, the resolver caches that *negative answer* for the duration of the SOA's **minimum TTL** (often 300–3600 seconds). This means a mistyped hostname that returns NXDOMAIN will not hammer your nameservers on every retry.

---

## Build It / In Depth

### Step-by-Step: What Actually Happens at `example.com`

**Step 1 — Browser cache check**

The browser maintains its own DNS cache. Chrome's is visible at `chrome://net-internals/#dns`. If the record is there and unexpired, resolution stops immediately.

**Step 2 — OS stub resolver**

The OS calls `getaddrinfo()` in libc. It checks `/etc/hosts` first (hardcoded overrides), then `/etc/nsswitch.conf` to determine the lookup order, then forwards to the configured recursor (usually from DHCP, e.g. `192.168.1.1` for a home router, or `8.8.8.8`/`1.1.1.1` for enterprise/cloud).

**Step 3 — Recursor checks its cache**

The recursor at `8.8.8.8` serves millions of clients. It almost certainly has `.com` TLD NS records cached (TTL 172800 — 2 days). It may also have `example.com`'s NS records cached. It only needs to query what it doesn't have.

**Step 4 — Iterative walk (if cache miss)**

```
1. Ask root (a.root-servers.net): "who handles .com?"
   → REFERRAL: a.gtld-servers.net, b.gtld-servers.net, …

2. Ask .com TLD (a.gtld-servers.net): "who handles example.com?"
   → REFERRAL: ns1.cloudflare.com, ns2.cloudflare.com

3. Ask authoritative (ns1.cloudflare.com): "A record for example.com?"
   → ANSWER: 172.67.21.11, TTL 300
```

**Step 5 — Cache and return**

The recursor stores the A record for 300 seconds and returns it to the stub. The OS stores it. The browser stores it.

**Step 6 — TCP connection begins**

Only now does the browser open a TCP connection to `172.67.21.11:443` and perform the TLS handshake. DNS is completely finished before the HTTP request begins.

### Using `dig` to See This Live

```bash
# Full iterative trace from root servers
dig +trace example.com

# Query a specific record type against a specific nameserver
dig @8.8.8.8 example.com A

# Check TTL on a live record (watch the ;; ANSWER SECTION TTL column)
dig example.com A +noall +answer

# Reverse lookup: IP → hostname
dig -x 172.67.21.11

# Check MX records (email routing)
dig example.com MX +short

# Check NS delegation
dig example.com NS +short
```

A `+trace` output shows every delegation step and which server answered at each stage. This is the single most useful debugging tool you have.

### Zone File Anatomy

```
; Zone: example.com.
$ORIGIN example.com.
$TTL 300

@   IN  SOA  ns1.cloudflare.com. admin.example.com. (
            2024062601  ; serial (date + counter)
            3600        ; refresh: secondaries poll every 1h
            900         ; retry: on failure, retry after 15m
            604800      ; expire: give up after 7 days
            300 )       ; negative TTL

@   IN  NS   ns1.cloudflare.com.
@   IN  NS   ns2.cloudflare.com.

@   IN  A    172.67.21.11
@   IN  AAAA 2606:4700::1

www IN  CNAME @
api IN  A     104.21.43.99

@   IN  MX   10 mail.example.com.
@   IN  TXT  "v=spf1 include:sendgrid.net ~all"
```

`@` is shorthand for the origin (`example.com.`). Trailing dots on FQDNs are mandatory — `ns1.cloudflare.com` without the trailing dot would be interpreted as `ns1.cloudflare.com.example.com.`.

---

## Use It

### Public Recursive Resolvers

| Resolver | IP | Strength |
|---|---|---|
| Google Public DNS | `8.8.8.8`, `8.8.4.4` | Largest anycast footprint; fast globally |
| Cloudflare | `1.1.1.1`, `1.0.0.1` | Privacy-first; fastest avg latency per benchmarks |
| OpenDNS (Cisco) | `208.67.222.222` | Filtering, parental controls, enterprise features |
| Route 53 Resolver | VPC-local `169.254.169.253` | AWS-integrated; resolves private hosted zones |

### Managed DNS Providers (Authoritative)

- **Cloudflare DNS** — Sub-millisecond responses globally, DDoS-resilient, free tier, supports DNSSEC.
- **AWS Route 53** — Native integration with ALB/CloudFront/ECS; health-check-based routing; latency routing; geolocation routing.
- **Google Cloud DNS** — Low-latency globally anycast; good for GKE workloads.
- **NS1** — Advanced traffic steering, filter chains, EDNS-client-subnet support; used by large enterprises.

### DNS in System Design Scenarios

**CDN routing** — CDN providers use DNS to steer users to the nearest edge PoP. When you query `cdn.example.com`, the CDN's nameserver returns different A records based on your resolver's IP. AWS CloudFront and Cloudflare both use this approach.

**Blue/green deployments** — Flip DNS from old IP to new IP. Set a low TTL (60s) before the cutover; restore it after. This is DNS-based blue/green — simpler than load balancer swaps but bounded by TTL propagation time.

**Service discovery (microservices)** — Kubernetes CoreDNS resolves `my-service.my-namespace.svc.cluster.local` to the ClusterIP. Consul DNS does the same in non-Kubernetes environments. DNS becomes the internal service registry.

**Failover** — Route 53 health checks monitor your origin. If it fails, Route 53 swaps the DNS record to a failover target. This is single-digit-minute failover — not instant, but simple and provider-agnostic.

---

## Common Pitfalls

- **Forgetting to lower TTL before a migration.** If your A record has a 24-hour TTL and you change the IP, some resolvers will serve the old address for up to 24 hours. Drop the TTL to 60–300 seconds at least one TTL-window before the change, perform the change, then restore the high TTL afterward.

- **CNAME at the zone apex (root domain).** DNS spec forbids a CNAME at `@` because the apex must also hold NS and SOA records. Many providers work around this with proprietary "ALIAS" or "ANAME" records that flatten at query time — but vanilla DNS has no solution. Pointing `example.com` (not `www.example.com`) to a load balancer hostname requires ALIAS support.

- **Assuming DNS changes are instant.** DNS is eventually consistent. There is no global cache-flush mechanism. Even with TTL=0, some broken resolvers ignore the TTL. Budget 5–10 minutes for low-TTL records and up to 48 hours for high-TTL records when planning cutovers.

- **Overlooking negative caching during debugging.** If you queried a hostname before the record was created and got NXDOMAIN, that negative result is cached for the SOA minimum TTL. `dig` from a different vantage point or wait out the negative TTL rather than assuming the record is missing.

- **Not validating DNSSEC or SPF/DKIM after DNS changes.** After migrating DNS providers or editing TXT records, SPF, DKIM, and DMARC records are easy to corrupt. Always verify email deliverability and run `dig TXT` checks after any DNS migration.

---

## Exercises

1. **Easy** — Use `dig +short example.com A` to find the IP address. Then run `dig +trace example.com A` and count how many DNS servers were queried in the iterative resolution chain. Identify which step returned the final authoritative answer.

2. **Medium** — You are migrating `api.example.com` from server A (`10.0.0.1`) to server B (`10.0.0.2`). The record currently has TTL 86400. Describe the complete migration procedure including timeline, TTL changes, and how you verify full propagation. What tool would you use to query multiple resolvers and confirm the new IP is visible everywhere?

3. **Hard** — Design a multi-region active/active DNS setup for a global SaaS application. Users in Europe should resolve to EU origin servers, users in Asia to APAC origins, and fallback to US-EAST for unknown regions. Address: which DNS routing policy you use (latency vs. geolocation), how health checks integrate, what happens to in-flight sessions if an origin goes down, and what the minimum safe TTL is given your RTO targets.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **DNS propagation** | A global sync process that takes 24–48 hours to "complete" | Old records expiring from caches according to their TTL; there is no active propagation — it is just cache expiry |
| **Authoritative nameserver** | Any DNS server | The server that holds the source-of-truth records for a specific zone; it answers with `AA` (Authoritative Answer) flag set |
| **Recursive resolver** | The same as authoritative | The server that does the iterative walk on your behalf and caches results; typically provided by ISP, Google, or Cloudflare |
| **TTL** | How long until DNS "refreshes" | How long a resolver is allowed to serve a cached record before re-querying the authoritative source |
| **CNAME** | Redirects traffic like an HTTP 301 | A DNS alias — the resolver substitutes the target name and resolves it; no HTTP redirect occurs at the DNS layer |
| **Root nameserver** | A single special server | 13 logical root server identities (A–M), each anycast across hundreds of physical machines globally — ~1,500 instances total |
| **NXDOMAIN** | The domain doesn't exist anywhere | The queried name has no records in the authoritative zone at the time of query; it is also cached (negative caching) |

---

## Further Reading

- [RFC 1034 — Domain Names: Concepts and Facilities](https://www.rfc-editor.org/rfc/rfc1034) — the original DNS specification; Section 3 explains the namespace model, Section 4 explains the resolution algorithm.
- [Cloudflare Learning: What is DNS?](https://www.cloudflare.com/learning/dns/what-is-dns/) — visual, accurate, and kept current; good companion to this lesson.
- [IANA Root Zone Database](https://www.iana.org/domains/root/db) — the authoritative list of every TLD and its associated nameservers.
- [DNS Spy / DNSViz](https://dnsviz.net/) — paste any domain and get a visual graph of the full delegation chain with DNSSEC validation status.
- [Julia Evans — "How DNS Works" zine](https://wizardzines.com/zines/dns/) — concise illustrated reference; excellent for internalizing the mental model quickly.
