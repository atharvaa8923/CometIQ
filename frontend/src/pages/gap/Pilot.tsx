import { BadgeCheck, Download } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Card, Empty, Spinner, Stat } from "../../components/ui";
import { download } from "../../lib/api";
import { useApi } from "../../lib/hooks";

interface Row {
  syllabus_id: string; analysis_id: string; course: string | null; title: string; semester: string | null; approved_by: string | null;
  pilot_approved: boolean; target: string; sample: string | null; job_count: number; mention_score: number; reviewed_score: number | null;
  reviewed: number; confirmed: number; corrected: number; planned: number; done: number; gaps_total: number; gaps_reviewed: number; total: number;
}
interface Summary {
  syllabi: Row[]; approved_only: boolean;
  totals: { reviewed: number; confirmed: number; corrected: number; planned: number; done: number; gaps_total: number; gaps_reviewed: number };
  corrections: { course: string | null; skill: string; system: string; faculty: string; rationale: string | null }[];
}

const pct = (a: number, b: number) => (b ? `${Math.round((100 * a) / b)}%` : "—");

export default function Pilot() {
  const [approvedOnly, setApprovedOnly] = useState(true);
  const { data, loading } = useApi<Summary>(`/gap/pilot/summary?approved_only=${approvedOnly}`);
  if (loading || !data) return <Spinner />;
  const t = data.totals;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-3xl text-sm text-slate-600">Tracks what faculty did with each report: findings they <b>confirmed</b>, <b>corrected</b> (with a rationale),
          and <b>acted on</b>. Only syllabi approved for the pilot are counted unless you include all.</p>
        <div className="flex items-center gap-3">
          <label className="inline-flex items-center gap-2 text-sm"><input type="checkbox" checked={!approvedOnly} onChange={(e) => setApprovedOnly(!e.target.checked)} />Include unapproved syllabi</label>
          <button className="btn-ghost btn-sm" onClick={() => download(`/gap/pilot/findings.csv?approved_only=${approvedOnly}`, "cometiq-pilot-findings.csv")}><Download className="h-4 w-4" />All findings (CSV)</button>
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <Stat label="Priority gaps reviewed" value={`${t.gaps_reviewed} / ${t.gaps_total}`} hint={pct(t.gaps_reviewed, t.gaps_total)} />
        <Stat label="Confirmed" value={t.confirmed} hint={`${pct(t.confirmed, t.reviewed)} of reviewed`} />
        <Stat label="Corrected" value={t.corrected} hint={`${pct(t.corrected, t.reviewed)} of reviewed`} tone="flame" />
        <Stat label="Change planned" value={t.planned} tone="navy" />
        <Stat label="Change made" value={t.done} tone="navy" />
      </div>
      <Card title="Syllabi in the pilot" padded={false}>
        {!data.syllabi.length ? <div className="p-5"><Empty title="No approved syllabi yet">Open a gap report and use “Record approval” once the instructor of record has agreed to include it.</Empty></div> : (
          <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Pilot syllabi">
            <table className="table-base"><thead><tr><th>Course</th><th>Approved by</th><th>Job sample</th><th>Mention-based</th><th>Faculty-reviewed</th><th>Gaps reviewed</th><th>Confirmed</th><th>Corrected</th><th>Acted on</th></tr></thead>
              <tbody>{data.syllabi.map((r) => (
                <tr key={r.syllabus_id}>
                  <td><Link className="font-medium text-comet-700 hover:underline" to={`/gap/analysis/${r.analysis_id}`}>{r.course} {r.title}</Link><div className="text-xs text-slate-500">{r.semester}</div></td>
                  <td className="text-sm">{r.pilot_approved ? <span className="inline-flex items-center gap-1"><BadgeCheck className="h-4 w-4 text-green-700" aria-hidden />{r.approved_by}</span> : <span className="text-slate-500">Not approved</span>}</td>
                  <td className="text-sm">{r.sample ?? <span className="text-slate-500">{r.target} (live)</span>}<div className="text-xs text-slate-500">{r.job_count} postings</div></td>
                  <td>{Math.round(r.mention_score)}%</td>
                  <td>{r.reviewed ? `${Math.round(r.reviewed_score ?? 0)}%` : "—"}</td>
                  <td>{r.gaps_reviewed} / {r.gaps_total}</td><td>{r.confirmed}</td><td>{r.corrected}</td><td>{r.planned + r.done}</td>
                </tr>))}</tbody></table>
          </div>)}
      </Card>
      <Card title="Corrections and rationale">
        {!data.corrections.length ? <p className="text-sm text-slate-500">No corrections yet.</p> : (
          <ul className="space-y-2">{data.corrections.map((c, i) => (
            <li key={i} className="rounded border border-slate-200 p-3 text-sm">
              <div><b>{c.course}</b> · {c.skill}: system said <b>{c.system}</b>, faculty classified <b>{c.faculty.replace("_", " ")}</b></div>
              <div className="mt-1 text-slate-700">“{c.rationale}”</div>
            </li>))}</ul>)}
      </Card>
    </div>
  );
}
