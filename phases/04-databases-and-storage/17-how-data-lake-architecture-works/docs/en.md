# How Data Lake Architecture Works?

> Store everything now, ask questions later — but only if you build it right.

**Type:** Learn
**Prerequisites:** Relational Databases vs. NoSQL, Data Warehousing Fundamentals, Object Storage at Scale
**Time:** ~30 minutes

---

## The Problem

A mid-size e-commerce company runs a standard OLAP data warehouse. Every table has a rigid schema agreed upon months in advance. When the data team wants to train a recommendation model using raw clickstream logs, they discover the logs were never ingested — the schema wasn't defined, so the ETL pipeline dropped them. By the time anyone notices, two years of behavioral data is gone.

This is the core failure mode of schema-on-write architectures: you must know every question you'll ever ask before you store the data. In practice, the most valuable data analysis happens reactively — a fraud team wants raw transaction payloads from three years ago, a data scientist needs unstructured customer-support emails, an IoT team needs sensor time-series that the warehouse couldn't represent efficiently. A rigid warehouse can't serve all of these simultaneously.

Beyond flexibility, scale is a forcing function. When you're ingesting 50 TB per day across video files, JSON event streams, database CDC feeds, and PDF receipts, replicating all of it into a columnar warehouse first is prohibitively expensive. You need cheap, durable, decoupled storage as the source of truth, with computation that runs on demand — not a monolithic system that must pre-process everything before anything can be queried. The data lake is the answer to both problems.

---

## The Concept

A **data lake** is a centralized, schema-agnostic repository that stores data in its raw or near-raw form, at any scale, in any format. The defining principle is **schema-on-read**: structure is applied when the data is read, not when it is written. This inverts the warehouse model.

### The Medallion Architecture (Bronze → Silver → Gold)

The most widely adopted structural pattern inside a data lake is the **medallion architecture**, which organizes data into three progressive zones of quality.

```
  ┌──────────────────────────────────────────────────────────────────────┐
  │                         DATA LAKE                                    │
  │                                                                      │
  │  ┌────────────────┐    ┌────────────────┐    ┌───────────────────┐  │
  │  │   BRONZE       │    │   SILVER       │    │   GOLD            │  │
  │  │  (Raw Zone)    │───▶│ (Curated Zone) │───▶│ (Serving Zone)    │  │
  │  │                │    │                │    │                   │  │
  │  │ • Exact copy   │    │ • Cleaned      │    │ • Aggregated      │  │
  │  │   of source    │    │ • Deduplicated │    │ • Business-ready  │  │
  │  │ • Immutable    │    │ • Validated    │    │ • Optimized for   │  │
  │  │ • Append-only  │    │ • Conformed    │    │   specific use    │  │
  │  │ • All formats  │    │   types        │    │   cases           │  │
  │  └────────────────┘    └────────────────┘    └───────────────────┘  │
  │                                                                      │
  └──────────────────────────────────────────────────────────────────────┘
```

**Bronze** is the landing zone. Data arrives exactly as the source system produced it — no transformation, no filtering. A database CDC event is stored as-is. A Kafka message is stored as raw JSON. This immutability gives you a full audit trail and the ability to reprocess if a downstream bug corrupts Silver data.

**Silver** applies cleaning, type coercion, deduplication, and conforming transformations. A date field stored as `"2024/01/15"` in one source and `"15-Jan-2024"` in another is normalized to ISO 8601. Null values are handled. Duplicates from CDC re-delivery are removed. The Silver layer is still generic — it doesn't assume a specific downstream consumer.

**Gold** produces denormalized, aggregated, use-case-specific datasets. One Gold table might be "daily active users per product category, last 90 days" optimized for a dashboard. Another might be a flattened feature table for a machine learning model. Gold data is expensive to compute but cheap to query.

### Ingestion Patterns

Data enters the lake through two primary patterns:

| Pattern | When to use | Latency | Tools |
|---|---|---|---|
| **Batch / scheduled** | Historical loads, nightly syncs, large file imports | Minutes to hours | Apache Sqoop, AWS Glue, Azure Data Factory |
| **Real-time streaming** | Event streams, CDC, IoT sensors, clickstreams | Milliseconds to seconds | Apache Kafka, AWS Kinesis, Apache Flink |
| **Micro-batch** | Near-real-time when true streaming is too complex | Seconds to minutes | Spark Structured Streaming, Databricks Auto Loader |

Most production lakes use both: streaming for operational freshness, batch for historical backfill and bulk migrations.

### The Role of the Data Catalog

Without a catalog, a data lake becomes a **data swamp** — storage full of files nobody can find or trust. A data catalog provides:

- **Schema discovery**: What columns does this Parquet file actually have?
- **Lineage**: Where did this Gold table come from? Which Bronze files feed it?
- **Ownership**: Who is responsible for this dataset?
- **Statistics**: Row counts, null rates, last-updated timestamps.

The catalog decouples storage from compute. Any query engine (Athena, Spark, Trino, Flink) can read the same physical files by consulting the catalog for schema information.

### How Schema-on-Read Actually Works

When Spark or Athena queries a Parquet file in S3, the execution looks like this:

```
Query Engine                    Catalog                    Object Store
     │                             │                            │
     │──── "What schema does ─────▶│                            │
     │      orders/2024/ have?"    │                            │
     │                             │──── Returns column ───────▶│
     │                             │     definitions,           │
     │◀─── column names,           │     partition info         │
     │     types, partitions ──────│                            │
     │                             │                            │
     │──── Predicate pushdown ─────│────────────────────────────▶
     │     "only files where       │                 (S3 returns
     │      date=2024-01"          │                  matching files)
     │                             │                            │
     │◀─────────── Data (Parquet bytes) ──────────────────────────
     │                                                          │
     │  [Engine applies schema projection and type casting]
```

The file format (Parquet, ORC, Avro) embeds some schema metadata, but the catalog is the authoritative registry. This is what allows multiple query engines to coexist on the same storage.

### Partitioning: The Performance Multiplier

Raw files stored without partitioning force full scans. At petabyte scale, a query for "all orders from January 2024" would scan every file ever written. Partitioning physically organizes files into a directory hierarchy:

```
s3://datalake/silver/orders/
  year=2024/
    month=01/
      day=01/
        part-00000.parquet
        part-00001.parquet
      day=02/
        ...
    month=02/
      ...
```

Query engines push the date filter down to the file-system layer, skipping irrelevant partitions entirely. Choosing partition keys well (high cardinality but not too high, matching common query patterns) is one of the highest-leverage tuning decisions in a data lake.

---

## Build It / In Depth

Let's trace a concrete scenario: an e-commerce company ingests order events and makes them queryable.

### Step 1 — Streaming Ingestion to Bronze

Order events flow from the application through Kafka. A Spark Structured Streaming job writes them to S3 in Parquet format, partitioned by event date.

```python
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, to_date, from_json
from pyspark.sql.types import StructType, StringType, DoubleType, TimestampType

spark = SparkSession.builder.appName("orders-bronze").getOrCreate()

schema = StructType() \
    .add("order_id", StringType()) \
    .add("user_id", StringType()) \
    .add("amount", DoubleType()) \
    .add("currency", StringType()) \
    .add("event_time", TimestampType())

# Read from Kafka
raw_stream = (
    spark.readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "kafka:9092")
    .option("subscribe", "order-events")
    .load()
    .select(from_json(col("value").cast("string"), schema).alias("data"))
    .select("data.*")
)

# Write to Bronze — append-only, partitioned by date
(
    raw_stream.writeStream
    .format("delta")                          # Delta Lake for ACID + time travel
    .outputMode("append")
    .option("checkpointLocation", "s3://lake/checkpoints/orders-bronze/")
    .partitionBy(to_date(col("event_time")).alias("event_date"))
    .start("s3://lake/bronze/orders/")
)
```

The Bronze write is append-only and immutable. If this job crashes and replays, duplicate events are handled in Silver.

### Step 2 — Batch Transformation to Silver

A daily Spark job reads Bronze, deduplicates using `order_id`, normalizes currency to USD, and writes to Silver as a Delta table.

```python
from pyspark.sql.functions import row_number, desc
from pyspark.sql.window import Window
from delta.tables import DeltaTable

bronze = spark.read.format("delta").load("s3://lake/bronze/orders/")

# Deduplicate: keep the latest record per order_id
window = Window.partitionBy("order_id").orderBy(desc("event_time"))

silver_df = (
    bronze
    .withColumn("rn", row_number().over(window))
    .filter(col("rn") == 1)
    .drop("rn")
    .filter(col("amount").isNotNull())
    .filter(col("amount") > 0)
)

# Merge into Silver (upsert to handle re-runs idempotently)
DeltaTable.forPath(spark, "s3://lake/silver/orders/") \
    .alias("target") \
    .merge(silver_df.alias("source"), "target.order_id = source.order_id") \
    .whenMatchedUpdateAll() \
    .whenNotMatchedInsertAll() \
    .execute()
```

### Step 3 — Gold Aggregation

The analytics team wants daily revenue by country. A Gold job materializes this:

```sql
-- Runs on Trino/Athena, writes result back to S3 as Gold table
CREATE TABLE gold.daily_revenue_by_country
WITH (
    format = 'PARQUET',
    partitioned_by = ARRAY['report_date'],
    location = 's3://lake/gold/daily_revenue_by_country/'
)
AS
SELECT
    DATE(event_time)     AS report_date,
    user_country         AS country,
    COUNT(*)             AS order_count,
    SUM(amount_usd)      AS revenue_usd
FROM silver.orders
JOIN silver.users USING (user_id)
GROUP BY 1, 2;
```

The BI tool connects directly to this Gold table. Query time drops from minutes (scanning Silver) to sub-second (reading a pre-aggregated, partitioned Parquet dataset).

### Full Architecture Flow

```
  Data Sources
  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌──────────┐
  │  RDBMS  │ │  Kafka  │ │   APIs   │ │   Blobs  │
  │ (orders)│ │(events) │ │(webhooks)│ │(PDF/img) │
  └────┬────┘ └────┬────┘ └────┬─────┘ └────┬─────┘
       │           │           │             │
       ▼           ▼           ▼             ▼
  ┌──────────────────────────────────────────────┐
  │           INGESTION LAYER                    │
  │   Debezium CDC │ Spark Streaming │ Airflow   │
  └───────────────────────┬──────────────────────┘
                          │
                          ▼
  ┌──────────────────────────────────────────────┐
  │        OBJECT STORAGE (S3 / ADLS / GCS)      │
  │  bronze/   silver/   gold/   checkpoints/    │
  └───────────────────────┬──────────────────────┘
                          │
             ┌────────────┴────────────┐
             ▼                         ▼
  ┌─────────────────┐       ┌───────────────────┐
  │   DATA CATALOG  │       │  PROCESSING ENGINE │
  │ (Glue / Hive /  │◀─────▶│ (Spark / Flink /  │
  │  Unity Catalog) │       │  dbt / Trino)     │
  └─────────────────┘       └─────────┬─────────┘
                                      │
                                      ▼
  ┌──────────────────────────────────────────────┐
  │              CONSUMPTION LAYER               │
  │  Dashboards │ ML Models │ Ad-hoc SQL │ APIs  │
  └──────────────────────────────────────────────┘
```

---

## Use It

### Cloud-Native Data Lake Stacks

| Platform | Storage | Catalog | Query Engine | Best For |
|---|---|---|---|---|
| **AWS** | S3 | Glue Data Catalog | Athena, EMR | Teams already on AWS; pay-per-query analytics |
| **Azure** | ADLS Gen2 | Purview / Hive Metastore | Synapse Analytics | Enterprises with existing Azure investments |
| **GCP** | GCS | Dataplex | BigQuery, Dataproc | BigQuery-centric orgs; strong ML pipelines |
| **Databricks** | S3/ADLS/GCS | Unity Catalog | Spark / SQL Warehouse | Unified lakehouse; Delta Lake ecosystem |
| **Snowflake** | Internal (S3-backed) | Native | Snowflake SQL | SQL-first teams; semi-structured JSON querying |

### When to Choose a Data Lake Over a Data Warehouse

Reach for a data lake when:
- Data volume exceeds what a warehouse can economically store (~100 TB+).
- You need to retain raw, unstructured data (images, PDFs, audio).
- Multiple teams will process the same data differently (ML vs. BI vs. audit).
- You can't define the schema up front — data science experimentation needs flexibility.
- Cost is a constraint — object storage is 10–100x cheaper than warehouse storage per GB.

Keep or use a warehouse when:
- The schema is stable and well-understood.
- End users are primarily SQL analysts who need subsecond interactive queries.
- You need strong transactional consistency and fine-grained access control on every column.

Many modern systems run a **lakehouse** pattern: Delta Lake, Apache Iceberg, or Apache Hudi add ACID transactions, schema evolution, and time travel on top of object storage, giving you warehouse-like features without leaving the lake.

### Open Table Formats Comparison

| Format | Key Strength | Ecosystem Fit |
|---|---|---|
| **Delta Lake** | Deep Databricks integration; Z-ordering | Spark-heavy shops |
| **Apache Iceberg** | Best multi-engine support; hidden partitioning | Multi-engine (Spark + Flink + Trino + Athena) |
| **Apache Hudi** | Optimized for high-frequency upserts; CDC | Streaming + upsert-heavy workloads |

---

## Common Pitfalls

- **The Data Swamp**: Dumping data into object storage without a catalog, naming conventions, or ownership records. Files become undiscoverable within months. Mitigation: enforce a catalog-first contract — no dataset is "in the lake" until it has a catalog entry with owner, schema, and update frequency.

- **Missing Partitioning or Wrong Partition Keys**: Querying a 500 TB dataset with no partition pruning burns money and patience. Partitioning on a column with extremely high cardinality (e.g., `user_id`) creates millions of tiny files, killing list operation performance. Mitigation: partition by time (day or month) as the primary key; add secondary partitions only if queries consistently filter on them.

- **No Schema Evolution Strategy**: As upstream systems change, Bronze files start diverging in schema. Adding a column is safe in Parquet; removing or renaming one silently breaks downstream reads. Mitigation: adopt Delta Lake or Iceberg, which track schema evolution history and support explicit schema migration operations.

- **Treating Bronze as Queryable**: Analysts connect BI tools directly to raw Bronze data, bypassing cleaning. They build dashboards on duplicated, null-riddled data. Months later, a metrics audit reveals the numbers were wrong the whole time. Mitigation: enforce zone access controls — analysts get Silver/Gold access by default; Bronze requires an explicit justification.

- **Small File Problem**: Real-time streaming writes thousands of tiny Parquet files (< 1 MB each). HDFS and S3 handle many small files poorly — metadata operations dominate query time. Mitigation: run a compaction job (Spark `optimize` in Delta Lake, or `rewrite_data_files` in Iceberg) on a schedule to merge small files into 128 MB–1 GB target sizes.

---

## Exercises

1. **Easy** — Draw the medallion architecture for a ride-sharing company that receives GPS pings every 5 seconds from drivers. Identify what belongs in Bronze, what transformations create Silver, and what Gold tables a pricing team would need.

2. **Medium** — A Silver table has been running for 6 months when you discover the ETL job had a bug: it silently dropped any order where `currency = "EUR"`. Describe how you would use a Bronze layer and Delta Lake's time travel to produce a corrected Silver dataset without losing the 6 months of non-EUR data already in Silver.

3. **Hard** — Design a data lake architecture for a healthcare organization that must satisfy HIPAA compliance: all PHI must be encrypted at rest and in transit, access must be auditable per-field, and raw data must be deletable within 30 days of a patient data-deletion request. Identify which open table format best supports the deletion requirement and explain the trade-offs.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Data Lake** | "A place to dump all our data" | A schema-agnostic storage system with structured ingestion zones, a catalog, and governed access — not a dumping ground |
| **Schema-on-Read** | "We don't need to think about schema" | Schema is enforced at query time, not write time — you still need a schema; you just defer when you apply it |
| **Data Swamp** | An inevitable outcome of a data lake | The failure state when a lake lacks governance, cataloging, and data quality — entirely avoidable with discipline |
| **Medallion Architecture** | A Databricks-specific concept | A vendor-neutral pattern (Bronze/Silver/Gold) for progressive data quality in any lake; widely adopted across AWS, Azure, and GCP |
| **Data Catalog** | A spreadsheet listing tables | A queryable metadata service tracking schema, lineage, ownership, statistics, and freshness — the connective tissue of a healthy lake |
| **Delta Lake** | "Delta is the database inside the lake" | An open-source storage layer that adds ACID transactions, schema enforcement, time travel, and upsert support on top of Parquet files in object storage |
| **Compaction** | Automatic optimization that just happens | A manual or scheduled job that merges many small files into fewer large files to improve query scan efficiency — does not happen automatically unless configured |

---

## Further Reading

- [AWS Lake Formation Documentation](https://docs.aws.amazon.com/lake-formation/latest/dg/what-is-lake-formation.html) — authoritative reference for building governed lakes on AWS, including fine-grained access control and blueprint-based ingestion
- [Delta Lake Documentation](https://docs.delta.io/latest/index.html) — deep reference for ACID transactions, schema evolution, time travel, and OPTIMIZE on object storage
- [Apache Iceberg Documentation](https://iceberg.apache.org/docs/latest/) — covers hidden partitioning, schema evolution, snapshot isolation, and multi-engine compatibility
- [Fundamentals of Data Engineering — Joe Reis & Matt Housley (O'Reilly, 2022)](https://www.oreilly.com/library/view/fundamentals-of-data/9781098108298/) — the most thorough modern treatment of the data engineering lifecycle, including storage and the lakehouse pattern
- [The Data Engineering Cookbook — Andreas Kretz](https://github.com/andkret/Cookbook) — open-source practitioner guide covering ingestion, processing, and storage architectures with real tool comparisons
