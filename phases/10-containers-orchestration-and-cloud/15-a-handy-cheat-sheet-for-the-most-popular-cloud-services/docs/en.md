# A handy cheat sheet for the most popular cloud services

> A side-by-side map of the major cloud providers across every category — for picking providers and for understanding which service maps to which need.

**Type:** Reference
**Prerequisites:** Basic cloud computing
**Time:** ~15 minutes

---

## The Problem

Every major cloud provider offers ~200 services with overlapping but non-identical capabilities. AWS has Lambda, Azure has Azure Functions, GCP has Cloud Functions. AWS has S3, Azure has Blob Storage, GCP has Cloud Storage. Knowing which service maps to which need — and which provider has the strongest offering in each category — is the basic vocabulary of cloud-native engineering.

This lesson is a reference cheat sheet. It does not rank providers or argue for one over another. It maps the major services to the categories of work they serve, so you can compare apples to apples and choose deliberately.

---

## The Concept

### The five major providers (mid-2025)

| Provider | Strength | Best for |
|---|---|---|
| **AWS** | Broadest catalog, deepest services, largest community | Most enterprise workloads |
| **Azure** | Microsoft integration, enterprise AD, hybrid cloud | Microsoft shops, enterprises |
| **GCP** | Data analytics, ML, Kubernetes, networking | Data and ML workloads |
| **Oracle Cloud** | Oracle database workloads, enterprise apps | Oracle-heavy enterprises |
| **Alibaba Cloud** | China market, strong Asia presence | Asia-Pacific, especially China |

The rest of this lesson maps services by category, with examples from each major provider.

---

### Compute: virtual servers and serverless

| Category | AWS | Azure | GCP |
|---|---|---|---|
| Virtual machines | EC2 | Virtual Machines | Compute Engine |
| Managed Kubernetes | EKS | AKS | GKE |
| Serverless functions | Lambda | Functions | Cloud Functions |
| Containers (managed) | ECS / Fargate | Container Apps | Cloud Run |
| Bare metal | EC2 Bare Metal | (limited) | (limited) |
| GPU instances | P-family (Nvidia) | N-family (Nvidia) | A-family (Nvidia + TPUs) |

**Decision criteria:**

- **Maximum service breadth:** AWS
- **Best Kubernetes:** GKE (managed upstream Kubernetes, often ahead of AKS/EKS in features)
- **Tightest Microsoft integration:** Azure
- **Cheapest for predictable workloads:** Oracle or Alibaba
- **Best GPU + ML:** GCP (TPUs are unique)

---

### Storage: object, block, file, archive

| Category | AWS | Azure | GCP |
|---|---|---|---|
| Object storage | S3 | Blob Storage | Cloud Storage |
| Block storage | EBS | Managed Disks | Persistent Disk |
| File storage | EFS, FSx | Files, NetApp | Filestore |
| Archive | Glacier | Archive Storage | Archive Storage |
| Backup service | Backup | Backup | (third-party) |

**Decision criteria:**

- **Industry standard for object storage:** AWS S3 (every other provider supports the S3 API)
- **Cheapest archival:** Glacier Deep Archive (less than $1 per TB per month)
- **Tightest integration with Hadoop/Spark:** GCS (used internally by Google)

---

### Databases: relational, NoSQL, specialized

| Category | AWS | Azure | GCP |
|---|---|---|---|
| Managed Postgres | RDS / Aurora | Database for PostgreSQL | Cloud SQL |
| Managed MySQL | RDS / Aurora | Database for MySQL | Cloud SQL |
| Distributed SQL | Aurora | Cosmos DB (different model) | Spanner |
| Key-value / document | DynamoDB | Cosmos DB | Firestore |
| In-memory cache | ElastiCache | Cache for Redis | Memorystore |
| Data warehouse | Redshift | Synapse | BigQuery |
| Time-series | Timestream | (third-party) | (third-party) |
| Graph | Neptune | Cosmos DB (Gremlin) | (third-party) |

**Decision criteria:**

- **Best managed Postgres:** Aurora (MySQL/Postgres-compatible, drop-in faster)
- **Best data warehouse:** BigQuery (serverless, decoupled storage/compute)
- **Best globally distributed SQL:** Cosmos DB (multi-region by default) or Spanner (strong consistency globally)
- **Best key-value / document for serverless apps:** DynamoDB (predictable latency at scale)

---

### Messaging and streaming

| Category | AWS | Azure | GCP |
|---|---|---|---|
| Message queue | SQS | Service Bus | Pub/Sub |
| Topic-based pub/sub | SNS | Event Grid / Service Bus Topics | Pub/Sub |
| Streaming platform | Kinesis / MSK (Kafka) | Event Hubs | Pub/Sub Lite / Dataflow |
| Managed Kafka | MSK | HDInsight Kafka | (third-party) |

**Decision criteria:**

- **Standard for event streaming:** Kafka (managed across all three providers)
- **Tightest serverless integration:** SNS + Lambda, or Pub/Sub + Cloud Functions
- **Best for exactly-once / ordered processing:** Kafka (the others are best-effort)

---

### Networking

| Category | AWS | Azure | GCP |
|---|---|---|---|
| Virtual private cloud | VPC | Virtual Network | VPC |
| Load balancer | ALB / NLB | Load Balancer / Application Gateway | Cloud Load Balancing |
| CDN | CloudFront | Front Door / CDN | Cloud CDN |
| DNS | Route 53 | DNS | Cloud DNS |
| DDoS protection | Shield | DDoS Protection | Cloud Armor |
| Hybrid connectivity | Direct Connect | ExpressRoute | Cloud Interconnect |

**Decision criteria:**

- **Most mature global network:** AWS (more regions, more edge locations)
- **Best network performance:** GCP (premium-tier networking)
- **Cheapest bandwidth:** varies; negotiate committed-use discounts

---

### Security and identity

| Category | AWS | Azure | GCP |
|---|---|---|---|
| Identity service | IAM | Entra ID (Azure AD) | Cloud IAM |
| Secrets manager | Secrets Manager | Key Vault | Secret Manager |
| Key management | KMS | Key Vault | Cloud KMS |
| WAF | WAF | Application Gateway WAF | Cloud Armor |
| Certificate manager | ACM | App Service Certificates | Certificate Manager |

**Decision criteria:**

- **Best enterprise identity:** Entra ID (if you are a Microsoft shop)
- **Most granular IAM:** AWS IAM (deep but complex)
- **Easiest IAM:** GCP IAM (simpler model, fewer features)

---

### Monitoring and observability

| Category | AWS | Azure | GCP |
|---|---|---|---|
| Metrics | CloudWatch | Monitor | Cloud Monitoring |
| Logs | CloudWatch Logs | Log Analytics | Cloud Logging |
| Tracing | X-Ray | Application Insights | Cloud Trace |
| Dashboards | CloudWatch Dashboards | Dashboards | Cloud Monitoring Dashboards |

**Cross-cloud options (work everywhere):** Datadog, New Relic, Grafana Cloud, Honeycomb.

---

### AI and ML

| Category | AWS | Azure | GCP |
|---|---|---|---|
| Foundation model API | Bedrock | Azure OpenAI | Vertex AI |
| Custom model training | SageMaker | Azure Machine Learning | Vertex AI |
| Speech | Polly / Transcribe | Speech | Speech-to-Text / Text-to-Speech |
| Vision | Rekognition | Computer Vision | Vision AI |
| Document understanding | Textract | Form Recognizer | Document AI |
| Translation | Translate | Translator | Translation |

**Decision criteria:**

- **Best managed ML platform:** SageMaker (broadest feature set)
- **Best OpenAI access:** Azure (the exclusive OpenAI Service partner)
- **Best foundation models for production:** Bedrock (Claude, Llama, Mistral, Cohere behind one API)
- **Best ML research + TPUs:** GCP Vertex AI

---

### Cost comparison: rough order of magnitude

For comparable workloads (3 web servers, 1 managed Postgres, 1 TB object storage, basic load balancer):

| Provider | Relative cost | Notes |
|---|---|---|
| AWS | 1.0 (baseline) | Most expensive at low scale; volume discounts at high scale |
| Azure | ~1.0–1.1 | Similar to AWS; better Windows integration |
| GCP | ~0.85–0.95 | Often slightly cheaper; aggressive sustained-use discounts |
| Oracle | ~0.7–0.9 | Cheapest for Oracle workloads |
| Alibaba | ~0.6–0.8 | Cheapest overall, especially in Asia |

These are rough averages. Real pricing depends on commitment, region, and workload shape. Always price your specific workload.

---

## Build It / In Depth

### Choosing a primary cloud provider

For most teams, the choice reduces to:

```
   Microsoft-heavy enterprise (Outlook, Teams, AD, Windows servers)?
   → Azure

   AWS-heavy existing infrastructure?
   → AWS

   Data / ML / Kubernetes-first team?
   → GCP

   Asia-Pacific / China market?
   → Alibaba Cloud (or Azure/AWS with China regions)

   Oracle database workloads?
   → Oracle Cloud
```

**The honest answer:** for greenfield projects, pick the provider where:

1. Your team has operational experience.
2. The services you need are strongest.
3. Pricing is competitive for your workload.
4. The provider has good support / managed services for your stack.

Switching providers is hard once you are deep. Pick deliberately.

---

### Multi-cloud strategy

Some organizations deliberately use multiple providers to avoid lock-in or for resilience. The trade-offs:

**Pros:**
- Avoid single-provider lock-in
- Use best-of-breed services from each
- Resilience against provider-wide outages

**Cons:**
- Operational complexity (two sets of tools, IAM, networking)
- Skills required across both
- Data transfer costs between clouds
- Compliance complexity (data residency per region)

**Pragmatic recommendation:** start with one provider, get operationally mature, then evaluate whether multi-cloud adds value for specific workloads (e.g., a CDN partner for global reach, a backup target in another provider).

---

## Use It

### When to choose which provider

| Situation | Best choice |
|---|---|
| Microsoft shop, Windows servers, Office 365 | Azure |
| Default choice for most startups | AWS |
| Heavy ML / data analytics / Kubernetes | GCP |
| China market entry | Alibaba Cloud (or Azure China, AWS China) |
| Existing Oracle databases | Oracle Cloud |
| Edge / CDN-heavy global app | Any, with a CDN partner (Cloudflare, Fastly) |

### When multi-cloud makes sense

| Situation | Multi-cloud? |
|---|---|
| Single-team SaaS | No — pick one and go deep |
| Multi-region failover | Sometimes — but usually multi-region within one provider is enough |
| Data residency across jurisdictions | Possibly — but mostly solved by multi-region within one provider |
| Avoiding single-provider lock-in at $10M+ annual spend | Maybe — at scale, the negotiation leverage is real |
| Genuinely best-of-breed services per workload | Sometimes — but rarely worth the operational cost |

---

## Common Pitfalls

- **Assuming provider services are interchangeable.** S3 and Blob Storage look similar but have different APIs, semantics, and edge cases. Switching providers is a real migration, not a config change.

- **Ignoring egress costs.** Data transfer out of a provider can be the largest line item in your bill. Cross-cloud or cross-region traffic is expensive.

- **Locking into proprietary services.** DynamoDB, Cosmos DB, BigQuery — each is excellent but unique. For maximum portability, prefer open-source equivalents (Postgres over Aurora Postgres over Spanner).

- **Choosing based on free credits.** Free credits run out. Price the long-term steady-state cost.

- **Underestimating operational complexity.** AWS has the broadest services but also the most configuration. A team new to cloud may do better on the simpler provider.

- **Building on every "best of breed" service.** Most teams benefit more from a tight, integrated stack than from picking the absolute best service in each category.

---

## Exercises

1. **Easy** — For each of the five providers, identify one service that is widely considered best-in-class. Justify your pick in one sentence.

2. **Medium** — You are choosing a primary cloud provider for a B2B SaaS startup. Build a decision matrix: list 5 criteria, score each provider on each, and recommend one.

3. **Hard** — A regulated-industry client requires data residency in both the US and EU. Design a multi-region architecture using a single primary provider. Specify the services, the data replication strategy, and the failover plan.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Cloud provider | AWS | One of the major platforms (AWS, Azure, GCP, Oracle, Alibaba) offering compute, storage, and managed services on demand |
| Managed service | A PaaS | A service where the provider operates the infrastructure (patching, scaling, backups); you focus on the data and code |
| Serverless | Lambda | A model where the provider manages servers entirely; you provide functions or containers; you pay per execution |
| Egress | A cost | The cost of transferring data out of a cloud provider; often the largest line item in cross-cloud architectures |
| Multi-cloud | A strategy | Using multiple cloud providers to avoid lock-in or for resilience; usually more cost than benefit |
| Region | A datacenter | A geographic area where a cloud provider has multiple isolated datacenters (availability zones) |
| Availability zone | A datacenter | A single datacenter within a region; multiple AZs in a region provide high availability |

---

## Further Reading

- **AWS Well-Architected Framework** — the AWS-specific guidance: https://aws.amazon.com/architecture/well-architected/
- **Azure Architecture Center** — Microsoft-specific guidance: https://learn.microsoft.com/en-us/azure/architecture/
- **Google Cloud Architecture Center** — Google-specific guidance: https://cloud.google.com/architecture
- **Cloud FinOps** — the discipline of managing cloud costs: https://www.finops.org/
- **Vantage Cloud Cost Comparison** — a regularly updated comparison of provider pricing: https://www.vantage.sh/