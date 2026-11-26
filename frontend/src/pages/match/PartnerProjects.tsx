import { Handshake, Send } from "lucide-react";
import { useState } from "react";
import { Badge, Card, Empty, Field, Modal, Spinner } from "../../components/ui";
import { api } from "../../lib/api";
import { useApi } from "../../lib/hooks";

interface Need { decision_id: string; course_code: string; course_title: string; skill: string; note: string | null; shared_since: string; postings_requesting: number | null; postings_in_sample: number | null; already_offered: boolean }
export interface Project { id: string; course_code: string; course_title: string; skill: string; company: string; kind: string; title: string; description: string; dataset_url: string | null; deliverables: string[]; term: string | null; status: string; faculty_note: string | null; decided_by: string | null; forge_draft_id: string | null; participants: number; created_at: string }
export const PROJECT_STATUS: Record<string, string> = { offered: "blue", accepted: "green", completed: "green", declined: "slate", withdrawn: "slate" };

export default function PartnerProjects() {
  const needs = useApi<Need[]>("/partners/needs");
  const mine = useApi<Project[]>("/partners/projects");
  const people = useApi<{ student_id: string; name: string; headline: string | null; skill: string; course: string; project: string; term: string | null }[]>("/partners/participants");
  const [offer, setOffer] = useState<Need | null>(null);
  if (needs.loading || mine.loading) return <Spinner />;
  return (
    <div className="space-y-5">
      <p className="text-sm text-slate-600">Faculty share skills they decided to add to a course. Offer a real project, dataset or guest session; if they accept, it becomes the course's team project,
        students who complete it earn a badge naming your company, and you get first look at them.</p>
      <Card title={<span className="flex items-center gap-2"><Handshake className="h-4 w-4 text-comet-700" aria-hidden />Curriculum needs shared with partners</span>}>
        {!needs.data?.length ? <Empty title="Nothing shared right now">You'll see needs here when faculty share them.</Empty> : (
          <ul className="space-y-3">{needs.data.map((n) => (
            <li key={n.decision_id} className="flex flex-wrap items-start gap-3 rounded-lg border border-slate-200 p-3">
              <div className="min-w-0 flex-1"><div className="font-semibold text-slate-800">{n.skill} in {n.course_code} {n.course_title}</div>
                {n.note && <p className="text-sm text-slate-700">{n.note}</p>}
                {n.postings_requesting !== null && <p className="text-xs text-slate-500">{n.postings_requesting} of {n.postings_in_sample} sampled postings ask for it</p>}</div>
              {n.already_offered ? <Badge color="green">You offered</Badge> : <button className="btn-primary btn-sm" onClick={() => setOffer(n)}><Send className="h-4 w-4" />Offer a project</button>}
            </li>))}</ul>)}
      </Card>
      <Card title="Your offers" padded={false}>
        {!mine.data?.length ? <p className="p-4 text-sm text-slate-500">No offers yet.</p> : (
          <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Your offers">
            <table className="table-base"><thead><tr><th>Project</th><th>Course · skill</th><th>Status</th><th>Faculty note</th><th>Participants</th></tr></thead>
              <tbody>{mine.data.map((p) => (
                <tr key={p.id}><td className="font-medium">{p.title}<div className="text-xs text-slate-500">{p.kind.replace("_", " ")}{p.term ? ` · ${p.term}` : ""}</div></td>
                  <td className="text-sm">{p.course_code} · {p.skill}</td><td><Badge color={PROJECT_STATUS[p.status]}>{p.status}</Badge></td>
                  <td className="max-w-xs text-sm">{p.faculty_note ?? "—"}</td><td className="tabular-nums">{p.participants}</td></tr>))}</tbody></table>
          </div>)}
      </Card>
      <Card title="First look: students who completed your projects">
        {!people.data?.length ? <p className="text-sm text-slate-500">Participants who are open to opportunities appear here once faculty record completion.</p> : (
          <ul className="space-y-1 text-sm">{people.data.map((p) => <li key={p.student_id + p.project}><b>{p.name}</b>{p.headline ? ` · ${p.headline}` : ""} — {p.skill} in {p.course} ({p.project}{p.term ? `, ${p.term}` : ""})</li>)}</ul>)}
      </Card>
      {offer && <OfferForm need={offer} onClose={() => setOffer(null)} onDone={() => { setOffer(null); needs.reload(); mine.reload(); }} />}
    </div>
  );
}

function OfferForm({ need, onClose, onDone }: { need: Need; onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ kind: "project", title: "", description: "", dataset_url: "", deliverables: "", term: "" });
  const [err, setErr] = useState<string | null>(null);
  const send = async () => {
    setErr(null);
    try {
      await api.post("/partners/projects", { decision_id: need.decision_id, kind: f.kind, title: f.title, description: f.description, dataset_url: f.dataset_url || null,
        deliverables: f.deliverables.split("\n").map((x) => x.trim()).filter(Boolean), term: f.term || null });
      onDone();
    } catch (e) { setErr((e as Error).message); }
  };
  return (
    <Modal open onClose={onClose} title={`Offer for ${need.skill} in ${need.course_code}`} wide>
      <div className="grid gap-3 md:grid-cols-2">
        <Field label="Type"><select className="input" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option value="project">Team project</option><option value="dataset">Dataset</option><option value="guest_session">Guest session</option></select></Field>
        <Field label="Term"><input className="input" value={f.term} onChange={(e) => setF({ ...f, term: e.target.value })} placeholder="Fall 2027" /></Field>
        <div className="md:col-span-2"><Field label="Title"><input className="input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field></div>
        <div className="md:col-span-2"><Field label="What students will do (at least a few sentences)"><textarea className="input min-h-[100px]" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field></div>
        <Field label="Dataset link (https, optional)"><input className="input" value={f.dataset_url} onChange={(e) => setF({ ...f, dataset_url: e.target.value })} /></Field>
        <Field label="Deliverables (one per line)"><textarea className="input min-h-[70px]" value={f.deliverables} onChange={(e) => setF({ ...f, deliverables: e.target.value })} /></Field>
      </div>
      {err && <p role="alert" className="mt-2 text-sm text-red-700">{err}</p>}
      <button className="btn-primary mt-3" disabled={f.title.trim().length < 5 || f.description.trim().length < 30} onClick={send}>Send offer</button>
    </Modal>
  );
}
