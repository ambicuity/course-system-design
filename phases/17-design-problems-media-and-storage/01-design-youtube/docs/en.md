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
