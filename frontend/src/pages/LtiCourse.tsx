import { Award, BarChart3, ExternalLink, Link2, Loader2, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { ConsentGate } from "../components/AccountMenu";
import { Logo } from "../components/Logo";
import { Badge, ErrorBox, ScoreBar, Spinner } from "../components/ui";
import { api, waitForTask } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useApi } from "../lib/hooks";

interface Build { skill: string; category: string | null; status: "covered" | "partial"; demand_pct: number; job_count: number | null;
  graded_share: number | null; graded_in: string[]; faculty_level: string | null }
interface CoursePage {
  canvas_course_id: string; role: string; staff: boolean; set_up: boolean; canvas_connected?: boolean; can_import?: boolean;
  syllabus_id?: string; analysis_id?: string; course?: { code: string | null; title: string; semester: string | null };
  target?: string; job_count?: number; builds?: Build[]; score?: number; score_basis?: string; reviewed?: number; skills_total?: number;
  open_decisions?: number; gaps?: { skill: string; status: string; priority: string; demand_pct: number }[];
  my_badges?: { skill: string; level: string }[];
}

/** Shown inside Canvas (course menu → CometIQ skills), after an LTI launch. Compact: no app navigation. */
export default function LtiCourse() {
  const { cid } = useParams();
  const { user } = useAuth();
  const title = new URLSearchParams(location.search).get("title");
  const { data, loading, error, reload } = useApi<CoursePage>(`/lti/course/${cid}`);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const open = (path: string) => window.open(path, "_blank", "noopener");

  const connect = async () => { try { window.open((await api.post<{ url: string }>("/canvas/connect")).url, "_blank", "noopener"); } catch (e) { setErr((e as Error).message); } };
  const analyze = async () => {
    setErr(null); setBusy("Starting…");
    try {
      const t = await api.post<{ task_id: string }>(`/canvas/courses/${cid}/import`, {});
      await waitForTask(t.task_id, (s) => s.progress && setBusy(s.progress), 10 * 60 * 1000);
      reload();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  };

  return (
    <main className="min-h-screen bg-white p-5">
      <ConsentGate />
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
        <div className="flex items-center gap-3"><Logo />
          <div><h1 className="text-lg font-bold text-comet-900">{data?.course ? `${data.course.code ?? ""} ${data.course.title}` : title || "This course"}</h1>
            <p className="text-xs text-slate-500">{user?.full_name} · {user?.role}{data?.course?.semester ? ` · ${data.course.semester}` : ""}</p></div></div>
        <button className="btn-ghost btn-sm" onClick={() => open(data?.analysis_id && data.staff ? `/gap/analysis/${data.analysis_id}` : "/app")}>
          <ExternalLink className="h-4 w-4" aria-hidden />Open CometIQ</button>
      </header>
      <ErrorBox error={error || err} />
      {loading && !data ? <Spinner /> : data && !data.set_up ? (
        <section className="max-w-2xl space-y-3 text-sm text-slate-700">
          {data.staff ? <>
            <p>This course has not been analyzed in CometIQ yet. CometIQ reads the syllabus page and graded assignments (with rubrics) from Canvas, compares the skills with current job postings, and shows students what the course builds.</p>
            {data.can_import && (data.canvas_connected
              ? <button className="btn-primary" onClick={analyze} disabled={!!busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <BarChart3 className="h-4 w-4" aria-hidden />}{busy ?? "Analyze this course"}</button>
              : <><button className="btn-primary" onClick={connect}><Link2 className="h-4 w-4" aria-hidden />Connect Canvas (opens a new tab)</button>
                  <p className="text-xs text-slate-500">Allow CometIQ to read your courses, then come back and reload this page.</p>
                  <button className="btn-ghost btn-sm" onClick={reload}><RefreshCw className="h-4 w-4" aria-hidden />Reload</button></>)}
          </> : <p>Your instructor has not set this course up in CometIQ yet. When they do, you will see here which skills it builds and how employers value them.</p>}
        </section>
      ) : data && (
        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <section aria-labelledby="builds-h">
            <h2 id="builds-h" className="mb-1 font-bold text-comet-900">Skills this course builds</h2>
            <p className="mb-3 text-xs text-slate-500">Compared with {data.job_count} current {data.target} postings{data.score_basis === "graded work" ? "; based on graded work" : ""}.</p>
            {!data.builds?.length ? <p className="text-sm text-slate-600">No in-demand skills were found in this course yet.</p> : (
              <ul className="divide-y divide-slate-100">
                {data.builds.map((b) => (
                  <li key={b.skill} className="py-2.5 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-slate-800">{b.skill}</span>
                      {b.faculty_level && <Badge color="green">Faculty-verified · {b.faculty_level}</Badge>}
                      {b.status === "partial" && <Badge color="orange">Introduced</Badge>}
                      <span className="ml-auto text-xs text-slate-600">asked for in {b.demand_pct}% of postings</span>
                    </div>
                    {b.graded_in.length > 0 && <p className="mt-0.5 text-xs text-slate-500">Practiced in: {b.graded_in.join(", ")}</p>}
                  </li>))}
              </ul>)}
          </section>
          <aside className="space-y-4">
            {data.staff ? <>
              <div className="rounded-xl border border-slate-200 p-4">
                <div className="mb-1 flex justify-between text-sm"><span className="font-semibold text-slate-700">Coverage ({data.score_basis === "graded work" ? "grade-weighted" : "mention-based"})</span><b>{Math.round(data.score ?? 0)}%</b></div>
                <ScoreBar value={data.score ?? 0} />
                <p className="mt-2 text-xs text-slate-600">{data.reviewed} of {data.skills_total} skills reviewed by faculty · {data.open_decisions} open decisions</p>
              </div>
              {!!data.gaps?.length && <div className="rounded-xl border border-slate-200 p-4">
                <h2 className="mb-2 text-sm font-bold text-comet-900">Top gaps</h2>
                <ul className="space-y-1 text-sm">{data.gaps.map((g) => (
                  <li key={g.skill} className="flex justify-between gap-2"><span>{g.skill} <span className="text-xs text-slate-500">({g.status})</span></span><span className="text-xs text-slate-600">{g.demand_pct}%</span></li>))}</ul>
                <button className="btn-ghost btn-sm mt-3" onClick={() => open(`/gap/analysis/${data.analysis_id}`)}><ExternalLink className="h-4 w-4" aria-hidden />Review in CometIQ</button>
              </div>}
              {data.can_import && data.canvas_connected && <button className="btn-ghost btn-sm" onClick={analyze} disabled={!!busy}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <RefreshCw className="h-4 w-4" aria-hidden />}{busy ?? "Re-import from Canvas"}</button>}
            </> : <div className="rounded-xl border border-slate-200 p-4">
              <h2 className="mb-2 flex items-center gap-2 text-sm font-bold text-comet-900"><Award className="h-4 w-4" aria-hidden />Your badges from this course</h2>
              {data.my_badges?.length ? <ul className="flex flex-wrap gap-2">{data.my_badges.map((b) => <li key={b.skill}><Badge color="green">{b.skill} · {b.level}</Badge></li>)}</ul>
                : <p className="text-xs text-slate-600">Once you complete the course and an advisor verifies it, faculty-verified skills become badges you can share with employers.</p>}
              <button className="btn-ghost btn-sm mt-3" onClick={() => open("/match")}><ExternalLink className="h-4 w-4" aria-hidden />See matching jobs</button>
            </div>}
          </aside>
        </div>)}
    </main>);
}
