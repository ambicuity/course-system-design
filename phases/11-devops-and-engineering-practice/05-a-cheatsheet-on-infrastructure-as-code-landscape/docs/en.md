# A Cheatsheet on Infrastructure as Code Landscape

> Treat your servers like cattle, not pets — define everything in code and rebuild rather than repair.

**Type:** Learn
**Prerequisites:** CI/CD Pipelines, Container Basics, Cloud Fundamentals
**Time:** ~25 minutes

---

## The Problem

It is Monday morning and your team needs to spin up a staging environment that mirrors production. A senior engineer spends two days SSHing into machines, running commands from memory, and tweaking config files. The environment still drifts from production by the time it is ready. When a security patch needs to be applied to 40 servers, someone manually runs commands on each one, misses three, and those three get compromised six weeks later.

Manual infrastructure management has three compounding failure modes: **drift** (environments diverge from their intended state over time), **toil** (every change requires human repetition), and **opacity** (nobody fully knows what is actually running). A new engineer can't onboard because "the infra knowledge lives in Dave's head."

Infrastructure as Code (IaC) solves all three by treating infrastructure definitions the same way you treat application code — stored in version control, reviewed via pull requests, tested in CI, and deployed automatically. The challenge is that "IaC" is now an umbrella term covering four distinct layers with overlapping tools. Picking the wrong tool for the wrong layer, or conflating layers, is the source of most team friction.

---

## The Concept

### The Four Layers of Modern IaC

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 4 — GitOps / Continuous Delivery                     │
│  ArgoCD · Flux · Spinnaker                                  │
├─────────────────────────────────────────────────────────────┤
│  Layer 3 — Orchestration                                    │
│  Kubernetes · ECS · Nomad                                   │
├─────────────────────────────────────────────────────────────┤
│  Layer 2 — Configuration Management                         │
│  Ansible · Chef · Puppet · SaltStack                        │
├─────────────────────────────────────────────────────────────┤
│  Layer 1 — Infrastructure Provisioning                      │
│  Terraform · Pulumi · AWS CDK · CloudFormation              │
├─────────────────────────────────────────────────────────────┤
│  Foundation — Containerization                              │
│  Docker · Podman · Buildah                                  │
└─────────────────────────────────────────────────────────────┘
```

Each layer answers a different question:

| Layer | Question answered | Key abstraction |
|---|---|---|
| Containerization | How do I package this app? | Image / Container |
| Provisioning | What cloud resources exist? | VPC, VM, RDS, S3 |
| Configuration Mgmt | What software runs on those resources? | Role / Playbook |
| Orchestration | How do containers get scheduled and healed? | Pod / Service / Deployment |
| GitOps | How does the desired state flow from Git to the cluster? | Sync loop |

### Declarative vs. Imperative

All mature IaC tools lean declarative: you describe the desired end state, the tool figures out the sequence of API calls needed to reach it.

```
Imperative (shell script):
  aws ec2 run-instances --image-id ami-123 ...
  aws ec2 create-security-group ...
  aws ec2 authorize-security-group-ingress ...
  # Fails on re-run if resources already exist

Declarative (Terraform HCL):
  resource "aws_instance" "web" {
    ami           = "ami-123"
    instance_type = "t3.micro"
  }
  # Safe to apply again — Terraform diffs against actual state
```

The declarative model is idempotent by design. Running it ten times produces the same result as running it once.

### Mutable vs. Immutable Infrastructure

**Mutable**: Servers live long lives and are modified in place (config updates, patches). Drift accumulates. This is what Ansible and Chef traditionally managed.

**Immutable**: Servers are never modified. To deploy a change, you build a new image (AMI, Docker image), provision new instances, shift traffic, and destroy old ones. Blue-green and canary deployments are immutable patterns. Kubernetes enforces immutability at the container level.

Modern stacks often mix both: Terraform provisions immutable cloud resources, and Kubernetes manages immutable container images on top of them.

### State Management in Provisioning Tools

Terraform maintains a **state file** (`.tfstate`) that maps your HCL definitions to real cloud resource IDs. This is what enables idempotent applies. The state file must be stored remotely (S3 + DynamoDB for locking, Terraform Cloud) in team settings — never committed to Git.

```
terraform plan   →  diffs desired state (HCL) vs current state (tfstate) vs real world
terraform apply  →  reconciles real world to desired state, updates tfstate
terraform destroy →  tears down all resources tracked in tfstate
```

CloudFormation uses a similar concept called a **stack** but state is managed by AWS itself, eliminating the remote-state bootstrapping problem.

---

## Build It / In Depth

### A Worked Provisioning Example: Web App on AWS

**Step 1 — Containerize the app**

```dockerfile
# Dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app .
EXPOSE 3000
CMD ["node", "server.js"]
```

Build and push to ECR:
```bash
docker build -t my-app:v1.2.0 .
docker tag my-app:v1.2.0 123456789.dkr.ecr.us-east-1.amazonaws.com/my-app:v1.2.0
docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/my-app:v1.2.0
```

**Step 2 — Provision infrastructure with Terraform**

```hcl
# main.tf
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
  backend "s3" {
    bucket         = "my-tfstate"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "tf-lock"
  }
}

resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
  tags       = { Name = "prod-vpc" }
}

resource "aws_eks_cluster" "main" {
  name     = "prod-cluster"
  role_arn = aws_iam_role.eks.arn
  vpc_config {
    subnet_ids = aws_subnet.private[*].id
  }
}
```

**Step 3 — Deploy application manifests via GitOps**

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: my-app
  template:
    spec:
      containers:
      - name: my-app
        image: 123456789.dkr.ecr.us-east-1.amazonaws.com/my-app:v1.2.0
        resources:
          requests: { cpu: "100m", memory: "128Mi" }
          limits:   { cpu: "500m", memory: "256Mi" }
```

ArgoCD watches this repository. When `v1.2.0` is merged to `main`, ArgoCD detects drift between the live cluster and the Git-declared state and reconciles automatically (pull-based deployment).

### GitOps: Push vs. Pull Model

```
PUSH (traditional CI/CD):
  CI pipeline → kubectl apply → cluster
  Problem: CI needs cluster credentials. Blast radius on credential leak is large.

PULL (GitOps):
  Git ←── ArgoCD polls ──→ diff ──→ reconcile
  ArgoCD runs inside the cluster. No external system needs write access.
  Credentials never leave the cluster boundary.
```

---

## Use It

### Tool Selection Guide

| Need | Tool | Why |
|---|---|---|
| Provision cloud resources (multi-cloud) | **Terraform / OpenTofu** | HCL, huge provider ecosystem, state management |
| Provision AWS resources (AWS-native) | **CloudFormation / CDK** | Deep AWS integration, no state file to manage |
| Provision using a real programming language | **Pulumi** | Python/TypeScript/Go; enables loops, functions, unit tests |
| Configure VMs / run ad-hoc commands | **Ansible** | Agentless, YAML playbooks, SSH-based |
| Manage Kubernetes workloads | **Helm** (packaging) + **ArgoCD/Flux** (delivery) | Templating + continuous sync loop |
| Service mesh (mTLS, traffic shaping) | **Istio / Linkerd** | Runs as a sidecar in each pod |
| Secrets management | **Vault / AWS Secrets Manager + External Secrets Operator** | Never store secrets in Git |

### When NOT to Use Kubernetes

Kubernetes solves orchestration at scale but adds operational complexity. For a team of three running a single service:
- A single ECS service + ALB is cheaper and simpler.
- A managed PaaS (Railway, Render, Fly.io) reduces IaC surface area dramatically.
- Kubernetes earns its keep when you have multiple teams, many services, or need fine-grained autoscaling and scheduling.

---

## Common Pitfalls

- **Storing `terraform.tfstate` in Git.** State files contain plaintext secrets (RDS passwords, API keys). Use remote backends (S3 + DynamoDB, Terraform Cloud) from day one, before you have a team.

- **Conflating configuration management with provisioning.** Ansible is excellent at configuring existing servers; it is a poor substitute for Terraform when creating cloud resources. Using Ansible's `ec2` modules for provisioning leads to fragile imperative scripts without state tracking.

- **Skipping resource tagging.** Every cloud resource should carry at minimum `env`, `team`, and `service` tags. Without tags, cost attribution and incident scoping become archaeology exercises.

- **Not pinning provider/module versions.** `terraform { required_providers { aws = { version = ">= 3.0" } } }` will silently upgrade to a breaking major version the next time a new team member runs `terraform init`. Pin to `~> 5.0`.

- **Treating GitOps as a deployment-only tool and ignoring drift detection.** The core value of ArgoCD/Flux is continuous reconciliation, not just initial deploys. Disabling auto-sync or ignoring `OutOfSync` alerts defeats the purpose and reintroduces manual drift.

---

## Exercises

1. **Easy** — Write a Terraform configuration that creates an S3 bucket with versioning enabled and a lifecycle rule that moves objects to Glacier after 90 days. Run `terraform plan` and explain each field in the plan output.

2. **Medium** — Take an existing Ansible playbook that installs Nginx on a VM and convert the infrastructure-creation portion (VM, security group, subnet) to Terraform while keeping Ansible only for the software configuration step. Document the boundary between the two tools.

3. **Hard** — Design a GitOps pipeline for a microservices app: Terraform manages the EKS cluster, Helm charts package each service, and ArgoCD `ApplicationSet` deploys per-environment. Add a pre-production promotion gate that requires a manual approval step before syncing to production. Sketch the full flow from a developer's `git push` to a production pod restart.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Infrastructure as Code** | Writing Bash scripts to provision servers | Declarative, version-controlled definitions of infrastructure that a tool reconciles against real cloud state |
| **Idempotent** | "It won't fail if you run it twice" | Running an operation N times produces the same end state as running it once — regardless of what was there before |
| **Terraform State** | A log file of what Terraform did | The source of truth mapping HCL resource names to real cloud resource IDs; required for plan/apply to work correctly |
| **GitOps** | "CI/CD that uses Git" | A specific pattern where Git is the single source of truth and an agent inside the cluster pulls and reconciles state continuously |
| **Immutable Infrastructure** | Never patching servers (impractical) | Replacing rather than modifying infrastructure units; change the image, not the running container |
| **Configuration Drift** | Minor differences between environments | The accumulation of undocumented, manual changes that cause environments to diverge from their intended state over time |
| **Helm Chart** | A Kubernetes config file | A parameterized package of Kubernetes manifests with a template engine, versioned and distributable via a chart repository |

---

## Further Reading

- [Terraform Documentation — Official](https://developer.hashicorp.com/terraform/docs)
- [OpenTofu (open-source Terraform fork)](https://opentofu.org/docs/)
- [Argo CD — Getting Started](https://argo-cd.readthedocs.io/en/stable/getting_started/)
- [AWS CDK Developer Guide](https://docs.aws.amazon.com/cdk/v2/guide/home.html)
- [Google SRE Book — Chapter 7: The Evolution of Automation at Google](https://sre.google/sre-book/the-evolution-of-automation/)
