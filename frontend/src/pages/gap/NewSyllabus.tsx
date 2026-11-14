import { FileText, GraduationCap, Loader2, ScanSearch, UploadCloud } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, ErrorBox, Field, PageHeader } from "../../components/ui";
import { api, waitForTask } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { TargetSelect } from "./GapHome";

export default function NewSyllabus() {
  const nav = useNavigate();
  const [mode, setMode] = useState<"file" | "text" | "utd">("file");
  const [utdCourse, setUtdCourse] = useState<{ id: string; code: string; title: string } | null>(null);
  const utd = useApi<{ available: boolean; reason?: string; syllabi: { term: string; section: string; url: string; professors: string[] }[] }>(utdCourse ? `/gap/utd-syllabi?course_id=${utdCourse.id}` : null);
  const [file, setFile] = useState<File | null>(null);
  const [f, setF] = useState({ title: "", code: "", semester: "Spring 2026", text: "", target: "auto" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("Uploading…");
  const courses = useApi<{ id: string; code: string; title: string }[]>(f.code.length >= 2 ? `/courses?limit=8&q=${encodeURIComponent(f.code)}` : null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null); setBusy(true);
    const fd = new FormData();
    Object.entries(f).forEach(([k, v]) => k !== "text" && fd.append(k, v));
    if (mode === "file" && file) fd.append("file", file); else fd.append("text", f.text);
    try {
      const r = await api.post<{ task_id: string; analysis_id?: string }>("/gap/syllabi", fd);
      const id = r.analysis_id ?? (await waitForTask(r.task_id, (t) => t.progress && setProgress(t.progress))).analysis_id;
      nav(`/gap/analysis/${id}`);
    }
    catch (x) { setErr((x as Error).message); setBusy(false); }
  };

  const importUtd = async (s: { term: string; url: string }) => {
    if (!utdCourse) return;
    setErr(null); setBusy(true); setProgress("Downloading the official syllabus…");
    try {
      const r = await api.post<{ task_id: string; analysis_id?: string }>("/gap/import-utd-syllabus", { course_id: utdCourse.id, url: s.url, term: s.term, target: f.target });
      const id = r.analysis_id ?? (await waitForTask(r.task_id, (t) => t.progress && setProgress(t.progress))).analysis_id;
      nav(`/gap/analysis/${id}`);
    } catch (x) { setErr((x as Error).message); setBusy(false); }
  };

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader icon={<ScanSearch className="h-5 w-5" />} title="Analyze a syllabus" subtitle="We extract the skills it teaches and compare them with live job postings" />
      <form onSubmit={submit} className="space-y-4">
        <ErrorBox error={err} />
        <Card>
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Course title"><input className="input" required value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="Business Analytics with R" /></Field>
            <div className="relative">
              <Field label="Course code" hint="Links the syllabus to the catalog"><input className="input" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} placeholder="BUAN 6356" /></Field>
              {f.code.length >= 2 && courses.data && courses.data.length > 0 && !courses.data.some((c) => c.code === f.code) && (
                <div className="absolute z-10 mt-1 w-full rounded-lg border border-slate-200 bg-white shadow-lg">
                  {courses.data.map((c) => <button type="button" key={c.id} className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
                    onClick={() => setF({ ...f, code: c.code, title: f.title || c.title })}><b>{c.code}</b> {c.title}</button>)}
                </div>)}
            </div>
            <Field label="Semester"><input className="input" value={f.semester} onChange={(e) => setF({ ...f, semester: e.target.value })} /></Field>
            <Field label="Compare against"><TargetSelect includeAuto value={f.target} onChange={(v) => setF({ ...f, target: v })} /></Field>
          </div>
        </Card>
        <Card>
          <div className="mb-4 flex gap-2">
            <button type="button" className={mode === "file" ? "btn-primary btn-sm" : "btn-ghost btn-sm"} onClick={() => setMode("file")}><UploadCloud className="h-4 w-4" />Upload file</button>
            <button type="button" className={mode === "text" ? "btn-primary btn-sm" : "btn-ghost btn-sm"} onClick={() => setMode("text")}><FileText className="h-4 w-4" />Paste text</button>
            <button type="button" className={mode === "utd" ? "btn-primary btn-sm" : "btn-ghost btn-sm"} onClick={() => setMode("utd")}><GraduationCap className="h-4 w-4" />Official UTD syllabus</button>
          </div>
          {mode === "utd" ? (
            <div className="space-y-3">
              <p className="text-sm text-slate-600">Pick a course; CometIQ finds its official syllabi on UTD's syllabus system (via Nebula) and analyzes the one you choose.</p>
              <div className="relative">
                <input className="input" placeholder="Search a course, e.g. BUAN 6341" value={utdCourse ? `${utdCourse.code} ${utdCourse.title}` : f.code}
                  onChange={(e) => { setUtdCourse(null); setF({ ...f, code: e.target.value }); }} aria-label="Course" />
                {!utdCourse && f.code.length >= 2 && courses.data && courses.data.length > 0 && (
                  <div className="absolute z-10 mt-1 w-full rounded-lg border border-slate-200 bg-white shadow-lg">
                    {courses.data.map((c) => <button type="button" key={c.id} className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50" onClick={() => { setUtdCourse(c); setF({ ...f, code: c.code, title: c.title }); }}><b>{c.code}</b> {c.title}</button>)}
                  </div>)}
              </div>
              {utdCourse && (utd.loading ? <div className="text-sm text-slate-500">Looking up syllabi…</div> : !utd.data?.syllabi.length ? (
                <div className="rounded-lg bg-slate-50 p-3 text-sm text-slate-600">{utd.data?.reason ?? "No official syllabi found for this course."}</div>
              ) : (
                <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">{utd.data.syllabi.map((s) => (
                  <li key={s.url} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                    <span><b>{s.term}</b> · section {s.section}{s.professors.length ? ` · ${s.professors.join(", ")}` : ""}</span>
                    <button type="button" className="btn-accent btn-sm" disabled={busy} onClick={() => importUtd(s)}>Analyze</button>
                  </li>))}</ul>))}
            </div>
          ) : mode === "file" ? (
            <label className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 px-6 py-10 text-center hover:border-comet-400 hover:bg-comet-50/40">
              <UploadCloud className="h-8 w-8 text-comet-600" />
              <div className="mt-2 font-semibold text-slate-700">{file ? file.name : "Choose a PDF, DOCX or TXT syllabus"}</div>
              <div className="text-xs text-slate-500">Up to 10 MB · text-based PDFs only (not scans)</div>
              <input type="file" accept=".pdf,.docx,.txt,.md" className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required={mode === "file"} />
              <a href="/samples/BUAN6356_syllabus.txt" download className="mt-3 text-xs font-semibold text-flame-600 hover:underline" onClick={(e) => e.stopPropagation()}>Download a sample syllabus</a>
            </label>
          ) : (
            <textarea className="input h-64 font-mono text-xs" required value={f.text} onChange={(e) => setF({ ...f, text: e.target.value })} placeholder="Paste the course description, learning objectives and weekly schedule…" />
          )}
        </Card>
        {mode !== "utd" && <button className="btn-accent w-full py-3" disabled={busy}>{busy ? <><Loader2 className="h-4 w-4 animate-spin" />{progress}</> : "Run gap analysis"}</button>}
        {mode === "utd" && busy && <div className="flex items-center justify-center gap-2 text-sm text-slate-600" role="status"><Loader2 className="h-4 w-4 animate-spin" />{progress}</div>}
      </form>
    </div>
  );
}
