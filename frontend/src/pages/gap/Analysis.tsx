import { BadgeCheck, BookOpen, Database, Download, FileSpreadsheet, Lightbulb, RefreshCw, ScanSearch, Sparkles, TrendingUp } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Badge, Card, PageHeader, ScoreRing, Spinner, ErrorBox } from "../../components/ui";
import { api, download, waitForTask } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { STATUS, StatusLegend, StatusTag, type Status } from "../../lib/viz";
import { TargetSelect } from "./GapHome";
import { ReviewPanel, type EvidenceRow, type Review, type ReviewSummary } from "./ReviewPanel";
import { SampleSelect, type Provenance } from "./Samples";

interface SkillRow extends EvidenceRow { is_emerging: boolean }
interface Analysis {
  id: string; syllabus: { id: string; title: string; code: string | null; semester: string | null; pilot_approved: boolean; approved_by: string | null };
  sample_id: string | null; provenance?: Provenance; reviews: Record<string, Review>; review_summary: ReviewSummary; faculty_statuses: Record<string, string>;
  score: number; target: string; job_count: number; engine: string; created_at: string; summary: string;
  counts: Record<Status, number>; skills: SkillRow[]; gaps: SkillRow[]; strengths: { name: string; mentions: number; in_market: boolean }[];
  emerging: { name: string; demand: number; status: Status }[]; categories: { category: string; coverage: number; skills: number }[];
  recommendations: { title: string; detail: string; skills: string[]; source: string }[];
}

export default function Analysis() {
  const { id } = useParams();
  const nav = useNavigate();
  const { data: a, loading, error, setData } = useApi<Analysis>(`/gap/analyses/${id}`);
  const [target, setTarget] = useState<string | null>(null);
  const [sample, setSample] = useState<string | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  if (loading) return <Spinner />;
  if (error || !a) return <ErrorBox error={error ?? "Not found"} />;

  const sampleId = sample === undefined ? a.sample_id : sample;
  const rerun = async () => {
    setBusy(true);
    try {
      const r = await api.post<{ id?: string; task_id: string }>(`/gap/syllabi/${a.syllabus.id}/analyze`, sampleId ? { target: a.target, sample_id: sampleId } : { target: target ?? (a.sample_id ? "auto" : a.target) });
      const id = r.id ?? (await waitForTask(r.task_id)).analysis_id;
      nav(`/gap/analysis/${id}`);
    } finally { setBusy(false); }
  };
  const rs = a.review_summary;
  const file = (a.syllabus.code ?? a.syllabus.title).replace(/\s+/g, "_");

  return (
    <div className="space-y-6">
      <PageHeader icon={<ScanSearch className="h-5 w-5" />} title={`${a.syllabus.code ?? ""} ${a.syllabus.title}`}
        subtitle={`Gap report · ${a.syllabus.semester ?? ""} · ${new Date(a.created_at).toLocaleString()}`}
        actions={<>
          <button className="btn-ghost btn-sm" onClick={() => download(`/gap/analyses/${a.id}/export.pdf`, `CometGap-${file}.pdf`)}><Download className="h-4 w-4" />PDF</button>
          <button className="btn-ghost btn-sm" onClick={() => download(`/gap/analyses/${a.id}/export.xlsx`, `CometGap-${file}.xlsx`)}><FileSpreadsheet className="h-4 w-4" />Excel</button>
          <button className="btn-ghost btn-sm" onClick={() => download(`/gap/analyses/${a.id}/findings.csv`, `CometGap-findings-${file}.csv`)}><FileSpreadsheet className="h-4 w-4" />Findings CSV</button>
          <Link to={`/forge/new?analysis=${a.id}`} className="btn-accent btn-sm"><BookOpen className="h-4 w-4" />Fix gaps with CometForge</Link>
        </>} />

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <Card>
          <div className="flex flex-col items-center text-center">
            <ScoreRing value={a.score} size={150} label="mention-based" />
            <div className="mt-3 text-sm text-slate-600">vs. top {a.skills.length} skills in <b>{a.job_count}</b> {a.provenance?.sample ? <>postings in the job sample <b>{a.provenance.sample.name}</b></> : <><b>{a.target}</b> postings</>}</div>
            <div className="mt-3 w-full rounded-lg border border-comet-200 bg-comet-50 p-3 text-left text-sm">
              <div className="flex items-baseline justify-between"><span className="font-semibold text-comet-800">Faculty-reviewed coverage</span>
                <span className="text-xl font-bold text-comet-800">{rs.reviewed ? `${Math.round(rs.reviewed_score ?? 0)}%` : "—"}</span></div>
              <p className="mt-1 text-xs text-slate-600">{rs.reviewed
                ? <>{rs.reviewed} of {rs.total} skills reviewed ({Math.round(rs.reviewed_demand_share)}% of demand); unreviewed skills still use the mention signal.</>
                : "Review the skills below. The mention-based score only helps prioritize; faculty judge whether students practice each skill."}</p>
            </div>
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
            <div className="mt-4 w-full space-y-2 border-t border-slate-100 pt-4 text-left">
              <label className="label" htmlFor="sample">Documented job sample (optional)</label>
              <SampleSelect id="sample" value={sampleId ?? null} onChange={(v) => setSample(v)} />
            </div>
            <div className="mt-3 text-[11px] text-slate-500">Engine: {a.engine === "claude" ? "Claude AI" : "CometIQ built-in"}</div>
          </div>
        </Card>
        <div className="space-y-6">
          <Card title={<span className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-flame-500" />Summary</span>}>
            <p className="text-sm leading-relaxed text-slate-700">{a.summary}</p>
          </Card>
          <EvidenceCard a={a} onApproval={(syl) => setData({ ...a, syllabus: { ...a.syllabus, ...syl } })} />
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

      <ReviewPanel analysisId={a.id} rows={a.skills} jobCount={a.job_count} reviews={a.reviews} statuses={a.faculty_statuses}
        onChange={(reviews, review_summary) => setData({ ...a, reviews, review_summary })} />

      <div className="grid gap-6">
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

function EvidenceCard({ a, onApproval }: { a: Analysis; onApproval: (s: { pilot_approved: boolean; approved_by: string | null }) => void }) {
  const p = a.provenance;
  const [by, setBy] = useState("");
  const [editing, setEditing] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const setApproval = async (approved: boolean) => {
    setErr(null);
    try {
      const r = await api.post<{ pilot_approved: boolean; approved_by: string | null }>(`/gap/syllabi/${a.syllabus.id}/approval`, { approved, approved_by: by });
      onApproval({ pilot_approved: r.pilot_approved, approved_by: r.approved_by }); setEditing(false);
    } catch (e) { setErr((e as Error).message); }
  };
  return (
    <Card title={<span className="flex items-center gap-2"><Database className="h-4 w-4 text-comet-700" />Evidence behind this report</span>}>
      {p ? <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
        <div><dt className="text-xs font-semibold uppercase text-slate-500">Job sample</dt>
          <dd className="text-slate-800">{p.sample ? <><b>{p.sample.name}</b> <span className="text-xs text-slate-500">(frozen {new Date(p.sample.created_at).toLocaleDateString()})</span></> : <>All open <b>{a.target}</b> postings at analysis time</>}</dd></div>
        <div><dt className="text-xs font-semibold uppercase text-slate-500">Postings</dt><dd className="text-slate-800"><b>{p.total}</b> postings · posted {p.date_from ?? "?"} to {p.date_to ?? "?"}</dd></div>
        <div><dt className="text-xs font-semibold uppercase text-slate-500">Sources</dt><dd className="text-slate-800">{Object.entries(p.sources).map(([k, v]) => `${k} (${v})`).join(", ") || "—"}</dd></div>
        <div><dt className="text-xs font-semibold uppercase text-slate-500">Captured</dt><dd className="text-slate-800">{new Date(p.captured_at).toLocaleString()}</dd></div>
        {p.sample?.method && <div className="sm:col-span-2"><dt className="text-xs font-semibold uppercase text-slate-500">Sampling method</dt><dd className="text-slate-700">{p.sample.method}</dd></div>}
      </dl> : <p className="text-sm text-slate-500">This analysis predates evidence tracking. Re-run it to record the job sample.</p>}
      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3 text-sm">
        {a.syllabus.pilot_approved
          ? <><span className="chip bg-green-50 text-green-800"><BadgeCheck className="h-3.5 w-3.5" aria-hidden />Approved for the pilot</span>
              <span className="text-slate-600">by {a.syllabus.approved_by}</span>
              <button className="btn-ghost btn-sm" onClick={() => setApproval(false)}>Withdraw</button></>
          : editing
            ? <><label className="sr-only" htmlFor="approved-by">Approved by</label>
                <input id="approved-by" className="input max-w-xs" placeholder="Who approved it, e.g. Dr. Lee (instructor of record)" value={by} onChange={(e) => setBy(e.target.value)} />
                <button className="btn-primary btn-sm" onClick={() => setApproval(true)} disabled={by.trim().length < 3}>Save approval</button>
                <button className="btn-ghost btn-sm" onClick={() => setEditing(false)}>Cancel</button></>
            : <><span className="text-slate-600">Not approved for the pilot.</span><button className="btn-ghost btn-sm" onClick={() => setEditing(true)}>Record approval</button></>}
        {err && <span role="alert" className="text-red-700">{err}</span>}
      </div>
    </Card>
  );
}
