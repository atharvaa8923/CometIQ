import { Radio } from "lucide-react";
import { useApi } from "../lib/hooks";
import { Badge, Spinner } from "./ui";

interface GradeStats { distribution: { grade: string; count: number }[]; students: number; gpa: number | null; a_rate: number | null; w_rate: number | null }
interface Live {
  configured: boolean; available: boolean; reason?: string; source?: string; latest_term?: string; terms_offered?: string[];
  sections?: { section: string; professors: string[]; instruction_mode: string; meetings: { days: string; time: string; location: string; modality: string }[]; syllabus_uri: string | null }[];
  grades?: GradeStats | null; professors?: ({ name: string } & GradeStats)[];
}

/** Live UTD data from Nebula Labs: sections, professors and grade distributions. */
export default function LiveCourse({ courseId }: { courseId: string }) {
  const { data, loading } = useApi<Live>(`/courses/${courseId}/live`);
  if (loading) return <Spinner label="Loading live UTD data…" />;
  if (!data) return null;
  if (!data.available) return (
    <div className="rounded-lg border border-dashed border-slate-300 p-3 text-xs text-slate-500"><Radio className="mr-1 inline h-3.5 w-3.5" />
      Live sections & grades: {data.reason}{!data.configured && " Ask your administrator to add a Nebula Labs API key."}</div>);
  const g = data.grades;
  const max = Math.max(1, ...(g?.distribution.map((d) => d.count) ?? [1]));
  return (
    <div className="space-y-4 rounded-xl border border-comet-200 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-bold text-comet-900"><Radio className="h-4 w-4 text-flame-500" />Live at UTD</div>
        <div className="flex flex-wrap gap-1">{data.terms_offered?.map((t, i) => <Badge key={t} color={i === 0 ? "green" : "slate"}>{t}</Badge>)}</div>
      </div>
      {!!data.sections?.length && (
        <div><div className="label">{data.latest_term} sections</div>
          <table className="table-base text-xs"><thead><tr><th>Section</th><th>Professor</th><th>When & where</th><th>Mode</th></tr></thead>
            <tbody>{data.sections.map((s) => (
              <tr key={s.section}><td className="font-semibold">{s.section}</td><td>{s.professors.join(", ") || "TBA"}</td>
                <td>{s.meetings.length ? s.meetings.map((m, i) => <div key={i}>{m.days} {m.time} {m.location && <span className="text-slate-500">· {m.location}</span>}</div>) : <span className="text-slate-400">—</span>}</td>
                <td>{s.instruction_mode}{s.syllabus_uri && <> · <a className="text-comet-700 underline" href={s.syllabus_uri} target="_blank" rel="noreferrer">syllabus</a></>}</td></tr>))}</tbody></table>
        </div>)}
      {g && (
        <div className="grid gap-4 md:grid-cols-[1fr_220px]">
          <div><div className="label">Grade distribution · {g.students} students, all terms</div>
            <div className="flex h-28 items-end gap-1" role="img" aria-label={`Grade distribution: ${g.distribution.map((d) => `${d.grade} ${d.count}`).join(", ")}`}>
              {g.distribution.map((d) => (
                <div key={d.grade} className="flex flex-1 flex-col items-center justify-end" title={`${d.grade}: ${d.count} (${Math.round((100 * d.count) / g.students)}%)`}>
                  <div className={`w-full rounded-t ${d.grade === "W" ? "bg-slate-400" : "bg-comet-600"}`} style={{ height: `${(d.count / max) * 96}px`, minHeight: d.count ? 2 : 0 }} />
                  <div className="mt-1 text-[10px] text-slate-500">{d.grade}</div>
                </div>))}
            </div></div>
          <div className="grid grid-cols-3 gap-2 text-center md:grid-cols-1 md:text-left">
            <div><div className="text-xs text-slate-500">Avg. GPA</div><div className="text-xl font-bold text-comet-700">{g.gpa?.toFixed(2) ?? "—"}</div></div>
            <div><div className="text-xs text-slate-500">A range</div><div className="text-xl font-bold text-slate-700">{g.a_rate ?? "—"}%</div></div>
            <div><div className="text-xs text-slate-500">Withdrew</div><div className="text-xl font-bold text-slate-700">{g.w_rate ?? "—"}%</div></div>
          </div>
        </div>)}
      {!!data.professors?.length && (
        <div><div className="label">By professor (10+ students)</div>
          <table className="table-base text-xs"><thead><tr><th>Professor</th><th>Avg. GPA</th><th>A range</th><th>Students</th></tr></thead>
            <tbody>{data.professors.map((p) => <tr key={p.name}><td className="font-medium">{p.name}</td><td>{p.gpa?.toFixed(2)}</td><td>{p.a_rate}%</td><td>{p.students}</td></tr>)}</tbody></table></div>)}
      <div className="text-right text-[10px] text-slate-400">Source: {data.source} · refreshed every 6 hours</div>
    </div>
  );
}
