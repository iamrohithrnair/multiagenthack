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
    {"provider": "models.dev", "url": "https://models.dev/"},
    {"provider": "Hugging Face", "url": "https://huggingface.co/models"},
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

FRONTIER_MODEL_IDS = [
    "anthropic/claude-opus-4-8",
    "anthropic/claude-fable-5",
    "openai/gpt-5.5-pro",
    "openai/gpt-5.5",
    "google/gemini-3.1-pro-preview",
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


def get_public_json(url: str, timeout: int = 40) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "find-my-model/0.1"}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


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


def prometheux_concept_names(project_id: str) -> set[str]:
    data = prometheux_json(f"/concepts/{urllib.parse.quote(project_id)}/list?scope=user", method="GET")
    return {
        str(concept.get("name") or concept.get("concept_name") or "")
        for concept in data.get("data") or []
    }


def prometheux_save_concept(project_id: str, name: str, definition: str, output_predicate: str, description: str, existing: set[str]) -> None:
    body = {
        "definition": definition,
        "concept_type": "logic",
        "concept_name": name,
        "output_predicate": output_predicate,
        "description": description,
        "scope": "user",
        "force_overwrite": True,
    }
    if name in existing:
        body["existing_name"] = name
    prometheux_json(f"/concepts/{urllib.parse.quote(project_id)}/save", body)


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


def model_summary(model: dict[str, Any]) -> dict[str, Any]:
    modalities = model.get("modalities") or {}
    limit = model.get("limit") or {}
    cost = model.get("cost") or {}
    return {
        "id": model.get("id"),
        "name": model.get("name"),
        "provider": str(model.get("id") or "").split("/", 1)[0],
        "family": model.get("family"),
        "context": limit.get("context"),
        "output": limit.get("output"),
        "inputModalities": modalities.get("input") or [],
        "outputModalities": modalities.get("output") or [],
        "openWeights": bool(model.get("open_weights")),
        "toolCall": bool(model.get("tool_call")),
        "structuredOutput": bool(model.get("structured_output")),
        "reasoning": bool(model.get("reasoning")),
        "releaseDate": model.get("release_date"),
        "inputCost": cost.get("input"),
        "outputCost": cost.get("output"),
    }


def models_dev_catalog(profile: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = get_public_json("https://models.dev/models.json", timeout=30)
    models = [model_summary(model) for model in data.values()]
    ranked = sorted(models, key=lambda model: model_score(model, profile), reverse=True)
    emit("model_catalog", {"source": "models.dev", "count": len(models), "models": ranked})
    finding = {
        "adapter": "models.dev",
        "provider": "models.dev",
        "title": f"models.dev model catalog ({len(models)} models)",
        "url": "https://models.dev/",
        "summary": "Full model catalog loaded and ranked against workload filters. Frontier closed models are evaluated before lower-cost and open-weight alternatives.",
        "evidence": json.dumps({"frontierFirst": FRONTIER_MODEL_IDS, "topRanked": ranked[:30]}, ensure_ascii=False),
        "retrievedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    emit("research_finding", finding)
    return ranked, [finding]


def model_score(model: dict[str, Any], profile: dict[str, Any]) -> tuple[Any, ...]:
    model_id = str(model.get("id") or "")
    name = f"{model_id} {model.get('name') or ''}".lower()
    inputs = set(model.get("inputModalities") or [])
    context = int(model.get("context") or 0)
    input_cost = model.get("inputCost")
    output_cost = model.get("outputCost")
    cost = float(input_cost or 99) + float(output_cost or 99)
    wants_context = int(profile.get("contextTokens") or (1000000 if profile.get("longContext") else 32000))
    fast_words = ("fast", "flash", "instant", "mini", "nano", "haiku", "turbo", "realtime")
    quality_words = ("opus", "fable", "gpt-5.5", "gemini-3.1-pro", "pro")
    return (
        1 if context >= wants_context else 0,
        1 if profile.get("voice") and "audio" in inputs else 0,
        1 if profile.get("vision") and "image" in inputs else 0,
        1 if profile.get("toolCalling") and model.get("toolCall") else 0,
        1 if profile.get("structuredOutput") and model.get("structuredOutput") else 0,
        1 if model_id in FRONTIER_MODEL_IDS and profile.get("frontierFirst", True) else 0,
        1 if profile.get("realTime") and any(word in name for word in fast_words) else 0,
        1 if (profile.get("fastModel") or profile.get("priority") == "fast") and any(word in name for word in fast_words) else 0,
        1 if profile.get("priority") == "best" and any(word in name for word in quality_words) else 0,
        -cost if profile.get("priority") == "cheap" else 0,
        context,
        str(model.get("releaseDate") or ""),
    )


def huggingface_search(profile: dict[str, Any]) -> list[dict[str, Any]]:
    product = profile.get("product") or profile.get("goalPrompt") or "llm"
    terms = [str(product), "text-generation"]
    if profile.get("voice"):
        terms.append("audio")
    if profile.get("vision"):
        terms.append("vision")
    query = urllib.parse.quote(" ".join(terms))
    try:
        data = get_public_json(f"https://huggingface.co/api/models?search={query}&sort=downloads&direction=-1&limit=10", timeout=20)
    except Exception as exc:
        emit("adapter_status", {"adapter": "huggingface", "status": f"search_failed: {exc}"})
        return []
    findings = []
    for model in data[:10]:
        finding = {
            "adapter": "huggingface",
            "provider": "Hugging Face",
            "title": model.get("modelId") or "Hugging Face model",
            "url": f"https://huggingface.co/{model.get('modelId')}",
            "summary": clip(", ".join(model.get("tags") or []) or "Hugging Face model candidate", 500),
            "evidence": json.dumps(model, ensure_ascii=False)[:1800],
            "retrievedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        findings.append(finding)
        emit("research_finding", finding)
    return findings


def evidence_packets(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"E{index}",
            "source": finding.get("adapter"),
            "provider": finding.get("provider"),
            "title": finding.get("title"),
            "url": finding.get("url"),
            "summary": finding.get("summary"),
            "retrievedAt": finding.get("retrievedAt"),
        }
        for index, finding in enumerate(findings[:24], start=1)
    ]


def vadalog_value(value: Any) -> str:
    return json.dumps(str(value or ""), ensure_ascii=False)


def vadalog_fact(predicate: str, *values: Any) -> str:
    return f"{predicate}({', '.join(vadalog_value(value) for value in values)})."


def build_ontology(profile: dict[str, Any], prompts: list[dict[str, Any]], ranked_models: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    requirements = [
        {"id": "context", "label": f"{int(profile.get('contextTokens') or 0):,} token context", "hard": bool(profile.get("contextTokens"))},
        {"id": "vision", "label": "image input", "hard": bool(profile.get("vision"))},
        {"id": "voice", "label": "audio input", "hard": bool(profile.get("voice"))},
        {"id": "tool_calling", "label": "tool calls", "hard": bool(profile.get("toolCalling"))},
        {"id": "structured_output", "label": "structured output", "hard": bool(profile.get("structuredOutput"))},
        {"id": "streaming", "label": "streaming", "hard": bool(profile.get("streaming"))},
    ]
    top_models = ranked_models[:8]
    concepts = [
        {"id": "workload", "label": profile.get("product") or profile.get("goalPrompt") or "workload", "kind": "first_party_input", "evidenceIds": ["U1"]},
        {"id": "prompt_profile", "label": f"{len(prompts)} profiled prompts", "kind": "first_party_input", "evidenceIds": ["U1"]},
        {"id": "evidence_packet", "label": f"{len(evidence)} retrieved evidence packets", "kind": "source"},
        {"id": "candidate_model", "label": f"{len(top_models)} ranked candidate models", "kind": "model"},
        {"id": "recommendation", "label": "grounded model recommendation", "kind": "output"},
    ]
    relations = [
        {"from": "workload", "to": requirement["id"], "type": "requires", "evidenceIds": ["U1"]}
        for requirement in requirements
        if requirement["hard"]
    ]
    relations.extend(
        {"from": str(model.get("id")), "to": "candidate_model", "type": "ranked_by_models_dev", "evidenceIds": ["E1"]}
        for model in top_models
    )
    lines = [
        "% Find My Model ontology. Saved into Prometheux for the project lineage view.",
        vadalog_fact("find_my_model_workload", "workload", profile.get("product") or "", profile.get("goalPrompt") or ""),
    ]
    lines.extend(vadalog_fact("find_my_model_requirement", item["id"], item["label"], "hard" if item["hard"] else "soft") for item in requirements)
    lines.extend(vadalog_fact("find_my_model_ontology", "requirement", item["id"], item["label"]) for item in requirements)
    lines.extend(vadalog_fact("find_my_model_evidence", item["id"], item.get("source") or "", item.get("url") or "") for item in evidence[:12])
    for model in top_models:
        model_id = str(model.get("id") or "")
        lines.append(vadalog_fact("find_my_model_candidate", model_id, model.get("name") or "", model.get("provider") or "", model.get("context") or 0))
        lines.append(vadalog_fact("find_my_model_ontology", "candidate_model", model_id, model.get("name") or ""))
        for modality in model.get("inputModalities") or []:
            lines.append(vadalog_fact("find_my_model_supports", model_id, modality))
        lines.append(vadalog_fact("find_my_model_grounded_by", model_id, "E1"))
    lines.append('@output("find_my_model_ontology").')
    return {
        "projectConcept": "find_my_model_ontology",
        "outputPredicate": "find_my_model_ontology",
        "concepts": concepts,
        "requirements": requirements,
        "relations": relations,
        "evidenceIds": [item["id"] for item in evidence],
        "definition": "\n".join(lines),
    }


def build_lineage(profile: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    web_ids = [item["id"] for item in evidence if item.get("source") in {"prometheux", "tavily", "huggingface"}]
    steps = [
        {"id": "L1", "from": "user_input", "to": "prompt_profile", "label": "Profile workload from product, prompt, and filters", "evidenceIds": ["U1"]},
        {"id": "L2", "from": "models.dev", "to": "ranked_models", "label": "Rank provider catalog against hard filters", "evidenceIds": ["E1"]},
        {"id": "L3", "from": "web_research", "to": "evidence_packets", "label": "Collect provider and product evidence", "evidenceIds": web_ids[:8]},
        {"id": "L4", "from": "evidence_packets", "to": "ontology", "label": "Bind requirements, candidates, and source evidence", "evidenceIds": ["E1", *web_ids[:4]]},
        {"id": "L5", "from": "ontology", "to": "recommendation", "label": "ADK may only reason from cited packets; missing facts stay unknown", "evidenceIds": ["E1", *web_ids[:4]]},
    ]
    lines = ["% Find My Model lineage. Prometheux can materialize this as a chase graph when run."]
    for step in steps:
        lines.append(vadalog_fact("find_my_model_lineage", step["id"], step["from"], step["to"], step["label"]))
        for evidence_id in step["evidenceIds"]:
            lines.append(vadalog_fact("find_my_model_lineage_evidence", step["id"], evidence_id))
    lines.extend([
        '@chase("csv", "disk/find_my_model", "lineage.csv").',
        '@output("find_my_model_lineage").',
    ])
    return {
        "projectConcept": "find_my_model_lineage",
        "outputPredicate": "find_my_model_lineage",
        "steps": steps,
        "definition": "\n".join(lines),
        "policy": "Evidence IDs are mandatory; unsupported price, latency, and availability claims must be returned as unknown or needs_verification.",
    }


def prometheux_save_context(project_id: str, ontology: dict[str, Any], lineage: dict[str, Any]) -> None:
    existing = prometheux_concept_names(project_id)
    prometheux_save_concept(project_id, ontology["projectConcept"], ontology["definition"], ontology["outputPredicate"], "Find My Model ontology: workload, requirements, candidates, and evidence bindings.", existing)
    prometheux_save_concept(project_id, lineage["projectConcept"], lineage["definition"], lineage["outputPredicate"], "Find My Model lineage: source evidence to ontology to recommendation.", existing)
    emit("adapter_status", {"adapter": "prometheux", "status": "saved_ontology_and_lineage_concepts", "projectId": project_id})


def context_layer(profile: dict[str, Any], prompts: list[dict[str, Any]], ranked_models: list[dict[str, Any]], findings: list[dict[str, Any]], ontology: dict[str, Any], lineage: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    nodes = [
        {"id": "site", "label": profile.get("productUrl") or profile.get("product") or "Product", "kind": "input", "x": 10, "y": 30},
        {"id": "prompt", "label": profile.get("goalPrompt") or f"{len(prompts)} representative prompts", "kind": "input", "x": 10, "y": 70},
        {"id": "prometheux", "label": "Prometheux context agent", "kind": "agent", "x": 32, "y": 18},
        {"id": "tavily", "label": "Tavily + web evidence", "kind": "source", "x": 32, "y": 50},
        {"id": "models", "label": f"models.dev catalog: {len(ranked_models)} models", "kind": "source", "x": 32, "y": 82},
        {"id": "ontology", "label": "Project ontology concept", "kind": "ontology", "x": 56, "y": 34},
        {"id": "lineage", "label": "Project lineage chase graph", "kind": "lineage", "x": 56, "y": 66},
        {"id": "filters", "label": f"{int(profile.get('contextTokens') or 0):,} ctx | voice {bool(profile.get('voice'))} | realtime {bool(profile.get('realTime'))}", "kind": "rank", "x": 76, "y": 34},
        {"id": "recommendation", "label": "Evidence-cited ADK recommendation", "kind": "output", "x": 88, "y": 66},
    ]
    edges = [
        {"from": "site", "to": "prometheux"},
        {"from": "prompt", "to": "prometheux"},
        {"from": "prometheux", "to": "ontology"},
        {"from": "tavily", "to": "ontology"},
        {"from": "models", "to": "ontology"},
        {"from": "ontology", "to": "lineage"},
        {"from": "lineage", "to": "filters"},
        {"from": "filters", "to": "recommendation"},
        {"from": "lineage", "to": "recommendation"},
    ]
    graph = {
        "nodes": nodes,
        "edges": edges,
        "evidenceCount": len(findings),
        "ontology": {key: ontology[key] for key in ["projectConcept", "concepts", "requirements", "relations", "evidenceIds"]},
        "lineage": {key: lineage[key] for key in ["projectConcept", "steps", "policy"]},
        "groundingPolicy": "Recommendation claims must cite evidence IDs; missing facts stay unknown or need verification.",
        "evidenceIds": [item["id"] for item in evidence],
    }
    emit("context_layer", graph)
    return graph


def tavily_search(profile: dict[str, Any]) -> list[dict[str, Any]]:
    key = env("TAVILY_API_KEY")
    if not key:
        emit("adapter_status", {"adapter": "tavily", "status": "missing_key"})
        return []
    website = profile.get("productUrl") or ""
    goal = profile.get("goalPrompt") or profile.get("notes") or ""
    queries = [
        "models.dev latest AI model API catalog pricing context windows OpenAI Anthropic Gemini voice realtime",
        "Claude Opus 4.8 Claude Fable 5 GPT-5.5 Gemini 3.1 Pro model pricing context voice vision",
        f"{profile.get('product', 'AI workload')} {website} {goal} LLM workload benchmark cost latency routing architecture",
    ]
    if website:
        queries.append(f"{website} product features AI assistant voice vision workflow users")
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


def prometheux_research(profile: dict[str, Any], ranked_models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    project_id = prometheux_project_id(create=True)
    emit("adapter_status", {"adapter": "prometheux", "status": "calling_agent", "projectId": project_id})
    website = profile.get("productUrl") or ""
    goal = profile.get("goalPrompt") or ""
    message = (
        "Act as the Find My Model autonomous research agent. Inspect current AI provider "
        "pricing, model availability, context windows, voice/audio support, rate limits, "
        "hardware options, regional availability, and supported features. If a product "
        "website is supplied, inspect it first and infer the workload from the site and "
        "use-case prompt. Evaluate frontier closed models first, then compare cheaper, "
        "faster, and open-weight options. Return compact evidence with source URLs and "
        "do not rely on static prior knowledge.\n\n"
        f"Product website: {website or 'not provided'}\n"
        f"Use-case prompt: {goal or 'not provided'}\n"
        f"Advanced filters: {json.dumps(profile, ensure_ascii=False)}\n"
        f"Provider pages: {json.dumps(PROVIDER_PAGES, ensure_ascii=False)}\n"
        f"Ranked models.dev candidates: {json.dumps(ranked_models[:12], ensure_ascii=False)}"
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
        with urllib.request.urlopen(request, timeout=150) as response:
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


async def adk_recommend(request: dict[str, Any], prompts: list[dict[str, Any]], evidence: list[dict[str, Any]], ranked_models: list[dict[str, Any]], ontology: dict[str, Any], lineage: dict[str, Any]) -> dict[str, Any]:
    key = env("GEMINI_API_KEY", "GOOLE_API_KEY", "GOOGLE_API_KEY", "GOOGLE_AI_API_KEY")
    if not key:
        raise RuntimeError("Gemini key missing: set GOOLE_API_KEY or GOOGLE_API_KEY")
    os.environ["GOOGLE_API_KEY"] = key
    model = env("GEMINI_MODEL") or "gemini-2.5-flash"
    prompt = f"""
You are an AI infrastructure architect. Recommend a real deployment strategy for this workload.
Use only the first-party workload input and the evidence packets below. Every factual claim about
model capability, price, latency, availability, provider support, or architecture must be supported
by evidenceIds from the packets. If the evidence does not contain a fact, write "unknown" or
"needs_verification"; do not infer it from memory.
Start with the best frontier models from models.dev, especially Claude Opus 4.8, Claude Fable 5,
GPT-5.5 / GPT-5.5 Pro, and Gemini 3.1 Pro when they match the filters. Do not restrict yourself
to open-source or open-weight models; include open-weight/Hugging Face options only when they are
a better fit for cost, privacy, deployment, or latency.
Voice and vision are hard requirements when true; voice requires audio input support and vision
requires image input support. If frontierFirst is true, pick the highest-ranked candidate that
satisfies the hard filters unless the evidence says it is unavailable.
Return only valid JSON with keys: primary, alternatives, routing, architecture, risks, markdown, grounding.
grounding must include evidenceIds and lineageStepIds used for the recommendation.

Workload:
{json.dumps(request.get("profile", {}), indent=2)}

Prompt profile:
{json.dumps([{**{k: p[k] for k in ["id", "category", "tokensEstimate"]}, "sample": p["text"][:240]} for p in prompts], indent=2)}

Evidence:
{json.dumps(evidence, indent=2)}

Ontology:
{json.dumps({key: ontology[key] for key in ["concepts", "requirements", "relations", "evidenceIds"]}, indent=2)}

Lineage:
{json.dumps({key: lineage[key] for key in ["steps", "policy"]}, indent=2)}

Ranked models.dev candidates:
{json.dumps(ranked_models[:60], indent=2)}
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


def enforce_grounding(recommendation: dict[str, Any], evidence: list[dict[str, Any]], lineage: dict[str, Any]) -> dict[str, Any]:
    known_evidence = {item["id"] for item in evidence}
    known_lineage = {step["id"] for step in lineage.get("steps") or []}
    grounding = recommendation.get("grounding") if isinstance(recommendation.get("grounding"), dict) else {}
    evidence_ids = [str(item) for item in grounding.get("evidenceIds") or [] if str(item) in known_evidence]
    lineage_ids = [str(item) for item in grounding.get("lineageStepIds") or [] if str(item) in known_lineage]
    if "E1" in known_evidence and "E1" not in evidence_ids:
        evidence_ids.insert(0, "E1")
    if not evidence_ids:
        raise RuntimeError("recommendation_missing_grounding_evidence_ids")
    recommendation["grounding"] = {
        **grounding,
        "evidenceIds": evidence_ids,
        "lineageStepIds": lineage_ids or sorted(known_lineage),
        "policy": lineage.get("policy"),
        "missingEvidenceBehavior": "unknown_or_needs_verification",
    }
    return recommendation


def model_matches_hard_filters(model: dict[str, Any], profile: dict[str, Any]) -> bool:
    inputs = set(model.get("inputModalities") or [])
    context = int(model.get("context") or 0)
    required_context = int(profile.get("contextTokens") or 0)
    return (
        (not required_context or context >= required_context)
        and (not profile.get("voice") or "audio" in inputs)
        and (not profile.get("vision") or "image" in inputs)
    )


def find_recommended_model(recommendation: dict[str, Any], ranked_models: list[dict[str, Any]]) -> dict[str, Any] | None:
    primary = recommendation.get("primary") or {}
    name = f"{primary.get('provider') or ''} {primary.get('model') or ''}".lower()
    return next((model for model in ranked_models if str(model.get("id") or "").lower() in name or str(model.get("name") or "").lower() in name), None)


def enforce_hard_filters(recommendation: dict[str, Any], profile: dict[str, Any], ranked_models: list[dict[str, Any]]) -> dict[str, Any]:
    current = find_recommended_model(recommendation, ranked_models)
    if current and model_matches_hard_filters(current, profile):
        return recommendation
    replacement = next((model for model in ranked_models if model_matches_hard_filters(model, profile)), None)
    if not replacement:
        return recommendation
    previous = recommendation.get("primary") or {}
    recommendation["alternatives"] = [{"label": "AI recommendation before hard-filter enforcement", **previous}, *(recommendation.get("alternatives") or [])]
    recommendation["primary"] = {
        "provider": replacement.get("provider"),
        "model": replacement.get("name"),
        "hardware": "Provider-managed API",
        "routing": "Primary route because it satisfies the selected hard filters before lower-ranked alternatives.",
        "latency": "Use the ranked provider endpoint directly; add a faster secondary route if production latency misses target.",
        "cost": "Pricing not present in models.dev for this entry; verify provider pricing before launch.",
        "quality": f"Ranked first for requested filters: context {replacement.get('context'):,}, modalities {', '.join(replacement.get('inputModalities') or [])}.",
        "confidence": "High on feature fit from models.dev; pricing confidence depends on provider evidence.",
    }
    note = f"Primary adjusted to {replacement.get('name')} because the selected hard filters require native support for the requested modalities/context.\n\n"
    recommendation["markdown"] = note + str(recommendation.get("markdown") or "")
    return recommendation


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
    profile = request.get("profile") or {}
    prompt_inputs = [str(item) for item in (request.get("prompts") or []) if str(item).strip()]
    if profile.get("goalPrompt"):
        prompt_inputs.insert(0, str(profile.get("goalPrompt")))
    if not prompt_inputs and profile.get("productUrl"):
        prompt_inputs.append(f"Infer the product workload from {profile.get('productUrl')} and recommend the best model stack.")
    prompts = profile_prompts(prompt_inputs)
    if not prompts:
        raise RuntimeError("Add a product website, prompt, or representative prompt.")
    categories: dict[str, int] = {}
    for prompt in prompts:
        categories[prompt["category"]] = categories.get(prompt["category"], 0) + 1
    profile_event = {"count": len(prompts), "categories": categories, "averageTokens": round(sum(p["tokensEstimate"] for p in prompts) / len(prompts))}
    emit("prompt_profile", profile_event)
    record("prompt_profile", profile_event)

    emit("phase", "research")
    ranked_models, model_findings = models_dev_catalog(profile)
    findings = [
        *model_findings,
        *huggingface_search(profile),
        *tavily_search(profile),
        *prometheux_research(profile, ranked_models),
    ]
    evidence = evidence_packets(findings)
    ontology = build_ontology(profile, prompts, ranked_models, evidence)
    lineage = build_lineage(profile, evidence)
    project_id = prometheux_project_id(create=True)
    prometheux_save_context(project_id, ontology, lineage)
    ontology["projectId"] = project_id
    lineage["projectId"] = project_id
    emit("ontology", ontology)
    emit("lineage", lineage)
    context_graph = context_layer(profile, prompts, ranked_models, findings, ontology, lineage, evidence)
    record("research", {"findings": findings})
    record("ontology", ontology)
    record("lineage", lineage)
    record("context_layer", context_graph)

    emit("phase", "reasoning")
    recommendation = await adk_recommend(request, prompts, evidence, ranked_models, ontology, lineage)
    recommendation = enforce_hard_filters(recommendation, profile, ranked_models)
    recommendation = enforce_grounding(recommendation, evidence, lineage)
    emit("recommendation", recommendation)
    record("recommendation", recommendation)
    emit("complete", {"runId": run_id})


def selfcheck() -> None:
    profiled = profile_prompts(["Classify this ticket.", "Summarize this page.", "Write Python code."])
    assert profiled[0]["category"] == "classification"
    assert profiled[1]["category"] == "summarization"
    assert profiled[2]["category"] == "coding"
    recommendation = {"primary": {"provider": "Anthropic", "model": "Claude Opus 4.8"}, "alternatives": [], "markdown": ""}
    ranked = [
        {"provider": "google", "name": "Gemini 3.1 Pro Preview", "id": "google/gemini-3.1-pro-preview", "context": 1048576, "inputModalities": ["text", "image", "audio"]},
        {"provider": "anthropic", "name": "Claude Opus 4.8", "id": "anthropic/claude-opus-4-8", "context": 1000000, "inputModalities": ["text", "image"]},
    ]
    assert enforce_hard_filters(recommendation, {"voice": True, "vision": True, "contextTokens": 200000}, ranked)["primary"]["provider"] == "google"
    evidence = evidence_packets([{"adapter": "models.dev", "title": "catalog", "url": "https://models.dev/"}])
    ontology = build_ontology({"product": "Support bot", "contextTokens": 200000, "vision": True}, profiled, ranked, evidence)
    lineage = build_lineage({}, evidence)
    assert "find_my_model_candidate" in ontology["definition"]
    assert '@chase("csv", "disk/find_my_model", "lineage.csv").' in lineage["definition"]
    grounded = enforce_grounding({"grounding": {"evidenceIds": ["E1"], "lineageStepIds": ["L2"]}}, evidence, lineage)
    assert grounded["grounding"]["missingEvidenceBehavior"] == "unknown_or_needs_verification"
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
