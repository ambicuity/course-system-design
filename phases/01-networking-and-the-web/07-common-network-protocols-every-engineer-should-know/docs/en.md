# Common Network Protocols Every Engineer Should Know

> Protocols are the contracts that make the internet work — know them and you can debug anything.

**Type:** Learn
**Prerequisites:** How the Internet Works, TCP/IP and the OSI Model, DNS Deep Dive
**Time:** ~35 minutes

---

## The Problem

You're on-call at 2 AM. A user reports that your app's real-time dashboard stopped updating, but the REST API still works fine. You SSH into the production box, check the logs, and see nothing obviously broken. The root cause? Your load balancer is stripping WebSocket upgrade headers and silently falling back to HTTP polling — but because you confused WebSocket with HTTP long-polling, your mental model was wrong from the start.

Misunderstanding protocols costs real money. Engineers pick UDP for a financial trading system because "it's faster," then spend weeks firefighting lost order confirmations. They deploy OAuth where OIDC is needed and wonder why they can't get user identities. They configure SMTP for their email system without STARTTLS and ship customer data in plaintext for months.

Protocols are not academic trivia. Every API call, file transfer, login flow, and background job you write sits on top of them. Knowing which protocol does what — and why — lets you design correct systems the first time and diagnose failures quickly when they happen.

---

## The Concept

### The Protocol Stack in One Mental Model

Think of protocols in four functional layers. Lower layers carry bytes; higher layers give those bytes meaning.

```
┌─────────────────────────────────────────────────────────────┐
│  IDENTITY & AUTH      OAuth 2.0 · OpenID Connect            │
│  APPLICATION          HTTP · WebSocket · WebRTC · MQTT      │
│                       SMTP · IMAP · SSH · SFTP · LDAP       │
│  SECURITY             TLS · WireGuard · IPsec               │
│  TRANSPORT            TCP · UDP · QUIC                      │
│  ADDRESSING           DNS · DHCP · NTP                      │
└─────────────────────────────────────────────────────────────┘
```

You pick protocols at each layer based on reliability, latency, ordering, and security requirements. The choices compound: HTTP/3 uses QUIC instead of TCP; QUIC includes TLS 1.3 by design; SSH tunnels can carry arbitrary traffic.

---

### Transport Protocols: TCP vs. UDP vs. QUIC

These three define the fundamental delivery contract.

| Property | TCP | UDP | QUIC |
|---|---|---|---|
| Reliability | Guaranteed (retransmit on loss) | Best-effort | Guaranteed per-stream |
| Ordering | Yes | No | Yes per-stream |
| Congestion control | Yes (cubic, BBR, …) | None built-in | Yes (pluggable) |
| Connection setup | 3-way handshake (~1 RTT) | Stateless | 0-RTT or 1-RTT |
| Head-of-line blocking | Yes (one lost packet stalls all) | No | No (streams independent) |
| Multiplexing | No | No | Yes, built-in |
| Built-in encryption | No | No | Yes (TLS 1.3 mandatory) |
| Common use | Web, databases, file transfer | DNS, video streaming, gaming | HTTP/3, real-time |

**TCP** is the workhorse. Its three-way handshake establishes sequence numbers and window sizes before any data flows. ACKs, retransmits, and flow control mean you never lose bytes — but a single dropped packet stalls the entire connection until it is recovered (head-of-line blocking).

**UDP** skips all that. No handshake, no ordering, no retransmit. It is a thin wrapper around IP datagrams. This makes it fast and simple, but the application must handle loss and ordering if it cares. DNS uses UDP for short queries because a lost packet just means sending another query. Video streaming tolerates a lost frame; it cannot tolerate a stalled stream waiting for a retransmit.

**QUIC** (RFC 9000) is UDP plus everything TCP gives you, redesigned without 30 years of legacy. It multiplexes independent streams so one lost packet only stalls the stream it belongs to, not the entire connection. The handshake includes TLS 1.3, cutting setup to one round-trip (or zero for repeat connections via session resumption). HTTP/3 runs exclusively on QUIC.

---

### HTTP: The Language of the Web

All three HTTP versions share the same semantics (verbs, headers, status codes) but differ in how bytes travel on the wire.

```
HTTP/1.1 — one request per connection (keep-alive reuses, but still serial)
HTTP/2   — binary framing + multiplexed streams over one TCP connection
HTTP/3   — same binary framing + multiplexed streams but over QUIC, not TCP
```

**HTTP/2** solved HTTP/1.1's serial request problem with stream multiplexing — but it still sits on TCP, so a single dropped packet stalls all streams. HTTP/2 also added HPACK header compression and server push.

**HTTP/3** moves to QUIC, eliminating TCP's head-of-line blocking entirely. Adoption crossed 30% of web traffic in 2024. Most modern CDNs and load balancers support it; enabling it is usually a config flag.

---

### WebSocket: Bidirectional Channels

HTTP is request-response. Once the server replies, it is silent until the client speaks again. For dashboards, collaborative editors, or chat, you need the server to push whenever state changes.

WebSocket solves this with a protocol upgrade. The client sends an HTTP `Upgrade: websocket` header; if the server agrees, both sides switch to a persistent, full-duplex TCP connection. From there, either party can send frames at any time.

```
Client → Server:  GET /ws HTTP/1.1
                  Upgrade: websocket
                  Connection: Upgrade
                  Sec-WebSocket-Key: dGhlIHNhbXBsZQ==

Server → Client:  HTTP/1.1 101 Switching Protocols
                  Upgrade: websocket
                  Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
```

After the handshake, both sides send framed messages — text, binary, ping/pong, or close. The connection stays open until explicitly closed.

WebSocket multiplexes poorly: one connection = one logical channel. For true multi-stream bidirectional communication, WebRTC data channels or QUIC streams are better.

---

### TLS: Encryption in Transit

TLS (Transport Layer Security) sits between TCP and application protocols. It provides:
- **Confidentiality** — symmetric encryption (AES-GCM)
- **Integrity** — HMAC ensures bytes were not modified
- **Authentication** — X.509 certificates prove server identity

**TLS 1.3 handshake** (simplified):

```
Client → Server:  ClientHello (supported ciphers, key_share)
Server → Client:  ServerHello (chosen cipher, key_share)
                  Certificate, CertificateVerify, Finished
Client → Server:  Finished
--- encrypted from here ---
```

TLS 1.3 completes in one round-trip (vs. two for TLS 1.2). It removed weak ciphers (RSA key exchange, RC4, MD5) and mandated perfect forward secrecy via ephemeral Diffie-Hellman. Every server you deploy should run TLS 1.3 only. QUIC bundles TLS 1.3 — there is no "QUIC without encryption."

---

### DNS: The Internet's Phone Book

DNS translates `api.example.com` into `93.184.216.34`. It is a distributed, hierarchical key-value store with TTL-based caching.

```
Browser → Resolver:    "What is api.example.com?"
Resolver → Root NS:    "Who handles .com?"
Root NS → Resolver:    "Ask ns1.verisign.com"
Resolver → TLD NS:     "Who handles example.com?"
TLD NS → Resolver:     "Ask ns1.example.com"
Resolver → Auth NS:    "What is api.example.com?"
Auth NS → Resolver:    "93.184.216.34 (A record, TTL 300)"
Resolver → Browser:    "93.184.216.34"
```

This full chain (recursive resolution) happens once; the result is cached for TTL seconds. For system design: set short TTLs (30–60 s) for services you failover frequently; set long TTLs (3600 s) for stable addresses. DNS changes take `TTL × propagation time` to fully roll out.

DNS-over-HTTPS (DoH) and DNS-over-TLS (DoT) encrypt DNS queries, preventing ISP snooping. Cloudflare (1.1.1.1) and Google (8.8.8.8) offer both.

---

### SSH: Secure Remote Access

SSH (port 22) creates an encrypted tunnel to a remote host. It authenticates with either passwords or public/private key pairs (prefer keys — passwords are brute-forceable).

Beyond interactive shells, SSH has three power features:
- **Port forwarding** — `ssh -L 5432:localhost:5432 user@host` tunnels a remote Postgres through an encrypted channel to your local machine
- **SCP/SFTP** — encrypted file transfer layered on SSH
- **Agent forwarding** — chain SSH hops without exposing private keys on intermediate hosts

SFTP is SSH + file transfer semantics. It is the right answer for secure bulk file movement. Do not confuse it with FTPS (FTP over TLS) — SFTP is a completely different protocol and the one you almost always want.

---

### Real-Time Protocols: WebRTC and MQTT

**WebRTC** is a browser API backed by several IETF protocols (ICE, STUN, TURN, DTLS, SRTP). It enables peer-to-peer audio, video, and data directly between browsers — no server in the media path. The signaling to establish the connection (exchanging ICE candidates) goes through your server, but audio/video packets flow peer-to-peer once connected. Use it for video conferencing, screen share, and latency-critical gaming.

**MQTT** (Message Queuing Telemetry Transport) is a publish-subscribe protocol designed for constrained devices and unreliable networks (IoT). Clients publish to topics; a broker (e.g., Mosquitto, AWS IoT Core) fans out to subscribers. QoS levels range from 0 (fire-and-forget) to 2 (exactly-once). MQTT runs over TCP; MQTT over WebSocket lets browsers participate.

---

### Auth Protocols: OAuth 2.0 and OpenID Connect

These are frequently confused. The distinction matters:

| | OAuth 2.0 | OpenID Connect |
|---|---|---|
| Purpose | **Authorization** (access delegation) | **Authentication** (identity) |
| What you get | Access token (opaque or JWT) | ID token (JWT with user claims) |
| Answers | "Can this app read your Drive?" | "Who is this user?" |
| Spec | RFC 6749 | Built on top of OAuth 2.0 |

The Authorization Code flow (with PKCE for public clients) is the recommended OAuth flow for web and mobile apps. It keeps tokens off the URL and prevents code interception attacks.

---

### Infrastructure Protocols: DHCP, NTP, LDAP

**DHCP** (Dynamic Host Configuration Protocol) assigns IP addresses automatically. When a device joins a network, it broadcasts a DHCP Discover; the server responds with an offered IP, subnet mask, gateway, and DNS servers. Lease time matters for system design: short leases (minutes) for dynamic environments, long leases (days) for stable servers.

**NTP** (Network Time Protocol) synchronizes clocks. Distributed systems depend on clock agreement for log correlation, token expiry, and distributed lock timeouts. Without NTP, clocks drift. Kubernetes nodes require clock sync within 500 ms or etcd starts rejecting writes. Use a local NTP pool; PTP (Precision Time Protocol) for sub-microsecond accuracy in trading systems.

**LDAP** (Lightweight Directory Access Protocol) is the standard for enterprise identity directories (Active Directory is LDAP under the hood). Applications query LDAP to look up users, groups, and attributes. For modern systems, LDAP is usually hidden behind SAML or OIDC, but understanding the DN/OU/CN hierarchy helps when debugging corporate SSO.

---

### VPN Protocols: WireGuard vs. IPsec

**WireGuard** is modern, minimal (~4000 lines of code vs. IPsec's hundreds of thousands), and fast. It operates at the kernel level, uses only modern cryptography (ChaCha20, Curve25519), and has a 1-RTT handshake. Site-to-site and client-to-server VPNs on Linux and macOS are increasingly WireGuard-first.

**IPsec** is the enterprise standard, supported everywhere including Cisco, Juniper, and AWS VPN Gateways. It operates in tunnel mode (encrypt entire IP packet, add new IP header) or transport mode (encrypt payload only). More complex to configure than WireGuard, but ubiquitous.

---

## Build It / In Depth

### Tracing a Full Request Through Protocol Layers

Let's trace what actually happens when your browser fetches `https://api.example.com/users`.

**Step 1 — DNS Resolution**
```bash
# dig shows the full resolution chain
dig +trace api.example.com

# Result: A record → 93.184.216.34, TTL 300
```

**Step 2 — TCP Handshake (if HTTP/1.1 or HTTP/2)**
```
Client → Server: SYN (seq=1000)
Server → Client: SYN-ACK (seq=2000, ack=1001)
Client → Server: ACK (ack=2001)
# Connection established. Elapsed: ~1 RTT
```

**Step 3 — TLS 1.3 Handshake**
```
Client → Server: ClientHello (key_share, ciphers)
Server → Client: ServerHello + Certificate + Finished
Client → Server: Finished
# Encrypted channel established. Elapsed: +1 RTT (total 2 RTT from TCP start)
```

With HTTP/3 (QUIC), steps 2 and 3 collapse into a single 1-RTT exchange.

**Step 4 — HTTP/2 Request**
```
HEADERS frame  (stream 1):
  :method = GET
  :path = /users
  :authority = api.example.com
  authorization = Bearer eyJ...

DATA frame (response, stream 1):
  [{"id":1,"name":"Alice"},...]
```

HTTP/2 sends this as binary frames. Multiple requests share the single TCP connection on independent streams.

**Step 5 — WebSocket Upgrade (if real-time needed)**
```python
# Python websockets client
import asyncio, websockets

async def listen():
    async with websockets.connect("wss://api.example.com/ws") as ws:
        await ws.send('{"action":"subscribe","topic":"users"}')
        async for message in ws:
            print(message)  # server pushes updates

asyncio.run(listen())
```

**Step 6 — SSH for ops access**
```bash
# Key-based auth, agent forwarding for hop through bastion
ssh -A -J bastion.example.com ec2-user@10.0.1.45

# Forward remote Postgres to local port
ssh -L 5432:db.internal:5432 ec2-user@bastion.example.com
```

---

### Choosing a Protocol — Decision Procedure

```
Need reliable, ordered delivery?
├── Yes → TCP (or QUIC if you also need low latency / multiplexing)
└── No  → UDP (video streams, DNS, gaming state)

Need the browser involved?
├── Yes, real-time push → WebSocket (or WebRTC for P2P audio/video)
└── Yes, request-response → HTTP/2 (or HTTP/3 if CDN supports it)

Need to secure a tunnel?
├── Modern infra → WireGuard
└── Must interop with enterprise gear → IPsec

Delegating access to a third-party?
├── "Can they do X on behalf of user?" → OAuth 2.0 Authorization Code + PKCE
└── "Who is the user?" → OpenID Connect (OAuth 2.0 + ID token)
```

---

## Use It

| Protocol | Where you see it | When to reach for it |
|---|---|---|
| HTTP/2 | gRPC, all major APIs | Default for server-to-server APIs; browser already negotiates it |
| HTTP/3 / QUIC | Cloudflare, Google, Fastly CDN | High-latency or lossy networks; global user base |
| WebSocket | Slack, Figma, trading UIs | Persistent bidirectional channel from browser to server |
| WebRTC | Zoom, Google Meet, Discord | Peer-to-peer audio/video; data channels for gaming |
| MQTT | AWS IoT, Home Assistant | IoT sensors, constrained devices, pub-sub at edge |
| gRPC (HTTP/2) | Kubernetes, microservices | Strongly typed, streaming, internal service mesh |
| TLS 1.3 | Everywhere | Always. No exceptions. Use Let's Encrypt or ACM. |
| WireGuard | Tailscale, Fly.io private nets | Modern VPN: dev access, site-to-site, zero-trust overlay |
| SSH | Every Linux server, CI runners | Remote admin, port forwarding, key-based auth |
| OAuth + OIDC | Auth0, Cognito, Google Sign-In | User login, third-party API access delegation |
| SMTP + IMAP | SendGrid, Postmark, Gmail | Transactional email (SMTP out); mailbox access (IMAP in) |
| NTP | Every server, Kubernetes node | Clock sync — non-negotiable for distributed systems |

---

## Common Pitfalls

- **Using UDP for "performance" without handling reliability yourself.** UDP has no retransmit. If your protocol requires message delivery guarantees, you must implement them in the application layer. Protocols like QUIC have already done this work — use them instead of reinventing the wheel.

- **Forgetting WebSocket proxy configuration.** Nginx and many load balancers drop the `Upgrade` and `Connection` headers by default. WebSocket connections silently fall back to HTTP or 400 immediately. Add `proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade";` to your Nginx config.

- **Setting DNS TTL too high before a migration.** If your A record has a 24-hour TTL, traffic will still go to the old IP for up to 24 hours after you update DNS. Lower TTLs to 60 seconds a day before any migration, then raise them again after the cutover.

- **Conflating OAuth 2.0 and OpenID Connect.** OAuth access tokens say "what the app can do." They say nothing about who the user is. If you call a `/userinfo` endpoint from an access token to determine identity, you are misusing OAuth. Use OIDC's ID token (with `sub` claim) for authentication.

- **Running old TLS versions.** TLS 1.0 and 1.1 are deprecated and broken. PCI-DSS 3.2+ requires at minimum TLS 1.2. Run TLS 1.3 where possible. Audit with `nmap --script ssl-enum-ciphers -p 443 <host>` or [SSL Labs](https://www.ssllabs.com/ssltest/).

---

## Exercises

1. **Easy** — Use `curl -v https://example.com` to inspect the TLS handshake and HTTP/2 negotiation. Identify: what TLS version was negotiated, what cipher suite was chosen, and which HTTP version the response used. Repeat with `curl --http1.1` to see the difference.

2. **Medium** — Write a minimal WebSocket echo server (Python `websockets` or Node.js `ws`) and a client. Capture the traffic in Wireshark. Observe the HTTP Upgrade handshake, then the framed messages. Now put Nginx in front and break it (forget the Upgrade header), then fix it. Document what you saw at each stage.

3. **Hard** — Design the protocol stack for a multiplayer browser game that needs: (a) sub-100 ms state sync between players, (b) a reliable chat channel, (c) user authentication via Google, and (d) a REST API for game history. Justify each protocol choice, identify where head-of-line blocking could hurt you, and explain how you would handle players behind NATs for the real-time channel.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **TCP** | "Slow but reliable" | Reliable, ordered byte-stream with congestion control; "slow" only relative to UDP on LAN — the real cost is RTT for handshake and HOL blocking |
| **QUIC** | "UDP with reliability bolted on" | A redesigned transport protocol with multiplexed streams, built-in TLS 1.3, and 0-RTT resumption; UDP is just the carrier, not the design |
| **TLS** | "The padlock in the browser" | A cryptographic protocol for confidentiality, integrity, and server authentication; it is also what makes HTTPS different from HTTP |
| **WebSocket** | "A separate protocol from HTTP" | An HTTP upgrade to a full-duplex TCP channel; it starts as HTTP and is carried over the same ports (80/443) |
| **OAuth 2.0** | "The login protocol" | An authorization delegation framework — it lets a user grant an app access to resources without sharing credentials; it does not authenticate the user |
| **DNS TTL** | "How long DNS takes to update" | How long resolvers should cache a record; the actual propagation delay equals the old TTL that was in effect when you made the change |
| **MQTT QoS** | "Message priority level" | Delivery guarantee: 0 = at-most-once (fire-and-forget), 1 = at-least-once (possible duplicates), 2 = exactly-once (heaviest, slowest) |

---

## Further Reading

- **RFC 9000 — QUIC Transport Protocol**: [https://datatracker.ietf.org/doc/html/rfc9000](https://datatracker.ietf.org/doc/html/rfc9000) — the canonical spec; the introduction and §17 (packet formats) are worth reading even if you skip the rest.
- **"HTTP/3 Explained" by Daniel Stenberg**: [https://http3-explained.haxx.se/](https://http3-explained.haxx.se/) — free online book by the curl author; covers QUIC and HTTP/3 thoroughly with context.
- **The WebSocket Protocol — RFC 6455**: [https://datatracker.ietf.org/doc/html/rfc6455](https://datatracker.ietf.org/doc/html/rfc6455) — short and readable; sections 1 and 4 explain the handshake and framing.
- **"High Performance Browser Networking" by Ilya Grigorik (Chapter 2–4)**: [https://hpbn.co/](https://hpbn.co/) — free online; deep dives on TCP, TLS, HTTP/2 with real latency numbers and optimization guidance.
- **WireGuard Whitepaper**: [https://www.wireguard.com/papers/wireguard.pdf](https://www.wireguard.com/papers/wireguard.pdf) — 12 pages; explains the cryptographic model and why it is simpler and faster than IPsec or OpenVPN.
