import { Bot, CheckCircle2, Loader2, Radio, RefreshCw, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Card, Spinner } from "../../components/ui";
import { api, waitForTask } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { useToast } from "../../lib/toast";

interface Run { id: number; trigger: string; status: string; results: Record<string, { fetched?: number; added?: number; error?: string; skipped?: boolean } | number>; started_at: string; finished_at: string | null }
interface Data {
  job_sources: Record<string, { enabled: boolean; detail: string; open_jobs: number }>;
  jobs_by_source: Record<string, number>;
  nightly: { enabled: boolean; hour_utc: number; location: string; expire_days: number };
  runs: Run[]; ai: { enabled: boolean; model: string }; nebula: { enabled: boolean };
}
const RUN_COLOR: Record<string, string> = { ok: "green", partial: "orange", failed: "red", running: "blue" };

export default function Integrations() {
  const toast = useToast();
  const { data, loading, reload } = useApi<Data>("/admin/integrations");
  const [aiResult, setAiResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [gradOnly, setGradOnly] = useState(true);
  const [catalog, setCatalog] = useState<{ busy: boolean; msg: string | null }>({ busy: false, msg: null });
  const importCatalog = async () => {
    setCatalog({ busy: true, msg: "Starting…" });
    try {
      const t = await api.post<{ task_id: string }>(`/admin/catalog/import-nebula?graduate_only=${gradOnly}`);
      const r = await waitForTask(t.task_id, (s) => s.progress && setCatalog({ busy: true, msg: s.progress }), 30 * 60 * 1000) as Record<string, number>;
      setCatalog({ busy: false, msg: `Done: ${r.courses_in_nebula} courses on Nebula · ${r.added} added · ${r.updated} updated · ${r.prerequisite_links} prerequisite links` });
    } catch (e) { setCatalog({ busy: false, msg: (e as Error).message }); }
  };
  const running = data?.runs.some((r) => r.status === "running");
  useEffect(() => { if (!running) return; const t = setInterval(reload, 3000); return () => clearInterval(t); }, [running, reload]);
  if (loading && !data) return <Spinner />;
  if (!data) return null;
  const syncNow = async () => { try { await api.post("/admin/jobs/sync-now"); toast("Sync started"); reload(); } catch (e) { toast((e as Error).message, "error"); } };
  const testAi = async () => { setAiBusy(true); try { setAiResult(await api.post("/admin/ai/test")); } finally { setAiBusy(false); } };
  const fmt = (v: Run["results"][string]) => typeof v === "number" ? `${v} expired` : v.skipped ? "not configured" : v.error ? `error: ${v.error}` : `${v.fetched} fetched, ${v.added} new`;

  return (
    <div className="space-y-6">
      <Card title="Live job market sources" actions={<button className="btn-primary btn-sm" onClick={syncNow} disabled={running}>{running ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}{running ? "Syncing…" : "Sync now"}</button>}>
        <div className="grid gap-3 md:grid-cols-3">
          {Object.entries(data.job_sources).map(([k, v]) => (
            <div key={k} className="rounded-lg border border-slate-200 p-3 text-sm">
              <div className="flex items-center justify-between"><span className="font-semibold text-slate-800">{({ github: "GitHub lists", adzuna: "Adzuna", usajobs: "USAJobs" } as Record<string, string>)[k] ?? k}</span>
                {v.enabled ? <span className="chip bg-green-50 text-green-800"><CheckCircle2 className="h-3.5 w-3.5 text-green-600" aria-hidden />On</span> : <span className="chip bg-slate-100 text-slate-600"><XCircle className="h-3.5 w-3.5" aria-hidden />Off</span>}</div>
              <div className="mt-1 text-xs text-slate-500">{v.detail}</div>
              <div className="mt-2 text-xs"><b>{v.open_jobs}</b> open postings</div>
            </div>))}
        </div>
        <p className="mt-3 text-xs text-slate-500">
          {data.nightly.enabled ? `Automatic sync runs nightly after ${String(data.nightly.hour_utc).padStart(2, "0")}:00 UTC for ${data.nightly.location}.` : "Nightly sync is disabled (JOB_SYNC_ENABLED=false)."}
          {" "}Synced postings older than {data.nightly.expire_days} days are closed automatically. Total open by source: {Object.entries(data.jobs_by_source).map(([k, v]) => `${k} ${v}`).join(" · ")}.</p>
        {data.runs.length > 0 && (
          <table className="table-base mt-4"><thead><tr><th>Started</th><th>Trigger</th><th>Status</th><th>Results</th></tr></thead>
            <tbody>{data.runs.map((r) => (
              <tr key={r.id}><td className="whitespace-nowrap text-xs text-slate-500">{new Date(r.started_at).toLocaleString()}</td><td className="text-xs">{r.trigger}</td>
                <td><Badge color={RUN_COLOR[r.status]}>{r.status}</Badge></td>
                <td className="text-xs text-slate-600">{Object.entries(r.results).map(([k, v]) => <div key={k}><b>{k}</b>: {fmt(v)}</div>)}</td></tr>))}</tbody></table>)}
      </Card>
      <div className="grid gap-6 md:grid-cols-2">
        <Card title={<span className="flex items-center gap-2"><Bot className="h-4 w-4 text-flame-500" />Claude AI</span>}>
          <div className="space-y-3 text-sm">
            <div>{data.ai.enabled ? <>Configured · model <code className="rounded bg-slate-100 px-1">{data.ai.model}</code></> : "Not configured — the built-in engine is used. Set ANTHROPIC_API_KEY on the server."}</div>
            <button className="btn-ghost btn-sm" onClick={testAi} disabled={aiBusy}>{aiBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Bot className="h-4 w-4" />}Test connection</button>
            {aiResult && <div className={`rounded-lg p-2 text-xs ${aiResult.ok ? "bg-green-50 text-green-800" : "bg-amber-50 text-amber-800"}`}>{aiResult.message}</div>}
          </div>
        </Card>
        <Card title={<span className="flex items-center gap-2"><Radio className="h-4 w-4 text-flame-500" />UTD Nebula (live sections & grades)</span>}>
          <div className="space-y-3 text-sm">
            <div>{data.nebula.enabled ? "Configured — course details show live sections, grade distributions and official syllabi." : "Not configured — set NEBULA_API_KEY (request one from UTD Nebula Labs)."}</div>
            {data.nebula.enabled && (
              <div className="rounded-lg border border-slate-200 p-3">
                <div className="font-semibold text-slate-800">Full UTD catalog</div>
                <p className="text-xs text-slate-500">Adds every UTD course (title, description, credits, prerequisites) next to the curated JSOM programs. Safe to re-run; curated prerequisites are kept.</p>
                <label className="mt-2 flex items-center gap-2 text-xs"><input type="checkbox" className="accent-comet-600" checked={gradOnly} onChange={(e) => setGradOnly(e.target.checked)} />Graduate courses only</label>
                <button className="btn-primary btn-sm mt-2" onClick={importCatalog} disabled={catalog.busy}>{catalog.busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}Import from Nebula</button>
                {catalog.msg && <div className="mt-2 text-xs text-slate-600" role="status">{catalog.msg}</div>}
              </div>)}
          </div>
        </Card>
      </div>
    </div>
  );
}
