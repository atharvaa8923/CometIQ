import { BadgeCheck, ExternalLink, FileText, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Badge, Card, Empty, PageHeader, Spinner, Tabs } from "../components/ui";
import { api } from "../lib/api";
import { useApi } from "../lib/hooks";
import { useToast } from "../lib/toast";
import { KIND, StatusChip, openFile, type EvidenceRow } from "./match/EvidencePortal";

function ReviewCard({ e, onDone }: { e: EvidenceRow; onDone: () => void }) {
  const toast = useToast();
  const [bonus, setBonus] = useState(e.suggested_bonus);
  const [note, setNote] = useState("");
  const [skills, setSkills] = useState(e.skills);
  const [busy, setBusy] = useState(false);
  const K = KIND[e.kind];
  const decide = async (decision: "verified" | "rejected") => {
    setBusy(true);
    try {
      await api.post(`/evidence/${e.id}/review`, { decision, bonus_points: bonus, note: note || null, skill_ids: skills.map((s) => s.id) });
      toast(decision === "verified" ? `Verified${bonus ? ` with +${bonus} bonus points` : ""}` : "Marked as not verified"); onDone();
    } catch (x) { toast((x as Error).message, "error"); } finally { setBusy(false); }
  };
  return (
    <Card title={<span className="flex items-center gap-2"><K.Icon className="h-4 w-4 text-comet-600" />{e.title}</span>} actions={<StatusChip e={e} />}>
      <div className="grid gap-4 md:grid-cols-[1fr_280px]">
        <div className="space-y-2 text-sm">
          <div className="text-xs text-slate-500"><b className="text-slate-700">{e.student?.name}</b> ({e.student?.email}) · {K.label}{e.issuer ? ` · ${e.issuer}` : ""}{e.course ? ` · ${e.course.code}` : ""}{e.issued_on ? ` · ${e.issued_on}` : ""} · submitted {new Date(e.created_at).toLocaleDateString()}</div>
          <p className="whitespace-pre-wrap text-slate-700">{e.description || <i className="text-slate-400">No description</i>}</p>
          {e.credential_id && <div className="text-xs">Credential ID: <code className="rounded bg-slate-100 px-1">{e.credential_id}</code></div>}
          <div className="flex flex-wrap gap-3 text-xs">
            {e.file ? <button className="inline-flex items-center gap-1 font-semibold text-comet-700 hover:underline" onClick={() => openFile(e.id)}><FileText className="h-3.5 w-3.5" />Open {e.file.filename} ({Math.round(e.file.size / 1024)} KB)</button> : <span className="text-slate-400">No file uploaded</span>}
            {e.credential_url && <a className="inline-flex items-center gap-1 font-semibold text-comet-700 hover:underline" href={e.credential_url} target="_blank" rel="noreferrer"><ExternalLink className="h-3.5 w-3.5" />Check verification link</a>}
          </div>
          <div><div className="label mt-2">Skills this proves (remove any that don't apply)</div>
            <div className="flex flex-wrap gap-1">{skills.map((s) => <span key={s.id} className="chip bg-comet-100 text-comet-800">{s.name}
              {e.status === "pending" && <button className="ml-0.5 text-comet-600 hover:text-red-600" aria-label={`Remove ${s.name}`} onClick={() => setSkills(skills.filter((x) => x.id !== s.id))}>×</button>}</span>)}</div></div>
          {e.review_note && <div className="rounded-lg bg-slate-50 p-2 text-xs text-slate-600"><b>Note:</b> {e.review_note}</div>}
        </div>
        {e.status === "pending" && (
          <div className="space-y-3 rounded-lg bg-slate-50 p-3">
            <label className="block"><span className="label">Bonus points (0–20)</span>
              <input type="number" min={0} max={20} className="input" value={bonus} onChange={(x) => setBonus(+x.target.value)} />
              <span className="text-[11px] text-slate-500">Added to job fit when the job needs these skills (max +15 per job).</span></label>
            <label className="block"><span className="label">Note to student</span><textarea className="input h-16 text-xs" value={note} onChange={(x) => setNote(x.target.value)} placeholder="Required when rejecting" /></label>
            <div className="flex gap-2">
              <button className="btn-primary btn-sm flex-1" disabled={busy} onClick={() => decide("verified")}><BadgeCheck className="h-4 w-4" />Verify</button>
              <button className="btn-ghost btn-sm flex-1 text-red-700" disabled={busy || !note.trim()} title={note.trim() ? "" : "Add a note first"} onClick={() => decide("rejected")}>Reject</button>
            </div>
          </div>)}
      </div>
    </Card>
  );
}

export default function Verifications() {
  const [status, setStatus] = useState<"pending" | "verified" | "rejected">("pending");
  const { data, loading, reload } = useApi<EvidenceRow[]>(`/evidence/queue?status=${status}`);
  return (
    <div>
      <PageHeader icon={<ShieldCheck className="h-5 w-5" />} title="Verifications" subtitle="Review student courses, certifications and projects before they count as verified skills" />
      <Tabs value={status} onChange={setStatus} tabs={[{ id: "pending", label: <>Pending {status === "pending" && data ? <Badge color="orange">{data.length}</Badge> : null}</> }, { id: "verified", label: "Verified" }, { id: "rejected", label: "Rejected" }]} />
      {loading ? <Spinner /> : !data?.length ? <Empty icon={<ShieldCheck className="h-8 w-8" />} title={status === "pending" ? "All caught up" : "Nothing here yet"} /> : (
        <div className="space-y-4">{data.map((e) => <ReviewCard key={e.id} e={e} onDone={reload} />)}</div>)}
    </div>
  );
}
