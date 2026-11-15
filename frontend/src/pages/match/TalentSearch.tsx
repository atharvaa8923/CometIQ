import { Award, BadgeCheck, Search, UserPlus, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge, Card, Empty, Modal, Spinner } from "../../components/ui";
import { api } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { useToast } from "../../lib/toast";

interface Result {
  student: { id: string; name: string; headline: string | null; program: string | null; career_goal: string | null };
  score: number; skill_count: number; top_skills: string[]; verified: string[]; faculty_verified: string[];
  skills: { skill: string; level: number; sources: string[] }[];
}

/** Search every student who opted in to CometMatch — not just applicants. */
export default function TalentSearch({ jobs }: { jobs: { id: string; title: string }[] }) {
  const toast = useToast();
  const allSkills = useApi<{ id: number; name: string; category: string }[]>("/skills");
  const programs = useApi<{ id: string; name: string }[]>("/programs");
  const meta = useApi<{ role_families: string[] }>("/meta");
  const [picked, setPicked] = useState<{ id: number; name: string }[]>([]);
  const [add, setAdd] = useState("");
  const [q, setQ] = useState("");
  const [program, setProgram] = useState("");
  const [goal, setGoal] = useState("");
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [facultyOnly, setFacultyOnly] = useState(false);
  const [invite, setInvite] = useState<Result | null>(null);
  const [jobId, setJobId] = useState("");
  const qs = useMemo(() => new URLSearchParams({ skills: picked.map((p) => p.id).join(","), q, program_id: program, goal, verified_only: String(verifiedOnly), faculty_verified: String(facultyOnly) }).toString(), [picked, q, program, goal, verifiedOnly, facultyOnly]);
  const { data, loading } = useApi<{ searched: string[]; results: Result[] }>(`/match/employer/talent?${qs}`);

  const addSkill = (name: string) => {
    const s = allSkills.data?.find((x) => x.name.toLowerCase() === name.toLowerCase());
    if (s && !picked.some((p) => p.id === s.id)) setPicked([...picked, { id: s.id, name: s.name }]);
    setAdd("");
  };
  const sendInvite = async () => {
    if (!invite || !jobId) return;
    await api.post(`/match/employer/jobs/${jobId}/candidates/${invite.student.id}`, { status: "shortlisted" });
    toast(`${invite.student.name} invited and added to your shortlist`); setInvite(null);
  };

  return (
    <div className="space-y-4">
      <Card>
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="label mb-0">Must-have skills</span>
            {picked.map((p) => <span key={p.id} className="chip bg-navy-500 text-white">{p.name}<button aria-label={`Remove ${p.name}`} onClick={() => setPicked(picked.filter((x) => x.id !== p.id))}><X className="h-3 w-3" /></button></span>)}
            <input className="input w-60 py-1.5" list="talent-skills" placeholder="Add a skill, e.g. SQL" value={add} onChange={(e) => setAdd(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addSkill(add)} onBlur={() => add && addSkill(add)} aria-label="Add skill filter" />
            <datalist id="talent-skills">{allSkills.data?.map((s) => <option key={s.id} value={s.name} />)}</datalist>
          </div>
          <div className="grid gap-2 md:grid-cols-4">
            <div className="relative"><Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" /><input className="input pl-9" placeholder="Name or headline" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search name" /></div>
            <select className="input" value={program} onChange={(e) => setProgram(e.target.value)} aria-label="Program"><option value="">Any program</option>{programs.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
            <select className="input" value={goal} onChange={(e) => setGoal(e.target.value)} aria-label="Career goal"><option value="">Any career goal</option>{meta.data?.role_families.map((r) => <option key={r}>{r}</option>)}</select>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-comet-600" checked={verifiedOnly} onChange={(e) => setVerifiedOnly(e.target.checked)} />Has verified certifications</label>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-comet-600" checked={facultyOnly} onChange={(e) => setFacultyOnly(e.target.checked)} />Count only faculty-verified skills</label>
          </div>
        </div>
      </Card>
      {loading ? <Spinner /> : !data?.results.length ? <Empty icon={<Search className="h-8 w-8" />} title="No students match these filters">Try fewer must-have skills.</Empty> : (
        <Card padded={false} title={`${data.results.length} students${data.searched.length ? ` · ranked by ${data.searched.join(", ")}` : " · open to opportunities"}`}>
          <ul className="divide-y divide-slate-100">{data.results.map((r) => (
            <li key={r.student.id} className="flex flex-wrap items-start gap-4 px-5 py-4">
              <div className={`flex w-20 shrink-0 flex-col items-center rounded-lg px-2 py-1.5 ${data.searched.length ? (r.score >= 70 ? "bg-comet-700 text-white" : r.score >= 40 ? "bg-comet-100 text-comet-800" : "bg-slate-100 text-slate-600") : "bg-slate-100 text-slate-700"}`}>
                <span className="text-lg font-bold leading-none">{data.searched.length ? `${Math.round(r.score)}%` : r.skill_count}</span>
                <span className="mt-0.5 text-[10px] font-semibold uppercase">{data.searched.length ? "skill match" : "skills"}</span></div>
              <div className="min-w-0 flex-1">
                <div className="font-semibold text-slate-800">{r.student.name}</div>
                <div className="text-xs text-slate-500">{r.student.headline} · {r.student.program ?? "—"}{r.student.career_goal ? ` · wants ${r.student.career_goal}` : ""}</div>
                {r.skills.length > 0 && <div className="mt-1.5 flex flex-wrap gap-1">{r.skills.map((s) => (
                  <Badge key={s.skill} color={s.level >= 0.95 ? "green" : s.level > 0 ? "yellow" : "red"} title={s.sources.join(", ") || "no evidence"}>{s.level >= 0.95 ? "✓" : s.level > 0 ? "~" : "✗"} {s.skill}</Badge>))}</div>}
                {!r.skills.length && <div className="mt-1.5 flex flex-wrap gap-1">{r.top_skills.map((s) => <Badge key={s}>{s}</Badge>)}</div>}
                {r.faculty_verified?.length > 0 && <div className="mt-1.5 flex flex-wrap gap-1">{r.faculty_verified.map((v) => <span key={v} className="chip bg-comet-100 text-comet-800"><Award className="h-3.5 w-3.5" aria-hidden />{v} · faculty-verified</span>)}</div>}
                {r.verified.length > 0 && <div className="mt-1.5 flex flex-wrap gap-1">{r.verified.map((v) => <span key={v} className="chip bg-green-50 text-green-800"><BadgeCheck className="h-3.5 w-3.5 text-green-600" aria-hidden />{v}</span>)}</div>}
              </div>
              <button className="btn-ghost btn-sm" disabled={!jobs.length} title={jobs.length ? "" : "Post a job first"} onClick={() => { setInvite(r); setJobId(jobs[0]?.id ?? ""); }}><UserPlus className="h-4 w-4" />Invite to apply</button>
            </li>))}</ul>
        </Card>)}
      <Modal open={!!invite} onClose={() => setInvite(null)} title={`Invite ${invite?.student.name ?? ""}`}>
        <div className="space-y-3">
          <select className="input" value={jobId} onChange={(e) => setJobId(e.target.value)} aria-label="Job">{jobs.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}</select>
          <p className="text-sm text-slate-500">They'll see the invitation in their Applications tab and can accept with one click.</p>
          <button className="btn-accent w-full" onClick={sendInvite}>Send invitation</button>
        </div>
      </Modal>
    </div>
  );
}
