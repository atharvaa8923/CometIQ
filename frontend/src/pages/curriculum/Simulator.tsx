import { ArrowRight, FlaskConical, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Card, Field, Spinner } from "../../components/ui";
import { api } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { TargetSelect } from "../gap/GapHome";

interface MapLite { courses: { id: string; code: string; title: string; is_core: boolean; has_syllabus: boolean }[]; skills: { id: number; name: string; in_market: boolean }[]; cells: Record<string, Record<string, { level: string }>> }
type Op = { op: string; [k: string]: string | number | boolean | undefined };
interface Metrics { coverage: number; never_practiced: number; no_mastery: number; overlaps: number; courses: number; max_chain_terms: number; plans_broken: number }
interface Result {
  operations: string[]; before: Metrics; after: Metrics; note: string;
  plans: { students_with_saved_plans: number; affected: number; newly_broken: number; fixed: number; already_broken: number; reasons: Record<string, number> };
  longest_chains: { course: string; terms: number }[];
  skill_changes: { skill: string; share: number; before: { levels: Record<string, string[]>; flags: string[] }; after: { levels: Record<string, string[]>; flags: string[] } }[];
}
const LEVELS = [["I", "Introduced"], ["P", "Practiced"], ["M", "Mastered"], ["-", "Not addressed"]];
const levelsText = (l: Record<string, string[]>) => (["M", "P", "I"] as const).filter((k) => l[k].length).map((k) => `${k}: ${l[k].join(", ")}`).join(" · ") || "nowhere";

export default function Simulator() {
  const programs = useApi<{ id: string; name: string }[]>("/programs");
  const all = useApi<{ id: string; code: string; title: string }[]>("/courses?limit=500");
  const [pid, setPid] = useState("");
  const [target, setTarget] = useState("All roles");
  const [ops, setOps] = useState<Op[]>([]);
  const [res, setRes] = useState<Result | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (!pid && programs.data?.length) setPid((programs.data.find((p) => p.name.includes("Business Analytics and Artificial Intelligence")) ?? programs.data[0]).id); }, [programs.data, pid]);
  const { data: m } = useApi<MapLite>(pid ? `/curriculum/programs/${pid}/map?target=${encodeURIComponent(target)}` : null);
  useEffect(() => { setOps([]); }, [pid]);
  useEffect(() => {
    if (!pid) return;
    const t = window.setTimeout(async () => {
      setErr(null);
      try { setRes(await api.post<Result>(`/curriculum/programs/${pid}/simulate`, { target, ops })); } catch (e) { setErr((e as Error).message); }
    }, 300);
    return () => window.clearTimeout(t);
  }, [pid, target, ops]);
  const shown = useMemo(() => m?.courses.filter((c) => c.is_core || c.has_syllabus) ?? [], [m]);
  const market = m?.skills.filter((s) => s.in_market) ?? [];
  const add = (o: Op) => setOps([...ops, o]);
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-4">
        <div className="w-96"><Field label="Program"><select className="input" value={pid} onChange={(e) => setPid(e.target.value)}>{programs.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field></div>
        <div className="w-64"><Field label="Skills in demand for"><TargetSelect value={target} onChange={setTarget} /></Field></div>
        <p className="mb-2 text-sm text-slate-600">Try a redesign here first. Nothing is saved.</p>
      </div>
      {!m ? <Spinner /> : (
        <div className="grid gap-5 xl:grid-cols-[1fr_420px]">
          <div className="space-y-5">
            <Card title="Change the program">
              <div className="grid gap-4 md:grid-cols-2">
                <OpForm title="Set a skill's level in a course" onAdd={(v) => add({ op: "set_level", course_id: v.course, skill_id: Number(v.skill), level: v.level })}
                  fields={[["course", "Course", shown.map((c) => [c.id, c.code])], ["skill", "Skill", market.map((s) => [String(s.id), s.name])], ["level", "Level", LEVELS]]} />
                <OpForm title="Move a skill between courses" onAdd={(v) => add({ op: "move_skill", skill_id: Number(v.skill), from_course: v.from, to_course: v.to, level: v.level })}
                  fields={[["skill", "Skill", market.map((s) => [String(s.id), s.name])], ["from", "From", shown.map((c) => [c.id, c.code])], ["to", "To", shown.map((c) => [c.id, c.code])], ["level", "Level there", LEVELS.slice(0, 3)]]} />
                <OpForm title="Add a course to the program" onAdd={(v) => add({ op: "add_course", course_id: v.course, core: v.kind === "core" })}
                  fields={[["course", "Catalog course", (all.data ?? []).filter((c) => !m.courses.some((x) => x.id === c.id)).map((c) => [c.id, `${c.code} ${c.title}`])], ["kind", "As", [["elective", "Elective"], ["core", "Core"]]]]} />
                <OpForm title="Remove a course" onAdd={(v) => add({ op: "remove_course", course_id: v.course })} fields={[["course", "Course", shown.map((c) => [c.id, `${c.code} ${c.title}`])]]} />
                <OpForm title="Add a prerequisite" onAdd={(v) => add({ op: "add_prereq", course_id: v.course, requires_id: v.req })}
                  fields={[["course", "Course", shown.map((c) => [c.id, c.code])], ["req", "Now requires", (all.data ?? []).map((c) => [c.id, c.code])]]} />
                <OpForm title="Remove a prerequisite" onAdd={(v) => add({ op: "remove_prereq", course_id: v.course, requires_id: v.req })}
                  fields={[["course", "Course", shown.map((c) => [c.id, c.code])], ["req", "No longer requires", (all.data ?? []).map((c) => [c.id, c.code])]]} />
              </div>
            </Card>
            <Card title={`Scenario (${ops.length} change${ops.length === 1 ? "" : "s"})`} actions={ops.length ? <button className="btn-ghost btn-sm" onClick={() => setOps([])}>Clear</button> : undefined}>
              {!res?.operations.length && !ops.length ? <p className="text-sm text-slate-500">Add changes above. Results update immediately.</p> : (
                <ol className="space-y-1 text-sm">{(res?.operations ?? []).map((o, i) => (
                  <li key={i} className="flex items-center gap-2"><span className="w-5 text-right text-xs text-slate-500">{i + 1}.</span>{o}
                    <button className="ml-auto rounded p-1 text-slate-500 hover:bg-red-50 hover:text-red-700" aria-label={`Remove change ${i + 1}`} onClick={() => setOps(ops.filter((_, k) => k !== i))}><Trash2 className="h-3.5 w-3.5" /></button></li>))}</ol>)}
              {err && <p role="alert" className="mt-2 rounded bg-red-50 p-2 text-sm text-red-800">{err}</p>}
            </Card>
            {res && res.skill_changes.length > 0 && <Card title="Skill changes" padded={false}>
              <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Skill changes">
                <table className="table-base"><thead><tr><th>Skill</th><th>Before</th><th>After</th></tr></thead>
                  <tbody>{res.skill_changes.map((c) => (
                    <tr key={c.skill}><td className="font-medium">{c.skill}<div className="text-xs text-slate-500">{c.share}% of postings</div></td>
                      <td className="text-xs">{levelsText(c.before.levels)}{c.before.flags.length > 0 && <div className="text-amber-800">{c.before.flags.join("; ")}</div>}</td>
                      <td className="text-xs">{levelsText(c.after.levels)}{c.after.flags.length > 0 && <div className="text-amber-800">{c.after.flags.join("; ")}</div>}</td></tr>))}</tbody></table>
              </div></Card>}
          </div>
          <aside className="space-y-4" aria-live="polite">
            <Card title={<span className="flex items-center gap-2"><FlaskConical className="h-4 w-4 text-flame-600" aria-hidden />Before → after</span>}>
              {!res ? <Spinner /> : (
                <dl className="space-y-2 text-sm">
                  {([["coverage", "Program coverage", "%", true], ["never_practiced", "In-demand skills never practiced", "", false], ["no_mastery", "Skills not taken to mastery", "", false],
                    ["overlaps", "Skills practiced in 3+ courses", "", false], ["max_chain_terms", "Longest prerequisite chain (terms)", "", false], ["plans_broken", "Saved plans with a problem", "", false]] as const).map(([k, label, unit, up]) => {
                    const b = res.before[k], a = res.after[k], d = Math.round((a - b) * 10) / 10;
                    const good = d === 0 ? null : up ? d > 0 : d < 0;
                    return (
                      <div key={k} className="flex items-center justify-between gap-2 border-b border-slate-100 pb-1.5">
                        <dt className="text-slate-700">{label}</dt>
                        <dd className="flex items-center gap-1.5 tabular-nums"><span className="text-slate-500">{b}{unit}</span><ArrowRight className="h-3 w-3 text-slate-400" aria-hidden /><b>{a}{unit}</b>
                          {d !== 0 && <span className={`text-xs font-semibold ${good ? "text-green-800" : "text-red-700"}`}>({d > 0 ? "+" : ""}{d})</span>}</dd>
                      </div>);
                  })}
                </dl>)}
            </Card>
            {res && <Card title="Student plans">
              <p className="text-sm text-slate-700">{res.plans.students_with_saved_plans} students in this program have a saved plan.
                This scenario adds a problem to <b>{res.plans.affected}</b> of them ({res.plans.newly_broken} that were fine before) and fixes {res.plans.fixed}.
                {res.plans.already_broken > 0 && ` ${res.plans.already_broken} plans already had problems before any change.`}</p>
              {Object.keys(res.plans.reasons).length > 0 && <ul className="mt-2 space-y-1 text-sm">{Object.entries(res.plans.reasons).map(([r, n]) => <li key={r}><b>{n}</b> × {r}</li>)}</ul>}
              <p className="mt-2 text-xs text-slate-500">Counts only; no student is named.</p>
            </Card>}
            {res && <Card title="Longest prerequisite chains (core)">
              <ul className="space-y-1 text-sm">{res.longest_chains.map((c) => <li key={c.course} className="flex justify-between"><span>{c.course}</span><span className="tabular-nums">{c.terms} term{c.terms === 1 ? "" : "s"}</span></li>)}</ul>
            </Card>}
            {res && <p className="text-xs text-slate-500">{res.note}</p>}
          </aside>
        </div>)}
    </div>
  );
}

function OpForm({ title, fields, onAdd }: { title: string; fields: [string, string, (string[] | readonly string[])[]][]; onAdd: (v: Record<string, string>) => void }) {
  const [v, setV] = useState<Record<string, string>>({});
  const ready = fields.every(([k]) => v[k]);
  const id = title.replace(/\W+/g, "-").toLowerCase();
  return (
    <fieldset className="rounded-lg border border-slate-200 p-3">
      <legend className="px-1 text-sm font-semibold text-slate-800">{title}</legend>
      <div className="space-y-2">{fields.map(([k, label, opts]) => (
        <div key={k}><label className="label" htmlFor={`${id}-${k}`}>{label}</label>
          <select id={`${id}-${k}`} className="input" value={v[k] ?? ""} onChange={(e) => setV({ ...v, [k]: e.target.value })}>
            <option value="">Choose…</option>{opts.map(([val, lab]) => <option key={val} value={val}>{lab}</option>)}
          </select></div>))}
        <button className="btn-ghost btn-sm" disabled={!ready} onClick={() => { onAdd(v); setV({}); }}><Plus className="h-4 w-4" />Add to scenario</button>
      </div>
    </fieldset>
  );
}
