# Forward Proxy versus Reverse Proxy

> A forward proxy hides the client; a reverse proxy hides the server — same word, opposite direction of trust.

**Type:** Learn
**Prerequisites:** HTTP fundamentals, Client-Server Architecture, Load Balancing basics
**Time:** ~25 minutes

---

## The Problem

You are configuring NGINX for a fast-growing startup. The backend team asks you to "add a proxy" to improve security. The networking team asks you to "add a proxy" to control what websites employees can visit. Both teams used the same word — but they need completely different things.

Mixing up forward and reverse proxies leads to broken deployments. A team that configures a forward proxy on their origin servers will not get load balancing. A team that sets up a reverse proxy for corporate internet filtering will not get content restriction — it will just add latency. The mismatch between intent and implementation can sit undetected in production for months, silently doing the wrong job.

Understanding the distinction also matters for security posture. Exposing a reverse proxy without knowing what it hides gives false confidence. Using a forward proxy without understanding its visibility to the destination leaks more than engineers expect. The two types carry different threat models, and choosing the wrong one for a use case creates real vulnerabilities.

---

## The Concept

The single question that resolves every confusion: **who is the proxy acting on behalf of?**

- **Forward proxy** — acts on behalf of the **client**. The client explicitly routes its requests through the proxy. The destination server sees the proxy's IP, not the client's.
- **Reverse proxy** — acts on behalf of the **server**. The client sends requests to the proxy not knowing (and not caring) that backend servers exist behind it. The client sees only the proxy's IP.

```
FORWARD PROXY (client-side)

  Client ──► Forward Proxy ──► Internet / Destination Server
   (knows about proxy)             (sees proxy, not client)


REVERSE PROXY (server-side)

  Client ──► Reverse Proxy ──► Backend Server(s)
(sees only proxy)               (hidden from client)
```

### Forward Proxy — How It Works

The client configures its HTTP stack (or OS network settings) to route all requests through the proxy. For HTTP, the client sends a full URL in the request line (`GET http://example.com/path HTTP/1.1`), and the proxy fetches it on the client's behalf. For HTTPS, the client issues a `CONNECT` tunnel request first:

```
Client → Proxy: CONNECT example.com:443 HTTP/1.1
Proxy  → Client: HTTP/1.1 200 Connection Established
Client → Proxy: [TLS handshake directly with example.com]
```

The proxy is opaque to the TLS content but can still enforce policies on which hosts the `CONNECT` tunnel is permitted to.

**What forward proxies give you:**

| Capability | Mechanism |
|---|---|
| Client anonymity | Destination sees proxy IP, not client IP |
| Content filtering | Block or allow requests by hostname/URL pattern |
| Caching | Store popular responses and serve locally |
| Bandwidth control | Rate-limit or shape outbound traffic |
| Audit logging | Log every external request by user/machine |

### Reverse Proxy — How It Works

The DNS for your domain resolves to the reverse proxy's IP. Clients connect to it directly. The proxy then opens a separate upstream connection to a backend server (selected by load-balancing policy or routing rules) and forwards the request. The backend response travels back through the proxy to the client.

```
Client                 Reverse Proxy             Backend Pool
  │                        │                    ┌──────────┐
  │  GET /api/users         │                    │ Server A │
  │ ──────────────────────► │  GET /api/users    │          │
  │                         │ ──────────────────►│          │
  │                         │   200 OK + body    └──────────┘
  │        200 OK + body    │◄──────────────────  Server B
  │◄──────────────────────  │                     Server C
```

**What reverse proxies give you:**

| Capability | Mechanism |
|---|---|
| Load balancing | Distribute requests across a pool of backends |
| SSL/TLS termination | Decrypt at the proxy; backends speak plain HTTP internally |
| DDoS mitigation | Absorb and filter attack traffic before it reaches origin |
| Caching | Cache dynamic responses at the edge |
| Request routing | Route `/api/*` to one service, `/static/*` to another |
| Authentication offloading | Verify JWT or mTLS at the proxy before passing upstream |

### The Key Asymmetry

| Dimension | Forward Proxy | Reverse Proxy |
|---|---|---|
| Who knows it exists | The **client** | Neither party by default |
| Who it protects | The **client** | The **server** |
| Where configuration lives | Client's network/OS/app settings | DNS + server infrastructure |
| Typical deployer | IT/security team, user's device | DevOps, platform engineering |
| Direction of "hiding" | Hides client from server | Hides server from client |

---

## Build It / In Depth

### Configuring NGINX as a Reverse Proxy

This is the most common use case. Install NGINX and configure it as a reverse proxy in front of an application server on port 3000:

```nginx
# /etc/nginx/sites-available/myapp.conf

upstream app_backend {
    least_conn;                  # load-balancing policy
    server 10.0.1.10:3000;
    server 10.0.1.11:3000;
    server 10.0.1.12:3000;
}

server {
    listen 443 ssl;
    server_name api.example.com;

    ssl_certificate     /etc/ssl/certs/api.example.com.crt;
    ssl_certificate_key /etc/ssl/private/api.example.com.key;

    location / {
        proxy_pass         http://app_backend;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

SSL terminates at NGINX. Backends never handle certificates. The `X-Forwarded-For` header carries the original client IP so application logs remain accurate.

### Configuring Squid as a Forward Proxy

Squid is the standard open-source forward proxy. Basic configuration for corporate internet filtering:

```
# /etc/squid/squid.conf

http_port 3128

# ACL: define internal network
acl internal_net src 192.168.0.0/16

# ACL: block social media
acl blocked_sites dstdomain .facebook.com .twitter.com .reddit.com

http_access deny blocked_sites
http_access allow internal_net
http_access deny all
```

Clients point their system proxy settings at `192.168.x.x:3128`. Every outbound HTTP/S request now passes through Squid, which enforces the policy.

### Tracing a Request Through Both (Combined Architecture)

Many production environments use both layers simultaneously:

```
Employee Browser
      │
      │ (configured to use forward proxy)
      ▼
Corporate Forward Proxy (Squid / Zscaler)
      │  enforces policy, logs, caches
      │
      ▼
Public Internet
      │
      ▼
CDN / Reverse Proxy (Cloudflare / NGINX)
      │  TLS termination, DDoS filtering, routing
      │
      ▼
Origin Backend Servers
```

The employee's identity is hidden from the origin. The origin's internal topology is hidden from the employee. Policies are enforced at both edges.

---

## Use It

### Forward Proxy Technologies

| Tool | Best For |
|---|---|
| **Squid** | Corporate networks; URL filtering; caching; mature, widely deployed |
| **Privoxy** | Privacy-focused filtering; ad blocking; runs locally |
| **Tinyproxy** | Lightweight; embedded or small environments |
| **Zscaler / Netskope** | SaaS cloud-delivered secure web gateway (enterprise) |
| **VPN** | Combines tunneling + forward proxy behavior; hides all traffic |

### Reverse Proxy Technologies

| Tool | Best For |
|---|---|
| **NGINX** | High-performance HTTP reverse proxy, TLS termination, static serving |
| **HAProxy** | TCP/HTTP load balancing; extremely low latency; high connection count |
| **Traefik** | Kubernetes-native; auto-discovers services via Docker/K8s labels |
| **Envoy** | Service mesh sidecar; advanced observability; gRPC support |
| **Cloudflare** | Global CDN + reverse proxy + DDoS mitigation at the edge |
| **AWS ALB / NLB** | Managed load balancer in AWS; deep integration with ECS, EKS |
| **AWS API Gateway** | Fully managed reverse proxy for serverless and REST/GraphQL APIs |

**CDNs are reverse proxies.** A CDN like Cloudflare or Fastly sits between the client and your origin server. It caches, accelerates, and protects exactly as a reverse proxy does — just with hundreds of global PoPs.

**API Gateways are specialized reverse proxies.** They add authentication, rate limiting, request transformation, and developer portal features on top of the core proxying function.

---

## Common Pitfalls

- **Forgetting `X-Forwarded-For` on a reverse proxy.** Application logs will show the proxy's IP for every request. Access control rules based on IP will break. Always set this header in the proxy config, and always trust it only from your own proxy's CIDR, not from the open internet.

- **SSL termination in the wrong place.** Terminating TLS at the reverse proxy but also keeping full TLS between the proxy and backend (mTLS) is often needed for compliance. Many engineers terminate at the proxy and assume backend communication is automatically secure — it is only secure if the internal network and backend auth are properly configured.

- **Using a forward proxy when you need a reverse proxy for DDoS protection.** A forward proxy sits client-side; it cannot shield your origin from inbound attacks. Only a reverse proxy positioned in front of your origin can absorb and filter attack traffic before it reaches servers.

- **Caching user-specific content on a reverse proxy.** Reverse proxy caches operate on URL patterns. If two users share a URL but should see different content (based on session cookie or auth), a misconfigured cache will serve one user's private data to another. Always set correct `Vary` headers and never cache `Set-Cookie` responses without care.

- **Assuming the proxy hides everything.** A forward proxy hides the client's IP but does not encrypt content for HTTP destinations — the proxy itself can read it. A reverse proxy hides backend topology but does not prevent application-layer vulnerabilities. Neither is a substitute for proper encryption and application security.

---

## Exercises

1. **Easy.** Draw a network diagram for a company where all 500 employee laptops browse the internet through a forward proxy, and the company's e-commerce site is fronted by a reverse proxy with three backend app servers. Label each component and the direction of each connection.

2. **Medium.** Configure NGINX to act as a reverse proxy for two services: route all requests to `/api/*` to `localhost:4000` and all requests to `/static/*` to `localhost:5000`, with a default fallback. Add `X-Forwarded-For` and `X-Forwarded-Proto` headers. Test with `curl -v`.

3. **Hard.** Design a system where a financial services company must (a) prevent employees from leaking data to personal cloud storage, (b) serve a global API with sub-50ms latency, and (c) absorb volumetric DDoS attacks up to 500 Gbps. Specify exactly which proxy types you would deploy at each layer, the vendors you would choose, and why. Identify what this architecture still cannot protect against.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Forward proxy** | Just a VPN | A proxy the *client* routes traffic through; the server does not know the real client |
| **Reverse proxy** | Same as a load balancer | A proxy that sits in front of servers; load balancing is one feature it may include |
| **SSL termination** | Removes encryption entirely | Ends the TLS session at the proxy; a new connection (encrypted or plain) continues to the backend |
| **X-Forwarded-For** | Automatically trusted | An HTTP header carrying the original client IP; must be explicitly set by the proxy and validated before trusting |
| **Origin server** | Any backend | The actual server holding the authoritative content, as opposed to a cache or proxy in front of it |
| **CDN** | Just a cache | A geographically distributed reverse proxy network; caching is one of its roles |
| **API Gateway** | A fancy router | A specialized reverse proxy with added auth, rate limiting, request transformation, and developer-facing features |

---

## Further Reading

- [NGINX Reverse Proxy Guide](https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy/) — official documentation covering `proxy_pass`, upstream blocks, and header forwarding.
- [Squid Configuration Reference](http://www.squid-cache.org/Doc/config/) — complete reference for ACLs, caching policies, and SSL bumping in Squid.
- [Cloudflare Learning: What is a Reverse Proxy?](https://www.cloudflare.com/learning/cdn/glossary/reverse-proxy/) — accessible conceptual explanation with real-world context.
- [HAProxy Documentation](https://www.haproxy.org/download/2.8/doc/configuration.txt) — in-depth config reference for high-performance TCP/HTTP load balancing.
- [RFC 7239 — Forwarded HTTP Extension](https://datatracker.ietf.org/doc/html/rfc7239) — the standardized replacement for `X-Forwarded-For`, defining the `Forwarded` header syntax and security considerations.
