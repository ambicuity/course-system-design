# Big Data Pipeline Cheatsheet for AWS, Azure, and Google Cloud

> Every cloud vendor calls the same five-stage pipeline by different names — memorize the pattern once, then map the branding.

**Type:** Learn
**Prerequisites:** Data Warehousing Fundamentals, Stream vs. Batch Processing, Cloud Storage Concepts
**Time:** ~25 minutes

---

## The Problem

You are building a data platform that must ingest millions of events per second from IoT sensors, mobile apps, and third-party APIs. The raw data lands in an unstructured lake, gets cleaned by a distributed compute cluster, and eventually ends up in a warehouse where analysts can query it with SQL and visualize it in a BI dashboard. Every cloud provider offers managed services for each of these five stages — but they use completely different names, pricing models, and integration patterns.

Without a mental map of how the stages align across AWS, Azure, and GCP, onboarding onto a new cloud feels like learning a foreign language from scratch. Worse, many teams bolt services together incorrectly: using a batch layer where a streaming layer belongs, landing raw data directly in the warehouse (expensive and slow), or building a visualization tier that bypasses the semantic layer entirely.

The goal of this lesson is to give you a durable mental model — stage by stage — so you can design a correct big data pipeline on any cloud and translate fluently between all three when you're reading architecture diagrams, job postings, or vendor documentation.

---

## The Concept

### The Five-Stage Pipeline Model

All production big data platforms share the same logical stages:

```
Sources          Ingestion             Data Lake          Compute             Warehouse         Presentation
────────────   ──────────────────   ───────────────   ───────────────   ─────────────────   ──────────────
IoT devices  → [ streaming / batch  → raw object store → ETL / ELT job  → columnar SQL DB  → BI dashboard ]
Web events       connector                              (Spark, Flink)    (MPP engine)        (Looker, PBI)
RDBMS CDC        queue ]
```

**Ingestion** is the entry point. It either streams data in real time (sub-second latency) or pulls it in bulk on a schedule. The ingestion tier decouples producers from consumers and absorbs traffic spikes.

**Data Lake** stores raw, unprocessed data in its native format (JSON, Parquet, Avro, CSV) on cheap object storage. Schema is not enforced here — that is intentional. You preserve the original signal so you can re-process it as requirements evolve.

**Compute** is where transformation happens. You run Spark, Hive, Flink, or a serverless engine to clean, join, aggregate, and enrich data. Output is usually written back to the lake in a curated zone or directly to the warehouse.

**Data Warehouse** is a massively parallel processing (MPP) SQL engine optimized for analytical queries over large, structured datasets. It is expensive per byte stored, so only curated, modeled data lives here.

**Presentation** is the BI and visualization layer. Analysts, product managers, and executives run dashboards and ad-hoc queries here. This tier should be read-only against the warehouse; it never touches the lake.

### Service Mapping Across Clouds

| Stage | AWS | Azure | Google Cloud |
|---|---|---|---|
| **Ingestion (streaming)** | Kinesis Data Streams | Event Hubs | Pub/Sub |
| **Ingestion (batch / CDC)** | AWS Glue (crawlers), DMS | Azure Data Factory | Datastream, Cloud Data Fusion |
| **Managed Kafka** | Amazon MSK | Event Hubs (Kafka protocol) | Confluent on GCP / Pub/Sub Lite |
| **Data Lake storage** | S3 | Azure Data Lake Storage Gen2 (ADLS) | Cloud Storage (GCS) |
| **Compute (batch Spark)** | EMR | Azure Databricks / HDInsight | Dataproc |
| **Compute (serverless ETL)** | AWS Glue (jobs) | Azure Data Factory pipelines | Dataflow (Apache Beam) |
| **Compute (stream)** | Kinesis Data Analytics (Flink) | Azure Stream Analytics | Dataflow (streaming) |
| **Data Warehouse** | Redshift | Azure Synapse Analytics | BigQuery |
| **Data Catalog / Governance** | AWS Glue Data Catalog, Lake Formation | Microsoft Purview | Dataplex, Data Catalog |
| **Presentation / BI** | Amazon QuickSight | Power BI | Looker Studio (fka Data Studio) |
| **Orchestration** | MWAA (Managed Airflow), Step Functions | Azure Data Factory (pipeline), Synapse Pipelines | Cloud Composer (Managed Airflow) |

### How the Pieces Connect (AWS Example End-to-End)

```
[ Kinesis Data Streams ]
        |
        v
  [ S3 raw bucket ]   <── also Kinesis Firehose dumps here
        |
        v
  [ AWS Glue ETL job ]  (PySpark, reads raw Parquet, writes clean Parquet)
        |
        v
  [ S3 curated bucket ]
        |
        v
  [ Redshift COPY command ]  or Redshift Spectrum queries S3 directly
        |
        v
  [ QuickSight dashboard ]
```

### Schema-on-Read vs. Schema-on-Write

The lake uses **schema-on-read**: data is stored without enforcement, and the schema is applied at query time. The warehouse uses **schema-on-write**: data is validated and typed before insertion.

This distinction matters for design decisions:

| Concern | Data Lake | Data Warehouse |
|---|---|---|
| Schema changes | No migration needed; re-read with new schema | Requires ALTER TABLE or reload |
| Cost per TB/month | ~$0.02 (S3/GCS/ADLS) | ~$25 (Redshift) or per-query (BigQuery) |
| Query latency | Minutes (Spark) | Seconds (MPP SQL) |
| Who queries it | Data engineers, ML engineers | Analysts, BI tools |
| File formats | JSON, Parquet, Avro, ORC | Proprietary internal columnar (Redshift, Synapse) |

---

## Build It / In Depth

### Designing a GCP Pipeline Step-by-Step

This walkthrough uses GCP because BigQuery's serverless model illustrates the trade-offs most clearly.

**Step 1 — Ingest with Pub/Sub**

Producers publish JSON messages to a Pub/Sub topic. You set a message retention window (7 days default) so downstream consumers can replay.

```bash
# Create a topic and subscription
gcloud pubsub topics create clickstream
gcloud pubsub subscriptions create clickstream-sub \
  --topic=clickstream \
  --ack-deadline=60
```

**Step 2 — Land in Cloud Storage (Data Lake)**

A Pub/Sub push subscription triggers a Dataflow job, or you use Pub/Sub to GCS Dataflow template. Raw JSON lands in `gs://my-lake/raw/clickstream/YYYY/MM/DD/`.

```bash
gcloud dataflow jobs run clickstream-to-gcs \
  --gcs-location gs://dataflow-templates/latest/Cloud_PubSub_to_GCS_Text \
  --parameters \
    inputTopic=projects/my-project/topics/clickstream,\
    outputDirectory=gs://my-lake/raw/clickstream/,\
    outputFilenamePrefix=events-,\
    outputFilenameSuffix=.json
```

**Step 3 — Transform with Dataflow (Apache Beam)**

A Python Beam pipeline reads raw JSON, applies parsing and enrichment, and writes Parquet to the curated zone.

```python
import apache_beam as beam
from apache_beam.io.gcp.gcsio import GcsIO

def parse_event(raw: str):
    import json
    record = json.loads(raw)
    return {
        "user_id": record["uid"],
        "event_type": record["evt"],
        "ts": record["ts"],
        "country": record.get("geo", {}).get("country", "UNKNOWN"),
    }

with beam.Pipeline() as p:
    (
        p
        | "ReadRaw" >> beam.io.ReadFromText("gs://my-lake/raw/clickstream/*")
        | "Parse" >> beam.Map(parse_event)
        | "WriteParquet" >> beam.io.WriteToParquet(
            "gs://my-lake/curated/clickstream/",
            schema=...,  # pyarrow schema
        )
    )
```

**Step 4 — Load into BigQuery**

```sql
-- External table queries GCS directly (no load needed, schema-on-read)
CREATE OR REPLACE EXTERNAL TABLE analytics.clickstream_external
OPTIONS (
  format = 'PARQUET',
  uris = ['gs://my-lake/curated/clickstream/*.parquet']
);

-- Or load for faster interactive queries
LOAD DATA INTO analytics.clickstream
FROM FILES (
  format = 'PARQUET',
  uris = ['gs://my-lake/curated/clickstream/*.parquet']
);
```

**Step 5 — Visualize in Looker Studio**

Connect Looker Studio to the BigQuery dataset via the native connector. Build dashboards on top of `analytics.clickstream`. Schedule daily email delivery.

### Equivalent AWS and Azure Commands

**AWS — Kinesis → S3 → Glue → Redshift**

```bash
# Create a Kinesis stream (4 shards = ~4 MB/s ingest)
aws kinesis create-stream --stream-name clickstream --shard-count 4

# Kinesis Firehose delivers to S3 automatically
aws firehose create-delivery-stream \
  --delivery-stream-name clickstream-to-s3 \
  --s3-destination-configuration \
    RoleARN=arn:aws:iam::123:role/firehose-role,\
    BucketARN=arn:aws:s3:::my-lake,\
    Prefix=raw/clickstream/

# Redshift COPY from S3
COPY analytics.clickstream
FROM 's3://my-lake/curated/clickstream/'
IAM_ROLE 'arn:aws:iam::123:role/redshift-role'
FORMAT AS PARQUET;
```

**Azure — Event Hubs → ADLS Gen2 → Databricks → Synapse**

```python
# Databricks PySpark reading from ADLS Gen2
df = spark.read.json(
    "abfss://raw@mylake.dfs.core.windows.net/clickstream/"
)
clean = df.selectExpr("uid as user_id", "evt as event_type", "ts", "geo.country")
clean.write.mode("overwrite").parquet(
    "abfss://curated@mylake.dfs.core.windows.net/clickstream/"
)
```

---

## Use It

### When to Use Which Cloud Service

| You need | AWS | Azure | GCP |
|---|---|---|---|
| Sub-second streaming at millions of events/s | Kinesis Data Streams | Event Hubs | Pub/Sub |
| Kafka API compatibility | Amazon MSK | Event Hubs (Kafka wire protocol) | Confluent Cloud |
| Fully managed Spark | EMR Serverless | Azure Databricks | Dataproc Serverless |
| Serverless ETL without Spark expertise | AWS Glue | Azure Data Factory | Dataflow (Beam templates) |
| Pay-per-query warehouse (no cluster to size) | Redshift Serverless | Synapse Serverless SQL | BigQuery (default) |
| ML feature engineering at scale | SageMaker Feature Store | Azure ML + Synapse | Vertex AI Feature Store + BigQuery ML |
| Data mesh / domain-oriented ownership | AWS Lake Formation | Microsoft Purview | Dataplex |

### BigQuery vs. Redshift vs. Synapse — Key Differences

| Dimension | BigQuery | Redshift | Synapse Analytics |
|---|---|---|---|
| Architecture | Serverless, storage/compute separated | Provisioned nodes (RA3 = separated) | Hybrid provisioned + serverless |
| Pricing model | Per query ($5/TB scanned) or flat-rate slots | Per node-hour + storage | Per DWU-hour or per query |
| Partition / clustering | Partition on date + cluster on 4 cols | Sort key + distribution key | Distribution + clustered index |
| Zero-ETL | BigQuery Data Transfer Service | Zero-ETL from Aurora/RDS (preview) | Synapse Link from Cosmos DB |
| Peak strength | SQL at petabyte scale, no ops | Tight AWS ecosystem integration | Microsoft BI stack integration |

---

## Common Pitfalls

- **Landing raw data directly in the warehouse.** Ingesting JSON blobs into Redshift or BigQuery without a lake layer means you lose replay ability and pay warehouse pricing for raw storage. Always write to object storage first.

- **Using a single Kinesis/Pub/Sub subscription for all consumers.** Multiple independent consumers (ETL job, audit logger, real-time dashboard) must each have their own subscription or consumer group. Sharing a single subscription causes each consumer to see only a fraction of messages.

- **Skipping the curated zone.** Teams that write directly from compute to the warehouse couple transformation failures to warehouse availability. A curated Parquet zone on S3/GCS/ADLS acts as a checkpoint — you can reload the warehouse from it without re-running the full pipeline.

- **Not setting data retention on streaming queues.** Kinesis defaults to 24 hours, Pub/Sub to 7 days. If your ETL falls behind by more than the retention window, messages are lost permanently. Set retention to at least 7 days and add a dead-letter topic.

- **Treating BigQuery partition expiration as a backup strategy.** Partition expiration deletes data silently after the configured period. Teams discover this only when a dashboard shows a gap months later. Use separate long-term storage buckets for archival and keep warehouse partitions for query performance only.

---

## Exercises

1. **Easy** — Draw the five-stage pipeline for a simple e-commerce order tracking system. For each stage, write down which AWS service you would use and why.

2. **Medium** — You have a GCP pipeline where Dataflow jobs are reading from Pub/Sub and writing to GCS. The pipeline falls behind by 6 hours during a traffic spike. Identify three knobs you can tune to increase throughput, and explain the trade-off each introduces.

3. **Hard** — Design a multi-cloud data platform where the data lake lives on GCS but analysts on three different teams use Redshift, Synapse, and BigQuery as their query engines. Describe the format strategy, access control model, and how you would handle schema evolution without breaking any of the three query engines.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Data Lake | A messy dump of random files | Intentional raw storage of all source data in native format, with a governed folder structure and metadata catalog |
| Data Warehouse | A database for big data | An MPP SQL engine optimized for analytical workloads on structured, modeled data with schema-on-write enforcement |
| Kinesis Firehose | A streaming database | A managed delivery service that buffers and batches streaming data then writes it to S3, Redshift, or HTTP endpoints — it does not provide replay |
| Pub/Sub | A message queue | A fully managed publish-subscribe messaging system with at-least-once delivery; it is not a queue (no FIFO) and consumers must handle deduplication |
| EMR vs. Glue | Both run Spark, so they're the same | EMR gives you full control over the Spark cluster (version, config, spot instances); Glue abstracts the cluster with a serverless job model but costs more per DPU and is harder to tune |
| BigQuery slot | A unit of storage | A unit of compute (virtual CPU) used for query execution; you reserve slots for flat-rate pricing or use on-demand pricing where slots are allocated automatically |
| Lakehouse | A data lake with SQL queries on top | An architectural pattern (Delta Lake, Iceberg, Hudi) where ACID transactions, schema enforcement, and time travel are added to object-store files, blurring the line between lake and warehouse |

---

## Further Reading

- [AWS Big Data Analytics Options on AWS (Whitepaper)](https://docs.aws.amazon.com/whitepapers/latest/big-data-analytics-options/welcome.html) — authoritative AWS reference for choosing between Kinesis, EMR, Glue, Redshift, and Athena.
- [Google Cloud Data Analytics Products Overview](https://cloud.google.com/products/data-analytics) — official GCP product page mapping the full pipeline from Pub/Sub through BigQuery and Looker.
- [Azure Analytics Architecture Guide](https://learn.microsoft.com/en-us/azure/architecture/solution-ideas/articles/analytics-start-here) — Microsoft's decision guide for Event Hubs, Synapse, Databricks, and Power BI.
- [The Data Engineering Cookbook (Andreas Kretz)](https://github.com/andkret/Cookbook) — widely cited open-source reference covering pipeline patterns across all major clouds with practical examples.
- [Apache Iceberg: The Definitive Guide (O'Reilly)](https://iceberg.apache.org/docs/latest/) — essential reading for anyone building a lakehouse on top of S3, GCS, or ADLS, now supported natively by Redshift, BigQuery, and Synapse.
