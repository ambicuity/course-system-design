# Top 20 AI Agent Concepts You Should Know

> Twenty terms that separate people who use AI agents from people who build them — with concrete definitions, not buzzwords.

**Type:** Learn
**Prerequisites:** What is an AI Agent?, Types of AI Agents, LLM Fundamentals
**Time:** ~30 minutes

---

## The Problem

The AI agent vocabulary is a swamp. Every vendor uses "agent," "workflow," "copilot," and "automation" to mean slightly different things. Every framework invents its own terminology for concepts that already have well-established names. Two engineers in the same room can talk about "the agent loop" and mean different processes.

The only way to navigate the swamp is to learn the underlying concepts, not the brand-name labels. Once you know what a *tool*, a *planner*, a *handoff*, and a *swarm* actually mean, you can read any framework's docs in ten minutes — because they all map to the same vocabulary underneath.

This lesson is a glossary of the twenty concepts that come up constantly when building, debugging, or evaluating AI agents. For each, you get the precise definition, why it matters, and what it looks like in code.

---

## The Concept

### The twenty concepts, grouped

The concepts fall into five clusters:

```
   1. The agent itself      →  agent, environment, perception, state, memory, LLM
   2. Reasoning & action    →  reflex, knowledge base, CoT, ReAct, tools, action
   3. Planning              →  planning, orchestration, handoffs
   4. Multi-agent patterns  →  multi-agent system, swarm, agent debate
   5. Operations            →  evaluation, learning loop
```

We will walk through each cluster.

---

### Cluster 1: The agent itself

These are the foundational concepts — without them, nothing else makes sense.

**1. Agent.** An autonomous entity that perceives, reasons, and acts in an environment to achieve goals. The full definition is in chapter 07; the short version is: it has autonomy, perception, reasoning, tool use, and memory, and runs in a closed loop.

**2. Environment.** The surrounding context or sandbox in which the agent operates. For a customer support agent, the environment is the ticketing system, the customer database, the Slack channels, the agent's own memory. For a coding agent, the environment is the file system, the terminal, the test runner, and the Git repo. The environment defines what the agent can perceive and what its actions affect.

```python
# Environment definition for a coding agent
environment = {
    "filesystem": "/repo",
    "shell": subprocess,
    "git": git_client,
    "tests": pytest_runner,
    "memory": vector_store,
}
```

**3. Perception.** The process of interpreting sensory or environmental data to build situational awareness. For an LLM agent, "perception" means parsing the user's message, reading tool responses, retrieving relevant memory, and turning all of that into the next prompt.

```python
def perceive(user_message, last_tool_results, retrieved_memory):
    return {
        "goal": extract_goal(user_message),
        "context": last_tool_results + retrieved_memory,
        "constraints": extract_constraints(user_message),
    }
```

**4. State.** The agent's current internal condition — what it knows, what it has tried, where it is in its plan. State is what gets passed from one step of the agent loop to the next.

```python
class AgentState(TypedDict):
    messages: list       # full conversation history
    plan: list[str]      # remaining steps to execute
    scratchpad: dict     # intermediate results
    retry_count: int     # how many times we've retried the last step
```

**5. Memory.** Storage of recent or historical information for continuity and learning. Three tiers: short-term (the conversation buffer, in-context), long-term episodic (specific past interactions, retrieved by similarity), long-term semantic (distilled facts about the user, stored compactly).

```python
# Three memory tiers
memory = {
    "short_term": conversation_buffer[-10:],     # last 10 turns
    "episodic":   semantic_search(past_sessions), # relevant past interactions
    "semantic":   {                               # distilled facts
        "user_name": "Alex",
        "preferred_tone": "terse, code-first",
        "account_id": 42,
    },
}
```

**6. Large Language Models.** Foundation models powering language understanding and generation. In an agent, the LLM is the reasoning engine — it is what decides what to do next. It is one of the six layers of an agent stack, not the whole stack.

---

### Cluster 2: Reasoning and action

These are the moving parts inside the agent loop.

**7. Reflex Agent.** A simple type of agent that makes decisions based on predefined "condition-action" rules. No memory, no planning. Useful for narrow, well-defined sub-tasks within a larger agent (e.g., "if the user said 'cancel,' route to the cancel-subscription skill").

**8. Knowledge Base.** Structured or unstructured data repository used by agents to inform decisions. In a RAG-augmented agent, the knowledge base is the vector store + document corpus. In a tool-using agent, the knowledge base includes the tool catalog and the agent's documentation of what each tool does.

**9. Chain of Thought (CoT).** A reasoning method where agents articulate intermediate steps for complex tasks. Instead of jumping from question to answer, the model writes out its reasoning: "First, I need to find X. Then, given X, I can compute Y. Finally, I can answer Z." CoT dramatically improves accuracy on multi-step problems with no architectural change — just a prompt that says "think step by step."

```python
prompt = """Solve this problem step by step.
Show your reasoning before giving the final answer."""
```

**10. ReAct.** A framework that combines step-by-step reasoning with direct environmental actions. The pattern alternates: **Thought** (reason about what to do) → **Action** (call a tool) → **Observation** (read the result) → repeat. ReAct is the dominant LLM agent pattern.

```
   Thought: I need to find the user's last invoice.
   Action:  search_invoices(customer_id=42)
   Observation: Found 3 invoices. Latest is INV-2024-001.
   Thought: Now I need to get the PDF for INV-2024-001.
   Action:  get_invoice(invoice_id="INV-2024-001")
   Observation: { pdf_url: "...", amount: 1500 }
   Thought: I have what I need. Reply to the user.
```

**11. Tools.** APIs or external systems that agents use to augment their capabilities. Tools are the agent's hands — without them, the agent can only generate text. Tools come in many forms: function calls, MCP servers, REST APIs, code execution sandboxes, browser automation.

**12. Action.** Any task or behavior executed by the agent as a result of its reasoning. In a tool-using agent, an action is usually a structured tool call. In a conversational agent, an action might be emitting a message.

---

### Cluster 3: Planning

When the agent has more than one step to take, planning enters the picture.

**13. Planning.** Devising a sequence of actions to reach a specific goal. Two common variants:

- **Plan-and-Execute:** generate the entire plan up front, then execute each step. Easier to debug, but rigid — if step 3 fails, you may need to replan.
- **Reactive (ReAct-style):** generate one step at a time, observe the result, decide the next step. More flexible, but harder to reason about overall progress.

```python
# Plan-and-Execute
plan = planner.create_plan(goal)        # ["search flights", "compare prices",
                                        #  "book cheapest", "email itinerary"]
for step in plan:
    result = execute(step)
    if failed(result):
        plan = planner.replan(goal, history)
```

**14. Orchestration.** Coordinating multiple steps, tools, or agents to fulfill a task pipeline. The orchestrator owns the loop: when does each step run, what happens when one fails, how is state passed between steps. LangGraph, Airflow, Temporal, and n8n are all orchestrators — at different levels of abstraction.

**15. Handoffs.** The transfer of responsibilities or tasks between different agents (or between an agent and a human). Handoffs are how multi-agent systems divide work: the triage agent hands off to the billing agent, which hands off to the escalation human when the issue exceeds its authority.

```python
# Handoff pattern in a multi-agent system
def triage_agent(customer_request):
    if "billing" in customer_request:
        return handoff(to="billing_agent", context=customer_request)
    if "technical" in customer_request:
        return handoff(to="tech_agent", context=customer_request)
    return handoff(to="human_agent", context=customer_request)
```

---

### Cluster 4: Multi-agent patterns

When one agent cannot hold the full task in its head, you split it across multiple.

**16. Multi-Agent System.** A framework where multiple agents operate and collaborate in the same environment. Each agent typically has a specialized role (planner, researcher, writer, reviewer) and a defined interface to other agents. Communication is via messages, shared state, or handoffs.

```
   Planner ──► Researcher ──► Writer ──► Reviewer ──► Final output
       ▲                                              │
       └──────────── feedback / revision ────────────┘
```

**17. Swarm.** Emergent intelligent behavior from many agents following local rules without central control. Each agent has simple local rules; complex global behavior emerges from their interaction. Inspired by ant colonies, bird flocks, and similar natural systems. In practice, "swarm" in agent frameworks usually means "many agents running in parallel with no central coordinator" — closer to embarrassingly parallel work distribution than true emergent intelligence.

**18. Agent Debate.** A mechanism where agents argue opposing views to refine or improve outcomes. Useful when a single agent's confidence is unreliable. Two (or more) agents generate competing answers, a judge evaluates them, and the better one wins. Reduces hallucinations and improves robustness on subjective tasks.

```
   Agent A: "The answer is X because ..."
   Agent B: "I disagree. The answer is Y because ..."
   Judge:   "Agent B's reasoning is stronger. Final answer: Y."
```

---

### Cluster 5: Operations

After the agent runs, you have to know whether it worked and how to make it work better.

**19. Evaluation.** Measuring the effectiveness or success of an agent's actions and outcomes. Three layers:

- **Component-level:** retrieval recall, tool-call accuracy, plan quality.
- **End-to-end:** task success rate, answer faithfulness, user satisfaction.
- **Operational:** latency, cost, error rate, escalation rate.

```python
# Evaluation example
eval_dataset = [
    {"input": "...", "expected_answer": "...", "expected_tools": [...]},
    ...
]
results = run_eval(agent, eval_dataset)
print(f"Task success: {results.task_success_rate:.1%}")
print(f"Avg cost: ${results.avg_cost_per_task:.4f}")
print(f"Avg latency: {results.avg_latency_seconds:.1f}s")
```

**20. Learning Loop.** The cycle where agents improve performance by continuously learning from feedback or outcomes. Feedback can come from user thumbs-up/down, downstream task success, or automated graders. The loop closes when the feedback signal is used to update the agent's prompt, tools, model, or memory.

```
   Run agent ──► Observe outcome ──► Score outcome
                                          │
                                          ▼
   Update policy ◄── Aggregate feedback ◄── Store feedback
        │
        ▼
   Next run uses updated policy
```

The learning loop is what separates a static agent (same behavior forever) from an adaptive agent (improves over time). Implementing it well requires an evaluation harness and a feedback pipeline — both of which most teams underinvest in.

---

### Quick reference table

| # | Concept | One-line definition | Common synonym |
|---|---|---|---|
| 1 | Agent | Autonomous entity that perceives, reasons, acts | AI agent |
| 2 | Environment | The world the agent operates in | Context, sandbox |
| 3 | Perception | Interpreting sensory/environmental data | Sensing, parsing |
| 4 | State | The agent's current internal condition | Working memory |
| 5 | Memory | Storage of recent/historical info | Knowledge store |
| 6 | LLM | Foundation model for language tasks | Model, brain |
| 7 | Reflex agent | Rule-based decision maker | If-this-then-that agent |
| 8 | Knowledge base | Data repository for the agent | KB, corpus |
| 9 | CoT | Reasoning by articulating intermediate steps | Step-by-step thinking |
| 10 | ReAct | Interleaved reasoning and acting | Thought-Action-Observation loop |
| 11 | Tools | External systems the agent can call | Functions, APIs |
| 12 | Action | A task executed by the agent | Step, move |
| 13 | Planning | Devising an action sequence | Plan generation |
| 14 | Orchestration | Coordinating steps, tools, agents | Workflow management |
| 15 | Handoffs | Transfer of work between agents/humans | Delegation |
| 16 | Multi-agent system | Multiple collaborating agents | MAS, agent team |
| 17 | Swarm | Many agents with local rules, no central control | Emergent system |
| 18 | Agent debate | Agents argue opposing views to refine outcomes | Adversarial collaboration |
| 19 | Evaluation | Measuring agent effectiveness | Assessment, scoring |
| 20 | Learning loop | Cycle of feedback-driven improvement | Adaptation, training |

---

## Build It / In Depth

### How the concepts compose

Here is how all twenty concepts fit together in a single agent run:

```
   User message arrives
           │
           ▼
   [Perception] ──► Goal + constraints
           │
           ▼
   [Memory retrieval] ──► Relevant past interactions, user facts
           │
           ▼
   [Planning] ──► ["search flights", "compare", "book", "email"]
           │
           ▼
   ┌─── Loop ──────────────────────────────────────────────┐
   │                                                        │
   │  [CoT / ReAct reasoning]                              │
   │         │                                              │
   │         ▼                                              │
   │  [Action: call tool] ──► [Tool executes]              │
   │         │                                              │
   │         ▼                                              │
   │  [Observation: tool result]                            │
   │         │                                              │
   │         ▼                                              │
   │  [State updated] ──► Continue or stop?                 │
   │                                                        │
   └────────────────────────────────────────────────────────┘
           │
           ▼
   [Orchestration] decides next move
           │
           ▼
   [Handoff] to another agent (or to human) if needed
           │
           ▼
   [Evaluation] scores the run
           │
           ▼
   [Learning loop] updates policy/memory/prompt
```

Every labeled box is one of the twenty concepts. An agent run is the orchestration of these concepts through a closed loop, with evaluation feeding back into future runs.

---

### Mini-glossary of related terms you will encounter

| Term | Relation to the 20 concepts |
|---|---|
| **Copilot** | An agent designed to assist a human, with the human in the loop at every step |
| **Autopilot** | An agent that runs without human oversight on a defined task |
| **Agentic workflow** | A workflow whose steps are decided by an agent, not a fixed rule chain |
| **Function calling** | The protocol by which the model emits a structured tool call |
| **MCP** | A standardized protocol for exposing tools to agents |
| **RAG** | Retrieval-augmented generation; an agent pattern that adds knowledge retrieval |
| **Prompt engineering** | Hand-tuning the system prompt to improve agent behavior |
| **Prompt optimization** | Automated tuning of prompts using feedback (DSPy, TextGrad) |
| **Constitutional AI** | Training or prompting the agent against a written set of principles |
| **Sandboxing** | Restricting the agent's tools to a safe environment during testing |

These are not on the top-20 list because they are either synonyms, specific implementations, or higher-level patterns composed from the 20. Knowing the 20 means you can decode any of these in context.

---

## Common Pitfalls

- **Treating the list as a checklist.** You do not need all twenty concepts in every agent. Most agents use ten or fewer. The list is vocabulary, not a shopping list.

- **Confusing similar concepts.** Memory vs state. Planning vs orchestration. ReAct vs CoT. Each has a precise meaning; conflating them produces confused designs.

- **Inventing new terms.** If a concept fits one of the twenty, use the existing term. Custom vocabulary makes it harder for new team members to learn your system.

- **Ignoring the operational concepts.** Evaluation and the learning loop are the difference between an agent that plateaus and one that improves. Teams that skip these ship agents that quietly degrade over time.

- **Over-applying multi-agent patterns.** Multi-agent systems, swarms, and agent debate add coordination overhead. Most problems are better solved by a single well-tuned goal-based agent.

- **Forgetting the basics.** CoT, ReAct, and tool use are the workhorses. Fancy multi-agent patterns are useless if the foundation is broken.

---

## Exercises

1. **Easy** — Pick any three of the twenty concepts. For each, write a one-sentence definition and an example of where it shows up in a real product you have used.

2. **Medium** — Take an agent you have built or used. For each of the twenty concepts, mark whether it is present, absent, or not applicable. Identify which concepts you would add to improve the agent's capability.

3. **Hard** — Design a multi-agent customer support system. Map each of the twenty concepts to a concrete component or process in your design. Justify any concept you leave out, and explain how the absence of that concept affects the system's capability.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Agent | Any LLM with a prompt | An autonomous system with five properties — perception, reasoning, tool use, memory, and a closed decision loop |
| Environment | Whatever the agent sees | The complete set of systems the agent can perceive and affect — APIs, databases, files, users, other agents |
| Perception | Reading input | Parsing the user's message, reading tool responses, retrieving memory, and assembling the next prompt |
| State | What the agent remembers | The typed object passed between steps of the agent loop — usually messages, plan, scratchpad, and counters |
| Memory | Conversation history | Three tiers: short-term (buffer), long-term episodic (retrieved past interactions), long-term semantic (distilled user facts) |
| ReAct | The only agent pattern | A specific loop interleaving Thought, Action, and Observation; one of several patterns, but the most common |
| Planning | Figuring out what to do | Generating a sequence of actions to reach a goal, either up front (Plan-and-Execute) or reactively (ReAct) |
| Orchestration | Running the agent loop | The runtime that owns the loop, the state, the tool dispatch, and the termination logic |
| Handoff | Passing the task | A structured transfer of work from one agent (or a human) to another, with context attached |
| Evaluation | Checking the answer | Multi-layer measurement: component metrics (retrieval, tool-call accuracy), end-to-end (task success, faithfulness), operational (latency, cost) |

---

## Further Reading

- **"Artificial Intelligence: A Modern Approach"** — Russell & Norvig's textbook chapter on intelligent agents defines the foundational vocabulary: https://aima.cs.berkeley.edu/
- **Lilian Weng's "LLM Powered Autonomous Agents"** — a deep dive into planning, memory, and tool use in modern agents: https://lilianweng.github.io/posts/2023-06-23-agent/
- **LangGraph Concepts** — the canonical reference for state, nodes, edges, and orchestration: https://langchain-ai.github.io/langgraph/concepts/
- **ReAct Paper** — the original paper that introduced the Thought-Action-Observation loop: https://arxiv.org/abs/2210.03629
- **DSPy** — a framework that treats prompts as optimizable parameters, the practical implementation of "learning loop" for prompt-based agents: https://dspy.ai