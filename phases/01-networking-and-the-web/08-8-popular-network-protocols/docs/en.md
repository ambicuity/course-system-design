# 8 Popular Network Protocols

> Eight protocols that move data on the modern internet — what each one does, where it fits, and why you should know them.

**Type:** Learn
**Prerequisites:** Basic networking
**Time:** ~20 minutes

---

## The Problem

Every interaction on the internet involves network protocols — rules that define how data moves between systems. Engineers use them daily without thinking: HTTPS, TCP, UDP, DNS, WebSockets. Knowing what each protocol does, where it sits in the stack, and what its trade-offs are is part of the vocabulary of professional engineering.

This lesson walks through eight protocols you will encounter constantly. For each, you get the problem it solves, how it works at a high level, where it shows up, and when to reach for it.

---

## The Concept

### The eight protocols

```
   Layer               Protocol           Use
   ─────────────       ──────────          ────────────────────
   Application         HTTP / HTTPS        Web requests
   Application         SMTP                Email transfer
   Application         WebSocket           Real-time bidirectional
   Transport           TCP                 Reliable, ordered
   Transport           UDP                 Fast, connectionless
   Transport           HTTP/3 (QUIC)       HTTP over UDP, faster
   (Various)           FTP                 File transfers (legacy)
```

The protocols span the OSI/TCP-IP stack. Knowing where each fits makes the rest of networking comprehensible.

---

### 1. FTP (File Transfer Protocol)

**The problem:** transfer files between a client and a server, originally over a network that did not have a generic file-sharing mechanism.

**How it works:** FTP uses two channels — a **control channel** (port 21) for commands and responses, and a **data channel** (port 20 or dynamic) for the actual file transfer.

```
   Client                          Server
     │                                │
     │──── command channel (21) ────►│  "USER alice"
     │◄─── "331 Password required" ──│
     │──── "PASS secret" ───────────►│
     │◄─── "230 Login successful" ───│
     │                                │
     │──── data channel (20/dynamic) ►│  ← file bytes flow
     │◄─────────────────────────────│
```

**Properties:**

- Stateful: the server tracks the client's session
- Uses separate channels, which makes it awkward with firewalls and NAT
- Originally unencrypted; secure variants (FTPS, SFTP) exist but are different protocols
- Largely replaced by HTTP for file transfer; still used for legacy systems

**Where you see it:** legacy file servers, some backup systems, occasional web hosting tools. Most modern systems use HTTPS, S3, or similar object storage instead.

---

### 2. TCP (Transmission Control Protocol)

**The problem:** deliver data reliably and in order between two systems, even when the underlying network is unreliable.

**How it works:** TCP establishes a connection via a three-way handshake, then guarantees delivery through acknowledgments, sequencing, retransmission, and flow control.

```
   Three-way handshake:
   Client                        Server
     │                              │
     │──── SYN (seq=x) ────────────►│  "I want to connect"
     │◄─── SYN + ACK (seq=y, ack=x+1)│  "OK, I accept"
     │──── ACK (seq=x+1, ack=y+1) ─►│  "Confirmed"
     │                              │
     │   Connection established     │
```

After the handshake, every byte is acknowledged. If a packet is lost, it is retransmitted. If packets arrive out of order, they are reordered. If the receiver is overwhelmed, the sender slows down (flow control).

**Properties:**

- **Reliable** — every byte is delivered (or the connection fails)
- **Ordered** — bytes are reassembled in the correct order
- **Connection-oriented** — state is maintained on both ends
- **Slower** than UDP because of the overhead

**Where you see it:** HTTP, HTTPS, SSH, database connections, email — almost every application protocol you care about runs over TCP.

---

### 3. UDP (User Datagram Protocol)

**The problem:** send data with minimal overhead, even at the cost of reliability.

**How it works:** UDP just sends packets (datagrams) without establishing a connection, acknowledging receipt, or retransmitting.

```
   Client                          Server
     │                                │
     │──── datagram ────────────────►│  (no handshake)
     │──── datagram ────────────────►│
     │──── datagram ────────────────►│
     │                                │
   No acknowledgments.
   No retransmissions.
   No ordering guarantees.
   No flow control.
```

**Properties:**

- **Fast** — minimal overhead
- **Connectionless** — no setup, no state
- **Unreliable** — packets can be lost, duplicated, or reordered
- **No flow control** — the sender can overwhelm the receiver

**Where you see it:** DNS, video streaming, VoIP, online gaming, real-time telemetry, HTTP/3 (which runs over UDP). Anywhere low latency matters more than perfect reliability.

---

### 4. HTTP (HyperText Transfer Protocol)

**The problem:** request and receive web resources (HTML, images, JSON, files) between a client and a server.

**How it works:** HTTP is a request-response protocol built on top of TCP. The client sends an HTTP request (method + path + headers + optional body); the server returns a response (status + headers + body).

```
   GET /index.html HTTP/1.1
   Host: example.com
   User-Agent: Mozilla/5.0
   Accept: text/html

   HTTP/1.1 200 OK
   Content-Type: text/html
   Content-Length: 1234

   <html>...</html>
```

**Properties:**

- **Stateless** — each request is independent
- **Text-based** — readable for debugging (though HTTP/2 and HTTP/3 use binary framing)
- **Extensible** — headers for everything
- **Composable** — supports caching, authentication, content negotiation

**Where you see it:** every web request, every API call (REST), every browser-server interaction.

---

### 5. HTTP/3 (QUIC)

**The problem:** HTTP/2 runs over TCP, which suffers from head-of-line blocking: one lost packet delays all subsequent packets, even on independent streams.

**How it works:** HTTP/3 runs over QUIC, a transport protocol built on UDP. QUIC integrates TLS 1.3, supports stream multiplexing without head-of-line blocking, and includes connection migration (a connection survives network changes).

```
   HTTP/1.1: one connection, one request at a time
   HTTP/2:   one connection, multiple streams, but TCP-level HOL blocking
   HTTP/3:   one connection, multiple streams, no TCP-level HOL blocking
             (each stream is independent; lost packets only affect their stream)
```

**Properties:**

- **Faster handshake** — 0-RTT possible with QUIC
- **No head-of-line blocking** — independent streams
- **Connection migration** — survives WiFi → cellular handoff
- **Built-in encryption** — TLS 1.3 is mandatory

**Where you see it:** modern web performance (Cloudflare, Google, Facebook all use HTTP/3); any latency-sensitive web traffic.

---

### 6. HTTPS (Secure HTTP)

**The problem:** HTTP traffic is plaintext — anyone on the network can read it. Sensitive data (passwords, credit cards, session tokens) must be encrypted.

**How it works:** HTTPS is HTTP over TLS (formerly SSL). The client and server perform a TLS handshake to exchange keys, then encrypt all subsequent traffic.

```
   TLS handshake (simplified):
   Client                        Server
     │                              │
     │──── ClientHello ───────────►│  (TLS version, ciphers)
     │◄─── ServerHello + Cert ─────│  (server's certificate)
     │──── Key exchange ──────────►│  (RSA or Diffie-Hellman)
     │◄─── Finished ────────────────│
     │                              │
     │   Encrypted HTTP begins      │
```

**Properties:**

- **Confidentiality** — encrypted, only sender and receiver can read
- **Integrity** — MACs detect tampering
- **Authentication** — server's certificate proves its identity (issued by a trusted CA)
- **Cost** — TLS handshake adds latency (mitigated by TLS 1.3, session resumption, 0-RTT)

**Where you see it:** every public web request, every API call over the internet. There is no longer a defensible reason to run plain HTTP in production.

---

### 7. SMTP (Simple Mail Transfer Protocol)

**The problem:** transfer email from a sender to a recipient, possibly across multiple intermediate servers.

**How it works:** SMTP is a text-based, push protocol. The sending server connects to the receiving server (port 25) and transfers the message along with envelope information.

```
   Sender's SMTP server          Recipient's SMTP server
   (smtp.example.com)            (mail.recipient.com)
     │                              │
     │──── EHLO ──────────────────►│
     │◄─── 250 OK ────────────────│
     │──── MAIL FROM:<alice@...> ─►│
     │◄─── 250 OK ────────────────│
     │──── RCPT TO:<bob@...> ────►│
     │◄─── 250 OK ────────────────│
     │──── DATA ─────────────────►│
     │──── (message body) ────────►│
     │──── . ────────────────────►│
     │◄─── 250 OK ────────────────│
     │──── QUIT ──────────────────►│
```

**Properties:**

- **Text-based** — readable for debugging
- **Push protocol** — sender initiates; no polling
- **Store and forward** — intermediate servers queue messages
- **Plaintext** by default; STARTTLS upgrades to TLS

**Where you see it:** every email sent between organizations. Modern email uses SMTP for transport, IMAP or POP3 for retrieval.

---

### 8. WebSocket

**The problem:** HTTP is request-response. Some applications (chat, live updates, multiplayer games, trading dashboards) need real-time, bidirectional communication without polling.

**How it works:** WebSocket starts as an HTTP request with an `Upgrade: websocket` header. If the server agrees, the connection is upgraded to a full-duplex, persistent TCP connection. Both client and server can send messages at any time.

```
   Client                          Server
     │                                │
     │──── GET /chat HTTP/1.1 ──────►│
     │     Upgrade: websocket        │
     │     Connection: Upgrade       │
     │                                │
     │◄─── 101 Switching Protocols ──│
     │                                │
     │   (TCP connection upgraded;    │
     │    both sides can send        │
     │    messages at any time)      │
     │                                │
     │──── message: "hello" ────────►│
     │◄─── message: "hi back" ───────│
     │──── message: "foo" ─────────►│
     │◄─── message: "bar" ──────────│
```

**Properties:**

- **Full-duplex** — both sides send simultaneously
- **Low latency** — no polling overhead
- **Persistent** — one TCP connection for the lifetime of the session
- **Harder to scale** — long-lived connections don't fit traditional load balancing as easily

**Where you see it:** chat apps, live dashboards, multiplayer games, collaborative tools, real-time notifications, trading platforms.

---

## Build It / In Depth

### The protocols at a glance

| Protocol | Layer | Reliable? | Stateful? | Use |
|---|---|---|---|---|
| FTP | Application | Yes | Yes | Legacy file transfer |
| TCP | Transport | Yes | Yes | Reliable transport for HTTP, SSH, DB |
| UDP | Transport | No | No | DNS, video, real-time, HTTP/3 |
| HTTP | Application | No (built on TCP) | No | Web requests |
| HTTP/3 (QUIC) | Application | Yes (built-in) | Yes | Faster web, no HOL blocking |
| HTTPS | Application | Yes | No | Secure web |
| SMTP | Application | Yes | Yes | Email transfer |
| WebSocket | Application | Yes | Yes | Real-time bidirectional |

---

### Choosing the right protocol

| Need | Use |
|---|---|
| Reliable data transfer | TCP (or HTTP over TCP for web) |
| Low-latency, loss-tolerant (video, gaming) | UDP (or HTTP/3) |
| Web requests | HTTPS (HTTP/3 if you can) |
| File transfer | HTTPS / S3 (not FTP) |
| Email | SMTP (between servers) |
| Real-time updates from server | WebSocket (or Server-Sent Events) |
| DNS lookups | UDP (port 53) |
| Database connections | TCP |

---

### The TCP vs UDP trade-off

```
   TCP: I need every byte, in order, even if it takes a bit longer.
   UDP: I need speed and I'll handle missing data myself.
```

**Real-world examples:**

- **Video streaming (Netflix, YouTube)** — UDP (or HTTP/3). Lost packets are hidden by re-buffering; latency is critical.
- **Voice calls (Zoom, FaceTime)** — UDP. Latency dominates quality; retransmitting a 100ms-old audio frame is useless.
- **DNS** — UDP. Tiny queries; TCP handshake would dominate.
- **Web browsing** — TCP (HTTP, HTTPS). You want every byte of the page.
- **Online gaming** — UDP for game state; TCP for chat.

---

### The evolution toward HTTP/3

```
   HTTP/1.1 (1996):  one request per TCP connection
                      → browsers opened 6 concurrent connections per host
   HTTP/2 (2015):    multiplexing on a single connection
                      → still has TCP-level head-of-line blocking
   HTTP/3 (2022):    multiplexing on QUIC (over UDP)
                      → no TCP-level head-of-line blocking
                      → 0-RTT handshake possible
                      → connection migration (WiFi → cellular)
```

HTTP/3 is increasingly the default for major websites (Google, Cloudflare, Facebook). Most browsers support it. The main remaining challenge is server and middleware support; legacy load balancers and proxies sometimes struggle with UDP.

---

## Use It

### When to use which protocol

| Situation | Protocol |
|---|---|
| Public web API | HTTPS |
| Public website | HTTPS, ideally HTTP/3 |
| Streaming video | HLS or DASH over HTTPS, or WebRTC over UDP |
| Real-time chat / collaboration | WebSocket (or WebRTC for P2P) |
| Voice / video calls | WebRTC (over UDP) or SIP |
| Online gaming | UDP for game state, TCP for chat |
| File upload / download | HTTPS (multipart for large) |
| Email sending | SMTP (or HTTP API like SendGrid) |
| DNS | UDP |
| Internal service-to-service (cloud) | gRPC over HTTP/2, or mTLS |

### Common protocol-related debugging

| Problem | Likely cause |
|---|---|
| Slow first request | TCP / TLS handshake; pre-warm connections |
| Long-tail latency spikes | TCP retransmits; check network quality |
| Sporadic 502 errors | Connection limits; load balancer closing idle connections |
| "WebSocket closed before connection established" | Reverse proxy not configured for Upgrade |
| High packet loss on UDP | Network congestion; switch to TCP or FEC |
| Email marked as spam | SPF / DKIM / DMARC misconfigured |

---

## Common Pitfalls

- **Confusing HTTP/2 with HTTP/3.** They look similar; HTTP/2 still uses TCP; HTTP/3 uses UDP (QUIC). Head-of-line blocking differs.

- **Assuming HTTPS is automatic.** It requires a certificate (Let's Encrypt is free), server configuration, and renewal.

- **Using FTP for new projects.** Use HTTPS, S3, or similar. FTP is legacy for a reason.

- **Building real-time features with HTTP polling.** Use WebSocket or Server-Sent Events. Polling at high frequency wastes resources and adds latency.

- **Confusing SMTP, IMAP, and POP3.** SMTP is for sending; IMAP and POP3 are for retrieving. Email clients use both.

- **Not understanding WebSocket scaling.** Long-lived WebSocket connections are harder to load-balance than HTTP requests. Plan for sticky sessions and connection limits.

- **Ignoring UDP's lack of delivery guarantees.** Your application code must handle lost, duplicated, and reordered packets.

---

## Exercises

1. **Easy** — Pick three of the eight protocols. For each, give a concrete use case and one reason to choose it over the alternatives.

2. **Medium** — A live sports streaming application needs to serve 1M concurrent viewers with sub-second latency. Recommend the protocol stack (transport + application). Justify each choice.

3. **Hard** — Your company is migrating from HTTP/1.1 to HTTP/3. List the operational changes required (server, load balancer, observability). Identify the risks and the rollout strategy.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| TCP | The protocol | Transmission Control Protocol — reliable, ordered, connection-oriented transport |
| UDP | The protocol | User Datagram Protocol — fast, connectionless, unreliable transport |
| HTTP | Web | HyperText Transfer Protocol — request-response application protocol for web |
| HTTPS | Secure web | HTTP over TLS; encrypted, authenticated, integrity-checked |
| TLS | Encryption | Transport Layer Security — the cryptographic protocol that secures HTTPS, SMTP, and other protocols |
| WebSocket | Chat | A protocol that upgrades an HTTP connection to a full-duplex, persistent channel for real-time communication |
| HTTP/2 | Faster HTTP | Multiplexing of multiple HTTP requests on one TCP connection; reduces but does not eliminate head-of-line blocking |
| HTTP/3 | Even faster HTTP | HTTP over QUIC (UDP); eliminates TCP-level head-of-line blocking, supports 0-RTT and connection migration |
| Head-of-line blocking | A queue problem | One slow packet delays all subsequent packets in the same connection; TCP has it, QUIC does not |

---

## Further Reading

- **"High Performance Browser Networking"** — Ilya Grigorik's free online book on HTTP/2, HTTP/3, and web performance: https://hpbn.co/
- **"Computer Networking: A Top-Down Approach"** — Kurose and Ross; the canonical networking textbook: https://www.pearson.com/store/p/computer-networking-a-top-down-approach/
- **MDN Web Docs — HTTP** — the definitive reference for HTTP: https://developer.mozilla.org/en-US/docs/Web/HTTP
- **Cloudflare Learning Center — HTTP/3** — a clear explanation of QUIC and HTTP/3: https://www.cloudflare.com/learning/http3/what-is-http3/
- **RFC 9000 — QUIC** — the formal specification: https://www.rfc-editor.org/rfc/rfc9000.html