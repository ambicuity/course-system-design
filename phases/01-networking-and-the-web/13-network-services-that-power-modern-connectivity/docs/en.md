# Network Services That Power Modern Connectivity

> The internet is not a single protocol — it is a stack of specialized services, each solving one small problem so the whole feels seamless.

**Type:** Learn
**Prerequisites:** IP Addresses and Subnetting, How DNS Works, TCP vs. UDP
**Time:** ~35 minutes

---

## The Problem

You deploy a brand-new server. You give it an IP address, open the firewall, and push your app. Thirty seconds later your colleague messages you: "I can't reach it." The hostname doesn't resolve. The time on the server is 47 minutes off, which breaks token validation. The remote shell keeps timing out. No one can log in because LDAP is pointing at the wrong port.

Each of these failures traces to a different foundational network service — not the application layer, not the database, not the load balancer. DNS, NTP, SSH, and LDAP are the invisible scaffolding that every application assumes is already correct. When they work, engineers forget they exist. When they break, everything above them breaks in confusing ways.

The second problem is architectural: as systems grow, these services are not just "nice to configure once." They become reliability surfaces. A single NTP stratum-2 server for a 500-node cluster is a single point of failure. A poorly scoped DHCP lease exhausts address space under a flash-sale traffic surge. Weak SSH key management becomes an audit finding. Understanding what each service does, where it fits in the stack, and what it costs when it fails is prerequisite knowledge for designing anything that runs in production.

---

## The Concept

### Taxonomy: Six Categories of Infrastructure Services

Network services cluster into six functional groups. Each group handles a distinct concern; all of them must be healthy for an application to function.

| Category | Services | Core job |
|---|---|---|
| Naming & Addressing | DNS, DHCP | Turn human-readable names into usable addresses |
| Time | NTP | Keep all clocks synchronized |
| Remote Access | SSH, RDP | Give operators secure shells and desktops |
| Messaging | SMTP (submission) | Move email between clients and servers |
| Web & API Transport | HTTPS, HTTP/3 (QUIC) | Encrypted data delivery over the internet |
| Identity & Access | LDAP/TLS, OAuth 2.0, OIDC | Authenticate users and authorize access |
| Private Networks | WireGuard, IPsec | Encrypted tunnels between sites or devices |

### Naming and Addressing

**DNS (Domain Name System, UDP/TCP 53)**

DNS is a globally distributed, hierarchical key-value store. A resolver walks from root nameservers → TLD nameservers → authoritative nameservers to turn `api.example.com` into `203.0.113.42`. It is recursive (the resolver does the work) and caches at every layer using the TTL embedded in each record.

```
Client → Recursive Resolver → Root NS → .com TLD NS → example.com Auth NS
                   ↑___________________________cached answer (TTL)__________↑
```

Record types that matter in system design:

| Record | Purpose | Example |
|---|---|---|
| A | IPv4 address | `api.example.com → 203.0.113.42` |
| AAAA | IPv6 address | `api.example.com → 2001:db8::1` |
| CNAME | Alias to another name | `www → api.example.com` |
| MX | Mail exchanger | `example.com → mail.example.com (pri 10)` |
| TXT | Arbitrary text (SPF, DKIM, verification) | `"v=spf1 include:…"` |
| SRV | Service discovery (port + weight) | `_https._tcp.example.com` |
| PTR | Reverse lookup (IP → name) | Used by anti-spam and logging |

**DHCP (Dynamic Host Configuration Protocol, UDP 67/68)**

DHCP removes the need to manually configure IP, subnet mask, default gateway, and DNS server on each device. The four-step handshake — Discover, Offer, Request, Acknowledge (DORA) — completes in under a second on a local network.

```
Client          DHCP Server
  |--DISCOVER-->|   (broadcast)
  |<---OFFER----|   (proposed IP + lease time)
  |--REQUEST--->|   (client claims the offer)
  |<---ACK------|   (server confirms)
```

Lease time is a design knob. Short leases (1–4 hours) let you reclaim addresses quickly in dynamic environments (containers, CI runners). Long leases (24 hours) reduce DHCP server load but delay reclamation after a device leaves.

### Time: NTP

**NTP (Network Time Protocol, UDP 123)**

Authentication tokens (JWT, Kerberos), TLS certificates, distributed tracing, and log correlation all assume clocks are close enough to agree. NTP synchronizes clocks hierarchically:

- **Stratum 0:** Atomic clocks, GPS receivers (not on the network)
- **Stratum 1:** Servers connected directly to Stratum 0 hardware
- **Stratum 2:** Servers that sync from Stratum 1 (what most cloud instances use)
- **Stratum 3+:** Downstream clients

Target accuracy on a LAN is sub-millisecond. Over the internet, 1–50 ms is typical. Kerberos and many token systems reject requests where clock skew exceeds 5 minutes.

### Remote Access: SSH and RDP

**SSH (Secure Shell, TCP 22)**

SSH provides an encrypted terminal session, port forwarding, and file transfer (SCP, SFTP) over a single authenticated connection. The handshake:

1. TCP connection established
2. Server sends its host key; client checks it against `~/.ssh/known_hosts`
3. Key exchange (ECDH) produces a symmetric session key
4. Client authenticates via public-key or password
5. Encrypted channel opens

Key pair auth (`-i ~/.ssh/id_ed25519`) is strongly preferred over passwords. Modern deployments layer on top: bastion hosts, SSH certificates signed by a CA, and short-lived ephemeral credentials (e.g., AWS EC2 Instance Connect).

**RDP (Remote Desktop Protocol, TCP 3389)**

RDP streams a full graphical desktop session to Windows (and Linux via xrdp). It is the operational default for Windows Server environments. Exposing port 3389 directly to the internet is a top attack vector; always terminate it behind a VPN or bastion.

### Messaging: SMTP Submission

**SMTP Submission (TCP 587 with STARTTLS, or 465 with TLS)**

SMTP is the protocol that moves email. The submission port (587) is distinct from the relay port (25) — clients authenticate to a mail server on 587; servers relay between each other on 25. A typical outbound email path:

```
Your app  →(587)→  SMTP relay (SendGrid/SES)  →(25)→  Recipient MX  →  Inbox
```

SPF, DKIM, and DMARC records (stored in DNS TXT records) tell the receiving server whether the sending IP is authorized and whether the message signature is valid. Missing these causes deliverability failure.

### Web and API Transport: HTTPS and HTTP/3

**HTTPS = HTTP + TLS (TCP 443)**

TLS negotiates a cipher suite and exchanges certificates before the first byte of HTTP travels. TLS 1.3 (current standard) reduces the handshake to one round trip. The certificate chain establishes trust back to a CA root that the client already trusts.

**HTTP/3 over QUIC (UDP 443)**

QUIC is a transport protocol built on UDP that internalizes multiplexing, congestion control, and encryption (always TLS 1.3). It eliminates head-of-line blocking that plagues HTTP/2 over TCP: losing one UDP packet stalls only the stream it belongs to, not all concurrent streams.

```
HTTP/2 over TCP:    [stream1][stream2][stream3] ← one dropped packet stalls ALL
HTTP/3 over QUIC:   [stream1] [stream2] [stream3] ← each independent
```

### Identity and Access: LDAP, OAuth 2.0, OpenID Connect

**LDAP over TLS (TCP 636 for LDAPS, or 389 + STARTTLS)**

LDAP is a hierarchical directory protocol. In enterprise environments it backs Active Directory (Microsoft) and OpenLDAP. Applications query it to resolve group membership, check credentials, and look up user attributes. The directory tree looks like:

```
dc=example,dc=com
  └── ou=Users
        ├── cn=alice
        └── cn=bob
  └── ou=Groups
        └── cn=engineering
```

Service accounts bind (authenticate) to the LDAP server, then query using filters like `(memberOf=cn=engineering,ou=Groups,dc=example,dc=com)`.

**OAuth 2.0 and OpenID Connect (OIDC)**

OAuth 2.0 is an authorization framework — it delegates access without sharing credentials. OIDC adds an identity layer on top via an ID Token (a signed JWT). The Authorization Code Flow with PKCE is the current best practice for web and mobile apps:

```
User → App → Authorization Server (Google, Okta, Auth0)
                        ↓  (user authenticates)
App  ← Authorization Code ← Auth Server
App  → Auth Server: exchange code for tokens
App  ← Access Token + ID Token
```

The access token is sent to APIs as `Authorization: Bearer <token>`. The ID token is decoded by the client to get user identity claims (name, email, sub).

### Private Networks: WireGuard and IPsec

**WireGuard (UDP, configurable port, default 51820)**

WireGuard is a modern VPN protocol: ~4000 lines of kernel code, fast handshake (1 round trip), and Curve25519 key exchange. It is stateless — peers identify each other by public key, and the tunnel is always on once keys are exchanged. Latency overhead is negligible (5–10 ms in practice).

**IPsec (UDP 500/4500 for IKEv2)**

IPsec is the enterprise standard for site-to-site VPNs (AWS VPN Gateway, Azure VPN, hardware firewalls). It is heavier than WireGuard and more complex to configure but is supported by virtually every network vendor and required in many compliance frameworks (FedRAMP, PCI-DSS zone-to-zone).

---

## Build It / In Depth

### End-to-End: What Happens When You Open `https://api.example.com/data`

Walking through a single HTTPS request reveals how these services compose:

```
1. DHCP (at boot)
   Your laptop received 192.168.1.45/24, gateway 192.168.1.1, DNS 8.8.8.8

2. DNS (milliseconds before TCP)
   Resolver queries 8.8.8.8 → ... → auth NS → returns 203.0.113.42 (TTL 300s)

3. NTP (background, always running)
   Your clock is within 12 ms of UTC — TLS certificate validity check will pass

4. TCP + TLS (HTTPS)
   SYN → SYN-ACK → ACK  [TCP handshake]
   ClientHello → ServerHello + Cert → Finished  [TLS 1.3, 1 RTT]

5. HTTP GET /data
   Server returns 200 OK with JSON payload

6. (If authenticated) OAuth 2.0
   App sent Authorization: Bearer eyJhbGci... acquired earlier from Auth Server

7. (If on corporate network) WireGuard
   Steps 2-6 all traveled inside a WireGuard tunnel to reach the internal API
```

Each service is a prerequisite for the next. If DNS is broken, step 2 fails and you never reach TCP. If NTP is drifted, TLS cert validation may fail or token expiry checks produce false positives.

### Checking Service Health (CLI Quick-Reference)

```bash
# DNS: resolve a name and see which server answered
dig api.example.com +short
dig api.example.com @8.8.8.8 A

# DHCP: renew lease (Linux)
sudo dhclient -v eth0

# NTP: check sync status
timedatectl status
chronyc tracking

# SSH: connect with verbose output to debug handshake
ssh -vvv user@host

# LDAP: query a directory entry
ldapsearch -H ldaps://ldap.example.com -b "dc=example,dc=com" "(uid=alice)"

# WireGuard: view tunnel status
sudo wg show
```

---

## Use It

### When to Reach for Each Service

| Scenario | Services involved | Notes |
|---|---|---|
| New VM joins a dynamic fleet | DHCP, DNS (dynamic updates), NTP | Use cloud DHCP + Route 53/Cloud DNS for auto-registration |
| Engineers need shell access to prod | SSH + bastion or SSM Session Manager | Avoid direct port 22 exposure to the internet |
| SaaS app sends transactional email | SMTP submission via SendGrid/SES | Set SPF, DKIM, DMARC or expect spam-folder delivery |
| Public API with millions of users | HTTPS (TLS 1.3) + CDN + HTTP/3 | Enable QUIC on CDN edge (Cloudflare, Fastly) |
| Enterprise SSO | LDAP/AD + OIDC (Okta, Azure AD) | Use LDAP for group sync; OIDC for app login tokens |
| Remote employee network access | WireGuard (Tailscale) or IPsec | WireGuard for simplicity; IPsec for compliance-heavy environments |
| Site-to-site cloud connectivity | IPsec (AWS VPN Gateway / VPC peering) | BGP over IPsec for dynamic routing |

### Technology Comparison: VPN Protocols

| | WireGuard | OpenVPN | IPsec/IKEv2 |
|---|---|---|---|
| Code size | ~4 000 lines | ~100 000 lines | ~50 000 lines |
| Performance | Excellent | Good | Good |
| Setup complexity | Low | Medium | High |
| NAT traversal | Yes (UDP) | Yes (TCP/UDP) | Yes (UDP 4500) |
| Compliance support | Growing | Broad | Extensive (FIPS etc.) |
| Best for | Dev teams, SMBs, modern stacks | Broad client support | Enterprise/government |

---

## Common Pitfalls

- **Short DNS TTLs during normal operation.** Setting TTLs to 60 seconds "for flexibility" means every client re-queries constantly, adding latency and hammering your authoritative server. Use 300–3600 seconds normally; drop TTLs only 24 hours before a planned migration.

- **Forgetting NTP in containerized or VM environments.** Docker containers inherit the host clock, but freshly provisioned VMs in some environments start with a clock far from UTC. A 5-minute drift causes Kerberos and many JWT libraries to reject tokens silently — the only symptom is auth failures with no error detail.

- **Exposing RDP or SSH directly on public IPs.** Automated scanners attempt brute-force on port 22 and 3389 within minutes of a public IP being allocated. Put these behind a VPN, bastion host, or use provider-native access (AWS SSM, GCP IAP).

- **SMTP without SPF/DKIM/DMARC.** An application that sends email from a bare IP or an unconfigured domain will land in spam or be rejected outright. Verify DNS TXT records before shipping any notification system.

- **Using OAuth 2.0 implicit flow in new applications.** The implicit flow returns access tokens in the URL fragment (visible in browser history, logs, referrer headers). The Authorization Code Flow with PKCE replaced it — all modern auth libraries default to PKCE and implicit is being deprecated by major providers.

---

## Exercises

1. **Easy — DNS record audit.** Pick any public domain you own or use. Run `dig example.com ANY` and identify at least one A record, one MX record, and one TXT record. Explain what each one does and what would break if it were missing.

2. **Medium — Trace a login flow.** Draw a sequence diagram for a web application that uses OIDC (e.g., "Sign in with Google") backed by an internal service that checks group membership via LDAP. Label each network service involved (DNS, HTTPS, OIDC, LDAP/TLS) and identify which step would fail first if the LDAP server were unreachable.

3. **Hard — Design a secure remote-access architecture.** A company has 200 engineers, a Kubernetes cluster on AWS, and a compliance requirement that all access to production must be audited and encrypted. Design a remote-access solution using at minimum three of the services from this lesson (e.g., WireGuard/IPsec, SSH via bastion, LDAP/OIDC for identity). Specify ports, trust boundaries, and how you would detect and alert on unauthorized access attempts.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| DNS TTL | "How long DNS is cached" | The number of seconds a resolver may cache a record before re-querying the authoritative server — you control it per record, not globally |
| DHCP lease | "A permanent IP assignment" | A time-limited loan of an IP address; the client must renew before expiry or lose the address |
| SSH port forwarding | "A VPN-like tunnel" | A TCP proxy that routes a local port through an existing SSH connection to a remote host or beyond — useful but not a replacement for a real VPN |
| OAuth 2.0 | "An authentication protocol" | An authorization delegation framework — it proves what a user consented to share, not who they are; OIDC is the identity layer on top |
| LDAP | "A database" | A hierarchical directory protocol optimized for reads and lookups, not general-purpose transactions; write performance is limited by design |
| QUIC | "HTTP/3" | A transport protocol (like TCP) that runs over UDP with built-in encryption and multiplexing; HTTP/3 is an application protocol that runs on top of QUIC |
| WireGuard | "A VPN app" | A VPN protocol and kernel module; apps like Tailscale and Mullvad are products built on the WireGuard protocol |

---

## Further Reading

- [RFC 1034 / RFC 1035 — Domain Names Concepts and Implementation](https://www.rfc-editor.org/rfc/rfc1035) — the original DNS specifications; still the authoritative source for record types and resolver behavior.
- [RFC 9110 / RFC 9114 — HTTP Semantics and HTTP/3](https://www.rfc-editor.org/rfc/rfc9114) — the IETF standard defining HTTP/3 over QUIC.
- [WireGuard Whitepaper](https://www.wireguard.com/papers/wireguard.pdf) — Jason Donenfeld's original paper; concise, explains the cryptographic model and kernel design clearly.
- [OAuth 2.0 Security Best Current Practice (RFC 9700)](https://www.rfc-editor.org/rfc/rfc9700) — the IETF's living document on what to do and avoid in OAuth 2.0 deployments, including PKCE requirements and implicit flow deprecation.
- [The NTP Pool Project — How It Works](https://www.ntppool.org/en/use.html) — explains stratum hierarchy, how to point servers at the pool, and why you should use at least four NTP sources for redundancy.
