# How Amazon S3 Works?

> One of the largest distributed systems ever built — the architecture that backs 350 trillion objects at 99.999999999% durability.

**Type:** Learn
**Prerequisites:** Basic distributed systems, HTTP / REST, AWS fundamentals
**Time:** ~25 minutes

---

## The Problem

S3 looks simple from the outside: `PUT` an object, `GET` it back, pay for what you use. Underneath, it is one of the largest and most complex distributed systems ever built — handling millions of requests per second, storing hundreds of trillions of objects, and promising eleven nines of durability. That simplicity on top of staggering complexity is the architectural achievement.

Most engineers use S3 daily but do not understand what is happening when they call `s3:GetObject`. Understanding the architecture helps you reason about latency, durability guarantees, costs, failure modes, and which S3 feature to use for which workload.

This lesson walks the S3 architecture end-to-end: how a request flows from your application through S3's microservices, how data is stored and protected, and how S3 achieves its scale and durability promises.

---

## The Concept

### The scale S3 operates at

```
   Storage volume:    350+ trillion objects
   Request rate:      millions per second
   Durability:        99.999999999% (eleven nines)
                     = average loss of one object per 10,000 years per 10M objects
   Availability:      99.9% (Standard) to 99.99% (Standard-IA)
   Geographic span:   30+ regions, 100+ availability zones
```

The "eleven nines" durability claim deserves a moment. It is not "your object will be there when you ask." It is "given the failure rates of the underlying storage, the expected rate of object loss is astronomically low." S3 achieves this through aggressive redundancy and continuous auditing.

---

### The high-level architecture

S3 is built as a collection of cooperating microservices. There is no monolithic service.

```
   ┌─────────────────────────────────────────────────────────────┐
   │                                                             │
   │   Front-end services        Indexing services               │
   │   (request handling,        (where objects live,            │
   │    auth, validation)         metadata)                      │
   │                                                             │
   │   Storage services          Durability services             │
   │   (physical disk write,     (checksums, repair,             │
   │    erasure coding)           audits)                        │
   │                                                             │
   │   Security services         (IAM, bucket policy,            │
   │                               DDoS protection)              │
   │                                                             │
   └─────────────────────────────────────────────────────────────┘
```

Each tier is independent, horizontally scalable, and replaceable. The microservices talk to each other over internal protocols.

---

### Layer 1: Front-end Request Handling Services

The first stop for every API call. This tier handles authentication, validation, and routing.

```
   Client application
        │
        │ HTTPS: PUT /my-bucket/my-object
        ▼
   ┌─────────────────────────────────────────────────────┐
   │  Front-end service                                  │
   │                                                     │
   │  1. DNS resolution → nearest S3 endpoint            │
   │  2. TLS termination                                 │
   │  3. Request parsing                                  │
   │  4. Authentication                                   │
   │     - SigV4 signature verification                  │
   │     - IAM role / user / anonymous                   │
   │  5. Authorization                                    │
   │     - Bucket policy check                           │
   │     - IAM policy check                              │
   │     - ACL check (legacy)                            │
   │  6. Request validation                               │
   │     - Bucket exists?                                │
   │     - Object key valid?                             │
   │     - Request size within limits?                   │
   │  7. Routing decision                                 │
   │     - Which storage node holds this object?         │
   │     - Looked up via the indexing service            │
   └─────────────────────────────────────────────────────┘
```

**What this tier optimizes for:** throughput, authentication latency, and DDoS protection. Every S3 API call hits a front-end service first.

**Common performance considerations:**

- Use S3 Transfer Acceleration for cross-region uploads
- Use multipart uploads for objects > 100 MB
- Use VPC endpoints to avoid the public internet
- Use SigV4 pre-signed URLs to delegate access without exposing credentials

---

### Layer 2: Indexing and Metadata Services

S3 needs to know where every object lives. The indexing tier is the brain.

```
   ┌─────────────────────────────────────────────────────┐
   │  Indexing service                                   │
   │                                                     │
   │  Stores:                                            │
   │    - Object key → storage node mapping              │
   │    - Object metadata (size, content-type, custom)   │
   │    - Versioning info (if versioning is enabled)     │
   │    - Object ACL and ownership                       │
   │                                                     │
   │  Implementation:                                    │
   │    - Global metadata store (replicated, consistent) │
   │    - Partitioning engine (shards the keyspace)      │
   │    - Hot/cold tiers (recent objects cached locally) │
   └─────────────────────────────────────────────────────┘
```

The keyspace is partitioned by bucket and key prefix. Different prefixes land on different metadata partitions. This is why S3 performance for "list all objects in a bucket" depends heavily on prefix distribution — a million objects under one prefix is much slower than a million objects under a million prefixes.

**The "single-tenant partition" lesson:** if one customer writes too many objects to one prefix, they overload that partition. AWS throttles such requests. The mitigation is to randomize key prefixes (`/2024-01-01-<uuid>/file.json`) to spread load.

---

### Layer 3: Storage and Data Placement Services

The actual disk I/O happens here. This tier writes objects to disk with erasure coding for redundancy.

```
   PUT /my-bucket/my-object (5 MB image)

   ┌─────────────────────────────────────────────────────┐
   │  Storage service                                    │
   │                                                     │
   │  1. Receive object data from front-end              │
   │  2. Compute erasure-coding fragments                │
   │     - Split into k data fragments                   │
   │     - Generate m parity fragments                   │
   │     - Any k of (k+m) can reconstruct                │
   │                                                     │
   │  3. Distribute fragments across multiple AZs         │
   │     - Fragment A → AZ1, Disk 1                     │
   │     - Fragment B → AZ1, Disk 2                     │
   │     - Fragment C → AZ2, Disk 1                     │
   │     - ...                                           │
   │                                                     │
   │  4. Acknowledge write once fragments are persisted  │
   └─────────────────────────────────────────────────────┘
```

**Erasure coding** is the key to S3's durability. Instead of replicating the full object three times (which costs 3× the storage), S3 splits the object into fragments and writes fragments across disks in multiple Availability Zones. As long as enough fragments survive, the object can be reconstructed. Typical settings allow recovery even if 2 AZs are lost simultaneously.

```
   Original object (5 MB) → split into 6 data + 3 parity = 9 fragments
   Spread across 3 AZs (3 fragments per AZ)
   → Can lose any 3 fragments and still reconstruct
   → Storage overhead: 1.5× (vs 3× for full replication)
```

S3's standard storage uses erasure coding tuned for very high durability at reasonable storage cost. For lower-cost tiers (S3 Glacier), the tuning favors storage cost over reconstruction latency.

---

### Layer 4: Durability and Recovery Services

Once data is on disk, S3 continuously verifies it can be retrieved.

```
   ┌─────────────────────────────────────────────────────┐
   │  Durability services                                │
   │                                                     │
   │  1. Checksum verification                           │
   │     - Every fragment has a checksum                 │
   │     - Periodic scans recompute checksums            │
   │     - Corrupted fragments detected and repaired     │
   │                                                     │
   │  2. Background auditing                             │
   │     - Independent processes scan storage            │
   │     - Compare actual data to expected (indexed)     │
   │     - Flag and repair inconsistencies               │
   │                                                     │
   │  3. Disaster recovery                               │
   │     - Cross-region replication (if configured)      │
   │     - Lifecycle policies to move data to cheaper    │
   │       tiers or expire it                            │
   │     - Object Lock for compliance (WORM storage)     │
   └─────────────────────────────────────────────────────┘
```

The "eleven nines" durability is achieved through continuous auditing and repair. When a disk fails, S3 detects it (via the auditing tier), reconstructs the lost fragments from surviving ones, and writes them to a healthy disk. The customer never sees the failure — by the time they request the object, the fragments are restored.

---

### Layer 5: Security and Compliance Services

```
   ┌─────────────────────────────────────────────────────┐
   │  Security services                                  │
   │                                                     │
   │  - IAM policies (who can do what)                   │
   │  - Bucket policies (resource-level rules)           │
   │  - ACLs (legacy per-object permissions)             │
   │  - Server-side encryption (SSE-S3, SSE-KMS, SSE-C)  │
   │  - TLS in transit (HTTPS only by default)           │
   │  - DDoS mitigation (AWS Shield)                     │
   │  - Object Lock (WORM, compliance)                   │
   │  - Versioning (recover from accidental delete)      │
   │  - Access logging (CloudTrail)                      │
   │  - MFA Delete (require MFA for destructive ops)     │
   └─────────────────────────────────────────────────────┘
```

Security is enforced at multiple layers — front-end (authentication), storage (encryption at rest), network (TLS, VPC endpoints), and audit (CloudTrail logs every API call).

---

### The end-to-end PUT flow

```
   Client                              S3
     │                                  │
     │  1. DNS resolve → nearest edge    │
     │─────────────────────────────────►│
     │                                  │
     │  2. HTTPS PUT /bucket/key         │
     │     (TLS + SigV4 signature)       │
     │─────────────────────────────────►│
     │                                  │
     │                          ┌───────┴────────┐
   [3. Front-end: auth + authz + validation]
     │                                  │
     │                          ┌───────┴────────┐
   [4. Indexing: where does this object belong?]
     │                                  │
     │                          ┌───────┴────────┐
   [5. Storage: erasure-code + write to multiple AZs]
     │                                  │
     │                          ┌───────┴────────┐
   [6. Durability: checksum + ack]
     │                                  │
     │  7. HTTP 200 OK                   │
     │◄─────────────────────────────────│
     │                                  │
```

The client sees ~50–200 ms for a PUT to a nearby region. The internal steps take longer in aggregate but are parallelized.

---

### The end-to-end GET flow

```
   Client                              S3
     │                                  │
     │  1. DNS resolve → nearest edge   │
     │─────────────────────────────────►│
     │                                  │
     │  2. HTTPS GET /bucket/key         │
     │─────────────────────────────────►│
     │                                  │
     │                          ┌───────┴────────┐
   [3. Front-end: auth + authz + validation]
     │                                  │
     │                          ┌───────┴────────┐
   [4. Indexing: which fragments, which AZs?]
     │                                  │
     │                          ┌───────┴────────┐
   [5. Storage: read k of (k+m) fragments in parallel]
     │                                  │
     │                          ┌───────┴────────┐
   [6. Storage: reconstruct object from fragments]
     │                                  │
     │                          ┌───────┴────────┐
   [7. Durability: verify checksum against manifest]
     │                                  │
     │  8. HTTPS 200 + object data      │
     │◄─────────────────────────────────│
     │                                  │
```

GETs are faster than PUTs because no new fragments are written and reconstruction is parallelized.

---

### Storage classes: the durability/cost trade-off

| Class | Durability | Availability | Use case | Cost (per GB/month) |
|---|---|---|---|---|
| **S3 Standard** | 99.999999999% | 99.99% | Frequently accessed data | ~$0.023 |
| **S3 Intelligent-Tiering** | 99.999999999% | 99.9% | Unknown access patterns | ~$0.023 + monitoring fee |
| **S3 Standard-IA** | 99.999999999% | 99.9% | Infrequent access, fast retrieval | ~$0.0125 + retrieval fee |
| **S3 One Zone-IA** | 99.999999999% | 99.5% | Re-creatable infrequent data | ~$0.01 |
| **S3 Glacier Instant** | 99.999999999% | 99.9% | Archive, instant retrieval | ~$0.004 |
| **S3 Glacier Flexible** | 99.999999999% | 99.9% (after retrieval) | Archive, minutes-to-hours retrieval | ~$0.0036 |
| **S3 Glacier Deep** | 99.999999999% | 99.9% (after retrieval, 12+ hour) | Long-term archive | ~$0.00099 |
| **S3 Outposts** | As configured | As configured | On-premises S3 | Varies |

The durability is the same across classes (eleven nines). What differs is **availability** (can you read it instantly), **retrieval latency**, and **cost**. Pick the cheapest class whose retrieval characteristics you can live with.

---

## Build It / In Depth

### A production-grade S3 usage pattern

```python
import boto3
from botocore.config import Config

# Configure for production
s3 = boto3.client(
    "s3",
    config=Config(
        retries={"max_attempts": 5, "mode": "adaptive"},
        max_pool_connections=50,
    ),
)

def upload_large_file(bucket: str, key: str, file_path: str):
    """Multipart upload for files > 100 MB."""
    from boto3.s3.transfer import TransferConfig

    config = TransferConfig(
        multipart_threshold=100 * 1024 * 1024,  # 100 MB
        multipart_chunksize=50 * 1024 * 1024,   # 50 MB parts
        max_concurrency=10,
        use_threads=True,
    )
    s3.upload_file(file_path, bucket, key, Config=config)

def generate_presigned_url(bucket: str, key: str, expires_in: int = 3600):
    """Generate a temporary URL for direct browser upload/download."""
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )

def list_objects_paginated(bucket: str, prefix: str = ""):
    """Handle large buckets with pagination."""
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            yield obj
```

Three patterns worth highlighting:

1. **Multipart uploads** for large files — parallel parts, resumable on failure.
2. **Pre-signed URLs** to delegate access without exposing credentials — the browser uploads/downloads directly to/from S3.
3. **Pagination** for large buckets — `list_objects_v2` returns at most 1000 keys per call.

---

### Lifecycle policies: cost optimization

```json
{
  "Rules": [
    {
      "ID": "Archive-old-logs",
      "Status": "Enabled",
      "Filter": { "Prefix": "logs/" },
      "Transitions": [
        { "Days": 30, "StorageClass": "STANDARD_IA" },
        { "Days": 90, "StorageClass": "GLACIER" },
        { "Days": 365, "StorageClass": "DEEP_ARCHIVE" }
      ],
      "Expiration": { "Days": 2555 }
    }
  ]
}
```

This rule automatically:
- Moves logs to Standard-IA after 30 days
- Moves them to Glacier after 90 days
- Moves them to Deep Archive after 1 year
- Deletes them after 7 years

Lifecycle policies are how production teams keep S3 costs manageable without manual intervention.

---

### Performance tuning

| Pattern | What it helps |
|---|---|
| **Multipart upload** | Large objects, parallel writes, resumable |
| **Transfer Acceleration** (CloudFront) | Cross-region uploads, ~50–500% faster |
| **S3 Select** | Server-side filtering; reduces data transfer and parsing time |
| **Random key prefixes** | Prevents hot partitions in high-write workloads |
| **VPC endpoints** | Avoids NAT and public internet; lower latency, lower data transfer cost |
| **Request rate monitoring** | Detect hot keys early |
| **CloudFront caching** | For frequently-read content |

---

## Use It

### When to use which S3 feature

| Use case | S3 feature |
|---|---|
| Frequently accessed files | S3 Standard |
| Backups accessed rarely | S3 Standard-IA |
| Compliance archive (7+ years) | S3 Glacier Deep Archive |
| Big data analytics | S3 + Athena, S3 + Redshift Spectrum |
| Static website hosting | S3 + CloudFront |
| User-uploaded files (images, videos) | S3 Standard + pre-signed URLs |
| Disaster recovery | S3 Cross-Region Replication |
| Data lake | S3 + Glue + Athena |
| Lock files (prevent deletion) | S3 Object Lock |
| Mount as filesystem | S3FS (FUSE), Mountpoint for S3 |

### When S3 is the wrong choice

| Situation | Better choice |
|---|---|
| Sub-millisecond reads | ElastiCache (Redis), DynamoDB DAX |
| Relational queries | RDS, Aurora |
| Block storage for EC2 | EBS |
| Long-running filesystem | EFS |
| Need POSIX file semantics | EFS, FSx |
| Cost-critical blob storage with infrequent access | S3 Glacier is fine — make sure you actually need S3 |

---

## Common Pitfalls

- **Treating S3 as a filesystem.** S3 is an object store; it does not have POSIX semantics. Listing operations are slow; partial reads of large objects require byte-range requests; renaming is a copy + delete.

- **Single prefix for millions of objects.** The metadata partition for that prefix becomes a bottleneck. Use randomized prefixes (UUIDs, hashes) for high-cardinality keys.

- **No lifecycle policies.** Without them, data sits in S3 Standard forever at the highest cost. Most data has a useful life; lifecycle policies express it.

- **Public buckets.** Accidentally making a bucket public has caused some of the largest data leaks in history. Default-deny; require explicit grants for public access. Enable Block Public Access at the account level.

- **Skipping encryption.** S3 supports default encryption; turn it on at the bucket level. KMS-encrypted buckets are auditable; SSE-S3 (AES-256) is free and sufficient for most use cases.

- **Not enabling versioning until after a deletion.** Once you delete without versioning, the data is gone. Enable versioning on day one for any bucket with mutable data.

- **Underestimating request costs.** S3 charges per request. Millions of small GETs add up. Use CloudFront or caching for high-request-volume workloads.

- **Cross-region replication not configured.** Without it, an AZ or region failure can lose your data. Enable cross-region replication for critical buckets.

---

## Exercises

1. **Easy** — List the five service tiers in S3's architecture. For each, describe its role in one sentence.

2. **Medium** — Design a bucket structure for a SaaS product that stores: (a) user-uploaded images (frequently accessed), (b) nightly database backups (retained 30 days), (c) audit logs (retained 7 years). For each, specify the storage class, lifecycle policy, versioning setting, and access control.

3. **Hard** — A team writes 1 million small JSON files per day to one S3 prefix. List performance is degrading. Diagnose what is happening and propose a fix. Walk through the change to confirm it works.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| S3 | A file storage service | Amazon's object storage service — 350 trillion objects, eleven nines of durability, built on a microservices architecture |
| Bucket | A folder | A top-level container for objects; globally unique name; defines region, access policy, and configuration |
| Object | A file | A blob of data (up to 5 TB) plus metadata; addressed by bucket + key; immutable |
| Erasure coding | Replication | A redundancy scheme that splits objects into fragments and writes across disks/AZs; cheaper than full replication with comparable durability |
| Eleven nines | A marketing number | 99.999999999% durability — the expected rate of object loss, achieved through continuous auditing and repair |
| Multipart upload | Large file upload | A protocol that splits large uploads into parallel parts; resumable on failure; required for objects > 5 GB |
| Pre-signed URL | A signed link | A time-limited URL that delegates S3 access without exposing credentials; the standard pattern for browser-direct uploads/downloads |
| Lifecycle policy | A backup rule | An automatic rule that transitions objects between storage classes or expires them based on age |
| Storage class | A price tier | A specific durability/availability/cost profile (Standard, IA, Glacier, etc.); pick the cheapest that meets your retrieval needs |

---

## Further Reading

- **"Building and operating a pretty big storage system called S3"** — Andy Warfield's deep technical writeup: https://www.allthingsdistributed.com/2024/03/building-and-operating-a-pretty-big-storage-system-called-s3.html
- **AWS re:Invent 2023 — Dive Deep on Amazon S3** — the official architecture session: https://www.youtube.com/watch?v=BIQvSpgU76k
- **S3 Documentation** — the canonical reference: https://docs.aws.amazon.com/s3/
| **S3 Storage Classes** — the official guide to choosing classes: https://aws.amazon.com/s3/storage-classes/
- **S3 Performance Guidelines** — the official performance optimization guide: https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance-guidelines.html