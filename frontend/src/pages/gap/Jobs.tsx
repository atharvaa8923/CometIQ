import { Plus, RefreshCw, Upload } from "lucide-react";
import { useState } from "react";
import { Badge, Card, ErrorBox, Field, Modal, Spinner } from "../../components/ui";
import { api } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { useToast } from "../../lib/toast";

export interface JobRow { id: string; title: string; company: string | null; location: string | null; role_family: string | null; employment_type: string;
  source: string; url: string | null; skills: { id: number; name: string; importance: string }[] }

export default function Jobs() {
  const toast = useToast();
  const [q, setQ] = useState("");
  const [fam, setFam] = useState("");
  const meta = useApi<{ role_families: string[] }>("/meta");
  const { data, loading, reload } = useApi<{ total: number; by_source: Record<string, number>; items: JobRow[] }>(
    `/jobs?limit=100&q=${encodeURIComponent(q)}&role_family=${encodeURIComponent(fam)}`);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ title: "", company: "", location: "", description: "" });
  const [err, setErr] = useState<string | null>(null);

  const sync = async () => {
    setBusy(true);
    try { const r = await api.post<{ fetched: number; added: number }>("/jobs/sync", { source: "github" }); toast(`Fetched ${r.fetched} postings, ${r.added} new`); reload(); }
    catch (e) { toast((e as Error).message, "error"); } finally { setBusy(false); }
  };
  const csv = async (file: File) => {
    const fd = new FormData(); fd.append("file", file);
    try { const r = await api.post<{ rows: number; added: number }>("/jobs/import-csv", fd); toast(`Imported ${r.added} of ${r.rows} rows`); reload(); }
    catch (e) { toast((e as Error).message, "error"); }
  };
  const add = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    try { await api.post("/jobs", f); setOpen(false); setF({ title: "", company: "", location: "", description: "" }); toast("Posting added and skills extracted"); reload(); }
    catch (x) { setErr((x as Error).message); }
  };

  return (
    <Card padded={false} title={data ? `${data.total} open postings · ${Object.entries(data.by_source).map(([k, v]) => `${k}: ${v}`).join(" · ")}` : "Job postings"}
      actions={<div className="flex gap-2">
        <button className="btn-ghost btn-sm" onClick={sync} disabled={busy}><RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} />Sync live postings</button>
        <label className="btn-ghost btn-sm cursor-pointer"><Upload className="h-4 w-4" />Import CSV
          <input type="file" accept=".csv" className="hidden" onChange={(e) => e.target.files?.[0] && csv(e.target.files[0])} /></label>
        <button className="btn-primary btn-sm" onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Add posting</button></div>}>
      <div className="flex gap-2 border-b border-slate-100 p-3">
        <input className="input" placeholder="Search title, company, location…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search jobs" />
        <select className="input w-64" value={fam} onChange={(e) => setFam(e.target.value)} aria-label="Role family">
          <option value="">All role families</option>{meta.data?.role_families.map((r) => <option key={r}>{r}</option>)}</select>
      </div>
      {loading ? <Spinner /> : (
        <div className="max-h-[60vh] overflow-y-auto" tabIndex={0} role="region" aria-label="Job postings">
          <table className="table-base"><thead><tr><th>Role</th><th>Family</th><th>Skills extracted</th><th>Source</th></tr></thead>
            <tbody>{data?.items.map((j) => (
              <tr key={j.id}>
                <td><div className="font-semibold text-slate-800">{j.url ? <a href={j.url} target="_blank" rel="noreferrer" className="hover:underline">{j.title}</a> : j.title}</div>
                  <div className="text-xs text-slate-500">{j.company} · {j.location} · {j.employment_type}</div></td>
                <td className="text-xs">{j.role_family ?? "—"}</td>
                <td><div className="flex max-w-xl flex-wrap gap-1">{j.skills.slice(0, 10).map((s) => <Badge key={s.id} color={s.importance === "required" ? "green" : "slate"} title={s.importance}>{s.name}</Badge>)}
                  {j.skills.length > 10 && <Badge>+{j.skills.length - 10}</Badge>}</div></td>
                <td><Badge color="blue">{j.source}</Badge></td>
              </tr>))}</tbody></table>
        </div>)}
      <div className="border-t border-slate-100 px-4 py-2 text-xs text-slate-500">Green = required skill, gray = preferred. CSV columns: title, company, location, description, url.</div>
      <Modal open={open} onClose={() => setOpen(false)} title="Add a job posting" wide>
        <form onSubmit={add} className="space-y-3">
          <ErrorBox error={err} />
          <div className="grid gap-3 md:grid-cols-3">
            <Field label="Title"><input className="input" required value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
            <Field label="Company"><input className="input" value={f.company} onChange={(e) => setF({ ...f, company: e.target.value })} /></Field>
            <Field label="Location"><input className="input" value={f.location} onChange={(e) => setF({ ...f, location: e.target.value })} /></Field>
          </div>
          <Field label="Description" hint="Paste the full posting. Put nice-to-haves under a 'Preferred' heading."><textarea className="input h-48" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
          <button className="btn-primary">Add & extract skills</button>
        </form>
      </Modal>
    </Card>
  );
}
