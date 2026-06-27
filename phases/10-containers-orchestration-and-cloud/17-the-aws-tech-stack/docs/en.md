# The AWS Tech Stack

> A reference architecture for a full-stack application on AWS — nine layers, from frontend to multi-region networking, with the service that fits each.

**Type:** Reference
**Prerequisites:** Basic AWS familiarity, web architecture
**Time:** ~15 minutes

---

## The Problem

AWS offers 200+ services. Building a real application requires choosing one (or a few) for each layer: frontend hosting, API exposure, business logic, data, security, monitoring, CI/CD. The choices interact; the wrong combination produces an architecture that is hard to operate, expensive, or unreliable.

This lesson is a reference stack — nine layers, each with the AWS service that fits, and the trade-offs at each choice. Use it as a starting point, then adapt to your specific workload.

---

## The Concept

### The nine layers

```
   ┌─────────────────────────────────────────────────────────────┐
   │  1. Frontend                                                │
   │  2. API Layer                                               │
   │  3. Application Layer                                       │
   │  4. Media & File Handling                                   │
   │  5. Data Layer                                              │
   │  6. Security & Identity                                     │
   │  7. Observability & Monitoring                              │
   │  8. CI/CD & DevOps                                          │
   │  9. Multi-Region Networking                                 │
   └─────────────────────────────────────────────────────────────┘
```

Each layer has a primary service and common alternatives. We walk through each.

---

### Layer 1: Frontend

**Primary services:**

- **Amazon S3 + CloudFront** — Static websites (HTML, CSS, JS, images) hosted in S3, served globally via CloudFront. Cheap, fast, infinitely scalable.
- **AWS Amplify** — Full-stack frontend hosting with built-in CI/CD, authentication, and backend integration.
- **Amazon Cognito** — User authentication and identity management.
- **AWS Device Farm** — Testing mobile and web apps on real devices in the cloud.

**When to use which:**

- **S3 + CloudFront** — Static sites, SPAs (React, Vue, Angular), simple marketing pages.
- **Amplify** — Full-stack apps needing auth, API integration, and CI/CD built in.
- **Cognito** — Any app needing user signup, login, and social identity (Google, Facebook, Apple).
- **Device Farm** — Mobile apps needing cross-device testing.

---

### Layer 2: API Layer

**Primary services:**

- **Amazon API Gateway** — REST APIs with built-in auth, throttling, request validation, and integration with Lambda.
- **AWS AppSync** — GraphQL APIs with built-in real-time subscriptions and offline sync.
- **AWS Lambda** — Backend functions triggered by API Gateway requests.
- **Elastic Load Balancing (ELB)** — For services that need traditional load balancing.
- **CloudFront** — For caching API responses at the edge.

**When to use which:**

- **API Gateway + Lambda** — Standard REST APIs, serverless backends, event-driven services.
- **AppSync** — GraphQL APIs, real-time apps (chat, collaboration), mobile apps needing offline sync.
- **ELB** — Traditional microservice architectures running on EC2/ECS.
- **CloudFront** — Cache API responses at the edge for global latency.

---

### Layer 3: Application Layer

**Primary services:**

- **AWS Fargate** — Serverless containers; no EC2 to manage.
- **Amazon EKS** — Managed Kubernetes for portable container workloads.
- **AWS Lambda** — For event-driven functions and glue code.
- **Amazon EventBridge** — Serverless event bus for connecting services.
- **AWS Step Functions** — Visual workflow orchestrator for multi-step processes.
- **Amazon SNS** — Pub/sub messaging for fanout.
- **Amazon SQS** — Message queues for decoupling producers and consumers.

**When to use which:**

- **Fargate** — Default for new container workloads; no Kubernetes needed.
- **EKS** — When you need Kubernetes APIs, tooling, or portability.
- **Lambda** — For event handlers, glue code, scheduled tasks.
- **EventBridge** — To wire services together with events.
- **Step Functions** — For long-running workflows with retries, parallel branches, human-in-the-loop.
- **SNS + SQS** — Classic pub/sub + queue pattern for fanout and decoupling.

---

### Layer 4: Media and File Handling

**Primary services:**

- **Amazon S3** — Object storage for media (videos, images, files).
- **AWS Elastic Transcoder** (or AWS MediaConvert) — Transcode video into multiple formats and resolutions.
- **Amazon Rekognition** — Image and video analysis (object detection, face recognition, content moderation).
- **Amazon CloudFront signed URLs** — Time-limited URLs for secure content delivery.

**Typical flow:**

```
   User uploads video
        │
        ▼
   [S3 bucket] stores raw file
        │
        ▼
   [Lambda] triggered by S3 event
        │
        ▼
   [MediaConvert] transcodes to multiple resolutions (1080p, 720p, 480p)
        │
        ▼
   [S3] stores transcoded versions
        │
        ▼
   [CloudFront] serves via signed URLs to authenticated users
        │
        ▼
   [Rekognition] moderates uploaded images (if applicable)
```

**Why CloudFront signed URLs matter:** without them, anyone with a URL can access your S3 content. Signed URLs are time-limited tokens that grant temporary access to authenticated users only.

---

### Layer 5: Data Layer

**Primary services:**

- **Amazon Aurora** — Managed MySQL/Postgres with cloud-native performance.
- **Amazon DynamoDB** — Serverless NoSQL with single-digit ms latency.
- **Amazon ElastiCache** — In-memory caching (Redis or Memcached).
- **Amazon Neptune** — Managed graph database.
- **Amazon OpenSearch** — Managed Elasticsearch for search and analytics.

**When to use which:**

- **Aurora** — Default for relational workloads needing transactions and complex queries.
- **DynamoDB** — Serverless apps, high-scale OLTP, predictable latency.
- **ElastiCache** — Cache layer in front of any database.
- **Neptune** — Graph relationships (social networks, recommendations, fraud detection).
- **OpenSearch** — Full-text search, log analytics, faceted queries.

---

### Layer 6: Security & Identity

**Primary services:**

- **AWS IAM** — Identity and access management; users, roles, policies.
- **Amazon Cognito** — End-user identity (signup, login, social identity).
- **AWS WAF** — Web Application Firewall for protecting HTTP endpoints.
- **AWS KMS** — Encryption key management.
- **AWS Secrets Manager** — Secret storage with rotation.
- **AWS CloudTrail** — Audit log of every API call.

**When to use which:**

- **IAM** — Service-to-service and human-to-service access control.
- **Cognito** — End-user identity (millions of users, social login).
- **WAF** — Any public-facing web app or API.
- **KMS** — Encryption at rest for S3, EBS, RDS, etc.
- **Secrets Manager** — Database credentials, API keys, third-party tokens.
- **CloudTrail** — Compliance audits, security investigations.

---

### Layer 7: Observability & Monitoring

**Primary services:**

- **Amazon CloudWatch** — Metrics, logs, alarms, dashboards.
- **AWS X-Ray** — Distributed tracing across services.
- **AWS CloudTrail** — Audit log of API calls.
- **AWS Config** — Resource configuration tracking and compliance.
- **Amazon GuardDuty** — Threat detection (compromised instances, malicious activity).

**When to use which:**

- **CloudWatch** — Every AWS deployment; the default observability.
- **X-Ray** — Microservices debugging.
- **CloudTrail** — Compliance and audit.
- **Config** — Track resource changes; compliance as code.
- **GuardDuty** — Continuous security monitoring.

---

### Layer 8: CI/CD & DevOps

**Primary services:**

- **AWS CodeCommit** — Managed Git repositories.
- **AWS CodeBuild** — Managed build service (compile, test).
- **AWS CodeDeploy** — Managed deployment service.
- **AWS CodePipeline** — End-to-end CI/CD orchestration.
- **AWS CloudFormation** — Infrastructure as Code.
- **Amazon ECR** — Managed container image registry.
- **AWS Systems Manager** — Operational insights, parameter store, session manager.

**When to use which:**

- **CodePipeline + CodeBuild + CodeDeploy** — Native AWS CI/CD.
- **GitHub Actions / CircleCI / Jenkins** — Most teams use third-party CI; they integrate with AWS deployment targets.
- **CloudFormation** — Infrastructure as Code; the standard on AWS.
- **Terraform / Pulumi** — Third-party IaC tools with broader multi-cloud support.
- **ECR** — Store Docker images for ECS / EKS / Lambda.
- **SSM** — Run commands on EC2 at scale, store configuration centrally.

---

### Layer 9: Multi-Region Networking

**Primary services:**

- **Amazon Route 53** — DNS with traffic routing policies (latency-based, geolocation, weighted).
- **AWS Global Accelerator** — Global anycast IPs for low-latency entry.
- **Amazon VPC** — Isolated network per region.
- **AWS PrivateLink** — Private connectivity between VPCs and AWS services.
- **NAT Gateway / Transit Gateway** — Secure traffic flow between VPCs and to the internet.
- **AWS Backup** — Cross-region backup for disaster recovery.

**Multi-region patterns:**

```
   Active-active:
     Route 53 → latency-based routing → nearest region
     Each region serves traffic; data replicated via DynamoDB Global Tables,
     S3 Cross-Region Replication, or Aurora Global Database

   Active-passive:
     Primary region serves traffic
     Standby region has data replicated but no live traffic
     Failover: update Route 53 to point to standby

   Disaster recovery:
     Backup in another region (AWS Backup)
     Recovery Time Objective (RTO) and Recovery Point Objective (RPO)
     determine the cost / complexity trade-off
```

---

## Build It / In Depth

### The full stack on one diagram

```
   ┌──────────────────────────────────────────────────────────────┐
   │                                                              │
   │   USER                                                      │
   │   │                                                         │
   │   ▼                                                         │
   │   [Route 53] DNS                                            │
   │   │                                                         │
   │   ▼                                                         │
   │   [CloudFront] CDN                                          │
   │   │                                                         │
   │   ▼                                                         │
   │   ┌──────────────────┐                                       │
   │   │ S3 (frontend)    │                                       │
   │   └──────────────────┘                                       │
   │   │                                                         │
   │   ▼                                                         │
   │   [WAF] web firewall                                        │
   │   │                                                         │
   │   ▼                                                         │
   │   [API Gateway] REST API                                    │
   │   │                                                         │
   │   ▼                                                         │
   │   ┌──────────────────┐                                       │
   │   │ Fargate / ECS    │ ← business logic                     │
   │   │ Lambda           │ ← event handlers                     │
   │   └──────────────────┘                                       │
   │   │                                                         │
   │   ├──► [ElastiCache] in-memory cache                       │
   │   ├──► [Aurora / DynamoDB] transactional data               │
   │   └──► [S3] files, images, backups                         │
   │              │                                              │
   │              ▼                                              │
   │          [Glacier] archival                                 │
   │                                                              │
   │   Cross-cutting:                                            │
   │     [CloudWatch] metrics, logs, alarms                      │
   │     [X-Ray] distributed tracing                             │
   │     [CloudTrail] audit                                      │
   │     [GuardDuty] threat detection                            │
   │     [IAM] identity & access                                 │
   │     [KMS] encryption keys                                   │
   │     [Secrets Manager] credentials                           │
   │     [CodePipeline] CI/CD                                    │
   │     [CloudFormation] IaC                                    │
   │                                                              │
   └──────────────────────────────────────────────────────────────┘
```

This is the canonical reference architecture for a typical SaaS application on AWS. Specific services change (Neptune for graph workloads, MediaConvert for video, etc.), but the structure holds.

---

### The default stack by workload type

| Workload type | Stack |
|---|---|
| Static website | S3 + CloudFront + Route 53 |
| SaaS web app | S3 + CloudFront + API Gateway + Fargate + Aurora + ElastiCache + Cognito |
| Mobile app backend | API Gateway + Lambda + DynamoDB + Cognito |
| Data pipeline | S3 + Lambda + Glue + Redshift + QuickSight |
| Video streaming | S3 + MediaConvert + CloudFront + signed URLs |
| Real-time chat | API Gateway WebSocket + Lambda + DynamoDB + ElastiCache |
| ML inference | SageMaker or Lambda + SageMaker endpoint + S3 |

---

## Use It

### Decision cheat sheet

| Layer | Default choice | When to deviate |
|---|---|---|
| Frontend | S3 + CloudFront | Use Amplify if you need auth + backend integration built in |
| API | API Gateway + Lambda | Use ALB + EC2 for long-running connections; AppSync for GraphQL |
| App compute | Fargate | Use EKS for Kubernetes portability; EC2 for specialized hardware |
| Database | Aurora | Use DynamoDB for serverless/scale; Redshift for analytics |
| Cache | ElastiCache (Redis) | Use DAX if your primary is DynamoDB |
| Async | SQS + SNS | Use EventBridge for cross-account events; Step Functions for workflows |
| Storage | S3 | Use EBS for block; FSx for shared file; Glacier for archival |
| Monitoring | CloudWatch | Add Datadog or Grafana Cloud for cross-service observability |
| CI/CD | GitHub Actions or CodePipeline | Use whichever your team already knows |
| IaC | Terraform or CloudFormation | Terraform for multi-cloud; CloudFormation for AWS-only |

---

### Common Pitfalls

- **Using EC2 when Fargate fits.** You pay for managing servers you do not need to manage.

- **Using RDS when DynamoDB fits.** Or vice versa. Match the database to the access pattern, not the team's familiarity.

- **Treating S3 as a filesystem.** S3 is an object store; it does not have POSIX semantics. Use it for objects, not for shared filesystems.

- **Putting CloudFront behind an ELB.** CloudFront should be in front of your origin, not behind it. Reverse-proxy at the edge; the origin serves only CloudFront.

- **Ignoring data transfer costs.** Cross-region replication, NAT Gateway, and internet egress all cost money. Design with bandwidth in mind.

- **No IaC.** Clicking through the console is fine for prototyping; production needs CloudFormation or Terraform. Otherwise, environments drift; recovery is impossible.

- **Insufficient observability.** Without CloudWatch metrics and X-Ray traces, debugging cross-service issues is guesswork.

---

## Exercises

1. **Easy** — Pick three of the nine layers. For each, name the primary service and one alternative.

2. **Medium** — Design the AWS stack for a video streaming service that serves 1M users. Specify each layer's service and the cost optimization you would apply.

3. **Hard** — You are migrating a legacy monolith to AWS. Design a phased plan: which services to introduce first, how to run monolith and new components side-by-side, how to retire legacy pieces, and how to ensure rollback is possible at each step.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| AWS stack | A list of services | A coherent set of AWS services chosen for each layer of an application — frontend, API, app, data, security, monitoring, CI/CD |
| Managed service | A PaaS | A service where AWS operates the infrastructure (patching, scaling, backups); you focus on data and code |
| Serverless | Lambda | A model where AWS manages servers entirely; you provide functions or containers; you pay per execution |
| IaC | Terraform | Infrastructure as Code — declarative definitions of AWS resources, version-controlled and reproducible |
| Multi-region | Two regions | Running your application in multiple geographic regions for latency, resilience, or compliance |
| Active-active | Both regions serve | Both regions serve live traffic with data replication between them; failover is automatic |
| Active-passive | One region serves | Primary region serves traffic; secondary is on standby; failover requires manual or automated switch |

---

## Further Reading

- **AWS Well-Architected Framework** — the five pillars of best practices: https://aws.amazon.com/architecture/well-architected/
- **AWS Solutions Library** — reference architectures for common patterns: https://aws.amazon.com/solutions/
- **AWS Architecture Blog** — official deep-dive posts: https://aws.amazon.com/blogs/architecture/
- **"The Good Parts of AWS"** — curated list of services worth learning: https://github.com/donnemartin/aws-great-good
- **AWS Pricing Calculator** — estimate your workload's cost: https://calculator.aws/