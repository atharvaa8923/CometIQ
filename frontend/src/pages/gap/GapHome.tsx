import { FileUp, ScanSearch, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Empty, PageHeader, ScoreBar, Spinner, Tabs } from "../../components/ui";
import { api } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { useToast } from "../../lib/toast";
import CanvasImport, { type CanvasStatus } from "./CanvasImport";
import Jobs from "./Jobs";
import Market from "./Market";
import Pilot from "./Pilot";
import ProgramHeatmap from "./ProgramHeatmap";
import Samples from "./Samples";

interface Syl { id: string; title: string; code: string | null; semester: string | null; skill_count: number; created_at: string; pilot_approved?: boolean;
  latest: { id: string; score: number; target: string } | null }

export default function GapHome() {
  type Tab = "syllabi" | "canvas" | "market" | "program" | "jobs" | "samples" | "pilot";
  const [tab, setTab] = useState<Tab>(() => {
    const q = new URLSearchParams(location.search);
    return q.has("canvas") || q.has("canvas_error") ? "canvas" : (q.get("tab") as Tab) ?? "syllabi";
  });
  const { data, loading, reload } = useApi<Syl[]>("/gap/syllabi");
  const canvas = useApi<CanvasStatus>("/canvas/status");
  const toast = useToast();
  const del = async (s: Syl) => {
    if (!confirm(`Delete "${s.title}" and its analyses?`)) return;
    await api.del(`/gap/syllabi/${s.id}`); toast("Syllabus deleted"); reload();
  };
  return (
    <div>
      <PageHeader icon={<ScanSearch className="h-5 w-5" />} title="CometGap" subtitle="Curriculum–Industry Gap Analysis"
        actions={<Link to="/gap/new" className="btn-primary"><FileUp className="h-4 w-4" />Analyze a syllabus</Link>} />
      <Tabs value={tab} onChange={setTab} tabs={[
        { id: "syllabi", label: "My syllabi" }, ...(canvas.data?.configured ? [{ id: "canvas" as const, label: "Canvas" }] : []),
        { id: "market", label: "Market demand" },
        { id: "program", label: "Program heatmap" }, { id: "jobs", label: "Job postings" },
        { id: "samples", label: "Job samples" }, { id: "pilot", label: "Pilot review" }]} />
      {tab === "syllabi" && (loading ? <Spinner /> : !data?.length ? (
        <Empty icon={<ScanSearch className="h-8 w-8" />} title="No syllabi yet">Upload a syllabus (PDF, DOCX or text) to compare it with current job postings.
          <div className="mt-4"><Link to="/gap/new" className="btn-primary">Analyze a syllabus</Link></div></Empty>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.map((s) => (
            <div key={s.id} className="card flex flex-col p-5">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-xs font-semibold text-flame-600">{s.code ?? "No course code"} {s.semester && `· ${s.semester}`}</div>
                  <div className="font-bold text-comet-900">{s.title}</div>
                  {s.pilot_approved && <span className="chip mt-1 bg-green-50 text-green-800">Approved for pilot</span>}
                </div>
                <button className="rounded p-1 text-slate-500 hover:bg-red-50 hover:text-red-600" onClick={() => del(s)} aria-label={`Delete ${s.title}`}><Trash2 className="h-4 w-4" /></button>
              </div>
              {s.latest ? (
                <div className="mt-4">
                  <div className="mb-1 flex justify-between text-xs text-slate-500"><span>Coverage vs. {s.latest.target}</span><span className="font-bold text-slate-700">{Math.round(s.latest.score)}%</span></div>
                  <ScoreBar value={s.latest.score} />
                </div>
              ) : <div className="mt-4 text-xs text-slate-500">Not analyzed</div>}
              <div className="mt-4 flex items-center justify-between">
                <Badge>{s.skill_count} skills detected</Badge>
                <span className="flex gap-3">
                  <Link to={`/gap/course/${s.id}`} className="text-sm font-semibold text-slate-600 hover:underline" aria-label={`History of ${s.title}`}>History</Link>
                  {s.latest && <Link to={`/gap/analysis/${s.latest.id}`} className="text-sm font-semibold text-comet-700 hover:underline">View report →</Link>}
                </span>
              </div>
            </div>
          ))}
        </div>
      ))}
      {tab === "canvas" && canvas.data?.configured && <CanvasImport status={canvas.data} reloadStatus={canvas.reload} onImported={reload} />}
      {tab === "market" && <Market />}
      {tab === "program" && <ProgramHeatmap />}
      {tab === "jobs" && <Jobs />}
      {tab === "samples" && <Samples />}
      {tab === "pilot" && <Pilot />}
    </div>
  );
}

export function TargetSelect({ value, onChange, includeAuto }: { value: string; onChange: (v: string) => void; includeAuto?: boolean }) {
  const { data } = useApi<{ name: string; job_count: number }[]>("/gap/targets");
  return (
    <select className="input" value={value} onChange={(e) => onChange(e.target.value)} aria-label="Target roles">
      {includeAuto && <option value="auto">Auto-detect best-fit roles</option>}
      {data?.map((t) => <option key={t.name} value={t.name} disabled={!t.job_count}>{t.name} ({t.job_count} postings)</option>)}
    </select>
  );
}

