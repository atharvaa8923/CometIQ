import { useState } from "react";
import { Badge, Card, Spinner } from "../../components/ui";
import { useApi } from "../../lib/hooks";
import { TargetSelect } from "./GapHome";

interface D { name: string; category: string; is_emerging: boolean; demand: number; job_count: number; required_share: number }

export default function Market() {
  const [target, setTarget] = useState("All roles");
  const { data, loading } = useApi<{ job_count: number; skills: D[] }>(`/gap/market?target=${encodeURIComponent(target)}`);
  const max = Math.max(...(data?.skills.map((s) => s.job_count) ?? [1]), 1);
  return (
    <Card title={`Top skills in demand${data ? ` — ${data.job_count} open postings` : ""}`} actions={<div className="w-72"><TargetSelect value={target} onChange={setTarget} /></div>}>
      {loading || !data ? <Spinner /> : (
        <div className="space-y-1.5">
          {data.skills.slice(0, 30).map((s) => (
            <div key={s.name} className="grid grid-cols-[220px_1fr_70px] items-center gap-3 text-sm"
              title={`${s.name}: in ${s.job_count} of ${data.job_count} postings (${Math.round(s.job_count / data.job_count * 100)}%), required in ${Math.round(s.required_share * 100)}% of those`}>
              <div className="truncate font-medium text-slate-700">{s.name} {s.is_emerging && <Badge color="orange">Emerging</Badge>}</div>
              <div className="h-3 rounded-r bg-slate-100"><div className="h-3 rounded-r bg-comet-600" style={{ width: `${(s.job_count / max) * 100}%` }} /></div>
              <div className="text-right text-xs text-slate-600">{Math.round((s.job_count / data.job_count) * 100)}% <span className="text-slate-500">({s.job_count})</span></div>
            </div>
          ))}
          <p className="pt-2 text-xs text-slate-500">Share of open postings that mention each skill. Hover a row for required vs. preferred detail.</p>
        </div>
      )}
    </Card>
  );
}
