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

---

## Time Budget for 45-Minute Interview

| Step | Duration | Purpose |
|------|----------|---------|
| **Step 1** | 3-10 min | Requirement clarification and scope definition |
| **Step 2** | 10-15 min | Blueprint proposal and stakeholder alignment |
| **Step 3** | 10-25 min | Detailed component investigation |
| **Step 4** | 3-5 min | Summary, feedback, and future considerations |

**Note:** Time allocation varies based on problem scope and interviewer priorities. Use as rough guidance only.

---

## Key Takeaway

System design interviews assess "ability to collaborate, to work under pressure, and to resolve ambiguity constructively." Success requires balancing technical depth, communication clarity, and pragmatic trade-off decisions while remaining responsive to interviewer feedback throughout the session.
