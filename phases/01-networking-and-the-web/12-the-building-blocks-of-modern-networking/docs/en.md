# The Building Blocks of Modern Networking

> The seven categories of components that every network — home, office, cloud — is built from. Know the parts; reason about the system.

**Type:** Learn
**Prerequisites:** Basic networking
**Time:** ~20 minutes

---

## The Problem

Networks look like magic until you understand the parts. "The internet" is just wires, switches, routers, firewalls, and protocols — each doing a specific job. Once you can name what each component does and how they fit together, network problems stop being mysterious and become diagnosable.

This lesson walks through the seven categories of building blocks that make up modern networks, from the smallest home Wi-Fi to global cloud infrastructure. For each category, you get the role, the leading technologies, and where it fits in a real architecture.

---

## The Concept

### The seven categories

```
   ┌────────────────────────────────────────────────────────────┐
   │  1. Core Networking          → switches, routers, SD-WAN    │
   │  2. Network Services         → DNS, DHCP, NTP              │
   │  3. Network Security         → firewalls, VPN, IDS/IPS     │
   │  4. Traffic Management        → LB, reverse proxy, gateway │
   │  5. Identity & Trust          → IdP, RADIUS, PKI           │
   │  6. Operations                → SIEM, NMS, alerting       │
   │  7. Edge & Infrastructure     → AP, IoT GW, NFV           │
   └────────────────────────────────────────────────────────────┘
```

These categories are present in every network — from a coffee shop Wi-Fi (subset) to a global enterprise WAN (full set).

---

### 1. Core Networking

**Switches** connect devices within a local network. Every office has dozens of them.

- Operate at Layer 2 (data link layer) using MAC addresses
- Forward frames based on destination MAC
- Managed switches add VLANs, port security, traffic monitoring
- Unmanaged switches just work — no configuration

**Routers** move packets between different networks. Your gateway to the internet is a router.

- Operate at Layer 3 (network layer) using IP addresses
- Maintain routing tables; pick the best path for each packet
- Home routers combine switch + router + firewall + Wi-Fi in one box
- Enterprise routers are modular and high-performance (Cisco, Juniper, Arista)

**SD-WAN (Software-Defined WAN)** is how modern companies connect branch offices. Software-defined, flexible, much cheaper than traditional MPLS.

- Replaces dedicated circuits with broadband + intelligent routing
- Centralized policy management across all branches
- Optimizes traffic across multiple links (MPLS, broadband, LTE)
- Examples: Cisco Viptela, VMware VeloCloud, Fortinet, Versa

**Why it matters:** every network you touch has switches and routers. Knowing the difference helps you debug ("the switch port is down" vs "the router can't reach the next hop") and design ("add a VLAN" vs "set up BGP").

---

### 2. Network Services

The invisible services that make networks work. Most users never see them, but every packet depends on them.

**DNS (Domain Name System)** translates domain names to IP addresses. The phone book of the internet.

- Hierarchical, distributed, eventually consistent
- The most critical service on the internet; if DNS is down, nothing works
- Authoritative DNS owns the zone; recursive DNS resolves queries
- Common implementations: BIND, Unbound, Route 53, Cloudflare DNS

**DHCP (Dynamic Host Configuration Protocol)** hands out IP addresses automatically. Your laptop getting an IP on Wi-Fi is DHCP.

- Lease-based: addresses are assigned for a period, then renewed
- Without DHCP, every device would need a static IP (operational nightmare)
- Includes default gateway, DNS servers, and other config

**NTP (Network Time Protocol)** keeps clocks synchronized across all systems.

- Critical for log correlation, distributed transactions, security certificates
- Stratum 0 = atomic clock; stratum 1 = NTP server connected to stratum 0; etc.
- Without NTP, certificates fail, distributed locks fail, logs are unreadable

**Why it matters:** DNS, DHCP, and NTP outages are some of the most common causes of "everything is broken" symptoms. Knowing they exist helps you check them first.

---

### 3. Network Security

The components that keep bad traffic out and good traffic in.

**Firewalls** are your first line of defense. They enforce rules about which traffic is allowed.

- **Packet-filtering firewalls** — basic; inspect headers, allow/deny based on rules
- **Stateful firewalls** — track connections; only allow return traffic for established connections
- **Next-generation firewalls (NGFW)** — inspect traffic at the application layer (Layer 7); detect malware, intrusion patterns, application misuse
- Common vendors: Palo Alto, Fortinet, Cisco Firepower, pfSense (open source)

**VPNs (Virtual Private Networks)** create encrypted tunnels for remote access and site-to-site connections.

- **Remote-access VPN** — individual user connects from outside (SSL VPN, IPsec)
- **Site-to-site VPN** — two networks connect over the internet (IPsec)
- Used for: remote work, connecting branch offices, accessing cloud resources privately
- Modern alternative: Zero Trust Network Access (ZTNA)

**IDS / IPS (Intrusion Detection / Prevention Systems)** detect and block malicious traffic before it reaches your servers.

- **IDS** — detects and alerts; does not block
- **IPS** — detects and blocks in real time
- Signature-based (known patterns) or anomaly-based (deviation from baseline)
- Often integrated into next-gen firewalls

**Why it matters:** security is not a feature you add at the end. It is the foundation of the network. Skipping it produces a network you cannot put anything sensitive on.

---

### 4. Traffic Management (Delivery)

The components that route, balance, and shape traffic.

**Load Balancers** distribute requests across multiple servers. One server goes down; users never notice.

- **L4 load balancer** — distributes TCP/UDP connections; based on IP/port; fast, simple
- **L7 load balancer** — distributes HTTP requests; can route by path, host, headers; smarter, more flexible
- Algorithms: round-robin, least-connections, weighted, IP-hash, consistent hash
- Common: AWS ALB/NLB, HAProxy, NGINX, F5, Envoy

**Reverse Proxy** sits in front of your backend servers, handling SSL termination, caching, and routing.

- NGINX, HAProxy, Envoy, Traefik
- Often combined with load balancing
- Can terminate TLS, compress responses, add headers, rate-limit

**API Gateway** manages all your API traffic. Like a reverse proxy with API-specific features.

- Routing, rate limiting, authentication, transformation, monitoring
- Examples: Kong, Apigee, AWS API Gateway, Tyk
- Often used in microservices architectures

**Why it matters:** without these components, every service must be reached directly, scaled manually, and secured individually. With them, you have a single ingress point that handles traffic intelligently.

---

### 5. Identity & Trust

Who is calling, and can we trust them?

**Identity Provider (IdP)** is your single source of truth for user authentication.

- Think Okta, Azure AD, Auth0, Google Workspace, OneLogin
- Manages users, groups, passwords, MFA
- Issues tokens (SAML, OIDC, JWT) that downstream services trust
- Centralizes security policy; one place to enforce MFA, password rules, session policy

**RADIUS / AAA** handles network device authentication.

- RADIUS = Remote Authentication Dial-In User Service
- AAA = Authentication, Authorization, Accounting
- Authenticates VPN users, Wi-Fi users, switch administrators
- Older protocol; still ubiquitous in enterprise networks

**PKI (Public Key Infrastructure)** manages digital certificates and encryption keys.

- Issues, revokes, and manages X.509 certificates
- The foundation of HTTPS, code signing, email encryption, smart cards
- Without PKI, HTTPS does not exist

**Why it matters:** most security incidents are identity failures — compromised credentials, missing MFA, over-privileged accounts. Centralizing identity is the highest-leverage security investment.

---

### 6. Operations

Who watches the network?

**SIEM (Security Information and Event Management)** collects and analyzes security events across your entire infrastructure.

- Ingests logs from firewalls, IDS/IPS, endpoints, applications, cloud
- Correlates events to detect attacks (e.g., 100 failed logins then a successful one)
- Stores long-term logs for compliance and forensics
- Examples: Splunk, Elastic Security, Microsoft Sentinel, IBM QRadar

**NMS (Network Monitoring System)** monitors network health and performance.

- SNMP-based polling of routers, switches, firewalls
- Latency and packet loss monitoring
- Alerting before users start complaining
- Examples: Datadog, New Relic, PRTG, Zabbix, LibreNMS

**Why it matters:** without monitoring, you learn about network problems from users. With monitoring, you learn about them first.

---

### 7. Edge & Infrastructure

The boundary between the network and the physical world.

**Access Points** provide Wi-Fi coverage.

- Enterprise APs are managed centrally (controller-based)
- Support for multiple SSIDs, VLANs, 802.1X authentication
- Vendors: Cisco Meraki, Aruba, Ubiquiti, Mist (Juniper)

**IoT Gateway** connects sensors, cameras, and smart devices to the network.

- Often runs at the edge where devices cannot speak IP directly
- Translates protocols (Zigbee, LoRa, Modbus) to IP
- The bridge between operational technology (OT) and IT

**NFV (Network Functions Virtualization)** runs network functions as software instead of dedicated hardware.

- Virtual firewalls, virtual routers, virtual load balancers
- Replaces expensive dedicated appliances with software running on commodity hardware
- The foundation of modern telco networks (vEPC, vRAN)

**Why it matters:** edge devices are where users meet the network. Their performance, security, and reliability directly affect user experience.

---

## Build It / In Depth

### A reference architecture: a mid-size company

```
                          Internet
                             │
                             ▼
                  ┌──────────────────────┐
                  │  Edge firewall       │
                  │  (NGFW with IPS)     │
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │  Perimeter router    │
                  │  (BGP, NAT)          │
                  └──────────┬───────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
       ┌───────────┐  ┌───────────┐  ┌───────────┐
       │ Switch A  │  │ Switch B  │  │ Switch C  │
       └─────┬─────┘  └─────┬─────┘  └─────┬─────┘
             │              │              │
             ▼              ▼              ▼
       ┌────────────────────────────────────────┐
       │   Servers (web, app, DB, etc.)         │
       └────────────────────────────────────────┘

   Services:
     ┌──────────┐  ┌──────────┐  ┌──────────┐
     │   DNS    │  │   DHCP   │  │   NTP    │
     └──────────┘  └──────────┘  └──────────┘

   Identity:
     ┌──────────┐  ┌──────────┐
     │   IdP    │  │   PKI    │
     └──────────┘  └──────────┘

   Operations:
     ┌──────────┐  ┌──────────┐
     │   SIEM   │  │   NMS    │
     └──────────┘  └──────────┘
```

This is a standard three-tier enterprise network. Every box corresponds to one of the seven categories.

---

### Mapping categories to problems

| Problem | Likely category |
|---|---|
| Cannot reach a website | DNS (resolution), Routing, Firewall (blocked) |
| Slow downloads | Switching (congestion), Routing (suboptimal path), WAN link |
| Authentication fails | Identity (wrong creds, MFA failure), DNS (IdP unreachable) |
| Latency spikes | WAN link (loss/retransmits), Load balancer (slow backend), DNS (slow resolution) |
| Security incident | Identity (compromised creds), Firewall (rule missed), IDS (silent) |
| Compliance audit | SIEM (logs missing), PKI (cert expired), Identity (access logs) |

---

## Use It

### When to use which component

| Need | Use |
|---|---|
| Connect devices in one room | Unmanaged switch |
| Connect devices across floors | Managed switch with VLANs |
| Connect offices | SD-WAN or site-to-site VPN |
| Remote work | SSL VPN or Zero Trust Network Access |
| Protect against web attacks | Next-gen firewall + WAF |
| Distribute traffic | Load balancer (L4 or L7) |
| Authenticate users | Identity provider (Okta, Azure AD) |
| Encrypt web traffic | TLS certificates from PKI |
| Monitor security events | SIEM (Splunk, Elastic Security) |
| Monitor network health | NMS (Datadog, PRTG) |

### The reference vendors by category

| Category | Common vendors |
|---|---|
| Switches | Cisco, Arista, Juniper, HPE Aruba, Ubiquiti |
| Routers | Cisco, Juniper, Nokia, MikroTik |
| SD-WAN | Cisco Viptela, VMware VeloCloud, Fortinet, Versa |
| Firewalls | Palo Alto, Fortinet, Cisco Firepower, pfSense |
| VPN | Cisco AnyConnect, WireGuard, OpenVPN |
| Load balancers | F5, Citrix ADC, HAProxy, NGINX, AWS ALB/NLB |
| API gateways | Kong, Apigee, AWS API Gateway, Tyk |
| Identity | Okta, Azure AD, Auth0, Google Workspace |
| SIEM | Splunk, Elastic Security, Microsoft Sentinel, IBM QRadar |
| NMS | Datadog, New Relic, PRTG, Zabbix |

---

## Common Pitfalls

- **Treating DNS as "just a service."** DNS is the most critical infrastructure component. Outages take down everything.

- **Putting security devices outside the firewall.** If the firewall is the only ingress, putting IDS inside the firewall means it sees only traffic that already passed the firewall. Defense in depth requires both.

- **Overlooking NTP.** Without synchronized clocks, certificates fail, logs are unreadable, distributed systems break. Set up NTP on day one.

- **Centralizing identity without considering availability.** If your IdP is down, no one can log in. Use multiple regions, redundant services, or cached credentials.

- **Neglecting monitoring until something breaks.** SIEM and NMS need historical data to be useful. Deploy them early; tune them over time.

- **Treating IoT devices as trusted.** They are often the weakest link. Segment them on their own VLAN; restrict their network access.

- **Confusing load balancers with API gateways.** Both distribute traffic, but they have different features. Load balancers balance; API gateways also authenticate, rate-limit, transform, and monitor.

---

## Exercises

1. **Easy** — Pick three of the seven categories. For each, give a concrete example of a component and what it does.

2. **Medium** — A new office needs network infrastructure for 50 employees. Design the network: which components from each category, what vendors, and what is the approximate cost.

3. **Hard** — A company is being audited for SOC 2 compliance. Map each SOC 2 control to the network component that addresses it. Identify gaps in the typical mid-size company's network.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Switch | A box with cables | A Layer 2 device that forwards Ethernet frames within a local network based on MAC addresses |
| Router | Another box | A Layer 3 device that forwards IP packets between networks based on routing tables |
| DNS | The internet's phone book | Domain Name System — translates domain names to IP addresses; the most critical service on the internet |
| DHCP | IP assignment | Dynamic Host Configuration Protocol — automatically assigns IP addresses to devices on a network |
| NTP | Time sync | Network Time Protocol — keeps clocks synchronized across systems; essential for certificates, logs, distributed systems |
| Firewall | A wall | A device that enforces rules about which traffic is allowed; NGFW inspects application-layer traffic |
| Load balancer | A traffic cop | A device that distributes requests across multiple backend servers for availability and throughput |
| VPN | A tunnel | An encrypted connection over a public network; used for remote access and site-to-site connectivity |
| IdP | Login service | Identity Provider — the single source of truth for user authentication (Okta, Azure AD, Auth0) |
| SIEM | A log collector | Security Information and Event Management — collects and correlates security events across the infrastructure |
| PKI | Certificates | Public Key Infrastructure — manages digital certificates and encryption keys; the foundation of HTTPS |

---

## Further Reading

- **"Computer Networking: A Top-Down Approach"** — Kurose and Ross; the canonical networking textbook: https://www.pearson.com/store/p/computer-networking-a-top-down-approach/
- **Cisco Networking Academy** — free courses on networking fundamentals: https://www.netacad.com/
- **Cloudflare Learning Center** — practical networking concepts explained well: https://www.cloudflare.com/learning/
- **NIST Cybersecurity Framework** — the standards for network security: https://www.nist.gov/cyberframework
- **AWS Networking & Content Delivery** — how AWS implements these patterns: https://aws.amazon.com/products/networking/