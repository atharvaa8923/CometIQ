import { BookOpen, Download, FileSpreadsheet, Lightbulb, RefreshCw, ScanSearch, Sparkles, TrendingUp } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Badge, Card, PageHeader, ScoreRing, Spinner, ErrorBox } from "../../components/ui";
import { api, download, waitForTask } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { PRIORITY_COLOR, STATUS, StatusLegend, StatusTag, type Status } from "../../lib/viz";
import { TargetSelect } from "./GapHome";

interface SkillRow { skill_id: number; name: string; category: string; is_emerging: boolean; demand: number; job_count: number; status: Status; priority: string; mentions: number; evidence: string | null; taught_in?: string[] }
interface Analysis {
  id: string; syllabus: { id: string; title: string; code: string | null; semester: string | null };
  score: number; target: string; job_count: number; engine: string; created_at: string; summary: string;
  counts: Record<Status, number>; skills: SkillRow[]; gaps: SkillRow[]; strengths: { name: string; mentions: number; in_market: boolean }[];
  emerging: { name: string; demand: number; status: Status }[]; categories: { category: string; coverage: number; skills: number }[];
  recommendations: { title: string; detail: string; skills: string[]; source: string }[];
}

export default function Analysis() {
  const { id } = useParams();
  const nav = useNavigate();
  const { data: a, loading, error } = useApi<Analysis>(`/gap/analyses/${id}`);
  const [target, setTarget] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (loading) return <Spinner />;
  if (error || !a) return <ErrorBox error={error ?? "Not found"} />;

  const rerun = async () => {
    setBusy(true);
    try {
      const r = await api.post<{ id?: string; task_id: string }>(`/gap/syllabi/${a.syllabus.id}/analyze`, { target: target ?? a.target });
      const id = r.id ?? (await waitForTask(r.task_id)).analysis_id;
      nav(`/gap/analysis/${id}`);
    } finally { setBusy(false); }
  };
  const file = (a.syllabus.code ?? a.syllabus.title).replace(/\s+/g, "_");

  return (
    <div className="space-y-6">
      <PageHeader icon={<ScanSearch className="h-5 w-5" />} title={`${a.syllabus.code ?? ""} ${a.syllabus.title}`}
        subtitle={`Gap report · ${a.syllabus.semester ?? ""} · ${new Date(a.created_at).toLocaleString()}`}
        actions={<>
          <button className="btn-ghost btn-sm" onClick={() => download(`/gap/analyses/${a.id}/export.pdf`, `CometGap-${file}.pdf`)}><Download className="h-4 w-4" />PDF</button>
          <button className="btn-ghost btn-sm" onClick={() => download(`/gap/analyses/${a.id}/export.xlsx`, `CometGap-${file}.xlsx`)}><FileSpreadsheet className="h-4 w-4" />Excel</button>
          <Link to={`/forge/new?analysis=${a.id}`} className="btn-accent btn-sm"><BookOpen className="h-4 w-4" />Fix gaps with CometForge</Link>
        </>} />

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <Card>
          <div className="flex flex-col items-center text-center">
            <ScoreRing value={a.score} size={150} label="industry coverage" />
            <div className="mt-3 text-sm text-slate-600">vs. top {a.skills.length} skills in <b>{a.job_count}</b> <b>{a.target}</b> postings</div>
            <div className="mt-4 grid w-full grid-cols-3 gap-2 text-center">
              {(Object.keys(STATUS) as Status[]).map((s) => { const x = STATUS[s]; return (
                <div key={s} className={`rounded-lg ${x.bg} p-2`}><div className="flex items-center justify-center gap-1 text-lg font-bold text-slate-800"><x.Icon className="h-4 w-4" style={{ color: x.color }} aria-hidden />{a.counts[s]}</div>
                  <div className={`text-[11px] font-semibold ${x.text}`}>{x.label}</div></div>); })}
            </div>
            <div className="mt-5 w-full space-y-2 border-t border-slate-100 pt-4 text-left">
              <label className="label">Compare against</label>
              <TargetSelect value={target ?? a.target} onChange={setTarget} />
              <button className="btn-ghost btn-sm w-full" onClick={rerun} disabled={busy}><RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} />Re-run analysis</button>
            </div>
            <div className="mt-3 text-[11px] text-slate-500">Engine: {a.engine === "claude" ? "Claude AI" : "CometIQ built-in"}</div>
          </div>
        </Card>
        <div className="space-y-6">
          <Card title={<span className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-flame-500" />Summary</span>}>
            <p className="text-sm leading-relaxed text-slate-700">{a.summary}</p>
          </Card>
          <Card title={<span className="flex items-center gap-2"><Lightbulb className="h-4 w-4 text-flame-500" />Actionable insights for faculty</span>}>
            <ol className="space-y-3">
              {a.recommendations.map((r, i) => (
                <li key={i} className="flex gap-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-comet-700 text-xs font-bold text-white">{i + 1}</span>
                  <div><div className="font-semibold text-slate-800">{r.title}</div><div className="text-sm text-slate-600">{r.detail}</div></div>
                </li>))}
            </ol>
          </Card>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <Card title="Industry skills vs. course content" actions={<StatusLegend />}>
          <div className="space-y-1">
            <div className="grid grid-cols-[minmax(150px,220px)_1fr_90px] gap-3 px-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500"><span>Skill</span><span>Share of postings</span><span>In syllabus</span></div>
            {a.skills.map((s) => (
              <div key={s.name} className="group grid grid-cols-[minmax(150px,220px)_1fr_90px] items-center gap-3 rounded px-1 py-1 text-sm hover:bg-slate-50"
                title={`${s.name} — ${Math.round(s.demand * 100)}% weighted demand, ${s.job_count} postings, priority ${s.priority}. ${s.mentions ? `Mentioned ${s.mentions}× in syllabus${s.evidence ? `: “${s.evidence}”` : ""}` : "Not found in syllabus"}`}>
                <div className="truncate font-medium text-slate-700">{s.name}{s.is_emerging && <span className="ml-1 text-[10px] font-bold text-flame-600">NEW</span>}</div>
                <div className="flex items-center gap-2">
                  <div className="h-2.5 flex-1 rounded-r bg-slate-100"><div className="h-2.5 rounded-r" style={{ width: `${Math.min(100, s.demand * 100)}%`, background: STATUS[s.status].color }} /></div>
                  <span className="w-9 text-right text-xs text-slate-500">{Math.round(s.demand * 100)}%</span>
                </div>
                <StatusTag s={s.status} />
              </div>))}
          </div>
        </Card>
        <div className="space-y-6">
          <Card title="Coverage by skill area">
            <div className="space-y-2.5">
              {a.categories.map((c) => (
                <div key={c.category} title={`${c.category}: ${c.coverage}% of demand covered (${c.skills} skills)`}>
                  <div className="mb-0.5 flex justify-between text-xs"><span className="font-medium text-slate-700">{c.category}</span><span className="text-slate-500">{Math.round(c.coverage)}%</span></div>
                  <div className="h-2 rounded-r bg-slate-100"><div className="h-2 rounded-r bg-comet-600" style={{ width: `${c.coverage}%` }} /></div>
                </div>))}
            </div>
          </Card>
          <Card title={<span className="flex items-center gap-2"><TrendingUp className="h-4 w-4 text-flame-500" />Emerging technologies</span>}>
            {a.emerging.length ? <ul className="space-y-2">{a.emerging.map((e) => (
              <li key={e.name} className="flex items-center justify-between gap-2 text-sm"><span>{e.name} <span className="text-xs text-slate-500">{Math.round(e.demand * 100)}%</span></span><StatusTag s={e.status} /></li>))}</ul>
              : <p className="text-sm text-slate-500">No emerging technologies in this market segment yet.</p>}
          </Card>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Priority gaps">
          <table className="table-base"><thead><tr><th>Skill</th><th>Priority</th><th>Already taught in</th></tr></thead>
            <tbody>{a.gaps.slice(0, 15).map((g) => (
              <tr key={g.name}><td><div className="font-medium">{g.name}</div><div className="text-xs text-slate-500">{g.category}</div></td>
                <td><Badge color={PRIORITY_COLOR[g.priority]}>{g.priority}</Badge></td>
                <td className="text-xs">{g.taught_in?.length ? g.taught_in.join(", ") : <span className="text-slate-500">Nowhere in catalog</span>}</td></tr>))}</tbody></table>
        </Card>
        <Card title="What this course already teaches">
          <div className="flex flex-wrap gap-1.5">
            {a.strengths.map((s) => <Badge key={s.name} color={s.in_market ? "green" : "slate"} title={`${s.mentions} mentions${s.in_market ? " · requested by employers" : ""}`}>{s.name}</Badge>)}
          </div>
          <p className="mt-3 text-xs text-slate-500">Green = also requested in current postings.</p>
        </Card>
      </div>
    </div>
  );
}
