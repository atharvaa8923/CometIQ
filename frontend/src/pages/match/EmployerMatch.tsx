import { BriefcaseBusiness, ChevronDown, ChevronUp, Plus, Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Card, Empty, ErrorBox, Field, Modal, PageHeader, Spinner, Tabs } from "../../components/ui";
import { api } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { useToast } from "../../lib/toast";
import { Breakdown, FitBadge, type MatchResult } from "./Breakdown";

interface EJob { id: string; title: string; location: string | null; employment_type: string; is_open: boolean; applications: number; skills: { name: string; importance: string }[] }
interface Cand extends MatchResult { student: { id: string; name: string; headline: string | null; program: string | null; concentration: string | null; career_goal: string | null; has_resume: boolean }; application: { status: string; initiated_by: string } | null }
type Pipeline = Record<string, { id: string; score: number; student: { id: string; name: string }; job: { id: string; title: string }; initiated_by: string }[]>;
const STAGES = ["applied", "shortlisted", "interview", "offer", "hired", "rejected"] as const;
const STATUS_COLOR: Record<string, string> = { applied: "blue", shortlisted: "purple", interview: "orange", offer: "green", hired: "green", rejected: "red" };

function PostJob({ open, onClose, onPosted }: { open: boolean; onClose: () => void; onPosted: () => void }) {
  const [f, setF] = useState({ title: "", location: "", employment_type: "Full-time", description: "" });
  const [skills, setSkills] = useState<{ name: string; importance: string }[] | null>(null);
  const [all, setAll] = useState<string[]>([]);
  const [add, setAdd] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) api.get<{ name: string }[]>("/skills").then((s) => setAll(s.map((x) => x.name))); }, [open]);
  const extract = async () => {
    setBusy(true); setErr(null);
    try { const r = await api.post<{ skills: { name: string; importance: string }[] }>("/match/employer/extract", { title: f.title, description: f.description }); setSkills(r.skills); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const post = async () => {
    setBusy(true);
    try { await api.post("/match/employer/jobs", { ...f, skills }); onPosted(); onClose(); setSkills(null); setF({ title: "", location: "", employment_type: "Full-time", description: "" }); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Modal open={open} onClose={onClose} title="Post a job" wide>
      <div className="space-y-3">
        <ErrorBox error={err} />
        <div className="grid gap-3 md:grid-cols-3">
          <Field label="Title"><input className="input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
          <Field label="Location"><input className="input" value={f.location} onChange={(e) => setF({ ...f, location: e.target.value })} /></Field>
          <Field label="Type"><select className="input" value={f.employment_type} onChange={(e) => setF({ ...f, employment_type: e.target.value })}>{["Full-time", "Internship", "Part-time", "Contract"].map((t) => <option key={t}>{t}</option>)}</select></Field>
        </div>
        <Field label="Description" hint="Put nice-to-haves under a 'Preferred' heading — CometIQ marks them as preferred skills."><textarea className="input h-40" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        {!skills ? <button className="btn-primary" onClick={extract} disabled={busy || f.title.length < 2}><Sparkles className="h-4 w-4" />{busy ? "Extracting…" : "Extract skills"}</button> : (
          <div className="space-y-3 rounded-lg border border-slate-200 p-4">
            <div className="label">Skills we'll match on — click to toggle required/preferred</div>
            <div className="flex flex-wrap gap-1.5">{skills.map((s, i) => (
              <span key={s.name} className={`chip cursor-pointer ${s.importance === "required" ? "bg-comet-100 text-comet-800" : "bg-slate-100 text-slate-600"}`}
                onClick={() => setSkills(skills.map((x, k) => (k === i ? { ...x, importance: x.importance === "required" ? "preferred" : "required" } : x)))}>
                {s.name} · {s.importance}<button onClick={(e) => { e.stopPropagation(); setSkills(skills.filter((_, k) => k !== i)); }} aria-label={`Remove ${s.name}`}><X className="h-3 w-3" /></button></span>))}</div>
            <div className="flex gap-2"><input className="input" list="all-skills" placeholder="Add a skill…" value={add} onChange={(e) => setAdd(e.target.value)} />
              <datalist id="all-skills">{all.map((n) => <option key={n} value={n} />)}</datalist>
              <button className="btn-ghost" onClick={() => { if (all.includes(add) && !skills.some((s) => s.name === add)) { setSkills([...skills, { name: add, importance: "required" }]); setAdd(""); } }}><Plus className="h-4 w-4" /></button></div>
            <button className="btn-accent w-full" onClick={post} disabled={busy || !skills.length}>Post job & find candidates</button>
          </div>)}
      </div>
    </Modal>
  );
}

export default function EmployerMatch() {
  const toast = useToast();
  const [tab, setTab] = useState<"jobs" | "cands" | "pipeline">("cands");
  const jobs = useApi<EJob[]>("/match/employer/jobs");
  const [jid, setJid] = useState("");
  const [open, setOpen] = useState(false);
  const [exp, setExp] = useState<string | null>(null);
  useEffect(() => { if (!jid && jobs.data?.length) setJid(jobs.data[0].id); }, [jobs.data, jid]);
  const cands = useApi<{ candidates: Cand[] }>(jid ? `/match/employer/jobs/${jid}/candidates` : null);
  const pipe = useApi<Pipeline>("/match/employer/pipeline");
  const setStatus = async (sid: string, status: string) => {
    await api.post(`/match/employer/jobs/${jid}/candidates/${sid}`, { status }); toast(`Candidate moved to ${status}`); cands.reload(); pipe.reload(); jobs.reload();
  };

  return (
    <div className="space-y-5">
      <PageHeader icon={<BriefcaseBusiness className="h-5 w-5" />} accent="navy" title="CometMatch" subtitle="Find students whose verified skills fit your roles"
        actions={<button className="btn-accent" onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Post a job</button>} />
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "cands", label: "Ranked candidates" }, { id: "jobs", label: `My jobs${jobs.data ? ` (${jobs.data.length})` : ""}` }, { id: "pipeline", label: "Hiring pipeline" }]} />

      {tab === "cands" && (!jobs.data?.length ? <Empty icon={<BriefcaseBusiness className="h-8 w-8" />} title="Post your first job">CometIQ extracts the skills and ranks matching students instantly.</Empty> : (
        <Card padded={false} title={<select className="input w-96 py-1.5" value={jid} onChange={(e) => setJid(e.target.value)} aria-label="Job">{jobs.data.map((j) => <option key={j.id} value={j.id}>{j.title} — {j.location}</option>)}</select>}>
          {cands.loading ? <Spinner /> : (
            <ul className="divide-y divide-slate-100">{cands.data?.candidates.map((c) => (
              <li key={c.student.id} className="px-5 py-4">
                <div className="flex items-start gap-4">
                  <FitBadge score={c.score} label={c.label} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2"><span className="font-semibold text-slate-800">{c.student.name}</span>{c.application && <Badge color={STATUS_COLOR[c.application.status]}>{c.application.status}</Badge>}</div>
                    <div className="text-xs text-slate-500">{c.student.headline} · {c.student.program ?? "Program not set"}{c.student.concentration ? ` (${c.student.concentration})` : ""}</div>
                    <div className="mt-1 text-xs text-slate-600">{c.summary}</div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <select className="input w-36 py-1.5 text-xs" value={c.application?.status ?? ""} onChange={(e) => e.target.value && setStatus(c.student.id, e.target.value)} aria-label={`Status for ${c.student.name}`}>
                      <option value="">Move to…</option>{STAGES.map((s) => <option key={s} value={s}>{s === "shortlisted" ? "Shortlist / invite" : s[0].toUpperCase() + s.slice(1)}</option>)}</select>
                    <button className="btn-ghost btn-sm" onClick={() => setExp(exp === c.student.id ? null : c.student.id)} aria-expanded={exp === c.student.id}>
                      {exp === c.student.id ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}Why</button>
                  </div>
                </div>
                {exp === c.student.id && <div className="mt-4 rounded-lg bg-slate-50 p-4"><Breakdown m={c} /></div>}
              </li>))}</ul>)}
        </Card>))}

      {tab === "jobs" && (
        <div className="grid gap-4 md:grid-cols-2">{jobs.data?.map((j) => (
          <Card key={j.id} title={j.title} actions={<Badge color={j.is_open ? "green" : "slate"}>{j.is_open ? "Open" : "Closed"}</Badge>}>
            <div className="text-sm text-slate-500">{j.location} · {j.employment_type} · {j.applications} candidates in pipeline</div>
            <div className="mt-3 flex flex-wrap gap-1">{j.skills.map((s) => <Badge key={s.name} color={s.importance === "required" ? "green" : "slate"}>{s.name}</Badge>)}</div>
            <button className="btn-ghost btn-sm mt-4" onClick={() => { setJid(j.id); setTab("cands"); }}>View candidates</button>
          </Card>))}</div>)}

      {tab === "pipeline" && (
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">{STAGES.map((s) => (
          <div key={s} className="rounded-xl bg-slate-100 p-3">
            <div className="mb-2 flex items-center justify-between text-xs font-bold uppercase tracking-wide text-slate-600">{s}<span>{pipe.data?.[s]?.length ?? 0}</span></div>
            <div className="space-y-2">{pipe.data?.[s]?.map((a) => (
              <div key={a.id} className="rounded-lg bg-white p-2.5 text-sm shadow-card"><div className="font-semibold text-slate-800">{a.student.name}</div>
                <div className="text-xs text-slate-500">{a.job.title}</div><div className="mt-1 text-xs font-semibold text-comet-700">{Math.round(a.score)}% fit</div></div>))}</div>
          </div>))}</div>)}

      <PostJob open={open} onClose={() => setOpen(false)} onPosted={() => { toast("Job posted"); jobs.reload(); }} />
    </div>
  );
}
