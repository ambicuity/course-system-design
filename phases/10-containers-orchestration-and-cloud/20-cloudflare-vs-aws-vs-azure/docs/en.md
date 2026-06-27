# Cloudflare vs. AWS vs. Azure

> Pick your cloud layer first — the edge, the region, or the enterprise backbone — then let the service catalog follow.

**Type:** Learn
**Prerequisites:** Content Delivery Networks, Serverless Functions, Cloud Infrastructure Fundamentals
**Time:** ~35 minutes

---

## The Problem

Your startup just landed a global user base. Requests from Singapore, São Paulo, and Stockholm all hit the same us-east-1 datacenter. Cold-start Lambda functions add 300 ms. Your S3 egress bill is climbing $4 000/month. A DDoS probe last week took the site down for 11 minutes.

You know you need "more cloud", but which cloud? AWS, Azure, and Cloudflare each solve a version of your problem — and each has a completely different mental model, pricing philosophy, and failure mode.

Choosing wrong means rearchitecting in 18 months. Choosing right means paying a fraction of the bill while serving sub-100 ms globally. The trap most engineers fall into is treating the three as interchangeable. They are not. AWS and Azure are **region-first**: you deploy to a datacenter region and traffic travels to you. Cloudflare is **edge-first**: your code lives in 300+ PoPs and traffic never leaves its nearest city.

This lesson maps the full capability surface of all three so you can make the decision deliberately.

---

## The Concept

### Mental Model: Three Different Delivery Philosophies

```
┌─────────────────────────────────────────────────────────────┐
│                  REQUEST FROM USER IN TOKYO                 │
└──────────────┬──────────────────────────────────────────────┘
               │
    ┌──────────▼──────────┐
    │  CLOUDFLARE MODEL   │  Code runs IN Tokyo PoP (<5 ms)
    │  (Edge-first)       │  300+ global locations, V8 isolates
    └─────────────────────┘

    ┌─────────────────────┐
    │  AWS MODEL          │  Traffic routed to ap-northeast-1
    │  (Region-first)     │  (Tokyo region) ≈ 10-30 ms
    │                     │  Or crosses ocean to us-east-1 ≈ 150 ms
    └─────────────────────┘

    ┌─────────────────────┐
    │  AZURE MODEL        │  Azure Japan East (Tokyo) ≈ 10-30 ms
    │  (Region-first,     │  Enterprise AD/Entra integration,
    │   enterprise lens)  │  global WAN backbone
    └─────────────────────┘
```

Cloudflare's edge runtime is built on **V8 isolates**, not containers or VMs. An isolate starts in microseconds (no OS boot, no JVM warmup). The trade-off: you get JavaScript/TypeScript/Wasm only, with a constrained API surface (no arbitrary syscalls, no filesystem). AWS Lambda and Azure Functions run full Linux containers, giving you any language but paying the cold-start tax.

### Core Service Comparison

| Capability | Cloudflare | AWS | Azure |
|---|---|---|---|
| **Edge Compute** | Workers (V8 isolates, 0 ms cold start) | Lambda@Edge / CloudFront Functions | Azure CDN Rules + Functions (limited) |
| **Serverless Compute** | Workers (also regional via Smart Placement) | Lambda (regional, any runtime) | Azure Functions (regional, any runtime) |
| **Object Storage** | R2 (S3-compatible, **zero egress fees**) | S3 | Azure Blob Storage |
| **Relational DB** | D1 (SQLite at the edge, distributed reads) | RDS / Aurora | Azure SQL / Cosmos DB |
| **Containers** | Cloudflare Containers (beta, runs in PoPs) | ECS / EKS / Fargate | AKS / ACI / App Service |
| **Sandboxes** | Workers Sandbox (isolated V8 per request) | Firecracker microVMs | Azure Container Instances |
| **Workflows** | Workflows (durable, step-based, built on DO) | Step Functions | Azure Durable Functions |
| **AI Agents SDK** | Agents SDK (built on Workers AI + DO) | Bedrock Agents | Azure AI Foundry / Semantic Kernel |
| **Vector & AI Search** | Vectorize (vector DB) + AI Gateway | OpenSearch / Bedrock Knowledge Bases | Azure AI Search |
| **Data Connectivity** | Hyperdrive (connection pool proxy to external DBs) | RDS Proxy | Azure SQL Connection Pooling |
| **AI Inference** | Workers AI (serverless GPU, 50+ models) | SageMaker / Bedrock | Azure OpenAI Service |
| **CDN** | Cloudflare CDN (300+ PoPs, Argo Smart Routing) | CloudFront (600+ PoPs) | Azure CDN / Front Door |
| **DNS** | Authoritative + Recursive (1.1.1.1), DNSSEC | Route 53 | Azure DNS |
| **Load Balancing** | Cloudflare LB (health checks, geo-steering, failover) | ALB / NLB / GLB | Azure Load Balancer / Front Door |
| **DDoS Protection** | Built-in, always-on, all plans | AWS Shield Standard/Advanced | Azure DDoS Protection |
| **WAF** | Cloudflare WAF (Managed Rules, Rate Limiting) | WAF (attached to CloudFront/ALB) | Azure WAF (Front Door/App Gateway) |
| **Key-Value Store** | Workers KV (eventually consistent, global reads) | DynamoDB / ElastiCache | Azure Cosmos DB / Cache for Redis |
| **Durable Objects** | Durable Objects (single-threaded actors, strong consistency) | No direct equivalent | No direct equivalent |

### Pricing Philosophy

This is where the models diverge most sharply.

**Cloudflare pricing model:**
- Workers Free tier: 100 000 requests/day, no cold starts ever
- Workers Paid: $5/month for 10 M requests, then $0.30 per million
- **R2: zero egress fees** — you only pay for storage ($0.015/GB-month) and operations
- D1: first 5 M rows read free per day; write costs apply above threshold
- No data transfer fees between Cloudflare services

**AWS pricing model:**
- Lambda: first 1 M requests free/month, then $0.20 per million + duration
- S3: $0.023/GB storage + **$0.09/GB egress** to the internet (the infamous egress tax)
- Data Transfer OUT is billed at every layer: EC2 → S3 → CloudFront → internet
- Reserved/Savings Plans needed to avoid 30–60% overpayment on steady workloads

**Azure pricing model:**
- Similar to AWS: pay-as-you-go with reserved instance discounts
- Blob Storage egress: $0.087/GB (first 10 GB/month free)
- Azure's differentiator is **enterprise licensing bundles** (M365/Windows Server hybrid benefits) reducing effective TCO for Microsoft shops
- Defender for Cloud, Entra ID, and Purview integrate at the identity/compliance layer with no equivalent in Cloudflare or AWS

### The Edge vs. Region Trade-off

```
                LATENCY vs. CAPABILITY SPECTRUM
Low latency  ←────────────────────────────────→  Full capability
             │                                 │
   CF Workers │    CF Workers (Smart Placement) │  AWS Lambda / EKS
   (Edge PoP) │    AWS Lambda@Edge              │  Azure AKS / Functions
              │    CF Durable Objects           │  AWS Step Functions
              │                                 │  Full OS, any language
              │                                 │  GPUs, large memory
```

Cloudflare Workers have hard limits: 128 MB memory, 10 ms CPU time per request (30 ms on paid), no native filesystem, no arbitrary TCP sockets (Hyperdrive and `connect()` work around this). AWS Lambda goes up to 10 GB memory, 15 minutes runtime, full POSIX environment. If you need to run ffmpeg, model training, or long-running batch jobs — AWS or Azure, not Cloudflare.

### When Cloudflare Wins

1. **Global API gateway / reverse proxy** — traffic hits the nearest PoP, auth/rate-limit/transform logic runs at the edge, origin in any cloud
2. **Zero-egress data serving** — static assets, large object downloads (R2 eliminates S3 egress costs entirely)
3. **Always-on DDoS + WAF** — included in every plan, no $3 000/month Shield Advanced required
4. **Sub-millisecond personalization** — AB tests, geolocation rewrites, cookie-based routing without a Lambda cold start
5. **Real-time collaboration** — Durable Objects give you a single-threaded actor co-located with users; trivially builds presence, CRDT sync, WebSocket state

### When AWS Wins

1. **Existing workloads** — 90% of enterprises run something on AWS; switching costs are real
2. **Complex data services** — Aurora Serverless, Redshift, SageMaker, Glue, Kinesis: Cloudflare has no equivalent depth
3. **Stateful containers at scale** — EKS + Fargate with Karpenter autoscaling is mature; CF Containers is beta
4. **Regulated workloads** — FedRAMP, HIPAA, PCI compliance at depth, GovCloud regions, CloudHSM
5. **Machine learning training** — GPU fleets, Trainium, Inferentia; Workers AI only serves inference

### When Azure Wins

1. **Microsoft-first enterprises** — Active Directory / Entra ID SSO, M365 integration, hybrid Windows Server on Azure Arc
2. **GitHub Actions + Azure DevOps** — native CI/CD pipeline integration
3. **OpenAI workloads** — Azure OpenAI is the only production path for GPT-4o with enterprise SLAs; AWS/CF go through API gateways
4. **SAP / Oracle on cloud** — Microsoft's certified enterprise application landscape
5. **Government and EU data residency** — sovereign cloud regions with compliance certifications

---

## Build It / In Depth

### Scenario: Global API with Cloudflare Workers + R2, Falling Back to AWS Lambda

A real architecture: Cloudflare sits in front. Light logic (auth, routing, rate limiting, caching) runs on Workers. Heavy compute (PDF generation, ML inference) offloads to a regional Lambda.

**Step 1 — Deploy a Worker that proxies to Lambda**

```typescript
// worker.ts (Cloudflare Workers)
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // 1. Rate-limit at the edge (no Lambda invocation wasted)
    const ip = request.headers.get("CF-Connecting-IP") ?? "";
    const { success } = await env.RATE_LIMITER.limit({ key: ip });
    if (!success) {
      return new Response("Too Many Requests", { status: 429 });
    }

    // 2. Serve static assets from R2 (zero egress cost)
    if (url.pathname.startsWith("/assets/")) {
      const object = await env.BUCKET.get(url.pathname.slice(8));
      if (object) {
        return new Response(object.body, {
          headers: { "Content-Type": object.httpMetadata?.contentType ?? "application/octet-stream" },
        });
      }
      return new Response("Not Found", { status: 404 });
    }

    // 3. Forward heavy compute to Lambda (signed request via AWS Signature v4)
    const lambdaUrl = env.LAMBDA_FUNCTION_URL; // Function URL, no API GW needed
    const upstreamReq = new Request(lambdaUrl + url.pathname + url.search, {
      method: request.method,
      headers: request.headers,
      body: request.body,
    });
    return fetch(upstreamReq);
  },
};
```

**Step 2 — Configure wrangler.toml**

```toml
name = "api-gateway"
main = "src/worker.ts"
compatibility_date = "2025-01-01"

[[r2_buckets]]
binding = "BUCKET"
bucket_name = "my-assets"

[[unsafe.bindings]]
name = "RATE_LIMITER"
type = "ratelimit"
namespace_id = "1001"
simple = { limit = 100, period = 60 }

[vars]
LAMBDA_FUNCTION_URL = "https://abc123.lambda-url.us-east-1.on.aws"
```

**Step 3 — Deploy**

```bash
wrangler deploy
# ✅ Uploaded api-gateway (1.23 sec)
# ✅ Deployed to 300+ locations worldwide
```

**Step 4 — Egress cost comparison for 10 TB/month served from storage**

```
AWS S3 egress to internet (10 TB):
  10 000 GB × $0.09/GB = $900/month

Cloudflare R2 egress (10 TB):
  10 000 GB × $0.00/GB = $0/month
  Storage: 10 000 GB × $0.015 = $150/month
  Total: $150/month

Savings: $750/month ($9 000/year) on storage egress alone.
```

**Step 5 — Durable Object for WebSocket state (where AWS has no clean equivalent)**

```typescript
// chat-room.ts — one DO instance per room, co-located near users
export class ChatRoom {
  private sessions: Set<WebSocket> = new Set();

  async fetch(request: Request): Promise<Response> {
    const upgradeHeader = request.headers.get("Upgrade");
    if (upgradeHeader !== "websocket") {
      return new Response("Expected WebSocket", { status: 426 });
    }

    const [client, server] = Object.values(new WebSocketPair());
    server.accept();

    this.sessions.add(server);
    server.addEventListener("message", (event) => {
      // Broadcast to all connections in this room — single-threaded, no locks needed
      for (const session of this.sessions) {
        if (session !== server && session.readyState === WebSocket.READY_STATE_OPEN) {
          session.send(event.data as string);
        }
      }
    });
    server.addEventListener("close", () => this.sessions.delete(server));

    return new Response(null, { status: 101, webSocket: client });
  }
}
```

On AWS, achieving the same requires API Gateway WebSocket + DynamoDB connection table + Lambda fan-out — roughly 5× more moving parts and 3× the latency.

---

## Use It

### Decision Tree

```
Do you need to run arbitrary binaries (ffmpeg, Python ML, Java)?
  YES → AWS Lambda / ECS  OR  Azure Functions / AKS
  NO  ↓

Is your primary concern global latency (<50 ms everywhere)?
  YES → Cloudflare Workers
  NO  ↓

Is this a Microsoft/Windows/Azure AD enterprise environment?
  YES → Azure
  NO  ↓

Does your team already have AWS expertise and existing AWS infra?
  YES → AWS (switching cost is real)
  NO  ↓

Are you optimizing for egress costs on large file serving?
  YES → Cloudflare R2 + Workers
  NO  → Evaluate based on specific service needs
```

### Common Hybrid Patterns

| Pattern | Architecture | Why |
|---|---|---|
| **Cloudflare as global proxy for AWS** | CF Workers → AWS ALB → ECS | CF handles DDoS, WAF, edge caching; AWS runs stateful app |
| **R2 for static, S3 for raw storage** | CF R2 (CDN-served assets) + S3 (internal data lake) | Zero egress on public assets, S3 ecosystem for data |
| **Azure OpenAI + CF AI Gateway** | Azure OpenAI → CF AI Gateway → apps | CF adds rate limiting, caching, observability to Azure AI |
| **Workers + Lambda Function URLs** | CF Worker → Lambda Function URL (no API GW) | Skip $3.50/million API Gateway cost, keep Lambda runtime |
| **D1 read replicas + RDS primary** | CF D1 (edge reads) → Hyperdrive → AWS RDS (writes) | Sub-10 ms reads globally, strong consistency on writes |

### Specific Technology Guidance

- **AWS CloudFront vs. Cloudflare CDN**: CloudFront has more edge locations (600+) but charges egress; Cloudflare has fewer PoPs but charges nothing for egress. For large file distribution (video, software), Cloudflare R2 + CDN often wins on cost.
- **AWS Lambda@Edge**: Runs Node.js only, max 5 seconds, limited to 1 MB response. Workers runs faster (V8 isolates), supports streaming, but also lacks POSIX.
- **Azure Front Door vs. Cloudflare**: Front Door is strong for Azure-native workloads with WAF integration; Cloudflare is provider-agnostic and simpler to operate globally.
- **Durable Objects**: No equivalent in AWS or Azure. If you need strongly consistent, low-latency, per-entity state without a regional DB, Durable Objects is uniquely suited.

---

## Common Pitfalls

- **Treating Cloudflare as just a CDN.** Engineers configure Cloudflare for caching and DDoS, then pay AWS for API Gateway, Lambda, S3 egress, and WAF separately — spending 3–5× more than necessary. Audit whether Workers + R2 can replace your API Gateway + Lambda@Edge + S3 egress entirely.

- **Cold-start blindness on Lambda.** Teams measure P50 latency and miss P99. A Lambda cold start on a VPC-attached function can add 800 ms–3 s. For user-facing APIs requiring global <100 ms, Lambda@Edge or Workers is the answer — not vanilla Lambda in a single region.

- **Ignoring Cloudflare's CPU time limit.** Workers default to 10 ms CPU time (30 ms on paid plans). Complex JSON transforms, cryptographic operations, or synchronous loop-heavy code will hit this. Profile before migrating; CPU-heavy work belongs on Lambda or Azure Functions.

- **Underestimating Azure's licensing leverage.** Teams migrating from on-prem Microsoft stacks to AWS often pay full price for Windows Server, SQL Server, and Active Directory integration. Azure Hybrid Benefit can reduce Windows VM costs by 40–49%. Run the TCO before assuming AWS is cheaper.

- **Using Cloudflare D1 as a write-heavy primary database.** D1 is SQLite at the edge with eventual consistency on read replicas. Write throughput is limited and single-primary. Use it for read-heavy, globally distributed query patterns (catalog, config, user preferences). Use RDS/Aurora or PlanetScale for write-heavy transactional workloads, then connect via Hyperdrive.

- **Neglecting egress cost in architecture decisions.** Egress is the hidden line item. A 10 TB/month S3 serving workload costs $900 in egress alone. Moving to Cloudflare R2 drops that to $0. Always model egress when choosing storage layers.

---

## Exercises

1. **Easy** — Take an existing S3 bucket serving public static assets. Set up Cloudflare R2 with an equivalent bucket and migrate the assets. Measure the monthly cost difference assuming 5 TB outbound per month. What is the break-even in storage size where R2 becomes more expensive than S3 (hint: compare storage rates)?

2. **Medium** — Design an architecture for a global leaderboard feature (read-heavy, eventually consistent reads acceptable, one write per user per game session). Compare three implementations: (a) DynamoDB Global Tables on AWS, (b) Azure Cosmos DB multi-region, (c) Cloudflare Workers KV + Durable Object per leaderboard. For each, estimate latency, cost at 1 M daily active users, and operational complexity.

3. **Hard** — You run a fintech application on AWS (EKS for app servers, RDS Aurora for the database, S3 for document storage, Lambda for async jobs). A compliance requirement arrives: all EU user data must be processed and stored in EU regions with <50 ms latency from any EU country. Design the migration plan using a combination of Cloudflare (for edge routing and data residency enforcement), AWS EU regions, and optionally Azure (for any Microsoft compliance tooling needed). Address: data routing, database replication, compliance attestation, and rollback strategy.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **V8 Isolate** | A container or VM | A lightweight JavaScript execution context inside a single process; starts in microseconds, shares memory space of the host process with strict isolation, no OS overhead |
| **Durable Object** | A key-value store or session cache | A single-threaded actor with its own durable storage, co-located with a specific region; provides strong consistency for one entity without a central database |
| **Egress Cost** | The fee to upload data to the cloud | The fee to download (send out) data FROM the cloud to the internet; this is the dominant data transfer cost in AWS/Azure |
| **Smart Placement** | Automatic load balancing | Cloudflare's heuristic that moves a Worker invocation from the nearest PoP to a PoP closer to the upstream database, reducing latency for DB-heavy requests |
| **Lambda@Edge** | The same as Lambda, but faster | A constrained subset of Lambda (Node.js only, 5 s max, 1 MB body) that runs at CloudFront edge locations; different service, different limits than Lambda |
| **Hyperdrive** | A database proxy inside Cloudflare | A connection-pooling service in Cloudflare's network that maintains warm DB connections to external databases (Postgres, MySQL), eliminating per-Worker connection overhead |
| **Workers KV** | A strongly consistent global store | An eventually consistent key-value store with strong read-after-write within a single PoP; reads from other PoPs may lag by seconds; not suitable for coordination between nodes |

---

## Further Reading

- [Cloudflare Workers Developer Docs](https://developers.cloudflare.com/workers/) — official reference for Workers, KV, R2, D1, Durable Objects, and Queues; the most reliable source for limits and pricing
- [AWS Lambda Performance Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html) — official guidance on cold starts, VPC attachment, memory tuning, and function URLs
- [Azure vs AWS Service Comparison](https://learn.microsoft.com/en-us/azure/architecture/aws-professional/services) — Microsoft's own side-by-side service mapping table for engineers moving between clouds
- [Cloudflare R2 Pricing and S3 Comparison](https://developers.cloudflare.com/r2/pricing/) — includes the egress fee comparison that drives most R2 migration decisions
- [The Durable Objects Model — Cloudflare Blog](https://blog.cloudflare.com/introducing-workers-durable-objects/) — original design post explaining the actor model, consistency guarantees, and why this is architecturally unique
