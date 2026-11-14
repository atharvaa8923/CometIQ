import { AlertTriangle, CalendarRange, CheckCircle2, Circle, CircleDot, Compass, GraduationCap, Lock, Plus, Route, Save, Sparkles, Target, Trash2, Wand2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Card, Empty, ErrorBox, Field, PageHeader, ScoreBar, Spinner, Stat, Tabs } from "../../components/ui";
import { CourseModal } from "../Catalog";
import { api } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { useToast } from "../../lib/toast";

interface Profile { program_id: string | null; concentration_id: string | null; career_goal: string | null; start_term: string; credits_per_term: number; include_summer: boolean }
interface Slot { or_group: number; status: string; options: { id: string; code: string; title: string; status: string | null }[] }
interface Readiness { goal: string | null; job_count: number; now: number; with_plan: number; skills: { skill: string; category: string; demand: number; status: "have" | "partial" | "planned" | "gap"; courses_outside_plan: string[] }[] }
interface Overview {
  profile: Profile;
  progress: { program: { name: string; total_sch: number; is_stem: boolean } | null; concentration: { name: string } | null; sch: Record<string, number>; total_sch: number;
    percent_complete: number; percent_with_plan: number; core: { slots: Slot[]; done: number; planned: number; total: number } };
  courses: { course_id: string; code: string; title: string; credits: number; status: string; term: string | null; grade: string | null }[];
  readiness: Readiness;
}
interface PlanCourse { id: string; code: string; title: string; credits: number; reason: string; is_core: boolean; skills: string[] }
interface Plan { concentration_suggestion: { id: string; name: string; current: string | null; reason: string } | null; terms: { term: string; credits: number; courses: PlanCourse[] }[]; graduation_term: string | null; planned_sch: number; total_sch: number; required_sch: number; warnings: string[]; readiness: Readiness }
interface Rec { id: string; code: string; title: string; credits: number; is_core: boolean; career_score: number; reasons: string[]; missing_prereqs?: string[] }

const READY = {
  have: { label: "Have", cls: "bg-green-50 text-green-800", Icon: CheckCircle2, color: "#0ca30c" },
  partial: { label: "Partial", cls: "bg-amber-50 text-amber-800", Icon: CircleDot, color: "#d97706" },
  planned: { label: "In plan", cls: "bg-sky-50 text-sky-800", Icon: CalendarRange, color: "#256abf" },
  gap: { label: "Gap", cls: "bg-red-50 text-red-800", Icon: AlertTriangle, color: "#d03b3b" },
};

export function ReadinessCard({ r, title = "Career readiness" }: { r: Readiness; title?: string }) {
  if (!r.goal) return <Card title={title}><p className="text-sm text-slate-500">Set a career goal to see which in-demand skills you have and which your plan adds.</p></Card>;
  return (
    <Card title={<span className="flex items-center gap-2"><Target className="h-4 w-4 text-flame-500" />{title}: {r.goal}</span>}>
      <div className="mb-4 grid grid-cols-2 gap-3">
        <div><div className="text-xs text-slate-500">Today</div><div className="text-2xl font-bold text-slate-700">{Math.round(r.now)}%</div><ScoreBar value={r.now} /></div>
        <div><div className="text-xs text-slate-500">After your plan</div><div className="text-2xl font-bold text-comet-700">{Math.round(r.with_plan)}%</div><ScoreBar value={r.with_plan} tone="comet" /></div>
      </div>
      <div className="mb-2 text-xs text-slate-500">Top skills in {r.job_count} {r.goal} postings</div>
      <ul className="space-y-1.5">
        {r.skills.map((s) => { const x = READY[s.status]; return (
          <li key={s.skill} className="flex items-center justify-between gap-2 text-sm" title={s.courses_outside_plan.length ? `Also taught in ${s.courses_outside_plan.join(", ")}` : undefined}>
            <span className="truncate">{s.skill} <span className="text-xs text-slate-400">{Math.round(s.demand * 100)}%</span></span>
            <span className={`chip ${x.cls}`}><x.Icon className="h-3.5 w-3.5" style={{ color: x.color }} aria-hidden />{x.label}{s.status === "gap" && s.courses_outside_plan.length ? ` · try ${s.courses_outside_plan[0]}` : ""}</span>
          </li>); })}
      </ul>
    </Card>
  );
}

function Setup({ profile, goals, onSaved }: { profile: Profile; goals: string[]; onSaved: () => void }) {
  const toast = useToast();
  const programs = useApi<{ id: string; name: string; type: string; concentrations: { id: string; name: string }[] }[]>("/programs");
  const [f, setF] = useState<Profile>(profile);
  const [err, setErr] = useState<string | null>(null);
  const prog = programs.data?.find((p) => p.id === f.program_id);
  const save = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    try { await api.put("/path/profile", f); toast("Profile saved"); onSaved(); } catch (x) { setErr((x as Error).message); }
  };
  return (
    <Card title="Your degree & career goal">
      <form onSubmit={save} className="grid gap-4 md:grid-cols-2">
        <div className="md:col-span-2"><ErrorBox error={err} /></div>
        <Field label="Program"><select className="input" required value={f.program_id ?? ""} onChange={(e) => setF({ ...f, program_id: e.target.value || null, concentration_id: null })}>
          <option value="">Select your program…</option>{programs.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
        <Field label="Concentration / track"><select className="input" value={f.concentration_id ?? ""} onChange={(e) => setF({ ...f, concentration_id: e.target.value || null })} disabled={!prog?.concentrations.length}>
          <option value="">{prog?.concentrations.length ? "Undecided" : "None for this program"}</option>{prog?.concentrations.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
        <Field label="Career goal" hint="Drives course recommendations using live job-market demand"><select className="input" value={f.career_goal ?? ""} onChange={(e) => setF({ ...f, career_goal: e.target.value || null })}>
          <option value="">Not sure yet</option>{goals.map((g) => <option key={g}>{g}</option>)}</select></Field>
        <Field label="Start term"><input className="input" value={f.start_term} pattern="(Spring|Summer|Fall) \d{4}" onChange={(e) => setF({ ...f, start_term: e.target.value })} /></Field>
        <Field label="Credit hours per term"><input type="number" min={3} max={18} className="input" value={f.credits_per_term} onChange={(e) => setF({ ...f, credits_per_term: +e.target.value })} /></Field>
        <label className="flex items-center gap-2 self-end pb-2 text-sm"><input type="checkbox" className="accent-comet-600" checked={f.include_summer} onChange={(e) => setF({ ...f, include_summer: e.target.checked })} />Take summer courses</label>
        <div className="md:col-span-2"><button className="btn-primary"><Save className="h-4 w-4" />Save</button></div>
      </form>
    </Card>
  );
}

export default function PathHome() {
  const toast = useToast();
  const prof = useApi<Profile & { career_goals: string[] }>("/path/profile");
  const ov = useApi<Overview>("/path/overview");
  const recs = useApi<{ eligible: Rec[]; blocked: Rec[]; career_goal: string | null }>("/path/recommendations");
  const [tab, setTab] = useState<"plan" | "progress" | "recs" | "setup">("plan");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [busy, setBusy] = useState(false);
  const [course, setCourse] = useState<string | null>(null);
  const [addQ, setAddQ] = useState("");
  const search = useApi<{ id: string; code: string; title: string }[]>(addQ.length >= 2 ? `/courses?limit=8&q=${encodeURIComponent(addQ)}` : null);

  const reloadAll = () => { prof.reload(); ov.reload(); recs.reload(); };
  const generate = async (save = false) => {
    setBusy(true);
    try { const p = await api.post<Plan>(`/path/plan?save=${save}`); setPlan(p); if (save) { toast("Plan saved to your courses"); ov.reload(); recs.reload(); } }
    catch (e) { toast((e as Error).message, "error"); } finally { setBusy(false); }
  };
  const setStatus = async (course_id: string, status: string) => {
    const r = await api.post<{ warning: string | null }>("/path/courses", { course_id, status });
    if (r.warning) toast(r.warning, "info"); else toast("Updated");
    ov.reload(); recs.reload();
  };
  const remove = async (course_id: string) => { await api.del(`/path/courses/${course_id}`); ov.reload(); recs.reload(); };

  useEffect(() => { if (prof.data && !prof.data.program_id) setTab("setup"); }, [prof.data]);
  if (prof.loading || ov.loading || !prof.data || !ov.data) return <Spinner />;
  const o = ov.data, p = o.progress;

  return (
    <div className="space-y-5">
      <PageHeader icon={<Route className="h-5 w-5" />} title="CometPath" subtitle="AI Degree & Career Planner"
        actions={p.program && <button className="btn-accent" onClick={() => { setTab("plan"); generate(false); }} disabled={busy}><Wand2 className="h-4 w-4" />Generate my plan</button>} />
      {p.program && (
        <div className="grid gap-4 md:grid-cols-4">
          <Stat label="Program" value={<span className="text-base">{p.program.name}</span>} hint={o.progress.concentration?.name ?? "No concentration"} />
          <Stat label="Completed" value={`${p.sch.completed} / ${p.total_sch} SCH`} hint={`${p.percent_complete}% · ${p.sch.enrolled} enrolled`} />
          <Stat label="Core requirements" value={`${p.core.done} / ${p.core.total}`} hint={`${p.core.planned} planned`} tone="flame" />
          <Stat label="Career readiness" value={o.readiness.goal ? `${Math.round(o.readiness.now)}% → ${Math.round(o.readiness.with_plan)}%` : "—"} hint={o.readiness.goal ?? "Set a goal"} tone="navy" />
        </div>)}
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "plan", label: "Semester plan" }, { id: "progress", label: "Degree progress" }, { id: "recs", label: "Recommended next" }, { id: "setup", label: "Profile & goal" }]} />

      {tab === "setup" && <Setup profile={prof.data} goals={prof.data.career_goals} onSaved={() => { reloadAll(); setPlan(null); setTab("plan"); }} />}

      {tab === "plan" && (!p.program ? <Empty icon={<GraduationCap className="h-8 w-8" />} title="Choose your program first" /> : (
        <div className="grid gap-5 lg:grid-cols-[1fr_380px]">
          <div className="space-y-4">
            {!plan ? (
              <Empty icon={<Compass className="h-8 w-8" />} title="Build a semester-by-semester plan">CometPath picks courses that satisfy your requirements and prerequisites, preferring the ones that build skills employers want for {prof.data.career_goal ?? "your goal"}.
                <div className="mt-4"><button className="btn-accent" onClick={() => generate(false)} disabled={busy}><Wand2 className="h-4 w-4" />{busy ? "Planning…" : "Generate my plan"}</button></div></Empty>
            ) : (<>
              <Card title={<span>Graduate <b className="text-comet-700">{plan.graduation_term ?? "—"}</b> · {plan.total_sch}/{plan.required_sch} SCH</span>}
                actions={<button className="btn-primary btn-sm" onClick={() => generate(true)} disabled={busy}><Save className="h-4 w-4" />Save plan</button>}>
                <ol className="relative space-y-5 border-l-2 border-comet-100 pl-6">
                  {plan.terms.map((t) => (
                    <li key={t.term}>
                      <span className="absolute -left-[9px] mt-1 h-4 w-4 rounded-full border-2 border-white bg-flame-500" />
                      <div className="mb-2 flex items-baseline gap-2"><span className="font-bold text-comet-900">{t.term}</span><span className="text-xs text-slate-500">{t.credits} SCH</span></div>
                      <div className="grid gap-2 md:grid-cols-2">
                        {t.courses.map((c) => (
                          <button key={c.id} onClick={() => setCourse(c.id)} className="rounded-lg border border-slate-200 bg-white p-3 text-left text-sm hover:border-comet-400">
                            <div className="flex items-center justify-between gap-2"><span className="font-semibold text-comet-800">{c.code}</span>{c.is_core ? <Badge color="green">core</Badge> : <Badge>elective</Badge>}</div>
                            <div className="text-slate-700">{c.title}</div>
                            <div className="mt-1 text-xs text-slate-500">{c.reason}</div>
                            {c.skills.length > 0 && <div className="mt-1.5 flex flex-wrap gap-1">{c.skills.map((s) => <Badge key={s} color="blue">{s}</Badge>)}</div>}
                          </button>))}
                      </div>
                    </li>))}
                </ol>
              </Card>
              {plan.concentration_suggestion && (
                <div className="flex flex-wrap items-center gap-3 rounded-xl border border-flame-200 bg-flame-50 p-4 text-sm text-flame-900">
                  <Sparkles className="h-4 w-4 text-flame-500" />
                  <div className="flex-1"><b>Consider the {plan.concentration_suggestion.name} concentration</b> for {prof.data.career_goal}{plan.concentration_suggestion.current ? ` (instead of ${plan.concentration_suggestion.current})` : ""}. {plan.concentration_suggestion.reason}</div>
                  <button className="btn-accent btn-sm" onClick={async () => { await api.put("/path/profile", { ...prof.data, concentration_id: plan.concentration_suggestion!.id }); reloadAll(); generate(false); toast("Concentration updated"); }}>Switch & re-plan</button>
                </div>)}
              {plan.warnings.length > 0 && <Card title="Notes for your advisor"><ul className="space-y-1 text-sm text-slate-600">{plan.warnings.map((w) => <li key={w} className="flex gap-2"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />{w}</li>)}</ul></Card>}
            </>)}
          </div>
          <ReadinessCard r={plan?.readiness ?? o.readiness} title={plan ? "Career readiness with this plan" : "Career readiness"} />
        </div>))}

      {tab === "progress" && p.program && (
        <div className="grid gap-5 lg:grid-cols-2">
          <Card title="Core requirements">
            <div className="mb-3"><ScoreBar value={(p.core.done / Math.max(p.core.total, 1)) * 100} tone="comet" /></div>
            <ul className="space-y-2">
              {p.core.slots.map((s, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  {s.status === "completed" ? <CheckCircle2 className="h-4 w-4 text-green-600" aria-label="completed" /> : s.status === "remaining" ? <Circle className="h-4 w-4 text-slate-300" aria-label="remaining" /> : <CircleDot className="h-4 w-4 text-sky-600" aria-label={s.status} />}
                  <div>{s.options.map((op, k) => <span key={op.id}>{k > 0 && <span className="mx-1 text-xs font-bold text-flame-600">OR</span>}
                    <button className="font-semibold text-comet-800 hover:underline" onClick={() => setCourse(op.id)}>{op.code}</button> <span className="text-slate-600">{op.title}</span></span>)}
                    <span className="ml-2 text-xs text-slate-400">{s.status}</span></div>
                </li>))}
            </ul>
          </Card>
          <Card title="My courses" actions={
            <div className="relative w-64"><input className="input py-1.5" placeholder="Add a course…" value={addQ} onChange={(e) => setAddQ(e.target.value)} aria-label="Add a course" />
              {search.data && addQ.length >= 2 && <div className="absolute right-0 z-10 mt-1 w-80 rounded-lg border border-slate-200 bg-white shadow-lg">
                {search.data.map((c) => <button key={c.id} className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-slate-50" onClick={() => { setStatus(c.id, "completed"); setAddQ(""); }}>
                  <span><b>{c.code}</b> {c.title}</span><Plus className="h-4 w-4 text-comet-600" /></button>)}</div>}</div>}>
            {o.courses.length === 0 ? <p className="text-sm text-slate-500">Add courses you've completed or are taking.</p> : (
              <table className="table-base"><thead><tr><th>Course</th><th>Term</th><th>Status</th><th /></tr></thead>
                <tbody>{o.courses.map((c) => (
                  <tr key={c.course_id}><td><button className="font-semibold text-comet-800 hover:underline" onClick={() => setCourse(c.course_id)}>{c.code}</button> <span className="text-slate-600">{c.title}</span></td>
                    <td className="text-xs text-slate-500">{c.term ?? "—"}</td>
                    <td><select className="input w-32 py-1 text-xs" value={c.status} onChange={(e) => setStatus(c.course_id, e.target.value)} aria-label={`Status of ${c.code}`}>
                      <option value="completed">Completed</option><option value="enrolled">Enrolled</option><option value="planned">Planned</option></select></td>
                    <td><button className="text-slate-400 hover:text-red-600" onClick={() => remove(c.course_id)} aria-label={`Remove ${c.code}`}><Trash2 className="h-4 w-4" /></button></td></tr>))}</tbody></table>)}
          </Card>
        </div>)}

      {tab === "recs" && (
        <div className="grid gap-5 lg:grid-cols-2">
          <Card title={<span className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-flame-500" />You can take these next</span>}>
            {!recs.data?.eligible.length ? <p className="text-sm text-slate-500">No eligible courses — set your program in Profile & goal.</p> : (
              <ul className="space-y-3">{recs.data.eligible.map((r) => (
                <li key={r.id} className="flex items-start justify-between gap-3 rounded-lg border border-slate-200 p-3">
                  <div><button className="font-semibold text-comet-800 hover:underline" onClick={() => setCourse(r.id)}>{r.code}</button> <span className="text-sm text-slate-700">{r.title}</span>
                    <ul className="mt-1 text-xs text-slate-500">{r.reasons.map((x) => <li key={x}>• {x}</li>)}</ul></div>
                  <button className="btn-ghost btn-sm shrink-0" onClick={() => setStatus(r.id, "planned")}><Plus className="h-4 w-4" />Plan</button>
                </li>))}</ul>)}
          </Card>
          <Card title={<span className="flex items-center gap-2"><Lock className="h-4 w-4 text-slate-400" />Unlock later</span>}>
            <ul className="space-y-3">{recs.data?.blocked.map((r) => (
              <li key={r.id} className="rounded-lg border border-slate-200 p-3 text-sm">
                <button className="font-semibold text-comet-800 hover:underline" onClick={() => setCourse(r.id)}>{r.code}</button> {r.title}
                <div className="mt-1 text-xs text-amber-700">Needs: {r.missing_prereqs?.join(" AND ")}</div></li>))}</ul>
          </Card>
        </div>)}
      <CourseModal id={course} onClose={() => setCourse(null)} />
    </div>
  );
}
