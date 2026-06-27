# Network Debugging Commands Every Engineer Should Know

> When someone says "it's a network issue," these commands are how you find out whether they're right — and exactly where the problem lives.

**Type:** Learn
**Prerequisites:** How the Internet Works, DNS Deep Dive, TCP/IP Fundamentals
**Time:** ~35 minutes

---

## The Problem

A user files a ticket: "The API is down." Your first instinct is to check the service logs — they look clean. The service thinks it is healthy. But requests are failing. Is it the service, the network, the DNS, a firewall rule, or a misconfigured load balancer upstream? Without the right commands, you are guessing. You restart the service, nothing changes, and thirty minutes later someone is escalating.

Network debugging is not magic — it is systematic elimination. The transport layer, the DNS layer, the routing layer, and the socket layer each expose different symptoms. The commands in this lesson give you a tool for each layer. Used in sequence, they let you isolate a fault in minutes rather than hours: you go from "something is wrong somewhere" to "packet loss starts at hop 4, which is owned by the upstream ISP."

This skill compounds over a career. Developers who can confidently triage a network issue own their incidents. Those who cannot end up dependent on a network team that may not be available at 2 a.m.

---

## The Concept

### The Diagnostic Stack

Treat network debugging as a layer-by-layer interrogation that mirrors the OSI model. Start at the bottom (reachability) and move up (DNS, sockets, HTTP, bandwidth):

```
┌─────────────────────────────────────────┐
│  Layer 7 — Application / HTTP           │  curl -I, dig
├─────────────────────────────────────────┤
│  Layer 4 — Transport / Sockets          │  ss, nmap
├─────────────────────────────────────────┤
│  Layer 3 — Network / Routing            │  ip route, ip neigh, traceroute, mtr
├─────────────────────────────────────────┤
│  Layer 2 — Data Link / ARP              │  ip neigh, ip link
├─────────────────────────────────────────┤
│  Layer 1 — Reachability / ICMP          │  ping
└─────────────────────────────────────────┘
Cross-cutting: tcpdump / tshark (sees all layers at once)
               iperf3 (tests throughput end-to-end)
               ssh / sftp (remote access to run all of the above)
```

Each command answers one or two specific questions. Picking the right command for the right layer is the skill.

### Command Reference

| Command | Layer | Core question it answers |
|---|---|---|
| `ping` | L3 | Is the host reachable? What is the round-trip time? |
| `traceroute` / `tracert` | L3 | Which path do packets take, and where do they slow or stop? |
| `mtr` / `pathping` | L3 | Which hop has intermittent packet loss over time? |
| `ip addr` / `ipconfig /all` | L2/L3 | What is this machine's IP, MAC, and interface state? |
| `ip route` | L3 | Which gateway will this machine use? Is the routing table correct? |
| `ip neigh` | L2/L3 | Is the ARP table stale or showing a duplicate IP? |
| `ss -tulpn` | L4 | Is the service actually listening on the expected port? |
| `dig` | L7 | What IP does DNS return for this name? Which server answered? |
| `curl -I` | L7 | What HTTP status, headers, and redirect chain does the endpoint return? |
| `tcpdump` / `tshark` | All | What packets are actually on the wire? |
| `iperf3` | L3/L4 | What is the real throughput between two hosts? |
| `nmap` | L3/L4 | Which ports on a host are open/filtered from a remote perspective? |
| `ssh` | L4/L7 | Can I open a secure shell to run remote diagnostics? |
| `sftp` | L4/L7 | Can I retrieve logs or push files over SSH? |

### Mental Model: Rule Out, Don't Rule In

A common mistake is jumping to the most sophisticated tool first. Start with `ping` — if the host does not reply, there is no point running `curl`. Follow this decision tree:

```
Host unreachable? ──► ping / traceroute / mtr
      ↓ reachable
Wrong IP from DNS? ──► dig
      ↓ DNS correct
Port not open? ──► ss (local), nmap (remote)
      ↓ port open
Wrong HTTP response? ──► curl -I
      ↓ HTTP OK
Slow throughput? ──► iperf3
      ↓
Need packet-level evidence? ──► tcpdump / tshark
```

---

## Build It / In Depth

### 1. Verify Reachability — `ping`

`ping` sends ICMP Echo Requests and reports round-trip time (RTT) and loss.

```bash
ping -c 5 api.example.com
# -c 5  → send exactly 5 packets (omit on Windows; Ctrl+C to stop)
```

Sample output:

```
PING api.example.com (203.0.113.42): 56 data bytes
64 bytes from 203.0.113.42: icmp_seq=0 ttl=56 time=12.4 ms
64 bytes from 203.0.113.42: icmp_seq=1 ttl=56 time=11.9 ms
64 bytes from 203.0.113.42: icmp_seq=2 ttl=56 time=89.2 ms   ← spike
64 bytes from 203.0.113.42: icmp_seq=3 ttl=56 time=12.1 ms
64 bytes from 203.0.113.42: icmp_seq=4 ttl=56 time=12.3 ms
--- api.example.com ping statistics ---
5 packets transmitted, 5 received, 0% packet loss
round-trip min/avg/max/stddev = 11.9/27.6/89.2/30.8 ms
```

The stddev spike at icmp_seq=2 signals intermittent jitter — the path is reachable but not stable. A 0% loss with normal RTT means L3 connectivity is fine; investigate higher layers.

### 2. Trace the Path — `traceroute` (Linux/macOS) / `tracert` (Windows)

Each hop is a router between you and the destination. `traceroute` sends probes with increasing TTL values and records which router sends back a TTL-exceeded ICMP message.

```bash
traceroute -n api.example.com   # -n skips reverse-DNS to speed it up
```

```
traceroute to api.example.com (203.0.113.42), 30 hops max
 1  192.168.1.1      1.2 ms    1.1 ms    1.1 ms   ← your gateway
 2  10.0.0.1         3.4 ms    3.2 ms    3.3 ms   ← ISP edge
 3  * * *                                          ← router drops ICMP (not a failure)
 4  198.51.100.9     11.2 ms   11.0 ms   11.3 ms
 5  203.0.113.42     12.1 ms   11.9 ms   12.0 ms  ← destination
```

`* * *` means the router at that hop silently drops ICMP — this is a firewall policy, not a routing failure. If the trace stops completely before the destination, that hop is the likely fault point.

### 3. Continuous Per-Hop Measurement — `mtr`

`mtr` combines `ping` and `traceroute` into a live, updating view. It catches intermittent loss that a single `traceroute` snapshot misses.

```bash
mtr --report --report-cycles 60 api.example.com
# Runs 60 cycles then prints a summary report
```

```
HOST: mybox                   Loss%   Snt   Last   Avg  Best  Wrst StDev
  1. 192.168.1.1               0.0%    60    1.1   1.1   1.0   1.5   0.1
  2. 10.0.0.1                  0.0%    60    3.2   3.2   2.9   4.0   0.2
  3. 203.0.113.1               4.0%    60   11.2  11.4  10.8  19.1   1.3  ← 4% loss
  4. 203.0.113.42              4.0%    60   12.0  12.1  11.5  20.0   1.2
```

If loss first appears at hop 3 and persists to the destination, hop 3 is the culprit. If hop 3 shows loss but hop 4 does not, the intermediate router is merely rate-limiting ICMP — normal behavior, not a real problem.

### 4. Inspect Local Interfaces — `ip addr` / `ipconfig /all`

```bash
ip addr show eth0
```

```
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc pfifo_fast state UP
    link/ether 52:54:00:ab:cd:ef brd ff:ff:ff:ff:ff:ff
    inet 10.0.1.5/24 brd 10.0.1.255 scope global eth0
    inet6 fe80::5054:ff:feab:cdef/64 scope link
```

Verify: the IP matches expectations, the interface state is `UP`, and the MTU is 1500 (a mismatch here causes jumbo-frame or fragmentation issues).

### 5. Check the Routing Table — `ip route`

```bash
ip route show
```

```
default via 10.0.1.1 dev eth0 proto dhcp
10.0.1.0/24 dev eth0 proto kernel scope link src 10.0.1.5
```

The `default` line shows your gateway. If this is missing or points to the wrong IP, all traffic to external hosts fails. After changing a gateway, confirm it here before blaming anything else.

### 6. Inspect ARP Cache — `ip neigh`

```bash
ip neigh show
```

```
10.0.1.1 dev eth0 lladdr 52:54:00:11:22:33 REACHABLE
10.0.1.7 dev eth0 lladdr 52:54:00:aa:bb:cc STALE
```

A `STALE` or `FAILED` entry for your gateway means ARP has not confirmed the MAC recently. A duplicate IP on the LAN (two hosts claiming the same IP) shows as two ARP entries for the same IP with different MACs — this causes intermittent connectivity for both hosts.

### 7. Check Listening Sockets — `ss`

`ss` replaced `netstat`. Use it to verify a process is bound where you expect.

```bash
ss -tulpn
# -t TCP  -u UDP  -l listening  -p show process  -n numeric ports
```

```
Netid  State   Recv-Q  Send-Q  Local Address:Port  Peer Address:Port  Process
tcp    LISTEN  0       128     0.0.0.0:8080        0.0.0.0:*          users:(("java",pid=1234,fd=42))
tcp    LISTEN  0       128     127.0.0.1:5432      0.0.0.0:*          users:(("postgres",pid=891,fd=5))
```

Key details:
- `0.0.0.0:8080` — bound on all interfaces, reachable externally.
- `127.0.0.1:5432` — bound only to loopback; external connections will be refused. A common misconfiguration when Postgres needs to accept remote connections.

### 8. Resolve DNS — `dig`

```bash
dig api.example.com A
dig api.example.com A @8.8.8.8   # query a specific resolver
dig +short api.example.com A      # terse output
```

Full output:

```
;; ANSWER SECTION:
api.example.com.  300  IN  A  203.0.113.42

;; Query time: 12 msec
;; SERVER: 10.0.1.1#53
```

Check: the IP returned, the TTL (low TTL = entries expire fast; watch for flapping), and which server answered (is it your local resolver or a public one?). Compare `@8.8.8.8` vs your local resolver — a difference means your internal DNS is stale or misconfigured.

### 9. Inspect HTTP Headers — `curl -I`

```bash
curl -I https://api.example.com/health
curl -Lv https://api.example.com/health  # -L follow redirects, -v verbose
```

```
HTTP/2 200
content-type: application/json
cache-control: no-cache
x-request-id: abc123
```

`-I` sends a HEAD request — no response body is downloaded. Use it to check status codes, redirect chains, TLS cert details (via `-v`), and cache headers without pulling data. A `301` instead of `200` often means the client is hitting an HTTP endpoint that redirects to HTTPS, adding a round trip.

### 10. Capture Packets — `tcpdump`

```bash
# Capture traffic to/from a host, write to file
tcpdump -i eth0 -n host 203.0.113.42 -w /tmp/capture.pcap

# Live: show only HTTP SYN packets
tcpdump -i eth0 -n 'tcp port 80 and tcp[tcpflags] & tcp-syn != 0'
```

`tcpdump` is the ground truth. When logs and metrics disagree, packet captures show exactly what was sent and what was received. Key flags: `-i` selects the interface, `-n` avoids reverse DNS, `-w` saves for analysis in Wireshark/tshark. Keep captures short and filtered — unfiltered captures on a busy interface fill disk quickly.

```bash
# Read a saved capture and display HTTP requests
tshark -r /tmp/capture.pcap -Y "http.request"
```

### 11. Measure Throughput — `iperf3`

`iperf3` requires a server process on the remote end:

```bash
# On the server:
iperf3 -s                # listens on port 5201

# On the client:
iperf3 -c 10.0.1.10 -t 10 -P 4
# -t 10  → run for 10 seconds
# -P 4   → 4 parallel streams (saturates multi-queue NICs)
```

```
[ ID] Interval       Transfer     Bandwidth
[  4] 0.00-10.00 s   1.10 GBytes   943 Mbits/sec
```

If you are seeing 50 Mbits/sec on a 1 Gbps link, the bottleneck is real — look for CPU saturation, NIC offload issues, or a half-duplex mismatch (`ip link` will show `HALF-DUPLEX` if so).

### 12. Remote Access — `ssh` and `sftp`

```bash
# Connect to a remote host to run all of the above commands there
ssh -v user@10.0.1.10          # -v verbose, useful for TLS/auth debugging

# Transfer logs from a remote host
sftp user@10.0.1.10
sftp> get /var/log/app/error.log ./
```

`ssh -v` (or `-vvv` for maximum verbosity) shows exactly where a connection stalls — key exchange, authentication, or post-auth. This distinguishes "SSH daemon is not running" from "firewall blocks port 22" from "wrong key."

### 13. Remote Port Scan — `nmap`

```bash
# Scan common ports on a host
nmap -sV 10.0.1.10            # -sV probe service versions

# Scan a specific port
nmap -p 8080 10.0.1.10

# Scan a subnet (use carefully in production)
nmap -sn 10.0.1.0/24          # ping scan only, no port probing
```

`nmap` shows what is reachable *from where you run it* — this is not the same as what `ss` shows locally. A service that `ss` says is listening on `0.0.0.0:8080` but that `nmap` shows as `filtered` means a firewall between you and the host is blocking the port.

---

## Use It

### When to Reach for Each Tool

| Symptom | Start Here | Then |
|---|---|---|
| Total connectivity failure | `ping` | `traceroute`/`mtr` |
| Wrong IP / DNS resolution | `dig` | compare internal vs. external resolver |
| Port refused / connection reset | `ss -tulpn` (local), `nmap` (remote) | `tcpdump` to see RST |
| HTTP error or redirect loop | `curl -Iv` | check TLS cert, status code |
| Slow throughput, intermittent drops | `mtr` per-hop loss | `iperf3` to isolate bandwidth |
| ARP / LAN issues | `ip neigh` | check for duplicate IPs |
| Need to see raw packets | `tcpdump` | open `.pcap` in Wireshark |
| Pulling logs from a sick host | `ssh`, `sftp` | |

### Tooling in Cloud Environments

Cloud providers (AWS, GCP, Azure) add firewall layers (Security Groups, VPC Firewall Rules, NSGs) that exist outside the OS. `ss` might show a service listening; `nmap` from outside might show the port filtered. Check cloud console firewall rules before concluding there is an application bug.

**AWS VPC Flow Logs** and **GCP Packet Mirroring** are managed equivalents of `tcpdump` for cloud-level traffic analysis. Use them when you cannot install tools on the host itself.

**Cloud-native diagnostics:**
- AWS Reachability Analyzer: graphically traces a path through VPC topology.
- `aws ec2 describe-route-tables`: programmatic equivalent of `ip route`.
- Kubernetes: `kubectl exec -it <pod> -- bash`, then run the same commands inside the pod.

---

## Common Pitfalls

- **Treating `* * *` in traceroute as a failure.** Many routers drop ICMP TTL-exceeded messages by policy. If the trace successfully reaches hops beyond the `* * *` line, those routers are fine — they just do not advertise themselves. Only worry if the trace stops completely before the destination.

- **Checking `ss` locally and concluding the port is reachable remotely.** `ss` shows the kernel's socket state. A service can be `LISTEN`ing on `0.0.0.0:8080` while `iptables` or a cloud Security Group blocks that port entirely from external traffic. Always verify from the client side with `nmap` or `curl`.

- **Using `ping` to prove a firewall is open.** Many firewalls block ICMP while passing TCP. A host that does not reply to `ping` can still have port 443 fully open. `ping` tests ICMP; `nmap -p 443` tests TCP.

- **Running `tcpdump` without a filter on a busy interface.** Unfiltered captures on a 10 Gbps interface generate gigabytes of data in seconds and can themselves degrade performance. Always use `host`, `port`, or BPF filters. Write to a file (`-w`) and analyze offline.

- **Forgetting that `mtr` output varies with direction.** Loss at a hop in `mtr` from your machine to the target does not mean the reverse path is also lossy. TCP is bidirectional; run `mtr` from the remote host back to you as well (via SSH) before blaming a single hop.

- **Reading stale `ip neigh` entries as current state.** ARP cache entries age out. An `ip neigh` entry marked `STALE` is not necessarily wrong — it just has not been refreshed recently. Trigger traffic or use `arping` to force a fresh lookup before concluding the ARP table is corrupt.

---

## Exercises

1. **Easy — Map a path end to end.** Run `traceroute -n google.com` from your machine. Identify how many hops are inside your local network vs. your ISP vs. Google's network. Then run `mtr --report --report-cycles 20 google.com` and note whether any hop shows loss above 0%.

2. **Medium — Diagnose a "port refused" error.** On a Linux VM or container, start a process bound to `127.0.0.1:8080` (e.g., `python3 -m http.server 8080`). Try to connect from another machine and observe the failure. Use `ss -tulpn` to see the bind address, explain why external connections fail, then rebind to `0.0.0.0:8080` and verify with both `ss` and `nmap` from the external machine.

3. **Hard — Isolate a throughput bottleneck.** Set up two hosts (VMs or containers) on the same network. Run `iperf3` between them and record the baseline throughput. Then introduce `tc qdisc add dev eth0 root netem delay 50ms loss 1%` (Linux traffic control) on one host to simulate latency and packet loss. Observe how throughput changes in `iperf3`, confirm the loss with `mtr`, and capture the retransmissions with `tcpdump`. Remove the netem rule and verify recovery.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Round-Trip Time (RTT)** | The time for data to reach the server | The time for a probe packet to reach the destination *and* for the reply to return to the sender — both directions combined |
| **TTL (Time To Live)** | A timer that expires after N seconds | A counter decremented by 1 at each router hop; when it hits 0 the packet is dropped, preventing routing loops |
| **ARP (Address Resolution Protocol)** | Part of DNS | A Layer 2 protocol that maps an IP address to a MAC address within a local network segment — completely separate from DNS |
| **Listening socket** | The server is ready for connections | The kernel has allocated a port and the process is blocked in `accept()`, waiting for inbound TCP connections |
| **Packet loss** | The network is broken | Some percentage of sent packets never arrive; small loss (< 0.1%) is normal on shared links; loss above 1% causes visible TCP throughput degradation due to retransmissions |
| **Filtered port (nmap)** | The service is down | A firewall is silently dropping packets destined for that port — the service may be running, but a network policy is blocking access |
| **tcpdump BPF filter** | A search query on captured output | A Berkeley Packet Filter expression evaluated *in the kernel* before packets are copied to userspace — filters happen at capture time, not at analysis time, which is why they improve performance |

---

## Further Reading

- [Linux `ip` command cheatsheet — Baturin (iproute2 docs)](https://baturin.org/docs/iproute2/)
- [tcpdump man page and filter syntax (official)](https://www.tcpdump.org/manpages/tcpdump.1.html)
- [mtr project documentation (GitHub)](https://github.com/traviscross/mtr)
- [Wireshark User Guide — analyzing `.pcap` files captured with tcpdump](https://www.wireshark.org/docs/wsug_html_chunked/)
- [Julia Evans — "Networking zines" (Wizard Zines)](https://wizardzines.com/zines/networking/) — concise visual reference for practicing engineers
