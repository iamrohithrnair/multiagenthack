The real problem is:

> **People optimize for benchmarks instead of their actual workload.**

Companies waste thousands (or millions) because they pick:

- GPT-5 when Gemini Flash would have been sufficient.

- Expensive hosted APIs instead of cheap local inference.

- Wrong GPU instances.

- Wrong quantization.

- Wrong context length.

- Wrong provider region.

- Wrong routing strategy.


That's a genuine pain point.

---

# The Pitch

> **"Find my model is the model recommender that benchmarks _your_ workload, not generic benchmarks."**

Instead of asking:

> "Should I use GPT or Claude?"

It asks:

- What are you building?

- Show me 5-20 real prompts.

- What latency do users expect?

- How many requests/day?

- Structured output?

- Long context?

- Vision?

- Tool calling?

- Budget?

- Privacy requirements?

- Can you self-host?

- Geographic constraints?


Then it automatically tests and recommends:

- Model

- Provider

- Hardware

- Routing strategy

- Estimated monthly cost

- Expected latency

- Expected quality


---

# Why this is novel

Everyone compares models like this:

| Model | MMLU | SWE | Arena |

Nobody actually asks:

> **"For MY chatbot with MY prompts, what's cheapest while maintaining 95% quality?"**

That's the gap.

---

# Demo Flow

This is what judges should experience.

---

## Step 1

Landing page

> **Stop choosing AI models from Twitter benchmarks.**

Button:

> Analyze My AI Workload

---

## Step 2

Conversation

Agent:

> What are you building?

User:

> Customer support chatbot.

---

Agent

How many users?

User

500/day

---

Agent

Maximum acceptable latency?

User

3 seconds

---

Agent

Budget?

User

<$300/month

---

Agent

Can you run GPUs?

User

Yes

---

Agent

Upload 10 real prompts.

User uploads JSON.

---

## Step 3

Agent automatically starts.

Now this is where Prometheux shines.

The agent:

- Opens OpenRouter

- Opens Together

- Opens Fireworks

- Opens Groq

- Opens Cerebras

- Opens DeepInfra

- Opens Google AI Studio

- Opens Anthropic pricing

- Opens OpenAI pricing


Collects:

- latest prices

- limits

- context windows

- supported features

- hardware availability


No hardcoding.

---

## Step 4

Tavily

Searches

- recent benchmark reports

- latest releases

- provider outages

- Reddit discussions

- pricing changes

- inference benchmarks


---

## Step 5

ClickHouse

Stores

Every benchmark

Every prompt

Latency

Cost

Output

Token counts

Hardware

Provider

Version

Over time this becomes a benchmark database.

---

## Step 6

Gemini

This is where context engineering matters.

Don't dump everything.

Instead retrieve

```
User requirements

Sample prompts

Recent provider pricing

Relevant benchmark history

Hardware options

Latency statistics

Provider reliability

Routing constraints
```

Gemini reasons

instead of searching.

---

# Then the magic

Instead of

> GPT is best.

It says

```
Recommendation

80%

Gemini Flash

Reason

Your prompts are simple classification tasks.

Average latency

0.8s

Monthly cost

$21

Quality score

95%
```

Then

```
Fallback

Claude Sonnet

for prompts exceeding 50k tokens
```

Then

```
Large coding requests

Route to DeepSeek R1
```

Then

```
Vision

Use GPT-4.1 Vision only when images exist.
```

Suddenly you've designed an inference router.

---

# Even cooler

Don't recommend ONE model.

Recommend a graph.

```
               Incoming Request
                      │
        ┌─────────────┴─────────────┐
        │                           │
 Vision?                      Coding?
        │                           │
 GPT-4.1 Vision          DeepSeek R1
        │                           │
        └─────────────┬─────────────┘
                      │
           Small prompt?
                      │
           Gemini Flash
                      │
        >50k tokens?
                      │
          Claude Sonnet
```

This is much more enterprise-ready.

---

# Context Engineering (the differentiator)

Everyone sends

```
Prompt

↓

LLM
```

Instead build

```
User Requirements
        │
Sample Prompts
        │
Latency Targets
        │
Budget
        │
Provider Metadata
        │
Historical Benchmarks
        │
Hardware Database
        │
Past Similar Workloads
        │
Retriever
        │
Gemini
```

Gemini only receives the top-k most relevant evidence, keeping the context focused and inexpensive while improving recommendation quality.

---

# How each required tool fits naturally

### Prometheux

The autonomous web agent.

Actions include:

- Visit provider pricing pages.

- Check rate limits.

- Inspect API documentation.

- Navigate GPU cloud pricing pages.

- Compare model availability.

- Capture updated context windows and feature support.


---

### Tavily

Research layer.

Finds:

- Latest model announcements.

- Independent benchmarks.

- Community evaluations.

- Release notes.

- Performance reports.

- API changes.


---

### ClickHouse

The long-term intelligence layer.

Store:

- Every benchmark run.

- Cost history.

- Token usage.

- Latency distributions.

- Hardware configurations.

- User workload fingerprints.

- Historical recommendations.


This lets your system improve over time instead of making each recommendation from scratch.

---

### Gemini Flash

Reasoning layer.

Given structured context, it:

- Classifies the workload.

- Detects dominant task types (coding, summarization, RAG, extraction, vision, agents).

- Explains trade-offs.

- Produces an optimized deployment architecture instead of a single-model answer.


---

# A feature that would really impress judges

Go beyond recommendations and add a **"What if?" simulator**.

After generating the optimal stack, users can adjust sliders such as:

- Budget: $100 → $5,000/month

- Maximum latency: 500 ms → 10 s

- Quality target: 90% → 99%

- Self-hosted vs managed

- Traffic: 100 requests/day → 10 million/day


The system instantly recomputes:

- Best providers.

- Hardware requirements.

- Monthly costs.

- Routing strategy.

- Expected latency and quality impact.


That transforms your project from an advisor into an interactive **AI infrastructure planning tool**, which is both highly demoable and addresses a real, growing problem as organizations struggle to choose among hundreds of rapidly evolving models and providers.
