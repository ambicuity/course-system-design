# IP Address Cheat Sheet Every Engineer Should Know

> Every networking decision — firewall rules, VPC design, service mesh, load balancer config — reduces to IP addresses. Know them cold.

**Type:** Learn
**Prerequisites:** How the Internet Works, DNS Fundamentals
**Time:** ~25 minutes

---

## The Problem

You are provisioning a new Kubernetes cluster on AWS. You pick a VPC CIDR of `10.0.0.0/16`, create three subnets, and deploy your pods. Two weeks later your on-prem VPN tunnel comes up — and nothing can reach anything, because the on-prem network also uses `10.0.0.0/16`. Every packet gets routed to the wrong place. You have to re-IP the entire cluster in production.

This is a $50,000 mistake that a five-minute CIDR review would have prevented. It happens to experienced engineers who treat IP addresses as something to click through in a cloud console without actually understanding them.

The same knowledge gap causes subtler failures every day: a service binds to `0.0.0.0` and becomes reachable from the public internet by accident; a firewall rule blocks `172.16.0.0/12` thinking it is "all 172.x.x.x addresses" when it only covers a fraction; a developer pings `localhost` from inside a Docker container and wonders why the host service is unreachable. IP addresses are the foundational currency of distributed systems. Every engineer should have a working mental model without reaching for a calculator.

---

## The Concept

### IPv4 Structure

An IPv4 address is a **32-bit unsigned integer** written in dotted-decimal notation: four octets (8-bit groups) separated by dots.

```
192     .  168     .  10      .  5
11000000   10101000   00001010   00000101
  octet1     octet2     octet3     octet4
```

Each octet ranges 0–255. The 32-bit space gives 2³² = ~4.3 billion addresses — not enough for the modern internet, which is why NAT, private ranges, and IPv6 exist.

### CIDR Notation

CIDR (Classless Inter-Domain Routing) expresses both an address and a **prefix length** in one token: `address/prefix`.

```
192.168.10.0/24
           ^^-- 24 bits are the "network" part
               8 bits are the "host" part (the rest)
```

The prefix length tells you which bits are fixed (the network) and which bits vary (the hosts in that subnet). A `/24` fixes the top 24 bits, leaving 8 bits free — 2⁸ = 256 addresses in the block.

**Host count formula:**

```
total addresses = 2^(32 - prefix_length)
usable hosts    = 2^(32 - prefix_length) - 2
```

Subtract 2 because the **first address** is the network address (all host bits = 0) and the **last address** is the broadcast address (all host bits = 1). Both are reserved.

### CIDR Quick-Reference Table

| Prefix | Total Addresses | Usable Hosts | Subnet Mask       |
|--------|-----------------|--------------|-------------------|
| /32    | 1               | 1 (host route) | 255.255.255.255  |
| /31    | 2               | 2 (point-to-point, RFC 3021) | 255.255.255.254 |
| /30    | 4               | 2            | 255.255.255.252   |
| /29    | 8               | 6            | 255.255.255.248   |
| /28    | 16              | 14           | 255.255.255.240   |
| /27    | 32              | 30           | 255.255.255.224   |
| /26    | 64              | 62           | 255.255.255.192   |
| /25    | 128             | 126          | 255.255.255.128   |
| /24    | 256             | 254          | 255.255.255.0     |
| /23    | 512             | 510          | 255.255.254.0     |
| /22    | 1,024           | 1,022        | 255.255.252.0     |
| /20    | 4,096           | 4,094        | 255.255.240.0     |
| /16    | 65,536          | 65,534       | 255.255.0.0       |
| /8     | 16,777,216      | 16,777,214   | 255.0.0.0         |
| /0     | 4,294,967,296   | all          | 0.0.0.0 (default route) |

### Private Address Ranges (RFC 1918)

These ranges are never routed on the public internet. Use them freely inside data centers, VPCs, home networks, and containers.

| Range              | CIDR         | Size       | Common Use              |
|--------------------|--------------|------------|-------------------------|
| 10.x.x.x           | 10.0.0.0/8   | 16 million | Enterprise / cloud VPCs |
| 172.16–31.x.x      | 172.16.0.0/12| 1 million  | Mid-size networks       |
| 192.168.x.x        | 192.168.0.0/16| 65,536    | Home / small office     |

> **Critical gotcha on 172.16.0.0/12:** this block covers `172.16.0.0` through `172.31.255.255`. It does NOT include `172.0.x.x` through `172.15.x.x`. Firewall rules that naively block `172.0.0.0/8` will overlap with public addresses.

### Special / Reserved Addresses

| Address / Range     | Purpose                                      |
|---------------------|----------------------------------------------|
| `127.0.0.0/8`       | Loopback — `127.0.0.1` is `localhost`        |
| `0.0.0.0`           | Unspecified / bind to all interfaces         |
| `0.0.0.0/0`         | Default route — matches everything           |
| `169.254.0.0/16`    | Link-local (APIPA) — assigned when DHCP fails|
| `224.0.0.0/4`       | Multicast                                    |
| `255.255.255.255`   | Limited broadcast (same-subnet only)         |
| `100.64.0.0/10`     | Shared address space (RFC 6598, carrier-grade NAT) |

### IPv6 in One Screen

IPv6 uses **128 bits** written as eight groups of four hex digits separated by colons.

```
2001:0db8:85a3:0000:0000:8a2e:0370:7334
```

Compression rules:
- Leading zeros in a group can be dropped: `0db8` → `db8`
- One contiguous run of all-zero groups can be replaced with `::` (only once)

```
2001:db8::8a2e:370:7334   ← compressed form of the above
```

| IPv6 Range / Address | Purpose                    |
|----------------------|----------------------------|
| `::1/128`            | Loopback (localhost)       |
| `::/128`             | Unspecified                |
| `fe80::/10`          | Link-local                 |
| `fd00::/8`           | Unique-local (private RFC 4193) |
| `2000::/3`           | Global unicast (public internet) |
| `ff00::/8`           | Multicast                  |

---

## Build It / In Depth

### Worked Example: Subnetting a /16 for Three Availability Zones

**Goal:** You have `10.10.0.0/16` (65,536 addresses). Divide it into three equal subnets — one per AZ — each large enough to hold 8,000 pods.

**Step 1 — How many bits do you need for 8,000 hosts?**

```
2^13 = 8,192  → /19 gives 8,190 usable hosts ✓
2^12 = 4,096  → /20 gives 4,094 — not enough ✗
```

Use `/19` subnets.

**Step 2 — Lay out the /19 blocks inside 10.10.0.0/16**

A `/19` consumes 2¹³ = 8,192 addresses. Starting from the base:

```
10.10.0.0/19   →  10.10.0.0   –  10.10.31.255   (AZ-a)
10.10.32.0/19  →  10.10.32.0  –  10.10.63.255   (AZ-b)
10.10.64.0/19  →  10.10.64.0  –  10.10.95.255   (AZ-c)
10.10.96.0/16↑ →  10.10.96.0  –  10.10.255.255  (spare ~40k for future)
```

**Step 3 — Verify with Python (no external libraries)**

```python
import ipaddress

vpc = ipaddress.IPv4Network("10.10.0.0/16")
subnets = list(vpc.subnets(new_prefix=19))

for i, subnet in enumerate(subnets[:3]):
    print(f"AZ-{chr(97+i)}: {subnet}  "
          f"({subnet.network_address} – {subnet.broadcast_address}, "
          f"{subnet.num_addresses - 2} usable)")
```

```
AZ-a: 10.10.0.0/19   (10.10.0.0 – 10.10.31.255, 8190 usable)
AZ-b: 10.10.32.0/19  (10.10.32.0 – 10.10.63.255, 8190 usable)
AZ-c: 10.10.64.0/19  (10.10.64.0 – 10.10.95.255, 8190 usable)
```

### Checking Whether an IP Is in a Range

```python
import ipaddress

def in_range(ip: str, cidr: str) -> bool:
    return ipaddress.IPv4Address(ip) in ipaddress.IPv4Network(cidr)

print(in_range("172.20.5.3",  "172.16.0.0/12"))  # True
print(in_range("172.15.0.1",  "172.16.0.0/12"))  # False
print(in_range("10.0.0.1",    "0.0.0.0/0"))      # True  (default route matches all)
```

### CLI Tools Every Engineer Should Have

```bash
# Inspect your machine's IP addresses
ip addr show                     # Linux
ipconfig getifaddr en0           # macOS (Wi-Fi)

# Check what CIDR a block represents
ipcalc 192.168.5.0/27
# → Hosts: 30, Mask: 255.255.255.224, Network: 192.168.5.0

# Trace the route to an address
traceroute 8.8.8.8               # macOS/Linux
tracert 8.8.8.8                  # Windows

# Check if an IP is reachable (ICMP)
ping -c 3 10.10.0.1

# Show the routing table
ip route show                    # Linux
netstat -rn                      # macOS
```

---

## Use It

### AWS VPC Design

AWS reserves five addresses per subnet (first four + last one), so a `/24` gives you only 251 usable IPs, not 254. Plan subnets one size larger than you think you need.

| Subnet Size | AWS Usable IPs | Good For            |
|-------------|---------------|---------------------|
| /28         | 11            | NAT gateway subnets |
| /24         | 251           | Small app tier       |
| /22         | 1,019         | Node group per AZ    |
| /19         | 8,187         | Large pod CIDR       |
| /16         | 65,531        | Full VPC             |

### Kubernetes Networking

Kubernetes assigns each pod its own IP from a **pod CIDR** (default: `10.244.0.0/16` for Flannel, `192.168.0.0/16` for Calico). If your VPC already uses those ranges you will have a routing conflict. Always check for overlap when installing a CNI plugin.

```yaml
# Example: tell kubeadm to use a non-conflicting pod CIDR
kubeadm init --pod-network-cidr=10.10.0.0/16
```

### Docker and Container Networks

Docker creates a bridge network `172.17.0.0/16` by default. If that conflicts with your corporate VPN you can override it in `/etc/docker/daemon.json`:

```json
{
  "bip": "10.200.0.1/24",
  "default-address-pools": [
    {"base": "10.201.0.0/16", "size": 24}
  ]
}
```

### Firewall Rules / Security Groups

Express rules as CIDR ranges. Prefer the smallest possible range for inbound rules:

| Intention                  | CIDR to Use         |
|----------------------------|---------------------|
| Allow from entire internet | 0.0.0.0/0           |
| Allow from my VPC only     | 10.0.0.0/8 (or exact VPC CIDR) |
| Allow from specific host   | 203.0.113.5/32      |
| Block all private ranges   | 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 |

---

## Common Pitfalls

- **CIDR overlap in multi-VPC / hybrid setups.** Two networks with overlapping CIDR ranges cannot be peered or connected via VPN. Audit all network ranges before provisioning any new VPC. A shared spreadsheet or a tool like AWS IP Address Manager (IPAM) pays for itself immediately.

- **Forgetting the AWS/GCP 5-address reservation.** Cloud providers reserve 5 addresses per subnet. A `/28` gives 16 total − 5 = 11 usable IPs, not 14. Size subnets accordingly; running out of IPs in a subnet requires re-IP or migration.

- **Binding a service to `0.0.0.0` without a firewall.** `0.0.0.0` binds to all interfaces, including the public NIC. A development server started with `--host 0.0.0.0` on a cloud VM is reachable from the internet if the security group is permissive. Always bind to a specific private IP in production, or use a firewall.

- **Misunderstanding `172.16.0.0/12`.** This block ends at `172.31.255.255`, not `172.255.255.255`. Writing a firewall rule that blocks `172.0.0.0/8` will block public addresses in the 172.x.x.x public range that are NOT part of RFC 1918. Use the exact CIDR `/12`, not `/8`.

- **Using `127.0.0.1` vs container networking.** Inside a Docker container, `127.0.0.1` refers to the container itself, not the host. To reach a service on the host, use the bridge gateway IP (often `172.17.0.1`) or the special hostname `host.docker.internal` on macOS/Windows. This trips up developers moving from bare metal to containers.

---

## Exercises

1. **Easy** — You are given the network `192.168.50.0/26`. Without a calculator: what is the network address, the broadcast address, and how many hosts can it hold? List the first and last usable host IPs.

2. **Medium** — Your company is building a new data center with three tiers (web, app, db). You have been allocated `10.20.0.0/20`. Design a subnetting plan where the web tier holds up to 500 hosts per AZ (three AZs), the app tier holds up to 250 hosts per AZ, and the db tier holds up to 60 hosts per AZ. Show your CIDR assignments and verify there is no overlap.

3. **Hard** — You need to peer two VPCs: VPC-A (`10.0.0.0/16`) and VPC-B (`10.0.0.0/20`). Why does this peering fail? Redesign the addressing plan for VPC-B so the peering can succeed. Then write a Python script using the `ipaddress` module that checks a list of CIDR blocks and prints any pairs that overlap.

---

## Key Terms

| Term | What People Think | What It Actually Means |
|------|-------------------|------------------------|
| **CIDR** | "A way to write IP addresses with a slash" | Classless Inter-Domain Routing — a routing protocol reform that replaced fixed class-based addressing; the `/prefix` notation is just its notation |
| **Subnet mask** | "Same as the prefix length, just in decimal" | The 32-bit mask where 1-bits denote the network portion; `/24` = `255.255.255.0` = `0xFFFFFF00` — three representations of the same thing |
| **Private IP** | "An IP that can't reach the internet" | An address in RFC 1918 ranges that routers on the public internet will not forward — your device still reaches the internet via NAT |
| **`0.0.0.0`** | "An invalid or empty address" | Context-dependent: in a binding it means "all local interfaces"; in a route it means "default route / match everything"; in DHCP it means the source before an address is assigned |
| **Loopback** | "Just `127.0.0.1`" | The entire `127.0.0.0/8` block; any address in that range loops back to the local machine — `127.0.0.2` also works |
| **Link-local (`169.254.x.x`)** | "An error state" | Addresses auto-assigned when DHCP is unavailable (APIPA on Windows); also used intentionally inside AWS for the instance metadata endpoint `169.254.169.254` |
| **`/0`** | "An empty or invalid prefix" | The default route — it matches every possible IP address and has the lowest specificity in routing decisions |

---

## Further Reading

- [RFC 1918 — Address Allocation for Private Internets](https://datatracker.ietf.org/doc/html/rfc1918) — the primary specification for private address ranges; short and worth reading in full.
- [RFC 4632 — Classless Inter-domain Routing (CIDR): The Internet Address Assignment and Aggregation Plan](https://datatracker.ietf.org/doc/html/rfc4632) — explains how CIDR replaced class-based routing and how prefix aggregation works.
- [AWS VPC Sizing and IP Addressing](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-cidr-blocks.html) — covers AWS-specific CIDR constraints, the 5-reserved-IPs rule, and secondary CIDR blocks.
- [Python `ipaddress` module documentation](https://docs.python.org/3/library/ipaddress.html) — the standard library module for IP address manipulation; supports IPv4, IPv6, networks, and overlap detection.
- [Cloudflare Learning Center — What is an IP address?](https://www.cloudflare.com/learning/dns/glossary/what-is-my-ip-address/) — a concise, well-illustrated refresher covering IPv4, IPv6, and NAT suitable for engineers who want a quick mental model reset.
