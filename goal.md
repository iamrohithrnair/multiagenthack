# IDEA:"FIND MY MODEL" APP

## Goal

Build an autonomous AI Infrastructure Architect that helps developers and companies determine the optimal AI deployment strategy for **their specific workload**, rather than relying on generic model leaderboards.

The system should interview the user about their use case, collect representative prompts and context, autonomously research current AI providers and infrastructure, benchmark recommendations against user constraints, and produce a deployable architecture with cost, latency, quality, and routing recommendations.

This is **not** another model comparison website.

It is an **AI agent that acts on the web** to continuously gather the latest provider information and recommends the best combination of:

* AI model(s)
* AI provider(s)
* GPU hardware
* Deployment strategy
* Routing strategy
* Cost optimization

---

# Problem Statement

Today developers choose AI providers using:

* Twitter
* Reddit
* Generic benchmarks
* Old blog posts

These rarely reflect:

* their prompts
* their latency requirements
* their traffic
* their budget
* privacy requirements
* structured outputs
* context length
* multimodal needs
* coding vs reasoning workloads

Companies therefore routinely overpay for inference or choose suboptimal architectures.

This application solves that problem.

---

# High Level User Journey

## 1. Interview

The AI asks questions such as:

* What are you building?
* Who are your users?
* Daily request volume?
* Budget?
* Required latency?
* Required quality?
* Region?
* Can you self-host?
* Privacy requirements?
* Long context?
* Vision?
* Tool calling?
* Streaming?
* Function calling?
* Structured output?

---

## 2. Prompt Collection

User uploads:

* JSON
* CSV
* Markdown
* Text

containing 5–20 representative prompts.

The system automatically categorizes them into:

* coding
* summarization
* extraction
* reasoning
* RAG
* classification
* vision
* agentic workflows
* multimodal

---

## 3. Autonomous Research Agent

The research agent autonomously gathers current information by acting on the web.

Tasks include:

* visiting provider pricing pages
* reading API documentation
* inspecting context windows
* checking model availability
* finding supported features
* checking rate limits
* monitoring benchmark updates
* discovering hardware pricing
* identifying regional availability

The research should not rely on hardcoded values whenever possible.

---

## 4. Benchmark & Context Retrieval

Store historical benchmark information including:

* latency
* throughput
* token cost
* GPU cost
* provider
* model version
* context window
* quality scores
* benchmark history

Retrieve only the most relevant information for the current workload.

---

## 5. AI Reasoning

Instead of dumping every document into the model, retrieve:

* user goals
* workload profile
* representative prompts
* pricing information
* provider capabilities
* historical benchmark data
* similar previous workloads

Only this compressed context should be sent to the reasoning model.

---

## 6. Final Recommendation

Return:

### Primary recommendation

Model

Provider

Hardware

Estimated latency

Estimated monthly cost

Expected quality

Confidence score

---

### Alternative recommendations

Lowest cost

Highest quality

Lowest latency

Self-hosted

Enterprise

Open source

---

### Routing graph

Example:

Incoming Request

↓

Coding

→ DeepSeek

↓

Vision

→ Gemini Vision

↓

Simple Chat

→ Gemini Flash

↓

Large Context

→ Claude

↓

Complex Reasoning

→ Gemini Pro

---

### Monthly Cost Estimator

Estimate costs based on:

* requests/day
* tokens/request
* output length
* concurrency
* provider pricing

---

### Infrastructure Diagram

Generate a deployment architecture showing:

Users

↓

Load Balancer

↓

Inference Router

↓

Multiple AI Providers

↓

Observability

↓

Analytics

---

# Technical Stack

## Frontend

* Next.js 16.2.6
* Node.js 24
* TypeScript
* App Router
* Server Actions
* Streaming UI
* Tailwind CSS
* shadcn/ui

---

## Agent Backend

Google Agent Development Kit (ADK)

Python

Multi-agent architecture

Suggested agents:

* Interview Agent
* Research Agent
* Benchmark Agent
* Recommendation Agent
* Report Generator

Use ADK tool calling for all external integrations.

---

## Primary LLM

Gemini 3.5 Flash (or newer Gemini model) and Gemini 3.5 Live if possible

Responsible for:

* orchestration
* reasoning
* recommendations
* report generation

---

## Required Partner Integrations

### Prometheux

Use for browser automation and web interaction.

Examples:

* visit pricing pages
* inspect documentation
* navigate authenticated portals
* gather structured information

Documentation:
https://docs.prometheux.ai/

---

### Tavily

Use as the web research engine.

Examples:

* benchmark reports
* provider announcements
* pricing changes
* API documentation
* release notes

Documentation:
https://docs.tavily.com/

---

### ClickHouse

Use as the long-term benchmark and telemetry database.

Store:

* benchmarks
* pricing history
* latency history
* recommendations
* prompt fingerprints
* workload fingerprints

Repository:
https://github.com/ClickHouse/ClickHouse

---

### Gemini

Reasoning engine.

Use structured context retrieval rather than sending all collected information.

---

### Langfuse

Use for:

* tracing
* prompt versioning
* evaluations
* tool traces
* latency
* token analytics
* benchmark comparisons

Every agent execution should be traced.

https://langfuse.com/

---

# Context Engineering Requirements

Never send raw search results directly to the model.

Instead create structured retrieval pipelines.

Context should include only:

* workload profile
* user constraints
* representative prompts
* relevant pricing
* relevant benchmarks
* similar historical workloads
* provider capabilities

The prompt should stay under a configurable token budget.

---

# Stretch Goals

* Live provider monitoring
* Benchmark replay
* Prompt quality scoring
* Multi-model routing simulator
* "What if?" budget simulator
* GPU recommendation engine
* OpenRouter support
* LiteLLM integration
* Local model recommendations
* Enterprise deployment recommendations

---

# Acceptance Criteria

## Functional

* User completes interview flow.
* User uploads representative prompts.
* Agent researches providers autonomously.
* Agent uses browser automation rather than static data.
* Tavily provides external research.
* ClickHouse stores benchmark history.
* Gemini reasons over retrieved context.
* Langfuse records every trace.
* Final report includes provider, model, hardware, routing, latency, and cost recommendations.

## Technical

* Next.js 16.2.6 frontend.
* Node.js 24 runtime.
* Python Google ADK backend.
* Streaming responses.
* Typed APIs.
* Clean modular architecture.
* Tool-based agent design.
* Docker Compose for local development.
* Environment-based configuration.

## UX

The complete demo should take under five minutes.

A first-time user should be able to:

1. Describe their workload.
2. Upload prompts.
3. Watch the agent research providers.
4. See live reasoning progress.
5. Receive a production-ready AI infrastructure recommendation.
6. Export the report as Markdown or PDF.

---

# Definition of Done

The project demonstrates a true web-acting AI agent that autonomously researches AI providers, reasons over a user's actual workload, and recommends an optimized AI infrastructure using live information, structured context engineering, persistent benchmark storage, and full observability.
