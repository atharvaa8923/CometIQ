import { BarChart3, GraduationCap, Handshake, Target } from "lucide-react";
import type { ReactNode } from "react";
import { useApi } from "../lib/hooks";

interface ImpactData {
  curricula: { syllabi_analyzed: number; avg_coverage: number | null; drafts: number; approved: number; avg_projected_lift: number | null; top_gaps: { skill: string; courses: number }[] };
  students: { total: number; with_goal: number; with_plan: number; goals: { goal: string; students: number }[] };
  employers: { total: number; open_roles: number };
  outcomes: { applications: number; shortlisted: number; interviews: number; offers: number; avg_fit: number | null };
}

function Pillar({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-bold text-comet-900"><span className="text-comet-600">{icon}</span>{title}</div>
      <div className="space-y-2 text-sm">{children}</div>
    </div>
  );
}
const Metric = ({ label, value }: { label: string; value: ReactNode }) => (
  <div className="flex items-baseline justify-between gap-2"><span className="text-slate-500">{label}</span><span className="font-bold text-slate-800">{value}</span></div>
);
const pct = (v: number | null) => (v == null ? "—" : `${Math.round(v)}%`);

/** The four outcomes of the CometIQ feedback loop, live from the knowledge graph. */
export default function Impact() {
  const { data } = useApi<ImpactData>("/dashboard/impact");
  if (!data) return <div className="text-sm text-slate-500">Loading impact…</div>;
  const c = data.curricula, s = data.students, o = data.outcomes;
  const maxGap = Math.max(1, ...c.top_gaps.map((g) => g.courses));
  return (
    <div className="space-y-5">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Pillar icon={<Target className="h-4 w-4" />} title="More Relevant Curricula">
          <Metric label="Syllabi analyzed" value={c.syllabi_analyzed} />
          <Metric label="Avg. industry coverage" value={pct(c.avg_coverage)} />
          <Metric label="Forge drafts (approved)" value={`${c.drafts} (${c.approved})`} />
          <Metric label="Avg. projected lift" value={c.avg_projected_lift == null ? "—" : `+${Math.round(c.avg_projected_lift)} pts`} />
        </Pillar>
        <Pillar icon={<GraduationCap className="h-4 w-4" />} title="Personalized Student Journeys">
          <Metric label="Students" value={s.total} />
          <Metric label="With a career goal" value={s.with_goal} />
          <Metric label="With a saved plan" value={s.with_plan} />
          <Metric label="Top goal" value={s.goals[0]?.goal ?? "—"} />
        </Pillar>
        <Pillar icon={<Handshake className="h-4 w-4" />} title="Stronger Employer Partnerships">
          <Metric label="Partner employers" value={data.employers.total} />
          <Metric label="Open partner roles" value={data.employers.open_roles} />
          <Metric label="Avg. candidate fit" value={pct(o.avg_fit)} />
        </Pillar>
        <Pillar icon={<BarChart3 className="h-4 w-4" />} title="Better Career Outcomes">
          <Metric label="Applications" value={o.applications} />
          <Metric label="Shortlisted" value={o.shortlisted} />
          <Metric label="Interviews" value={o.interviews} />
          <Metric label="Offers & hires" value={o.offers} />
        </Pillar>
      </div>
      {c.top_gaps.length > 0 && (
        <div>
          <div className="mb-2 text-sm font-semibold text-slate-700">Most common critical/high skill gaps across analyzed courses</div>
          <div className="space-y-1.5">{c.top_gaps.map((g) => (
            <div key={g.skill} className="grid grid-cols-[200px_1fr_80px] items-center gap-3 text-sm" title={`${g.skill}: missing in ${g.courses} analyzed course(s)`}>
              <span className="truncate text-slate-700">{g.skill}</span>
              <div className="h-2.5 rounded-r bg-slate-100"><div className="h-2.5 rounded-r bg-flame-500" style={{ width: `${(g.courses / maxGap) * 100}%` }} /></div>
              <span className="text-right text-xs text-slate-500">{g.courses} course{g.courses > 1 ? "s" : ""}</span>
            </div>))}</div>
        </div>)}
    </div>
  );
}
