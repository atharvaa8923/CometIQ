import { Layers, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Card, Field, Modal, Spinner } from "../../components/ui";
import { api } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import type { StackT } from "../match/Stacks";

export default function StacksAdmin() {
  const { data, loading, reload } = useApi<StackT[]>("/stacks");
  const skills = useApi<{ id: number; name: string }[]>("/skills");
  const [edit, setEdit] = useState<StackT | "new" | null>(null);
  if (loading || !data) return <Spinner />;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3"><p className="flex-1 text-sm text-slate-600">Skill stacks are role-ready credentials made of faculty-verified badges. Students see their progress and the next course to take; employers can follow a stack.</p>
        <button className="btn-primary btn-sm" onClick={() => setEdit("new")}><Plus className="h-4 w-4" />New stack</button></div>
      <div className="grid gap-4 lg:grid-cols-3">{data.map((s) => (
        <Card key={s.id} title={<span className="flex items-center gap-2"><Layers className="h-4 w-4 text-comet-700" aria-hidden />{s.name}{!s.is_active && <span className="chip bg-slate-100 text-slate-600">inactive</span>}</span>}
          actions={<button className="btn-ghost btn-sm" onClick={() => setEdit(s)}>Edit</button>}>
          <p className="text-sm text-slate-600">{s.description}</p>
          <div className="mt-2 flex flex-wrap gap-1">{s.requirements.map((r) => <span key={r.skill_id} className="chip bg-comet-100 text-comet-800">{r.skill} · {r.level}</span>)}</div>
          <p className="mt-2 text-xs text-slate-600">{s.completions} student{s.completions === 1 ? "" : "s"} completed it</p>
        </Card>))}</div>
      {edit && skills.data && <StackEditor stack={edit === "new" ? null : edit} skills={skills.data} onClose={() => setEdit(null)} onDone={() => { setEdit(null); reload(); }} />}
    </div>
  );
}

function StackEditor({ stack, skills, onClose, onDone }: { stack: StackT | null; skills: { id: number; name: string }[]; onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ name: stack?.name ?? "", role_family: stack?.role_family ?? "", description: stack?.description ?? "", is_active: stack?.is_active ?? true });
  const [reqs, setReqs] = useState<{ skill_id: number; level: string }[]>(stack?.requirements.map((r) => ({ skill_id: r.skill_id, level: r.level })) ?? [{ skill_id: 0, level: "practiced" }]);
  const [err, setErr] = useState<string | null>(null);
  const save = async () => {
    setErr(null);
    const body = { ...f, requirements: reqs.filter((r) => r.skill_id) };
    try { stack ? await api.put(`/stacks/${stack.id}`, body) : await api.post("/stacks", body); onDone(); } catch (e) { setErr((e as Error).message); }
  };
  return (
    <Modal open onClose={onClose} title={stack ? `Edit ${stack.name}` : "New skill stack"} wide>
      <div className="grid gap-3 md:grid-cols-2">
        <Field label="Name"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Analytics Engineer" /></Field>
        <Field label="Role family (optional)"><input className="input" value={f.role_family} onChange={(e) => setF({ ...f, role_family: e.target.value })} /></Field>
        <div className="md:col-span-2"><Field label="Description"><input className="input" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field></div>
      </div>
      <fieldset className="mt-3"><legend className="label">Required skills</legend>
        <div className="space-y-2">{reqs.map((r, i) => (
          <div key={i} className="flex gap-2">
            <label className="sr-only" htmlFor={`req-${i}`}>Skill {i + 1}</label>
            <select id={`req-${i}`} className="input" value={r.skill_id} onChange={(e) => setReqs(reqs.map((x, k) => (k === i ? { ...x, skill_id: Number(e.target.value) } : x)))}>
              <option value={0}>Choose a skill…</option>{skills.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
            <label className="sr-only" htmlFor={`lvl-${i}`}>Level {i + 1}</label>
            <select id={`lvl-${i}`} className="input w-40" value={r.level} onChange={(e) => setReqs(reqs.map((x, k) => (k === i ? { ...x, level: e.target.value } : x)))}>
              <option value="practiced">Practiced</option><option value="mastered">Mastered</option></select>
            <button className="rounded p-2 text-slate-500 hover:bg-red-50 hover:text-red-700" aria-label={`Remove skill ${i + 1}`} onClick={() => setReqs(reqs.filter((_, k) => k !== i))}><Trash2 className="h-4 w-4" /></button>
          </div>))}</div>
        <button className="btn-ghost btn-sm mt-2" onClick={() => setReqs([...reqs, { skill_id: 0, level: "practiced" }])}><Plus className="h-4 w-4" />Add skill</button>
      </fieldset>
      <label className="mt-3 inline-flex items-center gap-2 text-sm"><input type="checkbox" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} />Active</label>
      {err && <p role="alert" className="mt-2 text-sm text-red-700">{err}</p>}
      <div className="mt-3"><button className="btn-primary" onClick={save}>Save</button></div>
    </Modal>
  );
}
