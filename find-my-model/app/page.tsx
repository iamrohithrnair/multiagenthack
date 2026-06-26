"use client";

import { useMemo, useState } from "react";
import { Brain, Database, DollarSign, Download, FileText, Globe2, Loader2, Network, Play, Search, Timer, Upload, Zap } from "lucide-react";
import type { RecommendationReport, WorkloadProfile } from "@/lib/types";

const samplePrompts = `Classify this customer support ticket as billing, account, bug, or feature request and return JSON.

Summarize the following help-center conversation into a short answer with cited source snippets.

Given the user's plan and invoices, extract renewal date, current tier, and likely churn risk.

The user uploaded a screenshot of an error. Identify the likely UI issue and next action.`;

type EventRow = { type: string; text: string; timestamp: number };

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
  if (type === "recommendation") return "Recommendation ready";
  if (type === "complete") return "Pipeline complete";
  return type;
}

export default function Home() {
  const [profile, setProfile] = useState<WorkloadProfile>({
    product: "Customer support chatbot",
    users: "SaaS customers and internal support agents",
    requestsPerDay: 500,
    latencySeconds: 3,
    budgetMonthlyUsd: 300,
    region: "US/EU",
    canSelfHost: true,
    privacy: "sensitive",
    longContext: true,
    vision: true,
    toolCalling: true,
    structuredOutput: true,
    streaming: true,
    notes: "Prefer low cost for simple tickets, higher quality for escalations.",
  });
  const [promptsText, setPromptsText] = useState(samplePrompts);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [browserSummary, setBrowserSummary] = useState("Browser/API research pane");
  const [browserUrl, setBrowserUrl] = useState("");
  const [report, setReport] = useState<RecommendationReport | null>(null);
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
            <button className="run-button" onClick={run} disabled={running || prompts.length === 0 || !profile.product.trim()}>
              {running ? <Loader2 size={17} className="spin" /> : <Play size={17} />}
              Analyze workload
            </button>
          </div>
        </div>
      </header>

      <div className="layout">
        <section className="panel">
          <div className="panel-title"><span><Brain size={16} /> Workload Interview</span></div>
          <div className="form">
            <label>What are you building?<input value={profile.product} onChange={(e) => update("product", e.target.value)} /></label>
            <label>Users<input value={profile.users} onChange={(e) => update("users", e.target.value)} /></label>
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
                ["canSelfHost", "Self-host"],
                ["longContext", "Long context"],
                ["vision", "Vision"],
                ["toolCalling", "Tools"],
                ["structuredOutput", "JSON output"],
                ["streaming", "Streaming"],
              ] as const).map(([key, label]) => (
                <label className="check" key={key}><input type="checkbox" checked={Boolean(profile[key])} onChange={(e) => update(key, e.target.checked)} />{label}</label>
              ))}
            </div>
            <label>Notes<textarea rows={3} value={profile.notes} onChange={(e) => update("notes", e.target.value)} /></label>
            <label>Representative prompts ({prompts.length})<textarea rows={9} value={promptsText} onChange={(e) => setPromptsText(e.target.value)} /></label>
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
