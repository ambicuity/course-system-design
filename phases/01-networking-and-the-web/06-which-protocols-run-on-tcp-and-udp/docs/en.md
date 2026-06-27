# Which Protocols Run on TCP and UDP

> Transport choice is not arbitrary — every protocol sits on TCP or UDP for a precise engineering reason.

**Type:** Learn
**Prerequisites:** How TCP Works, How UDP Works, The OSI Model
**Time:** ~20 minutes

## The Problem

You are designing a video-conferencing feature. You reach for WebSockets because "they feel real-time." A teammate suggests raw UDP. A third person says "just use HTTP." All three options technically transfer bytes — but only one is right, and choosing the wrong one will cost you either latency (TCP head-of-line blocking killing your audio) or reliability (UDP dropping frames your users actually need to see).

The root of every bad transport decision is not knowing which application protocols already solved this problem and which transport they chose. HTTP, SMTP, SSH, DNS, RTP, QUIC — each one made a deliberate choice. Understanding *why* they chose what they chose lets you reuse those decisions correctly instead of reinventing them badly.

Without this map, you also can't debug real incidents. "Users can browse fine but video calls drop constantly" is a firewall or NAT problem that only makes sense once you know that video uses UDP and HTTP uses TCP, and that many corporate firewalls block UDP by default.

## The Concept

### The Two-Layer Mental Model

Every message on the internet stacks two layers:

```
Application Layer  (HTTP, DNS, SMTP, SSH, RTP …)
       │
Transport Layer    (TCP  ──or──  UDP)
       │
Network Layer      (IP)
```

TCP and UDP both ride on IP. The difference is what they add on top of raw IP packets before handing data to the application.

| Property | TCP | UDP |
|---|---|---|
| Connection setup | 3-way handshake (SYN/SYN-ACK/ACK) | None |
| Delivery guarantee | Yes — retransmits lost segments | No — fire and forget |
| Ordering | Yes — sequences every byte | No — packets arrive in any order |
| Flow control | Yes — receiver advertises window size | No |
| Congestion control | Yes — slow start, AIMD | No |
| Overhead per message | ~20-byte header + handshake cost | ~8-byte header, no handshake |
| Latency profile | Higher (ACKs, retransmit on loss) | Lower (no waiting) |

**Implication:** TCP adds guarantees by making the sender wait. UDP keeps the sender moving at the cost of those guarantees. Application protocols choose the transport that fits their tolerance for loss vs. latency.

### Protocols That Run on TCP

```
Client                            Server
  │── SYN ──────────────────────► │  ← TCP handshake
  │◄─ SYN-ACK ───────────────────│
  │── ACK ──────────────────────► │
  │                               │
  │── GET /index.html HTTP/1.1 ─► │  ← HTTP request
  │◄─ 200 OK + body ─────────────│  ← HTTP response
```

**HTTP/1.0 and HTTP/1.1** — One TCP connection per request (1.0) or persistent keep-alive connections with pipelining (1.1). TCP's ordering guarantee is essential: an HTML body corrupted mid-stream would render a broken page.

**HTTPS** — HTTP over TLS, which itself runs over TCP. The TCP handshake completes first, then the TLS handshake (ClientHello, ServerHello, certificate exchange, key agreement), then the encrypted HTTP exchange. TLS 1.3 cut TLS to a 1-RTT handshake; TCP still costs 1 RTT before that.

**SMTP (port 25/587/465)** — Email transfer between mail servers. An email that loses bytes in transit is undeliverable garbage, so TCP's reliability is non-negotiable. SMTP layered STARTTLS on top to add encryption without changing the transport.

**IMAP / POP3** — Email retrieval from a mailbox server. Same reasoning: you cannot afford partial messages.

**SSH (port 22)** — Secure remote shell. SSH implements its own multiplexing of channels, but all of it rides a single TCP connection. Ordering and reliability matter because a scrambled terminal session is unusable.

**FTP (ports 20/21)** — File transfer. Actually uses *two* TCP connections: one control channel (commands) and one data channel (file content). Files must arrive complete and in order.

**MySQL / PostgreSQL wire protocols** — Database query/response over TCP. A query result with missing rows or out-of-order bytes would be silently wrong data, which is worse than a visible error.

**Telnet, IRC, XMPP** — Legacy text-stream protocols. All TCP because their protocol framing assumes a reliable byte stream.

### Protocols That Run on UDP

```
Client                Server
  │── DNS Query ────► │   (one datagram)
  │◄─ DNS Response ── │   (one datagram, no connection)
```

**DNS (port 53)** — Queries and responses fit in a single UDP datagram most of the time (< 512 bytes historically, up to ~4096 bytes with EDNS). The client just retries if no response arrives within a timeout. UDP's low overhead means a DNS server can handle tens of thousands of queries per second per core. Exception: DNS falls back to TCP when a response exceeds the UDP payload limit (zone transfers, large DNSSEC responses).

**DHCP (port 67/68)** — Assigns IP addresses. The client has no IP address yet, so it broadcasts. TCP is impossible without a source IP. UDP broadcast is the only option.

**NTP (port 123)** — Network time protocol. Timestamp exchange is a single UDP packet each direction. Losing one measurement is fine; the algorithm just skips it. Reliability matters less than low jitter.

**SNMP (port 161)** — Network device polling. Lightweight read/write of counters. UDP fits the fire-and-poll model. SNMPv3 added encryption but kept UDP.

**RTP / RTCP** — Real-time Transport Protocol carries audio and video streams. A retransmitted video frame arrives too late to display. Better to skip the frame than stall playback waiting for TCP to recover it. RTCP (the control channel) also uses UDP to report jitter and packet loss back to the sender so it can adapt bitrate.

**QUIC (the transport for HTTP/3)** — QUIC is a general-purpose transport protocol built inside UDP datagrams. It reimplements connection setup (1-RTT, or 0-RTT on resumed sessions), reliability, ordering, and flow control — but per-stream, not per-connection. This breaks TCP's head-of-line blocking: if stream 3 loses a packet, streams 1, 2, and 4 keep flowing. QUIC also embeds TLS 1.3 in the handshake, so the first usable data arrives in 1 RTT (vs 2–3 RTT for TCP+TLS 1.2).

**WebRTC data channels and media** — Browser-to-browser video/audio uses RTP over UDP (SRTP for encrypted). WebRTC data channels use SCTP over DTLS over UDP, giving you ordered/unordered and reliable/unreliable delivery selectable per message.

### The Decision Heuristic

```
Does your app need EVERY byte, in order, reliably?
        │
        ├── YES → TCP (HTTP, SMTP, SSH, DB connections)
        │
        └── NO
              │
              ├── Tiny request/response, retries OK at app layer?
              │         → UDP (DNS, NTP, SNMP)
              │
              ├── Continuous stream, timeliness > completeness?
              │         → UDP + RTP or similar
              │
              └── Need reliability but hate head-of-line blocking?
                        → QUIC over UDP (HTTP/3, custom protocols)
```

## Build It / In Depth

### Confirming Protocol Transport with netstat / ss

Watch which transport a running service uses:

```bash
# Show listening sockets with process names
ss -tulnp

# Example output:
# Netid  State   Recv-Q  Send-Q  Local Address:Port
# tcp    LISTEN  0       128     0.0.0.0:22        # SSH on TCP
# tcp    LISTEN  0       511     0.0.0.0:80        # HTTP on TCP
# tcp    LISTEN  0       511     0.0.0.0:443       # HTTPS on TCP
# udp    UNCONN  0       0       0.0.0.0:53        # DNS on UDP
# udp    UNCONN  0       0       0.0.0.0:123       # NTP on UDP
```

### Capturing DNS (UDP) vs. HTTP (TCP) with tcpdump

```bash
# UDP: DNS query (no connection, single datagrams)
sudo tcpdump -i eth0 -n 'udp port 53' -c 5

# TCP: HTTP connection (SYN, SYN-ACK, ACK, then data)
sudo tcpdump -i eth0 -n 'tcp port 80' -c 10
```

The DNS capture shows isolated datagrams. The HTTP capture shows the three-way handshake followed by PSH/ACK segments — you can see the TCP machinery that HTTP depends on.

### Simulating UDP Packet Loss to Understand the Trade-off

```python
import socket, time, random

def udp_sender(host='127.0.0.1', port=9999, drop_rate=0.3):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for i in range(20):
        if random.random() > drop_rate:          # simulate network loss
            sock.sendto(f"frame-{i}".encode(), (host, port))
        time.sleep(0.05)
    sock.close()

def udp_receiver(port=9999):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', port))
    sock.settimeout(2)
    received = []
    try:
        while True:
            data, _ = sock.recvfrom(1024)
            received.append(data.decode())
    except socket.timeout:
        pass
    print(f"Received {len(received)}/20 frames: {received}")
```

Run both sides and observe: the receiver gets frames out of sequence and with gaps. For video, this is acceptable. For a database query result, it would be catastrophic — which is exactly why the DB wire protocol uses TCP.

### HTTP/3 QUIC Connection vs. HTTP/1.1 TCP Connection

```
HTTP/1.1 over TCP + TLS 1.2 (legacy):

t=0   Client ──SYN──────────────────────► Server
t=1   Client ◄─SYN-ACK─────────────────── Server
t=1   Client ──ACK──────────────────────► Server     (TCP ready, 1 RTT)
t=1   Client ──ClientHello──────────────► Server
t=2   Client ◄─ServerHello+Cert────────── Server
t=2   Client ──KeyExchange──────────────► Server
t=3   Client ◄─Finished─────────────────── Server    (TLS ready, +2 RTT)
t=3   Client ──GET /──────────────────────► Server
t=4   Client ◄─200 OK──────────────────── Server    (data, +1 RTT)
                                                      TOTAL: ~4 RTT

HTTP/3 over QUIC + TLS 1.3 (modern):

t=0   Client ──Initial[TLS ClientHello]──► Server
t=1   Client ◄─Initial[TLS ServerHello]─── Server   (connection + TLS, 1 RTT)
t=1   Client ──HTTP GET (encrypted)──────► Server
t=2   Client ◄─HTTP 200 (encrypted)─────── Server   (data, +1 RTT)
                                                      TOTAL: ~2 RTT (or 0-RTT on resume)
```

QUIC wins by combining the TCP handshake, TLS negotiation, and first request into fewer round trips.

## Use It

| Technology | Protocol | Transport | Why |
|---|---|---|---|
| Chrome / Firefox loading a page | HTTP/1.1 or HTTP/2 | TCP | Reliability required; byte ordering mandatory |
| Chrome / Firefox (modern) | HTTP/3 | UDP via QUIC | Lower latency, no head-of-line blocking |
| Zoom, Google Meet (media) | RTP/SRTP | UDP | Timeliness beats completeness |
| Zoom, Meet (signaling) | HTTPS WebSocket | TCP | Control messages must not be lost |
| Linux `dig` / DNS resolver | DNS | UDP (→ TCP fallback) | Single datagram RTT; retry on timeout |
| `git push` over SSH | SSH | TCP | Binary stream must be intact |
| PostgreSQL client | pq wire protocol | TCP | Queries must return complete, ordered results |
| IoT sensor telemetry (e.g., MQTT-SN) | MQTT-SN | UDP | Low-power devices; occasional loss tolerated |
| AWS Route 53 | DNS | UDP (TCP for DNSSEC/large) | Scale requires stateless UDP |
| Cloudflare's 1.1.1.1 over QUIC | DNS-over-QUIC | UDP | Encrypted DNS with lower overhead than DoT |

**When to use HTTP/2 vs HTTP/3:**
- HTTP/2 is universally supported and sufficient for most web traffic. Reach for HTTP/3 (QUIC) when you see latency-sensitive workloads over lossy networks (mobile, cross-continent), have high connection establishment rates (CDN edge), or are building a new API that controls both client and server.

## Common Pitfalls

- **Assuming UDP means unreliable for your use case.** UDP is unreliable at the transport layer, but application protocols like QUIC, RTP, and game engines build their own selective-reliability on top. Saying "we need reliability, so we must use TCP" ignores this entire class of solutions.

- **Forgetting DNS uses both.** Tools that only open UDP port 53 in firewalls break DNSSEC validation and large zone responses, which fall back to TCP port 53. Both must be open. This quietly breaks DNS for domains with large record sets.

- **Using TCP for real-time media and wondering why audio stutters.** TCP retransmits lost packets. By the time the retransmitted audio frame arrives, it is past its play-out deadline. The buffer either stalls (adds latency) or drops it anyway. You lose on both latency and jitter — use UDP + RTP instead.

- **Misunderstanding QUIC as "just HTTP/3."** QUIC is a general-purpose transport. You can run any application protocol over it. Some teams are already replacing custom TCP-based internal protocols with QUIC to get 0-RTT reconnection, per-stream reliability, and connection migration (your IP changes when switching from WiFi to LTE and the connection survives).

- **Blocking UDP at the corporate firewall and not understanding the consequences.** UDP 53 (DNS), UDP 123 (NTP), UDP 443 (QUIC/HTTP/3), and WebRTC media all use UDP. A firewall that blocks all UDP silently breaks time sync, encrypted DNS, modern web performance, and any video calling that can't fall back to TCP.

## Exercises

1. **Easy** — Run `ss -tulnp` on a Linux machine (or a Docker container). List every listening port and classify each service as TCP or UDP. Explain in one sentence *why* each service chose that transport.

2. **Medium** — Write a minimal Python UDP echo server and client. Then write the equivalent using TCP sockets. Measure the round-trip time for 1,000 single-byte messages on localhost. Document the difference in latency and explain what causes it (hint: TCP ACKs, Nagle's algorithm).

3. **Hard** — Examine an HTTP/3 connection using Wireshark (filter: `quic`). Identify the Initial, Handshake, and 1-RTT QUIC packet types. Map each to its TLS equivalent. Then explain why a QUIC stream that loses a packet does not block other streams on the same connection, while an HTTP/2 stream over TCP does.

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **UDP** | Broken, unreliable, only for games | A minimal transport with no built-in delivery guarantee; reliability is opt-in at the application layer |
| **TCP** | The safe, correct default for everything | A reliable, ordered byte-stream transport whose reliability adds latency via ACKs and retransmits |
| **QUIC** | A new version of TCP | A general-purpose transport protocol built on UDP that reimplements selective reliability, ordering, and encryption per-stream |
| **Port** | Just a number | A 16-bit identifier that combined with IP and transport (TCP or UDP) uniquely identifies a socket endpoint |
| **Head-of-line blocking** | A TCP bug | A fundamental consequence of ordered delivery: one lost packet stalls all subsequent data on the same TCP connection until it is recovered |
| **DTLS** | Obscure, irrelevant | TLS adapted to run over UDP (used by WebRTC); provides encryption without requiring a TCP connection |
| **Fallback to TCP** | Rare edge case | Standard DNS behavior when a UDP response is truncated; commonly triggered by DNSSEC and must be explicitly allowed in firewall rules |

## Further Reading

- [RFC 9000 — QUIC: A UDP-Based Multiplexed and Secure Transport](https://www.rfc-editor.org/rfc/rfc9000) — The authoritative QUIC specification; sections 1–3 give an accessible design rationale.
- [MDN Web Docs — HTTP/3](https://developer.mozilla.org/en-US/docs/Glossary/HTTP_3) — Concise explanation of how HTTP/3 maps onto QUIC and why it outperforms HTTP/2 on lossy networks.
- [Cloudflare Blog — The Road to QUIC](https://blog.cloudflare.com/the-road-to-quic/) — Engineering narrative of deploying QUIC at scale, with real latency improvement data.
- [RFC 1035 — Domain Names: Implementation and Specification](https://www.rfc-editor.org/rfc/rfc1035) — Section 4.2 specifies why DNS uses UDP with TCP fallback and the original 512-byte limit.
- [High Performance Browser Networking — O'Reilly (Grigorik)](https://hpbn.co/) — Free online book; chapters on UDP, TCP, and HTTP cover the trade-offs in depth with real-world measurements.
