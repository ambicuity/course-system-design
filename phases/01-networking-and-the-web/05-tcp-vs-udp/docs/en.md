# TCP vs UDP

> Choose correctness or choose speed — the protocol makes it explicit.

**Type:** Learn
**Prerequisites:** IP Fundamentals, OSI Model, DNS
**Time:** ~25 minutes

---

## The Problem

You are building a multiplayer shooter game. Players send 60 position-update packets per second. Each packet is tiny — a few dozen bytes — and the game client already interpolates between states, so a single dropped frame barely matters. You reach for TCP because you have heard it is "reliable." Immediately your game feels sluggish: when a packet is lost, TCP stalls subsequent packets until a retransmit succeeds. By the time the retransmit arrives the data is stale. Your latency budget is 50 ms; TCP's head-of-line blocking alone blows past that.

Now flip the scenario. You are building a banking API that transfers account balances. You consider UDP because it has lower overhead. One corrupted or silently dropped acknowledgment later, a transaction completes on one side and never registers on the other. You now have a consistency bug that is nearly impossible to reproduce and will show up in your audit log months later.

The choice between TCP and UDP is not cosmetic. It determines whether your system prioritizes data integrity over timeliness or timeliness over completeness. Getting it wrong forces you to either re-implement reliability in userspace (expensive, error-prone) or live with phantom latency in a real-time application. Every serious protocol designer — HTTP, DNS, QUIC, WebRTC — makes this choice deliberately.

---

## The Concept

### The Fundamental Trade-off

TCP and UDP are both transport-layer (Layer 4) protocols that ride on top of IP. IP itself is "best effort" — it drops, reorders, or duplicates packets freely. The two protocols differ in how much structure they add on top.

```
Application
────────────
  TCP / UDP       ← Layer 4: where you choose
────────────
     IP            ← Layer 3: best-effort delivery
────────────
  Ethernet/Wi-Fi   ← Layer 2: physical link
```

| Property                   | TCP                                  | UDP                              |
|----------------------------|--------------------------------------|----------------------------------|
| Connection setup           | 3-way handshake (SYN/SYN-ACK/ACK)   | None — fire and forget           |
| Delivery guarantee         | Yes — retransmits lost segments      | No                               |
| Ordering                   | Guaranteed (sequence numbers)        | Not guaranteed                   |
| Duplicate elimination      | Yes                                  | No                               |
| Flow control               | Yes (receiver window)                | No                               |
| Congestion control         | Yes (AIMD, slow-start, CUBIC, BBR)   | No                               |
| Header overhead            | 20–60 bytes                          | 8 bytes                          |
| Typical latency penalty    | 1–3 RTTs to establish, then ongoing  | Zero setup, each packet is fresh |
| Broadcast / multicast      | No                                   | Yes                              |

### TCP: How It Actually Works

**Connection lifecycle** — three messages before any application data flows:

```
Client                          Server
  |                               |
  |──── SYN (seq=x) ────────────▶|
  |◀─── SYN-ACK (seq=y, ack=x+1)─|
  |──── ACK (ack=y+1) ──────────▶|
  |                               |
  |═══════ Data flows ════════════|
  |                               |
  |──── FIN ────────────────────▶|   four-way teardown
  |◀─── ACK ──────────────────── |
  |◀─── FIN ──────────────────── |
  |──── ACK ────────────────────▶|
```

**Reliability mechanism** — every byte is numbered. The receiver sends acknowledgments (ACKs). If an ACK does not arrive within the retransmit timeout (RTO), the sender re-sends. TCP uses cumulative ACKs and selective ACKs (SACKs) to avoid re-sending already-delivered data.

**Flow control** — the receiver advertises a "receive window" (rwnd) in every ACK, capping how many bytes the sender can have in-flight. This prevents a fast sender from overwhelming a slow receiver.

**Congestion control** — TCP infers network congestion from packet loss and adjusts its "congestion window" (cwnd). Slow-start doubles cwnd each RTT until a loss event; then AIMD (Additive Increase Multiplicative Decrease) or modern algorithms like CUBIC and BBR take over. This is critical for fairness on shared networks but adds latency under loss.

**Head-of-line blocking** — the ordering guarantee means that if packet 5 is lost, packets 6–20 that arrived successfully are buffered and not delivered to the application until packet 5 is retransmitted and received. This is TCP's most significant latency cost.

### UDP: How It Actually Works

UDP adds exactly two things to raw IP:

1. Port numbers (source and destination) — so multiple applications on the same host can share one IP.
2. An optional checksum over the header and payload.

That is all. There is no connection, no ACK, no window, no retransmit, no ordering, no congestion control.

**UDP segment structure:**

```
 0      7 8     15 16    23 24    31
+--------+--------+--------+--------+
|  Source Port   | Dest Port        |
+--------+--------+--------+--------+
|   Length       | Checksum         |
+--------+--------+--------+--------+
|                                   |
|          Data (payload)           |
|                                   |
+-----------------------------------+
```

The 8-byte header is fixed. Compare to TCP's 20-byte minimum (often 32+ with options).

Because UDP has no built-in congestion control, an application sending UDP at full speed on a congested network can crowd out competing TCP flows. This is why most UDP-based protocols (QUIC, WebRTC, DCCP) implement their own congestion control in userspace.

---

## Build It / In Depth

### Seeing the Difference with Python

The two socket patterns below illustrate the handshake difference:

**TCP echo server (connection-oriented):**

```python
import socket

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # SOCK_STREAM = TCP
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("0.0.0.0", 9000))
server.listen(5)

print("TCP server listening on :9000")
while True:
    conn, addr = server.accept()          # blocks until a client completes handshake
    data = conn.recv(4096)
    conn.sendall(data)                    # guaranteed ordered delivery
    conn.close()
```

```python
# TCP client
import socket

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(("127.0.0.1", 9000))     # triggers 3-way handshake
client.sendall(b"hello")
print(client.recv(4096))                 # b'hello'
client.close()
```

**UDP echo server (connectionless):**

```python
import socket

server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)   # SOCK_DGRAM = UDP
server.bind(("0.0.0.0", 9001))

print("UDP server listening on :9001")
while True:
    data, addr = server.recvfrom(4096)   # no accept() — datagrams arrive directly
    server.sendto(data, addr)            # best-effort, no delivery guarantee
```

```python
# UDP client
import socket

client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client.sendto(b"hello", ("127.0.0.1", 9001))   # no connect() needed
data, _ = client.recvfrom(4096)
print(data)                              # b'hello' — if it arrives
```

Notice: the UDP client sends immediately with no prior handshake. If the server is not running, the send silently succeeds from the client's perspective — the packet is gone.

### Measuring Overhead with `tcpdump`

Run a TCP connection and count the setup cost:

```bash
# Terminal 1
sudo tcpdump -i lo -n port 9000

# Terminal 2: run the TCP client above
# You will see: SYN, SYN-ACK, ACK  (setup)
#               PSH+ACK, ACK       (data)
#               FIN, ACK, FIN, ACK (teardown)
# Seven packets for one request-response cycle.

# With UDP on port 9001:
# You will see: one datagram out, one datagram back.
# Two packets for the same cycle.
```

### Decision Procedure

```
Is data loss acceptable?
│
├─ No ──────────────────────────────▶ TCP
│   (financial, file transfer,
│    web pages, email, databases)
│
└─ Yes, within bounds ──────────────▶ Ask next question:
    │
    ├─ Do you need multicast/broadcast? ──▶ UDP
    │
    ├─ Is setup latency painful?          ──▶ UDP + app-layer reliability (QUIC)
    │  (short-lived queries, IoT sensors)
    │
    └─ Real-time with staleness > loss?   ──▶ UDP
       (voice, video, gaming, telemetry)
```

---

## Use It

### Where Each Protocol Appears in Production

| Technology      | Protocol | Why                                                                          |
|-----------------|----------|------------------------------------------------------------------------------|
| HTTP/1.1, HTTP/2 | TCP     | Web pages must arrive complete and in order                                  |
| HTTP/3 (QUIC)   | UDP      | QUIC implements its own reliability + TLS on UDP; eliminates TCP HOL blocking |
| DNS             | UDP      | Query-response fits in one packet; retry is cheap at the app layer           |
| DNS over TCP    | TCP      | Fallback when responses exceed 512 bytes (zone transfers, EDNS)              |
| TLS             | TCP      | Needs reliable stream; DTLS is the UDP counterpart                           |
| WebRTC          | UDP      | Real-time audio/video; SRTP rides on UDP with jitter buffers                 |
| VoIP (SIP/RTP)  | UDP      | Voice is time-sensitive; old frames are worthless                            |
| Multiplayer games | UDP    | Position data is replaced by next update; latency matters more than loss     |
| TFTP            | UDP      | Tiny file transfer in controlled LAN environments                            |
| NFS (v3)        | UDP      | Historically used UDP on trusted LANs; v4 mandates TCP                       |
| SSH, SFTP       | TCP      | Interactive sessions and file integrity require reliability                  |
| SNMP            | UDP      | Monitoring polls are idempotent and stateless                                |
| Video streaming (HLS/DASH) | TCP | Adaptive bitrate over HTTP; buffering masks loss               |
| Video streaming (live, low-latency) | UDP | Jitter-sensitive; SRT, RIST, or WebRTC replace TCP          |

### QUIC: The Modern Answer

QUIC (RFC 9000) is the most important lesson about TCP vs UDP: when TCP's constraints become a bottleneck at scale, engineers build a better transport on top of UDP rather than modifying TCP (which requires OS kernel changes and years of rollout). QUIC gives you:

- Encrypted transport from the first packet (TLS 1.3 integrated)
- 0-RTT connection resumption for known servers
- Independent streams so one lost packet blocks only that stream, not all others
- Connection migration (your IP can change mid-connection; QUIC survives it)

Google has run QUIC in production since 2013. As of 2024, over 60% of Chrome's requests to Google use QUIC. HTTP/3 standardizes this.

---

## Common Pitfalls

- **Using TCP for real-time data and accepting the latency tax.** Video calls over TCP feel sluggish under any loss. Even 0.5% packet loss triggers retransmits that compound with head-of-line blocking. Switch to UDP-based transports (WebRTC, SRT) for anything that must stay live.

- **Using UDP and ignoring congestion control.** Sending UDP at full line rate crushes TCP flows sharing the link. In a data center or public internet context, uncontrolled UDP is a bad neighbor. Implement rate limiting or adopt QUIC/DCCP which include congestion control.

- **Treating UDP's checksum as a reliability mechanism.** The UDP checksum detects corruption but does nothing for loss or reordering. Applications that need exactly-once delivery must implement sequence numbers, ACKs, and duplicate detection themselves. This is harder than it looks — do not roll it from scratch; use an existing library.

- **Forgetting that "connectionless" does not mean "stateless."** Firewalls and NAT gateways track UDP "connections" by source/destination IP+port tuples with a timer (typically 30 seconds). Long-lived UDP applications (VPN, DNS resolvers) must send keepalive packets to keep the mapping alive.

- **Assuming TCP delivery order equals application message boundaries.** TCP is a byte stream, not a message stream. `recv()` can return half a message or two messages concatenated. Always frame messages with a length prefix or delimiter; never assume one `send()` equals one `recv()`.

---

## Exercises

1. **Easy — Protocol matching.** For each application below, identify which protocol you would use and write one sentence explaining why: (a) bulk file sync between two data centers, (b) live GPS position updates from 10,000 delivery trucks to a map dashboard, (c) a password-reset email delivery confirmation.

2. **Medium — Build a reliable layer on UDP.** Extend the UDP echo client/server above to add sequence numbers and retransmit logic. The sender should retransmit a packet if no echo arrives within 200 ms and give up after three attempts. Measure how your implementation performs with `tc netem` packet loss: `sudo tc qdisc add dev lo root netem loss 20%`.

3. **Hard — Analyze QUIC.** Read RFC 9000's section on stream multiplexing (section 2) and compare QUIC's HOL blocking behavior to HTTP/2 over TCP. Under what packet-loss rate does QUIC's per-stream independence begin to provide measurable throughput advantages? Set up a local test environment using `ngtcp2` or `quiche` and measure download times for 10 parallel objects at 0%, 1%, and 5% loss.

---

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|------------------------|
| Reliable | The network guarantees delivery | TCP retransmits until acknowledged; it shifts the retry burden from the app to the OS |
| Connectionless | No state anywhere | No handshake, but firewalls and NAT still maintain per-flow state by IP+port tuple |
| Head-of-line blocking | A TCP bug | A deliberate trade-off: ordered delivery requires buffering out-of-order segments until the gap is filled |
| Congestion control | Slowing down to be polite | An adaptive algorithm that infers available bandwidth to prevent buffer bloat and network collapse |
| Datagram | A UDP packet | A self-contained, independently-routed unit with no relationship to prior or subsequent datagrams |
| 3-way handshake | Unnecessary overhead | The minimum exchange to synchronize initial sequence numbers and confirm bidirectional reachability |
| Flow control | Same as congestion control | Flow control protects the *receiver* from being overwhelmed; congestion control protects the *network* |

---

## Further Reading

- **RFC 793 – Transmission Control Protocol** — the original TCP specification; section 3 (Functional Specification) is the definitive source on sequence numbers, flow control, and the state machine. https://www.rfc-editor.org/rfc/rfc793
- **RFC 768 – User Datagram Protocol** — three pages; worth reading in full to appreciate how minimal UDP is. https://www.rfc-editor.org/rfc/rfc768
- **RFC 9000 – QUIC: A UDP-Based Multiplexed and Secure Transport** — understand why Google moved away from TCP before pushing this to the IETF. https://www.rfc-editor.org/rfc/rfc9000
- **"Computer Networks: A Top-Down Approach" (Kurose & Ross), Chapter 3** — the standard academic treatment of transport-layer protocols, with excellent diagrams of congestion control algorithms.
- **Cloudflare Blog: "HTTP/3: the past, the present, and the future"** — a practitioner-level explanation of how QUIC solves TCP's limitations in a CDN context. https://blog.cloudflare.com/http3-the-past-present-and-future/
