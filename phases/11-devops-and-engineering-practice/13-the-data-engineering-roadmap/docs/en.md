# The Data Engineering Roadmap

> Ten areas of competence, in order, that turn a developer into a data engineer — the path from Python to production data pipelines.

**Type:** Learn
**Prerequisites:** Basic SQL, programming fundamentals
**Time:** ~20 minutes

---

## The Problem

Data engineering has become one of the highest-leverage disciplines in modern software. Every company has more data than it knows what to do with, and the engineers who can move that data from where it lives to where decisions get made are in short supply.

The problem is figuring out what to learn. "Data engineering" spans databases, streaming, distributed systems, cloud infrastructure, and tooling that changes every year. A focused roadmap that orders the skills by dependency is more useful than a long list of topics.

This lesson walks through ten areas of competence that turn a developer into a data engineer. Each area is sequenced based on what you need to know before the next one makes sense.

---

## The Concept

### The ten areas

```
   1. Programming Languages
   2. Processing Techniques
   3. Databases
   4. Messaging Platforms
   5. Data Lakes & Warehouses
   6. Cloud Computing
   7. Storage Systems
   8. Orchestration Tools
   9. Automation & Deployments
   10. Frontend & Dashboarding
```

The order matters: you cannot query a database before you understand what a database is; you cannot stream data before you understand batch processing; you cannot orchestrate pipelines before you can build them.

---

### 1. Programming Languages

**Why it matters:** every data engineering tool is built on a programming language. You write transformations, custom connectors, and orchestration logic in code.

**Languages to know:**

- **Python** — the default. Most data tools have Python APIs (pandas, PySpark, dbt, Airflow). Learn it well.
- **SQL** — not technically a programming language, but you will write it daily. Window functions, CTEs, joins, aggregations.
- **Java / Scala** — required for Spark, Flink, Kafka (in their native APIs). If you do heavy data engineering, knowing JVM languages helps.
- **Bash / shell scripting** — for cron jobs, glue code, server administration.

**Minimum competence:**

- Python: decorators, generators, async, type hints, packaging
- SQL: complex joins, window functions, CTEs, query optimization, EXPLAIN plans
- Bash: pipes, conditionals, awk/sed basics, file handling

---

### 2. Processing Techniques

**Why it matters:** data has to be transformed. Whether batch or streaming, the transformations are the core of data engineering.

**Batch processing:**

- **Apache Spark** — the dominant batch engine. PySpark is the Python API; Spark SQL for SQL-on-dataframes.
- **Hadoop MapReduce** — the older paradigm; mostly replaced by Spark but still worth knowing.
- **Apache Beam** — unified batch + streaming API; runs on Spark, Flink, or Google Cloud Dataflow.

**Stream processing:**

- **Apache Flink** — the dominant stream engine. Strong exactly-once semantics, low latency.
- **Apache Kafka Streams** — stream processing built into Kafka.
- **Spark Structured Streaming** — Spark's streaming API; easier than Flink, higher latency.

**Minimum competence:**

- Spark: DataFrame API, Spark SQL, partitioning, shuffling, performance tuning
- Flink: windowing, watermarks, exactly-once, stateful processing
- The distinction between batch and streaming; when to use which

---

### 3. Databases

**Why it matters:** data lives somewhere. You need to know how to read, write, optimize, and operate the storage layer.

**Relational:**

- **PostgreSQL** — the modern default for transactional data
- **MySQL** — ubiquitous, especially in legacy systems
- **Cloud-managed** — AWS RDS, Aurora, Azure SQL, Cloud SQL

**NoSQL:**

- **MongoDB** — document store; flexible schemas
- **Cassandra** — wide-column; write-heavy, eventually consistent
- **Redis** — key-value; cache, session, leaderboard

**Search:**

- **Elasticsearch / OpenSearch** — full-text search, log analytics

**Minimum competence:**

- PostgreSQL: schema design, indexes, query optimization, replication
- Redis: caching patterns, pub/sub, streams
- MongoDB or Cassandra: at least one of these, for non-relational workloads

---

### 4. Messaging Platforms

**Why it matters:** data moves between systems via queues and streams. You need to know how to publish, consume, and reason about event flows.

**Platforms:**

- **Apache Kafka** — the dominant streaming platform. Partitioned, replicated, ordered per partition.
- **RabbitMQ** — the dominant traditional message queue. Strong routing, mature.
- **Pulsar** — newer; combines streaming and queuing; gaining traction.
- **AWS Kinesis / SQS / SNS** — cloud-native alternatives.

**Minimum competence:**

- Kafka: producers, consumers, partitions, consumer groups, exactly-once semantics
- The distinction between queues (consume once) and streams (consume repeatedly)
- Ordering guarantees, delivery guarantees, dead-letter queues

---

### 5. Data Lakes and Warehouses

**Why it matters:** data ends up in storage optimized for analytics. The two main approaches — lake and warehouse — have different strengths.

**Data warehouses (structured, schema-on-write):**

- **Snowflake** — cloud-native, separation of storage and compute
- **Google BigQuery** — serverless; scales to petabytes without ops
- **Amazon Redshift** — AWS-native; Postgres-compatible interface
- **Databricks SQL** — built on Spark; tight integration with the Databricks lakehouse

**Data lakes (raw, schema-on-read):**

- **AWS S3 + Iceberg / Delta Lake / Hudi** — open table formats on object storage
- **Apache Iceberg** — the dominant open table format

**Lakehouse:** combines warehouse performance with lake flexibility. The modern direction.

**Key concepts:**

- **OLTP vs OLAP** — transactional vs analytical workloads have different storage needs
- **Normalization vs denormalization** — for OLTP, normalize; for OLAP, denormalize (star schema, snowflake schema)
- **Partitioning and bucketing** — for query performance
- **ACID transactions** — vs eventual consistency

---

### 6. Cloud Computing Platforms

**Why it matters:** most modern data infrastructure runs on one of the big three clouds. Knowing at least one deeply is essential.

**Platforms:**

- **AWS** — broadest catalog; most data services
- **GCP** — strong for data analytics (BigQuery, Dataflow, Dataproc)
- **Azure** — strong for Microsoft shops; Synapse, Data Factory

**Key concepts:**

- **IAM** — identity and access management
- **VPC networking** — private networks in the cloud
- **Object storage** — S3, GCS, Blob Storage
- **Serverless** — Lambda, Cloud Functions, Azure Functions
- **Containers** — ECS, EKS, Cloud Run, AKS
- **Cost optimization** — reserved instances, spot instances, autoscaling

**Minimum competence:**

- One cloud: networking, IAM, storage, compute, data services
- The shared-responsibility model
- Cost-aware architecture decisions

---

### 7. Storage Systems

**Why it matters:** data has to be stored efficiently, durably, and in formats that the processing layer can read.

**Object storage:**

- **AWS S3** — the de facto standard
- **Google Cloud Storage**
- **Azure Data Lake Storage (ADLS)**

**Distributed file systems:**

- **HDFS** — the Hadoop file system; less common now but still relevant
- **GlusterFS / Ceph** — for on-premises distributed storage

**File formats:**

- **Parquet** — columnar; the default for analytics
- **ORC** — columnar; used by Hive and Spark
- **Avro** — row-based with schema; good for streaming
- **JSON / CSV** — universal but inefficient

**When to use which:**

- Parquet for analytics workloads (columnar, compressed, fast scans)
- Avro for streaming workloads (schema evolution, compact)
- JSON for interchange (universal but slow)

---

### 8. Orchestration Tools

**Why it matters:** pipelines have dependencies. Job B depends on job A. Orchestration tools schedule, sequence, retry, and monitor these workflows.

**Tools:**

- **Apache Airflow** — the dominant Python-based orchestrator. DAGs as code.
- **Prefect** — modern alternative; better defaults, cloud-friendly
- **Dagster** — asset-centric; treats data assets as first-class
- **AWS Step Functions** — managed; for AWS-native workflows
- **Google Cloud Composer** — managed Airflow on GCP

**Minimum competence:**

- Airflow: DAGs, operators, sensors, scheduling, retries, alerts
- The distinction between scheduling (when) and orchestration (dependencies)
- Idempotent tasks, backfills, catch-up runs

---

### 9. Automation and Deployments

**Why it matters:** data pipelines are code. They need version control, CI/CD, testing, and observability.

**Tools:**

- **Git** — version control
- **GitHub Actions / GitLab CI / CircleCI** — CI/CD pipelines
- **Terraform / Pulumi** — infrastructure as code
- **dbt (data build tool)** — version-controlled SQL transformations with testing
- **Great Expectations / Soda** — data quality testing

**Minimum competence:**

- Git: branching, PRs, rebasing, conflict resolution
- CI/CD: pipeline structure, secrets management, deployment strategies
- IaC: declarative infrastructure definitions
- dbt: models, tests, snapshots, exposures

---

### 10. Frontend and Dashboarding

**Why it matters:** data engineers do not build dashboards, but they collaborate with people who do. Knowing the tooling helps the conversation.

**Tools:**

- **Tableau** — the standard for business dashboards
- **Looker** — LookML-based, owned by Google
- **Power BI** — Microsoft's answer
- **Metabase** — open-source, simple, popular with smaller teams
- **Superset** — open-source, Apache project

**Notebooks (for exploration):**

- **Jupyter** — the standard for data exploration
- **Databricks Notebooks** — collaborative notebooks in the lakehouse
- **Hex / Observable** — modern notebook alternatives

**Minimum competence:**

- Read a Tableau / Looker dashboard and explain what it shows
- Build a basic notebook that queries a warehouse and visualizes results
- Understand the boundary between data engineering (the data) and BI (the dashboards)

---

## Build It / In Depth

### A focused 6-month learning plan

```
   Month 1: Programming + SQL
     - Python fluency (intermediate)
     - SQL mastery (window functions, CTEs, optimization)

   Month 2: Databases
     - PostgreSQL deep dive (schema, indexes, EXPLAIN)
     - One NoSQL store (Redis or MongoDB)

   Month 3: Batch processing
     - PySpark basics
     - Build a batch pipeline that ingests, transforms, loads

   Month 4: Streaming
     - Kafka basics
     - Build a streaming pipeline with windowed aggregations

   Month 5: Cloud + Storage
     - AWS or GCP core services
     - S3, Glue / Dataflow, basic data warehouse

   Month 6: Orchestration + production
     - Airflow basics
     - dbt for transformations
     - Deploy a real pipeline to production
```

After six months, you can build and operate a real data pipeline. The next six months are about depth (Spark performance tuning, Kafka operations, advanced SQL) and breadth (the remaining areas).

---

### The data engineer's day

A typical day might look like:

```
   09:00  Standup with the analytics team
   09:30  Debug a failed dbt model from yesterday's run
   10:00  Write a new Airflow DAG for a daily report
   12:00  Lunch
   13:00  Optimize a slow Spark job (EXPLAIN, repartitioning)
   15:00  Pair with an analyst on a new metric definition
   16:00  Review an infra PR for Terraform changes
   17:00  Write a Great Expectations check for a new data source
```

Data engineering is software engineering applied to data. The skills are general — debugging, code review, testing, deployment — applied to a specific domain.

---

### The data engineering stack, end to end

```
   Sources:    app DBs, events (Kafka), files (S3), APIs

   Ingestion:  Kafka Connect, Airbyte, custom Python

   Storage:    S3 (raw), Iceberg / Delta (curated), warehouse (modeled)

   Processing: Spark (batch), Flink (stream), dbt (SQL transforms)

   Orchestration: Airflow, Prefect, Dagster

   Quality:    Great Expectations, Soda, Monte Carlo

   Serving:    warehouse (analysts), feature store (ML), reverse ETL (apps)

   Observability: Datadog, Grafana, Monte Carlo, Bigeye
```

Every data engineering role touches a subset of this. Knowing the full map helps you see where your work fits.

---

## Use It

### When to use which tool

| Need | Use |
|---|---|
| SQL transformations on warehouse data | dbt |
| Batch processing at scale | Spark (PySpark or Scala) |
| Stream processing with low latency | Flink or Kafka Streams |
| Workflow orchestration | Airflow (or Prefect / Dagster) |
| Message queue | RabbitMQ (traditional) or Kafka (streaming) |
| OLTP database | PostgreSQL |
| OLAP database | Snowflake, BigQuery, Redshift |
| Document storage | MongoDB |
| Search | Elasticsearch / OpenSearch |
| Cloud data warehouse | Snowflake / BigQuery / Redshift |
| Notebook for exploration | Jupyter or Databricks |
| Data quality | Great Expectations, Soda |
| Reverse ETL | Hightouch, Census |

---

### Common pitfalls

- **Trying to learn everything at once.** Data engineering is too broad. Pick one stack (e.g., AWS + Snowflake + Airflow + dbt) and go deep before exploring alternatives.

- **Confusing data engineering with data science.** Data engineers build pipelines; data scientists analyze data. The skills overlap but are distinct.

- **Ignoring data quality.** A pipeline that produces wrong data is worse than no pipeline. Build quality checks from day one.

- **Building batch pipelines that should be streaming.** Some problems need real-time; most do not. Default to batch; reach for streaming when there is a concrete need.

- **Treating the warehouse as a database.** Warehouses are optimized for analytical queries, not for high-frequency point lookups. Different tools for different jobs.

- **No idempotency.** A pipeline that runs twice produces duplicate data. Make every step idempotent (use MERGE, not INSERT).

---

## Exercises

1. **Easy** — Pick three of the ten areas. For each, describe one concrete skill and one tool that teaches it.

2. **Medium** — Design the data architecture for a small e-commerce company (1B events/year, ~50GB of data). Specify each layer, the tools, and the cost.

3. **Hard** — A team has a fragile, undocumented pipeline that processes 5TB/day. Rewrite it as a new architecture with proper orchestration, quality checks, and observability. Specify the phased migration plan.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Data engineer | A data person | A software engineer who builds and operates data pipelines, warehouses, and infrastructure |
| ETL | Extract Transform Load | A pattern for moving data from sources to a destination with transformation; the historical default |
| ELT | Extract Load Transform | A modern pattern: load raw data first, transform in the warehouse using dbt; takes advantage of warehouse compute |
| Lakehouse | Lake + warehouse | An architecture combining the flexibility of a data lake with the performance of a warehouse (Iceberg, Delta) |
| dbt | A SQL tool | Data build tool — version-controlled SQL transformations with testing, lineage, and documentation |
| DAG | A graph | Directed Acyclic Graph — the structure of a workflow; nodes are tasks, edges are dependencies |
| OLTP vs OLAP | Two databases | Online Transaction Processing (high-frequency small queries) vs Online Analytical Processing (low-frequency large aggregations) |
| Idempotency | The same | The property that an operation produces the same result whether applied once or many times; essential for reliable pipelines |

---

## Further Reading

- **"Fundamentals of Data Engineering"** — Joe Reis and Matt Housley; the canonical book on the discipline: https://www.oreilly.com/library/view/fundamentals-of-data/9781098108298/
- **"Designing Data-Intensive Applications"** — Martin Kleppmann; the foundations every data engineer should know: https://dataintensive.net/
- **Apache Spark Documentation** — the standard batch processing engine: https://spark.apache.org/docs/latest/
- **dbt Documentation** — the standard SQL transformation tool: https://docs.getdbt.com/
- **Apache Airflow Documentation** — the standard orchestrator: https://airflow.apache.org/docs/
- **"Data Engineering Zoomcamp"** — a free, structured course: https://github.com/DataTalksClub/data-engineering-zoomcamp