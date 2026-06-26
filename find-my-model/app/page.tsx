"use client";

import { useMemo, useState } from "react";
import { Activity, ArrowRight, Boxes, Brain, Check, Cpu, Database, DollarSign, Download, FileText, Globe2, Layers3, Link2, Loader2, Mail, Network, Play, Rocket, ShieldCheck, Sparkles, SlidersHorizontal, Timer, Trophy, Upload, X, Zap } from "lucide-react";
import type { RecommendationReport, WorkloadProfile } from "@/lib/types";

const samplePrompts = `Classify a support ticket.
Return one JSON label.

Summarize a help-center conversation.
Include cited source snippets.

Extract renewal date, current tier, and churn risk.

Read a screenshot error and recommend the next action.`;

type EventRow = { type: string; text: string; timestamp: number };
type ModelRow = {
  id: string;
  name: string;
  provider: string;
  context?: number;
  inputModalities?: string[];
  openWeights?: boolean;
};
type ContextNode = { id: string; label: string; kind: string; x: number; y: number };
type ContextEdge = { from: string; to: string };
type OntologySummary = {
  projectConcept?: string;
  concepts?: Array<{ id: string; label: string; kind: string }>;
  requirements?: Array<{ id: string; label: string; hard?: boolean }>;
  evidenceIds?: string[];
};
type LineageSummary = {
  projectConcept?: string;
  steps?: Array<{ id: string; from: string; to: string; label: string; evidenceIds?: string[] }>;
  policy?: string;
};
type PipelineStep = { id: string; label: string; detail: string };
type ContextGraph = {
  nodes: ContextNode[];
  edges: ContextEdge[];
  pipeline?: PipelineStep[];
  evidenceCount?: number;
  evidenceIds?: string[];
  ontology?: OntologySummary;
  lineage?: LineageSummary;
  rag?: { enabled?: boolean; vectorDatabase?: string; files?: string[] };
  groundingPolicy?: string;
};

const defaultContextGraph: ContextGraph = {
  nodes: [
    { id: "input", label: "Product + prompts", kind: "input", x: 6, y: 50 },
    { id: "ingest", label: "Context ingest", kind: "ingest", x: 18, y: 50 },
    { id: "rag", label: "RAG agent", kind: "rag", x: 30, y: 50 },
    { id: "prometheux", label: "Prometheux research", kind: "agent", x: 42, y: 50 },
    { id: "evidence", label: "Evidence packets", kind: "source", x: 54, y: 50 },
    { id: "ontology", label: "Project ontology", kind: "ontology", x: 66, y: 50 },
    { id: "lineage", label: "Project lineage", kind: "lineage", x: 78, y: 50 },
    { id: "recommendation", label: "Recommendation", kind: "output", x: 90, y: 50 },
  ],
  edges: [
    { from: "input", to: "ingest" },
    { from: "ingest", to: "rag" },
    { from: "rag", to: "prometheux" },
    { from: "prometheux", to: "evidence" },
    { from: "evidence", to: "ontology" },
    { from: "ontology", to: "lineage" },
    { from: "lineage", to: "recommendation" },
  ],
  pipeline: [
    { id: "input", label: "Inputs", detail: "waiting" },
    { id: "ingest", label: "Ingest", detail: "waiting" },
    { id: "rag", label: "RAG", detail: "off" },
    { id: "prometheux", label: "Research", detail: "waiting" },
    { id: "evidence", label: "Evidence", detail: "waiting" },
    { id: "ontology", label: "Ontology", detail: "waiting" },
    { id: "lineage", label: "Lineage", detail: "waiting" },
    { id: "recommendation", label: "Recommend", detail: "waiting" },
  ],
};

function parsePrompts(raw: string) {
  const text = raw.trim();
  if (!text) return [];
  try {
    const parsed = JSON.parse(text);
    const values = Array.isArray(parsed) ? parsed : Object.values(parsed);
    return values
      .map((item) => typeof item === "string" ? item : (item as Record<string, unknown>).prompt ?? (item as Record<string, unknown>).text)
      .filter((item): item is string => typeof item === "string" && item.trim().length > 0)
      .slice(0, 20);
  } catch {
    return text.split(/\n\s*\n/).map((prompt) => prompt.trim()).filter(Boolean).slice(0, 20);
  }
}

function scrub(value: string) {
  return value
    .replace(/https?:\/\/models\.dev\/?/gi, "live model catalog")
    .replace(/models\.dev model catalog/gi, "live model catalog")
    .replace(/models\.dev/gi, "live model catalog");
}

function eventText(type: string, data: unknown) {
  if (type === "log" || type === "phase" || type === "error") return String(data);
  if (type === "run_started") {
    const d = data as { runId: string; runtime?: string };
    return `Run ${d.runId.slice(0, 8)} started on ${d.runtime ?? "backend"}`;
  }
  if (type === "prompt_profile") {
    const d = data as { count: number; averageTokens: number };
    return `${d.count} prompts profiled, avg ${d.averageTokens} tokens`;
  }
  if (type === "adapter_status") {
    const d = data as { adapter: string; status: string };
    if (d.adapter === "clickhouse" && d.status === "sql_password_missing_for_discovered_service") {
      return "clickhouse: hosted service found, storage needs SQL password or query endpoint opt-in";
    }
    return `${d.adapter}: ${d.status}`;
  }
  if (type === "integration_status") {
    const d = data as {
      gemini?: { configured?: boolean };
      tavily?: { configured?: boolean };
      clickhouse?: { storage?: string; cloudService?: string };
      prometheux?: { projectReady?: boolean };
    };
    return `apis: gemini ${d.gemini?.configured ? "ok" : "missing"}, tavily ${d.tavily?.configured ? "ok" : "missing"}, clickhouse ${d.clickhouse?.cloudService ?? d.clickhouse?.storage ?? "unknown"}, prometheux ${d.prometheux?.projectReady ? "agent" : "needs project"}`;
  }
  if (type === "research_finding") {
    const d = data as { adapter: string; provider?: string; title?: string };
    if ((d.adapter ?? "").includes("models.dev")) return "Live model catalog indexed";
    return `${d.adapter}: ${d.provider ?? d.title}`;
  }
  if (type === "browser_snapshot") {
    const d = data as { provider?: string; url?: string };
    return `web action: ${d.provider ?? d.url}`;
  }
  if (type === "model_catalog") {
    const d = data as { count?: number };
    return `Ranked ${d.count ?? 0} live models against your workload`;
  }
  if (type === "context_layer") {
    const d = data as { evidenceCount?: number };
    return `Prometheux context graph ready (${d.evidenceCount ?? 0} evidence packets, ontology + lineage)`;
  }
  if (type === "ontology") {
    const d = data as { projectConcept?: string; concepts?: unknown[] };
    return `Ontology saved in Prometheux (${d.projectConcept ?? "project concept"}, ${d.concepts?.length ?? 0} nodes)`;
  }
  if (type === "lineage") {
    const d = data as { projectConcept?: string; steps?: unknown[] };
    return `Lineage saved in Prometheux (${d.projectConcept ?? "project concept"}, ${d.steps?.length ?? 0} steps)`;
  }
  if (type === "recommendation") return "Recommendation ready";
  if (type === "complete") return "Pipeline complete";
  return type;
}

function ContextLayer({ graph }: { graph: ContextGraph }) {
  const nodes = new Map(graph.nodes.map((node) => [node.id, node]));
  const pipeline = graph.pipeline?.length ? graph.pipeline : graph.nodes.map((node) => ({ id: node.id, label: node.label, detail: node.kind }));
  return (
    <div className="context-shell">
      <div className="context-layer">
        <div className="context-pipeline">
          {pipeline.map((step) => (
            <div className={`context-step context-${nodes.get(step.id)?.kind ?? step.id}`} key={step.id}>
              <span>{step.label}</span>
              <strong>{step.detail}</strong>
            </div>
          ))}
        </div>
        <div className="context-edge-list">
          {graph.edges.map((edge) => (
            <span key={`${edge.from}-${edge.to}`}>{scrub(edge.from)} -&gt; {scrub(edge.to)}</span>
          ))}
        </div>
      </div>
      <div className="context-details">
        <div>
          <span>pipeline</span>
          <strong>{(graph.pipeline ?? []).map((step) => step.label).join(" -> ") || "waiting"}</strong>
          <small>{(graph.pipeline ?? []).map((step) => step.detail).join(" / ") || "waiting"}</small>
        </div>
        <div>
          <span>rag</span>
          <strong>{graph.rag?.enabled ? graph.rag.vectorDatabase : "off"}</strong>
          <small>{graph.rag?.files?.length ? graph.rag.files.join(" / ") : "no files"}</small>
        </div>
        <div>
          <span>ontology</span>
          <strong>{scrub(graph.ontology?.projectConcept ?? "waiting")}</strong>
          <small>{scrub((graph.ontology?.concepts ?? []).slice(0, 4).map((item) => item.label).join(" / ")) || "waiting"}</small>
        </div>
        <div>
          <span>lineage</span>
          <strong>{scrub(graph.lineage?.projectConcept ?? "waiting")}</strong>
          <small>{scrub((graph.lineage?.steps ?? []).slice(0, 3).map((step) => `${step.from} -> ${step.to}`).join(" / ")) || "waiting"}</small>
        </div>
        <div>
          <span>grounding</span>
          <strong>{graph.evidenceIds?.length ? `${graph.evidenceIds.length} cited packets` : "waiting"}</strong>
          <small>{graph.groundingPolicy ?? "waiting"}</small>
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  const [profile, setProfile] = useState<WorkloadProfile>({
    product: "Customer support chatbot",
    productUrl: "",
    goalPrompt: "Recommend the best model stack for:\n- customer support answers\n- screenshots and tool calls\n- optional voice escalation\n- streamed responses",
    users: "SaaS customers and internal support agents",
    requestsPerDay: 500,
    latencySeconds: 3,
    budgetMonthlyUsd: 300,
    region: "US/EU",
    canSelfHost: true,
    privacy: "sensitive",
    longContext: true,
    contextTokens: 200000,
    vision: true,
    voice: false,
    toolCalling: true,
    structuredOutput: true,
    streaming: true,
    fastModel: false,
    realTime: false,
    frontierFirst: true,
    rag: true,
    vectorDatabase: "pgvector",
    vectorConnection: "",
    documentUpload: true,
    imageUpload: true,
    uploadedContextFiles: [],
    uploadedContextText: "",
    priority: "best",
    notes: "Prefer low cost for simple tickets, higher quality for escalations.",
  });
  const [promptsText, setPromptsText] = useState(samplePrompts);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [browserSummary, setBrowserSummary] = useState("Browser/API research pane");
  const [browserUrl, setBrowserUrl] = useState("");
  const [report, setReport] = useState<RecommendationReport | null>(null);
  const [modelCatalog, setModelCatalog] = useState<ModelRow[]>([]);
  const [contextGraph, setContextGraph] = useState<ContextGraph>(defaultContextGraph);
  const [running, setRunning] = useState(false);
  const [settingUpClickHouse, setSettingUpClickHouse] = useState(false);
  const [trialOpen, setTrialOpen] = useState(false);
  const [trialEmail, setTrialEmail] = useState("");
  const [trialDone, setTrialDone] = useState(false);

  const openTrial = () => {
    setTrialDone(false);
    setTrialOpen(true);
  };
  const prompts = useMemo(() => parsePrompts(promptsText), [promptsText]);
  const markdown = report?.markdown ?? "";
  const recoModel = (report?.primary?.model ?? "").toLowerCase().trim();
  const recoMatchId = useMemo(() => {
    if (!recoModel || modelCatalog.length === 0) return null;
    const norm = (value: string) => value.toLowerCase().trim();
    const exact = modelCatalog.find((m) => norm(m.name) === recoModel || norm(m.id) === recoModel);
    if (exact) return exact.id;
    const partial = modelCatalog.find((m) => norm(m.name).includes(recoModel) || recoModel.includes(norm(m.name)) || norm(m.id).includes(recoModel));
    return partial?.id ?? null;
  }, [recoModel, modelCatalog]);

  const update = <K extends keyof WorkloadProfile>(key: K, value: WorkloadProfile[K]) => {
    setProfile((current) => ({ ...current, [key]: value }));
  };

  async function addRagFiles(files: FileList | null) {
    if (!files?.length) return;
    const names: string[] = [];
    const textParts: string[] = [];
    for (const file of Array.from(files).slice(0, 12)) {
      names.push(file.name);
      if (file.type.startsWith("image/")) {
        update("imageUpload", true);
        continue;
      }
      update("documentUpload", true);
      try {
        textParts.push(`\n\n# ${file.name}\n${await file.text()}`);
      } catch {
        textParts.push(`\n\n# ${file.name}\n[unreadable binary document]`);
      }
    }
    setProfile((current) => ({
      ...current,
      rag: true,
      uploadedContextFiles: Array.from(new Set([...current.uploadedContextFiles, ...names])).slice(0, 24),
      uploadedContextText: `${current.uploadedContextText}${textParts.join("")}`.slice(0, 16000),
    }));
  }

  async function run() {
    setRunning(true);
    setReport(null);
    setEvents([]);
    setModelCatalog([]);
    setContextGraph(defaultContextGraph);
    setBrowserSummary("Waiting for research events");
    setBrowserUrl("");
    try {
      const response = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile, prompts }),
      });
      if (!response.body) throw new Error("No response stream");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.trim()) continue;
          const msg = JSON.parse(line);
          setEvents((current) => [{ type: msg.type, text: scrub(eventText(msg.type, msg.data)), timestamp: msg.timestamp }, ...current].slice(0, 100));
          if (msg.type === "browser_snapshot") {
            setBrowserSummary(scrub(msg.data.summary ?? msg.data.provider ?? "Research update"));
            setBrowserUrl(scrub(msg.data.url ?? ""));
          }
          if (msg.type === "model_catalog") setModelCatalog(msg.data.models ?? []);
          if (msg.type === "context_layer") setContextGraph(msg.data);
          if (msg.type === "recommendation") setReport(msg.data);
        }
      }
    } catch (error) {
      setEvents((current) => [{ type: "error", text: (error as Error).message, timestamp: Date.now() }, ...current]);
    } finally {
      setRunning(false);
    }
  }

  async function setupClickHouse() {
    if (!window.confirm("Create or update the hosted ClickHouse query endpoint for this API key?")) return;
    setSettingUpClickHouse(true);
    try {
      const response = await fetch("/api/clickhouse/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: "ENABLE_CLICKHOUSE_QUERY_ENDPOINT" }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error ?? "ClickHouse setup failed");
      setEvents((current) => [{
        type: "adapter_status",
        text: `clickhouse: ${data.clickhouse?.status ?? "setup complete"}`,
        timestamp: Date.now(),
      }, ...current]);
    } catch (error) {
      setEvents((current) => [{
        type: "error",
        text: (error as Error).message,
        timestamp: Date.now(),
      }, ...current]);
    } finally {
      setSettingUpClickHouse(false);
    }
  }

  return (
    <main className={`shell ${running ? "is-running" : ""}`}>
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <div className="brand-mark"><Brain size={26} /></div>
            <div>
              <p className="eyebrow">Live model intelligence</p>
              <h1>Find My Model</h1>
              <p className="tagline">Ship your app using the right model. Stop guessing.</p>
            </div>
          </div>
          <div className="topbar-actions">
            <div className="quick-stats" aria-label="Workload summary">
              <span><Zap size={15} />{profile.requestsPerDay.toLocaleString()} req/day</span>
              <span><Timer size={15} />{profile.latencySeconds}s target</span>
              <span><DollarSign size={15} />{profile.budgetMonthlyUsd}/mo</span>
            </div>
            <button className="run-button" onClick={run} disabled={running || (!prompts.length && !profile.goalPrompt.trim() && !profile.productUrl.trim())}>
              {running ? <Loader2 size={17} className="spin" /> : <Play size={17} />}
              {running ? "Analyzing…" : "Find my model"}
            </button>
            <button className="trial-button" onClick={openTrial}>
              <Rocket size={17} /> Start free trial
            </button>
          </div>
        </div>
      </header>

      <div className="layout">
        <section className="panel">
          <div className="panel-title"><span><Boxes size={16} /> Product Input</span></div>
          <div className="form">
            <div className="quick-start">
              <label><span><Link2 size={14} /> Product website</span><input placeholder="https://your-product.com" value={profile.productUrl} onChange={(e) => update("productUrl", e.target.value)} /></label>
              <label><span><FileText size={14} /> What should the model do?</span><textarea rows={5} cols={1} wrap="soft" value={profile.goalPrompt} onChange={(e) => update("goalPrompt", e.target.value)} /></label>
            </div>

            <details className="advanced">
              <summary><SlidersHorizontal size={16} /> Advanced filters</summary>
              <div className="advanced-body">
                <label>Product name<input value={profile.product} onChange={(e) => update("product", e.target.value)} /></label>
                <label>Users<input value={profile.users} onChange={(e) => update("users", e.target.value)} /></label>
                <label>Priority<select value={profile.priority} onChange={(e) => update("priority", e.target.value as WorkloadProfile["priority"])}><option value="best">Best quality</option><option value="balanced">Balanced</option><option value="fast">Fast</option><option value="cheap">Low cost</option></select></label>
                <label>Context length: {profile.contextTokens.toLocaleString()} tokens<input type="range" min={1000} max={1000000} step={1000} value={profile.contextTokens} onChange={(e) => update("contextTokens", Number(e.target.value))} /></label>
                <div className="grid-2">
                  <label>Requests/day<input type="number" min={1} value={profile.requestsPerDay} onChange={(e) => update("requestsPerDay", Number(e.target.value))} /></label>
                  <label>Latency sec<input type="number" min={0.1} step={0.1} value={profile.latencySeconds} onChange={(e) => update("latencySeconds", Number(e.target.value))} /></label>
                </div>
                <div className="grid-2">
                  <label>Budget USD/mo<input type="number" min={1} value={profile.budgetMonthlyUsd} onChange={(e) => update("budgetMonthlyUsd", Number(e.target.value))} /></label>
                  <label>Region<input value={profile.region} onChange={(e) => update("region", e.target.value)} /></label>
                </div>
                <label>Privacy<select value={profile.privacy} onChange={(e) => update("privacy", e.target.value as WorkloadProfile["privacy"])}><option value="standard">Standard</option><option value="sensitive">Sensitive</option><option value="regulated">Regulated</option></select></label>
                <div className="checks">
                  {([
                    ["frontierFirst", "Frontier first"],
                    ["fastModel", "Fast model"],
                    ["realTime", "Real-time"],
                    ["voice", "Voice"],
                    ["vision", "Vision"],
                    ["longContext", "Long context"],
                    ["toolCalling", "Tools"],
                    ["structuredOutput", "JSON output"],
                    ["streaming", "Streaming"],
                    ["canSelfHost", "Self-host"],
                  ] as const).map(([key, label]) => (
                    <label className="check" key={key}><input type="checkbox" checked={Boolean(profile[key])} onChange={(e) => update(key, e.target.checked)} />{label}</label>
                  ))}
                </div>
                <label>Notes<textarea rows={3} cols={1} wrap="soft" value={profile.notes} onChange={(e) => update("notes", e.target.value)} /></label>
              </div>
            </details>

            <div className="rag-box">
              <div className="rag-head">
                <label className="check"><input type="checkbox" checked={profile.rag} onChange={(e) => update("rag", e.target.checked)} />RAG agent</label>
                <label>Vector DB<select value={profile.vectorDatabase} onChange={(e) => update("vectorDatabase", e.target.value as WorkloadProfile["vectorDatabase"])}>
                  <option value="pgvector">pgvector</option>
                  <option value="pinecone">Pinecone</option>
                  <option value="weaviate">Weaviate</option>
                  <option value="qdrant">Qdrant</option>
                  <option value="milvus">Milvus</option>
                  <option value="chroma">Chroma</option>
                  <option value="other">Other</option>
                  <option value="none">None</option>
                </select></label>
              </div>
              <label>Vector connection<input placeholder="index, collection, DSN, or notes" value={profile.vectorConnection} onChange={(e) => update("vectorConnection", e.target.value)} /></label>
              <label className="secondary-button">
                <Upload size={16} />
                Upload docs/images
                <input type="file" multiple accept=".txt,.md,.json,.csv,.pdf,image/*,text/*,application/json" hidden onChange={(e) => addRagFiles(e.target.files)} />
              </label>
              {profile.uploadedContextFiles.length > 0 && <div className="file-list">{profile.uploadedContextFiles.map((file) => <span key={file}>{file}</span>)}</div>}
            </div>

            <label>Representative prompts ({prompts.length})<textarea rows={5} cols={1} wrap="soft" value={promptsText} onChange={(e) => setPromptsText(e.target.value)} /></label>
            <label className="secondary-button">
              <Upload size={16} />
              Upload JSON, MD, TXT
              <input type="file" accept=".json,.md,.txt,text/*,application/json" hidden onChange={async (e) => {
                const file = e.target.files?.[0];
                if (file) setPromptsText(await file.text());
              }} />
            </label>
          </div>
        </section>

        <section className="stage">
          <div className="workbench">
            <section className="panel">
              <div className="panel-title"><span><Globe2 size={16} /> Web Research</span><small>{browserUrl}</small></div>
              <div className="browser">
                <div className="browser-glow" />
                <p>{browserSummary}</p>
              </div>
            </section>
            <section className="panel">
              <div className="panel-title"><span><Layers3 size={16} /> Prometheux Context Layer</span><small>{contextGraph.evidenceCount ? `${contextGraph.evidenceCount} evidence packets` : "waiting for run"}</small></div>
              <ContextLayer graph={contextGraph} />
            </section>
            <section className="panel">
              <div className="panel-title">
                <span><Sparkles size={16} /> Recommendation</span>
                <a className="secondary-button" href={markdown ? `data:text/markdown;charset=utf-8,${encodeURIComponent(markdown)}` : undefined} download="find-my-model-report.md"><Download size={15} />Markdown</a>
              </div>
              <div className="report">
                {report ? (
                  <>
                    <div className="reco-card">
                      <div className="reco-head">
                        <span className="reco-tag"><Trophy size={13} /> Recommended model</span>
                        {report.primary.confidence && <span className="reco-confidence">{report.primary.confidence} confidence</span>}
                      </div>
                      <strong className="reco-model">{report.primary.provider} · {report.primary.model}</strong>
                      <div className="reco-meta">
                        {report.primary.cost && <span><DollarSign size={13} />{report.primary.cost}</span>}
                        {report.primary.latency && <span><Timer size={13} />{report.primary.latency}</span>}
                      </div>
                      {report.primary.quality && <p className="reco-note"><Sparkles size={13} />{report.primary.quality}</p>}
                      <button className="trial-cta" onClick={openTrial}>
                        <Rocket size={15} /> Deploy this stack — start free trial <ArrowRight size={15} />
                      </button>
                    </div>
                    {report.markdown}
                  </>
                ) : (running ? "Reasoning over your structured workload context…" : "Run the pipeline to generate your model architecture.")}
              </div>
            </section>
          </div>
          <aside className="panel">
            <div className="panel-title">
              <span><Activity size={16} /> Agent Trace</span>
              <button className="secondary-button" onClick={setupClickHouse} disabled={settingUpClickHouse || running}>
                {settingUpClickHouse ? <Loader2 size={15} /> : <Database size={15} />}
                ClickHouse
              </button>
            </div>
            <div className="trace-tabs">
              <div><Database size={16} />ClickHouse</div>
              <div><Globe2 size={16} />Tavily</div>
              <div><FileText size={16} />ADK</div>
              <div><Network size={16} />API</div>
            </div>
            <div className="model-catalog">
              <div className="model-catalog-title"><span><Cpu size={14} /> Model universe</span><strong>{modelCatalog.length || "pending"}</strong></div>
              <div className="model-list">
                {modelCatalog.length === 0 ? <div className="model-row muted">Your ranked model catalog appears here after analysis.</div> : modelCatalog.map((model) => {
                  const recommended = model.id === recoMatchId;
                  return (
                    <div className={`model-row ${recommended ? "recommended" : ""}`} key={model.id}>
                      <strong>{model.name}{recommended && <span className="reco-pill"><Trophy size={11} /> Recommended</span>}</strong>
                      <span>{model.provider} · {model.context ? `${model.context.toLocaleString()} ctx` : "ctx unknown"} · {(model.inputModalities ?? []).join("/")}{model.openWeights ? " · open weights" : ""}</span>
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="events">
              {events.length === 0 ? <div className="event">Agent events appear here.</div> : events.map((event, index) => (
                <div className={`event event-${event.type} ${event.type === "error" ? "error" : ""}`} key={`${event.timestamp}-${index}`}>
                  <span className="dot" />
                  <span>{event.text}</span>
                </div>
              ))}
            </div>
          </aside>
        </section>
      </div>

      {trialOpen && (
        <div className="modal-overlay" role="dialog" aria-modal="true" onClick={() => setTrialOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" aria-label="Close" onClick={() => setTrialOpen(false)}><X size={18} /></button>
            {trialDone ? (
              <div className="modal-success">
                <div className="modal-badge ok"><Check size={26} /></div>
                <h2>You&apos;re in. Welcome aboard.</h2>
                <p>Your 14-day Pro trial is active. We sent setup steps to <strong>{trialEmail || "your inbox"}</strong>.</p>
                <button className="trial-button wide" onClick={() => setTrialOpen(false)}>Start building <ArrowRight size={16} /></button>
              </div>
            ) : (
              <form className="modal-body" onSubmit={(e) => { e.preventDefault(); setTrialDone(true); }}>
                <div className="modal-badge"><Rocket size={24} /></div>
                <h2>Start your free trial</h2>
                <p>Ship the right model in minutes. Full access to the routing engine, grounded recommendations, and the live model catalog.</p>
                <label className="modal-field">
                  <Mail size={16} />
                  <input type="email" required placeholder="you@company.com" value={trialEmail} onChange={(e) => setTrialEmail(e.target.value)} />
                </label>
                <button className="trial-button wide" type="submit"><Rocket size={16} /> Start free trial</button>
                <div className="trust-row">
                  <span><ShieldCheck size={14} /> No credit card</span>
                  <span><Check size={14} /> 14-day Pro access</span>
                  <span><Check size={14} /> Cancel anytime</span>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
