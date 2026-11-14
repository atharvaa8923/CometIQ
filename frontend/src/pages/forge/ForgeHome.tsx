import { ArrowRight, BookOpen, Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge, Empty, PageHeader, Spinner } from "../../components/ui";
import { useApi } from "../../lib/hooks";
import type { Draft } from "./types";

export default function ForgeHome() {
  const { data, loading } = useApi<Draft[]>("/forge/drafts");
  return (
    <div>
      <PageHeader icon={<BookOpen className="h-5 w-5" />} accent="flame" title="CometForge" subtitle="AI Course & Syllabus Generation"
        actions={<Link to="/forge/new" className="btn-accent"><Plus className="h-4 w-4" />New syllabus draft</Link>} />
      {loading ? <Spinner /> : !data?.length ? (
        <Empty icon={<BookOpen className="h-8 w-8" />} title="No drafts yet">Pick a CometGap report and CometForge rewrites the syllabus to close its gaps: modules, outcomes, assessments and accreditation alignment.
          <div className="mt-4"><Link to="/forge/new" className="btn-accent">Create a draft</Link></div></Empty>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.map((d) => (
            <Link key={d.id} to={`/forge/${d.id}`} className="card group p-5 transition hover:shadow-md">
              <div className="flex items-start justify-between gap-2">
                <div className="font-bold text-comet-900">{d.title}</div>
                <Badge color={d.status === "approved" ? "green" : "orange"}>{d.status === "approved" ? "Approved" : "Draft"} v{d.version}</Badge>
              </div>
              <div className="mt-1 text-xs text-slate-500">{new Date(d.created_at).toLocaleDateString()} · {d.new_modules} new modules · {d.engine === "claude" ? "Claude AI" : "Built-in engine"}</div>
              {d.scores.before != null && (
                <div className="mt-4 flex items-center gap-2 text-sm">
                  <span className="font-semibold text-slate-500">{Math.round(d.scores.before)}%</span><ArrowRight className="h-4 w-4 text-slate-400" />
                  <span className="text-lg font-bold text-comet-700">{Math.round(d.scores.after ?? 0)}%</span>
                  <span className="text-xs text-slate-500">projected coverage vs. {d.scores.target}</span>
                </div>)}
            </Link>))}
        </div>
      )}
    </div>
  );
}
