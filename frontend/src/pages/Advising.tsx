import { CheckCircle2, ClipboardCheck, Download, MessageSquareWarning } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Card, Empty, PageHeader, ScoreBar, Spinner } from "../components/ui";
import { api, download } from "../lib/api";
import { useApi } from "../lib/hooks";
import { useToast } from "../lib/toast";

interface Row { id: string; name: string; email: string; program: string | null; career_goal: string | null; review_status: string; review_id: string | null; submitted_at: string | null; pending_evidence: number }
interface Term { term: string; credits: number; courses: { id: string; code: string; title: string; credits: number }[] }
interface Detail {
  student: { id: string; name: string; email: string };
  profile: { career_goal: string | null };
  progress: { program: { name: string } | null; concentration: { name: string } | null; sch: Record<string, number>; total_sch: number; core: { done: number; total: number } };
  courses: { code: string; title: string; status: string; term: string | null }[];
  saved_plan: Term[];
  readiness: { goal: string | null; now: number; with_plan: number; skills: { skill: string; status: string }[] };
  evidence: { id: string; title: string; kind: string; status: string; bonus_points: number }[];
  review: { id: string; status: string; student_note: string | null; advisor_note: string | null; advisor: string | null; changed_since: boolean } | null;
  snapshot: { program: string; concentration: string | null; career_goal: string | null; terms: Term[] } | null;
}
const STATUS: Record<string, [string, string]> = {
  submitted: ["blue", "Awaiting review"], changes_requested: ["orange", "Changes requested"], approved: ["green", "Approved"], none: ["slate", "Not submitted"],
};

export default function Advising() {
  const toast = useToast();
  const [filter, setFilter] = useState("");
  const roster = useApi<Row[]>(`/advising/students?status=${filter}`);
  const [sel, setSel] = useState<string | null>(null);
  useEffect(() => { if (!sel && roster.data?.length) setSel(roster.data[0].id); }, [roster.data, sel]);
  const d = useApi<Detail>(sel ? `/advising/students/${sel}` : null);
  const [note, setNote] = useState("");
  const decide = async (decision: "approved" | "changes_requested") => {
    if (!d.data?.review) return;
    try { await api.post(`/advising/reviews/${d.data.review.id}`, { decision, note: note || null }); toast(decision === "approved" ? "Plan approved" : "Changes requested"); setNote(""); d.reload(); roster.reload(); }
    catch (e) { toast((e as Error).message, "error"); }
  };
  const plan = d.data?.snapshot?.terms ?? d.data?.saved_plan ?? [];

  return (
    <div>
      <PageHeader icon={<ClipboardCheck className="h-5 w-5" />} title="Advising" subtitle="Review and approve student degree plans" />
      <div className="grid gap-5 lg:grid-cols-[340px_1fr]">
        <Card padded={false} title={<select className="input w-52 py-1" value={filter} onChange={(e) => { setFilter(e.target.value); setSel(null); }} aria-label="Filter">
          <option value="">All students</option><option value="submitted">Awaiting review</option><option value="changes_requested">Changes requested</option><option value="approved">Approved</option><option value="none">Not submitted</option></select>}>
          {roster.loading ? <Spinner /> : !roster.data?.length ? <p className="p-5 text-sm text-slate-500">No students in this view.</p> : (
            <ul className="max-h-[70vh] divide-y divide-slate-100 overflow-y-auto">{roster.data.map((r) => (
              <li key={r.id}><button onClick={() => setSel(r.id)} className={`w-full px-4 py-3 text-left hover:bg-slate-50 ${sel === r.id ? "bg-comet-50" : ""}`}>
                <div className="flex items-center justify-between gap-2"><span className="font-semibold text-slate-800">{r.name}</span><Badge color={STATUS[r.review_status][0]}>{STATUS[r.review_status][1]}</Badge></div>
                <div className="truncate text-xs text-slate-500">{r.program ?? "No program"}{r.career_goal ? ` · ${r.career_goal}` : ""}</div>
                {r.pending_evidence > 0 && <div className="mt-1 text-xs text-amber-700">{r.pending_evidence} item{r.pending_evidence > 1 ? "s" : ""} to verify</div>}
              </button></li>))}</ul>)}
        </Card>
        {!sel ? <Empty title="Select a student" /> : d.loading || !d.data ? <Spinner /> : (
          <div className="space-y-4">
            <Card title={<span>{d.data.student.name} <span className="font-normal text-slate-500">· {d.data.student.email}</span></span>}
              actions={<button className="btn-ghost btn-sm" onClick={() => download(`/advising/students/${d.data!.student.id}/plan.pdf`, `plan-${d.data!.student.name}.pdf`)}><Download className="h-4 w-4" />PDF</button>}>
              <div className="grid gap-4 md:grid-cols-3 text-sm">
                <div><div className="label">Program</div>{d.data.progress.program?.name ?? "—"}{d.data.progress.concentration ? <div className="text-xs text-slate-500">{d.data.progress.concentration.name}</div> : null}</div>
                {d.data.progress.program && <div><div className="label">Progress</div>{d.data.progress.sch.completed}/{d.data.progress.total_sch} SCH · core {d.data.progress.core.done}/{d.data.progress.core.total}
                  <ScoreBar value={(d.data.progress.sch.completed / Math.max(d.data.progress.total_sch, 1)) * 100} tone="comet" /></div>}
                <div><div className="label">Career readiness</div>{d.data.readiness.goal ? `${Math.round(d.data.readiness.now)}% → ${Math.round(d.data.readiness.with_plan)}% (${d.data.readiness.goal})` : "No goal set"}</div>
              </div>
            </Card>
            {d.data.review ? (
              <Card title={<span className="flex items-center gap-2">Submitted plan <Badge color={STATUS[d.data.review.status][0]}>{STATUS[d.data.review.status][1]}</Badge>{d.data.review.changed_since && <Badge color="orange">changed since submission</Badge>}</span>}>
                {d.data.review.student_note && <div className="mb-3 rounded-lg bg-slate-50 p-3 text-sm"><b>Student note:</b> {d.data.review.student_note}</div>}
                <div className="grid gap-3 md:grid-cols-2">{plan.map((t) => (
                  <div key={t.term} className="rounded-lg border border-slate-200 p-3"><div className="mb-1 text-sm font-bold text-comet-900">{t.term} <span className="text-xs font-normal text-slate-500">{t.credits} SCH</span></div>
                    <ul className="space-y-0.5 text-sm">{t.courses.map((c) => <li key={c.id}><b className="text-comet-800">{c.code}</b> {c.title}</li>)}</ul></div>))}</div>
                <div className="mt-4 space-y-2 border-t border-slate-100 pt-4">
                  {d.data.review.advisor_note && <div className="text-sm text-slate-600"><b>Your last note:</b> {d.data.review.advisor_note}</div>}
                  <textarea className="input h-20" placeholder="Feedback for the student (required when requesting changes)" value={note} onChange={(e) => setNote(e.target.value)} />
                  <div className="flex gap-2">
                    <button className="btn-primary" onClick={() => decide("approved")}><CheckCircle2 className="h-4 w-4" />Approve plan</button>
                    <button className="btn-ghost text-amber-800" disabled={!note.trim()} onClick={() => decide("changes_requested")}><MessageSquareWarning className="h-4 w-4" />Request changes</button>
                  </div>
                </div>
              </Card>) : <Empty title="No plan submitted yet">The student hasn't sent a plan for review.</Empty>}
            <div className="grid gap-4 md:grid-cols-2">
              <Card title="Courses">
                <ul className="space-y-1 text-sm">{d.data.courses.filter((c) => c.status !== "planned").map((c) => <li key={c.code}><b>{c.code}</b> {c.title} <Badge>{c.status}</Badge></li>)}
                  {!d.data.courses.some((c) => c.status !== "planned") && <li className="text-slate-500">None recorded</li>}</ul>
              </Card>
              <Card title="Courses & certifications" actions={<Link to="/verify" className="text-xs font-semibold text-comet-700 hover:underline">Verifications →</Link>}>
                {!d.data.evidence.length ? <p className="text-sm text-slate-500">None submitted.</p> : <ul className="space-y-1 text-sm">{d.data.evidence.map((e) => (
                  <li key={e.id} className="flex justify-between gap-2"><span>{e.title}</span><Badge color={e.status === "verified" ? "green" : e.status === "rejected" ? "red" : "yellow"}>{e.status}{e.bonus_points ? ` +${e.bonus_points}` : ""}</Badge></li>))}</ul>}
              </Card>
            </div>
          </div>)}
      </div>
    </div>
  );
}
