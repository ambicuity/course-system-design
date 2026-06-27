# Must-Know Network Protocol Dependencies

> Every protocol you use sits on top of another — knowing the stack tells you exactly where things can break.

**Type:** Learn
**Prerequisites:** IP Addressing and Subnets, TCP vs UDP, The OSI Model
**Time:** ~25 minutes

---

## The Problem

A team deploys a new service and immediately sees sporadic connection failures. The logs show TCP handshakes completing, but `ping` to the same host times out. Someone locks down ICMP on the firewall because "ping is a security risk" — not realising that path MTU discovery depends on ICMP Type 3 (Destination Unreachable) messages. Now packets silently fragment or get dropped. The service works in the office and fails in production behind a corporate firewall that strips ICMP. Nobody connects the dots because the team thinks of protocols as isolated tools rather than a dependency tree.

Protocol dependencies are also what make or break performance decisions. A team picks WebSockets for a live video feed, not knowing that RTP over UDP already exists precisely because video cannot tolerate TCP's head-of-line blocking. Another team tries to deploy TLS on a raw UDP socket and then wonders why their TLS library complains — because TLS (pre-QUIC) expects a reliable ordered byte stream, which only TCP provides.

Understanding which protocols depend on which others — at both the transport and security layers — lets you predict failure modes, configure firewalls correctly, choose the right protocol for the job, and debug incidents without guessing.

---

## The Concept

### The Protocol Dependency Tree

Protocols form a strict dependency tree. An application-layer protocol cannot skip the layers below it. The tree looks like this:

```
Layer 3 — Network (IP)
├── IPv4
│   ├── ICMP        (diagnostics: ping, traceroute, MTU discovery)
│   └── IPsec       (encrypted tunnels — AH + ESP)
└── IPv6
    ├── ICMPv6      (diagnostics + Neighbor Discovery, replaces ARP)
    └── IPsec       (mandatory in spec, often optional in practice)

Layer 4 — Transport
├── TCP  (reliable, ordered, connection-oriented)
│   ├── HTTP/1.1, HTTP/2
│   ├── HTTPS  ──────── (HTTP + TLS over TCP)
│   ├── SSH
│   ├── SMTP / SMTPS
│   ├── IMAP / IMAPS
│   ├── POP3 / POP3S
│   ├── BGP             (routing between ASes)
│   ├── RDP
│   ├── LDAP / LDAPS
│   └── FTP (control channel; data channel can be TCP too)
│
├── UDP  (unreliable, unordered, connectionless)
│   ├── DNS             (queries ≤512 bytes; falls back to TCP for large responses)
│   ├── DHCP
│   ├── NTP
│   ├── SNMP
│   ├── SIP             (VoIP signalling)
│   ├── RTP / RTCP      (media streams)
│   └── QUIC ────────── (HTTP/3 + TLS 1.3 inside a single UDP flow)
│
├── SCTP  (multi-stream, multi-homing; telephony signalling, WebRTC data)
└── DCCP  (congestion-controlled, unreliable; largely academic)

Layer 5–6 — Security Layer
└── TLS 1.2 / 1.3  (sits between TCP and application protocols)
    ├── HTTPS   = HTTP  + TLS + TCP + IP
    ├── SMTPS   = SMTP  + TLS + TCP + IP
    ├── IMAPS   = IMAP  + TLS + TCP + IP
    └── LDAPS   = LDAP  + TLS + TCP + IP

QUIC is different: TLS 1.3 is baked inside QUIC itself (not layered on top of TCP)
    └── HTTP/3  = HTTP  + QUIC(TLS 1.3) + UDP + IP
```

### Why Transport Choice Matters

The core trade-off is between **reliability** and **latency**:

| Property | TCP | UDP |
|---|---|---|
| Delivery guarantee | Yes (retransmit on loss) | No |
| Ordering guarantee | Yes | No |
| Connection setup overhead | 3-way handshake | None |
| Head-of-line blocking | Yes (all streams blocked on one lost packet) | No (per-datagram) |
| Built-in congestion control | Yes (Cubic, BBR, RENO) | Must implement yourself |
| Best for | Web pages, files, email, auth | Video, DNS, game state, VoIP |

This is why DNS uses UDP by default — a single request/response fits in one datagram, so there is nothing to order or retransmit. It falls back to TCP only when responses exceed 512 bytes (e.g., DNSSEC responses with large record sets) or during zone transfers.

### TLS Is Not a Transport Protocol

TLS lives between TCP and the application. It needs TCP because TLS records require a reliable, ordered byte stream to reassemble correctly. You cannot run TLS/1.2 over raw UDP — you would lose record boundaries. This is exactly the problem QUIC solves: it internalises reliability at the stream level and bakes TLS 1.3 in, so individual streams are encrypted and loss in one stream does not block the others.

```
HTTP/2 over TLS over TCP        HTTP/3 over QUIC over UDP
┌───────────────────────────┐   ┌──────────────────────────────┐
│ HTTP/2 (streams 1..N)     │   │ HTTP/3 (streams 1..N)        │
├───────────────────────────┤   ├──────────────────────────────┤
│ TLS 1.2/1.3               │   │ QUIC (TLS 1.3 embedded)      │
├───────────────────────────┤   ├──────────────────────────────┤
│ TCP (one byte stream)     │   │ UDP                          │
├───────────────────────────┤   ├──────────────────────────────┤
│ IP                        │   │ IP                           │
└───────────────────────────┘   └──────────────────────────────┘

Head-of-line blocking at TCP     No HOL blocking — lost packet
layer blocks ALL HTTP/2 streams. affects only its own stream.
```

### ICMP — The Silent Dependency

ICMP (IPv4) and ICMPv6 (IPv6) are not optional niceties. They are hard dependencies for:

- **`ping`** — ICMP Echo Request/Reply (Type 8/0)
- **`traceroute`** — ICMP Time Exceeded (Type 11) returned by routers
- **Path MTU Discovery (PMTUD)** — relies on ICMP Type 3 Code 4 ("Fragmentation Needed") to tell the sender to reduce packet size. If a firewall drops these, TCP sessions silently stall on large transfers.
- **IPv6 Neighbor Discovery** — uses ICMPv6 to replace ARP for address resolution

Blocking all ICMP is a misconfiguration. At minimum, allow ICMP Type 3 and Type 8 inbound and outbound.

---

## Build It / In Depth

### Tracing a Dependency Chain: HTTPS Request End-to-End

When a browser loads `https://example.com`, the dependency chain fires in strict order:

```
1. DNS (UDP/53) → resolve example.com → 93.184.216.34
   If response > 512B, DNS retries over TCP/53.

2. TCP handshake (IP + TCP SYN/SYN-ACK/ACK) to 93.184.216.34:443
   Round-trip required before any data flows.

3. TLS 1.3 handshake (1 RTT with session tickets, 0-RTT on resumption)
   Negotiates cipher suite, exchanges certificates, derives session keys.

4. HTTP/2 request sent over the encrypted TLS record layer.

Total new-connection latency:
  = DNS lookup (if not cached) + TCP RTT + TLS 1-RTT handshake + HTTP RTT
  ≈ 50ms DNS + 50ms TCP SYN + 50ms TLS + 50ms HTTP  (on 50ms base RTT)
  = 4 round trips → ~200ms before first byte of HTML arrives.

With QUIC (HTTP/3):
  = DNS lookup + QUIC 1-RTT (combines transport + TLS) + HTTP RTT
  = ~150ms — saves one round trip on new connections.
  On 0-RTT resumption: ~100ms — request piggybacks on handshake packet.
```

### Verifying Protocol Layers with `curl` and `openssl`

```bash
# Check which TLS version and cipher an HTTPS server negotiates
openssl s_client -connect example.com:443 -tls1_3

# Force HTTP/3 (QUIC) if curl is compiled with HTTP/3 support
curl --http3 https://cloudflare.com -v

# Confirm DNS is falling back to TCP for a large DNSSEC-signed zone
dig +tcp example.com ANY

# Test ICMP PMTUD is working (look for "frag needed" in tracepath)
tracepath -n 8.8.8.8
```

### Protocol Dependency Map for a VoIP Call (SIP + RTP)

```
Call setup:     SIP (UDP/5060 or TCP/5060)
                  └─ Negotiates codec, IP, port via SDP inside SIP INVITE

Media stream:   RTP (UDP, dynamic port negotiated in SDP)
                  └─ Video/audio datagrams, no retransmit — loss → glitch, not stall

Control/stats:  RTCP (UDP, RTP port + 1)
                  └─ Quality reports, jitter, packet loss stats

NAT traversal:  STUN / TURN / ICE (UDP, built on top of UDP)
                  └─ Discovers public IP:port, relays if symmetric NAT
```

Notice that SIP can use either TCP or UDP, but RTP is always UDP. If you configure a firewall to block "all UDP above port 1024", you kill every media stream while SIP signalling still appears to work — a classic debugging trap.

---

## Use It

| Scenario | Protocol Stack | Why |
|---|---|---|
| REST API | HTTP/2 + TLS + TCP | Reliable, ordered; HTTP/2 multiplexes requests |
| File upload to S3 | HTTPS (HTTP/1.1 + TLS + TCP) | Large sequential payload; reliability required |
| Video streaming (HLS) | HTTPS (adaptive segments) | Stateless segments; CDN-friendly |
| Real-time video call | RTP/RTCP over UDP | Latency beats reliability for media |
| DNS resolution | UDP/53 (fallback TCP/53) | Single packet exchange; speed critical |
| Kubernetes pod scheduling | HTTPS to kube-apiserver | REST over TLS |
| BGP between routers | BGP over TCP/179 | Long-lived session; reliability essential |
| QUIC/HTTP/3 (Cloudflare, Google) | HTTP/3 + QUIC + UDP | Eliminates HOL blocking; faster on mobile |
| VPN tunnel | IPsec (ESP over IP) or WireGuard (UDP) | Network-layer encryption |
| LDAP auth (corporate) | LDAP over TCP/389, LDAPS over TCP/636 | Directory queries; TLS for security |

### When to Reach for Each Transport

- **TCP:** Any protocol that needs ordered, lossless delivery — web, email, SSH, file transfer, database connections.
- **UDP:** Any protocol where latency matters more than reliability — DNS, video, game state sync, NTP, monitoring.
- **QUIC:** When you need HTTP/2-style multiplexing without TCP's HOL blocking — target high-packet-loss paths (mobile, satellite).
- **SCTP:** Telephony signalling (SS7 over IP), WebRTC data channels, where you need multi-streaming and multi-homing.

---

## Common Pitfalls

- **Blocking all ICMP at the firewall.** Path MTU Discovery silently breaks. Large TCP payloads stall. Allow ICMP Type 3 (unreachable) and Type 8 (echo) at minimum.

- **Treating DNS as always UDP.** DNS falls back to TCP for responses over 512 bytes (DNSSEC, ANY queries, zone transfers). Firewall rules that block TCP/53 break these cases, causing intermittent resolution failures that are hard to reproduce.

- **Assuming TLS is only for HTTPS.** TLS is used by SMTPS, IMAPS, LDAPS, FTPS, and any TCP-based protocol that needs encryption. When you audit a service's security posture, check every TCP port — not just 443.

- **Deploying QUIC without firewall and middlebox awareness.** Many enterprise firewalls and proxies do not inspect UDP at high ports. QUIC traffic may be silently dropped, causing browsers to fall back to HTTP/2. If QUIC adoption is a goal, UDP/443 must be explicitly permitted end-to-end.

- **Ignoring the handshake cost of TCP+TLS on latency-sensitive paths.** A fresh HTTPS connection costs at minimum 2 RTTs before data flows (1 TCP + 1 TLS 1.3). At 100ms RTT, that is 200ms before the first byte. Use connection pooling, HTTP keep-alive, TLS session resumption, and QUIC's 0-RTT to reduce this.

---

## Exercises

1. **Easy:** Draw (in plain text or on paper) the full protocol dependency chain for an IMAP email client connecting to Gmail with SSL. List every protocol from IP up to IMAP, including the port number at each layer.

2. **Medium:** A SRE reports that `curl https://api.internal` works fine but large file downloads consistently stall at around 1400 bytes. What protocol mechanism is most likely broken, and how would you diagnose and fix it? (Hint: think about ICMP and MTU.)

3. **Hard:** You are designing a multiplayer game that needs to send 60 position updates per second per player. Dropped updates are acceptable; stale updates are not. Design the protocol stack (transport, any framing layer, security). Justify every choice and explain what happens to a TCP-based design under 2% packet loss at 100ms RTT.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **TLS** | "The thing that makes HTTPS secure" | A record-layer protocol that provides encryption, authentication, and integrity for any TCP stream; unrelated to HTTP specifically |
| **QUIC** | "A faster version of TCP" | A transport protocol built on UDP that embeds TLS 1.3, provides stream-level multiplexing, and eliminates TCP's head-of-line blocking |
| **ICMP** | "Optional ping protocol — safe to block" | The control plane of IP; used for diagnostics and Path MTU Discovery; blocking it breaks large TCP transfers silently |
| **DNS over UDP** | "DNS always uses UDP" | DNS defaults to UDP/53 for queries ≤512 bytes but falls back to TCP/53 for large responses and zone transfers |
| **IPsec** | "A VPN protocol" | A suite of IP-layer extensions (AH for authentication, ESP for encryption) that can protect any IP traffic, not just VPN tunnels |
| **RTP** | "The video streaming protocol" | A UDP-based framing protocol for real-time media; it does not guarantee delivery — that is intentional |
| **LDAPS** | "A different directory protocol from LDAP" | LDAP (the same protocol) wrapped in TLS on TCP/636, analogous to how HTTPS is HTTP wrapped in TLS |

---

## Further Reading

- [IANA Service Name and Transport Protocol Port Number Registry](https://www.iana.org/assignments/service-names-port-numbers/service-names-port-numbers.xhtml) — the authoritative list of which application protocols run on which ports and transports.
- [RFC 9000 — QUIC: A UDP-Based Multiplexed and Secure Transport](https://www.rfc-editor.org/rfc/rfc9000) — the QUIC specification; Section 1 is an excellent motivation for why QUIC was designed.
- [RFC 4821 — Packetization Layer Path MTU Discovery](https://www.rfc-editor.org/rfc/rfc4821) — explains why PMTUD matters and how to implement it without relying on ICMP.
- [Cloudflare Learning: What is DNS?](https://www.cloudflare.com/learning/dns/what-is-dns/) — covers the full DNS resolution chain including TCP fallback.
- [High Performance Browser Networking — Ilya Grigorik (O'Reilly)](https://hpbn.co/) — free online; chapters on TCP, TLS, HTTP/2, and QUIC are the best practical treatment of protocol dependency costs for web engineers.
