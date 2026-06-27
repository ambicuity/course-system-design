# 18 Common Ports Worth Knowing

> A port number is the apartment number — the IP address gets the packet to the building, the port gets it to the right tenant.

**Type:** Learn
**Prerequisites:** IP Addresses and Subnets, TCP vs UDP, DNS Fundamentals
**Time:** ~25 minutes

---

## The Problem

You've just deployed a PostgreSQL database on a new cloud VM. Your application can't connect. The VM is reachable (ping works), DNS resolves correctly, and the credentials are right. The issue is a firewall rule that nobody opened for port 5432 — because nobody on the team remembered which port Postgres listens on.

This scenario plays out constantly: an engineer opens port 3360 instead of 3306 and wonders why MySQL is unreachable. Another copies a security group config and accidentally exposes port 23 (Telnet, plaintext, unacceptable) to the public internet. A third debugs an email delivery failure for two hours before realizing the outbound SMTP port 25 is blocked by the cloud provider by default.

Port numbers are the vocabulary of networked systems. You don't need to memorize all 65,535 of them — but you must know the 18 that show up constantly in production, in interviews, and in incident postmortems. Getting them wrong costs hours.

---

## The Concept

### What a Port Actually Is

A port is a 16-bit unsigned integer (0–65535) included in the TCP or UDP header. It lets the operating system demultiplex incoming packets to the correct process. The kernel maintains a socket table keyed on the 5-tuple: `(protocol, src-ip, src-port, dst-ip, dst-port)`. Every active connection is uniquely identified by that tuple.

```
  Client (1.2.3.4)                       Server (5.6.7.8)
  ┌──────────────────┐                   ┌──────────────────┐
  │ src-ip: 1.2.3.4  │                   │ dst-ip: 5.6.7.8  │
  │ src-port: 51234  │  ──────────────►  │ dst-port: 443    │
  └──────────────────┘   TCP segment     └──────────────────┘
      ephemeral port                          well-known port
```

The server listens on a well-known port. The client's OS assigns a random **ephemeral port** (49152–65535 per IANA) for the return path. Multiple simultaneous connections to the same server port are fine because each has a different source port.

### Port Ranges

| Range | Name | Who assigns |
|-------|------|-------------|
| 0 – 1023 | Well-known / system | IANA (requires root on Linux) |
| 1024 – 49151 | Registered | IANA, vendor conventions |
| 49152 – 65535 | Dynamic / ephemeral | OS assigns per connection |

### TCP vs UDP — Which Protocol Matters

Many people treat this as trivia, but it directly affects firewall rules and behavior:

- **TCP** — connection-oriented, reliable, ordered. Requires a 3-way handshake before data flows. Firewall rules that track state (stateful inspection) distinguish established connections from new ones.
- **UDP** — connectionless, fire-and-forget. No handshake. Stateful firewalls have limited ability to enforce session semantics.

DNS famously uses **both**: UDP/53 for normal queries (fast, small), TCP/53 for zone transfers and large responses (DNSSEC, responses > 512 bytes historically, now > ~1232 bytes with EDNS).

### The 18 Ports — Reference Table

| # | Protocol | Port | Transport | Purpose |
|---|----------|------|-----------|---------|
| 1 | FTP | 21 | TCP | File transfer control channel |
| 2 | SSH | 22 | TCP | Encrypted remote shell + SFTP + tunneling |
| 3 | Telnet | 23 | TCP | Plaintext remote terminal (legacy) |
| 4 | SMTP | 25 | TCP | Mail transfer between mail servers |
| 5 | DNS | 53 | UDP/TCP | Name resolution |
| 6 | DHCP Server | 67 | UDP | Server sends IP lease offers |
| 7 | DHCP Client | 68 | UDP | Client sends discovery/requests |
| 8 | HTTP | 80 | TCP | Unencrypted web traffic |
| 9 | POP3 | 110 | TCP | Email retrieval (download and delete model) |
| 10 | NTP | 123 | UDP | Time synchronization |
| 11 | NetBIOS | 139 | TCP | Windows name service / file sharing |
| 12 | IMAP | 143 | TCP | Email retrieval (server-side folder model) |
| 13 | HTTPS | 443 | TCP | TLS-encrypted web traffic |
| 14 | SMB | 445 | TCP | Windows file sharing (direct, no NetBIOS) |
| 15 | Oracle DB | 1521 | TCP | Oracle database listener |
| 16 | MySQL | 3306 | TCP | MySQL / MariaDB database |
| 17 | RDP | 3389 | TCP | Windows Remote Desktop Protocol |
| 18 | PostgreSQL | 5432 | TCP | PostgreSQL database |

### Why These Ports Are "Well-Known"

IANA assigns well-known ports through an RFC process. Services listen on a fixed port so clients can find them without out-of-band negotiation. Before a TLS connection to `api.example.com`, your browser knows to try port 443 because the URL scheme `https` maps to it. Same principle for every entry in the table above.

### Security Tier — Not All Ports Are Equal

```
HIGH RISK (expose to internet with extreme care or never):
  23  Telnet    — plaintext credentials, no integrity
  21  FTP       — plaintext, active mode punches holes in firewalls
  139 NetBIOS   — Windows attack surface (WannaCry, EternalBlue)
  445 SMB       — same; block at internet boundary without exception
  3389 RDP      — brute-forced relentlessly; put behind VPN

MEDIUM RISK (encrypt, authenticate, rate-limit):
  25  SMTP      — spam relay if open relay misconfiguration
  110 POP3      — replaced by IMAPS (993) and POP3S (995)
  143 IMAP      — use IMAPS (993) instead
  3306 MySQL    — never expose directly; use SSH tunnel or private subnet
  5432 PostgreSQL — same
  1521 Oracle   — same

LOW RISK (designed for public exposure):
  80  HTTP      — redirect to HTTPS; keep for HTTP→HTTPS redirect
  443 HTTPS     — public-facing; TLS handles confidentiality
  53  DNS       — public resolvers; rate-limit to block amplification
  22  SSH       — public-facing acceptable; use key auth, disable passwords
  123 NTP       — generally safe; be aware of NTP amplification DDoS
  67/68 DHCP   — LAN only, not internet-facing
```

---

## Build It / In Depth

### Scenario: Hardening a New Linux Server

You've just provisioned an Ubuntu 22.04 VM. Walk through port-by-port decisions.

**Step 1 — See what's listening**

```bash
# Show listening sockets with process name
ss -tlnp
# Or the older classic
netstat -tlnp 2>/dev/null

# Sample output:
# State    Recv-Q  Send-Q  Local Address:Port  Process
# LISTEN   0       128     0.0.0.0:22          sshd
# LISTEN   0       128     0.0.0.0:80          nginx
# LISTEN   0       10      127.0.0.1:5432      postgres
```

Notice Postgres binds to `127.0.0.1:5432` — local only. If it showed `0.0.0.0:5432`, it would be reachable from the network.

**Step 2 — Configure the firewall (ufw example)**

```bash
# Default deny incoming, allow outgoing
ufw default deny incoming
ufw default allow outgoing

# Allow SSH from anywhere (or restrict to your IP range)
ufw allow 22/tcp

# Allow HTTP and HTTPS for a web server
ufw allow 80/tcp
ufw allow 443/tcp

# If this is a mail server
ufw allow 25/tcp    # SMTP inbound from other mail servers
# NOT 110 or 143 — use encrypted variants 995/993 instead

ufw enable
ufw status verbose
```

**Step 3 — Test a specific port from outside**

```bash
# From your local machine — does the port answer?
nc -zv 203.0.113.10 5432
# If connection refused: firewall or nothing listening
# If timeout: firewall silently dropping
# If connected: port is open

# More detail with nmap (requires install)
nmap -p 22,80,443,5432 203.0.113.10
```

**Step 4 — Verify DHCP is only on LAN**

```bash
# DHCP broadcast doesn't cross router boundaries by design
# Verify UDP 67 is not exposed on your public interface
ufw status | grep 67
# Should be empty — DHCP has no business on a cloud VM's public NIC
```

**Step 5 — Check NTP sync status**

```bash
# NTP client sends from ephemeral port to server:123
timedatectl status
chronyc tracking

# Force a sync
chronyc makestep
```

**Firewall rule decision flow:**

```
Is this port used by a public-facing service?
  ├── YES → Open it (80, 443, 22, 53 for DNS servers)
  └── NO  → Is it used internally (db, cache, RDP)?
              ├── YES → Bind to loopback or private NIC only
              │          Use SSH tunnel or VPN for remote access
              └── NO  → Close it and disable the service
```

---

## Use It

### Cloud Provider Defaults

| Cloud | What they block by default | Why |
|-------|---------------------------|-----|
| AWS EC2 | Everything inbound (new security groups deny-all) | Least privilege default |
| GCP Compute | Most ports; allows SSH (22) via IAP tunnel | Zero-trust model |
| Azure VMs | 3389 (RDP) open if you click "allow selected ports" — danger | Legacy wizard option |
| DigitalOcean | No inbound except 22 when you add SSH key | Clean default |

### Service Discovery: Which Port to Open

| Situation | Ports to open |
|-----------|---------------|
| Static website | 80, 443 |
| API server (public) | 443 (redirect 80→443) |
| MySQL on private subnet | None externally; SSH tunnel from bastion |
| Internal Windows file share | 445 only from specific VLANs |
| Self-hosted DNS resolver | 53 UDP+TCP inbound from your networks |
| NTP server | 123 UDP inbound from your networks |

### Tools that Use These Ports Daily

- **`ssh -L 5432:db-host:5432 bastion`** — tunnel Postgres through SSH (port 22) rather than exposing 5432
- **`nginx`** — proxies 443 → application on a high port (8080, 3000, etc.)
- **`certbot`** — needs 80 open briefly for HTTP-01 ACME challenge during TLS cert issuance
- **`nmap -sV -p 1-1024`** — service version scan of well-known range
- **`Wireshark` filter** — `tcp.port == 3306` to isolate MySQL traffic during debugging

---

## Common Pitfalls

- **Typo in the port number.** MySQL is 3306, not 3360. Oracle is 1521, not 1512. IMAP is 143, not 139. Double-check with `ss -tlnp` on the server — don't guess from memory. One transposed digit means a timeout instead of a connection.

- **Exposing databases to `0.0.0.0`.** Default installs of MySQL, Postgres, and Redis sometimes bind to all interfaces. Always verify the bind address and restrict it to `127.0.0.1` or a private subnet IP. A publicly reachable DB port is a critical finding in any security audit.

- **Forgetting that DNS uses both UDP and TCP.** Opening only `udp/53` in a firewall rule breaks DNSSEC validation, zone transfers, and large AAAA record responses. Always pair `udp/53` with `tcp/53`.

- **Leaving Telnet (23) or FTP (21) enabled.** These transmit credentials in plaintext. Every packet on the wire reveals the password. SSH (22) replaced Telnet; SFTP (over SSH) or FTPS replaced FTP. If you see port 23 open on a production server, treat it as a P0 finding.

- **Opening RDP (3389) directly to the internet.** Shodan lists millions of exposed RDP endpoints. Automated credential stuffing and vulnerability scanning hit port 3389 within minutes of exposure. RDP should live behind a VPN or accessed through a jump host over SSH. If you must expose it, enforce NLA, MFA, and account lockout.

---

## Exercises

1. **Easy — Port recall drill.** Without looking at the table, fill in the port number for each: HTTPS, SSH, MySQL, DNS, PostgreSQL, SMTP, RDP. Then check your answers. Which ones did you miss? Repeat until you can do it in under 30 seconds.

2. **Medium — Firewall audit.** Spin up a free-tier cloud VM (AWS, GCP, or Azure). Run `ss -tlnp` and compare the listening ports against the services you actually intended to run. Write a `ufw` or `iptables` ruleset that keeps only necessary ports open and explain each decision.

3. **Hard — Tunnel design.** You have a PostgreSQL database on a private subnet (no public IP). Your team needs query access from developer laptops without a VPN. Design a solution using only SSH (port 22) and describe: the exact `ssh -L` command, the security group rules needed, how you'd rotate access when an engineer leaves, and why this is safer than opening port 5432 directly.

---

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|------------------------|
| **Port** | A physical socket on a server | A 16-bit integer in a TCP/UDP header that identifies a logical endpoint on a host |
| **Well-known port** | Any port you've heard of | Specifically port 0–1023, assigned by IANA and typically requiring root/admin to bind |
| **Ephemeral port** | Any temporary port | The random high-numbered source port (49152–65535) the OS assigns to the client side of a connection |
| **Listening** | The port is "open" | A process has called `bind()` and `listen()` on a socket and is waiting for connections |
| **Firewall rule** | Blocks specific IPs | Matches packets on any combination of protocol, src/dst IP, and src/dst port; stateful firewalls also track connection state |
| **SFTP** | A separate protocol on a different port | SSH File Transfer Protocol running inside an SSH session on port 22 — not related to FTP on port 21 |
| **SMTPS / IMAPS** | Encrypted versions use the same ports | SMTPS runs on 465, IMAPS on 993 — entirely different port assignments from the plaintext originals |

---

## Further Reading

- [IANA Service Name and Transport Protocol Port Number Registry](https://www.iana.org/assignments/service-names-port-numbers/service-names-port-numbers.xhtml) — the authoritative source for every registered port assignment.
- [RFC 6335 — Internet Assigned Numbers Authority (IANA) Procedures for the Management of the Service Name and Transport Protocol Port Number Registry](https://datatracker.ietf.org/doc/html/rfc6335) — explains how ports get assigned and the rationale behind port ranges.
- [nmap.org — Port Scanning Techniques](https://nmap.org/book/man-port-scanning-techniques.html) — the nmap manual covers how port scanning works and what different states (open, closed, filtered) mean in practice.
- [Linux `ss` man page](https://man7.org/linux/man-pages/man8/ss.8.html) — the modern replacement for `netstat`; essential for inspecting sockets on production Linux systems.
- [CIS Benchmarks](https://www.cisecurity.org/cis-benchmarks) — per-OS hardening guides that include specific port and service recommendations; free PDF downloads available after registration.
