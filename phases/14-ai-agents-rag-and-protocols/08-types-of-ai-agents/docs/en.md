# Types of AI Agents

> Five categories, each a step up in capability — pick the simplest one that solves the problem.

**Type:** Learn
**Prerequisites:** What is an AI Agent?, LLM Fundamentals
**Time:** ~20 minutes

---

## The Problem

Every agent you build sits somewhere on a spectrum from "follows the rules" to "figures it out." A simple thermostat is not the same kind of system as a chess engine, and neither is the same as a robot learning to walk. Conflating them produces over-engineered solutions for simple problems and under-engineered solutions for complex ones.

The classic taxonomy from AI textbooks (Russell & Norvig, others) classifies agents along two axes: how much they know about their environment and how much they plan ahead. That taxonomy still works in the LLM era, even though the underlying machinery has changed. Reflex agents map to simple if-this-then-that prompts. Goal-based agents map to ReAct-style loops. Utility-based agents map to LLM-as-judge evaluation. Learning agents map to fine-tuning and online feedback loops.

This lesson walks through the five types, gives you a clear mental model for each, and shows when each one fits — and when you should reach for the next type up.

---

## The Concept

### The five types at a glance

```
   Simple              Model-based           Goal-based           Utility-based        Learning
   Reflex              Reflex                                     (with trade-offs)    Agents
   ┌─────────┐         ┌─────────┐           ┌─────────┐         ┌─────────┐          ┌─────────┐
   │ Sensor  │         │ Sensor  │           │ Sensor  │         │ Sensor  │          │ Sensor  │
   └────┬────┘         └────┬────┘           └────┬────┘          └────┬────┘          └────┬────┘
        ▼                   ▼                     ▼                    ▼                     ▼
   ┌─────────┐         ┌─────────┐           ┌─────────┐         ┌─────────┐          ┌─────────┐
   │ IF-THEN │         │  World  │           │ Planner │         │Utility  │          │ Learner │
   │  rules  │         │  model  │           │ (model) │         │function │          │(feedback│
   └────┬────┘         └────┬────┘           └────┬────┘          └────┬────┘          └────┬────┘
        ▼                   ▼                     ▼                    ▼                     ▼
   ┌─────────┐         ┌─────────┐           ┌─────────┐         ┌─────────┐          ┌─────────┐
   │ Action  │         │ Action  │           │ Action  │         │ Action  │          │ Action  │
   └─────────┘         └─────────┘           └─────────┘         └─────────┘          └─────────┘
   "If hot,            "If I turn             "If I move           "Among plans         "I got a
    turn on              off the fan,           here, I will        that achieve         low score
    the fan."            temp will              reach the           the goal, this       last time,
                         drop in                goal."              one has the          adjust the
                         5 min."                                    best trade-          weights."
                                                                     off."
```

Each type adds one new capability to the previous one. The progression is also the order of design complexity — start at simple reflex, add complexity only when the simpler model fails.

---

### Type 1: Simple Reflex Agents

**Behavior:** match the current percept to a rule, fire the corresponding action. No memory, no reasoning about the future.

```
   Percept → Condition → Action
   "Temperature is 30°C" → "temperature > 25" → "Turn on fan"
```

**Properties:**
- Stateless — every decision is made from the current input alone.
- Deterministic — same input always produces same output.
- Fast — a single pattern match.
- Brittle — fails on inputs the rules did not anticipate.

**Modern LLM equivalent:** A system prompt with rigid instructions and a constrained output schema. "If the user asks about X, respond with Y. Otherwise, respond with Z."

**Fits when:**
- The input space is narrow and fully enumerated.
- Decisions are independent (one does not affect the next).
- Latency must be near-zero.
- You cannot afford the cost or non-determinism of an LLM.

**Examples:**
- Email auto-responder that replies to known subjects with canned answers.
- Form validator that rejects malformed inputs.
- Chatbot that routes known intents to human agents and falls back on everything else.

---

### Type 2: Model-based Reflex Agents

**Behavior:** maintain an internal model of the world, update it with each new percept, then choose actions based on the model state — not just the current percept.

```
   Percept → Update internal model → Rule based on model state → Action
```

**Properties:**
- Stateful — remembers what it has perceived.
- Handles partial observability — infers hidden state from what it can see.
- Still reactive — does not plan ahead, just reacts based on the current best model.
- More robust than simple reflex when the world has hidden state.

**Modern LLM equivalent:** An agent with short-term memory. The conversation history is the world model; the agent decides what to do based on the model of "what we have talked about so far," not just the latest message.

**Fits when:**
- Decisions depend on history (this is the third time the user asked about the same thing).
- The agent cannot directly observe everything it needs (some information is in past tool calls).
- Rules can be expressed as functions of state, not just current input.

**Examples:**
- Customer support agent that remembers what was tried in this conversation.
- Game-playing agent that tracks piece positions even when they are off-screen.
- Trading agent that maintains a model of current positions and recent fills.

---

### Type 3: Goal-based Agents

**Behavior:** reason about future states. Given a goal, consider possible action sequences and choose the one most likely to reach the goal.

```
   Goal → Consider candidate plans → Choose plan → Execute step → Observe → Repeat
```

**Properties:**
- Forward-looking — considers what will happen, not just what is.
- Search-based — explores possible action sequences.
- Flexible — same state can lead to different actions depending on the goal.
- Slower than reflex agents due to planning overhead.

**Modern LLM equivalent:** This is the dominant LLM agent pattern. The model is given a goal, it generates a plan (or thinks step-by-step), executes a step, observes the result, and decides whether the plan is still on track. ReAct, Plan-and-Execute, and most LangGraph agents are goal-based.

**Fits when:**
- The task has multiple steps.
- The order of steps matters.
- Some actions have dependencies (you cannot book a flight before searching for it).
- The user gives a goal, not a procedure.

**Examples:**
- A research agent that searches, reads, summarizes, then synthesizes.
- A coding agent that reads the codebase, identifies a bug, writes a fix, runs tests.
- A travel agent that searches flights, compares, books, emails the itinerary.

---

### Type 4: Utility-based Agents

**Behavior:** like goal-based, but instead of binary "did I reach the goal," evaluate each outcome on a continuous utility function that captures trade-offs (cost, time, quality, risk).

```
   Goal → Generate candidate plans → Score each on utility → Pick the highest-utility plan
```

**Properties:**
- Handles trade-offs — when no plan reaches the goal perfectly, picks the best compromise.
- Requires a utility function — you must define what "better" means quantitatively.
- Computationally heavier — scoring many candidates is expensive.
- Often combined with goals: reach the goal *and* minimize cost.

**Modern LLM equivalent:** LLM-as-a-judge. Generate multiple candidate answers (or plans), have the model score them on a rubric (relevance, accuracy, tone, brevity), and pick the best. Also: agents that optimize for cost, latency, or token usage alongside task completion.

**Fits when:**
- There is no single correct answer.
- Multiple goals compete (cheapest vs fastest vs highest quality).
- You can express "good" as a function of measurable properties.

**Examples:**
- An agent that picks the cheapest flight that meets constraints, not just any flight.
- A summarization agent that picks the most faithful summary from N candidates.
- A coding agent that picks the most efficient solution from N approaches.

---

### Type 5: Learning Agents

**Behavior:** improve over time by observing the consequences of past actions and adjusting the policy.

```
   Performance element ──► Critic ──► Learning element ──► Policy update
   (does the action)        (scores    (modifies the        (changes the
                             outcome)   agent's behavior)   decision rules)
```

**Properties:**
- Adaptive — gets better (or worse) with experience.
- Requires feedback signal — explicit rewards, user thumbs-up/down, or downstream task success.
- Can be expensive — every interaction may update the model.
- Risk of regression — feedback loops can drift the agent away from good behavior.

**Modern LLM equivalent:** Fine-tuning on user feedback (DPO, RLHF), prompt optimization (DSPy, TextGrad), online evaluation pipelines that update prompts or model selection based on production traces. Also: agents that store successful action sequences in memory and replay them on similar future tasks.

**Fits when:**
- The task has high volume and clear feedback signal.
- Hand-written rules plateau in quality.
- You have an evaluation harness to measure improvement.
- You can afford the cost of periodic fine-tuning or prompt updates.

**Examples:**
- A customer support agent that learns from thumbs-up/down on its answers.
- A code-review agent that improves at finding bugs in your codebase over time.
- A recommendation agent that learns from click-through data.

---

### The progression

Each type strictly subsumes the previous one:

```
   Simple Reflex  ⊂  Model-based Reflex  ⊂  Goal-based  ⊂  Utility-based  ⊂  Learning
```

A learning agent can act as a goal-based agent. A goal-based agent can act as a model-based reflex. But each additional capability adds complexity, cost, and failure modes. The art is matching the simplest type that solves the actual problem.

---

### When each type fits

```
   Problem characteristics                         Reach for
   ─────────────────────────────────────────       ──────────────
   Narrow inputs, fully enumerated rules          Simple reflex
   Decisions depend on history                    Model-based reflex
   Multi-step task with a clear goal              Goal-based
   Multiple competing objectives                  Utility-based
   Volume + feedback + plateau in hand rules      Learning
```

---

## Build It / In Depth

### Same task, five implementations

The task: given a customer email, decide what to do with it.

**Simple Reflex (rule-based):**
```python
def handle_email(email):
    if "refund" in email.subject.lower():
        return "forward_to_billing"
    if "bug" in email.subject.lower():
        return "forward_to_engineering"
    return "auto_reply_thanks"
```

**Model-based Reflex (with memory):**
```python
def handle_email(email, history):
    if email.sender in history.vip_customers:
        return "escalate_to_manager"
    if "refund" in email.subject.lower():
        return "forward_to_billing"
    return "auto_reply_thanks"
```

**Goal-based (LLM agent with planning):**
```python
agent = Agent(
    model="claude-sonnet-4-5",
    tools=[search_customer, open_ticket, send_reply, escalate],
    system_prompt="""Resolve the customer's issue end-to-end.
    Goal: customer is satisfied, issue is tracked, no duplicate tickets.""",
)

# The agent decides what to do step by step
agent.run(email.body)
```

**Utility-based (LLM-as-judge):**
```python
candidates = [generate_reply(email, style="formal"),
              generate_reply(email, style="friendly"),
              generate_reply(email, style="concise")]

scores = [judge(reply, rubric={"accurate": 5, "tone": 5, "brevity": 3})
          for reply in candidates]
return candidates[scores.index(max(scores))]
```

**Learning (with feedback loop):**
```python
# Production
reply = handle_email(email)

# Days later, collect feedback
if customer_replied_positively(email.thread_id):
    positive_examples.append((email, reply))
elif customer_replied_negatively(email.thread_id):
    negative_examples.append((email, reply))

# Weekly, retrain
if len(positive_examples) + len(negative_examples) > 1000:
    fine_tune(base_model, positive_examples, negative_examples)
```

Each version is more capable but more expensive to build, run, and maintain.

---

### Mapping types to LLM agent patterns

| Agent type | LLM pattern | How to recognize |
|---|---|---|
| Simple reflex | System prompt with rigid rules, no tool calls | Output is deterministic given input |
| Model-based reflex | Conversation buffer + simple prompt | Decision depends on prior turns |
| Goal-based | ReAct, Plan-and-Execute, LangGraph | Model plans multi-step actions |
| Utility-based | Best-of-N + LLM judge, multi-criteria prompt | Multiple candidates scored and ranked |
| Learning | DPO, RLHF, online prompt tuning | Behavior changes based on production feedback |

If you are using a modern agent framework (LangGraph, AutoGen, CrewAI), you are most likely building a goal-based agent. Adding a judge step makes it utility-based. Adding feedback-driven fine-tuning makes it learning.

---

## Use It

### Choosing by problem shape

| If your task is… | The right type is… |
|---|---|
| Known set of inputs, deterministic responses | Simple reflex |
| Decision depends on conversation history | Model-based reflex |
| Multi-step goal with clear success criteria | Goal-based |
| Multiple valid answers, quality varies | Utility-based |
| High volume + clear feedback signal | Learning |

### Choosing by cost

| Type | Build cost | Run cost | Maintenance |
|---|---|---|---|
| Simple reflex | Very low | Free (no LLM) | Low |
| Model-based reflex | Low | Free (no LLM) | Low |
| Goal-based | Medium | Per-token | Medium |
| Utility-based | Medium-high | 3–10× goal-based (multiple candidates) | Medium |
| Learning | High | Per-token + fine-tuning | High |

A reasonable default for a new AI agent product: start as a goal-based agent with a clear system prompt and a small set of tools. Add utility-based selection only when you need to optimize for non-functional properties (cost, tone). Add learning only when you have a stable feedback signal and a hand-written prompt has plateaued.

---

## Common Pitfalls

- **Defaulting to learning agents.** Most teams do not have the data, evaluation harness, or feedback loops to make learning agents work. A goal-based agent with a well-tuned prompt will outperform a poorly-tuned learning agent.

- **Treating all LLMs as goal-based.** Many LLM applications are really model-based reflex agents with a prompt — they do not actually plan. Conflating the two leads to over-promising ("our agent plans!") and under-delivering.

- **Utility functions that nobody understands.** "Maximize user satisfaction" is not a utility function — it is a wish. A utility function must be measurable, computable, and aligned with what you actually want.

- **No feedback signal for learning agents.** Without a way to score outcomes, the learning element has nothing to learn from. Define the feedback signal before you build the learning loop.

- **Choosing complex types for simple problems.** A simple reflex agent handles 80% of support emails faster, cheaper, and more consistently than a learning agent. Use complexity when the problem demands it.

- **Ignoring the subsumption hierarchy.** A learning agent that has not learned anything yet is worse than a goal-based agent with good rules. Start simpler; add complexity only when the simpler version plateaus.

---

## Exercises

1. **Easy** — Pick a system you use daily (a thermostat, a spam filter, a navigation app). Classify it into one of the five agent types. Justify in two sentences.

2. **Medium** — Take a customer support task: triaging incoming emails. Design all five implementations (simple reflex through learning). For each, write the core decision logic and estimate the build cost, run cost, and expected quality.

3. **Hard** — A fintech company wants to build an investment research agent. The agent reads news, fetches stock prices, reads SEC filings, and produces a recommendation. Walk through which agent type fits best at each stage of the product's lifecycle (MVP, growth, mature). Justify each choice and identify the moment you would graduate from one type to the next.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Simple reflex agent | An AI agent | A rule-based system that maps current input to action via if-then rules; no memory, no planning; the simplest kind of "agent" |
| Model-based reflex agent | A learning agent | A stateful agent that maintains an internal model of the world, updates it with each percept, and chooses actions based on the model — not just the current input |
| Goal-based agent | Any LLM agent | An agent that reasons about future states to find an action sequence that reaches a stated goal; the dominant LLM agent pattern (ReAct, Plan-and-Execute) |
| Utility-based agent | A smarter agent | A goal-based agent that scores multiple candidate plans on a continuous utility function, picking the highest-utility option when no plan perfectly achieves the goal |
| Learning agent | An agent that improves itself | An agent that updates its policy based on observed outcomes; requires a feedback signal and an evaluation harness |
| ReAct | The only agent pattern | A specific goal-based pattern that interleaves Reasoning and Acting in a Thought → Action → Observation loop; one of several agent patterns, not the only one |
| LLM-as-a-judge | A way to evaluate outputs | A utility-based pattern where one LLM scores outputs from another (or itself) on a rubric; enables picking the best of N candidates |
| Subsumption | A theory of mind | The architectural principle that simpler agent types can be entirely contained within more complex ones; a learning agent can act as a goal-based agent, but you pay the cost of the learning overhead |

---

## Further Reading

- **"Artificial Intelligence: A Modern Approach"** — Russell & Norvig's textbook chapter on agent types that defines all five categories: https://aima.cs.berkeley.edu/
- **"What is an AI Agent?"** — the prerequisite lesson in this phase: see chapter 07
- **Lilian Weng's "LLM Powered Autonomous Agents"** — a deep technical breakdown of the ReAct and Plan-and-Execute patterns that modern goal-based agents implement: https://lilianweng.github.io/posts/2023-06-23-agent/
- **DSPy** — a framework for systematic prompt optimization and learning agents that compile prompts from examples: https://dspy.ai
- **"Building Effective Agents"** by Anthropic — research-backed guidance on when agents add value, with examples of each pattern in production: https://www.anthropic.com/research/building-effective-agents