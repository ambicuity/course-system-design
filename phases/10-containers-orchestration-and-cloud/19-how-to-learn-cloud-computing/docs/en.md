# How to Learn Cloud Computing?

> Start with primitives, not products — understand compute, storage, and networking before you memorize service names.

**Type:** Learn
**Prerequisites:** Containers and Docker, Kubernetes Fundamentals, Networking Basics
**Time:** ~25 minutes

---

## The Problem

Cloud computing spans hundreds of services across a dozen providers, each with its own naming conventions, pricing models, and failure modes. A developer who sits down to "learn AWS" for the first time is confronted with over 200 services and no clear entry point. The result is a common pattern: they bookmark tutorials, spin up a few EC2 instances, forget to terminate them, and end up with a surprise $400 bill — still unsure how any of it fits together.

The deeper problem is that cloud concepts are layered. Security groups make no sense until you understand VPCs. Auto-scaling groups make no sense until you understand load balancers. If you approach the cloud as a product catalog to memorize, you will always be one unfamiliar service away from being stuck. Engineers who are genuinely productive in the cloud think in primitives — compute, storage, network, identity — and then map specific services onto those primitives as needed.

Without a structured roadmap, most self-taught engineers end up with large gaps. They can deploy a container but cannot explain how traffic reaches it. They can create an S3 bucket but cannot tell you the difference between server-side and client-side encryption. This lesson gives you the learning sequence that fills those gaps in the right order.

---

## The Concept

### The Six-Phase Learning Map

Cloud computing knowledge builds in layers. Each layer depends on the one below it. The six phases below represent the order in which the concepts unlock one another:

```
Phase 1: Cloud Fundamentals
  └─ What is cloud? Public / Private / Hybrid / Multi-cloud
  └─ Cloud vs. on-premise trade-offs
  └─ Total cost of ownership (TCO)

Phase 2: Service Models
  └─ IaaS  →  you manage OS and above
  └─ PaaS  →  you manage code and data
  └─ SaaS  →  you consume the service

Phase 3: Core Primitives (provider-agnostic)
  ├─ Compute  →  VMs, containers, serverless functions
  ├─ Storage  →  block, object, file, archive
  └─ Networking  →  VPC, subnets, routing, load balancers

Phase 4: Identity, Security & Compliance
  └─ IAM: roles, policies, least privilege
  └─ Encryption at rest and in transit
  └─ WAF, DDoS protection, audit logging

Phase 5: Cloud-Native Patterns
  └─ Managed Kubernetes, serverless, event-driven
  └─ Observability: metrics, logs, traces
  └─ Databases: RDS, managed NoSQL, caching layers

Phase 6: DevOps & Automation
  └─ CI/CD pipelines with cloud-native tooling
  └─ Infrastructure as Code (Terraform, CloudFormation, Pulumi)
  └─ Cost governance and FinOps basics
```

### The Service Model Mental Model

Understanding IaaS / PaaS / SaaS removes most of the confusion about "which service to use":

| Layer             | You manage                               | Provider manages                        | Example                |
|-------------------|------------------------------------------|-----------------------------------------|------------------------|
| On-Premise        | Everything                               | Nothing                                 | Your data center       |
| IaaS              | OS, runtime, app, data                   | Physical servers, hypervisor, network   | AWS EC2, Azure VM      |
| PaaS              | App code and data                        | OS, runtime, middleware, scaling        | AWS Elastic Beanstalk, Heroku |
| SaaS              | Configuration and usage                  | Everything                              | Gmail, Salesforce      |
| FaaS (serverless) | Function code and invocation triggers    | Runtime, scaling, infra                 | AWS Lambda, GCP Cloud Run |

As you move up the stack, you give up control in exchange for reduced operational overhead. There is no universally correct level — the right choice depends on your team's skills, latency requirements, and how much differentiation you get from owning the layer.

### The Three Core Primitives

Every cloud service is ultimately built from three primitives. Knowing these makes every new service easy to categorize:

**Compute** — something that runs your code. This ranges from bare-metal servers through VMs, containers, and managed Kubernetes clusters, all the way to serverless functions where you pay per invocation millisecond.

**Storage** — somewhere to persist data. Block storage attaches to VMs like a hard drive (AWS EBS, Azure Managed Disk). Object storage is a flat key-value store for arbitrary files with no hierarchy (S3, Azure Blob). File storage provides a shared filesystem mountable by multiple VMs (EFS, Azure Files). Archive storage is for cold data you rarely read (S3 Glacier).

**Networking** — how traffic flows. A VPC (Virtual Private Cloud) is an isolated network you control. Subnets partition that VPC. Security groups (or NSGs) are stateful firewalls on individual resources. Load balancers distribute incoming traffic. CDNs cache content at edge locations close to users.

---

## Build It / In Depth

### A Concrete Learning Progression

The best way to learn cloud is to build a production-grade reference architecture incrementally. Here is the path, using AWS terminology (every concept maps 1:1 to Azure and GCP equivalents):

#### Step 1 — Understand the global infrastructure

Before touching a service, understand the physical structure:

```
Region  →  a geographic area (us-east-1, eu-west-2)
  └─ Availability Zone (AZ)  →  independent data center in a region
       └─ Edge Location  →  CDN point-of-presence

Design rule: place critical workloads across ≥2 AZs for high availability.
```

#### Step 2 — Network first, services second

Create a VPC with public and private subnets before deploying anything else:

```bash
# Create a VPC
aws ec2 create-vpc --cidr-block 10.0.0.0/16

# Public subnet: resources here can receive internet traffic
aws ec2 create-subnet --vpc-id vpc-xxx --cidr-block 10.0.1.0/24 \
  --availability-zone us-east-1a

# Private subnet: resources here can only be reached from within the VPC
aws ec2 create-subnet --vpc-id vpc-xxx --cidr-block 10.0.2.0/24 \
  --availability-zone us-east-1b

# Attach an Internet Gateway to allow outbound internet from public subnet
aws ec2 create-internet-gateway
aws ec2 attach-internet-gateway --vpc-id vpc-xxx --internet-gateway-id igw-xxx
```

Mental model: your VPC is your data center floor plan. Public subnets face the internet. Private subnets hold databases, queues, and internal services. Traffic between subnets flows through route tables.

#### Step 3 — Compute with least privilege

Launch a VM in the private subnet, and always attach an IAM role instead of hardcoding credentials:

```bash
# Create an IAM role that grants S3 read access — no long-term credentials
aws iam create-role --role-name MyEC2Role \
  --assume-role-policy-document file://trust-policy.json

aws iam attach-role-policy --role-name MyEC2Role \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess

# Launch instance with the role attached
aws ec2 run-instances \
  --image-id ami-0abcdef1234567890 \
  --instance-type t3.medium \
  --subnet-id subnet-xxx \
  --iam-instance-profile Name=MyEC2Role \
  --no-associate-public-ip-address
```

The instance now automatically gets short-lived credentials via the instance metadata service. No secrets in environment variables, no secrets in code.

#### Step 4 — Storage: right type for the job

```
Block  (EBS)    →  database data files, OS volumes, anything needing low latency
                   Attached to exactly one EC2 at a time.

Object (S3)     →  static assets, logs, backups, data lake files
                   Globally addressable, no capacity limit, pay per GB stored.

File   (EFS)    →  shared config, ML model weights, content management assets
                   Multiple EC2 or containers mount the same filesystem.

Archive (Glacier) → compliance backups, regulatory data retention
                    Retrieval measured in minutes to hours, not milliseconds.
```

#### Step 5 — Add observability before adding features

A common mistake is deploying infrastructure and treating monitoring as an afterthought. Set up the three pillars early:

```
Metrics  →  CloudWatch Metrics (AWS) / Azure Monitor / GCP Cloud Monitoring
            Numeric measurements over time: CPU%, request count, error rate

Logs     →  CloudWatch Logs / Azure Log Analytics / GCP Cloud Logging
            Structured text: application output, audit trails

Traces   →  AWS X-Ray / Azure App Insights / GCP Cloud Trace
            End-to-end request flow across distributed services
```

Create an alert before you deploy: if error rate > 1% over 5 minutes, page someone.

#### Step 6 — Automate everything with IaC

Once you understand what you are building, encode it in code so it is reproducible:

```hcl
# Terraform: define your VPC declaratively
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  tags = { Name = "production" }
}

resource "aws_subnet" "private" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "us-east-1b"
}
```

IaC makes your infrastructure reviewable, versionable, and deployable to multiple environments without manual steps.

---

## Use It

### Choosing a Cloud Provider

All three major providers offer equivalent primitives. The decision comes down to existing contracts, team familiarity, and specific managed service maturity:

| Criterion                  | AWS                          | Azure                         | GCP                           |
|----------------------------|------------------------------|-------------------------------|-------------------------------|
| Market share (2025)        | ~31%                         | ~25%                          | ~12%                          |
| Compute                    | EC2, Lambda, ECS/EKS         | VMs, Functions, AKS           | Compute Engine, Cloud Run, GKE |
| Object storage             | S3                           | Blob Storage                  | Cloud Storage                 |
| Managed Kubernetes         | EKS                          | AKS                           | GKE (most mature)             |
| Enterprise / AD integration | IAM + AWS SSO               | Entra ID (native)             | Cloud Identity                |
| Data / ML                  | Redshift, SageMaker          | Synapse, Azure ML             | BigQuery, Vertex AI           |
| Best fit                   | Widest service catalog       | Microsoft-heavy enterprise    | Data engineering, ML workloads|

Pick one provider and go deep on it before touching a second. The concepts transfer; the service names do not.

### Certifications as a Learning Structure

Certifications are controversial but make excellent structured curricula:

| Level       | AWS                              | Azure                          | GCP                           |
|-------------|----------------------------------|--------------------------------|-------------------------------|
| Foundational | AWS Cloud Practitioner          | AZ-900                         | Cloud Digital Leader          |
| Associate   | Solutions Architect Associate    | AZ-104 (Admin), AZ-204 (Dev)  | Associate Cloud Engineer      |
| Professional | Solutions Architect Professional | AZ-305                        | Professional Cloud Architect  |

Recommendation: use the **Associate-level exam guide** as your syllabus, not the Foundational. The Foundational is marketing material. The Associate guide forces you to understand networking, IAM, and core services at a functional depth.

---

## Common Pitfalls

- **Learning by memorizing service names instead of primitives.** When a new service launches, engineers who understand primitives can categorize it immediately. Engineers who memorized names are lost. Always ask: "Is this compute, storage, networking, or identity?"

- **Skipping networking.** Most cloud outages and security incidents trace back to misconfigured security groups, open S3 buckets, or missing VPC flow logs. Spend at least 20% of your learning time on VPCs, subnets, routing tables, and security group rules.

- **Hardcoding credentials.** Long-lived access keys in environment variables or code repositories are the most exploited cloud attack vector. Always use IAM roles for resources and OIDC federation for CI/CD pipelines.

- **Ignoring cost until the bill arrives.** Set up billing alerts on day one. Enable Cost Explorer. Tag resources from the start. A single forgotten GPU instance running overnight can cost more than a month of smaller workloads.

- **Trying to learn multiple providers simultaneously.** The mental overhead of keeping `aws s3 cp`, `az storage blob upload`, and `gcloud storage cp` straight while also learning IAM, VPCs, and Kubernetes is overwhelming. Pick one provider, go deep, then the second provider takes a fraction of the time.

---

## Exercises

1. **Easy** — Create an AWS free-tier account and deploy a static website using only S3 and CloudFront. Verify that the bucket is not publicly accessible (block public access is ON) and traffic is served only through the CloudFront distribution with HTTPS enforced.

2. **Medium** — Design a three-tier architecture (web tier, application tier, database tier) for a social media feed service on paper. Specify which subnet (public or private) each tier lives in, how security groups restrict traffic between tiers, and which managed service you would use for the database. Justify each choice.

3. **Hard** — Write a Terraform module that provisions a VPC with two public and two private subnets across two availability zones, an Application Load Balancer in the public subnets, and an Auto Scaling Group of EC2 instances in the private subnets. The ASG should scale out when CPU > 70% for 5 minutes and scale in when CPU < 30% for 10 minutes. Store the Terraform state in an S3 bucket with state locking via DynamoDB.

---

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|------------------------|
| Region | A city where a cloud provider has servers | A geographic cluster of data centers (Availability Zones) operated as a unit, with its own pricing and service availability |
| Availability Zone (AZ) | Redundant server in the same building | A physically separate data center with independent power, cooling, and networking — within driving distance of other AZs in the same region |
| IaaS | Just renting a server | Renting virtualized infrastructure (VMs, storage, network) where you are responsible for everything above the hypervisor, including the OS, patches, and runtime |
| Serverless | No servers exist | Servers still exist; you do not manage or provision them. You provide a function and a trigger; the provider handles scaling to zero and back |
| Security Group | A firewall on the edge of the network | A stateful, instance-level virtual firewall that controls inbound and outbound traffic per resource — not per subnet or VPC |
| IAM Role | A user account for a service | A set of permissions with no long-lived credentials, assumed temporarily by AWS resources (EC2, Lambda) or external identities via federation |
| Managed Service | A hosted version of open-source software | A service where the provider handles provisioning, patching, backups, failover, and scaling — you configure behavior, not infrastructure |

---

## Further Reading

- [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html) — The authoritative reference for designing reliable, secure, efficient, and cost-optimized cloud systems. Read the five pillars in order.
- [Google Cloud Architecture Framework](https://cloud.google.com/architecture/framework) — GCP's equivalent; the operational excellence and reliability sections contain vendor-neutral insights applicable everywhere.
- [Terraform: Up & Running (Gruntwork)](https://www.terraformupandrunning.com/) — The most practical IaC reference; works through real production patterns rather than toy examples.
- [AWS Certified Solutions Architect – Associate Study Guide (Official)](https://www.amazon.com/Certified-Solutions-Architect-Study-Guide/dp/1119713080) — Use the exam objectives as a structured checklist regardless of whether you intend to certify.
- [The Cloud Resume Challenge](https://cloudresumechallenge.dev/) — A project-based learning path that takes you from zero to deploying a full serverless web app with CI/CD, IaC, and a database in a single week.
