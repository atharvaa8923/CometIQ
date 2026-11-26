import { ClipboardList, Download, Plus, Sparkles, Trash2 } from "lucide-react";
import { Fragment, useEffect, useState } from "react";
import { Badge, Card, Empty, ErrorBox, Field, Modal, Spinner, Stat } from "../../components/ui";
import { api, download } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { useToast } from "../../lib/toast";

interface Measure { course: string; assignment: string; points: number | null; rubric_criteria: string[]; course_grade_share: number | null }
interface Result { id: string; term: string; course_code: string | null; measure: string; measure_type: string; students_assessed: number;
  students_meeting: number; met_pct: number | null; target_pct: number; met_target: boolean; notes: string | null; action: string | null; entered_by: string | null }
interface Loop { kind: string; course?: string | null; skill?: string; decision?: string; status?: string; rationale?: string | null; title?: string;
  effective_term?: string | null; term?: string; action?: string }
interface Goal { id: string; code: string; title: string; description: string | null; target_pct: number; skills: { id: number; name: string }[];
  coverage: Record<"introduced_in" | "practiced_in" | "mastered_in" | "verified_in", string[]>; skills_detail: { skill: string; measures: Measure[] }[];
  direct_measures: number; results: Result[]; closing_the_loop: Loop[]; status: string; status_text: string; warnings: string[] }
interface Report { program: { id: string; name: string }; goals: Goal[];
  summary: { goals: number; met: number; below_with_action: number; below: number; not_assessed: number; gap: number; terms_assessed: string[];
             direct_measures: number; industry_coverage: number | null } }
interface SkillLite { id: number; name: string; category: string }

const STATUS: Record<string, { label: string; color: string }> = {
  met: { label: "Met target", color: "green" }, below_with_action: { label: "Below target · action recorded", color: "orange" },
  below: { label: "Below target · no action", color: "red" }, not_assessed: { label: "Not yet assessed", color: "slate" },
  gap: { label: "Not practiced in any course", color: "red" },
};

function GoalEditor({ open, onClose, pid, initial, onSaved, skills }: { open: boolean; onClose: () => void; pid: string; skills: SkillLite[];
  initial: { id?: string; code: string; title: string; description?: string | null; target_pct: number; skill_ids: number[] }; onSaved: () => void }) {
  const [g, setG] = useState(initial);
  const [q, setQ] = useState("");
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { setG(initial); setErr(null); }, [initial]);
  const save = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    try {
      const body = { code: g.code, title: g.title, description: g.description, target_pct: g.target_pct, skill_ids: g.skill_ids };
      if (g.id) await api.put(`/curriculum/programs/${pid}/aol/goals/${g.id}`, body); else await api.post(`/curriculum/programs/${pid}/aol/goals`, body);
      onSaved(); onClose();
    } catch (x) { setErr((x as Error).message); }
  };
  const picked = new Set(g.skill_ids);
  const matches = q.length >= 2 ? skills.filter((s) => s.name.toLowerCase().includes(q.toLowerCase()) && !picked.has(s.id)).slice(0, 8) : [];
  return (
    <Modal open={open} onClose={onClose} title={g.id ? `Edit ${g.code}` : "New competency goal"} wide>
      <form onSubmit={save} className="space-y-3">
        <ErrorBox error={err} />
        <div className="grid gap-3 md:grid-cols-[120px_1fr_140px]">
          <Field label="Code"><input className="input" required maxLength={20} value={g.code} onChange={(e) => setG({ ...g, code: e.target.value })} /></Field>
          <Field label="Goal"><input className="input" required minLength={5} value={g.title} onChange={(e) => setG({ ...g, title: e.target.value })} /></Field>
          <Field label="Target (% meeting)"><input className="input" type="number" min={1} max={100} value={g.target_pct} onChange={(e) => setG({ ...g, target_pct: Number(e.target.value) })} /></Field>
        </div>
        <Field label="Description (optional)"><textarea className="input" rows={2} value={g.description ?? ""} onChange={(e) => setG({ ...g, description: e.target.value })} /></Field>
        <div>
          <div className="label">Skills that show this goal</div>
          <ul className="mb-2 flex flex-wrap gap-2">{g.skill_ids.map((id) => (
            <li key={id}><button type="button" className="chip bg-comet-50 text-comet-800" onClick={() => setG({ ...g, skill_ids: g.skill_ids.filter((x) => x !== id) })}
              aria-label={`Remove ${skills.find((s) => s.id === id)?.name ?? id}`}>{skills.find((s) => s.id === id)?.name ?? id} ✕</button></li>))}</ul>
          <input className="input" placeholder="Add a skill: type at least two letters" aria-label="Find a skill" value={q} onChange={(e) => setQ(e.target.value)} />
          {matches.length > 0 && <ul className="mt-1 rounded-lg border border-slate-200">{matches.map((s) => (
            <li key={s.id}><button type="button" className="w-full px-3 py-1.5 text-left text-sm hover:bg-slate-50" onClick={() => { setG({ ...g, skill_ids: [...g.skill_ids, s.id] }); setQ(""); }}>
              {s.name} <span className="text-xs text-slate-500">{s.category}</span></button></li>))}</ul>}
        </div>
        <button className="btn-primary">Save goal</button>
      </form>
    </Modal>);
}

function ResultForm({ open, onClose, pid, goal, onSaved }: { open: boolean; onClose: () => void; pid: string; goal: Goal | null; onSaved: () => void }) {
  const blank = { term: "", course_code: "", measure: "", measure_type: "direct", students_assessed: "", students_meeting: "", notes: "", action: "" };
  const [f, setF] = useState(blank);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { setF(blank); setErr(null); }, [goal?.id]);   // eslint-disable-line react-hooks/exhaustive-deps
  if (!goal) return null;
  const pct = Number(f.students_assessed) > 0 ? Math.round(100 * Number(f.students_meeting) / Number(f.students_assessed)) : null;
  const save = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    try {
      await api.post(`/curriculum/programs/${pid}/aol/goals/${goal.id}/results`, { ...f, students_assessed: Number(f.students_assessed),
        students_meeting: Number(f.students_meeting), course_code: f.course_code || null, notes: f.notes || null, action: f.action || null });
      onSaved(); onClose();
    } catch (x) { setErr((x as Error).message); }
  };
  const measures = goal.skills_detail.flatMap((s) => s.measures.map((m) => `${m.course} ${m.assignment}${m.rubric_criteria.length ? `: ${m.rubric_criteria[0]}` : ""}`));
  return (
    <Modal open={open} onClose={onClose} title={`Assessment result for ${goal.code}`} wide>
      <form onSubmit={save} className="space-y-3">
        <ErrorBox error={err} />
        <div className="grid gap-3 md:grid-cols-3">
          <Field label="Term"><input className="input" required placeholder="Fall 2026" value={f.term} onChange={(e) => setF({ ...f, term: e.target.value })} /></Field>
          <Field label="Course (optional)"><input className="input" placeholder="BUAN 6320" value={f.course_code} onChange={(e) => setF({ ...f, course_code: e.target.value })} /></Field>
          <Field label="Measure type"><select className="input" value={f.measure_type} onChange={(e) => setF({ ...f, measure_type: e.target.value })}>
            <option value="direct">Direct (graded student work)</option><option value="indirect">Indirect (survey, placement)</option></select></Field>
        </div>
        <Field label="Measure" hint={measures.length ? `From Canvas: ${measures.slice(0, 3).join("; ")}` : undefined}>
          <input className="input" required minLength={3} list={`m-${goal.id}`} value={f.measure} onChange={(e) => setF({ ...f, measure: e.target.value })} />
          <datalist id={`m-${goal.id}`}>{measures.map((m) => <option key={m} value={m} />)}</datalist></Field>
        <div className="grid gap-3 md:grid-cols-3">
          <Field label="Students assessed"><input className="input" type="number" min={1} required value={f.students_assessed} onChange={(e) => setF({ ...f, students_assessed: e.target.value })} /></Field>
          <Field label="Met or exceeded expectations"><input className="input" type="number" min={0} required value={f.students_meeting} onChange={(e) => setF({ ...f, students_meeting: e.target.value })} /></Field>
          <div className="pt-6 text-sm" role="status">{pct !== null && <>= <b>{pct}%</b> (target {goal.target_pct}%)</>}</div>
        </div>
        <Field label="Notes (optional)"><textarea className="input" rows={2} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
        <Field label="Action taken (closing the loop)" hint="What faculty decided to change, especially when below target"><textarea className="input" rows={2} value={f.action} onChange={(e) => setF({ ...f, action: e.target.value })} /></Field>
        <button className="btn-primary">Save result</button>
      </form>
    </Modal>);
}

/** AACSB assurance of learning: competency goals, where they are taught, direct measures, results, closing the loop. */
export default function Aol() {
  const toast = useToast();
  const programs = useApi<{ id: string; name: string }[]>("/programs");
  const skills = useApi<SkillLite[]>("/skills");
  const [pid, setPid] = useState("");
  useEffect(() => { if (!pid && programs.data?.length) setPid((programs.data.find((p) => p.name.includes("Business Analytics and Artificial Intelligence")) ?? programs.data[0]).id); }, [programs.data, pid]);
  const rep = useApi<Report>(pid ? `/curriculum/programs/${pid}/aol` : null);
  const sug = useApi<{ title: string; skills: { id: number; name: string }[] }[]>(pid ? `/curriculum/programs/${pid}/aol/suggestions` : null);
  const [editing, setEditing] = useState<Parameters<typeof GoalEditor>[0]["initial"] | null>(null);
  const [resultFor, setResultFor] = useState<Goal | null>(null);
  const r = rep.data;
  const nextCode = () => `LG${(r?.goals.length ?? 0) + 1}`;
  const delResult = async (g: Goal, x: Result) => {
    if (!confirm(`Delete the ${x.term} result "${x.measure}"?`)) return;
    await api.del(`/curriculum/programs/${pid}/aol/goals/${g.id}/results/${x.id}`); rep.reload();
  };
  const delGoal = async (g: Goal) => {
    if (!confirm(`Delete ${g.code} and its results?`)) return;
    await api.del(`/curriculum/programs/${pid}/aol/goals/${g.id}`); toast(`${g.code} deleted`); rep.reload();
  };
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="w-96"><Field label="Program"><select className="input" value={pid} onChange={(e) => setPid(e.target.value)}>{programs.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field></div>
        {r && <div className="flex gap-2">
          <button className="btn-ghost btn-sm" onClick={() => download(`/curriculum/programs/${pid}/aol/report.docx`, `AoL-${r.program.name}.docx`)}><Download className="h-4 w-4" aria-hidden />Word</button>
          <button className="btn-ghost btn-sm" onClick={() => download(`/curriculum/programs/${pid}/aol/report.pdf`, `AoL-${r.program.name}.pdf`)}><Download className="h-4 w-4" aria-hidden />PDF</button>
          <button className="btn-primary btn-sm" onClick={() => setEditing({ code: nextCode(), title: "", target_pct: 80, skill_ids: [] })}><Plus className="h-4 w-4" aria-hidden />Add goal</button></div>}
      </div>
      <p className="max-w-3xl text-sm text-slate-600">AACSB Standard 5: for each competency goal, show where it is taught, how it is assessed, the results, and what faculty changed in response.
        CometIQ assembles the map, graded work from Canvas and faculty decisions; you enter assessment results and actions.</p>
      {rep.loading && !r ? <Spinner /> : r && <>
        <div className="grid gap-4 md:grid-cols-5">
          <Stat label="Competency goals" value={r.summary.goals} />
          <Stat label="Met target" value={r.summary.met} />
          <Stat label="Below target" value={r.summary.below + r.summary.below_with_action} hint={`${r.summary.below_with_action} with an action recorded`} tone="flame" />
          <Stat label="Not yet assessed" value={r.summary.not_assessed + r.summary.gap} tone="slate" />
          <Stat label="Direct measures" value={r.summary.direct_measures} hint="graded assignments from Canvas" tone="navy" />
        </div>
        {!r.goals.length && <Card title={<span className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-flame-500" aria-hidden />Start from the program's in-demand skills</span>}>
          {sug.loading ? <Spinner /> : <ul className="space-y-2">{sug.data?.map((s, i) => (
            <li key={s.title} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 p-3 text-sm">
              <span><b>{s.title}</b><span className="block text-xs text-slate-500">{s.skills.map((x) => x.name).join(", ")}</span></span>
              <button className="btn-ghost btn-sm" onClick={() => setEditing({ code: `LG${i + 1}`, title: s.title, target_pct: 80, skill_ids: s.skills.map((x) => x.id) })}>Use as a goal</button></li>))}</ul>}
        </Card>}
        {!r.goals.length && !sug.data?.length && <Empty icon={<ClipboardList className="h-8 w-8" />} title="No goals yet">Add the program's competency goals to start the report.</Empty>}
        {r.goals.map((g) => (
          <Card key={g.id} title={<span><b>{g.code}</b> {g.title}</span>} actions={<span className="flex items-center gap-2">
            <Badge color={STATUS[g.status]?.color}>{STATUS[g.status]?.label ?? g.status}</Badge>
            <button className="btn-ghost btn-sm" onClick={() => setEditing({ id: g.id, code: g.code, title: g.title, description: g.description, target_pct: g.target_pct, skill_ids: g.skills.map((s) => s.id) })}>Edit</button>
            <button className="rounded p-1 text-slate-500 hover:bg-red-50 hover:text-red-600" onClick={() => delGoal(g)} aria-label={`Delete ${g.code}`}><Trash2 className="h-4 w-4" /></button></span>}>
            <div className="grid gap-5 lg:grid-cols-2">
              <div className="space-y-3 text-sm">
                <p className="text-slate-600">{g.status_text}. Target: {g.target_pct}% meet expectations. Skills: {g.skills.map((s) => s.name).join(", ") || "none"}.</p>
                {g.warnings.length > 0 && <ul className="text-xs text-amber-800">{g.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
                <div><div className="label">Where it is taught</div>
                  <dl className="grid grid-cols-[110px_1fr] gap-y-1 text-xs">
                    {(["introduced_in", "practiced_in", "mastered_in"] as const).map((k) => (<Fragment key={k}><dt className="text-slate-500">{({ introduced_in: "Introduced", practiced_in: "Practiced", mastered_in: "Mastered" })[k]}</dt>
                      <dd className="text-slate-800">{g.coverage[k].join(", ") || "—"}</dd></Fragment>))}
                  </dl></div>
                <div><div className="label">Direct measures from graded work</div>
                  {g.direct_measures ? <ul className="space-y-1 text-xs">{g.skills_detail.flatMap((s) => s.measures.map((m) => (
                    <li key={s.skill + m.course + m.assignment}><b>{m.course}</b> {m.assignment} · {s.skill}{m.rubric_criteria.length ? ` · rubric: ${m.rubric_criteria.join(", ")}` : ""}
                      {m.course_grade_share != null && <span className="text-slate-500"> ({Math.round(m.course_grade_share * 100)}% of the course grade)</span>}</li>)))}</ul>
                    : <p className="text-xs text-slate-500">None on record. Import the courses from Canvas to list graded assignments and rubric criteria.</p>}</div>
              </div>
              <div className="space-y-3 text-sm">
                <div className="flex items-center justify-between"><div className="label mb-0">Results</div>
                  <button className="btn-ghost btn-sm" onClick={() => setResultFor(g)}><Plus className="h-4 w-4" aria-hidden />Add result</button></div>
                {g.results.length ? <table className="table-base text-xs"><caption className="sr-only">Assessment results for {g.code}</caption>
                  <thead><tr><th scope="col">Term</th><th scope="col">Measure</th><th scope="col">Met</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
                  <tbody>{g.results.map((x) => (
                    <tr key={x.id}><td className="whitespace-nowrap">{x.term}{x.course_code ? <div className="text-slate-500">{x.course_code}</div> : null}</td>
                      <td>{x.measure} <span className="text-slate-500">({x.measure_type}, n={x.students_assessed})</span>{x.action && <div className="mt-0.5 text-slate-600">Action: {x.action}</div>}</td>
                      <td><Badge color={x.met_target ? "green" : "red"}>{x.met_pct}% / {x.target_pct}%</Badge></td>
                      <td><button className="rounded p-1 text-slate-500 hover:text-red-600" onClick={() => delResult(g, x)} aria-label={`Delete ${x.term} result`}><Trash2 className="h-3.5 w-3.5" /></button></td></tr>))}</tbody></table>
                  : <p className="text-xs text-slate-500">No results yet.</p>}
                <div><div className="label">Closing the loop</div>
                  {g.closing_the_loop.length ? <ul className="space-y-1 text-xs">{g.closing_the_loop.map((i, n) => (
                    <li key={n}>{i.kind === "decision" ? <>{i.course}: decision on <b>{i.skill}</b> ({i.decision?.replace(/_/g, " ")}, {i.status})</>
                      : i.kind === "proposal" ? <>{i.course}: proposal {i.title} ({i.status}{i.effective_term ? `, ${i.effective_term}` : ""})</>
                      : <>{i.course ? `${i.course} ` : ""}{i.term}: {i.action}</>}</li>))}</ul>
                    : <p className="text-xs text-slate-500">No actions yet.</p>}</div>
              </div>
            </div>
          </Card>))}
      </>}
      {editing && <GoalEditor open={!!editing} onClose={() => setEditing(null)} pid={pid} initial={editing} skills={skills.data ?? []} onSaved={() => { rep.reload(); toast("Goal saved"); }} />}
      <ResultForm open={!!resultFor} onClose={() => setResultFor(null)} pid={pid} goal={resultFor} onSaved={() => { rep.reload(); toast("Result saved"); }} />
    </div>);
}
