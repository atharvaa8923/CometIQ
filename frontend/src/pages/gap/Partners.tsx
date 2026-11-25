import { Check, Handshake, Share2, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Card, Empty, Field, Modal, Spinner } from "../../components/ui";
import { api } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { PROJECT_STATUS, type Project } from "../match/PartnerProjects";
import type { Decision } from "./ReviewPanel";

type D = Decision & { share_with_partners?: boolean; partner_note?: string | null };

/** Faculty: share accepted additions with employer partners, review their offers, record who completed a sponsored project. */
export default function Partners({ sid }: { sid: string }) {
  const decs = useApi<{ active: D[] }>(`/gap/syllabi/${sid}/decisions`);
  const projects = useApi<Project[]>(`/partners/projects?syllabus_id=${sid}`);
  const [sharing, setSharing] = useState<D | null>(null);
  const [completing, setCompleting] = useState<Project | null>(null);
  if (decs.loading || projects.loading) return <Spinner />;
  const additions = (decs.data?.active ?? []).filter((d) => d.decision === "add_here" && d.status !== "implemented");
  const decide = async (p: Project, accept: boolean) => {
    const note = prompt(accept ? "Note for the partner (optional)" : "Why are you declining? (sent to the partner)") ?? "";
    try { await api.post(`/partners/projects/${p.id}/decide`, { accept, note }); projects.reload(); } catch (e) { alert((e as Error).message); }
  };
  return (
    <div className="space-y-5">
      <Card title={<span className="flex items-center gap-2"><Share2 className="h-4 w-4 text-comet-700" aria-hidden />Share accepted additions with employer partners</span>}>
        <p className="mb-3 text-sm text-slate-600">Partners see the course, the skill and a note you write for them, never your internal rationale. They can offer a project, dataset or guest session.</p>
        {!additions.length ? <Empty title="No accepted additions">Choose “Add to this course” on a reviewed gap first.</Empty> : (
          <ul className="space-y-2">{additions.map((d) => (
            <li key={d.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 p-3 text-sm">
              <div className="flex-1"><b>{d.skill}</b>{d.share_with_partners ? <span className="text-slate-600"> · shared: “{d.partner_note}”</span> : <span className="text-slate-500"> · not shared</span>}</div>
              <button className="btn-ghost btn-sm" onClick={() => setSharing(d)}>{d.share_with_partners ? "Edit or stop sharing" : "Share with partners"}</button>
            </li>))}</ul>)}
      </Card>
      <Card title={<span className="flex items-center gap-2"><Handshake className="h-4 w-4 text-comet-700" aria-hidden />Offers from partners</span>}>
        {!projects.data?.length ? <p className="text-sm text-slate-500">No offers yet.</p> : (
          <ul className="space-y-3">{projects.data.map((p) => (
            <li key={p.id} className="rounded-lg border border-slate-200 p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2"><b className="text-slate-800">{p.title}</b><Badge color={PROJECT_STATUS[p.status]}>{p.status}</Badge>
                <span className="text-xs text-slate-600">{p.company} · {p.kind.replace("_", " ")} · {p.skill}{p.term ? ` · ${p.term}` : ""}</span></div>
              <p className="mt-1 text-slate-700">{p.description}</p>
              {p.dataset_url && <p className="text-xs text-slate-600">Dataset: {p.dataset_url}</p>}
              {p.deliverables.length > 0 && <p className="text-xs text-slate-600">Deliverables: {p.deliverables.join("; ")}</p>}
              <div className="mt-2 flex flex-wrap gap-2">
                {p.status === "offered" && <><button className="btn-primary btn-sm" onClick={() => decide(p, true)}><Check className="h-4 w-4" />Accept into CometForge</button>
                  <button className="btn-ghost btn-sm" onClick={() => decide(p, false)}><X className="h-4 w-4" />Decline</button></>}
                {p.forge_draft_id && <Link className="btn-ghost btn-sm" to={`/forge/${p.forge_draft_id}`}>Open the draft</Link>}
                {(p.status === "accepted" || p.status === "completed") && <button className="btn-ghost btn-sm" onClick={() => setCompleting(p)}>Record students who completed it ({p.participants})</button>}
              </div>
            </li>))}</ul>)}
      </Card>
      {sharing && <ShareModal d={sharing} onClose={() => setSharing(null)} onDone={() => { setSharing(null); decs.reload(); }} />}
      {completing && <CompleteModal p={completing} onClose={() => setCompleting(null)} onDone={() => { setCompleting(null); projects.reload(); }} />}
    </div>
  );
}

function ShareModal({ d, onClose, onDone }: { d: D; onClose: () => void; onDone: () => void }) {
  const [note, setNote] = useState(d.partner_note ?? "");
  const [err, setErr] = useState<string | null>(null);
  const go = async (share: boolean) => { try { await api.put(`/gap/decisions/${d.id}/share`, { share, note }); onDone(); } catch (e) { setErr((e as Error).message); } };
  return (
    <Modal open onClose={onClose} title={`Share ${d.skill} with partners`}>
      <Field label="Note for partners: what should students be able to do?"><textarea className="input min-h-[80px]" value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      {err && <p role="alert" className="mt-2 text-sm text-red-700">{err}</p>}
      <div className="mt-3 flex gap-2"><button className="btn-primary btn-sm" onClick={() => go(true)}>Share</button>{d.share_with_partners && <button className="btn-ghost btn-sm" onClick={() => go(false)}>Stop sharing</button>}</div>
    </Modal>
  );
}

function CompleteModal({ p, onClose, onDone }: { p: Project; onClose: () => void; onDone: () => void }) {
  const { data } = useApi<{ student_id: string; name: string; status: string; term: string | null }[]>(`/partners/projects/${p.id}/candidates`);
  const [pick, setPick] = useState<Set<string>>(new Set());
  const [term, setTerm] = useState(p.term ?? "");
  const [err, setErr] = useState<string | null>(null);
  const go = async () => { try { await api.post(`/partners/projects/${p.id}/complete`, { student_ids: [...pick], term }); onDone(); } catch (e) { setErr((e as Error).message); } };
  return (
    <Modal open onClose={onClose} title={`Who completed “${p.title}”?`}>
      <p className="text-sm text-slate-600">Each student earns a faculty-verified {p.skill} badge naming {p.company}. {p.company} gets first look at participants who are open to opportunities.</p>
      {!data ? <Spinner /> : !data.length ? <p className="mt-2 text-sm text-slate-500">No students are enrolled in or completing this course in CometIQ.</p> : (
        <fieldset className="mt-3 space-y-1"><legend className="label">Students in the course</legend>{data.map((s) => (
          <label key={s.student_id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={pick.has(s.student_id)}
            onChange={(e) => { const n = new Set(pick); e.target.checked ? n.add(s.student_id) : n.delete(s.student_id); setPick(n); }} />{s.name} <span className="text-xs text-slate-500">{s.status}{s.term ? ` · ${s.term}` : ""}</span></label>))}</fieldset>)}
      <div className="mt-3"><Field label="Term"><input className="input" value={term} onChange={(e) => setTerm(e.target.value)} /></Field></div>
      {err && <p role="alert" className="mt-2 text-sm text-red-700">{err}</p>}
      <button className="btn-primary mt-3" disabled={!pick.size} onClick={go}>Issue badges ({pick.size})</button>
    </Modal>
  );
}
