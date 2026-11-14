import { Award, BookOpen, Briefcase, CheckCircle2, Clock, ExternalLink, FileText, FolderGit2, Plus, Trash2, XCircle } from "lucide-react";
import { useState } from "react";
import { Card, Empty, ErrorBox, Field, Modal, Spinner } from "../../components/ui";
import { api } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { useToast } from "../../lib/toast";

export interface EvidenceRow {
  id: string; kind: "course" | "certification" | "project" | "experience"; title: string; issuer: string | null; description: string;
  course: { id: string; code: string; title: string } | null; skills: { id: number; name: string }[];
  credential_id: string | null; credential_url: string | null; issued_on: string | null;
  status: "pending" | "verified" | "rejected"; bonus_points: number; review_note: string | null; created_at: string; suggested_bonus: number;
  file: { filename: string; content_type: string; size: number } | null;
  student?: { id: string; name: string; email: string };
}

export const KIND = {
  course: { label: "Course", Icon: BookOpen, hint: "A class you took (at UTD or elsewhere, e.g. Coursera)" },
  certification: { label: "Certification", Icon: Award, hint: "e.g. AWS Cloud Practitioner — verified certifications earn bonus points" },
  project: { label: "Project", Icon: FolderGit2, hint: "A project you built (link to GitHub or a demo)" },
  experience: { label: "Work experience", Icon: Briefcase, hint: "An internship or job" },
} as const;

export function StatusChip({ e }: { e: Pick<EvidenceRow, "status" | "bonus_points"> }) {
  if (e.status === "verified") return <span className="chip bg-green-50 text-green-800"><CheckCircle2 className="h-3.5 w-3.5 text-green-600" aria-hidden />Verified{e.bonus_points ? ` · +${e.bonus_points} pts` : ""}</span>;
  if (e.status === "rejected") return <span className="chip bg-red-50 text-red-800"><XCircle className="h-3.5 w-3.5 text-red-600" aria-hidden />Not verified</span>;
  return <span className="chip bg-amber-50 text-amber-800"><Clock className="h-3.5 w-3.5 text-amber-600" aria-hidden />Pending review</span>;
}

export async function openFile(id: string) {
  const blob = await api.get<Blob>(`/evidence/${id}/file`);
  window.open(URL.createObjectURL(blob), "_blank", "noopener");
}

export default function EvidencePortal({ onChange }: { onChange?: () => void }) {
  const toast = useToast();
  const { data, loading, reload } = useApi<EvidenceRow[]>("/evidence/mine");
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ kind: "certification", title: "", issuer: "", description: "", course_id: "", credential_id: "", credential_url: "", issued_on: "" });
  const [file, setFile] = useState<File | null>(null);
  const [courseQ, setCourseQ] = useState("");
  const courses = useApi<{ id: string; code: string; title: string }[]>(courseQ.length >= 2 ? `/courses?limit=6&q=${encodeURIComponent(courseQ)}` : null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null); setBusy(true);
    const fd = new FormData();
    Object.entries(f).forEach(([k, v]) => fd.append(k, v));
    if (file) fd.append("file", file);
    try {
      const r = await api.post<EvidenceRow>("/evidence", fd);
      toast(`Submitted for verification — ${r.skills.length} skills detected`);
      setOpen(false); setFile(null); setCourseQ("");
      setF({ kind: "certification", title: "", issuer: "", description: "", course_id: "", credential_id: "", credential_url: "", issued_on: "" });
      reload(); onChange?.();
    } catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  };
  const removeSkill = async (ev: EvidenceRow, id: number) => {
    await api.put(`/evidence/${ev.id}/skills`, { skill_ids: ev.skills.filter((s) => s.id !== id).map((s) => s.id) }); reload(); onChange?.();
  };
  const del = async (ev: EvidenceRow) => { if (confirm(`Remove "${ev.title}"?`)) { await api.del(`/evidence/${ev.id}`); reload(); onChange?.(); } };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-comet-200 bg-comet-50 p-4 text-sm text-comet-900">
        <div><b>Show employers what you've learned.</b> Describe courses, certifications and projects and upload proof. Once an advisor or admin verifies it, the skills count fully toward every match, and verified certifications add <b>bonus points</b> (usually +10) to jobs that need those skills.</div>
        <button className="btn-primary" onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Add course or certification</button>
      </div>
      {loading ? <Spinner /> : !data?.length ? <Empty icon={<Award className="h-8 w-8" />} title="Nothing added yet">Example: “AWS Certified Cloud Practitioner — learned EC2, S3, IAM and cloud security” with your certificate PDF.</Empty> : (
        <div className="grid gap-4 md:grid-cols-2">
          {data.map((e) => { const K = KIND[e.kind]; return (
            <Card key={e.id} title={<span className="flex items-center gap-2"><K.Icon className="h-4 w-4 text-comet-600" />{e.title}</span>} actions={<StatusChip e={e} />}>
              <div className="space-y-2 text-sm">
                <div className="text-xs text-slate-500">{K.label}{e.issuer ? ` · ${e.issuer}` : ""}{e.course ? ` · ${e.course.code}` : ""}{e.issued_on ? ` · ${e.issued_on}` : ""}</div>
                {e.description && <p className="text-slate-700">{e.description}</p>}
                <div className="flex flex-wrap gap-1">{e.skills.map((s) => (
                  <span key={s.id} className="chip bg-comet-100 text-comet-800">{s.name}{e.status !== "verified" && <button onClick={() => removeSkill(e, s.id)} aria-label={`Remove ${s.name}`} className="ml-0.5 text-comet-600 hover:text-red-600">×</button>}</span>))}</div>
                <div className="flex flex-wrap items-center gap-3 text-xs">
                  {e.file && <button className="inline-flex items-center gap-1 font-semibold text-comet-700 hover:underline" onClick={() => openFile(e.id)}><FileText className="h-3.5 w-3.5" />{e.file.filename}</button>}
                  {e.credential_url && <a className="inline-flex items-center gap-1 font-semibold text-comet-700 hover:underline" href={e.credential_url} target="_blank" rel="noreferrer"><ExternalLink className="h-3.5 w-3.5" />Verification link</a>}
                  {e.status !== "verified" && <button className="ml-auto inline-flex items-center gap-1 text-slate-400 hover:text-red-600" onClick={() => del(e)}><Trash2 className="h-3.5 w-3.5" />Remove</button>}
                </div>
                {e.review_note && <div className={`rounded-lg p-2 text-xs ${e.status === "rejected" ? "bg-red-50 text-red-800" : "bg-slate-50 text-slate-600"}`}><b>Reviewer:</b> {e.review_note}</div>}
              </div>
            </Card>); })}
        </div>)}

      <Modal open={open} onClose={() => setOpen(false)} title="Add a course, certification or project" wide>
        <form onSubmit={submit} className="space-y-3">
          <ErrorBox error={err} />
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            {(Object.keys(KIND) as (keyof typeof KIND)[]).map((k) => { const K = KIND[k]; return (
              <button type="button" key={k} onClick={() => setF({ ...f, kind: k })} className={`flex items-center gap-2 rounded-lg border p-2.5 text-sm font-semibold ${f.kind === k ? "border-comet-500 bg-comet-50 text-comet-800" : "border-slate-200 text-slate-600"}`}>
                <K.Icon className="h-4 w-4" />{K.label}</button>); })}
          </div>
          <p className="text-xs text-slate-500">{KIND[f.kind as keyof typeof KIND].hint}</p>
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="Title"><input className="input" required value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder={f.kind === "certification" ? "AWS Certified Cloud Practitioner" : "Applied Machine Learning"} /></Field>
            <Field label={f.kind === "experience" ? "Company" : "Issuer / provider"}><input className="input" value={f.issuer} onChange={(e) => setF({ ...f, issuer: e.target.value })} placeholder="Amazon Web Services, Coursera, UT Dallas…" /></Field>
          </div>
          {f.kind === "course" && (
            <div className="relative"><Field label="Matching UTD course (optional)" hint="Link it if this is a UTD catalog course — once verified it counts as completed in CometPath">
              <input className="input" value={courseQ} onChange={(e) => { setCourseQ(e.target.value); setF({ ...f, course_id: "" }); }} placeholder="Search e.g. BUAN 6341" /></Field>
              {courses.data && courseQ.length >= 2 && !f.course_id && <div className="absolute z-10 mt-1 w-full rounded-lg border border-slate-200 bg-white shadow-lg">
                {courses.data.map((c) => <button type="button" key={c.id} className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50" onClick={() => { setF({ ...f, course_id: c.id }); setCourseQ(`${c.code} ${c.title}`); }}><b>{c.code}</b> {c.title}</button>)}</div>}
            </div>)}
          <Field label="What did you learn or build?" hint="Be specific — tools, techniques and results. CometIQ detects skills from this text.">
            <textarea className="input h-28" required value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })}
              placeholder="Learned core AWS services (EC2, S3, IAM), cloud security basics and cost management; deployed a static website on S3." /></Field>
          <div className="grid gap-3 md:grid-cols-3">
            <Field label="Credential ID"><input className="input" value={f.credential_id} onChange={(e) => setF({ ...f, credential_id: e.target.value })} /></Field>
            <Field label="Verification URL"><input className="input" type="url" value={f.credential_url} onChange={(e) => setF({ ...f, credential_url: e.target.value })} placeholder="https://…" /></Field>
            <Field label="Completed (month/year)"><input className="input" value={f.issued_on} onChange={(e) => setF({ ...f, issued_on: e.target.value })} placeholder="Aug 2026" /></Field>
          </div>
          <Field label={`Proof ${f.kind === "certification" ? "(certificate — required unless you add a verification URL)" : "(optional)"}`} hint="PDF, PNG, JPG or WebP · up to 10 MB">
            <input type="file" accept=".pdf,.png,.jpg,.jpeg,.webp" className="input" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></Field>
          <button className="btn-accent w-full" disabled={busy}>{busy ? "Submitting…" : "Submit for verification"}</button>
        </form>
      </Modal>
    </div>
  );
}
