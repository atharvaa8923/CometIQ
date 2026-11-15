import { Download, GitPullRequest, Grid3x3, LineChart } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Badge, Card, Empty, Field, Modal, PageHeader, Spinner, Stat, Tabs } from "../../components/ui";
import { api, download } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useApi } from "../../lib/hooks";
import { TargetSelect } from "../gap/GapHome";

export interface ProposalBrief {
  id: string; number: number; title: string; status: string; revision: number; author: string | null; author_id: string | null;
  syllabus: { id: string; code: string | null; title: string } | null; effective_term: string | null; created_at: string; submitted_at: string | null;
  tally: { approvals: number; changes_requested: number; required: number }; open_comments: number; current_score: number | null; projected_score: number | null;
}
export const PSTATUS: Record<string, { label: string; color: string }> = {
  draft: { label: "Draft", color: "slate" }, in_review: { label: "In review", color: "blue" }, changes_requested: { label: "Changes requested", color: "orange" },
  approved: { label: "Approved", color: "green" }, adopted: { label: "Adopted", color: "green" }, withdrawn: { label: "Withdrawn", color: "slate" },
};

export default function CurriculumHome() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as "proposals" | "map" | "outcomes") ?? "proposals";
  return (
    <div>
      <PageHeader icon={<GitPullRequest className="h-5 w-5" />} title="Curriculum" subtitle="Proposals, the program curriculum map and outcomes of implemented changes" />
      <Tabs value={tab} onChange={(t) => setParams({ tab: t })} tabs={[
        { id: "proposals", label: <span className="inline-flex items-center gap-1.5"><GitPullRequest className="h-4 w-4" aria-hidden />Proposals</span> },
        { id: "map", label: <span className="inline-flex items-center gap-1.5"><Grid3x3 className="h-4 w-4" aria-hidden />Curriculum map</span> },
        { id: "outcomes", label: <span className="inline-flex items-center gap-1.5"><LineChart className="h-4 w-4" aria-hidden />Outcomes</span> }]} />
      {tab === "proposals" && <Proposals />}
      {tab === "map" && <CurriculumMap />}
      {tab === "outcomes" && <Outcomes />}
    </div>
  );
}

function Proposals() {
  const [filter, setFilter] = useState("open");
  const { data, loading } = useApi<ProposalBrief[]>(`/curriculum/proposals?status=${filter === "all" ? "" : filter}`);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {[["open", "Open"], ["adopted", "Adopted"], ["all", "All"]].map(([k, l]) => (
          <button key={k} className={`btn-sm ${filter === k ? "btn-primary" : "btn-ghost"}`} aria-pressed={filter === k} onClick={() => setFilter(k)}>{l}</button>))}
        <span className="ml-auto text-sm text-slate-600">Start a proposal from a course's <b>Course history → Proposed changes</b>.</span>
      </div>
      {loading ? <Spinner /> : !data?.length ? <Empty icon={<GitPullRequest className="h-8 w-8" />} title="No proposals">Accept a gap (“Add to this course”), create a CometForge draft, then open a proposal from Course history.</Empty> : (
        <Card padded={false}>
          <ul className="divide-y divide-slate-100">{data.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <GitPullRequest className={`h-5 w-5 ${p.status === "adopted" || p.status === "approved" ? "text-green-700" : "text-slate-500"}`} aria-hidden />
              <div className="min-w-0 flex-1">
                <Link to={`/curriculum/proposals/${p.id}`} className="font-semibold text-comet-800 hover:underline">{p.title}</Link>
                <div className="text-xs text-slate-600">#{p.number} · {p.syllabus?.code} · by {p.author ?? "—"} · effective {p.effective_term ?? "—"} · revision {p.revision}</div>
              </div>
              <Badge color={PSTATUS[p.status].color}>{PSTATUS[p.status].label}</Badge>
              <span className="text-xs text-slate-600">{p.tally.approvals}/{p.tally.required} approvals</span>
              {p.open_comments > 0 && <span className="text-xs text-slate-600">{p.open_comments} open comment{p.open_comments === 1 ? "" : "s"}</span>}
              {p.projected_score !== null && <span className="text-xs text-slate-600">coverage {Math.round(p.current_score ?? 0)}% → {Math.round(p.projected_score)}%</span>}
            </li>))}</ul>
        </Card>)}
    </div>
  );
}

// ── Curriculum map ─────────────────────────────────────────────────────────────
interface Cell { level: "I" | "P" | "M" | "-"; source: string; unverified: boolean; detail: string }
interface MapData {
  program: { id: string; name: string; catalog_year: string | null }; target: string; job_count: number;
  courses: { id: string; code: string; title: string; is_core: boolean; has_syllabus: boolean }[];
  skills: { id: number; name: string; category: string; demand: number | null; in_market: boolean }[];
  cells: Record<string, Record<string, Cell>>;
  summary: Record<string, { introduced_in: string[]; practiced_in: string[]; mastered_in: string[]; verified_in: string[]; flags: string[]; badge_holders: number }>;
  totals: { skills: number; practiced_somewhere: number; mastered_somewhere: number; courses_with_syllabus: number };
}
// Sequential single hue (comet), light → dark for Introduced → Practiced → Mastered; the letter is always shown
const LEVEL_STYLE: Record<string, string> = { I: "bg-comet-100 text-comet-900", P: "bg-comet-600 text-white", M: "bg-comet-900 text-white", "-": "bg-slate-100 text-slate-600" };
const LEVEL_NAME: Record<string, string> = { I: "Introduced", P: "Practiced", M: "Mastered", "-": "Not addressed" };

function CurriculumMap() {
  const programs = useApi<{ id: string; name: string }[]>("/programs");
  const [pid, setPid] = useState<string>("");
  const [target, setTarget] = useState("All roles");
  useEffect(() => {
    if (!pid && programs.data?.length) setPid((programs.data.find((p) => p.name.includes("Business Analytics and Artificial Intelligence")) ?? programs.data[0]).id);
  }, [programs.data, pid]);
  const { data: m, loading, reload } = useApi<MapData>(pid ? `/curriculum/programs/${pid}/map?target=${encodeURIComponent(target)}` : null);
  const [edit, setEdit] = useState<{ course: MapData["courses"][0]; skill: MapData["skills"][0]; cell?: Cell } | null>(null);
  const [allCourses, setAllCourses] = useState(false);
  const shown = m ? m.courses.filter((c) => allCourses || c.is_core || c.has_syllabus || Object.values(m.cells[c.id] ?? {}).some((x) => x.source === "faculty map")) : [];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-96"><Field label="Program"><select className="input" value={pid} onChange={(e) => setPid(e.target.value)}>{programs.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field></div>
        <div className="w-64"><Field label="Skills in demand for"><TargetSelect value={target} onChange={setTarget} /></Field></div>
        {m && <label className="mb-2 inline-flex items-center gap-2 text-sm"><input type="checkbox" className="accent-comet-600" checked={allCourses} onChange={(e) => setAllCourses(e.target.checked)} />
          Show all {m.courses.length} program courses</label>}
        {m && <button className="btn-ghost btn-sm mb-1" onClick={() => download(`/curriculum/programs/${pid}/map.xlsx?target=${encodeURIComponent(target)}`, "curriculum-map.xlsx")}><Download className="h-4 w-4" />Excel for AACSB</button>}
      </div>
      {loading || !m ? <Spinner /> : <>
        <div className="grid gap-4 sm:grid-cols-4">
          <Stat label="Skills mapped" value={m.totals.skills} hint={`top demand in ${m.job_count} postings + faculty entries`} />
          <Stat label="Practiced somewhere" value={`${m.totals.practiced_somewhere}/${m.totals.skills}`} />
          <Stat label="Taken to mastery" value={`${m.totals.mastered_somewhere}/${m.totals.skills}`} tone="navy" />
          <Stat label="Courses with a syllabus" value={`${m.totals.courses_with_syllabus}/${m.courses.length}`} tone="flame" />
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-700" aria-label="Legend">
          {(["I", "P", "M"] as const).map((l) => <span key={l} className="inline-flex items-center gap-1"><span className={`inline-flex h-5 w-5 items-center justify-center rounded text-[11px] font-bold ${LEVEL_STYLE[l]}`}>{l}</span>{LEVEL_NAME[l]}</span>)}
          <span className="inline-flex items-center gap-1"><span className="inline-flex h-5 w-6 items-center justify-center rounded border border-dashed border-slate-500 text-[11px] font-bold">P*</span>Unverified (keyword signal or catalog)</span>
          <span>Click a cell to set its level.{!allCourses && ` Showing core courses and courses with a syllabus or faculty entry (${shown.length} of ${m.courses.length}).`}</span>
        </div>
        <Card padded={false}>
          <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Curriculum map">
            <table className="w-full border-collapse text-sm">
              <thead><tr className="bg-slate-50 text-left text-xs text-slate-600">
                <th className="sticky left-0 z-10 bg-slate-50 px-3 py-2">Skill</th>
                {shown.map((c) => <th key={c.id} className="px-1 py-2 text-center font-semibold" title={c.title}>
                  <span className="block whitespace-nowrap">{c.code}</span><span className="block text-[10px] font-normal">{c.is_core ? "core" : "elective"}{c.has_syllabus ? "" : " · catalog"}</span></th>)}
                <th className="px-3 py-2">Flags</th><th className="px-3 py-2 text-right">Badge holders</th>
              </tr></thead>
              <tbody>{m.skills.map((s) => {
                const sm = m.summary[String(s.id)];
                return (
                  <tr key={s.id} className="border-t border-slate-100">
                    <th scope="row" className="sticky left-0 z-10 bg-white px-3 py-1.5 text-left font-medium text-slate-800">{s.name}
                      <span className="block text-[11px] font-normal text-slate-500">{s.demand !== null ? `${Math.round(s.demand * 100)}% of postings` : "faculty entry"}</span></th>
                    {shown.map((c) => {
                      const x = m.cells[c.id]?.[String(s.id)];
                      const lvl = x?.level ?? "";
                      return (
                        <td key={c.id} className="px-1 py-1 text-center">
                          <button onClick={() => setEdit({ course: c, skill: s, cell: x })} title={x ? `${LEVEL_NAME[lvl]} — ${x.source}: ${x.detail}` : "Not mapped — click to set"}
                            aria-label={x && lvl !== "-" ? `${lvl}${x.unverified ? "*" : ""}: ${s.name} in ${c.code}, ${LEVEL_NAME[lvl]}${x.unverified ? " (unverified)" : ""}` : `${s.name} in ${c.code}: not mapped`}
                            className={`inline-flex h-7 w-8 items-center justify-center rounded text-xs font-bold ${lvl && lvl !== "-" ? LEVEL_STYLE[lvl] : "text-slate-400 hover:bg-slate-100"} ${x?.unverified ? "border border-dashed border-slate-500 !bg-white !text-slate-800" : ""}`}>
                            {lvl && lvl !== "-" ? `${lvl}${x?.unverified ? "*" : ""}` : "·"}
                          </button>
                        </td>);
                    })}
                    <td className="px-3 py-1.5 text-xs text-slate-700">{sm.flags.join("; ") || <span className="text-slate-500">—</span>}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{sm.badge_holders}</td>
                  </tr>);
              })}</tbody>
            </table>
          </div>
        </Card>
      </>}
      {edit && m && <MapCellEditor pid={m.program.id} {...edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload(); }} />}
    </div>
  );
}

function MapCellEditor({ pid, course, skill, cell, onClose, onSaved }: { pid: string; course: MapData["courses"][0]; skill: MapData["skills"][0]; cell?: Cell; onClose: () => void; onSaved: () => void }) {
  const { user } = useAuth();
  const [level, setLevel] = useState<string>(cell?.level ?? "P");
  const [why, setWhy] = useState(cell?.source === "faculty map" ? cell.detail.replace(/^Set by [^:]*:?\s*/, "") : "");
  const [err, setErr] = useState<string | null>(null);
  const save = async () => {
    setErr(null);
    try { await api.put(`/curriculum/programs/${pid}/map/${course.id}/${skill.id}`, { level, rationale: why }); onSaved(); } catch (e) { setErr((e as Error).message); }
  };
  const clear = async () => { await api.del(`/curriculum/programs/${pid}/map/${course.id}/${skill.id}`); onSaved(); };
  return (
    <Modal open onClose={onClose} title={`${skill.name} in ${course.code}`}>
      <div className="space-y-3 text-sm">
        {cell && <p className="rounded bg-slate-50 p-2 text-slate-700"><b>Now: {LEVEL_NAME[cell.level]}</b> ({cell.source}{cell.unverified ? ", unverified" : ""}). {cell.detail}</p>}
        <fieldset><legend className="label">Level in this program</legend>
          <div className="grid grid-cols-2 gap-2">{(["I", "P", "M", "-"] as const).map((l) => (
            <label key={l} className={`flex cursor-pointer items-center gap-2 rounded-lg border p-2 ${level === l ? "border-comet-600 ring-1 ring-comet-600" : "border-slate-200"}`}>
              <input type="radio" name="lvl" checked={level === l} onChange={() => setLevel(l)} />
              <span className={`inline-flex h-5 w-5 items-center justify-center rounded text-[11px] font-bold ${LEVEL_STYLE[l]}`}>{l}</span>{LEVEL_NAME[l]}</label>))}</div>
        </fieldset>
        <Field label={`Rationale${level === "M" ? " (required: which assessment shows mastery?)" : " (optional)"}`}>
          <textarea className="input min-h-[70px]" value={why} onChange={(e) => setWhy(e.target.value)} placeholder="e.g. Final project graded with the program's analytics rubric" /></Field>
        {(level === "P" || level === "M") && <p className="text-xs text-slate-600">Students who complete {course.code} with an advisor-verified completion earn a faculty-verified {skill.name} badge.</p>}
        {err && <p role="alert" className="text-red-700">{err}</p>}
        <div className="flex gap-2"><button className="btn-primary btn-sm" onClick={save}>Save as {user?.full_name}</button>
          {cell?.source === "faculty map" && <button className="btn-ghost btn-sm" onClick={clear}>Remove faculty entry</button>}</div>
      </div>
    </Modal>
  );
}

// ── Outcomes ───────────────────────────────────────────────────────────────────
interface Metrics { students: number | string; suppressed: boolean; badge_rate?: number; applications?: number; interview_or_offer_rate?: number | null; applications_note?: string }
interface OutcomeRow { decision_id: string; skill: string; course: string; change_term: string | null; available: boolean; reason?: string; caveat: string; before?: Metrics; after?: Metrics }

function Outcomes() {
  const { data, loading } = useApi<{ decisions: OutcomeRow[]; supply: { skill: string; students: number }[]; min_group: number }>("/curriculum/outcomes");
  if (loading || !data) return <Spinner />;
  const max = Math.max(1, ...data.supply.map((s) => s.students));
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <Card title="Did implemented changes make a difference?">
        <p className="mb-3 text-sm text-slate-600">For each change added to a course, students who completed it before the change are compared with those after it,
          only in groups of at least {data.min_group}. This is an observational comparison, not proof of cause.</p>
        {!data.decisions.length ? <Empty title="No implemented changes yet">Changes appear here once a decision is implemented (adopted proposal or a new syllabus version).</Empty> : (
          <ul className="space-y-3">{data.decisions.map((o) => (
            <li key={o.decision_id} className="rounded-lg border border-slate-200 p-3">
              <div className="font-semibold text-slate-800">{o.course}: {o.skill} <span className="text-xs font-normal text-slate-600">changed {o.change_term ?? "—"}</span></div>
              {!o.available ? <p className="text-sm text-slate-600">{o.reason}</p> : (
                <div className="mt-2 grid gap-3 sm:grid-cols-2">{(["before", "after"] as const).map((k) => { const x = o[k]!; return (
                  <div key={k} className="rounded bg-slate-50 p-2 text-sm">
                    <div className="text-xs font-semibold uppercase text-slate-600">{k === "before" ? "Completed before the change" : "Completed after the change"}</div>
                    {x.suppressed ? <p className="text-slate-600">{x.students} students — not shown</p> : <>
                      <p><b>{x.students}</b> students · <b>{x.badge_rate}%</b> hold a verified {o.skill} badge</p>
                      <p>{x.interview_or_offer_rate !== null && x.interview_or_offer_rate !== undefined ? <><b>{x.interview_or_offer_rate}%</b> of {x.applications} applications to {o.skill} jobs reached interview or offer</> : <span className="text-slate-600">{x.applications_note}</span>}</p></>}
                  </div>); })}</div>)}
            </li>))}</ul>)}
      </Card>
      <Card title="Students with faculty-verified skills">
        {!data.supply.length ? <p className="text-sm text-slate-500">No badges issued yet.</p> : (
          <ul className="space-y-1.5">{data.supply.slice(0, 15).map((s) => (
            <li key={s.skill} className="grid grid-cols-[1fr_90px_32px] items-center gap-2 text-sm" title={`${s.students} students hold a faculty-verified ${s.skill} badge`}>
              <span className="truncate text-slate-700">{s.skill}</span>
              <span className="h-2 rounded-r bg-slate-100"><span className="block h-2 rounded-r bg-comet-600" style={{ width: `${(100 * s.students) / max}%` }} /></span>
              <span className="text-right font-semibold tabular-nums text-slate-800">{s.students}</span></li>))}</ul>)}
      </Card>
    </div>
  );
}
