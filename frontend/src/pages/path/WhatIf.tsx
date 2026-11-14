import { ArrowRight, FlaskConical, Loader2 } from "lucide-react";
import { useState } from "react";
import { Badge, Card, ErrorBox, Field } from "../../components/ui";
import { api } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { useToast } from "../../lib/toast";

interface Summary { program: { id: string; name: string }; concentration: { id: string; name: string } | null; career_goal: string | null; graduation_term: string | null;
  planned_sch: number; total_sch: number; required_sch: number; counted_courses: string[]; not_counted_courses: string[]; terms_left: number; readiness_now: number; readiness_with_plan: number }
interface Result { current: Summary | null; what_if: Summary; comparison?: { extra_sch: number; term_shift: number; readiness_change: number };
  plan: { terms: { term: string; credits: number; courses: { id: string; code: string; title: string }[] }[]; warnings: string[] } }

const Row = ({ label, a, b, better }: { label: string; a: React.ReactNode; b: React.ReactNode; better?: "a" | "b" | null }) => (
  <tr><td className="font-medium text-slate-600">{label}</td><td className={better === "a" ? "font-bold text-comet-700" : ""}>{a}</td><td className={better === "b" ? "font-bold text-comet-700" : ""}>{b}</td></tr>
);

/** "What if I switch to Finance?" — compare the current plan with a hypothetical program/goal. */
export default function WhatIf({ goals, onSwitch }: { goals: string[]; onSwitch: () => void }) {
  const toast = useToast();
  const programs = useApi<{ id: string; name: string; concentrations: { id: string; name: string }[] }[]>("/programs");
  const [f, setF] = useState({ program_id: "", concentration_id: "", career_goal: "" });
  const [r, setR] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const prog = programs.data?.find((p) => p.id === f.program_id);
  const run = async () => {
    setBusy(true); setErr(null);
    try { setR(await api.post<Result>("/path/what-if", { program_id: f.program_id, concentration_id: f.concentration_id || null, career_goal: f.career_goal || null })); }
    catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  };
  const switchNow = async () => {
    if (!r || !confirm(`Switch your profile to ${r.what_if.program.name}? Your current saved plan will need regenerating.`)) return;
    const cur = await api.get<Record<string, unknown>>("/path/profile");
    await api.put("/path/profile", { ...cur, program_id: f.program_id, concentration_id: f.concentration_id || null, career_goal: f.career_goal || cur.career_goal || null });
    toast("Program switched — generate a new plan"); onSwitch();
  };
  const c = r?.current, w = r?.what_if, cmp = r?.comparison;
  const termWord = (n: number) => (n === 0 ? "same graduation term" : `${Math.abs(n)} term${Math.abs(n) > 1 ? "s" : ""} ${n > 0 ? "later" : "earlier"}`);
  return (
    <div className="space-y-4">
      <Card title={<span className="flex items-center gap-2"><FlaskConical className="h-4 w-4 text-flame-500" />Explore a different path — nothing changes until you switch</span>}>
        <ErrorBox error={err} />
        <div className="grid gap-3 md:grid-cols-4">
          <Field label="What if I switch to…"><select className="input" value={f.program_id} onChange={(e) => setF({ ...f, program_id: e.target.value, concentration_id: "" })}>
            <option value="">Choose a program</option>{programs.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
          <Field label="Concentration"><select className="input" value={f.concentration_id} onChange={(e) => setF({ ...f, concentration_id: e.target.value })} disabled={!prog?.concentrations.length}>
            <option value="">{prog?.concentrations.length ? "Any / undecided" : "None"}</option>{prog?.concentrations.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
          <Field label="Career goal"><select className="input" value={f.career_goal} onChange={(e) => setF({ ...f, career_goal: e.target.value })}>
            <option value="">Keep my current goal</option>{goals.map((g) => <option key={g}>{g}</option>)}</select></Field>
          <div className="flex items-end"><button className="btn-accent w-full" disabled={!f.program_id || busy} onClick={run}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FlaskConical className="h-4 w-4" />}Compare</button></div>
        </div>
      </Card>
      {w && (
        <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
          <Card title="Side-by-side">
            {cmp && <div className="mb-3 flex flex-wrap gap-2 text-sm">
              <Badge color={cmp.extra_sch > 0 ? "red" : "green"}>{cmp.extra_sch > 0 ? `+${cmp.extra_sch}` : cmp.extra_sch} SCH remaining</Badge>
              <Badge color={cmp.term_shift > 0 ? "red" : "green"}>{termWord(cmp.term_shift)}</Badge>
              <Badge color={cmp.readiness_change < 0 ? "red" : "green"}>{cmp.readiness_change > 0 ? "+" : ""}{cmp.readiness_change} pts career readiness</Badge></div>}
            <table className="table-base"><thead><tr><th /><th>Current</th><th>What-if</th></tr></thead>
              <tbody>
                <Row label="Program" a={c?.program.name ?? "—"} b={w.program.name} />
                <Row label="Concentration" a={c?.concentration?.name ?? "—"} b={w.concentration?.name ?? "—"} />
                <Row label="Career goal" a={c?.career_goal ?? "—"} b={w.career_goal ?? "—"} />
                <Row label="Courses that count" a={c ? `${c.counted_courses.length} (${c.counted_courses.join(", ") || "none"})` : "—"} b={`${w.counted_courses.length} (${w.counted_courses.join(", ") || "none"})`}
                  better={c ? (c.counted_courses.length > w.counted_courses.length ? "a" : c.counted_courses.length < w.counted_courses.length ? "b" : null) : null} />
                <Row label="Hours still needed" a={c ? `${c.planned_sch} SCH` : "—"} b={`${w.planned_sch} SCH`} better={c ? (c.planned_sch < w.planned_sch ? "a" : c.planned_sch > w.planned_sch ? "b" : null) : null} />
                <Row label="Graduate" a={c?.graduation_term ?? "—"} b={w.graduation_term ?? "—"} />
                <Row label="Career readiness after plan" a={c ? `${Math.round(c.readiness_with_plan)}%` : "—"} b={`${Math.round(w.readiness_with_plan)}%`}
                  better={c ? (c.readiness_with_plan > w.readiness_with_plan ? "a" : c.readiness_with_plan < w.readiness_with_plan ? "b" : null) : null} />
              </tbody></table>
            {w.not_counted_courses.length > 0 && <p className="mt-3 text-xs text-amber-700">Wouldn't count: {w.not_counted_courses.join(", ")} (possible free elective with advisor approval).</p>}
            <button className="btn-primary mt-4" onClick={switchNow}>Switch to this program<ArrowRight className="h-4 w-4" /></button>
          </Card>
          <Card title={`What-if plan · graduate ${w.graduation_term ?? "—"}`}>
            <div className="space-y-3">{r!.plan.terms.map((t) => (
              <div key={t.term}><div className="text-sm font-bold text-comet-900">{t.term} <span className="text-xs font-normal text-slate-500">{t.credits} SCH</span></div>
                <div className="mt-1 flex flex-wrap gap-1">{t.courses.map((x) => <Badge key={x.id} title={x.title}>{x.code}</Badge>)}</div></div>))}</div>
          </Card>
        </div>)}
    </div>
  );
}
