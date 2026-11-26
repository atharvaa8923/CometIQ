import { CheckCircle2, ExternalLink, Link2, Loader2, RefreshCw, Unlink } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Card, Empty, ErrorBox, Spinner } from "../../components/ui";
import { api, waitForTask } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { useToast } from "../../lib/toast";

export interface CanvasStatus { configured: boolean; connected: boolean; canvas_name: string | null; base_url: string | null }
interface CanvasCourse { id: string; name: string; course_code: string; state: string; term: string | null; semester: string | null;
  catalog_code: string | null; in_catalog: boolean; imported_syllabus_id: string | null; imported_semester: string | null }
interface ImportResult { syllabus_id: string; analysis_id: string; created: boolean; changed: boolean; assignments: number; graded_assignments: number }

/** Faculty: connect Canvas once, then import a course's syllabus page and graded assignments in one click. */
export default function CanvasImport({ status, reloadStatus, onImported }: { status: CanvasStatus; reloadStatus: () => void; onImported: () => void }) {
  const toast = useToast();
  const params = new URLSearchParams(location.search);
  const [err, setErr] = useState<string | null>(params.get("canvas_error"));
  const courses = useApi<CanvasCourse[]>(status.connected ? "/canvas/courses" : null);
  const [busy, setBusy] = useState<Record<string, string>>({});
  const [done, setDone] = useState<Record<string, ImportResult>>({});

  const connect = async () => {
    setErr(null);
    try { window.location.href = (await api.post<{ url: string }>("/canvas/connect")).url; } catch (e) { setErr((e as Error).message); }
  };
  const disconnect = async () => {
    if (!confirm("Disconnect Canvas? Imported syllabi and reports stay in CometIQ.")) return;
    await api.del("/canvas/connection"); toast("Canvas disconnected"); reloadStatus();
  };
  const importCourse = async (c: CanvasCourse) => {
    setBusy((b) => ({ ...b, [c.id]: "Starting…" })); setErr(null);
    try {
      const t = await api.post<{ task_id: string }>(`/canvas/courses/${c.id}/import`, {});
      const r = await waitForTask(t.task_id, (s) => s.progress && setBusy((b) => ({ ...b, [c.id]: s.progress! })), 10 * 60 * 1000) as unknown as ImportResult;
      setDone((d) => ({ ...d, [c.id]: r }));
      toast(r.created ? `Imported ${c.catalog_code ?? c.name}` : r.changed ? "New syllabus version imported" : "Already up to date");
      courses.reload(); onImported();
    } catch (e) { setErr((e as Error).message); }
    finally { setBusy((b) => { const n = { ...b }; delete n[c.id]; return n; }); }
  };

  if (!status.connected) return (
    <Card title="Import from Canvas">
      <ErrorBox error={err} />
      <p className="mb-4 max-w-2xl text-sm text-slate-600">Connect your Canvas account once. CometIQ then reads the syllabus page and the graded
        assignments (instructions and rubrics) of courses you teach, analyzes them, and keeps a version per semester. It only reads; nothing in Canvas changes.</p>
      <button className="btn-primary" onClick={connect}><Link2 className="h-4 w-4" />Connect Canvas</button>
    </Card>);

  return (
    <Card title="Your Canvas courses" actions={<span className="flex items-center gap-2 text-sm text-slate-600">
      <CheckCircle2 className="h-4 w-4 text-green-600" aria-hidden />Connected{status.canvas_name ? ` as ${status.canvas_name}` : ""}
      <button className="btn-ghost btn-sm" onClick={disconnect}><Unlink className="h-4 w-4" />Disconnect</button></span>}>
      <ErrorBox error={err} />
      {courses.loading ? <Spinner /> : courses.error ? <ErrorBox error={courses.error} /> : !courses.data?.length ? (
        <Empty title="No courses found">Canvas lists no courses where you are a teacher.</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Canvas courses you teach</caption>
            <thead><tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-500">
              <th scope="col" className="py-2 pr-3">Course</th><th scope="col" className="py-2 pr-3">Term</th>
              <th scope="col" className="py-2 pr-3">Catalog match</th><th scope="col" className="py-2 pr-3">In CometIQ</th><th scope="col" className="py-2"><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {courses.data.map((c) => {
                const r = done[c.id];
                return (
                  <tr key={c.id} className="border-b border-slate-100 align-top">
                    <td className="py-2 pr-3"><div className="font-semibold text-slate-800">{c.name}</div><div className="text-xs text-slate-500">{c.course_code}</div></td>
                    <td className="py-2 pr-3 text-slate-600">{c.semester ?? c.term ?? "—"}{c.state !== "available" && <div className="text-xs text-slate-500">{c.state}</div>}</td>
                    <td className="py-2 pr-3">{c.in_catalog ? <Badge color="green">{c.catalog_code}</Badge> : <span className="text-xs text-slate-500">{c.catalog_code ? `${c.catalog_code} (not in catalog)` : "No course code found"}</span>}</td>
                    <td className="py-2 pr-3">{c.imported_syllabus_id
                      ? <Link to={`/gap/course/${c.imported_syllabus_id}`} className="font-semibold text-comet-700 hover:underline">{c.imported_semester ?? "Imported"} history</Link>
                      : <span className="text-xs text-slate-500">Not imported</span>}
                      {r && <div className="mt-1 text-xs text-slate-600">{r.graded_assignments} graded of {r.assignments} assignments ·{" "}
                        <Link to={`/gap/analysis/${r.analysis_id}`} className="text-comet-700 underline">report</Link></div>}</td>
                    <td className="py-2 text-right">
                      <button className="btn-ghost btn-sm" disabled={!!busy[c.id]} onClick={() => importCourse(c)}
                        aria-label={`${c.imported_syllabus_id ? "Re-import" : "Import"} ${c.name}`}>
                        {busy[c.id] ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <RefreshCw className="h-4 w-4" aria-hidden />}
                        {busy[c.id] ?? (c.imported_syllabus_id ? "Re-import" : "Import")}</button>
                    </td>
                  </tr>);
              })}
            </tbody>
          </table>
        </div>)}
      {status.base_url && <p className="mt-3 text-xs text-slate-500">Re-importing creates a new syllabus version only when the course changed in Canvas.{" "}
        <a href={status.base_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-comet-700 underline">Open Canvas<ExternalLink className="h-3 w-3" aria-hidden /></a></p>}
    </Card>);
}

interface Assignment { id: string; name: string; points: number | null; due_at: string | null; graded: boolean; skills: string[];
  rubric: { criterion: string; detail: string; points: number | null }[] }

/** On a report for a course imported from Canvas: the graded work behind each skill. */
export function CanvasAssignments({ syllabusId }: { syllabusId: string }) {
  const { data } = useApi<{ canvas_course_id: string | null; assignments: Assignment[]; graded_practice: Record<string, string[]> }>(`/canvas/syllabi/${syllabusId}/assignments`);
  if (!data?.canvas_course_id || !data.assignments.length) return null;
  const practice = Object.entries(data.graded_practice);
  return (
    <Card title="Graded work from Canvas" className="mt-6">
      {practice.length > 0 && <div className="mb-4">
        <div className="label">Skills students practice in graded assignments</div>
        <ul className="flex flex-wrap gap-2">{practice.map(([skill, names]) => (
          <li key={skill}><Badge color="green" title={names.join(", ")}>{skill} · {names.length} assignment{names.length === 1 ? "" : "s"}</Badge></li>))}</ul>
      </div>}
      <ul className="divide-y divide-slate-100 text-sm">
        {data.assignments.map((a) => (
          <li key={a.id} className="py-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="font-semibold text-slate-800">{a.name}</span>
              <span className="text-xs text-slate-500">{a.graded ? `${a.points ?? 0} points` : "Not graded"}{a.due_at && ` · due ${new Date(a.due_at).toLocaleDateString()}`}</span>
            </div>
            {a.skills.length > 0 && <div className="mt-1 text-xs text-slate-600">Skills: {a.skills.join(", ")}</div>}
            {a.rubric.length > 0 && <div className="mt-1 text-xs text-slate-500">Rubric: {a.rubric.map((r) => r.criterion).join("; ")}</div>}
          </li>))}
      </ul>
    </Card>);
}
