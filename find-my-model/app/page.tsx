"use client";

import { useMemo, useState } from "react";
import { Brain, Database, DollarSign, Download, FileText, Globe2, Layers3, Link2, Loader2, Mic2, Network, Play, Search, SlidersHorizontal, Timer, Upload, Zap } from "lucide-react";
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
type ContextGraph = { nodes: ContextNode[]; edges: ContextEdge[]; evidenceCount?: number };

const defaultContextGraph: ContextGraph = {
  nodes: [
    { id: "site", label: "Product website", kind: "input", x: 14, y: 50 },
    { id: "prometheux", label: "Prometheux context agent", kind: "agent", x: 36, y: 32 },
    { id: "models", label: "models.dev catalog", kind: "source", x: 36, y: 68 },
    { id: "recommendation", label: "Recommendation", kind: "output", x: 84, y: 50 },
  ],
  edges: [
    { from: "site", to: "prometheux" },
    { from: "prometheux", to: "recommendation" },
    { from: "models", to: "recommendation" },
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
    return `${d.adapter}: ${d.provider ?? d.title}`;
  }
  if (type === "browser_snapshot") {
    const d = data as { provider?: string; url?: string };
    return `web action: ${d.provider ?? d.url}`;
  }
  if (type === "model_catalog") {
    const d = data as { source?: string; count?: number };
    return `${d.source ?? "models.dev"}: ${d.count ?? 0} models ranked`;
  }
  if (type === "context_layer") {
    const d = data as { evidenceCount?: number };
    return `Prometheux context graph ready (${d.evidenceCount ?? 0} evidence packets)`;
  }
  if (type === "recommendation") return "Recommendation ready";
  if (type === "complete") return "Pipeline complete";
  return type;
}

function ContextLayer({ graph }: { graph: ContextGraph }) {
  const nodes = new Map(graph.nodes.map((node) => [node.id, node]));
  return (
    <div className="context-layer">
      <svg className="context-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        {graph.edges.map((edge) => {
          const from = nodes.get(edge.from);
          const to = nodes.get(edge.to);
          if (!from || !to) return null;
          return <line key={`${edge.from}-${edge.to}`} x1={from.x + 8} y1={from.y} x2={to.x} y2={to.y} />;
        })}
      </svg>
      {graph.nodes.map((node) => (
        <div className={`context-node context-${node.kind}`} style={{ left: `${node.x}%`, top: `${node.y}%` }} key={node.id}>
          <span>{node.kind}</span>
          <strong>{node.label}</strong>
        </div>
      ))}
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
  const prompts = useMemo(() => parsePrompts(promptsText), [promptsText]);
  const markdown = report?.markdown ?? "";

  const update = <K extends keyof WorkloadProfile>(key: K, value: WorkloadProfile[K]) => {
    setProfile((current) => ({ ...current, [key]: value }));
  };

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
          setEvents((current) => [{ type: msg.type, text: eventText(msg.type, msg.data), timestamp: msg.timestamp }, ...current].slice(0, 100));
          if (msg.type === "browser_snapshot") {
            setBrowserSummary(msg.data.summary ?? msg.data.provider ?? "Research update");
            setBrowserUrl(msg.data.url ?? "");
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
              <p className="eyebrow">Find My Model</p>
              <h1>Model routing console for real workloads.</h1>
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
              Analyze workload
            </button>
          </div>
        </div>
      </header>

      <div className="layout">
        <section className="panel">
          <div className="panel-title"><span><Brain size={16} /> Product Input</span></div>
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
                <span><Network size={16} /> Recommendation</span>
                <a className="secondary-button" href={markdown ? `data:text/markdown;charset=utf-8,${encodeURIComponent(markdown)}` : undefined} download="find-my-model-report.md"><Download size={15} />Markdown</a>
              </div>
              <div className="report">{report ? report.markdown : (running ? "ADK is reasoning over structured context" : "Run the pipeline to generate the architecture")}</div>
            </section>
          </div>
          <aside className="panel">
            <div className="panel-title">
              <span><Search size={16} /> Agent Trace</span>
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
              <div className="model-catalog-title"><span><Mic2 size={14} /> Model universe</span><strong>{modelCatalog.length || "pending"}</strong></div>
              <div className="model-list">
                {modelCatalog.length === 0 ? <div className="model-row muted">models.dev catalog appears here after analysis.</div> : modelCatalog.map((model) => (
                  <div className="model-row" key={model.id}>
                    <strong>{model.name}</strong>
                    <span>{model.provider} · {model.context ? `${model.context.toLocaleString()} ctx` : "ctx unknown"} · {(model.inputModalities ?? []).join("/")}{model.openWeights ? " · open weights" : ""}</span>
                  </div>
                ))}
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
    </main>
  );
}
