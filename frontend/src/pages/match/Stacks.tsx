import { Bell, BellOff, CheckCircle2, Circle, Layers } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Card, Empty, Spinner } from "../../components/ui";
import { api } from "../../lib/api";
import { useApi } from "../../lib/hooks";

export interface StackT {
  id: string; name: string; role_family: string | null; description: string; is_active: boolean; completions: number; subscribed?: boolean;
  requirements: { skill_id: number; skill: string; level: string }[];
  progress?: { done: number; total: number; complete: boolean; items: { skill: string; required_level: string; done: boolean; held: { level: string; course: string } | null;
    next_courses: { course_id: string; code: string; title: string; level: string; in_program: boolean; status: string | null }[] }[] };
}

/** Student view: progress toward each role-ready stack and the next course for each missing skill. */
export function StackProgress() {
  const { data, loading } = useApi<StackT[]>("/stacks");
  if (loading || !data) return <Spinner />;
  const active = data.filter((s) => s.is_active);
  if (!active.length) return <Empty icon={<Layers className="h-8 w-8" />} title="No skill stacks yet">Faculty define role-ready stacks; they will appear here.</Empty>;
  return (
    <div className="space-y-4">
      <p className="rounded-xl border border-comet-200 bg-comet-50 p-4 text-sm text-comet-900"><b>Skill stacks</b> group faculty-verified badges into role-ready credentials.
        Complete every skill to earn the stack; employers who follow it are notified if you are open to opportunities.</p>
      <div className="grid gap-4 lg:grid-cols-2">{active.map((s) => { const p = s.progress!; return (
        <Card key={s.id} title={<span className="flex items-center gap-2"><Layers className="h-4 w-4 text-comet-700" aria-hidden />{s.name}</span>}
          actions={<span className={`chip ${p.complete ? "bg-green-50 text-green-800" : "bg-slate-100 text-slate-700"}`}>{p.complete ? "Complete" : `${p.done} of ${p.total}`}</span>}>
          <p className="text-sm text-slate-600">{s.description}</p>
          <div className="mt-2 h-2 rounded-r bg-slate-100" role="img" aria-label={`${p.done} of ${p.total} skills`}><div className="h-2 rounded-r bg-comet-600" style={{ width: `${(100 * p.done) / Math.max(1, p.total)}%` }} /></div>
          <ul className="mt-3 space-y-2 text-sm">{p.items.map((i) => (
            <li key={i.skill} className="flex items-start gap-2">
              {i.done ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-green-700" aria-hidden /> : <Circle className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" aria-hidden />}
              <div><b>{i.skill}</b> <span className="text-xs text-slate-500">({i.required_level})</span>
                {i.done ? <span className="text-xs text-slate-600"> · verified in {i.held?.course}</span>
                  : i.next_courses.length ? <div className="text-xs text-slate-700">Next: {i.next_courses.map((c, k) => (
                      <span key={c.course_id}>{k > 0 && ", "}<Link className="font-semibold text-comet-700 hover:underline" to="/path">{c.code}</Link>{c.in_program ? "" : " (outside your program)"}{c.status ? ` · ${c.status}` : ""}</span>))}</div>
                  : <div className="text-xs text-slate-500">No course is faculty-confirmed for this level yet.</div>}
              </div>
            </li>))}</ul>
        </Card>); })}</div>
    </div>
  );
}

/** Employer view: follow stacks and see students who completed them. */
export function EmployerStacks() {
  const { data, loading, setData } = useApi<StackT[]>("/stacks");
  const [open, setOpen] = useState<string | null>(null);
  const done = useApi<{ student_id: string; name: string; headline: string | null; completed_at: string }[]>(open ? `/stacks/${open}/completions` : null);
  if (loading || !data) return <Spinner />;
  const toggle = async (s: StackT) => {
    await api.post(`/stacks/${s.id}/subscribe`, { subscribe: !s.subscribed });
    setData(data.map((x) => (x.id === s.id ? { ...x, subscribed: !s.subscribed } : x)));
  };
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">Follow a stack to get a notification whenever a student who is open to opportunities completes it. Every skill in a stack is a faculty-verified badge.</p>
      <div className="grid gap-4 lg:grid-cols-2">{data.filter((s) => s.is_active).map((s) => (
        <Card key={s.id} title={s.name} actions={<button className={`btn-sm ${s.subscribed ? "btn-primary" : "btn-ghost"}`} aria-pressed={!!s.subscribed} onClick={() => toggle(s)}>
          {s.subscribed ? <><Bell className="h-4 w-4" />Following</> : <><BellOff className="h-4 w-4" />Follow</>}</button>}>
          <p className="text-sm text-slate-600">{s.description}</p>
          <div className="mt-2 flex flex-wrap gap-1">{s.requirements.map((r) => <span key={r.skill_id} className="chip bg-comet-100 text-comet-800">{r.skill} · {r.level}</span>)}</div>
          <button className="mt-3 text-sm font-semibold text-comet-700 hover:underline" onClick={() => setOpen(open === s.id ? null : s.id)}>{s.completions} student{s.completions === 1 ? "" : "s"} completed it {open === s.id ? "▴" : "▾"}</button>
          {open === s.id && (done.loading ? <Spinner /> : <ul className="mt-2 space-y-1 text-sm">{(done.data ?? []).map((c) => <li key={c.student_id}><b>{c.name}</b>{c.headline ? ` · ${c.headline}` : ""} <span className="text-xs text-slate-500">{new Date(c.completed_at).toLocaleDateString()}</span></li>)}
            {!done.data?.length && <li className="text-slate-500">No students open to opportunities have completed it yet.</li>}</ul>)}
        </Card>))}</div>
    </div>
  );
}
