import { ArrowRight, FileUp, Gavel, GitCompare, History, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Badge, Card, Empty, ErrorBox, Field, Modal, PageHeader, Spinner, Tabs } from "../../components/ui";
import { api, waitForTask } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { StatusTag, type Status } from "../../lib/viz";
import type { Inputs } from "./Analysis";
import { DECISION_STATUS, type Decision } from "./ReviewPanel";
import { SampleSelect } from "./Samples";

interface Version { id: string; version: number; semester: string | null; filename: string | null; created_at: string; change_note: string | null; text_hash: string; skill_count: number; engine: string; created_by: string | null }
interface Report { id: string; created_at: string; score: number; target: string; job_count: number; inputs: Inputs }
interface Effects { course_revision: number; demand_change: number; method_update: number }
interface Step { from: { analysis_id: string; score: number; syllabus_version: number; semester: string | null; created_at: string }; to: Step["from"]; total: number; effects: Effects; skills_changed: number }
interface HistoryData { syllabus: { id: string; code: string | null; title: string; semester: string | null; latest: { id: string } | null }; versions: Version[]; reports: Report[]; steps: Step[]; scoring_version: string; taxonomy_version: string }
interface Comparison {
  available: boolean; reason?: string; total: number; effects: Effects; from: Step["from"]; to: Step["from"];
  method: { scoring_from: string; scoring_to: string; taxonomy_from: string; taxonomy_to: string };
  syllabus: { changed: boolean; same_version: boolean; added: string[]; removed: string[]; added_count: number; removed_count: number };
  sample: { same: boolean; postings_in_both: number; from: SampleSum; to: SampleSum };
  catalog: { available: boolean; changed?: boolean; catalog_year?: string; catalog_year_from?: string; catalog_year_to?: string; title_changed?: boolean; description_changed?: boolean; prerequisites_added?: string[]; prerequisites_removed?: string[] };
  skills: { skill: string; status_from: Status | null; status_to: Status | null; demand_from: number | null; demand_to: number | null; mentions_from: number; mentions_to: number; in_top_from: boolean; in_top_to: boolean; reasons: string[] }[];
}
interface SampleSum { name: string; kind: string; total: number; date_from: string | null; date_to: string | null; sources: Record<string, number> }

// Categorical slots 1–3 (validated: CVD ΔE 9.2, normal 27.6; aqua < 3:1 so every bar carries a visible text label)
const EFFECT = {
  course_revision: { label: "Course revision", color: "#2a78d6", help: "the syllabus changed" },
  demand_change: { label: "Demand change", color: "#eb6834", help: "the job sample changed" },
  method_update: { label: "Method update", color: "#1baf7a", help: "scoring or the skill list changed" },
} as const;
type EffectKey = keyof typeof EFFECT;
const REASON_COLOR: Record<string, string> = { "course revision": "blue", "demand change": "orange", "method update": "green" };
const fmt = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v).toFixed(1)}`;

export default function CourseHistory() {
  const { sid } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as "time" | "decisions" | "proposed") ?? "time";
  const { data, loading, error, reload } = useApi<HistoryData>(`/gap/syllabi/${sid}/history`);
  const [upload, setUpload] = useState(false);
  if (loading && !data) return <Spinner />;
  if (error || !data) return <ErrorBox error={error ?? "Not found"} />;
  const s = data.syllabus;
  return (
    <div className="space-y-6">
      <PageHeader icon={<History className="h-5 w-5" />} title={`${s.code ?? ""} ${s.title}`} subtitle="Course history: versions, decisions and proposed changes"
        actions={<>
          {s.latest && <Link to={`/gap/analysis/${s.latest.id}`} className="btn-ghost btn-sm">Latest report</Link>}
          <button className="btn-primary btn-sm" onClick={() => setUpload(true)}><FileUp className="h-4 w-4" />Upload new semester version</button>
        </>} />
      <Tabs value={tab} onChange={(t) => setParams({ tab: t })} tabs={[{ id: "time", label: "Changes over time" }, { id: "decisions", label: "Decisions" }, { id: "proposed", label: "Proposed changes" }]} />
      {tab === "time" && <OverTime data={data} />}
      {tab === "decisions" && <Decisions sid={s.id} />}
      {tab === "proposed" && <Proposed sid={s.id} />}
      <UploadVersion open={upload} onClose={() => setUpload(false)} sid={s.id} onDone={() => { setUpload(false); reload(); }} />
    </div>
  );
}

// ── Changes over time ──────────────────────────────────────────────────────────
function OverTime({ data }: { data: HistoryData }) {
  const recorded = data.reports.filter((r) => r.inputs.recorded);
  const [pair, setPair] = useState<[string, string] | null>(null);
  const [a, setA] = useState(recorded.at(-2)?.id ?? "");
  const [b, setB] = useState(recorded.at(-1)?.id ?? "");
  const label = (r: Report) => `v${r.inputs.syllabus?.version ?? "?"} ${r.inputs.syllabus?.semester ?? ""} · ${new Date(r.created_at).toLocaleDateString()} · ${Math.round(r.score)}%`;
  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <Card title="Mention-based coverage over time">
          {recorded.length ? <Timeline reports={recorded} /> : <p className="text-sm text-slate-500">No versioned reports yet. Re-run the analysis to start recording inputs.</p>}
        </Card>
        <Card title={<span className="flex items-center gap-2"><GitCompare className="h-4 w-4 text-comet-700" />Compare two reports</span>}>
          {recorded.length < 2 ? <p className="text-sm text-slate-500">Needs at least two versioned reports. Upload a new semester version or re-run with another job sample.</p> : (
            <div className="space-y-3">
              <Field label="From"><select className="input" value={a} onChange={(e) => setA(e.target.value)}>{recorded.map((r) => <option key={r.id} value={r.id}>{label(r)}</option>)}</select></Field>
              <Field label="To"><select className="input" value={b} onChange={(e) => setB(e.target.value)}>{recorded.map((r) => <option key={r.id} value={r.id}>{label(r)}</option>)}</select></Field>
              <button className="btn-primary btn-sm w-full" disabled={a === b} onClick={() => setPair([a, b])}>Explain the change</button>
            </div>)}
        </Card>
      </div>
      {pair && <CompareDetail a={pair[0]} b={pair[1]} />}
      <Card title="What changed between consecutive reports">
        {!data.steps.length ? <p className="text-sm text-slate-500">Nothing to compare yet.</p> : (
          <ul className="space-y-4">{[...data.steps].reverse().map((st) => (
            <li key={st.to.analysis_id} className="rounded-lg border border-slate-200 p-3">
              <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
                <b>v{st.from.syllabus_version} {st.from.semester}</b> ({Math.round(st.from.score)}%) <ArrowRight className="h-4 w-4 text-slate-500" aria-hidden />
                <b>v{st.to.syllabus_version} {st.to.semester}</b> ({Math.round(st.to.score)}%)
                <span className="font-semibold text-slate-800">{fmt(st.total)} points</span>
                <span className="text-xs text-slate-500">{new Date(st.to.created_at).toLocaleDateString()} · {st.skills_changed} skill changes</span>
                <button className="btn-ghost btn-sm ml-auto" onClick={() => setPair([st.from.analysis_id, st.to.analysis_id])}>Details</button>
              </div>
              <Attribution effects={st.effects} />
            </li>))}</ul>)}
      </Card>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Syllabus versions" padded={false}>
          <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Syllabus versions">
            <table className="table-base"><thead><tr><th>Version</th><th>Semester</th><th>Saved</th><th>Change note</th><th>Skills</th></tr></thead>
              <tbody>{[...data.versions].reverse().map((v) => (
                <tr key={v.id}><td><b>v{v.version}</b><div className="font-mono text-[11px] text-slate-500">{v.text_hash}</div></td><td>{v.semester ?? "—"}</td>
                  <td className="text-xs">{new Date(v.created_at).toLocaleDateString()}{v.created_by ? <div className="text-slate-500">{v.created_by}</div> : null}</td>
                  <td className="text-sm">{v.change_note ?? <span className="text-slate-500">—</span>}</td><td>{v.skill_count}</td></tr>))}</tbody></table>
          </div>
        </Card>
        <Card title="Reports and their inputs" padded={false}>
          <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Reports">
            <table className="table-base"><thead><tr><th>Report</th><th>Score</th><th>Inputs</th></tr></thead>
              <tbody>{[...data.reports].reverse().map((r) => (
                <tr key={r.id}><td><Link className="font-medium text-comet-700 hover:underline" to={`/gap/analysis/${r.id}`}>{new Date(r.created_at).toLocaleString()}</Link></td>
                  <td>{Math.round(r.score)}%</td>
                  <td className="text-xs">{r.inputs.recorded
                    ? <>Syllabus v{r.inputs.syllabus?.version} · {r.inputs.sample?.kind === "auto" ? `${r.target} snapshot` : r.inputs.sample?.name} ({r.inputs.sample?.total}) · catalog {r.inputs.catalog?.catalog_year ?? "n/a"} · scoring {r.inputs.scoring_version}</>
                    : <span className="text-slate-500">Not recorded (made before versioning)</span>}</td></tr>))}</tbody></table>
          </div>
        </Card>
      </div>
    </div>
  );
}

function Attribution({ effects }: { effects: Effects }) {
  const [hover, setHover] = useState<EffectKey | null>(null);
  const max = Math.max(5, ...Object.values(effects).map(Math.abs));
  return (
    <div>
      <div className="space-y-1.5" onMouseLeave={() => setHover(null)}>
        {(Object.keys(EFFECT) as EffectKey[]).map((k) => {
          const v = effects[k], w = (Math.abs(v) / max) * 50;
          return (
            <div key={k} className="grid grid-cols-[130px_1fr_60px] items-center gap-2 text-sm" onMouseEnter={() => setHover(k)} onFocus={() => setHover(k)}
              tabIndex={0} aria-label={`${EFFECT[k].label}: ${fmt(v)} points (${EFFECT[k].help})`}>
              <span className="text-slate-700">{EFFECT[k].label}</span>
              <div className="relative h-5">
                <div className="absolute inset-y-0 left-1/2 w-px bg-slate-300" aria-hidden />
                {v !== 0 && <div className={`absolute inset-y-1 ${v > 0 ? "rounded-r" : "rounded-l"}`}
                  style={{ background: EFFECT[k].color, left: v > 0 ? "50%" : `${50 - w}%`, width: `${w}%`, minWidth: 2 }} />}
              </div>
              <span className="text-right font-semibold tabular-nums text-slate-800">{fmt(v)}</span>
            </div>);
        })}
      </div>
      <p className="mt-1 h-4 text-xs text-slate-600" aria-live="polite">{hover ? `${EFFECT[hover].label}: ${fmt(effects[hover])} points because ${EFFECT[hover].help}.` : "Points of coverage. Hover a row for what it means."}</p>
    </div>
  );
}

function Timeline({ reports }: { reports: Report[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 640, H = 220, L = 36, R = 16, T = 14, B = 46;
  const x = (i: number) => (reports.length === 1 ? (L + W - R) / 2 : L + (i * (W - L - R)) / (reports.length - 1));
  const y = (v: number) => T + (1 - v / 100) * (H - T - B);
  const pts = reports.map((r, i) => `${x(i)},${y(r.score)}`).join(" ");
  const h = hover !== null ? reports[hover] : null;
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="group" aria-label={`Coverage across ${reports.length} reports, from ${Math.round(reports[0].score)}% to ${Math.round(reports.at(-1)!.score)}%`}>
        {[0, 25, 50, 75, 100].map((g) => <g key={g}><line x1={L} x2={W - R} y1={y(g)} y2={y(g)} stroke="#e7e5e4" strokeWidth={1} />
          <text x={L - 6} y={y(g) + 4} textAnchor="end" fontSize="11" fill="#57534e">{g}%</text></g>)}
        <polyline points={pts} fill="none" stroke="#2a78d6" strokeWidth={2} strokeLinejoin="round" />
        {reports.map((r, i) => (
          <g key={r.id}>
            <circle cx={x(i)} cy={y(r.score)} r={hover === i ? 6 : 4} fill="#2a78d6" stroke="#fff" strokeWidth={2} />
            <circle cx={x(i)} cy={y(r.score)} r={14} fill="transparent" tabIndex={0} role="button" aria-label={`v${r.inputs.syllabus?.version} ${r.inputs.syllabus?.semester ?? ""}: ${r.score}%`}
              onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(i)} onBlur={() => setHover(null)} />
            <text x={x(i)} y={H - B + 18} textAnchor="middle" fontSize="11" fill="#44403c">v{r.inputs.syllabus?.version}</text>
            <text x={x(i)} y={H - B + 32} textAnchor="middle" fontSize="10" fill="#57534e">{new Date(r.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</text>
          </g>))}
        <text x={x(reports.length - 1)} y={y(reports.at(-1)!.score) - 10} textAnchor="end" fontSize="12" fontWeight="600" fill="#1c1917">{Math.round(reports.at(-1)!.score)}%</text>
      </svg>
      {h && <div className="pointer-events-none absolute right-2 top-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow">
        <div className="font-semibold text-slate-800">{h.score}% · syllabus v{h.inputs.syllabus?.version} {h.inputs.syllabus?.semester ?? ""}</div>
        <div className="text-slate-600">{new Date(h.created_at).toLocaleString()}</div>
        <div className="text-slate-600">Sample: {h.inputs.sample?.kind === "auto" ? `${h.target} snapshot` : h.inputs.sample?.name} ({h.inputs.sample?.total} postings)</div>
        <div className="text-slate-600">Scoring {h.inputs.scoring_version} · catalog {h.inputs.catalog?.catalog_year ?? "n/a"}</div>
      </div>}
    </div>
  );
}

function CompareDetail({ a, b }: { a: string; b: string }) {
  const { data: c, loading } = useApi<Comparison>(`/gap/compare?a=${a}&b=${b}`);
  if (loading || !c) return <Spinner />;
  if (!c.available) return <Card><p className="text-sm text-slate-600">{c.reason}</p></Card>;
  return (
    <Card title={`v${c.from.syllabus_version} ${c.from.semester ?? ""} (${Math.round(c.from.score)}%) → v${c.to.syllabus_version} ${c.to.semester ?? ""} (${Math.round(c.to.score)}%): ${fmt(c.total)} points`}>
      <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        <div>
          <Attribution effects={c.effects} />
          <p className="mt-2 text-xs text-slate-500">Each part is measured by recomputing the score with one input swapped and everything else held fixed; the three parts add up to the total change.</p>
        </div>
        <dl className="space-y-2 text-sm">
          <div><dt className="font-semibold text-slate-700">Syllabus</dt><dd className="text-slate-600">{c.syllabus.same_version ? "Same version." : c.syllabus.changed ? `${c.syllabus.added_count} lines added, ${c.syllabus.removed_count} removed.` : "New version, same text."}</dd></div>
          <div><dt className="font-semibold text-slate-700">Job sample</dt><dd className="text-slate-600">{c.sample.same ? `Same postings (${c.sample.to.total}).`
            : `${c.sample.from.total} → ${c.sample.to.total} postings (${c.sample.postings_in_both} in both) · ${c.sample.from.date_from ?? "?"}–${c.sample.from.date_to ?? "?"} → ${c.sample.to.date_from ?? "?"}–${c.sample.to.date_to ?? "?"}`}</dd></div>
          <div><dt className="font-semibold text-slate-700">Catalog</dt><dd className="text-slate-600">{!c.catalog.available ? "Course not in the catalog." : !c.catalog.changed ? `Unchanged (${c.catalog.catalog_year ?? "year n/a"}).`
            : [c.catalog.catalog_year_from !== c.catalog.catalog_year_to && `Catalog year ${c.catalog.catalog_year_from} → ${c.catalog.catalog_year_to}`, c.catalog.title_changed && "title changed", c.catalog.description_changed && "description changed",
               c.catalog.prerequisites_added?.length && `prerequisites added: ${c.catalog.prerequisites_added.join(", ")}`, c.catalog.prerequisites_removed?.length && `prerequisites removed: ${c.catalog.prerequisites_removed.join(", ")}`].filter(Boolean).join("; ")}</dd></div>
          <div><dt className="font-semibold text-slate-700">Method</dt><dd className="text-slate-600">{c.method.scoring_from === c.method.scoring_to && c.method.taxonomy_from === c.method.taxonomy_to ? `Same scoring (${c.method.scoring_to}) and skill list.`
            : `Scoring ${c.method.scoring_from} → ${c.method.scoring_to}; skill list ${c.method.taxonomy_from} → ${c.method.taxonomy_to}`}</dd></div>
        </dl>
      </div>
      {c.skills.length > 0 && (
        <div className="mt-5 overflow-x-auto" tabIndex={0} role="region" aria-label="Skill changes">
          <table className="table-base"><thead><tr><th>Skill</th><th>Before</th><th>After</th><th>Mentions</th><th>Share of postings</th><th>Why</th></tr></thead>
            <tbody>{c.skills.map((x) => (
              <tr key={x.skill}><td className="font-medium">{x.skill}</td>
                <td>{x.status_from ? <StatusTag s={x.status_from} /> : <span className="text-xs text-slate-500">not in top skills</span>}</td>
                <td>{x.status_to ? <StatusTag s={x.status_to} /> : <span className="text-xs text-slate-500">not in top skills</span>}</td>
                <td className="tabular-nums">{x.mentions_from} → {x.mentions_to}</td>
                <td className="tabular-nums">{x.demand_from !== null ? `${Math.round(x.demand_from * 100)}%` : "—"} → {x.demand_to !== null ? `${Math.round(x.demand_to * 100)}%` : "—"}</td>
                <td>{x.reasons.map((r) => <Badge key={r} color={REASON_COLOR[r]}>{r}</Badge>)}</td></tr>))}</tbody></table>
        </div>)}
      {c.syllabus.changed && (
        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          <div><div className="label">Lines added</div><ul className="space-y-1 text-sm">{c.syllabus.added.map((l, i) => <li key={i} className="rounded border-l-4 border-green-600 bg-green-50 px-2 py-1">{l}</li>)}</ul></div>
          <div><div className="label">Lines removed</div>{c.syllabus.removed.length ? <ul className="space-y-1 text-sm">{c.syllabus.removed.map((l, i) => <li key={i} className="rounded border-l-4 border-red-600 bg-red-50 px-2 py-1">{l}</li>)}</ul> : <p className="text-sm text-slate-500">None</p>}</div>
        </div>)}
    </Card>
  );
}

function UploadVersion({ open, onClose, sid, onDone }: { open: boolean; onClose: () => void; sid: string; onDone: () => void }) {
  const [semester, setSemester] = useState("");
  const [note, setNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [sample, setSample] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const submit = async () => {
    if (!file) return;
    setBusy(true); setErr(null);
    const fd = new FormData();
    fd.append("semester", semester); fd.append("change_note", note); fd.append("file", file);
    if (sample) fd.append("sample_id", sample);
    try { const r = await api.post<{ task_id: string }>(`/gap/syllabi/${sid}/versions`, fd); await waitForTask(r.task_id); onDone(); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Modal open={open} onClose={onClose} title="Upload a new semester version">
      <div className="space-y-3">
        <p className="text-sm text-slate-600">The current version and every report based on it are kept. The new version is analyzed against the same documented job sample unless you choose another.</p>
        <Field label="Semester"><input className="input" value={semester} onChange={(e) => setSemester(e.target.value)} placeholder="Fall 2027" /></Field>
        <Field label="What changed (optional)"><input className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Added a Python unit and a graded lab" /></Field>
        <Field label="Syllabus file (PDF, DOCX or TXT)"><input type="file" accept=".pdf,.docx,.txt" className="input" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></Field>
        <Field label="Job sample (optional)"><SampleSelect value={sample} onChange={setSample} /></Field>
        {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
        <button className="btn-primary w-full" onClick={submit} disabled={busy || !file || semester.trim().length < 4}>{busy ? "Analyzing…" : "Save version and analyze"}</button>
      </div>
    </Modal>
  );
}

// ── Decisions ──────────────────────────────────────────────────────────────────
function Decisions({ sid }: { sid: string }) {
  const { data, loading, reload } = useApi<{ active: Decision[]; history: Decision[]; options: Record<string, string> }>(`/gap/syllabi/${sid}/decisions`);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (loading && !data) return <Spinner />;
  if (!data) return null;
  const accepted = data.active.filter((d) => d.decision === "add_here" && d.status !== "implemented");
  const draft = async () => {
    setBusy(true); setErr(null);
    try { const r = await api.post<{ task_id: string }>(`/gap/syllabi/${sid}/decisions/draft`); await waitForTask(r.task_id); reload(); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const mark = async (d: Decision, status: string) => {
    const note = status === "implemented" ? prompt("How was it implemented? (optional)") ?? "" : "";
    await api.post(`/gap/decisions/${d.id}/status`, { status, note }); reload();
  };
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-2 text-sm">{Object.entries(data.options).map(([k, l]) => (
          <span key={k} className="chip bg-slate-100 text-slate-700">{l}: <b>{data.active.filter((d) => d.decision === k).length}</b></span>))}</div>
        <button className="btn-accent btn-sm ml-auto" onClick={draft} disabled={busy || !accepted.length}><Sparkles className="h-4 w-4" />{busy ? "Drafting…" : `Create CometForge draft for ${accepted.length} accepted addition${accepted.length === 1 ? "" : "s"}`}</button>
      </div>
      {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
      <Card title={<span className="flex items-center gap-2"><Gavel className="h-4 w-4 text-violet-700" />Current decisions</span>} padded={false}>
        {!data.active.length ? <div className="p-5"><Empty title="No decisions yet">Open a gap report, review a gap, then record what to do about it.</Empty></div> : (
          <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Decisions">
            <table className="table-base"><thead><tr><th>Skill</th><th>Decision</th><th>Rationale</th><th>Decided</th><th>Evidence versions</th><th>Status</th></tr></thead>
              <tbody>{data.active.map((d) => (
                <tr key={d.id}>
                  <td className="font-medium">{d.skill}</td>
                  <td><div className="font-semibold text-slate-800">{d.decision_label}</div>
                    {d.covered_in.length > 0 && <div className="text-xs text-slate-600">in {d.covered_in.join(", ")}</div>}
                    {d.revisit_term && <div className="text-xs text-slate-600">revisit {d.revisit_term}</div>}</td>
                  <td className="max-w-xs text-sm text-slate-700">{d.rationale}</td>
                  <td className="text-xs">{d.reviewer ?? "—"}<div className="text-slate-500">{new Date(d.decided_at).toLocaleDateString()}</div></td>
                  <td className="text-xs text-slate-600">Syllabus v{d.evidence.syllabus_version ?? "?"} <span className="font-mono">{d.evidence.syllabus_hash}</span><br />
                    {d.evidence.sample_kind === "auto" ? "Snapshot" : "Sample"} “{d.evidence.sample_name}” <span className="font-mono">{d.evidence.sample_hash}</span><br />
                    Catalog {d.evidence.catalog_year ?? "n/a"} · scoring {d.evidence.scoring_version ?? "n/a"}<br />
                    {d.evidence.postings_requesting} of {d.evidence.postings_in_sample} postings · faculty: {String(d.evidence.faculty_status).replace("_", " ")}</td>
                  <td className="text-sm">
                    <div className="font-semibold">{DECISION_STATUS[d.status]}</div>
                    {d.detected_in_version && d.status !== "implemented" && <div className="text-xs text-green-800">Syllabus v{d.detected_in_version} now mentions it</div>}
                    {d.implemented_note && <div className="text-xs text-slate-600">{d.implemented_note}</div>}
                    {d.forge_draft_id && <Link className="text-xs font-semibold text-comet-700 hover:underline" to="?tab=proposed">Proposed change</Link>}
                    {d.decision === "add_here" && d.status !== "implemented" && <div><button className="btn-ghost btn-sm mt-1" onClick={() => mark(d, "implemented")}>Mark implemented</button></div>}
                  </td>
                </tr>))}</tbody></table>
          </div>)}
      </Card>
      {data.history.length > 0 && (
        <details className="card p-4">
          <summary className="cursor-pointer text-sm font-semibold text-slate-700">Earlier decisions ({data.history.length}), replaced by a newer decision</summary>
          <ul className="mt-3 space-y-2 text-sm">{data.history.map((d) => (
            <li key={d.id} className="rounded border border-slate-200 p-2"><b>{d.skill}</b>: {d.decision_label}{d.revisit_term ? ` (revisit ${d.revisit_term})` : ""} — “{d.rationale}”
              <span className="text-xs text-slate-500"> · {d.reviewer ?? "—"}, {new Date(d.decided_at).toLocaleDateString()}</span></li>))}</ul>
        </details>)}
    </div>
  );
}

// ── Proposed changes (current syllabus beside the CometForge draft) ───────────
interface Outcome { id: string; text: string; bloom: string; skills: string[]; is_new: boolean }
interface ModuleT { week: number; title: string; topics: string[]; skills?: string[]; activities: string[]; is_new: boolean }
interface AssessmentT { name: string; type: string; weight: number; description: string; skills: string[] }
interface ProposedData {
  syllabus: { id: string; code: string | null; title: string; version: number | null; semester: string | null };
  draft: { id: string; version: number; status: string; created_at: string; content: { learning_outcomes: Outcome[]; modules: ModuleT[]; assessments: AssessmentT[]; project: { title: string; description: string; skills: string[] } } } | null;
  drafts: { id: string; version: number; status: string; created_at: string }[];
  skills: { decision_id: string; skill: string; status: string; rationale: string; current: string[]; proposed: { outcomes: Outcome[]; modules: ModuleT[]; assessments: AssessmentT[]; project: { title: string; description: string } | null } }[];
  current_lines: { n: number; text: string; skills: string[] }[];
}

function Proposed({ sid }: { sid: string }) {
  const [draftId, setDraftId] = useState<string | null>(null);
  const { data: p, loading } = useApi<ProposedData>(`/gap/syllabi/${sid}/proposed-changes${draftId ? `?draft_id=${draftId}` : ""}`);
  if (loading && !p) return <Spinner />;
  if (!p) return null;
  if (!p.skills.length) return <Empty title="No accepted additions">Choose “Add to this course” on a reviewed gap to propose a change.</Empty>;
  const names = new Set(p.skills.map((s) => s.skill));
  const touches = (sk?: string[]) => (sk ?? []).some((x) => names.has(x));
  const c = p.draft?.content;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <label className="label mb-0" htmlFor="draft">CometForge draft</label>
        <select id="draft" className="input max-w-sm" value={p.draft?.id ?? ""} onChange={(e) => setDraftId(e.target.value || null)}>
          {!p.draft && <option value="">No draft yet</option>}
          {p.drafts.map((d) => <option key={d.id} value={d.id}>Draft v{d.version} · {d.status} · {new Date(d.created_at).toLocaleDateString()}</option>)}
        </select>
        {p.draft && <Link to={`/forge/${p.draft.id}`} className="btn-ghost btn-sm">Open in CometForge</Link>}
        {!p.draft && <span className="text-sm text-slate-600">Create one from the Decisions tab.</span>}
      </div>
      <Card title="Each accepted addition: current syllabus vs proposed change" padded={false}>
        <div className="divide-y divide-slate-100">
          {p.skills.map((s) => (
            <div key={s.decision_id} className="grid gap-4 p-4 lg:grid-cols-[180px_1fr_1fr]">
              <div><div className="font-semibold text-slate-800">{s.skill}</div><div className="text-xs text-slate-600">{s.rationale}</div></div>
              <div>
                <div className="label">Current · v{p.syllabus.version} {p.syllabus.semester ?? ""}</div>
                {s.current.length ? <ul className="space-y-1 text-sm">{s.current.map((e, i) => <li key={i} className="rounded bg-slate-50 px-2 py-1 text-slate-700">{e}</li>)}</ul>
                  : <p className="rounded bg-slate-50 px-2 py-1 text-sm text-slate-500">Not mentioned in the current syllabus.</p>}
              </div>
              <div>
                <div className="label">Proposed · {p.draft ? `draft v${p.draft.version}` : "no draft"}</div>
                {!p.draft ? <p className="text-sm text-slate-500">—</p> : (
                  <ul className="space-y-1 text-sm">
                    {s.proposed.outcomes.map((o) => <li key={o.id} className="rounded border-l-4 border-green-600 bg-green-50 px-2 py-1"><b>{o.id}</b> {o.text}</li>)}
                    {s.proposed.modules.map((m) => <li key={m.week} className="rounded border-l-4 border-green-600 bg-green-50 px-2 py-1"><b>Week {m.week}:</b> {m.title}{m.is_new && <Badge color="green">new</Badge>}</li>)}
                    {s.proposed.assessments.map((a) => <li key={a.name} className="rounded border-l-4 border-green-600 bg-green-50 px-2 py-1"><b>{a.name}</b> ({a.weight}%) {a.description}</li>)}
                    {s.proposed.project && <li className="rounded border-l-4 border-green-600 bg-green-50 px-2 py-1"><b>Project:</b> {s.proposed.project.title}</li>}
                    {!s.proposed.outcomes.length && !s.proposed.modules.length && !s.proposed.assessments.length && !s.proposed.project && <li className="text-slate-500">This draft doesn't add it yet.</li>}
                  </ul>)}
              </div>
            </div>))}
        </div>
      </Card>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title={`Current syllabus · v${p.syllabus.version ?? "?"} ${p.syllabus.semester ?? ""}`} padded={false}>
          <ol className="max-h-[560px] overflow-y-auto p-4 font-mono text-xs leading-relaxed" tabIndex={0} aria-label="Current syllabus text">
            {p.current_lines.map((l) => (
              <li key={l.n} className={`flex gap-3 ${l.skills.length ? "bg-amber-50" : ""}`}><span className="w-8 shrink-0 text-right text-slate-500">{l.n}</span>
                <span className="whitespace-pre-wrap text-slate-800">{l.text}{l.skills.length > 0 && <span className="ml-2 font-sans text-[10px] font-semibold text-amber-800">{l.skills.join(", ")}</span>}</span></li>))}
          </ol>
        </Card>
        <Card title={p.draft ? `Proposed · CometForge draft v${p.draft.version}` : "Proposed"} padded={false}>
          {!c ? <p className="p-4 text-sm text-slate-500">No draft yet.</p> : (
            <div className="max-h-[560px] space-y-4 overflow-y-auto p-4 text-sm" tabIndex={0} aria-label="Proposed syllabus">
              <div><div className="label">Learning outcomes</div><ul className="space-y-1">{c.learning_outcomes.map((o) => (
                <li key={o.id} className={touches(o.skills) ? "rounded bg-green-50 px-2 py-0.5" : "px-2"}><b>{o.id}</b> {o.text}{o.is_new && <Badge color="green">new</Badge>}</li>))}</ul></div>
              <div><div className="label">Weekly modules</div><ul className="space-y-1">{c.modules.map((m) => (
                <li key={m.week} className={touches(m.skills) ? "rounded bg-green-50 px-2 py-0.5" : "px-2"}><b>Week {m.week}:</b> {m.title}{m.is_new && <Badge color="green">new</Badge>}</li>))}</ul></div>
              <div><div className="label">Assessments</div><ul className="space-y-1">{c.assessments.map((a) => (
                <li key={a.name} className={touches(a.skills) ? "rounded bg-green-50 px-2 py-0.5" : "px-2"}><b>{a.name}</b> · {a.weight}%</li>))}</ul></div>
              <p className="text-xs text-slate-500">Highlighted: items that add an accepted skill.</p>
            </div>)}
        </Card>
      </div>
    </div>
  );
}
