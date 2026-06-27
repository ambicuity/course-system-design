# Top 30 AWS Services That Are Commonly Used

> The thirty services that cover 90% of AWS workloads — by category, with the role each one plays.

**Type:** Reference
**Prerequisites:** Basic AWS familiarity
**Time:** ~15 minutes

---

## The Problem

AWS offers 200+ services. You do not need to know them all. You need to know the thirty that show up in production work, what each one does, when to reach for it, and what it costs relative to alternatives. That is the working vocabulary of an AWS engineer.

This lesson is a focused reference. It groups the thirty most-used services into seven categories, lists each with its role, and gives a one-line description of when to reach for it. By the end, you should be able to look at almost any AWS architecture diagram and recognize every component.

---

## The Concept

### The seven categories

```
   1. Compute             →  EC2, Lambda, ECS, EKS, Fargate
   2. Storage             →  S3, EBS, FSx, Backup, Glacier
   3. Database            →  RDS, DynamoDB, Aurora, Redshift, ElastiCache, DocumentDB, Keyspaces
   4. Networking          →  VPC, CloudFront, Route 53, WAF, Shield
   5. AI / ML             →  SageMaker, Rekognition, Textract, Comprehend
   6. Monitoring / DevOps →  CloudWatch, X-Ray, CodePipeline, CloudFormation
   7. (Bonus categories)  →  Security, Identity, Messaging (covered in other lessons)
```

We walk through each category with one-line descriptions and the standard use case.

---

### 1. Compute

**1. Amazon EC2** — Virtual servers in the cloud. The foundation of AWS compute. Choose instance type, OS, and size; you manage the rest. Reach for: any workload where you need full control of the OS or runtime.

**2. AWS Lambda** — Serverless functions for event-driven workloads. No servers to manage; pay per invocation. Reach for: APIs, event handlers, glue code, scheduled tasks.

**3. Amazon ECS** — Managed container orchestration. Run Docker containers on AWS without managing Kubernetes. Reach for: container workloads when you do not need Kubernetes-specific features.

**4. Amazon EKS** — Managed Kubernetes. Run upstream Kubernetes without managing the control plane. Reach for: when you need Kubernetes APIs, tooling, or portability.

**5. AWS Fargate** — Serverless compute for containers. Run containers without managing EC2 instances. Reach for: ECS or EKS workloads where you do not want to manage nodes.

---

### 2. Storage

**6. Amazon S3** — Scalable, secure object storage. The default for blobs, backups, data lakes, static websites. Eleven nines of durability. Reach for: any unstructured data — files, images, videos, backups, logs.

**7. Amazon EBS** — Block storage for EC2 instances. Persistent, low-latency SSD or HDD volumes attached to one EC2. Reach for: database storage, OS disks, anything that needs block-level access.

**8. Amazon FSx** — Fully managed file storage. NFS (FSx for Lustre, FSx for NetApp ONTAP) or Windows file systems. Reach for: shared file storage, high-performance computing, Windows workloads.

**9. AWS Backup** — Centralized backup automation across AWS services. Reach for: cross-service backup policies, compliance retention.

**10. Amazon Glacier** — Archival cold storage for backups. Very cheap ($1 per TB per month); retrieval latency in minutes to hours. Reach for: long-term archives, compliance retention, disaster recovery.

---

### 3. Database

**11. Amazon RDS** — Managed relational database service. Postgres, MySQL, MariaDB, Oracle, SQL Server. AWS handles backups, patching, replication. Reach for: traditional relational workloads with minimal ops overhead.

**12. Amazon DynamoDB** — NoSQL database with single-digit ms latency at any scale. Fully managed; key-value and document. Reach for: serverless apps, high-scale OLTP, predictable latency requirements.

**13. Amazon Aurora** — High-performance cloud-native database. MySQL and Postgres compatible. Reach for: when you need RDS but with better performance (5× typical MySQL, 3× typical Postgres).

**14. Amazon Redshift** — Scalable data warehousing solution. Columnar storage, MPP architecture. Reach for: OLAP workloads, BI, dashboards, large-scale analytics.

**15. Amazon ElastiCache** — In-memory caching with Redis or Memcached. Reach for: caching layer in front of RDS/DynamoDB, session storage, leaderboards.

**16. Amazon DocumentDB** — NoSQL document database, MongoDB-compatible. Reach for: MongoDB workloads without managing MongoDB yourself.

**17. Amazon Keyspaces** — Managed Cassandra database service. Reach for: Cassandra workloads (wide-column, time-series, IoT) without managing Cassandra yourself.

---

### 4. Networking & Security

**18. Amazon VPC** — Secure cloud networking. Isolated virtual network with subnets, route tables, NAT, IGW. Reach for: every AWS deployment; the foundation of private networking.

**19. AWS CloudFront** — Content Delivery Network. Cache and serve content from 600+ edge locations. Reach for: static assets, video, APIs needing low global latency.

**20. AWS Route 53** — Scalable DNS. Domain registration, DNS routing, health checks. Reach for: public DNS, internal DNS (via private hosted zones), traffic routing policies.

**21. AWS WAF** — Web Application Firewall. Protects against common web exploits (SQL injection, XSS). Reach for: any public-facing web app or API.

**22. AWS Shield** — DDoS protection. Standard (free) for all customers; Advanced ($3000/month) for higher protection. Reach for: applications at risk of DDoS.

---

### 5. AI & Machine Learning

**23. Amazon SageMaker** — Build, train, and deploy ML models. End-to-end ML platform with notebooks, training jobs, endpoints. Reach for: custom ML model development and deployment.

**24. Amazon Rekognition** — Image and video analysis. Object detection, face recognition, content moderation. Reach for: vision tasks without building models.

**25. Amazon Textract** — Extracts text from scanned documents. OCR with structure awareness. Reach for: digitizing forms, invoices, receipts, IDs.

**26. Amazon Comprehend** — NLP service. Sentiment, entities, topics, language detection. Reach for: text understanding without training a model.

---

### 6. Monitoring & DevOps

**27. Amazon CloudWatch** — Metrics, logs, alarms, dashboards. The default observability for AWS workloads. Reach for: every AWS deployment.

**28. AWS X-Ray** — Distributed tracing. Trace requests across services to find latency bottlenecks. Reach for: microservices debugging.

**29. Amazon CodePipeline** — CI/CD automation. Build, test, deploy pipelines. Reach for: any team doing continuous deployment.

**30. AWS CloudFormation** — Infrastructure as Code. Declarative templates for AWS resources. Reach for: any non-trivial AWS deployment; the standard for IaC on AWS.

---

## Build It / In Depth

### The thirty services on one diagram

```
   User request
        │
        ▼
   [Route 53] DNS routing                  (Service 20)
        │
        ▼
   [CloudFront] CDN                       (Service 19)
        │
        ▼
   [WAF] + [Shield] Web firewall + DDoS   (Services 21, 22)
        │
        ▼
   [ALB] (part of VPC) Load balancer
        │
        ▼
   [ECS / EKS / Fargate] Container compute (Services 3, 4, 5)
        │
        ▼
   [Lambda] for event-driven code         (Service 2)
        │
        ▼
   [Application service]
        │
        ├──► [ElastiCache] in-memory cache   (Service 15)
        │
        ├──► [RDS / Aurora / DynamoDB] database (Services 11, 12, 13)
        │
        └──► [S3] for objects and backups   (Service 6)
                  │
                  ▼
              [Glacier] archival             (Service 10)
                  │
                  ▼
              [Backup] centralized          (Service 9)

   Cross-cutting:
     [CloudWatch] metrics, logs, alarms   (Service 27)
     [X-Ray] distributed tracing          (Service 28)
     [IAM] identity & access
     [KMS] encryption keys
     [Secrets Manager] credentials
     [CodePipeline] CI/CD                 (Service 29)
     [CloudFormation] IaC                 (Service 30)
```

A typical production system uses 15–20 of these thirty. Knowing all thirty lets you recognize any architecture you encounter.

---

### The categories of cost

For a typical production system, where does the AWS bill go?

```
   Compute (EC2 / Lambda / containers):  30–50%
   Database (RDS / DynamoDB / Aurora):    20–35%
   Storage (S3 / EBS):                   5–15%
   Networking (data transfer, NAT, ELB): 5–15%
   Other (CloudWatch, KMS, etc.):        5–10%
```

Compute and database dominate. Optimization efforts should focus there first.

---

### The "managed" gradient

Each AWS service sits somewhere on the managed-services spectrum:

| Less managed | More managed |
|---|---|
| EC2 (you manage OS, runtime, scaling) | Fargate (AWS manages servers) |
| RDS (AWS manages backups, patching) | Aurora Serverless (AWS manages capacity) |
| Elasticsearch on EC2 | OpenSearch Service (managed) |
| Cassandra on EC2 | Keyspaces (managed Cassandra-compatible) |
| Kafka on EC2 | MSK (managed Kafka) |

**Rule of thumb:** the more managed, the higher the per-unit cost, but the lower the operational burden. For most teams, more managed is the right default.

---

## Use It

### Quick mapping: need → service

| You need… | Use |
|---|---|
| Virtual servers | EC2 |
| Serverless functions | Lambda |
| Managed Kubernetes | EKS |
| Serverless containers | Fargate + ECS |
| Object storage | S3 |
| Block storage | EBS |
| Shared file storage | FSx |
| Cold archival | Glacier |
| Managed Postgres | RDS or Aurora |
| Managed MySQL | RDS or Aurora |
| Serverless NoSQL | DynamoDB |
| Data warehouse | Redshift |
| In-memory cache | ElastiCache (Redis) |
| MongoDB-compatible | DocumentDB |
| Cassandra-compatible | Keyspaces |
| Private network | VPC |
| CDN | CloudFront |
| DNS | Route 53 |
| Web firewall | WAF |
| DDoS protection | Shield |
| ML platform | SageMaker |
| Image recognition | Rekognition |
| OCR | Textract |
| NLP | Comprehend |
| Metrics & logs | CloudWatch |
| Distributed tracing | X-Ray |
| CI/CD | CodePipeline |
| Infrastructure as Code | CloudFormation |

---

### Cost optimization tips

| Service | Cost optimization |
|---|---|
| EC2 | Reserved Instances or Savings Plans for steady-state; Spot for fault-tolerant |
| Lambda | Right-size memory; reduce duration; avoid over-provisioning |
| RDS | Aurora Serverless for variable load; Reserved Instances for steady-state |
| DynamoDB | On-demand for variable load; provisioned for predictable; auto-scaling |
| S3 | Intelligent-Tiering for unknown access; lifecycle policies to Glacier |
| CloudFront | Use edge caching; tune TTLs; compress responses |
| Data transfer | Minimize cross-region; use VPC endpoints; CloudFront for external |

---

## Common Pitfalls

- **Treating AWS services as interchangeable across providers.** They are not. S3 and Blob Storage and GCS have different APIs, semantics, and quirks.

- **Underestimating data transfer costs.** Cross-AZ, cross-region, and egress to internet all cost money. A naïve architecture can have data transfer as the largest line item.

- **Defaulting to EC2 when serverless fits.** Lambda is often simpler and cheaper for variable or event-driven workloads.

- **Using RDS when DynamoDB fits (or vice versa).** Relational and NoSQL have different trade-offs. Match the database to the access pattern.

- **Ignoring the managed gradient.** Building on EC2 when a managed service exists means more operations, more patches, more on-call burden.

- **Picking the most popular service in each category.** "Best of breed" is sometimes best; often the integrated stack is better.

- **Forgetting CloudWatch costs.** CloudWatch Logs and custom metrics add up. Set retention policies; aggregate logs; sample traces.

- **Believing AWS-marketed "free tier" lasts.** It does not. Plan for full price after 12 months.

---

## Exercises

1. **Easy** — Pick three of the thirty services. For each, give one sentence describing what it does and one concrete scenario where you would use it.

2. **Medium** — Take a real product you use. Identify which fifteen of the thirty AWS services it likely uses. For each, explain how.

3. **Hard** — You are designing the AWS architecture for a new SaaS product. Choose one service from each of the seven categories. Justify each choice and estimate the relative cost contribution.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| AWS | A cloud provider | Amazon's cloud platform offering 200+ services across compute, storage, database, networking, AI, and more |
| EC2 | Virtual machines | Elastic Compute Cloud — virtual servers in the cloud; the foundation of AWS compute |
| Lambda | Serverless | A serverless compute service that runs code in response to events without managing servers |
| S3 | Object storage | Simple Storage Service — scalable object storage with eleven nines of durability; the default for blobs |
| RDS | Managed Postgres/MySQL | Relational Database Service — managed relational databases (Postgres, MySQL, Oracle, SQL Server) |
| DynamoDB | A NoSQL database | A fully managed NoSQL database with single-digit ms latency at any scale; key-value and document |
| VPC | A network | Virtual Private Cloud — an isolated virtual network; the foundation of private AWS networking |
| CloudFront | A CDN | Amazon's content delivery network with 600+ edge locations |
| Aurora | RDS on steroids | A cloud-native relational database compatible with MySQL and Postgres; 5× typical MySQL performance |
| CloudWatch | Monitoring | The default AWS observability service for metrics, logs, alarms, and dashboards |

---

## Further Reading

- **AWS Documentation** — the canonical reference: https://docs.aws.amazon.com/
- **AWS Well-Architected Framework** — five pillars of best practices: https://aws.amazon.com/architecture/well-architected/
- **AWS Architecture Blog** — official architecture posts: https://aws.amazon.com/blogs/architecture/
- **AWS Pricing Calculator** — estimate costs for your workload: https://calculator.aws/
- **"The Good Parts of AWS"** — a curated list of services worth learning: https://github.com/donnemartin/aws-great-good
- **AWS Solutions Library** — reference architectures for common patterns: https://aws.amazon.com/solutions/