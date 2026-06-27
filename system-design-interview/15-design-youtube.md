# Design YouTube

## Chapter Overview

This chapter addresses designing a video streaming service comparable to YouTube, applicable to platforms like Netflix and Hulu. The solution focuses on handling massive scale with 2 billion monthly active users and 5 billion daily video views.

---

## Step 1: Understanding the Problem & Establishing Design Scope

### Key Statistics (2020)
- 2 billion monthly active users
- 5 billion videos watched daily
- 73% of US adults use the platform
- 50 million content creators
- $15.1 billion ad revenue (2019)
- 37% of mobile internet traffic
- Available in 80 languages

### Design Scope Definition

**Candidate-Interviewer Dialog:**

| Question | Answer |
|----------|--------|
| Important features? | Upload and watch videos |
| Supported clients? | Mobile apps, web browsers, smart TV |
| Daily active users? | 5 million |
| Average daily time spent? | 30 minutes |
| International user support? | Yes, significant percentage |
| Video resolution support? | Most resolutions and formats |
| Encryption required? | Yes |
| Maximum file size? | 1GB |
| Leverage cloud infrastructure? | Yes (recommended approach) |

### Design Focus Areas

The system prioritizes:
- Fast video uploads
- Smooth streaming experience
- Quality adaptation capability
- Low infrastructure costs
- High availability, scalability, reliability
- Support for mobile apps, web, smart TV

### Back-of-Envelope Estimation

**Assumptions:**
- 5 million daily active users (DAU)
- Users watch 5 videos per day
- 10% of users upload 1 video daily
- Average video size: 300 MB

**Storage Calculation:**
- Daily storage needed: 5 million × 10% × 300 MB = 150 TB

**CDN Cost Estimation:**
- Using Amazon CloudFront at $0.02 per GB average
- Daily bandwidth cost: 5 million users × 5 videos × 0.3GB × $0.02 = $150,000/day
- This demonstrates CDN's significant expense, necessitating optimization strategies

---

## Step 2: High-Level Design & Obtaining Agreement

### Architecture Philosophy

Rather than building everything from scratch:
- System design interviews prioritize selecting appropriate technology
- Detailed implementation explanations are less important than architectural decisions
- Large companies (Netflix, Facebook) leverage existing cloud services
- Cost and complexity of building scalable blob storage or CDN is prohibitive

### Three-Component System Architecture

**Client Layer**
- Desktop computers
- Mobile phones
- Smart TVs
- Multiple device types accessing the service

**CDN (Content Delivery Network)**
- Stores and streams videos
- Optimizes video delivery globally
- Handles streaming video requests

**API Servers**
- Process all non-video-streaming requests
- Handle feed recommendations
- Generate upload URLs
- Update metadata database and cache
- Manage user authentication

### Two Primary Flows

1. **Video uploading flow** - Content creation and storage
2. **Video streaming flow** - Content delivery to viewers

---

## Video Uploading Flow (High-Level)

### Components Involved

**User**
- Accesses via computer, mobile phone, or smart TV

**Load Balancer**
- Distributes requests evenly across API servers

**API Servers**
- Route all user requests (except video streaming)
- Coordinate upload process

**Metadata DB**
- Stores video information (sharded and replicated)
- Ensures performance and high availability

**Metadata Cache**
- Improves performance for frequently accessed data
- Caches video metadata and user objects

**Original Storage**
- Blob storage system for raw/original videos
- Binary Large Object (BLOB) defined as collection of binary data stored as single entity in database

**Transcoding Servers**
- Convert videos to multiple formats (MPEG, HLS, etc.)
- Optimize for different devices and bandwidth capabilities

**Transcoded Storage**
- Blob storage for processed video files

**CDN**
- Caches transcoded videos globally
- Streams to users on playback

**Completion Queue**
- Message queue storing transcoding completion events

**Completion Handler**
- Workers pull event data from queue
- Updates metadata cache and database

### Parallel Upload Processes

**Process A: Upload Actual Video**

Steps:
1. Videos uploaded to original storage
2. Transcoding servers fetch and process videos
3. Upon completion (parallel execution):
   - 3a. Transcoded videos sent to transcoded storage
   - 3a.1. Transcoded videos distributed to CDN
   - 3b. Transcoding completion events queued
   - 3b.1. Completion handler pulls event data
   - 3b.1.a & 3b.1.b. Metadata database and cache updated
4. API servers inform client of successful upload and readiness

**Process B: Update Metadata**

- Client sends metadata update request while file uploads
- Metadata includes filename, size, format, codec information
- API servers update both cache and database
- Two-phase approach enables faster overall upload completion

---

## Video Streaming Flow (High-Level)

### Key Concept: Streaming vs. Downloading

**Streaming:** Device continuously receives video data from remote source, allowing immediate playback
**Downloading:** Entire video copied to device before viewing begins

### Streaming Protocols

Essential standardized methods controlling video data transfer:

1. **MPEG-DASH** (Moving Picture Experts Group Dynamic Adaptive Streaming over HTTP)
   - Industry standard format

2. **Apple HLS** (HTTP Live Streaming)
   - Widely supported protocol

3. **Microsoft Smooth Streaming**
   - Microsoft ecosystem standard

4. **Adobe HDS** (HTTP Dynamic Streaming)
   - Legacy format support

Different protocols support varying video encodings and playback players. Protocol selection depends on use case requirements.

### Basic Streaming Architecture

- Videos stream directly from CDN
- Edge servers closest to users deliver content
- Minimal latency through geographic distribution
- Client devices connect to nearest CDN edge location

---

## Step 3: Design Deep Dive

### Video Transcoding

**Definition:** Converting video format to other formats providing optimal streams for different devices and bandwidth capabilities.

**Why Transcoding Matters:**

1. **Storage Efficiency**
   - Raw video consumes massive storage space
   - One-hour HD video at 60fps requires hundreds of GB

2. **Device Compatibility**
   - Different devices/browsers support specific formats only
   - Encoding to multiple formats ensures universal access

3. **Bandwidth Optimization**
   - Higher bitrate for users with fast connections
   - Lower resolution for limited bandwidth users
   - Bitrate: rate at which bits process over time

4. **Network Adaptability**
   - Mobile networks experience varying conditions
   - Automatic quality switching based on network state
   - Maintains continuous playback experience

### Encoding Format Components

**Container**
- File wrapper holding video, audio, metadata
- Identifiable by extension (.avi, .mov, .mp4)
- Functions as organizational structure

**Codecs**
- Compression/decompression algorithms
- Reduce video size while preserving quality
- Common video codecs: H.264, VP9, HEVC

### Directed Acyclic Graph (DAG) Model

**Purpose:** Supports varied video processing needs with high parallelism

**Rationale:**
- Different creators require different processing
- Some need watermarks, thumbnails, varied resolutions
- DAG enables flexible, customizable pipelines
- Facebook's streaming video engine uses similar model

**Example DAG Tasks:**

Original video splits into three processing paths:
1. Video stream → Inspection → Encoding → Thumbnail → Watermark
2. Audio stream → Audio processing
3. Metadata extraction

Final assembly combines all processed elements.

### Video Encoding Example Output

Single source video encoded into multiple resolutions:
- 360p.mp4
- 480p.mp4
- 720p.mp4
- 1080p.mp4
- 4K.mp4

### Video Transcoding Architecture

**Six Main Components:**

1. **Preprocessor**
   - Splits video stream into Group of Pictures (GOP) chunks
   - GOP: group of frames arranged sequentially, independently playable unit (typically few seconds)
   - Handles legacy device compatibility
   - Generates DAG based on configuration files
   - Caches GOPs and metadata in temporary storage
   - Enables retry operations on failure

2. **DAG Scheduler**
   - Breaks DAG into task stages
   - Queues tasks in resource manager
   - Orchestrates parallel and sequential execution
   - Example: Stage 1 splits into video/audio/metadata; Stage 2 encodes and generates thumbnails

3. **Resource Manager**
   - Manages resource allocation efficiency
   - Contains three priority queues:
     - Task queue: tasks to execute
     - Worker queue: worker utilization info
     - Running queue: currently executing tasks and assigned workers
   - Task scheduler component picks optimal task/worker pairs

   **Process:**
   - Gets highest priority task from task queue
   - Selects optimal worker from worker queue
   - Instructs chosen worker to execute
   - Binds task/worker info to running queue
   - Removes completed jobs from queue

4. **Task Workers**
   - Execute defined DAG tasks
   - Different worker types for different operations:
     - Watermark workers
     - Encoder workers
     - Thumbnail workers
     - Merger workers
   - Specialized processing units for parallel execution

5. **Temporary Storage**
   - Stores intermediate processing results
   - Storage choice depends on data characteristics:
     - Frequently accessed metadata cached in memory
     - Video/audio data stored in blob storage
     - Data freed after processing completion

6. **Encoded Video Output**
   - Final output of encoding pipeline
   - Named according to specifications (e.g., funny_720p.mp4)
   - Ready for CDN distribution

---

## System Optimizations

### Speed Optimization: Parallelized Upload

**Challenge:** Uploading entire videos as single unit is inefficient

**Solution:** Split videos into GOP-aligned chunks for parallel uploads

**Advantages:**
- Fast resumable uploads on failure
- Faster overall upload completion
- Client-side splitting improves efficiency
- Failed chunks retry independently

### Speed Optimization: Geographically Distributed Upload Centers

**Approach:** Multiple upload centers positioned globally

**Regional Centers:**
- North America upload center
- Asian upload center
- European upload center
- South America upload center

**Implementation:** Leverage CDN as upload infrastructure

**Benefits:**
- Users upload to nearest regional center
- Reduced latency for upload operations
- Lower bandwidth costs through localization

### Speed Optimization: Parallelism Everywhere

**Problem:** Linear dependencies prevent parallelization

Original flow: Download → Segment → Encode → Upload

**Solution:** Message queues decouple system components

**How Message Queues Help:**
- Encoding module doesn't wait for download completion
- Each module processes queue items independently
- Multiple stages execute simultaneously
- Loose coupling improves system responsiveness

**Modified Flow:**
```
Original Storage → Message Queue → Download Module
                                  ↓
                          Message Queue → Encoding Module
                                          ↓
                                  Message Queue → Upload Module
                                                  ↓
                                                 CDN
```

### Safety Optimization: Pre-Signed Upload URLs

**Purpose:** Ensure only authorized users upload to correct locations

**Implementation Process:**

1. Client sends HTTP POST request to API servers
2. API servers respond with pre-signed URL
3. Client uploads video using URL-provided access
4. Pre-signed URL grants temporary, limited access

**Terminology Variations:**
- Amazon S3 uses "pre-signed URL"
- Microsoft Azure uses "Shared Access Signature"
- Same underlying security principle

### Video Protection Methods

**Digital Rights Management (DRM):**
- Apple FairPlay
- Google Widevine
- Microsoft PlayReady
- Prevents unauthorized copying/distribution

**AES Encryption:**
- Encrypt video content
- Configure authorization policies
- Decrypt upon playback
- Restricts viewing to authorized users only

**Visual Watermarking:**
- Image overlay on video
- Contains identifying information
- Company logo or name
- Deters unauthorized copying

### Cost-Saving Optimization

**Key Insight:** YouTube video access follows long-tail distribution

Long-tail distribution characteristics:
- Few videos accessed frequently
- Many videos have few or no viewers
- Popular content drives most traffic

**Optimization Strategies:**

1. **Selective CDN Usage**
   - Serve most popular videos from CDN
   - Serve less popular videos from high-capacity storage servers
   - Reduces CDN bandwidth costs

2. **On-Demand Encoding**
   - Less popular content needs fewer encoded versions
   - Short videos encoded on-demand (not pre-encoded)
   - Reduces storage requirements

3. **Regional Content Distribution**
   - Some videos popular only in specific regions
   - Don't distribute globally unnecessarily
   - Saves bandwidth costs

4. **Custom CDN Development**
   - Build internal CDN like Netflix
   - Partner with Internet Service Providers (ISPs)
   - ISPs positioned globally, near users
   - Improves viewing experience
   - Reduces bandwidth charges

**Critical Consideration:** Optimizations require historical viewing pattern analysis before implementation

---

## Error Handling

### Error Categories

**Recoverable Errors**
- Retry operation multiple times
- Example: video segment transcoding failure
- Return proper error code if ultimately fails
- System determines recoverability

**Non-Recoverable Errors**
- Stop associated tasks immediately
- Example: malformed video format
- Return appropriate error code to client
- Cannot proceed with processing

### Component-Specific Error Handling Playbook

| Component | Error | Handling Strategy |
|-----------|-------|-------------------|
| Upload | General upload failure | Retry multiple times |
| Video splitting | Legacy client incompatibility | Server-side splitting fallback |
| Transcoding | Encoding failure | Retry operation |
| Preprocessor | DAG generation failure | Regenerate diagram |
| DAG scheduler | Scheduling failure | Reschedule task |
| Resource manager queue | Queue service down | Activate replica queue |
| Task worker | Worker crash/failure | Retry task on new worker |
| API server | Server down | Route to different stateless server |
| Metadata cache | Cache node failure | Access replicated data nodes, launch replacement |
| Metadata DB master | Master database down | Promote slave to new master |
| Metadata DB slave | Slave failure | Use alternate slave, launch replacement server |

---

## Step 4: Wrap-Up & Extensions

### Horizontal Scalability

**API Tier Scaling:**
- API servers are stateless
- Horizontal scaling straightforward
- Add servers as demand increases
- Load balancer distributes traffic

### Database Scaling

**Techniques:**
- Database replication (master-slave)
- Sharding for distributed storage
- Partition data across multiple nodes

### Live Streaming Considerations

**Similarities to Non-Live:**
- Require uploading
- Require encoding
- Require streaming

**Key Differences:**

| Aspect | Live Streaming | Non-Live Streaming |
|--------|----------------|-------------------|
| Latency | Higher latency requirements | Batched processing acceptable |
| Protocol | May need specialized protocols | Standard protocols sufficient |
| Parallelism | Lower requirement (real-time chunks) | High parallelism utilized |
| Error handling | Must be fast (delays unacceptable) | Can afford retry delays |
| Data size | Processed in real-time | Batched for efficiency |

### Video Takedown Process

**Content Removal Triggers:**
- Copyright violations
- Pornographic content
- Illegal activities
- User-flagged violations

**Detection Timing:**
- Some identified during upload
- Others discovered through user reports
- Automated and manual review processes

---

## Key Technical Concepts Summary

**Blob Storage:** Binary Large Objects stored as single database entities; ideal for raw video files

**Bitrate:** Rate at which bits process over time; higher bitrate typically means better quality

**GOP (Group of Pictures):** Frame sequence forming independently playable unit; typically seconds-long

**Codec:** Compression/decompression algorithms reducing file size while maintaining quality

**Container:** Wrapper holding video, audio, and metadata; identified by file extension

**DAG (Directed Acyclic Graph):** Task definition model enabling sequential and parallel execution

**Pre-signed URL:** Temporary access token granting limited permissions to specific resources

**Long-tail Distribution:** Few popular items receive most traffic; many items receive minimal traffic

**CDN (Content Delivery Network):** Geographically distributed servers delivering content with minimal latency

---

## Design Tradeoffs Discussed

1. **Cloud Services vs. Build-from-Scratch**
   - Cloud services reduce complexity and cost
   - Building internally requires massive resources
   - Interview focus: right tool selection over implementation details

2. **CDN Cost vs. Availability**
   - CDN expensive but essential for global coverage
   - Cost optimization requires analyzing access patterns
   - Popular content warrants CDN; niche content uses storage servers

3. **Upload Speed vs. Simplicity**
   - Parallel GOP uploading faster but more complex
   - Single-file upload simpler but slower
   - Geographic distribution adds complexity but reduces latency

4. **Pre-encoding vs. On-Demand Encoding**
   - Pre-encoding: faster playback, higher storage
   - On-demand: lower storage, slower initial playback
   - Decision depends on content popularity

5. **DRM vs. Watermarking**
   - DRM more secure but more complex
   - Watermarking simpler but less protective
   - Choose based on content value

---

## Architecture Summary

The YouTube design leverages cloud infrastructure with three core layers:
- **Client devices** requesting content
- **API servers** handling metadata and orchestration
- **CDN/storage** providing video delivery

The system handles two primary flows:
- **Upload path** featuring parallel video transcoding via DAG model with geographically distributed centers
- **Streaming path** optimized through CDN with adaptive quality selection

Success depends on parallelization through message queues, regional optimization based on content popularity, and comprehensive error handling at each system component.

---

# Deep Dive Addendum

The remainder of this chapter is enrichment for interview-grade depth: extended capacity math, architecture diagrams, trade-off tables, real-world case studies (Netflix, Twitch, TikTok, Periscope, VEVO, Chaos Monkey, HLS/DASH), failure modes, interviewer Q&A, and a glossary.

## Back-of-the-Envelope Math (Extended)

The chapter's headline estimate — 5M DAU, 5 videos/day, 300 MB upload — gives 150 TB of new storage per day. Defend that and extrapolate it to a Netflix/YouTube-class system.

### Step 1 — QPS for streams

```
DAU = 5,000,000 ≈ 5 × 10^6
videos / user / day = 5
total streams / day = 25 × 10^6
seconds / day = 86,400 ≈ 8.64 × 10^4
```

Average stream QPS:

```
QPS_streams_avg = 25e6 / 86,400 ≈ 289 / s
```

This number is deceptively low. Real systems peak at 5-10× the daily average, and a single blockbuster release can push a regional CDN to 10× its baseline within minutes. Treat **3,000-5,000 peak QPS** as the planning target for the API tier, separate from the CDN's bandwidth budget.

### Step 2 — bandwidth (the real constraint)

Average bitrate per stream (mixed SD/HD/4K; YouTube reported in 2017 that >70% of watch time was HD or higher):

```
SD    : 1.5 Mbps
HD    : 5   Mbps
4K    : 25  Mbps
avg   ≈ 5 Mbps (weighted)
```

Per stream ≈ 0.625 MB/s. Total aggregate bandwidth:

```
bandwidth_avg = 289 streams/s × 0.625 MB/s ≈ 181 MB/s ≈ 1.45 Gbps
bandwidth_peak ≈ 5 × bandwidth_avg ≈ 7.2 Gbps
```

A single 100 Gbps port can serve all of it. The cost, however, is dominated by **CDN egress** at the edge.

### Step 3 — storage and growth

Use a more conservative media size estimate. A 10-minute HD video at 5 Mbps encodes to roughly:

```
size = 5 Mbps × 600 s / 8 ≈ 375 MB
```

Chapter says 300 MB upload — close. Assume 300 MB raw average for math continuity.

```
upload_bytes / day = 5e6 × 0.10 × 300 MB = 150 TB / day
upload_bytes / year = 150 TB × 365 ≈ 54.75 PB / year
```

After 5 years, ignoring retention:

```
5y_storage ≈ 274 PB
```

With 3× replication:

```
5y_storage_with_replicas ≈ 822 PB ≈ 0.82 EB
```

Compare to public statements:
- YouTube stored ~1 EB of video in 2015 and was adding hundreds of PB per year.
- Netflix's catalog has been reported in the 10-15 PB range for the master mezzanine files.
- TikTok reportedly stores >100 PB of video (estimates vary).

So the 0.82 EB / 5-year figure is in the right neighborhood for an interview.

### Step 4 — CDN cost deep dive

CloudFront at $0.02/GB egress is a useful baseline but is only the egress fee. Real costs include:

| Cost component | Approx $/GB | Notes |
|---|---|---|
| Egress (CDN) | 0.02-0.08 | Tier discounts above 10 PB/mo |
| Storage (hot S3) | 0.023 | Frequently accessed |
| Storage (infrequent) | 0.0125 | S3 IA |
| Storage (Glacier) | 0.004 | Cold backups |
| Origin request | 0.0075 per 10k | Cache miss penalty |
| Transcoding (per minute of video) | 0.005-0.015 | Codec-dependent |

The chapter's $150,000/day = $54.75M/year CDN cost is on the **low** side for production. Netflix's bandwidth budget alone has been estimated (publicly, by analysts) at >$1B/year at peak. The optimization strategies in the chapter — selective CDN use, on-demand encoding, regional distribution — are precisely how Netflix drove its cost per stream down by an order of magnitude between 2010 and 2020.

### Step 5 — transcoding compute

Transcoding a 10-minute HD video to 5 renditions (1080p, 720p, 480p, 360p, audio-only) takes roughly:

```
real_time_factor = 0.5x (modern x264/HEVC on 16-core CPU)
                   ≈ 1.0x for AV1 on commodity hardware
                   ≈ 0.2x with hardware acceleration (NVENC, Xilinx)
```

So 10 minutes of source ≈ 5-10 minutes of CPU time per rendition × 5 renditions = 25-50 CPU-minutes per upload. With 500,000 uploads/day (10% of 5M DAU):

```
cpu_minutes / day = 5e5 × 40 = 2e7 minutes ≈ 333,333 cpu-hours
```

Equivalent fleet:

```
vms (16 vCPU each) ≈ 333,333 / 24 / 16 ≈ 868 VMs continuously running
```

This fleet is the dominant compute cost and is why modern systems invest heavily in per-instance hardware encoders (NVENC) and per-rack FPGAs.

---

## ASCII Architecture Diagrams

### Diagram 1 — Upload pipeline (full fan-out)

```
                       Client
                         │
              ┌──────────┴──────────┐
              │ POST /videos (meta) │──▶ API GW ─▶ Metadata DB (sharded)
              │                     │           └─▶ Metadata Cache (Redis)
              │ PUT  presigned URL  │◀──────────── pre-signed S3 URL
              │                     │
              │ chunked PUT         │             ┌────────────┐
              └─────────────────────┘             │  Original  │
                                                  │   (S3)     │
                                                  └─────┬──────┘
                                                        │  event: ObjectCreated
                                                        ▼
                                                  ┌────────────┐
                                                  │   SQS /    │
                                                  │   Kafka    │
                                                  └─────┬──────┘
                                                        │
                          ┌─────────────────────────────┼─────────────────────────────┐
                          │                             │                             │
                          ▼                             ▼                             ▼
                  ┌──────────────┐            ┌──────────────┐              ┌──────────────┐
                  │  Preprocess  │            │  Preprocess  │              │  Preprocess  │
                  │  worker #1   │            │  worker #2   │              │  worker #N   │
                  └──────┬───────┘            └──────┬───────┘              └──────┬───────┘
                         │                           │                             │
                         ▼                           ▼                             ▼
                  ┌──────────────┐            ┌──────────────┐              ┌──────────────┐
                  │  DAG         │            │  DAG         │              │  DAG         │
                  │  Scheduler   │            │  Scheduler   │              │  Scheduler   │
                  └──────┬───────┘            └──────┬───────┘              └──────┬───────┘
                         │                           │                             │
       ┌───────────┬─────┴─────┬───────────┐         │                             │
       ▼           ▼           ▼           ▼         ▼                             ▼
  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐                              (…)
  │Inspect  │ │Encode   │ │Thumb-   │ │Watermark│
  │worker   │ │worker   │ │nail wkr │ │worker   │
  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
       │           │           │           │
       └───────────┴─────┬─────┴───────────┘
                         ▼
                  ┌──────────────┐
                  │   Merger     │
                  └──────┬───────┘
                         ▼
                  ┌──────────────┐
                  │ Transcoded   │
                  │   (S3)       │── event ──▶ SQS ──▶ Completion Handler ──▶ Metadata update
                  └──────┬───────┘                                            ──▶ CDN pre-warm
                         │
                         ▼
                    CDN POPs (global)
```

### Diagram 2 — Streaming sequence (HTTP-based ABR)

```
Player              CDN edge              Origin (S3)         Manifest service
  │                    │                       │                    │
  │ GET manifest.m3u8  │                       │                    │
  │───────────────────▶│  cache miss           │                    │
  │                    │──────────────────────▶│                    │
  │                    │◀─── 404 to manifest ──│                    │
  │                    │────── fallback ────────────────────────────▶│
  │                    │◀────── fresh manifest ──────────────────────│
  │◀── HLS manifest ───│                       │                    │
  │                    │                       │                    │
  │ (parses available  │                       │                    │
  │  bitrates; picks   │                       │                    │
  │  based on bandwidth│                       │                    │
  │  estimate)         │                       │                    │
  │ GET seg-00042.ts   │                       │                    │
  │───────────────────▶│  cache hit            │                    │
  │◀───── segment ─────│                       │                    │
  │ ...                │                       │                    │
  │ GET seg-00043.ts   │                       │                    │
  │───────────────────▶│                       │                    │
  │                    │  cache miss           │                    │
  │                    │───── range GET ──────▶│                    │
  │                    │◀──── segment ─────────│                    │
  │◀───── segment ─────│                       │                    │
  │                    │                       │                    │
  │ (re-evaluates bw;  │                       │                    │
  │  upgrades to 720p  │                       │                    │
  │  variant)          │                       │                    │
  │ GET seg-00044.ts (720p variant)             │                    │
  │───────────────────▶│                       │                    │
  │◀───── segment ─────│                       │                    │
```

### Diagram 3 — DAG (transcoding pipeline, conceptual)

```
        ┌────────────┐
        │  Source    │
        │   video    │
        └─────┬──────┘
              │
   ┌──────────┼──────────┐
   │          │          │
   ▼          ▼          ▼
┌──────┐  ┌──────┐  ┌──────────┐
│Probe │  │Probe │  │ Extract  │
│video │  │audio │  │ metadata │
└──┬───┘  └──┬───┘  └────┬─────┘
   │         │           │
   ▼         ▼           ▼
┌──────┐  ┌──────┐  ┌──────────┐
│Encode│  │Encode│  │ Thumb-   │
│video │  │audio │  │ nails    │
│ x N  │  │ x 1  │  │ x K      │
└──┬───┘  └──┬───┘  └────┬─────┘
   │         │           │
   └────┬────┴─────┬─────┘
        │          │
        ▼          ▼
   ┌────────┐ ┌────────┐
   │Watermark│ │Manifest│
   └────┬────┘ └────┬───┘
        │          │
        └────┬─────┘
             ▼
        ┌─────────┐
        │  Pack   │──▶ Transcoded renditions
        └─────────┘
```

### Diagram 4 — Live streaming (LL-HLS / WebRTC hybrid)

```
Creator device ──▶ Ingest server (RTMP/SRT)
                          │
                          ▼
                   Transcode cluster
                          │
                ┌─────────┴─────────┐
                ▼                   ▼
         Packager (HLS/DASH)   Recording (VOD)
                │
                ▼
         Origin (S3 / origin cache)
                │
        ┌───────┼───────┐
        ▼       ▼       ▼
     Edge A   Edge B   Edge C
        │       │       │
        ▼       ▼       ▼
   Viewer A Viewer B Viewer C
   (2-15 s glass-to-glass)
```

---

## Trade-off Tables

### Trade-off 1 — Where to transcode

| Option | Latency to playback | Cost | Operational complexity | Best for |
|---|---|---|---|---|
| Direct EC2/VM with x264 | Minutes | Low–medium (CPU-bound) | Low | Small systems |
| Hardware-accelerated (NVENC, M-series) | Seconds | Medium (per-host license) | Low | Mid-scale, AV1 |
| FPGA-based | Seconds | High (capex + dev) | High | Netflix-class, AV1 at scale |
| Serverless (Lambda + FFmpeg) | Minutes | Variable (per-GB-second) | Low | Bursty workloads |
| Hybrid: GPU + CPU fallback | Seconds | Medium | Medium | Most production |

### Trade-off 2 — Streaming protocol

| Protocol | Latency | Codec flexibility | Device support | DRM | Cost |
|---|---|---|---|---|---|
| HLS | 2-30 s | All (with fMP4) | Excellent (Apple, Android, browsers) | FairPlay / Widevine | Low |
| DASH | 2-30 s | Excellent | Excellent (browsers, Android, smart TVs) | Widevine / PlayReady | Low |
| LL-HLS / LL-DASH | 1-3 s | All | Excellent (recent) | Same as HLS/DASH | Slightly higher (more segments) |
| WebRTC | <500 ms | Limited (VP8/VP9/AV1/H.264) | Browsers, native apps | Custom | High (stateful) |
| RTMP (legacy) | 2-5 s | H.264/AAC | Flash-era (deprecated) | Limited | Low |
| SRT / RIST | <500 ms | All | Broadcast hardware | Limited | Medium |

The chapter's enumeration is the historical baseline. The pragmatic modern answer is **HLS for VOD and live to massive audiences**, **DASH for cross-platform VOD with Widevine/PlayReady**, and **LL-HLS or WebRTC** when glass-to-glass latency matters (sports, auctions).

### Trade-off 3 — CDN strategy

| Strategy | Upfront cost | Per-stream cost | Reliability | Failure isolation | Best for |
|---|---|---|---|---|---|
| Single CDN | Low | High (no leverage) | Medium | Poor | Small |
| Multi-CDN with weighted DNS | Medium | Low (competitive bidding) | High | Good | Most production |
| Multi-CDN with real-time load balancing | High | Lowest | Highest | Excellent | Netflix/YouTube-class |
| Owned CDN (Open Connect model) | Very high | Lowest per-GB at scale | Highest | Excellent | ISPs and large catalogs |

### Trade-off 4 — Storage for source vs. transcoded

| Option | Source retention | Transcoded retention | Cost |
|---|---|---|---|
| Keep source + all renditions | Forever | Forever | Highest |
| Keep source, regenerate renditions on demand | Forever | None hot; regenerate | Medium |
| Keep source + only popular renditions | Forever | Conditional | Lower |
| Source + renditions + per-region copies | Forever | Forever | Highest (regional egress) |

---

## Real-World Case Studies

### Case Study 1 — YouTube's video pipeline (and the VEVO partnership)

YouTube's published details describe a pipeline similar to the chapter's design, with two notable twists:

- **Region-pinned upload**: uploads terminate at the nearest of ~10 regional upload centers; the original is then replicated to a global bucket via internal backbone. This is the "geographically distributed upload centers" optimization in production.
- **The VEVO content delivery pipeline** (described in academic and industry talks): VEVO's catalog is uploaded by labels through a separate pipeline that enforces higher quality standards (master files, color grading metadata) before public release. This is the canonical example of **multi-tenant transcoding** within a shared infrastructure.

YouTube also publishes that >90% of views come from **H.264 + VP9** renditions; the AV1 rollout (announced 2018, expanded 2020+) targets long-tail views to reduce egress. This is exactly the long-tail argument from the chapter.

### Case Study 2 — Netflix Open Connect

Netflix's Open Connect is the canonical reference for **owning your CDN**:

- Netflix places **Open Connect Appliances (OCAs)** — high-density storage servers — directly inside ISP networks on a peering basis.
- Each OCA holds a slice of Netflix's catalog; ISP-popularity heuristics determine which OCA gets which titles.
- The **"Netflix ZooKeeper"** system manages OCA fleet, catalog placement, and routing.
- Netflix publishes a **"FreeBSD" stack** on OCA hardware for predictable performance.

Key tradeoffs Netflix made:

- **Capex vs. Opex**: building OCAs is high-capex but cuts egress costs by 50-80% vs. commercial CDN.
- **ISP negotiation**: this works at Netflix's scale because ISPs will negotiate; smaller streamers cannot replicate it.

### Case Study 3 — Twitch live streaming

Twitch is the canonical reference for **live streaming at scale**:

- Ingest: RTMP from broadcaster → Twitch edge → transcoding cluster.
- Distribution: HLS to most viewers; LL-HLS (since 2020) for sub-2-second latency to some clients.
- Storage: every broadcast is **simultaneously recorded to VOD** — the same pipeline produces both a live stream and a permanent recording.
- Chat is decoupled: handled by a separate IRC-derived service.

Twitch's key insight: the **storage write path for live is the same as the upload path for VOD** — the pipeline is essentially a VOD pipeline that runs continuously. The latency constraint is in the player edge, not the ingest or transcoding.

### Case Study 4 — TikTok upload

TikTok's pipeline is heavily optimized for **short-form content**:

- Client app **uploads in parallel GOPs** (chapter's optimization 1) at aggressive bitrates, prioritizing speed over quality.
- Server-side transcoding happens within a few seconds; the platform enforces a **hard upload-size cap** (288 MB for many years, lifted in stages).
- The pipeline is sized for **billions of uploads per day** (TikTok reported >1B daily video views by 2019, with the upload number comparable).

The interesting design choice is **client-side processing**: TikTok's mobile SDK handles most editing, effects, and even some compression before upload, offloading compute that YouTube/Netflix would do server-side.

### Case Study 5 — Periscope / Twitter Live

Periscope (acquired by Twitter, shut down 2021) was a notable reference for **live from phone** before Twitter Live absorbed it:

- Used **HLS** for distribution within seconds of ingest.
- The "replay" feature reused the recorded stream as a regular VOD — the pipeline emitted both.
- Showed the cost economics of live: storage costs dominated by replay retention.

Periscope is now mostly a historical reference but is a clean interview example of "live + replay = one pipeline, two outputs."

### Case Study 6 — Netflix Chaos Monkey

Chaos Monkey (open-sourced 2012) and the broader **Simian Army** are Netflix's canonical reliability tooling:

- Chaos Monkey **randomly terminates EC2 instances** in production to ensure services tolerate instance loss.
- Latency Monkey injects delays; Doctor Monkey detects unhealthy instances; Security Monkey finds security violations.
- The broader principle: **failure is normal**; services must be designed so single-instance loss is a non-event.

The chapter's error handling table is the static version of what Chaos Monkey enforces: every component must have a tested failure path, and the system as a whole must keep serving.

### Case Study 7 — HLS / DASH technical specifics

**HLS (HTTP Live Streaming)**:

- Apple-authored, 2009. Now an IETF-style RFC (RFC 8216).
- Manifest: `.m3u8` playlist referencing `.ts` or `fMP4` segments.
- Default segment length: 6 s (LL-HLS: 200 ms to 1 s).
- Wide device support; the de facto cross-platform standard.

**DASH (Dynamic Adaptive Streaming over HTTP)**:

- MPEG / ISO standard (ISO/IEC 23009-1), first published 2012.
- Manifest: `.mpd` (Media Presentation Description) XML.
- Codec-agnostic; supports H.264, HEVC, AV1, VP9.
- Required for some broadcast and standards-driven use cases.

**Common low-latency extensions**:

- **LL-HLS**: partial segments, HTTP/2 push, playlist delta updates.
- **LL-DASH**: chunked transfer encoding, low-latency CMAF.
- **CMAF (Common Media Application Format)**: fMP4 segments that work with both HLS and DASH, halving storage for dual-format delivery.

The chapter enumerates the legacy quartet (HLS, DASH, Smooth, HDS). For an interview today, **HLS + DASH over CMAF with optional LL-HLS** is the production default; Smooth and HDS are legacy.

---

## Common Pitfalls & Failure Modes

### Pitfall 1 — Transcoding a malformed source crashes the worker

A single malformed video file can take down a worker if the FFmpeg invocation doesn't sandbox failures. Mitigations:

- Run each transcode in a **container with strict resource caps**.
- Use FFmpeg's **error tolerance flags** (`-err_detect ignore_err`, `-max_interleave_delta`).
- Pre-flight with a **probe-only pass** before queuing the full DAG.

### Pitfall 2 — GOP-aligned chunks fail to reassemble

If the client splits the upload on byte boundaries that don't align with the server's GOP boundaries, the server cannot cleanly reassemble the source. Mitigations:

- Define a **canonical chunk size** (e.g., 16 MB) and document the contract.
- Have the server always **re-segment on ingest** regardless of client splits.

### Pitfall 3 — CDN cache poisoning via malicious manifest

If an attacker can write to the manifest service (e.g., via leaked credentials or SSRF), they can redirect all viewers to malicious content. Mitigations:

- **Sign manifests** (HLS: AES-128 + signed URI; DASH: signed MP4 boxes).
- Strict IAM on the manifest service; no public write paths.
- **DRM** for premium content.

### Pitfall 4 — Long-tail catalog overflows the CDN

A naive "cache everything" approach explodes CDN storage when the catalog is 10 PB+. Mitigations:

- **Tiered CDN**: popular content in hot tier; long-tail in cold tier (slower, cheaper).
- **Pre-warming**: only push to CDN after view-count threshold (e.g., 100 views/hour).
- **On-demand retrieval**: long-tail content comes from origin with longer cache TTL.

### Pitfall 5 — Live stream stutter under flash crowd

When a streamer goes viral mid-broadcast, the ingest cluster saturates and the stream stalls for everyone. Mitigations:

- **Adaptive ingest**: transcoding scales horizontally; metrics-driven autoscaling with 30-60 s headroom.
- **Multi-CDN failover**: when one CDN is saturated, push to another.
- **Limit broadcast quality** during saturation (e.g., cap to 1080p temporarily).

### Pitfall 6 — Transcoding cost blow-out from re-encoding

Re-encoding on every metadata update multiplies costs: a 1% re-encode rate is fine; a 100% re-encode rate doubles the bill. Mitigations:

- Encode is **idempotent on source hash**: same source → no re-encode.
- Metadata changes (title, thumbnail) do **not** trigger re-encode.
- Re-encode triggered only when **source content** changes.

### Pitfall 7 — Player stalls because ABR misreads bandwidth

The player misreads available bandwidth (cross-traffic, VPN overhead) and over-requests the highest rendition, then stalls. Mitigations:

- Use **buffer-based ABR** (Bola, BBR) instead of pure throughput-based.
- **Aggressive initial buffer** (10-15 s) to absorb jitter.
- **Forensic logging** of player metrics to detect bad networks.

---

## Interview Q&A

**Q1 — How would you redesign for 10× the upload volume?**

A: Three answers, in order. (1) **Decouple ingest from transcoding**: uploads go to S3 (or equivalent), and transcoding is a separate, autoscaled worker pool. The ingest path's only job is to durably store the source. (2) **Distribute upload ingress**: instead of one global endpoint, route uploads to the nearest of N regional ingest POPs; cross-region replication handles fan-out. (3) **Pre-warm encoders**: keep a baseline fleet sized for 2× the average load; burst-scale 10× on demand (warm pool of spot instances, not cold Lambda). Mention that the cost of 10× more uploads is dominated by **storage**, not transcoding — so the storage tier must be tiered (hot/warm/cold) and the catalog management must purge aggressively.

**Q2 — How do you cut CDN cost by 50%?**

A: Stack the optimizations. (1) **Selective CDN**: only the top X% of views-per-title go to CDN; the rest serve from origin with longer cache TTL. (2) **On-demand encoding**: don't pre-encode renditions for content with no views; encode on first view. (3) **AV1**: AV1 is ~30% smaller than H.264 at the same quality; rolling out AV1 to compatible clients is the single largest bandwidth lever. (4) **Regional popularity**: don't distribute a Korean drama globally; keep it in regional CDN POPs. (5) **Long-tail cache eviction**: push titles below a view threshold out of CDN. The combination routinely cuts egress by 40-60% in published case studies.

**Q3 — How does live streaming differ architecturally?**

A: Three differences. (1) **Latency budget**: VOD can take hours to encode; live must be <30 s end-to-end. This pushes the pipeline to **incremental transcoding** (process each segment as it arrives, not the whole file). (2) **No source retention before ingest**: a live stream is consumed as it is created; you cannot go back. Storage happens **after** the live edge. (3) **Adaptive protocols**: HLS/DASH still work for live, but with shorter segments (1-2 s) and HTTP/2 push for sub-second latency (LL-HLS). WebRTC is the alternative for sub-500 ms (chat, gaming).

**Q4 — How would you make this system global?**

A: Layered answer. (1) **Edge ingress**: regional upload POPs in 5-10 regions; cross-region replication to a global bucket. (2) **CDN by region**: each region has its own CDN POPs and a regional manifest service; cross-region requests route to the nearest healthy edge. (3) **Geo-DNS**: latency-based DNS to direct viewers to the nearest edge. (4) **Per-region catalog**: legal content varies by region; the manifest service enforces per-region allowlists. (5) **Compliance**: data residency rules (GDPR, China's PIPL) may require keeping source uploads in-region; the storage layer must be region-aware. The interview should mention that **the metadata DB is the hard part** — global transactions across regions are slow; use eventual consistency with conflict resolution for cross-region metadata.

**Q5 — What if a single 4K stream is taking down a CDN POP?**

A: This is a real failure mode during major events. Mitigations: (1) **Per-CDN rate limit**; the player backs off when 4xx/5xx rates spike. (2) **Origin shielding**: route edge misses through a regional shield POP that can absorb the load. (3) **Manifest-based fallback**: the manifest serves a lower-bitrate variant when the player signals network pressure. (4) **Multi-CDN failover**: when one CDN's error rate exceeds a threshold, redirect to a backup via DNS. (5) **Pre-positioning**: for known events, pre-warm the catalog into CDN POPs ahead of time.

**Q6 — How do you measure QoE (Quality of Experience)?**

A: Player-side metrics, sampled at scale. (1) **Startup time**: from `play` to first frame; target <1 s. (2) **Rebuffer ratio**: total stall time / play time; target <1%. (3) **Rendition switches per session**: too many indicates ABR misbehavior. (4) **Average bitrate delivered**: proxy for quality. (5) **Video startup failure rate**: catastrophic failures. The hard part is correlating these to **content ID + CDN + region + device** to find root causes. The data volume requires a streaming pipeline (Kafka → Flink → BigQuery / Druid).

---

## Glossary

| Term | Definition | Common misconception |
|---|---|---|
| GOP (Group of Pictures) | Sequence of frames starting with a keyframe, independently decodable | "A GOP is one second" — it varies; 1-10 s is common |
| Codec | Compression/decompression algorithm for video (H.264, HEVC, AV1, VP9) | "Codec is the same as container" — codec compresses; container holds |
| Container | File format wrapping audio + video + metadata (MP4, MKV, TS) | Confusing MP4 the codec vs MP4 the container |
| ABR (Adaptive Bitrate) | Player-side logic that switches rendition based on bandwidth | "Higher bitrate is always better" — only if bandwidth supports it |
| HLS | HTTP Live Streaming; Apple's protocol, now ubiquitous | "HLS is Apple-only" — used everywhere, including Android |
| DASH | MPEG-DASH; ISO standard adaptive streaming | "DASH is replacing HLS" — both coexist; CMAF unifies the storage |
| CMAF | Common Media Application Format; fMP4 used by both HLS and DASH | Often confused with "fragmented MP4" generally |
| LL-HLS / LL-DASH | Low-latency extensions, sub-2-second glass-to-glass | "LL-HLS is just shorter segments" — also uses HTTP/2 push and playlist delta |
| Glass-to-glass latency | Time from camera capture to viewer screen | Often confused with player-side latency only |
| Pre-signed URL | Time-limited upload/download token granting direct blob access | "Pre-signed = public" — the URL is bearer-token; leak = full access |
| DRM | Digital Rights Management; encryption-based content protection | "DRM prevents all copying" — DRM is defeated by screen recording; it raises the bar |
| CDN POP | Point of Presence; a CDN edge location | "POP = data center" — POPs are smaller, optimized for cache + egress |
| OCA | Open Connect Appliance; Netflix's ISP-deployed CDN node | "OCA = CDN" — it is Netflix-specific; the strategy generalizes |
| Transcoding | Converting video format/codec/resolution | "Transcoding = compression" — also covers container and codec change |
| Rendition | A specific encoded version of a video (e.g., 720p H.264) | "Rendition = bitrate" — rendition includes codec, resolution, and bitrate |
| Manifest | Playlist file describing available renditions and segments | "Manifest = the video" — manifest is metadata; video is the segments |
| DAG | Directed Acyclic Graph; task dependency model | Used for many pipelines; transcoding is one example |
| OCA / Open Connect | Netflix's ISP-deployed CDN | Often confused with "private CDN" generally |
| Chaos engineering | Discipline of injecting failures to test resilience | "Chaos = random reboots" — Chaos Monkey is one tool; the practice is broader |
| AV1 | Royalty-free codec from Alliance for Open Media | "AV1 is unproven" — now deployed at YouTube, Netflix, Meta at scale |
| fMP4 | Fragmented MP4; ISOBMFF segments used by HLS/DASH/CMAF | Confused with regular MP4; structure is different |