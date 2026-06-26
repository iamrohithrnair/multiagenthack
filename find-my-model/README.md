# Find My Model

Standalone hackathon demo app.

## Run

```bash
npm install
npm run dev -- -H 127.0.0.1 -p 3001
```

Open `http://127.0.0.1:3001`.

Health check:

```bash
curl http://127.0.0.1:3001/api/health
```

## Backend

The Next route streams from the Python backend:

```bash
npm run backend:selfcheck
npm run backend:health
```

Runtime is Python `3.14.5` via `uv` because `3.14.6` is not available locally.

## API Integrations

The backend uses only hosted APIs:

- Tavily search API for external benchmark/news/release research.
- Prometheux REST API:
  - derives org/user from the JWT claims when possible,
  - lists or creates a `find_my_model` project,
  - calls `POST /api/v1/agent/{project_id}/chat` and reads the NDJSON stream.
- ClickHouse Cloud API for service discovery.
- ClickHouse SQL HTTP API when `CLICKHOUSE_PASSWORD` is set.
- Google ADK + Gemini for recommendation reasoning.

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
