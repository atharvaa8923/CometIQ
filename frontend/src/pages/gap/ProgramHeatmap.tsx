import { useEffect, useState } from "react";
import { Badge, Card, Empty, Spinner } from "../../components/ui";
import { useApi } from "../../lib/hooks";
import { HEAT } from "../../lib/viz";
import { TargetSelect } from "./GapHome";

interface Heat {
  program: string; target: string; job_count: number; score: number;
  skills: { name: string; demand: number; is_emerging: boolean; program_coverage: number }[];
  courses: { code: string; title: string; is_core: boolean; source: string; cells: number[] }[];
}

export default function ProgramHeatmap() {
  const programs = useApi<{ id: string; name: string; type: string }[]>("/programs");
  const [pid, setPid] = useState("");
  const [target, setTarget] = useState("Data Analyst");
  useEffect(() => {
    if (!pid && programs.data?.length) setPid(programs.data.find((p) => p.name.includes("Business Analytics and Artificial"))?.id ?? programs.data[0].id);
  }, [programs.data, pid]);
  const { data, loading } = useApi<Heat>(pid ? `/gap/programs/${pid}?target=${encodeURIComponent(target)}` : null);
  const label = (v: number) => (v >= 1 ? "taught" : v > 0 ? "touched on" : "not taught");

  return (
    <Card title="Which courses in a program teach the skills employers want?"
      actions={<div className="flex gap-2">
        <select className="input w-80" value={pid} onChange={(e) => setPid(e.target.value)} aria-label="Program">
          {programs.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
        <div className="w-60"><TargetSelect value={target} onChange={setTarget} /></div></div>}>
      {loading || !data ? <Spinner /> : !data.courses.length ? <Empty title="This program has no listed courses" /> : (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-4 text-sm">
            <div><span className="text-2xl font-bold text-comet-700">{Math.round(data.score)}%</span> <span className="text-slate-500">program-level coverage of the top {data.skills.length} {data.target} skills ({data.job_count} postings)</span></div>
            <div className="ml-auto flex items-center gap-3 text-xs text-slate-600" aria-label="Legend">
              {[0, 0.5, 1].map((v) => <span key={v} className="inline-flex items-center gap-1"><span className="h-3 w-3 rounded-sm ring-1 ring-black/10" style={{ background: HEAT[v] }} />{label(v)}</span>)}
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="border-separate" style={{ borderSpacing: 2 }}>
              <thead>
                <tr>
                  <th className="sticky left-0 z-10 bg-white" />
                  {data.skills.map((s) => (
                    <th key={s.name} className="h-40 w-7 align-bottom" title={`${s.name}: ${Math.round(s.demand * 100)}% demand`}>
                      <div className="flex w-7 justify-center"><span className="whitespace-nowrap text-[11px] font-medium text-slate-600 [writing-mode:vertical-rl] rotate-180">
                        {s.name}{s.program_coverage === 0 ? " ⚠" : ""}</span></div>
                    </th>))}
                </tr>
              </thead>
              <tbody>
                {data.courses.map((c) => (
                  <tr key={c.code}>
                    <td className="sticky left-0 z-10 bg-white pr-3 text-xs whitespace-nowrap" title={c.title}>
                      <span className="font-semibold text-comet-800">{c.code}</span> {c.is_core && <Badge color="green">core</Badge>}
                      {c.source === "syllabus" && <Badge color="blue">syllabus</Badge>}
                    </td>
                    {c.cells.map((v, i) => (
                      <td key={i} className="h-6 w-7 rounded-sm ring-1 ring-inset ring-black/5" style={{ background: HEAT[v] }}
                        title={`${c.code} ${c.title} — ${data.skills[i].name}: ${label(v)}`} />))}
                  </tr>))}
                <tr>
                  <td className="sticky left-0 bg-white pr-3 pt-2 text-xs font-bold text-slate-700">Program</td>
                  {data.skills.map((s) => <td key={s.name} className="h-6 w-7 rounded-sm pt-2" title={`${s.name}: ${label(s.program_coverage)} anywhere in program`}>
                    <div className="h-6 rounded-sm ring-1 ring-inset ring-black/10" style={{ background: HEAT[s.program_coverage] }} /></td>)}
                </tr>
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-slate-500">Skills are ordered by demand (left = most wanted). ⚠ marks skills no course in the program teaches. Cells come from the course catalog, or from an uploaded syllabus when one is linked.</p>
        </>
      )}
    </Card>
  );
}
