# Find My Model

Find My Model is a hackathon demo that helps teams choose the right AI model stack for a real workload. The app takes a product URL, use-case prompt, hard requirements, uploaded context/RAG settings, and priority hints, then produces an evidence-cited recommendation instead of blindly picking the newest or most expensive model.

The core idea: the best model is not always the costliest frontier model. Picking a model is a headache because context length, modality support, tool use, latency, pricing, availability, RAG needs, and deployment constraints all interact. This project turns that messy comparison into a grounded workflow with research, ontology, lineage, and a final recommendation.

## What It Does

1. Profiles the submitted workload and prompts.
2. Loads and ranks current model candidates from `models.dev`.
3. Pulls extra provider and product evidence from Hugging Face, Tavily, and Prometheux.
4. Builds a Prometheux ontology for requirements, RAG context, candidate models, and evidence.
5. Builds a separate Prometheux lineage concept showing how input, research, ontology, and recommendation connect.
6. Runs both Prometheux concepts and fetches their populated rows.
7. Uses Google ADK + Gemini to produce a JSON recommendation with citations and hard-filter enforcement.
8. Optionally stores run events in ClickHouse and traces events to Langfuse.

## Technology Usage

- **Next.js 16, React 19, TypeScript**: frontend app and API routes. The UI collects workload details and streams backend events from `/api/run`; `/api/health` exposes integration status.
- **Python 3.14.5 + uv**: backend orchestration runtime. Python handles model ranking, hosted API calls, ontology/lineage generation, telemetry, and self-checks.
- **Google ADK + Gemini**: recommendation agent. The backend defaults to `gemini-2.5-flash` through ADK and can be overridden with `GEMINI_MODEL`. The agent must return grounded JSON and cite evidence/lineage IDs.
- **Prometheux REST API**: research, ontology, and lineage system of record. The app creates or reuses the `find_my_model` project, calls the Prometheux agent for provider research, saves two separate Vadalog concepts, runs them, polls execution status, and fetches output rows:
  - `find_my_model_ontology`
  - `find_my_model_lineage`
- **Vadalog concepts**: represent the ontology and lineage as executable Prometheux logic. Output predicates are explicit derived rules so Prometheux can materialize and fetch them.
- **models.dev**: live model catalog. The backend ranks models by context window, modality support, tool calling, structured output, frontier preference, speed hints, release date, and cost when the user prioritizes cheap options.
- **Hugging Face API**: open-weight candidate discovery for workloads where cost, privacy, deployment, or latency may make open models useful.
- **Tavily Search API**: current external research for pricing, releases, provider pages, benchmark/news context, and product/workload evidence.
- **ClickHouse Cloud API + SQL HTTP API**: optional event storage. Cloud API keys discover the service; SQL credentials enable writing run events to a MergeTree table.
- **Langfuse ingestion API**: optional trace/event logging for observability.
- **RAG context inputs**: the app records selected vector database, connection label, uploaded files, and document/image settings in the ontology and lineage so recommendations account for retrieval needs.

## Prometheux Verification

The Prometheux dashboard/console should show two separate concepts in project `find_my_model`:

- `find_my_model_ontology`
- `find_my_model_lineage`

The ontology is saved as graph triples with fields `Subject`, `Relation`, and `Object`. The lineage is saved separately with fields `Step`, `Source`, `Target`, and `Label`.

The backend follows the documented concept lifecycle:

```text
save concept -> run concept -> poll execution status -> fetch output predicate rows
```

Latest live verification:

- concept save/list works and shows the corrected ontology graph shape
- the full demo backend stream reaches `context_layer`, `recommendation`, and `complete`
- Prometheux run/fetch currently returns `Selected compute resource is not reachable`; once the selected Prometheux compute machine is running, the same app flow will populate/fetch rows

## Run Locally

```bash
npm install
npm run dev -- -H 127.0.0.1 -p 3001
```

Open `http://127.0.0.1:3001`.

Health check:

```bash
curl http://127.0.0.1:3001/api/health
```

Backend checks:

```bash
npm run backend:selfcheck
npm run backend:health
```

Runtime is Python `3.14.5` via `uv`.

## Environment Variables

Required for the full demo:

```bash
GEMINI_API_KEY=...
PROMETHEUX_API_KEY=...
TAVILY_API_KEY=...
```

Optional:

```bash
GEMINI_MODEL=gemini-2.5-flash
PROMETHEUX_PROJECT_ID=find_my_model
PROMETHEUX_BASE_URL=...
PROMETHEUX_ORG=...
PROMETHEUX_USER=...
CLICKHOUSE_API_KEY_ID=...
CLICKHOUSE_API_KEY_SECRET=...
CLICKHOUSE_URL=...
CLICKHOUSE_USERNAME=default
CLICKHOUSE_PASSWORD=...
CLICKHOUSE_DATABASE=default
CLICKHOUSE_TABLE=find_my_model_events
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_HOST=https://cloud.langfuse.com
```

ClickHouse SQL storage is active when one of these is set: `CLICKHOUSE_PASSWORD`, `CLICKHOUSE_DEFAULT_USER_PASSWORD`, or the current `.env` spelling `CLICKHOUST_DEFAULT_USER_PASSWORD`.

ClickHouse Cloud OpenAPI keys can discover the service, but they are not SQL credentials. To allow this app to create the Cloud service query endpoint instead, explicitly set:

```bash
CLICKHOUSE_QUERY_ENDPOINT_AUTO_CREATE=true
CLICKHOUSE_QUERY_ENDPOINT_ALLOWED_ORIGINS=http://localhost:3001
```

Skipped by default because it changes hosted ClickHouse access policy.

Or call the guarded setup route:

```bash
curl -X POST http://127.0.0.1:3001/api/clickhouse/setup \
  -H 'content-type: application/json' \
  -d '{"confirm":"ENABLE_CLICKHOUSE_QUERY_ENDPOINT"}'
```

## Submission Project Details

Choosing an AI model should not mean defaulting to the most expensive frontier model. For many products, the right answer depends on context length, image or audio support, tool calling, latency, data retrieval, deployment constraints, and cost. Find My Model turns that decision into a research-backed workflow.

The app takes a real workload or product idea, profiles the prompts and hard requirements, searches current model/provider evidence, ranks candidates from live catalogs, and then creates a recommendation with citations. Prometheux is used as the system of record for the reasoning context: one populated ontology captures requirements, candidate models, RAG settings, and evidence; a separate populated lineage concept shows how the input and research flow into the final recommendation.

The result is a practical model-selection assistant for builders who want the best fit, not just the biggest model. It helps answer: when do I need a premium frontier model, when is a faster/cheaper model enough, and what evidence supports that choice?
