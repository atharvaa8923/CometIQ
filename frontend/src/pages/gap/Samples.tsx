import { Download, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Card, Empty, Field } from "../../components/ui";
import { api, download } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { useToast } from "../../lib/toast";
import { TargetSelect } from "./GapHome";

export interface SampleInfo {
  id: string; name: string; method: string; criteria: Record<string, unknown>; created_at: string; created_by: string | null;
  total: number; sources: Record<string, number>; role_families: Record<string, number>; date_from: string | null; date_to: string | null; used_by: number;
}
export interface Provenance {
  total: number; sources: Record<string, number>; role_families: Record<string, number>; date_from: string | null; date_to: string | null;
  captured_at: string; kind: string; sample: { id: string; name: string; method: string; criteria: Record<string, unknown>; created_at: string } | null;
}

const SOURCES = ["seed", "github", "adzuna", "usajobs", "csv", "manual", "employer"];

export function SampleSelect({ id, value, onChange }: { id?: string; value: string | null; onChange: (v: string | null) => void }) {
  const { data } = useApi<SampleInfo[]>("/gap/samples");
  return (
    <select id={id} className="input" value={value ?? ""} onChange={(e) => onChange(e.target.value || null)}>
      <option value="">None — use all current postings for the target roles</option>
      {data?.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.total} postings, {s.date_from ?? "?"} to {s.date_to ?? "?"})</option>)}
    </select>
  );
}

export default function Samples() {
  const { data, reload } = useApi<SampleInfo[]>("/gap/samples");
  const toast = useToast();
  const [form, setForm] = useState({ name: "", method: "", role_family: "All roles", sources: [] as string[], date_from: "", date_to: "", location: "", query: "", max_postings: 500 });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  const create = async () => {
    setBusy(true); setErr(null);
    try {
      const body = { ...form, role_family: form.role_family === "All roles" ? null : form.role_family, sources: form.sources.length ? form.sources : null,
        date_from: form.date_from || null, date_to: form.date_to || null, location: form.location || null, query: form.query || null };
      const s = await api.post<SampleInfo>("/gap/samples", body);
      toast(`Sample saved with ${s.total} postings`); reload();
      setForm((f) => ({ ...f, name: "", method: "" }));
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const del = async (s: SampleInfo) => {
    if (!confirm(`Delete the sample "${s.name}"?`)) return;
    try { await api.del(`/gap/samples/${s.id}`); reload(); } catch (e) { toast((e as Error).message); }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
      <Card title="Documented job samples">
        <p className="mb-3 text-sm text-slate-600">A sample freezes a specific set of postings with a written method, so a gap report can be checked and repeated.
          Download the postings to share the evidence with reviewers.</p>
        {!data?.length ? <Empty title="No samples yet">Create one on the right, then choose it when you analyze a syllabus.</Empty> : (
          <ul className="space-y-3">{data.map((s) => (
            <li key={s.id} className="rounded-lg border border-slate-200 p-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-semibold text-comet-900">{s.name}</div>
                  <div className="text-xs text-slate-600"><b>{s.total}</b> postings · posted {s.date_from ?? "?"} to {s.date_to ?? "?"} · frozen {new Date(s.created_at).toLocaleDateString()}{s.created_by ? ` by ${s.created_by}` : ""}</div>
                  <div className="text-xs text-slate-600">Sources: {Object.entries(s.sources).map(([k, v]) => `${k} (${v})`).join(", ")}</div>
                  <div className="text-xs text-slate-600">Role families: {Object.entries(s.role_families).map(([k, v]) => `${k} (${v})`).join(", ")}</div>
                </div>
                <div className="flex shrink-0 gap-1">
                  <button className="btn-ghost btn-sm" onClick={() => download(`/gap/samples/${s.id}/postings.csv`, `job-sample-${s.name.replace(/\s+/g, "_")}.csv`)}><Download className="h-4 w-4" />Postings</button>
                  <button className="rounded p-1 text-slate-500 hover:bg-red-50 hover:text-red-600 disabled:opacity-40" onClick={() => del(s)} disabled={s.used_by > 0}
                    aria-label={`Delete ${s.name}`} title={s.used_by ? `Used by ${s.used_by} analyses` : "Delete"}><Trash2 className="h-4 w-4" /></button>
                </div>
              </div>
              <p className="mt-2 rounded bg-slate-50 px-2 py-1.5 text-sm text-slate-700"><b>Method:</b> {s.method}</p>
              {s.used_by > 0 && <p className="mt-1 text-xs text-slate-500">Evidence for {s.used_by} analys{s.used_by === 1 ? "is" : "es"}</p>}
            </li>))}</ul>)}
      </Card>
      <Card title="New sample">
        <div className="space-y-3">
          <Field label="Name"><input className="input" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. DFW business analytics postings, Oct 2026" /></Field>
          <Field label="Sampling method" hint="How the postings were chosen and what was excluded. At least a sentence.">
            <textarea className="input min-h-[80px]" value={form.method} onChange={(e) => set("method", e.target.value)}
              placeholder="e.g. All Adzuna and USAJobs postings for analyst roles in Texas posted 1–31 Oct 2026; duplicates removed by title + company." /></Field>
          <Field label="Role family"><TargetSelect value={form.role_family} onChange={(v) => set("role_family", v)} /></Field>
          <fieldset>
            <legend className="label">Sources (none selected = all)</legend>
            <div className="flex flex-wrap gap-2">{SOURCES.map((s) => (
              <label key={s} className="inline-flex items-center gap-1 text-sm"><input type="checkbox" checked={form.sources.includes(s)}
                onChange={(e) => set("sources", e.target.checked ? [...form.sources, s] : form.sources.filter((x) => x !== s))} />{s}</label>))}</div>
          </fieldset>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Posted from"><input type="date" className="input" value={form.date_from} onChange={(e) => set("date_from", e.target.value)} /></Field>
            <Field label="Posted to"><input type="date" className="input" value={form.date_to} onChange={(e) => set("date_to", e.target.value)} /></Field>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Location contains"><input className="input" value={form.location} onChange={(e) => set("location", e.target.value)} placeholder="TX" /></Field>
            <Field label="Title contains"><input className="input" value={form.query} onChange={(e) => set("query", e.target.value)} placeholder="analyst" /></Field>
          </div>
          {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
          <button className="btn-primary w-full" onClick={create} disabled={busy || form.name.trim().length < 3 || form.method.trim().length < 20}>
            <Plus className="h-4 w-4" />Freeze sample</button>
        </div>
      </Card>
    </div>
  );
}
