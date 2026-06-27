# How to Learn AWS?

> AWS is not a product — it is a platform of 200+ services; learning it means building a map, not memorizing an encyclopedia.

**Type:** Learn
**Prerequisites:** Containers & Docker Basics, Cloud Fundamentals, Networking (TCP/IP, DNS, Load Balancing)
**Time:** ~25 minutes

---

## The Problem

You have been hired as a backend engineer at a company that runs entirely on AWS. On day one, a teammate mentions "we use RDS in a private subnet behind an ALB, Lambda functions pull from SQS, and CloudWatch alarms feed PagerDuty." You nod. You have no idea what any of that means in operational terms. When the on-call alert fires at 2 AM, you cannot even navigate the AWS console to find the relevant logs.

This is the AWS knowledge gap. It is not about credentials or certification badges. The real problem is that AWS has over 200 distinct services and the documentation is 50,000+ pages long. Without a structured learning map, engineers either learn only what they touched accidentally, or they try to learn everything and burn out before building anything. Both paths leave dangerous blind spots: teams that misconfigure VPC security groups and expose databases publicly, set S3 buckets to public-read because they did not know about bucket policies, or over-provision EC2 instances for workloads that cost 1/10th as Lambda functions.

The goal of this lesson is to give you the mental map — the six layers of AWS knowledge, how they depend on each other, and a concrete study path that gets you productive in weeks rather than years.

---

## The Concept

### The Six-Layer AWS Mental Model

AWS services are not a flat list. They form a dependency stack. Understanding this layering is the key insight that lets you navigate the platform with confidence.

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 6: Learning Paths & Certifications                       │
│  (Cloud Practitioner → Solutions Architect → Specialty)         │
├─────────────────────────────────────────────────────────────────┤
│  Layer 5: DevOps, Monitoring & Automation                       │
│  (CodePipeline, CloudWatch, CloudTrail, CloudFormation, CDK)    │
├─────────────────────────────────────────────────────────────────┤
│  Layer 4: Security, Identity & Compliance                       │
│  (IAM, KMS, Secrets Manager, Security Groups, WAF, Shield)      │
├─────────────────────────────────────────────────────────────────┤
│  Layer 3: Databases & Data Services                             │
│  (RDS, DynamoDB, ElastiCache, Redshift, S3 Analytics)           │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2: Core Compute, Storage & Networking                    │
│  (EC2, Lambda, ECS/EKS, S3, EBS, VPC, ELB, Route 53)           │
├─────────────────────────────────────────────────────────────────┤
│  Layer 1: AWS Fundamentals                                      │
│  (Global Infrastructure, Billing, IAM Basics, AWS CLI)          │
└─────────────────────────────────────────────────────────────────┘
```

Each layer depends on the ones below it. You cannot reason about an RDS cluster without understanding VPCs (Layer 2). You cannot debug a Lambda permission error without understanding IAM (Layer 4 and 1). This is not arbitrary; it mirrors how AWS services actually compose at runtime.

---

### Layer 1 — AWS Fundamentals

Before writing a single line of infrastructure code, you need four concepts:

| Concept | Why it matters |
|---|---|
| Global Infrastructure | Regions, Availability Zones (AZs), and Edge Locations determine latency, resilience, and data sovereignty. |
| Billing & Cost Model | AWS charges per second / per request / per GB. Misunderstanding this burns budgets fast. |
| IAM Basics | Every API call is authenticated via IAM. Getting this wrong either blocks everything or exposes everything. |
| AWS CLI & Console | Two interfaces to the same API. You need both; scripts use CLI, debugging uses Console. |

**Key insight:** An AWS Region is a geographic cluster of isolated data centers. Each Region contains 2–6 Availability Zones (AZs). AZs are physically separate facilities connected by low-latency fiber. Deploying across AZs gives you fault tolerance at the infrastructure level without replicating across countries.

---

### Layer 2 — Core Compute, Storage & Networking

This is the foundation you will touch in almost every architecture.

**Compute:**

| Service | Model | When to use |
|---|---|---|
| EC2 | Virtual machine, you manage OS | Long-running services, stateful workloads, GPU |
| Lambda | Function-as-a-service, event-driven | Short-lived tasks, event processing, <15 min execution |
| ECS (Fargate) | Managed container orchestration | Containerized apps without managing EC2 |
| EKS | Managed Kubernetes | Teams already using Kubernetes, complex microservices |

**Storage:**

| Service | Type | Durability | Use case |
|---|---|---|---|
| S3 | Object store | 11 nines | Static assets, backups, data lake |
| EBS | Block device (attached to one EC2) | 99.999% | Database volumes, OS disks |
| EFS | Managed NFS (shared) | 99.999% | Shared filesystem across EC2 instances |
| Glacier / S3 Glacier | Cold object store | 11 nines | Archival, compliance, infrequent access |

**Networking — VPC is the most important service to understand deeply:**

```
Region: us-east-1
┌──────────────────────────────────────────────────────────┐
│  VPC 10.0.0.0/16                                         │
│                                                          │
│  ┌─────────────────┐    ┌─────────────────┐             │
│  │  Public Subnet  │    │  Private Subnet │             │
│  │  10.0.1.0/24    │    │  10.0.2.0/24    │             │
│  │                 │    │                 │             │
│  │  [ALB]          │───▶│  [EC2/RDS]      │             │
│  │  [NAT Gateway]  │    │                 │             │
│  └─────────────────┘    └─────────────────┘             │
│          │                                               │
│          ▼                                               │
│  [Internet Gateway]                                      │
└──────────┼───────────────────────────────────────────────┘
           │
      Internet
```

Resources in a private subnet cannot receive inbound traffic from the internet directly. A NAT Gateway lets them initiate outbound connections (for software updates, API calls) without being exposed. An Application Load Balancer (ALB) in the public subnet accepts inbound HTTPS traffic and routes it to private EC2 instances.

Route 53 is AWS's DNS service. It integrates with other AWS services for health-check-based routing, latency-based routing, and geolocation routing.

---

### Layer 3 — Databases & Data Services

| Service | Type | Key characteristic |
|---|---|---|
| RDS (MySQL, PostgreSQL, etc.) | Relational | Managed, Multi-AZ failover, automated backups |
| Aurora | Relational (AWS-native) | 5x faster than MySQL, serverless option |
| DynamoDB | NoSQL key-value/document | Single-digit millisecond latency, serverless |
| ElastiCache (Redis) | In-memory | Cache layer, session store, pub/sub |
| ElastiCache (Memcached) | In-memory | Simple caching, no persistence |
| Redshift | Columnar data warehouse | OLAP queries over petabytes |

**Rule of thumb:** Use RDS or Aurora for transactional relational data (OLTP). Use DynamoDB when you need horizontal scale with predictable latency at any size. Use Redshift for analytics over historical data. Use ElastiCache to sit in front of either.

---

### Layer 4 — Security, Identity & Compliance

IAM is central to everything. The mental model:

```
  IAM Principal (User / Role / Service)
       │
       │ has attached
       ▼
  IAM Policy  ──── Effect: Allow | Deny
               ──── Action: s3:GetObject, ec2:DescribeInstances, ...
               ──── Resource: arn:aws:s3:::my-bucket/*
               ──── Condition: (optional) IP, MFA, time-of-day
```

**IAM Roles vs. IAM Users:** Users are for humans. Roles are for machines (EC2 instances, Lambda functions, ECS tasks). An EC2 instance assumes an IAM Role, which grants it temporary credentials to call other AWS services without hard-coding access keys. If you see hard-coded `AWS_ACCESS_KEY_ID` in an application, that is a security smell — replace with a role.

**Encryption:**
- **KMS (Key Management Service):** Managed key store. You control keys; AWS services (S3, RDS, EBS) use KMS keys for server-side encryption.
- **S3 SSE (Server-Side Encryption):** Encrypts objects at rest. Three modes: SSE-S3 (AWS manages keys), SSE-KMS (you manage keys in KMS), SSE-C (you provide keys).
- **Secrets Manager:** Store database passwords, API tokens. Supports automatic rotation.

**VPC Security:** Two layers — Security Groups (stateful, instance-level firewall) and Network ACLs (stateless, subnet-level). Security Groups are the primary tool in practice.

---

### Layer 5 — DevOps, Monitoring & Automation

| Service | Purpose |
|---|---|
| CloudFormation | Infrastructure as Code (declarative JSON/YAML templates) |
| AWS CDK | IaC using real programming languages (TypeScript, Python) that compile to CloudFormation |
| CodeCommit | Git repository hosting (largely replaced by GitHub/GitLab in practice) |
| CodeBuild | Managed CI build service |
| CodePipeline | CI/CD pipeline orchestration |
| CloudWatch | Metrics, logs, alarms, dashboards |
| CloudTrail | Audit log of every API call made in your account |
| AWS Config | Tracks configuration changes to resources over time |

**CloudWatch vs. CloudTrail — the most common confusion:**

| | CloudWatch | CloudTrail |
|---|---|---|
| What it captures | Resource metrics and application logs | API-level audit events ("who called what when") |
| Primary use | Operational monitoring, alerting | Security auditing, compliance, debugging IAM denials |
| Example | CPU utilization of an EC2 instance | "User alice called ec2:TerminateInstance at 14:03 UTC" |

---

### Layer 6 — Certifications and Structured Learning

AWS certifications provide official proof of knowledge and impose a useful curriculum structure:

```
Entry-Level
└── AWS Certified Cloud Practitioner (CLF-C02)
    └── Good for: managers, non-engineers, anyone needing a foundation

Associate Level (pick your path)
├── Solutions Architect Associate (SAA-C03)  ← most popular, design focus
├── Developer Associate (DVA-C02)            ← coding + deployment focus
└── SysOps Administrator Associate           ← operations focus

Professional Level
├── Solutions Architect Professional
└── DevOps Engineer Professional

Specialty
├── Security Specialty
├── Machine Learning Specialty
├── Database Specialty
└── Advanced Networking Specialty
```

The **Solutions Architect Associate** is the highest-ROI certification for most engineers. It covers all six layers of the mental model and is the prerequisite mindset for designing any non-trivial AWS architecture.

---

## Build It / In Depth

The best way to internalize AWS is to build a small but realistic system using real services. Here is a learning sequence that escalates through all six layers:

**Phase 1: Set Up Your AWS Account and IAM**

```bash
# Install and configure the AWS CLI
brew install awscli                  # macOS
aws configure                        # enter Access Key, Secret, Region, output format

# Verify identity
aws sts get-caller-identity

# Create an IAM group with read-only access for safe exploration
aws iam create-group --group-name Learners
aws iam attach-group-policy \
  --group-name Learners \
  --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess
```

**Phase 2: Launch a VPC and EC2 Instance**

```bash
# Create a VPC
aws ec2 create-vpc --cidr-block 10.0.0.0/16 --query 'Vpc.VpcId' --output text
# → vpc-0abc123

# Create a public subnet
aws ec2 create-subnet \
  --vpc-id vpc-0abc123 \
  --cidr-block 10.0.1.0/24 \
  --availability-zone us-east-1a

# Launch a t3.micro EC2 instance (free tier)
aws ec2 run-instances \
  --image-id ami-0c02fb55956c7d316 \
  --instance-type t3.micro \
  --subnet-id subnet-0xyz789 \
  --key-name my-keypair \
  --security-group-ids sg-0abc123
```

**Phase 3: Put Something Behind S3 and Lambda**

```python
# lambda_function.py — minimal Lambda handler
import json
import boto3

s3 = boto3.client('s3')

def lambda_handler(event, context):
    bucket = event['bucket']
    key    = event['key']
    obj    = s3.get_object(Bucket=bucket, Key=key)
    data   = obj['Body'].read().decode('utf-8')
    return {
        'statusCode': 200,
        'body': json.dumps({'content': data})
    }
```

Deploy via the CLI:

```bash
zip function.zip lambda_function.py
aws lambda create-function \
  --function-name s3-reader \
  --runtime python3.12 \
  --role arn:aws:iam::123456789:role/lambda-s3-role \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://function.zip
```

**Phase 4: Add a Managed Database (RDS)**

```bash
# Create a PostgreSQL RDS instance in the private subnet
aws rds create-db-instance \
  --db-instance-identifier mydb \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --master-username admin \
  --master-user-password "ChangeMePlease123!" \
  --allocated-storage 20 \
  --vpc-security-group-ids sg-private \
  --db-subnet-group-name my-private-subnet-group \
  --no-publicly-accessible
```

**Phase 5: Add Monitoring**

```bash
# Create a CloudWatch alarm for high CPU on EC2
aws cloudwatch put-metric-alarm \
  --alarm-name "HighCPU" \
  --metric-name CPUUtilization \
  --namespace AWS/EC2 \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=InstanceId,Value=i-0abc123 \
  --evaluation-periods 2 \
  --alarm-actions arn:aws:sns:us-east-1:123456789:alerts
```

After completing these five phases you will have touched all six conceptual layers with real resources.

---

## Use It

### Real-World Deployment Patterns Using This Map

**Serverless Web API:**
Route 53 → CloudFront → API Gateway → Lambda → DynamoDB + S3
- Security: Lambda execution role (IAM), API Gateway authorizer (Cognito or custom)
- Monitoring: CloudWatch Logs for Lambda, X-Ray for tracing

**Traditional Three-Tier Web App:**
Route 53 → ALB (public subnet) → EC2 Auto Scaling Group (private subnet) → RDS Multi-AZ (private subnet)
- Security: Security Groups isolating each tier, Secrets Manager for DB credentials
- Monitoring: CloudWatch metrics on EC2 and RDS, CloudTrail for audit

**Data Pipeline:**
S3 → Lambda → SQS → Lambda → Redshift or DynamoDB
- Security: S3 bucket policy, VPC endpoints so traffic stays within AWS
- Monitoring: SQS queue depth as a CloudWatch metric

### Which Compute to Choose

```
Is the task event-driven and < 15 minutes?
   YES → Lambda
   NO  → Is it containerized?
            YES → ECS Fargate or EKS
            NO  → EC2 (with Auto Scaling Group for production)
```

---

## Common Pitfalls

- **Starting with certifications instead of building things.** Watching 40 hours of video without a personal AWS account produces shallow knowledge. Certifications are validation, not a substitute for hands-on time. Build first, certify second.

- **Treating IAM as an afterthought.** Teams often start with broad permissions (`AdministratorAccess` on Lambda functions) and "clean up later." Later never comes. Follow least-privilege from day one — grant only the specific actions the resource needs.

- **Confusing Availability Zones with Regions.** A Region is not an AZ. Multi-AZ deployments protect you from a single data-center failure but not from a regional outage. Decide up front whether your SLA requires cross-region replication.

- **Ignoring Cost Alerts.** A misconfigured NAT Gateway, an accidentally large EC2 instance, or undeleted EBS snapshots can generate thousands of dollars in charges. Set a billing alert at your expected monthly spend on day one using CloudWatch + SNS.

- **Copying security group settings from Stack Overflow.** Generic tutorials often set `0.0.0.0/0` as the inbound source on security groups to "just make it work." In production, inbound source should be another Security Group ID, a specific CIDR, or the load balancer's Security Group — never the entire internet for database ports.

---

## Exercises

1. **Easy — IAM Exploration:** In your AWS Console (or CLI), list all IAM policies attached to your current user or role. Identify which policy grants you S3 access. Read its JSON and enumerate what actions it allows and which resources it restricts to.

2. **Medium — Build a Static Site with HTTPS:** Host a static website using S3 (enable Static Website Hosting), serve it through CloudFront with a custom domain, and provision an ACM certificate for HTTPS. Document the sequence of services involved and draw a request-flow diagram.

3. **Hard — Three-Tier App with IaC:** Using AWS CDK (TypeScript or Python), define a VPC with public and private subnets, an ALB in the public subnet, an Auto Scaling Group of EC2 instances in the private subnet, and an RDS PostgreSQL instance in a separate DB subnet group. Deploy the stack to a real account and verify that the EC2 instances can reach RDS but the RDS instance has no public IP.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Region | A country or continent | A geographic cluster of 2–6 isolated data centers (AZs) managed as a unit — a specific city (e.g., us-east-1 = Northern Virginia) |
| Availability Zone (AZ) | Synonym for Region | One physically separate data center within a Region, connected to others by low-latency fiber; deployments span AZs for fault tolerance |
| IAM Role | Like a user account for services | A set of temporary, automatically rotated credentials that AWS services assume at runtime — no long-lived secret keys |
| Security Group | A network firewall at the VPC edge | A stateful, instance-level virtual firewall — each EC2, RDS, or Lambda (in VPC) instance has its own Security Group(s) |
| S3 Bucket | Just a folder in the cloud | A globally unique, flat namespace object store with its own access control model (bucket policies, ACLs, Object Lock) |
| CloudWatch | AWS's monitoring dashboard | A metrics, logs, and alarms platform — stores time-series data, lets you query logs with Insights, and triggers alarms via SNS |
| Lambda Cold Start | A random slowdown | The latency cost of provisioning a new execution environment for a function that has not run recently — typically 100ms–1s depending on runtime |

---

## Further Reading

- [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html) — AWS's official guide to building production-grade systems across the five pillars: operational excellence, security, reliability, performance efficiency, and cost optimization.
- [AWS Skill Builder](https://skillbuilder.aws/) — AWS's official learning platform with free and paid courses, labs, and exam prep paths for all certification tracks.
- [AWS Certified Solutions Architect Study Guide (Sybex)](https://www.wiley.com/en-us/AWS+Certified+Solutions+Architect+Study+Guide%3A+Associate+SAA+C03+Exam%2C+4th+Edition-p-9781119982623) — One of the most comprehensive exam prep books, also useful as a reference without pursuing certification.
- [The Open Guide to Amazon Web Services](https://github.com/open-guides/og-aws) — A community-maintained, practitioner-written reference covering gotchas, cost tips, and service comparisons not found in official docs.
- [AWS Architecture Center](https://aws.amazon.com/architecture/) — Curated reference architectures for common workloads (web apps, data lakes, ML pipelines) with diagrams and CloudFormation templates you can deploy directly.
