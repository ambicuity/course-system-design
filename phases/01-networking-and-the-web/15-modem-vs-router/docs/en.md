# Modem vs. Router

> The modem talks to the internet; the router talks to your devices. Confusing them wastes hours of troubleshooting.

**Type:** Learn
**Prerequisites:** IP Addresses, DNS Basics, How the Internet Works
**Time:** ~18 minutes

---

## The Problem

You call your ISP to report that the internet is down. The support rep asks: "Have you tried restarting your router?" You restart it. Nothing changes. The real problem was the modem — a device most people do not know they own separately — and the five minutes you spent rebooting the wrong box delayed the fix.

This is the mildest version of the problem. In production, the same conceptual confusion leads to engineers misdiagnosing network latency as application-layer slowness, misconfiguring firewall rules on the wrong device, or buying the wrong hardware to add capacity. Understanding the modem/router boundary is foundational for any work that touches networks: cloud VPC design, on-premise data center layout, home lab setup, and mobile app debugging all depend on knowing exactly where the public internet ends and your private network begins.

The distinction also matters for security. Traffic between your devices and the router never touches the public internet. Traffic from the router to the modem does. Threat models, firewall placement, and encryption requirements differ on either side of that boundary.

---

## The Concept

### The Two Jobs, Clearly Separated

| Device | Layer it operates at | What it connects | What it "speaks" |
|--------|---------------------|-----------------|-----------------|
| Modem  | Physical + Data Link | Your home ↔ ISP | ISP's signal (DOCSIS, DSL, fiber optic, LTE) on one side; Ethernet on the other |
| Router | Network (Layer 3) | LAN ↔ WAN | IP; manages private vs. public address space |

**Modem** stands for **modulator-demodulator**. ISPs do not deliver raw Ethernet into your wall. They deliver a signal over a medium that requires translation: radio frequencies over coaxial cable (DOCSIS for cable internet), voltage pulses over phone lines (DSL), light pulses over fiber (handled by an Optical Network Terminal, ONT), or radio waves from a cell tower (4G/5G). The modem's job is to convert that medium-specific signal into ordinary Ethernet packets — and to convert Ethernet back when you send data out. The modem hands your equipment **one public IP address**, assigned by the ISP via DHCP or PPPoE.

**Router** takes that single public IP and builds a private network behind it. Every device you connect — laptop, phone, smart TV, thermostat — gets a **private IP** (typically in the `192.168.x.x` or `10.x.x.x` range). The router uses **Network Address Translation (NAT)** to map outbound connections from many private IPs to the single public IP, and to route inbound responses back to the correct device.

### How NAT Actually Works

```
Device A (192.168.1.10) ---\
                            > Router (public: 203.0.113.5) ---> Internet
Device B (192.168.1.11) ---/
```

When Device A opens a TCP connection to `93.184.216.34:443` (example.com), the router:

1. Picks an unused **source port** on the public IP, e.g. `203.0.113.5:51234`.
2. Writes a NAT table entry: `(192.168.1.10:54312) ↔ (203.0.113.5:51234)`.
3. Sends the packet with the public source address.
4. When the response arrives at `203.0.113.5:51234`, looks up the table and rewrites the destination to `192.168.1.10:54312`.

This is called **NAPT** (Network Address Port Translation) or loosely "NAT". It is how one public IP supports hundreds of simultaneous connections from many devices.

### DHCP: Who Hands Out Private IPs?

The router runs a **DHCP server** for your LAN. When your phone connects to Wi-Fi, it broadcasts a DHCP Discover; the router responds with an IP offer (e.g. `192.168.1.42`), a lease duration, and the addresses of the **default gateway** (the router itself) and **DNS resolvers**. Your phone accepts the offer and is ready to communicate.

There is also a DHCP exchange between the modem and the ISP, but that is entirely separate: the ISP's DHCP server assigns the modem its one public IP.

### Packet Flow: End to End

```
[Your laptop]
  |  (private IP: 192.168.1.10)
  | Ethernet / Wi-Fi
  v
[Router]  <--- DHCP server, NAT, firewall, routing table
  |  (public IP: 203.0.113.5, assigned by ISP DHCP)
  | Ethernet
  v
[Modem]   <--- converts Ethernet ↔ DOCSIS/DSL/fiber/LTE signal
  |  (ISP physical medium)
  v
[ISP Network] --> [Internet]
```

### Modem Types by Connection Technology

| Technology | Medium | Standard / Protocol | Typical Speed |
|-----------|--------|-------------------|--------------|
| Cable     | Coaxial cable | DOCSIS 3.0 / 3.1 | 100 Mbps – 10 Gbps |
| DSL       | Telephone line | ADSL2+, VDSL2 | 1–100 Mbps |
| Fiber (ONT) | Optical fiber | GPON, XGS-PON | 100 Mbps – 10 Gbps |
| Cellular  | Radio (4G LTE / 5G) | LTE, NR | 20 Mbps – 1 Gbps |
| Satellite | Radio (LEO/GEO) | Proprietary (Starlink) | 20–220 Mbps |

Note: fiber ONTs are sometimes called "optical modems" even though they do not modulate in the traditional sense — they convert optical signals to Ethernet electrically.

### Combo Devices (Gateway)

ISPs frequently rent customers a **modem-router combo** (often called a **gateway** or **residential gateway**). Physically it is one box, but logically it still performs both functions. The internal bus between the modem and router functions is just on a circuit board instead of an Ethernet cable.

```
[Gateway device]
+----------------------------+
|  Modem function            |
|  (DOCSIS / DSL / fiber)    |
|          |                 |
|  Router function           |
|  (NAT, DHCP, Wi-Fi, LAN)   |
+----------------------------+
```

Combos are convenient but inflexible: when one half fails or becomes outdated, you replace the whole unit. Enthusiasts and businesses often prefer a standalone modem with a separate router so each can be upgraded independently.

---

## Build It / In Depth

### Tracing a Real Connection Step by Step

**Scenario:** You type `https://api.example.com` in your browser from your laptop at home.

**Step 1 — DNS resolution (LAN to router)**
Your laptop sends a DNS query to the DNS resolver address the router provided via DHCP (e.g., `192.168.1.1` or a forwarded resolver like `8.8.8.8`). The router may answer from cache or forward the query outbound through the modem to the ISP's resolver or a public resolver.

**Step 2 — TCP handshake leaves the LAN**
Your browser opens a TCP connection to the resolved IP. The packet's source is `192.168.1.10:54001`. The router rewrites source to `203.0.113.5:52345` and records the NAT mapping.

**Step 3 — Modem encapsulation**
The Ethernet frame containing that IP packet arrives at the modem. The modem wraps it in the ISP's protocol (e.g., a DOCSIS MAC frame) and sends it over coaxial cable to the ISP's CMTS (Cable Modem Termination System) — the ISP's equivalent of the "other end" of your modem.

**Step 4 — Response comes back**
The response from `api.example.com` arrives at the modem addressed to `203.0.113.5:52345`. The modem strips the DOCSIS framing, produces an Ethernet frame, sends it to the router. The router consults its NAT table, rewrites the destination to `192.168.1.10:54001`, and delivers it to your laptop over Wi-Fi.

### Reading Your NAT Table (Linux router / firewall)

If you run a Linux box as a router (or inspect a DD-WRT / OpenWrt device), you can inspect active NAT mappings:

```bash
# View current NAT conntrack table
sudo conntrack -L -n

# Example output line:
# tcp 6 117 ESTABLISHED src=192.168.1.10 dst=93.184.216.34
#   sport=54312 dport=443
#   src=93.184.216.34 dst=203.0.113.5 sport=443 dport=51234
#   [ASSURED] mark=0 use=2
```

The two lines per entry show the forward and reverse translation: local device `192.168.1.10:54312` maps to public `203.0.113.5:51234` for the connection to `93.184.216.34:443`.

### Diagnosing: Modem Problem vs. Router Problem

```
Symptom: No internet on any device
                |
         ┌──────┴──────┐
      Plug one device directly into modem via Ethernet cable
                |
         ┌──────┴──────┐
    Gets public IP?   No → Modem/ISP problem → call ISP
         |
        Yes → Router problem → restart / reconfigure router
```

This is the definitive split test. If a device plugged directly into the modem receives a public IP and reaches the internet, the modem and ISP link are healthy. Blame the router.

---

## Use It

### Where This Shows Up in Real Systems

**Home labs and self-hosted services**
Exposing a service (e.g., a Minecraft server or a home NAS) requires **port forwarding** on the router — not the modem. The router's firewall decides which inbound connections get forwarded to which private IP. The modem does not filter traffic; it is transparent at Layer 3.

**Cloud provider VPCs**
AWS VPC, GCP VPC, and Azure VNet implement the same modem/router conceptual split at cloud scale. An **Internet Gateway (IGW)** in AWS is analogous to the modem: it is the boundary between the VPC's private address space and the public internet. A **NAT Gateway** is analogous to the home router's NAT function, allowing private-subnet instances to reach the internet without being publicly addressable.

| Home network | AWS equivalent |
|-------------|---------------|
| Modem (ISP boundary) | Internet Gateway (IGW) |
| Router (NAT) | NAT Gateway |
| Private IP (192.168.x.x) | Private subnet IP (10.x.x.x) |
| Public IP (from ISP) | Elastic IP / public IP |
| DHCP server (router) | VPC DHCP options set |

**Mobile / cellular networks**
Your phone connected to LTE is using a built-in cellular modem. Your carrier's network acts as the router (via CGNAT — Carrier-Grade NAT). You rarely get a true public IP on a mobile data connection; you share a carrier IP with thousands of other subscribers. This is why inbound connections to phones over cellular are extremely difficult without a relay service.

**Corporate networks**
Enterprise edge routers (Cisco ASR, Juniper MX series) handle NAT, routing, and firewall at scale. The "modem" equivalent is typically handled by the ISP's CPE or a dedicated WAN interface card. SD-WAN solutions abstract this further but the underlying boundary between WAN signal and LAN IP routing is the same.

---

## Common Pitfalls

- **Restarting the wrong device.** Restarting only the router when the modem is the problem (or vice versa) wastes time. The split test — plug directly into the modem — takes 30 seconds and identifies the culprit immediately.

- **Double NAT.** Connecting a router to an ISP gateway that is already doing NAT creates two NAT layers. Devices end up behind two layers of address translation, which breaks peer-to-peer applications (VoIP, gaming, WebRTC) and makes port forwarding extremely complicated. Fix by putting the ISP gateway in **bridge mode** (disabling its router function) so only your router does NAT.

- **Assuming the public IP is on the router.** The router's WAN port holds the public IP, not its LAN ports. Binding an application to `0.0.0.0` on a LAN machine does not make it reachable from the internet. You also need a port forwarding rule on the router and confirmation that your ISP is not CGNAT-ing you.

- **Forgetting CGNAT.** Many ISPs, especially cable and mobile carriers, now use Carrier-Grade NAT: your modem's "public" IP is actually private (`100.64.x.x` range). You share a true public IP with other customers. Port forwarding at your router does nothing useful because the ISP's CGNAT layer discards inbound connections anyway. You need an ISP static IP or a tunnel (WireGuard, ngrok, Tailscale) to reliably accept inbound connections.

- **Treating a combo device as just a router.** When you call the ISP about your "router" but actually mean the combo gateway, mixed communication causes confusion. Know whether you have a standalone modem + router or a combo gateway — it affects every troubleshooting and configuration conversation.

---

## Exercises

1. **Easy** — Without touching any device, determine which public IP address your home network is using. Then identify which device in your home actually "holds" that IP. Verify your answer by plugging a laptop directly into the modem (if possible) and running `ip a` or `ipconfig` to see which IP is assigned.

2. **Medium** — Set up a local web server on your laptop (`python3 -m http.server 8080`). Access it from another device on the same Wi-Fi. Then try to access it from your phone on mobile data. Explain why the second attempt fails in terms of NAT, port forwarding, and/or CGNAT. Describe exactly what configuration changes would be needed to make the server reachable from the public internet.

3. **Hard** — Research how **AWS NAT Gateway** compares to a home router's NAT in terms of: (a) state tracking, (b) scalability mechanism, (c) handling of inbound connection initiation, and (d) cost model. Write a short technical comparison (400–600 words) identifying two situations where AWS NAT Gateway behavior differs meaningfully from what a home router would do.

---

## Key Terms

| Term | What people think | What it actually means |
|------|------------------|----------------------|
| Modem | The box that gives you Wi-Fi | A signal converter that bridges your home Ethernet and the ISP's physical medium (cable, DSL, fiber, cellular) |
| Router | The box that connects you to the internet | A Layer-3 device that creates and manages your private network, runs NAT, and routes packets between LAN and WAN |
| NAT | Something routers do magically | A translation table that maps many (private IP, port) pairs to one (public IP, port) pair, tracking state per connection |
| Public IP | My IP address | An IP address routable on the global internet, assigned to the modem's WAN interface by the ISP |
| Private IP | An internal address | An IP in RFC 1918 ranges (10/8, 172.16/12, 192.168/16) used inside a LAN, not routable on the public internet |
| Gateway (combo) | Just a fancy router | A single device performing both modem and router functions; often rented from the ISP |
| CGNAT | An ISP internal detail | Carrier-Grade NAT: your ISP places another NAT layer above your modem, meaning your modem's "public" IP is actually shared and not truly public |

---

## Further Reading

- [How DOCSIS Works — CableLabs Overview](https://www.cablelabs.com/technologies/docsis) — authoritative explanation of the cable modem standard from the standards body that created it.
- [RFC 1918 — Address Allocation for Private Internets](https://datatracker.ietf.org/doc/html/rfc1918) — the IETF document defining the private address ranges every router uses.
- [RFC 3022 — Traditional IP Network Address Translator](https://datatracker.ietf.org/doc/html/rfc3022) — the original NAT specification; short and readable.
- [AWS — NAT Gateways documentation](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-nat-gateway.html) — shows how cloud providers implement the same NAT concept at scale with an explicit managed service.
- [Tailscale Blog — How NAT Traversal Works](https://tailscale.com/blog/how-nat-traversal-works) — a deep, accurate breakdown of NAT behavior including CGNAT, hole-punching, and why peer-to-peer over NAT is hard.
