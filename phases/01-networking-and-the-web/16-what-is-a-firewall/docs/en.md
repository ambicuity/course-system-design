# What is a Firewall?

> A firewall is a policy-enforcing checkpoint — every packet either has permission to pass or it doesn't.

**Type:** Learn
**Prerequisites:** OSI Model, IP Addresses and Ports, TCP/IP Fundamentals
**Time:** ~25 minutes

---

## The Problem

Imagine you spin up a fresh Linux server on a cloud provider. Within seconds, automated scanners on the internet are probing it — trying port 22 for SSH brute-force, port 3306 for an exposed MySQL instance, port 6379 for an unauthenticated Redis server. This is not hypothetical; it happens in under a minute on any publicly routable IP address.

Without a firewall, every service your server runs is fully reachable by anyone on the internet. You expose your database, your admin panels, your internal APIs. One misconfigured service with a known CVE, and an attacker is in. The blast radius extends to every other service on the same machine and, potentially, your entire internal network.

At the network level the situation is the same. An office network with no perimeter firewall is wide open — internal machines can be reached directly from the internet, and any traffic leaving the network (exfiltration, malware callbacks) goes completely unchecked. A firewall's job is to make access explicit: you define what is allowed; everything else is denied by default.

---

## The Concept

### What a Firewall Does

A firewall sits between two networks (or on a single host) and inspects every packet that crosses the boundary. For each packet it applies an ordered list of **rules**. The first rule that matches determines the fate of the packet: **allow**, **deny** (drop silently), or **reject** (drop and notify the sender). If no rule matches, a **default policy** applies — in a well-configured firewall, that default is deny-all.

The attributes a firewall can inspect depend on which OSI layers it operates at:

| Layer | What's inspectable | Example rule |
|-------|-------------------|--------------|
| 3 (Network) | Source IP, Destination IP, Protocol | Block all traffic from 203.0.113.0/24 |
| 4 (Transport) | TCP/UDP port, TCP flags, connection state | Allow TCP to port 443, deny everything else |
| 7 (Application) | HTTP method, URL path, DNS name, TLS SNI | Block HTTP requests with `User-Agent: sqlmap` |

### Stateless vs. Stateful Firewalls

This is the most important conceptual divide.

**Stateless firewall** — examines each packet in isolation. It does not know whether this packet belongs to an established connection or is unsolicited. Fast, but limited.

**Stateful firewall** — maintains a **connection tracking table**. When TCP handshake (SYN → SYN-ACK → ACK) completes, that session is recorded. Return traffic for established connections is automatically permitted without matching a specific allow rule. This is how nearly all modern firewalls work.

```
Connection tracking table (simplified):

  src_ip        src_port  dst_ip         dst_port  proto  state
  ─────────────────────────────────────────────────────────────
  10.0.0.5      52341     93.184.216.34  443       TCP    ESTABLISHED
  10.0.0.5      52342     8.8.8.8        53        UDP    NEW
  10.0.0.12     61200     172.217.0.46   80        TCP    TIME_WAIT
```

With a stateful firewall you write: "allow outbound TCP to port 443." The return packets (ACK, data, FIN) are allowed automatically because they match an established entry. You do not need a separate inbound rule for each outbound session.

### Two Deployment Models

```
                         INTERNET
                            │
                    ┌───────▼────────┐
                    │ Network Firewall│  ← Perimeter defense
                    │  (Layer 3–4)   │
                    └───────┬────────┘
                            │
              ┌─────────────┴─────────────┐
              │       INTERNAL NETWORK     │
              │                           │
        ┌─────▼─────┐             ┌───────▼─────┐
        │  Web Srv  │             │   DB Srv    │
        │ [host fw] │             │  [host fw]  │  ← Host-based
        └───────────┘             └─────────────┘
```

**Network Firewall (Perimeter)**
- Deployed at the network edge — between your infrastructure and the internet.
- Can be physical hardware (Cisco ASA, Palo Alto), a virtualized appliance (pfSense, FortiGate-VM), or a cloud-native service (AWS Network Firewall, GCP Cloud Armor at L7).
- Protects all devices behind it simultaneously. One rule set governs the entire subnet.
- Operates primarily at Layers 3–4. Next-Generation Firewalls (NGFW) add Layer 7 inspection (DPI, TLS termination).
- First packet in: internet traffic hits this firewall before touching any internal system.

**Host-Based Firewall**
- Software running on the individual machine — `iptables`/`nftables` on Linux, `pf` on macOS/BSD, Windows Defender Firewall.
- Protects that one device only, even from traffic that already crossed the perimeter.
- Operates at Layers 3–7 (can inspect application data, enforce per-process rules).
- Last line of defense. If malware gets inside or an attacker moves laterally from another internal host, the host firewall is still in the way.

The two are **complementary, not alternatives**. Best practice is defense in depth: the perimeter firewall blocks the majority of external attack surface; host firewalls limit what can happen even after an attacker breaches the perimeter.

### Rule Evaluation

Rules are evaluated top-to-bottom in order. The **first match wins** — subsequent rules are not checked. This means:

1. More specific rules go first.
2. Your catch-all "deny everything" rule goes last (or is the default policy).
3. Order bugs are a leading source of misconfigured firewalls.

```
Rule table example (simplified iptables INPUT chain):

 #   Action  Protocol  Src IP         Dst Port  Match?
 ─────────────────────────────────────────────────────
 1   ALLOW   TCP       any            22        SSH admin access
 2   ALLOW   TCP       any            443       HTTPS
 3   ALLOW   TCP       any            80        HTTP
 4   ALLOW   ICMP      10.0.0.0/8     any       Internal ping
 5   DROP    any       any            any       ← Default deny
```

A packet destined for port 8080 hits rule 1 (no match), 2 (no match), 3 (no match), 4 (no match if src is external), 5 (DROP). The packet is silently discarded.

---

## Build It / In Depth

Let's walk through configuring a minimal but realistic firewall using `iptables` — the classic Linux tool that still underlies many container and cloud environments. This makes the abstract rules above concrete.

### Goal

Harden a web server that should:
- Accept inbound HTTPS (443) and HTTP (80) from anywhere.
- Accept inbound SSH (22) from a single admin IP only.
- Accept ICMP from the internal network (10.0.0.0/8).
- Allow all outbound traffic (so the server can fetch updates, call APIs).
- Drop everything else inbound.

### Step 1 — Flush existing rules and set default policies

```bash
# Clear all existing rules
iptables -F
iptables -X

# Default policy: block everything coming in, allow everything going out
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT ACCEPT
```

### Step 2 — Allow loopback (localhost traffic must be unrestricted)

```bash
iptables -A INPUT -i lo -j ACCEPT
```

### Step 3 — Allow established/related return traffic (stateful)

```bash
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
```

This single rule permits all return traffic for sessions your server initiates outbound, without opening individual inbound ports for each one.

### Step 4 — Add service-specific allow rules

```bash
# HTTPS from anywhere
iptables -A INPUT -p tcp --dport 443 -j ACCEPT

# HTTP from anywhere
iptables -A INPUT -p tcp --dport 80 -j ACCEPT

# SSH only from admin IP
iptables -A INPUT -p tcp --dport 22 -s 198.51.100.10 -j ACCEPT

# ICMP from internal network
iptables -A INPUT -p icmp -s 10.0.0.0/8 -j ACCEPT
```

### Step 5 — Verify the rule set

```bash
iptables -L INPUT -v --line-numbers
```

```
Chain INPUT (policy DROP)
num  pkts bytes target  prot opt in  out  source          destination
1       0     0 ACCEPT  all  --  lo  any  anywhere        anywhere
2    1834  2.1M ACCEPT  all  --  any any  anywhere        anywhere  ctstate RELATED,ESTABLISHED
3       0     0 ACCEPT  tcp  --  any any  anywhere        anywhere  tcp dpt:443
4      12   680 ACCEPT  tcp  --  any any  anywhere        anywhere  tcp dpt:80
5       0     0 ACCEPT  tcp  --  any any  198.51.100.10   anywhere  tcp dpt:22
6       0     0 ACCEPT  icmp --  any any  10.0.0.0/8      anywhere
```

### Step 6 — Persist rules across reboots

```bash
# On Debian/Ubuntu
apt-get install iptables-persistent
netfilter-persistent save

# On RHEL/CentOS
service iptables save
```

### What Happens at Packet Time

```
Inbound packet arrives on eth0
         │
         ▼
  [Routing decision: is this for me?]
         │ yes
         ▼
  [INPUT chain — walk rules top to bottom]
         │
    ┌────┴──────────────────────────────────┐
    │ Rule 1: lo interface? No.             │
    │ Rule 2: ESTABLISHED/RELATED? Check    │
    │   conntrack table. Yes → ACCEPT       │
    │ Rule 3: TCP dport 443? If yes → ACCEPT│
    │ Rule 4: TCP dport 80? If yes → ACCEPT │
    │ Rule 5: TCP dport 22 from admin IP?   │
    │   If both match → ACCEPT              │
    │ Rule 6: ICMP from 10.0.0.0/8? → ACPT │
    │ Default policy: DROP                  │
    └───────────────────────────────────────┘
```

---

## Use It

### Tool and Service Landscape

| Tool / Service | Deployment | Layer | Best For |
|----------------|-----------|-------|----------|
| `iptables` / `nftables` | Linux host | 3–4 | Server hardening, container networking |
| `pf` | macOS / BSD | 3–4 | Unix workstations, BSD-based appliances |
| Windows Defender Firewall | Windows host | 3–4 | Windows servers and endpoints |
| pfSense / OPNsense | VM or hardware | 3–7 | Open-source perimeter firewall |
| Cisco ASA / Palo Alto | Hardware | 3–7 NGFW | Enterprise perimeter, branch offices |
| AWS Security Groups | Cloud (per-ENI) | 3–4 stateful | EC2, RDS, Lambda VPC — most common AWS control |
| AWS Network ACL | Cloud (per-subnet) | 3–4 stateless | Subnet-level coarse control in VPCs |
| AWS Network Firewall | Cloud (managed) | 3–7 | Advanced VPC inspection, IDS/IPS |
| GCP Firewall Rules | Cloud (VPC-wide) | 3–4 | GCP VM ingress/egress |
| Azure NSG | Cloud (per-NIC/subnet) | 3–4 | Azure VM and subnet filtering |
| Cloudflare Magic Firewall | Network edge (CDN) | 3–4 | DDoS mitigation, global edge filtering |

### Cloud Security Groups vs. Traditional Firewalls

AWS Security Groups are stateful host-level firewalls applied to each network interface. You write inbound rules only; return traffic is automatic. The key difference from on-prem: Security Groups are **allow-list only** — you cannot write explicit deny rules. For deny capability at the subnet level you need Network ACLs, which are stateless and evaluated in numerical rule order — same as `iptables`.

### Next-Generation Firewalls (NGFW)

NGFWs add Layer 7 inspection to the traditional Layer 3–4 filter. Capabilities include:
- **Deep Packet Inspection (DPI)** — inspect payload content, not just headers.
- **Application identification** — distinguish Netflix traffic from generic HTTPS.
- **TLS inspection** — terminate, inspect, re-encrypt traffic.
- **IDS/IPS integration** — match known attack signatures inline.
- **URL and DNS filtering** — block categories of websites.

Use an NGFW at the perimeter when you need to control what applications your users can run, or when compliance requires content inspection.

---

## Common Pitfalls

- **Overly permissive default policy.** Many operators set the default INPUT policy to ACCEPT and add a few block rules. This is backwards. Set the default to DROP and add explicit allow rules. Anything you forget to allow is blocked; with ACCEPT defaults, anything you forget to block is open.

- **Forgetting the loopback interface.** Setting INPUT to DROP without an `iptables -A INPUT -i lo -j ACCEPT` rule breaks internal IPC. Processes on the same host that communicate via 127.0.0.1 (databases, local agents, socket proxies) will start failing silently.

- **Relying solely on the perimeter.** If an attacker compromises one internal host (via a phishing email, a vulnerable VPN client, a rogue USB stick), the perimeter firewall is already behind them. Host-based firewalls on every server limit lateral movement. Use both layers.

- **Opening port ranges instead of specific ports.** Rules like `--dport 1024:65535` are almost always wrong. Define the exact ports your services need. Unused open ports are attack surface.

- **Not persisting rules.** On Linux, `iptables` rules live in memory. A reboot wipes them. Always install a persistence mechanism (`iptables-persistent`, `firewalld`, systemd unit) and verify it survives a restart. Many incidents trace back to "the firewall was fine until the server rebooted."

---

## Exercises

1. **Easy** — On paper, write a rule table (like the numbered list in The Concept section) for a database server that should only accept MySQL connections (port 3306) from a specific application-server IP (10.0.1.5), accept SSH from a single admin IP, and drop everything else. State the default policy explicitly.

2. **Medium** — You have a web server correctly firewalled with the rules from the Build It section. A new requirement arrives: the server must call an external payment API at 185.25.0.0/20 over HTTPS. No other outbound traffic to the internet should be allowed. Rewrite the OUTPUT chain rules (default ACCEPT becomes default DROP) to implement this, making sure the server can still reach its own package repositories at apt.ubuntu.com.

3. **Hard** — Compare AWS Security Groups with Linux `iptables` in depth. Identify three behavioral differences (e.g., statefulness model, deny rules, rule limits, rule evaluation order). For each difference, describe a scenario where that difference would cause a real operational problem if an engineer assumed both tools worked the same way.

---

## Key Terms

| Term | What people think | What it actually means |
|------|------------------|----------------------|
| Firewall | A magic box that blocks hackers | A policy-enforcement point that filters packets by matching rules against packet attributes |
| Stateful inspection | The firewall deeply reads packet contents | The firewall tracks connection state (SYN, ESTABLISHED, etc.) and permits return traffic automatically — it is not the same as deep content inspection |
| Default deny | "Block bad things" | Block *everything* by default; only explicitly listed traffic is permitted — flips the security model from blacklist to allowlist |
| Network ACL (NACL) | Same as a security group | A *stateless* subnet-level filter; each direction (inbound/outbound) requires its own rule; no connection tracking |
| NGFW | A better firewall | A firewall that adds Layer 7 inspection — application awareness, DPI, TLS termination, IDS/IPS — on top of traditional L3-4 filtering |
| DMZ | A dangerous zone | A network segment sitting between the internet-facing firewall and the internal network, designed to host public-facing services with limited trust on both sides |
| Egress filtering | Only relevant for inbound | Filtering *outbound* traffic — crucial for stopping data exfiltration and malware C2 callbacks, but often overlooked |

---

## Further Reading

- [Linux iptables man page and Netfilter project](https://www.netfilter.org/documentation/) — canonical reference for `iptables`, `nftables`, and the Linux packet filtering subsystem.
- [AWS Security Groups vs. Network ACLs](https://docs.aws.amazon.com/vpc/latest/userguide/security.html) — AWS documentation comparing both VPC security controls, with a clear comparison table.
- [NIST SP 800-41 Rev 1 — Guidelines on Firewalls and Firewall Policy](https://csrc.nist.gov/publications/detail/sp/800-41/rev-1/final) — government reference for firewall policy planning and architecture decisions.
- [pfSense documentation — Firewall rules](https://docs.netgate.com/pfsense/en/latest/firewall/index.html) — practical, readable coverage of rule ordering, stateful filtering, and interface-level policies using an open-source firewall OS.
- [Cloudflare Learning — What is a Firewall?](https://www.cloudflare.com/learning/security/what-is-a-firewall/) — accessible overview that covers packet filtering, stateful inspection, and NGFW in plain language.
