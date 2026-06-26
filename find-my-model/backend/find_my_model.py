from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types


PROVIDER_PAGES = [
    {"provider": "OpenRouter", "url": "https://openrouter.ai/models"},
    {"provider": "Together", "url": "https://www.together.ai/pricing"},
    {"provider": "Fireworks", "url": "https://fireworks.ai/pricing"},
    {"provider": "Groq", "url": "https://groq.com/pricing/"},
    {"provider": "Cerebras", "url": "https://www.cerebras.ai/pricing"},
    {"provider": "DeepInfra", "url": "https://deepinfra.com/pricing"},
    {"provider": "Google AI", "url": "https://ai.google.dev/gemini-api/docs/pricing"},
    {"provider": "Anthropic", "url": "https://www.anthropic.com/pricing"},
    {"provider": "OpenAI", "url": "https://openai.com/api/pricing/"},
]


def load_env() -> None:
    for env_path in [Path.cwd() / ".env", Path.cwd().parent / ".env", Path(__file__).resolve().parents[2] / ".env"]:
        if not env_path.exists():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def env(*names: str) -> str:
    load_env()
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def jwt_claims(token: str) -> dict[str, Any]:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode())
        return json.loads(decoded)
    except Exception:
        return {}


def emit(event_type: str, data: Any) -> None:
    print(json.dumps({"type": event_type, "data": data, "timestamp": int(time.time() * 1000)}, ensure_ascii=False), flush=True)


def post_json(url: str, body: dict[str, Any], headers: dict[str, str] | None = None, timeout: int = 40) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="ignore")
        raise RuntimeError(f"{url} returned {error.code}: {detail[:800]}") from error


def get_json(url: str, headers: dict[str, str] | None = None, timeout: int = 40) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="ignore")
        raise RuntimeError(f"{url} returned {error.code}: {detail[:800]}") from error


def prometheux_token() -> str:
    token = env("PROMETHEUX_API_KEY")
    if not token:
        raise RuntimeError("missing_PROMETHEUX_API_KEY")
    return token


def prometheux_base_url() -> str:
    explicit = env("PROMETHEUX_BASE_URL").rstrip("/")
    if explicit:
        return explicit
    claims = jwt_claims(prometheux_token())
    org = env("PROMETHEUX_ORG") or str(claims.get("organization") or "")
    user = env("PROMETHEUX_USER") or str(claims.get("username") or "")
    if not org or not user:
        raise RuntimeError("missing_PROMETHEUX_ORG_or_USER")
    return f"https://api.prometheux.ai/jarvispy/{urllib.parse.quote(org)}/{urllib.parse.quote(user)}/api/v1"


def prometheux_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {prometheux_token()}", "Content-Type": "application/json"}


def prometheux_json(path: str, body: dict[str, Any] | None = None, method: str = "POST") -> dict[str, Any]:
    url = f"{prometheux_base_url()}{path}"
    if method == "GET":
        return get_json(url, {"Authorization": f"Bearer {prometheux_token()}"})
    return post_json(url, body or {}, prometheux_headers())


def prometheux_project_id(create: bool = True) -> str:
    explicit = env("PROMETHEUX_PROJECT_ID")
    if explicit:
        return explicit
    project_id = "find_my_model"
    data = prometheux_json("/projects/list?scopes=user", method="GET")
    projects = data.get("data") or []
    for project in projects:
        existing_id = str(project.get("id") or project.get("project_id") or "")
        if existing_id == project_id and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", existing_id):
            return project_id
    if not create:
        return ""
    prometheux_json(
        "/projects/save",
        {"project": {"id": project_id, "name": "Find My Model", "scope": "user", "description": "Provider research project for the Find My Model demo."}},
    )
    return project_id


_CLICKHOUSE_URL: str | None = None
_CLICKHOUSE_STATUS_EMITTED = False


def clickhouse_cloud_request(path: str, method: str = "GET", body: dict[str, Any] | None = None) -> dict[str, Any]:
    key = env("CLICKHOUSE_API_KEY_ID")
    secret = env("CLICKHOUSE_API_KEY_SECRET")
    if not key or not secret:
        raise RuntimeError("missing_CLICKHOUSE_API_KEY_ID_or_SECRET")
    data = json.dumps(body).encode() if body is not None else None
    auth = base64.b64encode(f"{key}:{secret}".encode()).decode()
    request = urllib.request.Request(
        f"https://api.clickhouse.cloud{path}",
        data=data,
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode())


def clickhouse_user_password() -> tuple[str, str]:
    return (
        env("CLICKHOUSE_USERNAME", "CLICKHOUSE_USER") or "default",
        env(
            "CLICKHOUSE_PASSWORD",
            "CLICKHOUSE_SQL_PASSWORD",
            "CLICKHOUSE_DEFAULT_USER_PASSWORD",
            "CLICKHOUST_DEFAULT_USER_PASSWORD",
        ),
    )


def discover_clickhouse_url(emit_status: bool = True) -> str:
    global _CLICKHOUSE_URL, _CLICKHOUSE_STATUS_EMITTED
    if _CLICKHOUSE_URL is not None:
        return _CLICKHOUSE_URL

    explicit = env("CLICKHOUSE_URL", "CLICKHOUSE_HOST").rstrip("/")
    if explicit:
        _CLICKHOUSE_URL = explicit
        return _CLICKHOUSE_URL

    try:
        organizations = clickhouse_cloud_request("/v1/organizations").get("result") or []
        if not organizations:
            raise RuntimeError("no_organizations")
        organization = organizations[0]
        services = clickhouse_cloud_request(f"/v1/organizations/{organization['id']}/services").get("result") or []
        service_id = env("CLICKHOUSE_SERVICE_ID")
        service_name = env("CLICKHOUSE_SERVICE_NAME")
        service = next(
            (
                svc for svc in services
                if (service_id and svc.get("id") == service_id)
                or (service_name and svc.get("name") == service_name)
                or (not service_id and not service_name and svc.get("state") in {"idle", "running", "degraded"})
            ),
            None,
        )
        if not service:
            raise RuntimeError("no_matching_service")
        endpoint = next((item for item in service.get("endpoints", []) if item.get("protocol") == "https"), None)
        if not endpoint:
            raise RuntimeError("no_https_endpoint")
        _CLICKHOUSE_URL = f"https://{endpoint['host']}:{int(endpoint['port'])}"
        if emit_status and not _CLICKHOUSE_STATUS_EMITTED:
            emit("adapter_status", {
                "adapter": "clickhouse",
                "status": "discovered_cloud_service_endpoint",
                "service": service.get("name"),
                "region": service.get("region"),
            })
            _CLICKHOUSE_STATUS_EMITTED = True
        return _CLICKHOUSE_URL
    except Exception as exc:
        if emit_status and not _CLICKHOUSE_STATUS_EMITTED:
            emit("adapter_status", {"adapter": "clickhouse", "status": f"cloud_discovery_failed: {exc}"})
            _CLICKHOUSE_STATUS_EMITTED = True
        return ""


def maybe_upsert_clickhouse_query_endpoint() -> None:
    if env("CLICKHOUSE_QUERY_ENDPOINT_AUTO_CREATE").lower() != "true":
        return
    upsert_clickhouse_query_endpoint()


def upsert_clickhouse_query_endpoint() -> dict[str, Any]:
    key = env("CLICKHOUSE_API_KEY_ID")
    organizations = clickhouse_cloud_request("/v1/organizations").get("result") or []
    if not organizations:
        raise RuntimeError("no_clickhouse_organizations")
    organization = organizations[0]
    services = clickhouse_cloud_request(f"/v1/organizations/{organization['id']}/services").get("result") or []
    service_id = env("CLICKHOUSE_SERVICE_ID")
    service_name = env("CLICKHOUSE_SERVICE_NAME")
    service = next(
        (
            svc for svc in services
            if (service_id and svc.get("id") == service_id)
            or (service_name and svc.get("name") == service_name)
            or (not service_id and not service_name and svc.get("state") in {"idle", "running", "degraded"})
        ),
        None,
    )
    if not service:
        raise RuntimeError("no_matching_clickhouse_service")
    # ponytail: opt-in only; this widens hosted-service API access and should not happen implicitly.
    data = clickhouse_cloud_request(
        f"/v1/organizations/{organization['id']}/services/{service['id']}/serviceQueryEndpoint",
        "POST",
        {
            "roles": [env("CLICKHOUSE_QUERY_ENDPOINT_ROLE") or "sql_console_admin"],
            "openApiKeys": [key],
            "allowedOrigins": env("CLICKHOUSE_QUERY_ENDPOINT_ALLOWED_ORIGINS") or "http://localhost:3001",
        },
    )
    result = data.get("result") or {}
    setup = {
        "status": "query_endpoint_upserted",
        "service": service.get("name"),
        "region": service.get("region"),
        "roles": result.get("roles"),
        "openApiKeyCount": len(result.get("openApiKeys") or []),
        "allowedOrigins": result.get("allowedOrigins"),
    }
    emit("adapter_status", {"adapter": "clickhouse", **setup})
    return setup


def clickhouse_sql(sql: str, body: str = "") -> bool:
    clickhouse_url = discover_clickhouse_url()
    if not clickhouse_url:
        return False

    database = env("CLICKHOUSE_DATABASE") or "default"
    user, password = clickhouse_user_password()
    if not password:
        maybe_upsert_clickhouse_query_endpoint()
        emit("adapter_status", {"adapter": "clickhouse", "status": "sql_password_missing_for_discovered_service"})
        return False
    auth = base64.b64encode(f"{user}:{password}".encode()).decode()
    url = f"{clickhouse_url}/?database={urllib.parse.quote(database)}"
    request = urllib.request.Request(
        url,
        data=(sql + body).encode(),
        headers={"Authorization": f"Basic {auth}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20):
            return True
    except Exception as exc:
        emit("adapter_status", {"adapter": "clickhouse", "status": f"write_failed: {exc}"})
        return False


def clickhouse_probe() -> str:
    clickhouse_url = discover_clickhouse_url(emit_status=False)
    if not clickhouse_url:
        return "inactive"
    user, password = clickhouse_user_password()
    if not password:
        return "needs_sql_password_or_query_endpoint_opt_in"
    auth = base64.b64encode(f"{user}:{password}".encode()).decode()
    url = f"{clickhouse_url}/?query={urllib.parse.quote('SELECT 1')}"
    request = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode(errors="ignore").strip()
            return "active" if body == "1" else f"probe_unexpected_response: {body[:80]}"
    except Exception as exc:
        return f"probe_failed: {exc}"


def integration_status() -> dict[str, Any]:
    clickhouse: dict[str, Any] = {
        "configured": bool(env("CLICKHOUSE_API_KEY_ID") and env("CLICKHOUSE_API_KEY_SECRET")),
        "storage": "inactive",
    }
    try:
        organizations = clickhouse_cloud_request("/v1/organizations").get("result") or []
        organization = organizations[0] if organizations else None
        if organization:
            services = clickhouse_cloud_request(f"/v1/organizations/{organization['id']}/services").get("result") or []
            service = services[0] if services else None
            if service:
                clickhouse.update({
                    "cloudService": service.get("name"),
                    "region": service.get("region"),
                    "state": service.get("state"),
                    "endpointDiscovered": bool(next((item for item in service.get("endpoints", []) if item.get("protocol") == "https"), None)),
                    "storage": clickhouse_probe(),
                })
    except Exception as exc:
        clickhouse["error"] = str(exc)

    prometheux: dict[str, Any] = {"configured": bool(env("PROMETHEUX_API_KEY"))}
    if prometheux["configured"]:
        try:
            project_id = prometheux_project_id(create=False)
            prometheux.update({
                "baseUrlConfigured": bool(env("PROMETHEUX_BASE_URL")),
                "orgUserDiscovered": bool(prometheux_base_url()),
                "projectId": project_id or None,
                "projectReady": bool(project_id),
            })
        except Exception as exc:
            prometheux["error"] = str(exc)

    return {
        "python": sys.version.split()[0],
        "gemini": {"configured": bool(env("GEMINI_API_KEY", "GOOLE_API_KEY", "GOOGLE_API_KEY", "GOOGLE_AI_API_KEY"))},
        "tavily": {"configured": bool(env("TAVILY_API_KEY"))},
        "prometheux": prometheux,
        "clickhouse": clickhouse,
        "langfuse": {"configured": bool(env("LANGFUSE_PUBLIC_KEY") and env("LANGFUSE_SECRET_KEY"))},
    }


class ClickHouseAdapter:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.table = env("CLICKHOUSE_TABLE") or "find_my_model_events"
        self.ready = False
        self.checked = False

    def insert(self, event_type: str, payload: Any) -> None:
        if not self.checked:
            self.ready = clickhouse_sql(
                f"""
CREATE TABLE IF NOT EXISTS {self.table}
(
  run_id String,
  event_type LowCardinality(String),
  created_at DateTime,
  payload String
)
ENGINE = MergeTree
ORDER BY (created_at, run_id)
"""
            )
            self.checked = True
        if not self.ready:
            return
        row = {
            "run_id": self.run_id,
            "event_type": event_type,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "payload": json.dumps(payload, ensure_ascii=False),
        }
        clickhouse_sql(f"INSERT INTO {self.table} FORMAT JSONEachRow\n", json.dumps(row, ensure_ascii=False) + "\n")


class LangfuseAdapter:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.public_key = env("LANGFUSE_PUBLIC_KEY")
        self.secret_key = env("LANGFUSE_SECRET_KEY")
        self.host = (env("LANGFUSE_HOST") or "https://cloud.langfuse.com").rstrip("/")

    def trace(self, name: str, body: Any) -> None:
        if not self.public_key or not self.secret_key:
            return
        auth = base64.b64encode(f"{self.public_key}:{self.secret_key}".encode()).decode()
        event_body = (
            {"id": self.run_id, "name": "find-my-model", "input": body}
            if name == "start"
            else {"traceId": self.run_id, "name": name, "metadata": body}
        )
        post_json(
            f"{self.host}/api/public/ingestion",
            {"batch": [{"id": str(uuid.uuid4()), "type": "trace-create" if name == "start" else "event-create", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "body": event_body}]},
            {"Authorization": f"Basic {auth}"},
            timeout=10,
        )


def clip(text: str, limit: int = 1600) -> str:
    return re.sub(r"\s+", " ", text).strip()[:limit]


def estimate_tokens(text: str) -> int:
    return max(1, (len(text.strip()) + 3) // 4)


def categorize_prompt(text: str) -> str:
    t = text.lower()
    rules = [
        ("classification", r"\b(classify|label|category|sentiment|spam)\b"),
        ("coding", r"\b(code|typescript|python|bug|stack trace|function|class|sql)\b"),
        ("summarization", r"\b(summarize|summary|tl;dr|meeting notes|brief)\b"),
        ("extraction", r"\b(extract|parse|invoice|receipt|json|schema|field)\b"),
        ("rag", r"\b(retrieve|context|knowledge base|sources|citations|rag)\b"),
        ("vision", r"\b(image|screenshot|photo|vision|ocr|multimodal)\b"),
        ("agentic", r"\b(tool|browser|click|workflow|agent|plan)\b"),
        ("reasoning", r"\b(reason|prove|solve|think|logic|math)\b"),
    ]
    for label, pattern in rules:
        if re.search(pattern, t):
            return label
    return "chat"


def profile_prompts(prompts: list[str]) -> list[dict[str, Any]]:
    profiled = []
    for index, text in enumerate([p.strip() for p in prompts if p.strip()][:20], start=1):
        profiled.append({"id": f"prompt-{index}", "text": text, "category": categorize_prompt(text), "tokensEstimate": estimate_tokens(text)})
    return profiled


def tavily_search(profile: dict[str, Any]) -> list[dict[str, Any]]:
    key = env("TAVILY_API_KEY")
    if not key:
        emit("adapter_status", {"adapter": "tavily", "status": "missing_key"})
        return []
    queries = [
        "latest AI model API pricing context windows latency benchmarks OpenAI Anthropic Gemini Groq Together Fireworks DeepInfra",
        f"{profile.get('product', 'AI workload')} LLM workload benchmark cost latency routing architecture",
    ]
    findings: list[dict[str, Any]] = []
    for query in queries:
        emit("log", f"Tavily search: {query}")
        data = post_json(
            "https://api.tavily.com/search",
            {"api_key": key, "query": query, "search_depth": "advanced", "include_answer": True, "max_results": 5},
            {"Authorization": f"Bearer {key}"},
        )
        for result in data.get("results", []):
            finding = {
                "adapter": "tavily",
                "title": result.get("title") or "Tavily result",
                "url": result.get("url"),
                "summary": clip(result.get("content") or data.get("answer") or "", 700),
                "evidence": clip(result.get("content") or ""),
                "retrievedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            findings.append(finding)
            emit("research_finding", finding)
    return findings


def prometheux_research() -> list[dict[str, Any]]:
    project_id = prometheux_project_id(create=True)
    emit("adapter_status", {"adapter": "prometheux", "status": "calling_agent", "projectId": project_id})
    message = (
        "Act as the Find My Model autonomous research agent. Inspect current AI provider "
        "pricing, model availability, context windows, rate limits, hardware options, "
        "regional availability, and supported features for these pages. Return compact "
        "evidence with source URLs and do not rely on static prior knowledge.\n\n"
        f"{json.dumps(PROVIDER_PAGES, ensure_ascii=False)}"
    )
    request = urllib.request.Request(
        f"{prometheux_base_url()}/agent/{urllib.parse.quote(project_id)}/chat",
        data=json.dumps({"message": message, "session_id": f"find-my-model-{uuid.uuid4().hex[:8]}"}).encode(),
        headers=prometheux_headers(),
        method="POST",
    )
    chunks: list[str] = []
    tool_events: list[dict[str, Any]] = []
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            for raw_line in response:
                line = raw_line.decode(errors="ignore").strip()
                if not line:
                    continue
                event = json.loads(line)
                event_type = event.get("type")
                data = event.get("data") or {}
                if event_type == "error":
                    raise RuntimeError(f"prometheux_agent_error: {data}")
                if event_type == "tool_start":
                    tool_events.append(data)
                    emit("browser_snapshot", {"provider": "Prometheux", "url": prometheux_base_url(), "summary": f"tool: {data.get('tool')}"})
                elif event_type == "tool_result":
                    tool_events.append(data)
                elif event_type == "content":
                    chunks.append(str(data.get("chunk") or ""))
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="ignore")
        raise RuntimeError(f"prometheux_agent_failed: {error.code}: {detail[:800]}") from error

    evidence = clip("\n".join([*chunks, json.dumps(tool_events, ensure_ascii=False)]), 2400)
    if not evidence:
        raise RuntimeError("prometheux_agent_returned_no_evidence")
    finding = {
        "adapter": "prometheux",
        "provider": "Prometheux",
        "title": "Prometheux AI Agent provider research",
        "url": f"{prometheux_base_url()}/agent/{project_id}/chat",
        "summary": clip(evidence, 700),
        "evidence": evidence,
        "retrievedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    emit("research_finding", finding)
    return [finding]


async def adk_recommend(request: dict[str, Any], prompts: list[dict[str, Any]], findings: list[dict[str, Any]]) -> dict[str, Any]:
    key = env("GEMINI_API_KEY", "GOOLE_API_KEY", "GOOGLE_API_KEY", "GOOGLE_AI_API_KEY")
    if not key:
        raise RuntimeError("Gemini key missing: set GOOLE_API_KEY or GOOGLE_API_KEY")
    os.environ["GOOGLE_API_KEY"] = key
    model = env("GEMINI_MODEL") or "gemini-2.5-flash"
    evidence = [
        {"source": f.get("adapter"), "provider": f.get("provider"), "title": f.get("title"), "url": f.get("url"), "summary": f.get("summary")}
        for f in findings[:24]
    ]
    prompt = f"""
You are an AI infrastructure architect. Recommend a real deployment strategy for this workload.
Use only the evidence packets below. If pricing evidence is weak, say so and lower confidence.
Return only valid JSON with keys: primary, alternatives, routing, architecture, risks, markdown.

Workload:
{json.dumps(request.get("profile", {}), indent=2)}

Prompt profile:
{json.dumps([{**{k: p[k] for k in ["id", "category", "tokensEstimate"]}, "sample": p["text"][:240]} for p in prompts], indent=2)}

Evidence:
{json.dumps(evidence, indent=2)}
"""
    agent = Agent(
        name="recommendation_agent",
        model=model,
        instruction="Return concise, valid JSON only. Include provider, model, hardware, routing, latency, cost, quality and confidence.",
        generate_content_config=types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )
    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name="find-my-model", user_id="demo")
    runner = Runner(app_name="find-my-model", agent=agent, session_service=session_service)
    content = types.Content(role="user", parts=[types.Part(text=prompt)])
    chunks: list[str] = []
    async for event in runner.run_async(user_id="demo", session_id=session.id, new_message=content):
        if not event.is_final_response() or not event.content:
            continue
        for part in event.content.parts or []:
            if part.text:
                chunks.append(part.text)
    text = "".join(chunks).strip()
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise RuntimeError(f"ADK returned no JSON: {text[:500]}")
    return json.loads(match.group(0))


async def run(request: dict[str, Any]) -> None:
    run_id = str(uuid.uuid4())
    clickhouse = ClickHouseAdapter(run_id)
    langfuse = LangfuseAdapter(run_id)

    def record(event_type: str, payload: Any) -> None:
        clickhouse.insert(event_type, payload)
        try:
            langfuse.trace(event_type, payload)
        except Exception:
            pass

    emit("run_started", {"runId": run_id, "python": sys.version.split()[0], "runtime": "python-3.14.5-adk"})
    emit("integration_status", integration_status())
    record("run_started", request)
    prompts = profile_prompts(request.get("prompts") or [])
    if not prompts:
        raise RuntimeError("Upload at least one representative prompt.")
    categories: dict[str, int] = {}
    for prompt in prompts:
        categories[prompt["category"]] = categories.get(prompt["category"], 0) + 1
    profile_event = {"count": len(prompts), "categories": categories, "averageTokens": round(sum(p["tokensEstimate"] for p in prompts) / len(prompts))}
    emit("prompt_profile", profile_event)
    record("prompt_profile", profile_event)

    emit("phase", "research")
    findings = [*tavily_search(request.get("profile") or {}), *prometheux_research()]
    record("research", {"findings": findings})

    emit("phase", "reasoning")
    recommendation = await adk_recommend(request, prompts, findings)
    emit("recommendation", recommendation)
    record("recommendation", recommendation)
    emit("complete", {"runId": run_id})


def selfcheck() -> None:
    profiled = profile_prompts(["Classify this ticket.", "Summarize this page.", "Write Python code."])
    assert profiled[0]["category"] == "classification"
    assert profiled[1]["category"] == "summarization"
    assert profiled[2]["category"] == "coding"
    print("ok")


def healthcheck() -> None:
    print(json.dumps(integration_status(), indent=2, ensure_ascii=False))


def setup_clickhouse_storage() -> None:
    result = upsert_clickhouse_query_endpoint()
    print(json.dumps({"clickhouse": result, "health": integration_status()}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selfcheck", action="store_true")
    parser.add_argument("--health", action="store_true")
    parser.add_argument("--setup-clickhouse-storage", action="store_true")
    args = parser.parse_args()
    if args.selfcheck:
        selfcheck()
        return
    if args.health:
        healthcheck()
        return
    if args.setup_clickhouse_storage:
        setup_clickhouse_storage()
        return
    try:
        asyncio.run(run(json.loads(sys.stdin.read())))
    except Exception as exc:
        emit("error", str(exc))
        raise


if __name__ == "__main__":
    main()
