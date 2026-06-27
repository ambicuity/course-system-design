# Hub, Switch, & Router Explained

> Each device lives at a different layer of the stack — confuse them and your network design falls apart.

**Type:** Learn
**Prerequisites:** OSI Model Basics, IP Addressing, MAC Addresses
**Time:** ~20 minutes

---

## The Problem

You are designing the network for a small office with 50 employees. You buy a box of "network hardware" and someone hands you a hub, two switches, and a router. You plug everything together, traffic crawls, packets collide, and half the office loses internet access. You have no idea which device caused what.

This confusion is extremely common because all three devices look similar (ports and blinking lights) and the marketing on the box rarely explains the actual OSI layer each one operates at. Without understanding the distinction, you cannot debug slowdowns, plan VLANs, isolate subnets, or even understand why your `ping` is timing out.

The good news: each device has a single, well-defined job. Once you internalize which layer it works at and what "address" it understands, the entire picture clicks into place — and you can reason about every network architecture from a home lab to AWS VPC peering.

---

## The Concept

### The OSI Layer Each Device Lives On

| Device | OSI Layer | Address Used | Primary Job |
|--------|-----------|--------------|-------------|
| Hub | Layer 1 — Physical | None | Repeat electrical signals to all ports |
| Switch | Layer 2 — Data Link | MAC address | Forward frames to the correct port |
| Router | Layer 3 — Network | IP address | Route packets between different networks |

This table is the mental model. Everything else is a consequence of it.

---

### Hub — Layer 1, Electrical Repeater

A hub has no intelligence. It receives a raw electrical signal on one port and immediately re-transmits it on **every other port**. It does not read any address. It has no memory. It does not make decisions.

```
          ┌─────────────────────────────────┐
          │              HUB                │
  A ──────┤                                 ├────── B  ← receives A's frame
          │   signal floods all ports       ├────── C  ← receives A's frame
  D ──────┤                                 ├────── E  ← receives A's frame
          └─────────────────────────────────┘
               ONE collision domain
```

**Consequences:**
- All ports share the same **collision domain**. If A and D transmit simultaneously, the signals collide, both frames are destroyed, and CSMA/CD kicks in to retry.
- All ports share the same **bandwidth**. 100 Mbps hub with 10 devices → each device effectively competes for that 100 Mbps.
- Hubs only support **half-duplex**: a port can either send or receive, never both at once.
- Any device can see every other device's traffic — a security nightmare.

Hubs are obsolete in modern networking. You will encounter them in legacy hardware inventories and certification exam questions.

---

### Switch — Layer 2, MAC-Aware Frame Forwarder

A switch understands **frames** (Layer 2 PDUs). It reads the destination MAC address in the Ethernet frame header and forwards the frame only to the port where that MAC address lives.

**MAC Address Table (CAM Table)**

The switch builds this table dynamically through a process called **MAC learning**:
1. Frame arrives on port 3 from source MAC `AA:BB:CC:DD:EE:01`.
2. Switch records: `AA:BB:CC:DD:EE:01` → port 3.
3. Switch looks up the destination MAC. If found, it forwards only to that port. If not found (unknown unicast), it **floods** the frame to all ports except the ingress port — behaving like a hub for that single frame.

```
          ┌──────────────────────────────────────────┐
          │                 SWITCH                   │
          │  CAM Table:                              │
  A ──────┤  AA:BB → port 1                         ├────── B
          │  CC:DD → port 2      A→B: only port 2   │
  C ──────┤  EE:FF → port 3                         ├────── D
          │                                          │
          └──────────────────────────────────────────┘
    Each port = separate collision domain
```

**Key properties:**
- Each port is its **own collision domain** — collisions are eliminated between ports.
- Full-duplex communication: a port can send and receive simultaneously.
- All ports remain in the **same broadcast domain** — a broadcast (dest `FF:FF:FF:FF:FF:FF`) still floods every port.
- Switches support **VLANs** (802.1Q tagging) to carve a single physical switch into multiple isolated Layer 2 segments, each with its own broadcast domain.

---

### Router — Layer 3, IP Packet Forwarder

A router understands **packets** (Layer 3 PDUs). It reads the destination IP address, consults a **routing table**, and forwards the packet out the appropriate interface — which may be connected to a completely different network with different addressing.

```
          192.168.1.0/24               10.0.0.0/8
                │                           │
    ┌───────────┴───────────────────────────┴───────────┐
    │                      ROUTER                       │
    │  Routing Table:                                   │
    │  192.168.1.0/24 → eth0 (local)                   │
    │  10.0.0.0/8     → eth1 (local)                   │
    │  0.0.0.0/0      → 203.0.113.1 (ISP gateway)      │
    └───────────────────────────────────────────────────┘
```

**Key properties:**
- Each router interface is a **separate broadcast domain** — broadcasts do not cross the router. This is why your home network's ARP storm doesn't pollute the entire internet.
- Routers decrement the IP TTL on each packet and drop packets with TTL=0 (prevents loops).
- Routers perform **NAT** (Network Address Translation) at the boundary between private RFC 1918 space and the public internet.
- Routing decisions use **longest-prefix match**: a `/28` route beats a `/24` route for the same destination.
- Dynamic routing protocols (OSPF, BGP, EIGRP) allow routers to learn routes automatically and adapt to topology changes.

---

### Collision Domain vs. Broadcast Domain

This distinction is tested constantly and matters for network design:

| Boundary | Hub | Switch | Router |
|----------|-----|--------|--------|
| Breaks collision domain? | No — all ports share one | Yes — each port is isolated | Yes |
| Breaks broadcast domain? | No | No (unless VLANs configured) | Yes — always |

---

## Build It / In Depth

### Tracing a Packet Through All Three Devices

Scenario: Your laptop (`192.168.1.5`) requests `google.com` (`142.250.80.46`).

**Step 1 — Laptop to Switch**

Your laptop constructs an IP packet (src `192.168.1.5`, dst `142.250.80.46`) inside an Ethernet frame addressed to the router's MAC (obtained via ARP). The frame hits the office switch.

```
Ethernet Frame on the wire:
  Src MAC: A4:83:E7:11:22:33  (laptop NIC)
  Dst MAC: C8:D7:19:AA:BB:CC  (router LAN interface)
  Src IP:  192.168.1.5
  Dst IP:  142.250.80.46
```

The switch reads the **destination MAC** (`C8:D7:19:AA:BB:CC`), looks it up in its CAM table, and forwards the frame only to the port the router is plugged into. No other device sees this frame.

**Step 2 — Switch to Router**

The router's LAN interface receives the frame. It strips the Ethernet header and looks at the IP packet. The routing table has a default route (`0.0.0.0/0 → ISP gateway`). The router:
1. Decrements the IP TTL by 1.
2. Constructs a **new** Ethernet frame with its WAN interface MAC as source and the ISP gateway MAC as destination.
3. Sends the packet out the WAN interface.

The source and destination **MAC addresses changed** at the router. The source and destination **IP addresses did not** (ignoring NAT for simplicity).

**Step 3 — NAT at the Router**

Most home/office routers also perform NAT. The router rewrites the source IP from `192.168.1.5` to the public IP (e.g., `203.0.113.100`) and records the mapping in its NAT table so return traffic can be translated back.

```
NAT Table entry:
  Internal: 192.168.1.5:54321
  External: 203.0.113.100:54321
  Protocol: TCP
```

**Verifying with command-line tools:**

```bash
# See the MAC address table on a Cisco switch
show mac address-table

# Trace hop-by-hop routing (each hop = a router)
traceroute google.com

# See your local ARP cache (IP → MAC mappings)
arp -a

# Inspect your routing table
ip route show          # Linux
netstat -rn            # macOS / BSD
route print            # Windows
```

Notice that `traceroute` shows routers (Layer 3 hops) but not switches — switches are invisible to Layer 3 tooling.

---

## Use It

### Where Each Device Appears in Real Infrastructure

| Context | Device | Why |
|---------|--------|-----|
| Connecting workstations within a floor/rack | Managed switch | Per-port isolation, VLANs, link aggregation |
| Connecting floors or buildings | Layer 3 switch or router | Need inter-VLAN routing, broadcast isolation |
| Home/office internet edge | Router (+ built-in switch + WAP) | NAT, DHCP, routing to ISP |
| Data center top-of-rack | High-density managed switch (48-96 ports) | East-west server traffic within same subnet |
| Data center spine layer | Layer 3 switches or routers | Route between racks/pods, ECMP load balancing |
| Cloud VPC | Virtual router (implicit) | AWS VPC router, GCP VPC routes — you configure route tables, not physical hardware |

**AWS analogy:**
- **Security Groups** and **Subnets** replace switch VLANs for isolation.
- **Route Tables** in a VPC are the routing table of a virtual router.
- **Internet Gateway** and **NAT Gateway** fill the role of the edge router.
- **Transit Gateway** is a managed router connecting multiple VPCs (analogous to a core enterprise router).

**Managed vs. Unmanaged Switches:**
Unmanaged switches behave almost like smart hubs — plug-and-play, no configuration. Managed switches (Cisco Catalyst, Juniper EX, Arista) support VLANs, STP, LACP, port mirroring, and QoS — essential for anything beyond a home network.

---

## Common Pitfalls

- **Treating a switch as a router.** A switch (without Layer 3 capabilities) cannot route between subnets. If two devices on different VLANs can't communicate, the missing link is almost always a router or Layer 3 switch providing inter-VLAN routing.

- **Forgetting that switches flood unknown unicast.** Until the CAM table is populated, a switch floods frames like a hub. During ARP storms or MAC flooding attacks, a switch effectively becomes a hub. Rate-limiting and port security mitigate this.

- **Assuming MAC addresses are globally unique in practice.** CAM tables rely on MAC uniqueness, but VMs, Docker containers, and some NICs allow MAC spoofing. In multi-tenant environments, MAC collisions can cause frames to be silently delivered to the wrong host.

- **Ignoring broadcast domain size.** A flat Layer 2 network with thousands of hosts generates enormous broadcast traffic (ARP, DHCP, multicast). Symptoms: unexplained CPU spikes on servers, slow ARP resolution. Fix: segment with VLANs and route between them.

- **Conflating Layer 3 switches with routers.** A Layer 3 switch can route between VLANs at wire speed (hardware ASICs), but typically lacks WAN interfaces, NAT, stateful firewall, and dynamic routing protocol support that a dedicated router provides. Choose the right tool: Layer 3 switches for high-speed intra-datacenter routing, routers for WAN edges.

---

## Exercises

1. **Easy — Layer identification:** You run `ping 192.168.1.1` from your laptop to your router. List every device (hub/switch/router) a packet traverses on a typical home network, and identify which layer each device uses to make its forwarding decision.

2. **Medium — Broadcast domain analysis:** A company has one switch with 40 ports, no VLANs, and a router connecting it to the internet. An engineer adds 3 VLANs (VLAN 10: Sales, VLAN 20: Engineering, VLAN 30: Finance). How many broadcast domains now exist? How many collision domains? What additional configuration is needed for the VLANs to reach the internet?

3. **Hard — Design exercise:** Design the network topology for an office with 200 workstations, 10 servers, a VoIP system, and an internet uplink. Specify how many switches and routers you need, how you would segment the network (subnets/VLANs), and explain why you made each decision in terms of collision domains, broadcast domains, and security isolation.

---

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|------------------------|
| Hub | An older type of switch | A Layer 1 repeater with no address awareness that broadcasts every frame to every port |
| Switch | Routes traffic between networks | A Layer 2 device that forwards frames within a single network using MAC addresses |
| Router | Just connects you to Wi-Fi | A Layer 3 device that routes packets between distinct IP networks using a routing table |
| Collision domain | Same as broadcast domain | A network segment where simultaneous transmissions cause collisions; each switch port is its own collision domain |
| Broadcast domain | Broken by switches | A segment where a broadcast frame reaches every device; only routers (or VLANs) break broadcast domains |
| CAM Table | Some internal switch memory | Content Addressable Memory: the switch's MAC-to-port mapping table, learned dynamically |
| NAT | Just a firewall | Network Address Translation — rewrites IP addresses at the router boundary to allow private IPs to share a public IP |

---

## Further Reading

- [Cisco Networking Academy — Introduction to Networks](https://www.netacad.com/courses/networking/ccna-introduction-networks) — the canonical hands-on foundation for everything in this lesson.
- [RFC 826 — Ethernet Address Resolution Protocol](https://datatracker.ietf.org/doc/html/rfc826) — the original ARP spec; understanding ARP explains why switches learn MAC addresses the way they do.
- [IEEE 802.1Q — VLAN Tagging Standard](https://standards.ieee.org/ieee/802.1Q/10968/) — the spec behind VLANs and how switches tag frames to maintain broadcast domain separation.
- [AWS VPC Documentation — Route Tables](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Route_Tables.html) — maps the physical router concept to the cloud; essential for cloud networking work.
- [Julia Evans — Networking Zines](https://wizardzines.com/zines/networking/) — concise, illustrated reference covering DNS, TCP, HTTP — complements this lesson with the protocol layers above Layer 3.
