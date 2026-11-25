import { AlertTriangle, ChevronDown, ChevronRight, GitPullRequest } from "lucide-react";
import { Fragment, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Card, Field, Spinner, Stat } from "../../components/ui";
import { useApi } from "../../lib/hooks";
import { PRIORITY_COLOR } from "../../lib/viz";
import { TargetSelect } from "../gap/GapHome";

interface Prog {
  id: string; name: string; type: string; catalog_year: string | null; catalog_confirmed: boolean; courses: number; core_courses: number;
  analyzed_courses: number; core_analyzed: number; badge_holders: number; active: boolean;
  coverage?: number; coverage_change?: number; trend?: { at: string; score: number; courses: number }[];
  undecided_gaps?: { course: string; analysis_id: string; skill: string; priority: string; share: number }[]; undecided_count?: number;
  proposals_waiting?: { id: string; number: number; title: string; status: string; tally: { approvals: number; required: number } }[];
  never_mastered?: string[]; never_practiced?: string[]; skills_mapped?: number;
  courses_detail?: { code: string; syllabus_id: string; analysis_id: string; score: number; is_core: boolean }[]; attention?: string[];
}
interface Data { target: string; job_count: number; programs: Prog[]; totals: { programs: number; active_programs: number; undecided_gaps: number; proposals_waiting: number; badge_holders: number; avg_coverage: number | null } }

function Sparkline({ points }: { points: { score: number; at: string }[] }) {
  if (points.length < 2) return <span className="text-xs text-slate-500">one data point</span>;
  const W = 96, H = 28, xs = (i: number) => 2 + (i * (W - 4)) / (points.length - 1), ys = (v: number) => H - 3 - (v / 100) * (H - 6);
  const last = points[points.length - 1];
  return (
    <svg width={W} height={H} role="img" aria-label={`Coverage from ${points[0].score}% to ${last.score}% over ${points.length} analyses`}>
      <polyline points={points.map((p, i) => `${xs(i)},${ys(p.score)}`).join(" ")} fill="none" stroke="#2a78d6" strokeWidth={2} strokeLinejoin="round" />
      <circle cx={xs(points.length - 1)} cy={ys(last.score)} r={3} fill="#2a78d6" />
    </svg>
  );
}

export default function Scorecard() {
  const [target, setTarget] = useState("All roles");
  const [showAll, setShowAll] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const { data, loading } = useApi<Data>(`/curriculum/scorecard?target=${encodeURIComponent(target)}`);
  if (loading || !data) return <Spinner />;
  const t = data.totals;
  const rows = data.programs.filter((p) => showAll || p.active);
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-4">
        <div className="w-72"><Field label="Compare against demand for"><TargetSelect value={target} onChange={setTarget} /></Field></div>
        <label className="mb-2 inline-flex items-center gap-2 text-sm"><input type="checkbox" className="accent-comet-600" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
          Include programs with no analyzed syllabus ({t.programs - t.active_programs})</label>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <Stat label="Programs with analyzed courses" value={`${t.active_programs} / ${t.programs}`} />
        <Stat label="Average coverage" value={t.avg_coverage !== null ? `${Math.round(t.avg_coverage)}%` : "—"} hint="mention-based, latest report per course" />
        <Stat label="Priority gaps without a decision" value={t.undecided_gaps} tone="flame" />
        <Stat label="Proposals waiting" value={t.proposals_waiting} tone="navy" />
        <Stat label="Students with verified badges" value={t.badge_holders} />
      </div>
      <Card padded={false}>
        <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Program scorecard">
          <table className="table-base">
            <thead><tr><th className="w-8"><span className="sr-only">Expand</span></th><th>Program</th><th>Courses analyzed</th><th>Coverage</th><th>Trend</th>
              <th>Undecided gaps</th><th>Proposals waiting</th><th>Never mastered</th><th>Badge holders</th><th>Needs attention</th></tr></thead>
            <tbody>{rows.map((p) => (
              <Fragment key={p.id}>
                <tr className={p.active ? "" : "text-slate-500"}>
                  <td>{p.active && <button aria-expanded={open === p.id} aria-label={`Details for ${p.name}`} onClick={() => setOpen(open === p.id ? null : p.id)} className="rounded p-1 hover:bg-slate-100">
                    {open === p.id ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</button>}</td>
                  <td className="font-medium text-slate-800">{p.name}<div className="text-xs font-normal text-slate-500">{p.type}{p.catalog_year ? ` · catalog ${p.catalog_year}` : ""}{p.catalog_confirmed ? " (confirmed)" : ""}</div></td>
                  <td className="text-sm tabular-nums">{p.analyzed_courses} / {p.courses}<div className="text-xs text-slate-500">core {p.core_analyzed}/{p.core_courses}</div></td>
                  <td className="tabular-nums">{p.active ? `${Math.round(p.coverage!)}%` : "—"}</td>
                  <td>{p.active ? <div className="flex items-center gap-2"><Sparkline points={p.trend!} /><span className="text-xs tabular-nums text-slate-700">{p.coverage_change! > 0 ? "+" : ""}{p.coverage_change}</span></div> : "—"}</td>
                  <td className="tabular-nums">{p.active ? p.undecided_count : "—"}</td>
                  <td className="tabular-nums">{p.active ? p.proposals_waiting!.length : "—"}</td>
                  <td className="tabular-nums">{p.active ? `${p.never_mastered!.length} / ${p.skills_mapped}` : "—"}</td>
                  <td className="tabular-nums">{p.badge_holders}</td>
                  <td className="text-xs">{p.active ? (p.attention!.length ? <ul className="space-y-0.5">{p.attention!.map((a) => <li key={a} className="flex items-start gap-1"><AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-600" aria-hidden />{a}</li>)}</ul> : "On track") : "No analyzed syllabus yet"}</td>
                </tr>
                {open === p.id && p.active && (
                  <tr><td colSpan={10} className="bg-slate-50">
                    <div className="grid gap-4 p-3 lg:grid-cols-3">
                      <div><div className="label">Priority gaps without a decision</div>
                        {p.undecided_gaps!.length ? <ul className="space-y-1 text-sm">{p.undecided_gaps!.slice(0, 10).map((g) => (
                          <li key={g.course + g.skill}><Link className="text-comet-700 underline" to={`/gap/analysis/${g.analysis_id}`}>{g.course}</Link>: {g.skill} <Badge color={PRIORITY_COLOR[g.priority]}>{g.priority}</Badge> <span className="text-xs text-slate-500">{g.share}% of postings</span></li>))}</ul>
                          : <p className="text-sm text-slate-500">Every priority gap has a decision.</p>}</div>
                      <div><div className="label">Proposals waiting</div>
                        {p.proposals_waiting!.length ? <ul className="space-y-1 text-sm">{p.proposals_waiting!.map((x) => (
                          <li key={x.id} className="flex items-center gap-1"><GitPullRequest className="h-3.5 w-3.5 text-slate-500" aria-hidden /><Link className="text-comet-700 underline" to={`/curriculum/proposals/${x.id}`}>#{x.number} {x.title}</Link>
                            <span className="text-xs text-slate-500">{x.status.replace("_", " ")} · {x.tally.approvals}/{x.tally.required}</span></li>))}</ul>
                          : <p className="text-sm text-slate-500">None.</p>}
                        <div className="label mt-3">Analyzed courses</div>
                        <ul className="space-y-0.5 text-sm">{p.courses_detail!.map((c) => <li key={c.code}><Link className="text-comet-700 underline" to={`/gap/course/${c.syllabus_id}`}>{c.code}</Link> {Math.round(c.score)}%{c.is_core ? "" : " · elective"}</li>)}</ul></div>
                      <div><div className="label">In-demand skills never practiced</div><p className="text-sm text-slate-700">{p.never_practiced!.join(", ") || "None"}</p>
                        <div className="label mt-3">Practiced but never taken to mastery</div><p className="text-sm text-slate-700">{p.never_mastered!.filter((s) => !p.never_practiced!.includes(s)).join(", ") || "None"}</p>
                        <Link className="mt-2 inline-block text-sm font-semibold text-comet-700 hover:underline" to="/curriculum?tab=map">Open the curriculum map →</Link></div>
                    </div>
                  </td></tr>)}
              </Fragment>))}</tbody>
          </table>
        </div>
      </Card>
      <p className="text-xs text-slate-500">Coverage is the mention-based score of each course's latest report, averaged across the program's analyzed courses. Trend points are added each time a course is analyzed.</p>
    </div>
  );
}
