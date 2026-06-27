# A Framework For System Design Interviews

## Chapter Overview

System design interviews simulate real-world problem-solving where professionals collaborate on ambiguous problems to reach practical solutions. The final design matters less than the process demonstrated, revealing capabilities in design thinking, collaboration, pressure management, and ambiguity resolution.

### Interviewer Assessment Criteria

Interviewers evaluate multiple dimensions beyond technical design:

- **Collaboration abilities** - working effectively with others
- **Performance under pressure** - maintaining composure and clarity
- **Constructive ambiguity resolution** - asking clarifying questions
- **Critical questioning** - identifying what information is needed

**Red flags to avoid:**
- Over-engineering without considering trade-offs
- Narrow-mindedness and inflexibility
- Proceeding without understanding requirements
- Failing to communicate thinking process

### What the Interviewer Is Actually Scoring

The interviewer is not (usually) trying to verify a specific design. They are trying to answer four questions in 45 minutes:
1. Can this candidate decompose an ambiguous problem into something tractable?
2. Can they reason about scale without getting lost in implementation detail?
3. Can they identify trade-offs and make defensible decisions under uncertainty?
4. Will they be a productive teammate who pushes back constructively on bad ideas?

Every artifact in the interview — the diagram, the back-of-envelope math, the trade-off table — is in service of those four signals.

---

## The 4-Step Process for System Design Interviews

### Step 1: Understand the Problem and Establish Design Scope (3-10 minutes)

**Core Principle:** "Do not jump right in to give a solution. Slow down. Think deeply and ask questions to clarify requirements and assumptions."

#### Key Questions to Ask

- What specific features should we build?
- How many users does the product have?
- What scaling timeline: 3 months, 6 months, 1 year?
- What technology stack exists to leverage?
- Target platform: mobile, web, or both?
- What are the most important features?
- How should content be sorted or ranked?
- What is the expected traffic volume?
- What media types should be supported?

#### Documentation Strategy

Write down interviewer answers and your explicit assumptions on the whiteboard for future reference during the session.

#### Example: News Feed System

**Candidate:** Is this mobile, web, or both?
**Interviewer:** Both.

**Candidate:** What are the critical features?
**Interviewer:** Post creation and viewing friends' feeds.

**Candidate:** Sort order preferences?
**Interviewer:** Reverse chronological for simplicity.

**Candidate:** Friend connection limits?
**Interviewer:** 5,000 friends per user.

**Candidate:** Daily active users?
**Interviewer:** 10 million.

**Candidate:** Media support needs?
**Interviewer:** Images and videos included.

#### The "Five-Question Rule" for Scoping

When the problem is genuinely ambiguous, ask at minimum:
1. **Who** are the users, and roughly how many?
2. **What** are the 2-3 most important features?
3. **How much** traffic (QPS) and data (storage)?
4. **Where** are the users geographically?
5. **Which** constraints are non-negotiable (latency, consistency, compliance)?

These five questions give you 80% of the design context. The remaining 20% comes out during the deep dive.

---

### Step 2: Propose High-Level Design and Get Buy-In (10-15 minutes)

**Approach:** Develop an initial blueprint, seek feedback, and treat the interviewer as a collaborative teammate.

#### Design Deliverables

- Draw box diagrams showing major components (clients, APIs, servers, data stores, cache, CDN, message queues)
- Perform back-of-the-envelope calculations to validate scale assumptions
- Communicate reasoning out loud throughout
- Walk through concrete use cases
- Optionally include API endpoints and database schemas (depends on problem scope)

#### Example: News Feed System Design

**Two Primary Flows:**

1. **Feed Publishing Flow** - User publishes post → data written to cache/database → post distributed to friends' feeds

2. **News Feed Building Flow** - Aggregates friends' posts in reverse chronological order

**Figure 1: Feed Publishing Architecture**

System displays user request path through DNS, load balancer, and multiple web servers. Web servers communicate with Post Service (accessing Post Cache and Post DB), Fanout Service (populating News Feed Cache), and Notification Service. Architecture demonstrates clustering and replication with dashed lines around web servers and cache layers.

**Figure 2: News Feed Retrieval Architecture**

User request flows through DNS and load balancer to web server cluster. News Feed Service retrieves data from News Feed Cache layers. Read-only operation pattern shown with unidirectional data flow.

#### What "High-Level" Actually Looks Like

The high-level design is intentionally rough — boxes with labels, arrows showing the dominant flow, and a few key annotations. The purpose is to anchor the conversation, not to ship a precise diagram. If you spend 20 minutes drawing, you have failed at this step. The boxes you should always include:
- Client (mobile/web)
- Edge (DNS, CDN, load balancer)
- API gateway / web tier
- Stateless services (the meat of your design)
- Stateful stores (database, cache, blob, search index)
- Async messaging (queue, stream)

Anything beyond this is the deep dive.

---

### Step 3: Design Deep Dive (10-25 minutes)

**Prerequisites Before Deep Dive:**
- Agreement on overall goals and feature scope
- Sketched high-level blueprint
- Interviewer feedback incorporated
- Identified focus areas for detailed investigation

#### Strategic Approach

- Collaborate with interviewer to prioritize which components deserve deep exploration
- Adapt to interviewer signals: some prefer high-level focus, senior roles may emphasize performance characteristics
- Manage time carefully to avoid getting lost in irrelevant minutiae
- Prioritize demonstrating scalability design abilities over algorithmic depth

#### Example: News Feed System - Detailed Flows

**Figure 3: Feed Publishing Detailed Design**

Complete request flow includes: user authentication, rate limiting through web servers, Post Service interaction with Post Cache/DB, Fanout Service querying Graph DB for friend IDs (step 1), retrieval of friend data from User Cache/DB (step 2), message queuing (step 3), Fanout Workers processing queue messages (step 4), and News Feed Cache updates (step 5).

**Figure 4: News Feed Retrieval Detailed Design**

Retrieval process: load balancer (1) distributes to web server cluster (2), News Feed Service handles requests (3), News Feed Cache provides data (4), User Cache and Post Cache store supplementary information (5), CDN layer optimizes content delivery (6).

#### How to Choose What to Dive Into

Three signals tell you which component deserves 10 minutes of detail:
- **The interviewer named it.** ("Tell me about the feed assembly step.") — answer at depth.
- **It is a known hard problem.** (Sharding, distributed cache invalidation, leader election.) — show you know the trade-offs.
- **It is the bottleneck you just identified.** (DB writes, fanout cost, search index size.) — explain how you'd address it.

Everything else should get one sentence.

---

### Step 4: Wrap Up (3-5 minutes)

#### Discussion Topics for Conclusion

**System Bottlenecks & Improvements:**
- Identify scaling limitations in current design
- Propose enhancement strategies
- Never claim perfection—there is always room for optimization

**Design Recap:**
- Summarize key components and decisions
- Refresh interviewer memory if multiple solutions were proposed

**Error Handling & Failure Scenarios:**
- Server failures
- Network partitions and loss
- Data consistency approaches

**Operational Concerns:**
- Monitoring and metrics strategy
- Error logging mechanisms
- System rollout procedures

**Future Scaling:**
- How to support 10x growth from current capacity
- Infrastructure and architectural changes required

**Additional Refinements:**
- Further improvements with additional time or resources

#### A Strong Wrap-Up Pattern

In the last 3-5 minutes, structure your close like this:
1. **Recap in one sentence.** "We built a fanout-on-write news feed with read-from-cache serving, sharded user database, and Kafka-backed fanout workers."
2. **Identify the single biggest bottleneck.** "If load grows 10x, the fanout step for celebrity users becomes the constraint — we'd move to hybrid fanout-on-write for normal users and fanout-on-read for celebrities."
3. **Acknowledge what you would not do yet.** "We have not addressed GDPR data deletion or media upload pipeline — both would be the next priorities."
4. **Invite feedback.** "What part of this design would you push on?" — gives the interviewer a graceful way to redirect.

This pattern takes 60 seconds and converts a generic close into a strong signal of engineering judgment.

---

## Best Practices: Dos and Don'ts

### Dos ✓

- Always request clarification rather than assuming
- Thoroughly understand stated requirements
- Recognize that solutions vary by organizational context (startup vs. established enterprise)
- Communicate your thinking process explicitly to interviewer
- Suggest multiple viable approaches when possible
- Focus on most critical components after high-level agreement
- Use interviewer as a collaborative partner, bouncing ideas continuously
- Persist through difficult sections without surrender

### Don'ts ✗

- Don't arrive unprepared for common interview questions
- Don't propose solutions before clarifying requirements
- Don't dive deeply into single components during initial design
- Don't hesitate to request hints when stuck
- Don't solve problems silently without external communication
- Don't consider the interview concluded after presenting design—continue seeking feedback until interviewer signals completion

### The Senior-Engineer Behaviors

What separates a senior answer from a mid-level answer is not vocabulary but behavior:
- **Naming the trade-off out loud.** "We could do X, but it costs Y, so I'd choose Z because…" — not just "Z is best."
- **Pushing back when something is wrong.** If the interviewer says "the database cannot fail," say "then we need a synchronous replica — but that doubles write latency."
- **Knowing when not to optimize.** "For 10 M DAU, single-region Postgres is fine. We should not shard yet."
- **Asking "who owns this?"** A senior engineer thinks about the team that has to operate the system, not just the system itself.

---

## Time Budget for 45-Minute Interview

| Step | Duration | Purpose |
|------|----------|---------|
| **Step 1** | 3-10 min | Requirement clarification and scope definition |
| **Step 2** | 10-15 min | Blueprint proposal and stakeholder alignment |
| **Step 3** | 10-25 min | Detailed component investigation |
| **Step 4** | 3-5 min | Summary, feedback, and future considerations |

**Note:** Time allocation varies based on problem scope and interviewer priorities. Use as rough guidance only.

### Time-Allocation Heuristics

- **Open-ended problems** ("design Twitter"): spend more time on Step 1 (scoping is the whole game) and less on Step 3 (depth on one component).
- **Bounded problems** ("design a rate limiter"): Step 1 should be brief; spend more time in Step 3 (algorithms, distributed state).
- **Senior+ interviews**: Step 2 may shrink and Step 3 grow as the interviewer expects you to make trade-off calls quickly.
- **Phone screens**: usually only Steps 1 and 2 fit. Save the deep dive for onsite.

---

## Back-of-the-Envelope Math — Anchoring the Design

The framework's "back-of-envelope math" step is not decoration. It is the moment where vague requirements become a concrete workload that the design must satisfy. Worked example for "design Twitter," with assumptions stated out loud:

```
Assumptions (state on the whiteboard):
  - 300 M MAU, 50% DAU          → 150 M DAU
  - 5 timeline reads per DAU/day, 0.5 writes (tweets/likes/RTs)
  - Read payload 200 KB, write payload 1 KB
  - 2x peak vs average for consumer social
  - 5-year retention
```

**QPS:**

```
Read  QPS = 150e6 *  5 / 86_400 ≈  8.7 K avg, ~17 K peak
Write QPS = 150e6 * 0.5 / 86_400 ≈   870 avg, ~1.7 K peak
Fanout QPS (writes × avg followers) — if avg followers ≈ 200:
            = 870 * 200          ≈ 174 K fanout writes/s avg
            = ~350 K peak
```

**Storage (5 years):**

```
Tweets/day = 150 M * 0.5 = 75 M
Bytes/day  = 75 M * 1 KB = 75 GB raw
5 years     ≈ 75 * 365 * 5 GB = ~137 TB raw
With 3x replication                       ≈ 410 TB
+ media (10% of tweets, 1 MB each)        ≈ 13 PB raw, ~40 PB replicated
```

**Bandwidth:**

```
Read  BW   = 8.7 K * 200 KB = 1.7 GB/s avg, ~3.5 GB/s peak
Write BW   = 870  *   1 KB = 870 KB/s (negligible)
Fanout BW  = 174 K * 1 KB  = 174 MB/s to internal queue (significant)
```

**Decision implications (what the math forces):**
- 17 K read peak QPS → at least 3-5 web nodes behind a load balancer.
- 1.7 K write QPS → a single Postgres primary with replicas is fine until you cross ~10 K.
- 174 K fanout QPS → a synchronous fanout inside the request path is impossible. Must be async via Kafka.
- 13 PB of media → object storage (S3-class), not filesystem.
- 3.5 GB/s egress → CDN offload essential (target 95%+ hit rate).

This is what the interviewer wants to see: not the math itself, but the way the math constrains the design.

---

## ASCII Architecture Diagrams

### 1. The High-Level "Boxes and Arrows" Pattern

```
                  ┌─────────────────────────────────────────────────┐
                  │                  Clients                        │
                  │   (Mobile app, Web SPA, partner integrations)   │
                  └────────────────────────┬────────────────────────┘
                                           │
                                           ▼
                  ┌─────────────────────────────────────────────────┐
                  │  DNS / Anycast → CDN → L4 LB → L7 Gateway      │
                  │  (TLS, auth, rate limit, request tracing)       │
                  └────────────────────────┬────────────────────────┘
                                           │
                                           ▼
                  ┌─────────────────────────────────────────────────┐
                  │   Stateless API services (auto-scaled fleet)    │
                  │   Service A │ Service B │ Service C             │
                  └──┬───────────────┬───────────────┬──────────────┘
                     │               │               │
                     ▼               ▼               ▼
              ┌───────────┐    ┌───────────┐    ┌───────────┐
              │  Cache    │    │  Primary  │    │  Object   │
              │  (Redis)  │    │  DB +     │    │  Store    │
              │           │    │  Replicas │    │  (S3)     │
              └───────────┘    └───────────┘    └───────────┘
                                           ▲
                                           │
                                  ┌────────┴─────────┐
                                  │ Async workers    │
                                  │ fed by Kafka /   │
                                  │ SQS queue        │
                                  └──────────────────┘
```

This is the canonical "five boxes" layout. Every system design fits into it. The interview value is in recognizing which boxes the problem actually requires.

### 2. Time-Boxed Flow of a System Design Interview

```
   0 min ───────► 5 min ──────► 20 min ─────► 40 min ───► 45 min
     │              │              │              │           │
     ▼              ▼              ▼              ▼           ▼
   Scope         High-level      Deep dive       Wrap-up     Exit
   (ask)         (boxes &        (1-3 critical   (recap,
                  arrows)         components)     bottlenecks,
                                                 follow-ups)

   Goal:        Goal:           Goal:           Goal:
   Anchor       Anchor the      Show trade-off   Strong close
   requirements conversation    reasoning       & openness
```

This sequence is what the interviewer is mentally tracking. If you spend 15 minutes on Step 1, you have failed the structure even if your scope was perfect.

### 3. Decision Tree: Choosing Storage

```
                              What kind of data?
                                      │
              ┌────────────┬──────────┼──────────┬────────────┐
              ▼            ▼          ▼          ▼            ▼
           Tabular      Graph      Blob      Time-series   Full-text
              │            │          │          │            │
              ▼            ▼          ▼          ▼            ▼
         Relational    Neo4j /    S3 / GCS  InfluxDB /   Elasticsearch /
         (Postgres,    Neptune    (objects)  Timescale   OpenSearch
         MySQL)                            (TSDB)
              │
              │  Need to scale writes?
              ▼
         Sharded (Vitess, Citus,
         or app-level sharding)
              │
              │  Need global strong consistency?
              ▼
         Spanner / CockroachDB
         (cost 5-10x, complexity
         3-5x)
```

Knowing this tree lets you answer "why this database?" with a defensible chain of decisions instead of a default answer.

---

## Trade-off Tables

### Interview Approach: Reactive vs Proactive vs Mixed

| Style | What it looks like | Strengths | Weaknesses | Best for |
|---|---|---|---|---|
| Reactive | Wait for interviewer to drive the conversation | Safe, never goes off-script | Looks passive, weak signal | Mid-level interviews, hostile interviewers |
| Proactive | Drive the entire conversation; make decisions and defend them | Strong ownership signal | Can steamroll the interviewer | Senior+ interviews, when you read strong buy-in |
| Mixed (recommended) | Propose, then ask for feedback; let interviewer redirect | Best signal of collaboration | Requires reading the room | Most interviews |

### Communication Channel: Whiteboard vs Docs vs Code

| Medium | Strengths | Weaknesses | Use when |
|---|---|---|---|
| Whiteboard | Forces high-level thinking, conversation-friendly | Ephemeral, hard to reference later | Most system design interviews |
| Digital doc (Google Docs, Excalidraw) | Persistent, shareable, easy to edit | Tempting to dive into detail | Take-home design exercises |
| Code | Precise, executable | Wrong tool — implementation, not design | Only when the question is about a specific algorithm in context |

### Pre-Drawn Diagrams vs Live Drawing

| Approach | Pros | Cons |
|---|---|---|
| Pre-drawn (bring a tablet) | Looks polished | Cannot adapt to interviewer redirect; signals you rehearsed |
| Live drawing | Adapts in real time, looks authentic | Messy, slower |

The right answer is live drawing. The interviewer's mental model of your thought process is the signal; a polished diagram is noise.

---

## Real-World Case Studies

### 1. Twitter's "Frozen Dessert" Timeline Architecture

In 2012, Twitter's engineering team published a talk describing how they solved the news feed problem at scale. The two architectures they called "the frozen dessert" (pull model) and "the sundae" (push model) became reference designs for the industry. The pull model assembled feeds at read time by querying posts from followed accounts. It was cheap on writes but expensive on reads — every timeline fetch touched N users' posts. The push model precomputed timelines at write time. Cheap on reads but a single celebrity tweet triggered millions of fanout writes. Twitter ultimately settled on a hybrid: push for normal users, pull for celebrities, with a "Big Bird" threshold above which accounts switched to pull. The interview lesson: the right answer is rarely pure push or pure pull — it is a hybrid driven by workload shape.

### 2. Stripe's Idempotency-Key Design

Stripe famously lets clients retry the same payment safely by attaching a client-generated idempotency key. Internally, every state-changing API stores the request hash + response for ~24 hours. If a retry arrives with the same key, Stripe returns the cached response instead of charging the card twice. This is the single most cited interview design — and rightly so. It demonstrates:
- Why at-least-once delivery + idempotent handlers is the realistic contract.
- Why client cooperation (the key) is often necessary because the server cannot deduplicate by content alone.
- Why state must outlive the request that created it.

The lesson for the framework: a good design surfaces the failure modes (duplicate requests, network retries, mobile reconnects) explicitly and addresses them with named mechanisms, not hand-waving.

### 3. Discord's Trillion-Message Storage Migration

Discord publicly documented migrating trillions of messages from MongoDB to Cassandra, then later to ScyllaDB. The driver was operational pain: their MongoDB cluster had grown to thousands of shards, each with its own operational quirks, and the cost of even simple schema changes had become prohibitive. They chose the new datastore not because Cassandra was intrinsically "better" but because its write model and partition key design matched their access pattern (fetch messages by channel, in time order). The interview lesson from this: the right database is the one whose access patterns align with your data model. When you find yourself fighting the database, the answer is usually migration, not more nodes.

### 4. Uber's Ringpop / gRPC Service Mesh

Uber's growth from hundreds to thousands of microservices forced them to solve the service-discovery problem at scale. Their solution, Ringpop, used a consistent-hashing ring of nodes, each node gossiping membership state to its neighbors. Every request could be routed to the owning node via the ring in O(1) hops. Uber later migrated much of this to a more standard gRPC + Envoy stack, but the principles — eventual consistency in membership, gossip for state propagation, hash-based routing — are the canonical interview answer for "how do services find each other." Lesson for the framework: when you reach for a service mesh in the interview, name the problem it solves (mTLS, retries, observability) instead of cargo-culting the technology.

### 5. Cloudflare's Edge Rate Limiter

Cloudflare operates one of the largest distributed rate limiters in the world, processing tens of millions of requests per second at the edge. Their system uses a sliding-window counter algorithm (see Chapter 5) maintained in a shared key-value store, with decisions made at the closest edge location. Counters eventually propagate to other edges for consistency. The interview lesson: when you describe a rate limiter in an interview, name Cloudflare's approach explicitly — "I'd use a sliding window counter at the edge, with counters in a globally distributed KV store, accepting eventual consistency for ~1 second." It signals you have read about production systems, not just textbook examples.

---

## Common Pitfalls & Failure Modes

### Pitfall 1: Jumping Into a Design Without Scoping

The most common failure mode. The candidate hears "design Twitter" and immediately starts drawing a web server, then a database, then a cache — without knowing whether the question is about the timeline, search, notifications, or media uploads. The interviewer watches 20 minutes of work that does not address the actual question. The fix: 3-10 minutes of explicit scoping questions, every time, even when the problem seems obvious.

### Pitfall 2: Spending the Whole Time on Step 2

Candidates often produce a beautiful high-level diagram and then run out of time before the deep dive. The diagram is 20% of the value; the reasoning that follows is 80%. If you have 25 minutes left and a blank deep-dive section, you have failed the structure. The fix: time-box the diagram explicitly. Set a 12-minute hard limit on Step 2.

### Pitfall 3: Drowning the Interviewer in Detail

The opposite failure: candidates dive into the deep dive on a single component (say, the database sharding strategy) and never come back up. They describe consistent hashing, virtual nodes, replication factors, and quorum reads while the interviewer politely waits for them to surface. The fix: every 2 minutes of detail, pause and ask "is this the area you want me to go deeper on, or should I move on?" Use the interviewer as a guide.

### Pitfall 4: Failing to Name Trade-offs

Candidates often describe a single design as if it were the only answer. "We will use Cassandra. We will use Kafka. We will use Redis." Each of those is a defensible choice, but presenting them as defaults signals inexperience. The fix: name 2-3 alternatives and explain why you chose the one you did. "Cassandra gives us multi-region writes at the cost of weaker consistency; for this workload, we accept that trade-off because…"

### Pitfall 5: Not Closing

Candidates finish the deep dive and just stop talking, waiting for the interviewer to dismiss them. The wrap-up step exists for a reason: it converts a complete design into a thoughtful engineer. The fix: always close with a one-sentence recap, a named bottleneck, and an open question. It takes 60 seconds and dramatically improves the interviewer's last impression.

### Pitfall 6: Designing in a Vacuum

"You have infinite engineers and infinite money" is not real. Every design choice has an operational cost. A 5-shard MongoDB cluster with strong consistency sounds great until you remember someone has to migrate the schema, back up the data, page when it breaks at 3 AM, and explain to the CTO why it's costing $200K/month. Senior engineers think about who owns the system, not just what the system does. The fix: name operational concerns in the wrap-up step.

### Pitfall 7: Refusing to Push Back

If the interviewer gives you an obviously wrong constraint, the wrong answer is to silently work around it. The right answer is to flag it: "If we genuinely cannot cache anything, then we cannot hit our latency target with this data volume — could we relax the no-cache rule, or is this a hard constraint?" Pushing back is a senior behavior. Accepting obviously broken premises is not.

---

## Interview Q&A

### Q1: "How do you decide when to stop asking scoping questions and start designing?"

**Answer sketch:** When you can answer four questions: who are the users (and roughly how many), what are the 2-3 critical features, what is the workload shape (QPS, storage, bandwidth), and what are the hard constraints (latency, consistency, compliance). After that, additional questions are diminishing returns. In a 45-minute interview, aim for 5 minutes of scoping, then commit to the design.

### Q2: "What if the interviewer gives you a problem you have never seen?"

**Answer sketch:** Treat it as a decomposition problem, not a recall problem. State what you know (similar systems), what you don't know (specific requirements), and ask 3-5 scoping questions. Then describe the system as the four canonical tiers: edge, gateway, stateless services, stateful stores, plus async messaging. Fill in the boxes based on the workload. Even if you have never designed a parking reservation system, you can describe it as "read-heavy workload with strong consistency requirements at write time, bounded by physical capacity of parking lots."

### Q3: "How do you handle the deep-dive if you don't know the specific technology?"

**Answer sketch:** Be honest about the limits of your knowledge, then describe the trade-off space. "I have not used Kafka in production, but I know the design space: durable log, partitioned, ordered within partition, at-least-once delivery, consumer offsets. Given our workload — high throughput, partitioned by user — Kafka is the right shape, and a managed service like Confluent Cloud would let us avoid operational burden." This signals both honesty and architectural thinking.

### Q4: "Your design has a bottleneck. How do you find it without running a load test?"

**Answer sketch:** Walk through each tier and identify the one with the lowest headroom. For most designs that is the database (write QPS, replication lag) or the message queue (consumer lag). Use back-of-envelope math: at 10x traffic, which tier exceeds its capacity first? That is your bottleneck. The interview version is "if traffic 10x's, the fanout workers become the bottleneck because they scale linearly with followers — I'd address this with hybrid fanout and dedicated queues for high-fanout accounts."

### Q5: "How do you decide between a monolithic service and microservices in the interview?"

**Answer sketch:** Default to a monolith with internal module boundaries, unless the workload clearly demands separation. Microservices buy you independent deploys and scaling at the cost of network reliability, distributed transactions, and operational complexity. In an interview, name the threshold: "with 5 engineers and 100 K DAU, a monolith is correct. With 50 engineers and 100 M DAU, we need service boundaries aligned to bounded contexts."

### Q6: "What if the interviewer is silent for 30 seconds?"

**Answer sketch:** Treat silence as a signal to keep talking — specifically, to verbalize your reasoning. "I am choosing this database because the access pattern is point reads by primary key, and the volume here is small enough that a single Postgres instance will work for the next 12 months." Silence is rarely the interviewer disagreeing; usually they are waiting to see if you will defend your choice or change it without justification.

### Q7: "How do you handle a 60-minute interview that ran out of time at the high-level design?"

**Answer sketch:** Acknowledge the truncation explicitly: "I have spent too long on the high-level design. Here is what I would deep-dive on next: the feed assembly path and the cache invalidation strategy. The other components would use standard patterns." This is a senior move — showing you know what matters most, even under time pressure.

---

## Key Terms / Glossary

| Term | What people say | What it actually means |
|---|---|---|
| Scope | "What we are building." | The set of features, scale assumptions, and constraints you agree with the interviewer to design for. Always negotiated, never assumed. |
| High-level design | "The architecture diagram." | A simplified box-and-arrow sketch that anchors the conversation. Should take 10-15 minutes to produce, not 25. |
| Deep dive | "The detailed design." | Detailed treatment of 1-3 components identified as critical. Demonstrates trade-off reasoning and operational awareness. |
| Trade-off | "The pros and cons." | A decision where improving one dimension worsens another (latency vs consistency, cost vs durability). Senior engineers name them explicitly. |
| Bottleneck | "The slow part." | The single tier or component that will fail first under load. Identifying it is the most common follow-up question in interviews. |
| Bounded context | "A microservice." | A domain-driven-design term for the boundary within which a single model is consistent. The unit at which you split microservices. |
| Idempotency | "Safe to retry." | An operation that can be applied multiple times without changing the result beyond the first application. Critical for at-least-once delivery. |
| Fanout | "Distribute to many." | The cost of delivering one piece of content to N recipients. Fanout-on-write (push) vs fanout-on-read (pull) is one of the most common interview choices. |
| Back-of-envelope | "Rough math." | Order-of-magnitude reasoning that constrains a design before any code is written. Anchors the design in concrete workload shape. |
| Whiteboard | "Where I draw." | A physical or digital surface for sketching designs. The format forces high-level thinking; perfectionism is a sign of weakness here. |
| Hot path | "Synchronous critical request." | The part of the system that must respond within the user-facing latency budget (typically 100-300 ms). Everything off the hot path can be async. |
| Cold path | "Background work." | Async processing that does not need to complete within the user's request. Allows batching, retries, and graceful degradation. |

---

## Key Takeaway

System design interviews assess "ability to collaborate, to work under pressure, and to resolve ambiguity constructively." Success requires balancing technical depth, communication clarity, and pragmatic trade-off decisions while remaining responsive to interviewer feedback throughout the session.

The framework is a tool, not a script. Use it to stay on track and demonstrate structure, but the strongest signal you can send is engineering judgment — the willingness to make a decision, defend it with named trade-offs, and revise it when given new information. Memorize the four steps; practice the deep dive; relax into the wrap-up. The rest is conversation.