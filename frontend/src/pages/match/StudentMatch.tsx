import { BriefcaseBusiness, ExternalLink, FileUp, Lightbulb, Loader2, Plus, Send, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";
import Badges from "./Badges";
import { StackProgress } from "./Stacks";
import EvidencePortal from "./EvidencePortal";
import { useState } from "react";
import { Badge, Card, Empty, Modal, PageHeader, Spinner, Tabs } from "../../components/ui";
import { api } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { useToast } from "../../lib/toast";
import { AiExplain, Breakdown, FitBadge, type MatchResult } from "./Breakdown";

interface JobMatch { id: string; title: string; company: string | null; location: string | null; employment_type: string; role_family: string | null; source: string; url: string | null;
  score: number; bonus: number; label: string; summary: string; matched: string[]; missing: string[]; can_apply: boolean; application: string | null }
interface LearnSkill { skill_id: number; skill: string; category: string; jobs: number; points: number; points_per_job: number; current_level: number; examples: string[];
  courses: { id: string; code: string; title: string; in_program: boolean; status: string | null }[] }
interface Tips { summary: string; tips: { title: string; detail: string; priority: string }[]; engine: string }
interface Detail extends MatchResult { job: { id: string; title: string; company: string; location: string; description: string; url: string | null; employment_type: string }; can_apply: boolean; application: { status: string } | null }
interface Me { headline: string | null; open_to_match: boolean; resume_filename: string | null; resume_preview: string; skills: { id: number; name: string; category: string; level: number; sources: string[] }[] }
interface AppRow { id: string; status: string; score: number; initiated_by: string; updated_at: string; job: { id: string; title: string; company: string; location: string } }

const STATUS_COLOR: Record<string, string> = { applied: "blue", shortlisted: "purple", interview: "orange", offer: "green", hired: "green", rejected: "red" };

export default function StudentMatch() {
  const toast = useToast();
  const [tab, setTab] = useState<"jobs" | "evidence" | "badges" | "stacks" | "learn" | "profile" | "apps">("jobs");
  const learn = useApi<{ career_goal: string | null; skills: LearnSkill[] }>(tab === "learn" ? "/match/learn-next" : null);
  const [tips, setTips] = useState<Tips | null>(null);
  const [tipsBusy, setTipsBusy] = useState(false);
  const getTips = async () => { setTipsBusy(true); try { setTips(await api.post<Tips>("/match/me/resume-tips")); } finally { setTipsBusy(false); } };
  const planCourse = async (course_id: string, code: string) => {
    const r = await api.post<{ warning: string | null }>("/path/courses", { course_id, status: "planned" });
    toast(r.warning ? `${code} added to your plan. ${r.warning}` : `${code} added to your CometPath plan`, r.warning ? "info" : "success"); learn.reload();
  };
  const [fam, setFam] = useState("");
  const [postedOnly, setPostedOnly] = useState(false);
  const meta = useApi<{ role_families: string[] }>("/meta");
  const jobs = useApi<{ has_skills: boolean; items: JobMatch[] }>(`/match/jobs?role_family=${encodeURIComponent(fam)}&posted_only=${postedOnly}`);
  const me = useApi<Me>("/match/me");
  const apps = useApi<AppRow[]>("/match/applications");
  const [sel, setSel] = useState<string | null>(null);
  const detail = useApi<Detail>(sel ? `/match/jobs/${sel}` : null);
  const [uploading, setUploading] = useState(false);
  const [headline, setHeadline] = useState<string | null>(null);

  const upload = async (f: File) => {
    setUploading(true);
    const fd = new FormData(); fd.append("file", f);
    try { const r = await api.post<{ skills_found: number }>("/match/me/resume", fd); toast(`Resume analyzed: ${r.skills_found} skills found`); me.reload(); jobs.reload(); }
    catch (e) { toast((e as Error).message, "error"); } finally { setUploading(false); }
  };
  const apply = async (id: string) => {
    try { await api.post(`/match/jobs/${id}/apply`, {}); toast("Application sent"); detail.reload(); jobs.reload(); apps.reload(); }
    catch (e) { toast((e as Error).message, "error"); }
  };
  const saveProfile = async (patch: Partial<Me>) => {
    await api.put("/match/me", { headline: patch.headline ?? me.data?.headline, open_to_match: patch.open_to_match ?? me.data?.open_to_match });
    me.reload(); toast("Profile updated");
  };

  return (
    <div className="space-y-5">
      <PageHeader icon={<BriefcaseBusiness className="h-5 w-5" />} accent="navy" title="CometMatch" subtitle="Student–Employer Talent Matching"
        actions={<label className="btn-primary cursor-pointer"><FileUp className="h-4 w-4" />{uploading ? "Analyzing…" : me.data?.resume_filename ? "Update resume" : "Upload resume"}
          <input type="file" accept=".pdf,.docx,.txt" className="hidden" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} /></label>} />
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "jobs", label: "Best-fit jobs" }, { id: "evidence", label: "Courses & certifications" }, { id: "badges", label: "Verified skill badges" }, { id: "stacks", label: "Skill stacks" }, { id: "learn", label: "Skills to learn next" }, { id: "profile", label: "Skill profile & resume tips" }, { id: "apps", label: `Applications${apps.data?.length ? ` (${apps.data.length})` : ""}` }]} />

      {tab === "jobs" && (
        <Card padded={false} title={<div className="flex flex-wrap items-center gap-3">
          <select className="input w-60 py-1.5" value={fam} onChange={(e) => setFam(e.target.value)} aria-label="Role family"><option value="">All role families</option>{meta.data?.role_families.map((r) => <option key={r}>{r}</option>)}</select>
          <label className="flex items-center gap-2 text-sm font-normal"><input type="checkbox" className="accent-comet-600" checked={postedOnly} onChange={(e) => setPostedOnly(e.target.checked)} />Partner employers only (apply in CometIQ)</label></div>}>
          {jobs.loading ? <Spinner /> : !jobs.data?.has_skills ? (
            <div className="p-5"><Empty icon={<FileUp className="h-8 w-8" />} title="Add your skills to see matches">Upload your resume or add completed courses in CometPath — CometMatch scores every job against your skills.</Empty></div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {jobs.data.items.map((j) => (
                <li key={j.id}>
                  <button className="flex w-full items-start gap-4 px-5 py-4 text-left hover:bg-slate-50" onClick={() => setSel(j.id)}>
                    <FitBadge score={j.score} label={j.label} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2"><span className="font-semibold text-slate-800">{j.title}</span>
                        {j.can_apply ? <Badge color="green">Partner employer</Badge> : <Badge>{j.source}</Badge>}{j.application && <Badge color={STATUS_COLOR[j.application]}>{j.application}</Badge>}{j.bonus > 0 && <Badge color="orange">+{j.bonus} verified bonus</Badge>}</div>
                      <div className="text-xs text-slate-500">{j.company} · {j.location} · {j.employment_type}</div>
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {j.matched.map((s) => <Badge key={s} color="green">✓ {s}</Badge>)}
                        {j.missing.map((s) => <Badge key={s} color="red">✗ {s}</Badge>)}
                      </div>
                    </div>
                  </button>
                </li>))}
            </ul>)}
        </Card>)}

      {tab === "badges" && <Badges />}
      {tab === "stacks" && <StackProgress />}
      {tab === "evidence" && <EvidencePortal onChange={() => { me.reload(); jobs.reload(); }} />}

      {tab === "learn" && (
        <Card title={<span className="flex items-center gap-2"><TrendingUp className="h-4 w-4 text-flame-500" />Skills that would raise your fit the most{learn.data?.career_goal ? ` for ${learn.data.career_goal} roles` : ""}</span>}>
          {learn.loading || !learn.data ? <Spinner /> : !learn.data.skills.length ? <p className="text-sm text-slate-500">You already cover the skills in your best-fit jobs. 🎉</p> : (
            <ol className="space-y-3">{learn.data.skills.map((g, i) => (
              <li key={g.skill_id} className="rounded-lg border border-slate-200 p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div><span className="mr-2 text-sm font-bold text-flame-600">#{i + 1}</span><span className="font-semibold text-slate-800">{g.skill}</span>
                    <span className="ml-2 text-xs text-slate-500">{g.category}{g.current_level > 0 ? ` · you have ${Math.round(g.current_level * 100)}%` : ""}</span></div>
                  <div className="text-sm"><b className="text-comet-700">+{g.points_per_job} pts</b> <span className="text-slate-500">avg. per job · needed in {g.jobs} of your top jobs</span></div>
                </div>
                <div className="mt-1 text-xs text-slate-500">e.g. {g.examples.join(" · ")}</div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {g.courses.length ? g.courses.map((c) => (
                    <div key={c.id} className="flex items-center gap-2 rounded-md border border-slate-200 px-2 py-1 text-xs">
                      <span><b className="text-comet-800">{c.code}</b> {c.title}</span>{c.in_program && <Badge color="green">in your program</Badge>}
                      {c.status ? <Badge color="blue">{c.status}</Badge> : <button className="inline-flex items-center gap-0.5 font-semibold text-flame-600 hover:underline" onClick={() => planCourse(c.id, c.code)}><Plus className="h-3 w-3" />Add to plan</button>}
                    </div>)) : <span className="text-xs text-slate-500">No catalog course teaches this yet — try a certification or project, then add it under Courses & certifications.</span>}
                </div>
              </li>))}</ol>)}
          <div className="mt-4 text-right text-sm"><Link to="/path" className="font-semibold text-comet-700 hover:underline">Open my CometPath plan →</Link></div>
        </Card>)}

      {tab === "profile" && (
        <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
          <Card title="Skills CometIQ knows you have">
            {!me.data?.skills.length ? <p className="text-sm text-slate-500">Upload a resume or record completed courses in CometPath.</p> : (
              <table className="table-base"><thead><tr><th>Skill</th><th>Level</th><th>Evidence</th></tr></thead>
                <tbody>{me.data.skills.map((s) => (
                  <tr key={s.id}><td className="font-medium">{s.name}<div className="text-xs text-slate-500">{s.category}</div></td>
                    <td className="w-28"><div className="h-2 rounded-r bg-slate-100"><div className="h-2 rounded-r bg-navy-500" style={{ width: `${s.level * 100}%` }} /></div><div className="text-[11px] text-slate-500">{Math.round(s.level * 100)}%</div></td>
                    <td className="text-xs text-slate-600">{s.sources.join(", ")}</td></tr>))}</tbody></table>)}
          </Card>
          <Card title="Visibility to employers">
            <div className="space-y-4 text-sm">
              <label className="block"><span className="label">Headline</span>
                <input className="input" value={headline ?? me.data?.headline ?? ""} onChange={(e) => setHeadline(e.target.value)} onBlur={() => headline !== null && saveProfile({ headline })} /></label>
              <label className="flex items-center gap-2"><input type="checkbox" className="accent-comet-600" checked={me.data?.open_to_match ?? true} onChange={(e) => saveProfile({ open_to_match: e.target.checked })} />Let partner employers find me</label>
              <div className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600">Employers see your name, program, headline and skill evidence — not your full resume text.</div>
              {me.data?.resume_filename && <div className="text-xs text-slate-500">Resume on file: <b>{me.data.resume_filename}</b></div>}
            </div>
          </Card>
          <Card title={<span className="flex items-center gap-2"><Lightbulb className="h-4 w-4 text-flame-500" />Resume improvement tips</span>} className="lg:col-span-2">
            {!tips ? <button className="btn-accent" onClick={getTips} disabled={tipsBusy}>{tipsBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Lightbulb className="h-4 w-4" />}Review my resume</button> : (
              <div className="space-y-3">
                <p className="text-sm text-slate-600">{tips.summary}</p>
                <ul className="space-y-2">{tips.tips.map((t) => (
                  <li key={t.title} className="flex gap-3 rounded-lg border border-slate-200 p-3 text-sm">
                    <Badge color={t.priority === "high" ? "red" : t.priority === "medium" ? "orange" : "slate"}>{t.priority}</Badge>
                    <div><div className="font-semibold text-slate-800">{t.title}</div><div className="text-slate-600">{t.detail}</div></div></li>))}</ul>
                <div className="flex items-center justify-between text-[11px] text-slate-500"><span>{tips.engine === "claude" ? "Reviewed by Claude" : "CometIQ built-in reviewer"}</span><button className="btn-ghost btn-sm" onClick={getTips}>Refresh</button></div>
              </div>)}
          </Card>
        </div>)}

      {tab === "apps" && (
        <Card padded={false}>{!apps.data?.length ? <div className="p-5"><Empty title="No applications yet">Apply to partner-employer roles from your matches.</Empty></div> : (
          <table className="table-base"><thead><tr><th>Role</th><th>Fit</th><th>Status</th><th>Updated</th></tr></thead>
            <tbody>{apps.data.map((a) => (
              <tr key={a.id} className="cursor-pointer hover:bg-slate-50" onClick={() => setSel(a.job.id)}><td><div className="font-semibold">{a.job.title}</div><div className="text-xs text-slate-500">{a.job.company} · {a.job.location}</div></td>
                <td>{Math.round(a.score)}%</td><td><Badge color={STATUS_COLOR[a.status]}>{a.status}{a.initiated_by === "employer" && a.status === "shortlisted" ? " (employer invited you)" : ""}</Badge></td>
                <td className="text-xs text-slate-500">{new Date(a.updated_at).toLocaleDateString()}</td></tr>))}</tbody></table>)}
        </Card>)}

      <Modal open={!!sel} onClose={() => setSel(null)} title={detail.data?.job.title ?? "Job"} wide>
        {detail.loading || !detail.data ? <Spinner /> : (
          <div className="space-y-5">
            <div className="flex items-start gap-4">
              <FitBadge score={detail.data.score} label={detail.data.label} />
              <div className="flex-1 text-sm"><div className="font-semibold text-slate-800">{detail.data.job.company}</div><div className="text-slate-500">{detail.data.job.location} · {detail.data.job.employment_type}</div></div>
              {detail.data.can_apply ? (detail.data.application && detail.data.application.status !== "shortlisted" ? <Badge color={STATUS_COLOR[detail.data.application.status]}>{detail.data.application.status}</Badge>
                : <button className="btn-accent" onClick={() => apply(detail.data!.job.id)}><Send className="h-4 w-4" />{detail.data.application ? "Accept invitation" : "Apply"}</button>)
                : detail.data.job.url && <a className="btn-ghost" href={detail.data.job.url} target="_blank" rel="noreferrer"><ExternalLink className="h-4 w-4" />Apply on site</a>}
            </div>
            <AiExplain key={detail.data.job.id} path={`/match/jobs/${detail.data.job.id}/explain`} />
            <Breakdown m={detail.data} showLearn />
            {detail.data.job.description && <details className="text-sm"><summary className="cursor-pointer font-semibold text-slate-700">Job description</summary><pre className="mt-2 whitespace-pre-wrap font-sans text-slate-600">{detail.data.job.description}</pre></details>}
          </div>)}
      </Modal>
    </div>
  );
}
