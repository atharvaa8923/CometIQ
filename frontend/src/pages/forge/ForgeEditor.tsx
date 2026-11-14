import { ArrowDown, ArrowRight, ArrowUp, BadgeCheck, BookOpen, Download, FileText, Lock, Plus, Save, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Badge, Card, ErrorBox, PageHeader, Spinner, Tabs } from "../../components/ui";
import { api, download } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { useToast } from "../../lib/toast";
import type { Content, Draft, Module } from "./types";

type Tab = "schedule" | "outcomes" | "assessment" | "project" | "alignment" | "changes";
const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);

export default function ForgeEditor() {
  const { id } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const { data, loading, error, setData } = useApi<Draft>(`/forge/drafts/${id}`);
  const [c, setC] = useState<Content | null>(null);
  const [dirty, setDirty] = useState(false);
  const [tab, setTab] = useState<Tab>("schedule");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (data) { setC(structuredClone(data.content)); setDirty(false); } }, [data]);

  if (loading || !c) return error ? <ErrorBox error={error} /> : <Spinner />;
  const d = data!;
  const locked = d.status === "approved";
  const upd = (patch: Partial<Content>) => { setC({ ...c, ...patch }); setDirty(true); };
  const updModule = (i: number, patch: Partial<Module>) => upd({ modules: c.modules.map((m, k) => (k === i ? { ...m, ...patch } : m)) });
  const move = (i: number, dir: -1 | 1) => {
    const ms = [...c.modules]; const j = i + dir;
    if (j < 0 || j >= ms.length) return;
    [ms[i], ms[j]] = [ms[j], ms[i]];
    upd({ modules: ms.map((m, k) => ({ ...m, week: k + 1 })) });
  };
  const totalWeight = c.assessments.reduce((s, a) => s + (Number(a.weight) || 0), 0);

  const save = async () => {
    setBusy(true);
    try { const r = await api.put<Draft>(`/forge/drafts/${d.id}`, { content: c }); setData(r); toast("Draft saved"); }
    catch (e) { toast((e as Error).message, "error"); } finally { setBusy(false); }
  };
  const approve = async () => {
    if (dirty) await save();
    if (!confirm("Approve this syllabus? It will be locked and its skills added to the knowledge graph.")) return;
    const r = await api.post<Draft & { graph_skills_added: number }>(`/forge/drafts/${d.id}/approve`);
    setData(r); toast(`Approved. ${r.graph_skills_added} new skills added to the course in the knowledge graph.`);
  };
  const file = `${d.title.replace(/\s+/g, "_")}_v${d.version}`;

  const ed = "input py-1.5";
  return (
    <div className="space-y-5">
      <PageHeader icon={<BookOpen className="h-5 w-5" />} accent="flame" title={`${c.course_code} ${c.course_title}`}
        subtitle={`Syllabus draft · ${d.engine === "claude" ? "generated with Claude" : "generated with the CometIQ engine"} · ${c.framework} aligned`}
        actions={<>
          {d.versions.length > 1 && (
            <select className="input w-32 py-1.5 text-xs" value={d.id} onChange={(e) => nav(`/forge/${e.target.value}`)} aria-label="Version">
              {d.versions.map((v) => <option key={v.id} value={v.id}>v{v.version}{v.status === "approved" ? " ✓" : ""}</option>)}</select>)}
          <button className="btn-ghost btn-sm" onClick={() => download(`/forge/drafts/${d.id}/export.docx`, `${file}.docx`)}><FileText className="h-4 w-4" />Word</button>
          <button className="btn-ghost btn-sm" onClick={() => download(`/forge/drafts/${d.id}/export.pdf`, `${file}.pdf`)}><Download className="h-4 w-4" />PDF</button>
          {!locked && <button className="btn-primary btn-sm" onClick={save} disabled={!dirty || busy}><Save className="h-4 w-4" />{dirty ? "Save" : "Saved"}</button>}
          {!locked ? <button className="btn-accent btn-sm" onClick={approve}><BadgeCheck className="h-4 w-4" />Approve</button>
            : <><Badge color="green"><Lock className="h-3 w-3" />Approved v{d.version}</Badge>
              {d.analysis_id && <Link to={`/forge/new?analysis=${d.analysis_id}`} className="btn-ghost btn-sm"><Plus className="h-4 w-4" />New version</Link>}</>}
        </>} />

      <div className="grid gap-4 md:grid-cols-4">
        <div className="card flex items-center gap-3 p-4 md:col-span-2">
          {d.scores.before != null ? (<>
            <div className="text-center"><div className="text-2xl font-bold text-slate-400">{Math.round(d.scores.before)}%</div><div className="text-[11px] text-slate-500">current</div></div>
            <ArrowRight className="h-5 w-5 text-flame-500" />
            <div className="text-center"><div className="text-2xl font-bold text-comet-700">{Math.round(d.scores.after ?? 0)}%</div><div className="text-[11px] text-slate-500">projected</div></div>
            <div className="ml-2 text-sm text-slate-600">industry coverage vs. <b>{d.scores.target}</b> postings once this draft is taught{d.analysis_id && <> · <Link to={`/gap/analysis/${d.analysis_id}`} className="font-semibold text-comet-700 hover:underline">gap report</Link></>}</div>
          </>) : <div className="text-sm text-slate-500">No linked gap report.</div>}
        </div>
        <div className="card p-4"><div className="text-xs font-semibold uppercase text-slate-500">Gaps addressed</div><div className="mt-1 flex flex-wrap gap-1">{c.gaps_addressed.map((g) => <Badge key={g} color="orange">{g}</Badge>)}</div></div>
        <div className="card p-4"><div className="text-xs font-semibold uppercase text-slate-500">Structure</div>
          <div className="mt-1 text-sm text-slate-700">{c.modules.length} weeks · {c.learning_outcomes.length} outcomes · {c.assessments.length} assessments</div></div>
      </div>

      <Card title="Course description"><textarea className="input h-24" disabled={locked} value={c.description} onChange={(e) => upd({ description: e.target.value })} aria-label="Course description" /></Card>

      <Tabs value={tab} onChange={setTab} tabs={[
        { id: "schedule", label: "Weekly modules" }, { id: "outcomes", label: "Learning outcomes" }, { id: "assessment", label: `Assessment (${totalWeight}%)` },
        { id: "project", label: "Team project" }, { id: "alignment", label: "Accreditation & goals" }, { id: "changes", label: "What changed" }]} />

      {tab === "schedule" && (
        <div className="space-y-2">
          {c.modules.map((m, i) => (
            <div key={i} className={`card grid gap-3 p-4 md:grid-cols-[70px_1fr_1fr_110px] ${m.is_new ? "border-l-4 border-l-flame-500" : ""}`}>
              <div><div className="text-xs font-semibold uppercase text-slate-500">Week</div><div className="text-2xl font-bold text-comet-800">{i + 1}</div>
                {m.is_new && <Badge color="orange"><Sparkles className="h-3 w-3" />New</Badge>}</div>
              <div className="space-y-2">
                <input className={`${ed} font-semibold`} disabled={locked} value={m.title} onChange={(e) => updModule(i, { title: e.target.value })} aria-label={`Week ${i + 1} title`} />
                <textarea className={`${ed} h-20 text-xs`} disabled={locked} value={m.topics.join("\n")} onChange={(e) => updModule(i, { topics: lines(e.target.value) })} aria-label={`Week ${i + 1} topics`} placeholder="Topics, one per line" />
              </div>
              <div className="space-y-2">
                <textarea className={`${ed} h-20 text-xs`} disabled={locked} value={m.activities.join("\n")} onChange={(e) => updModule(i, { activities: lines(e.target.value) })} aria-label={`Week ${i + 1} activities`} placeholder="Activities / labs, one per line" />
                <div className="flex flex-wrap gap-1">{m.skills.map((s) => <Badge key={s} color={m.is_new ? "orange" : "green"}>{s}</Badge>)}{m.outcomes.map((o) => <Badge key={o} color="blue">{o}</Badge>)}</div>
              </div>
              {!locked && <div className="flex items-start justify-end gap-1">
                <button className="btn-ghost btn-sm px-2" onClick={() => move(i, -1)} aria-label="Move up"><ArrowUp className="h-3.5 w-3.5" /></button>
                <button className="btn-ghost btn-sm px-2" onClick={() => move(i, 1)} aria-label="Move down"><ArrowDown className="h-3.5 w-3.5" /></button>
                <button className="btn-ghost btn-sm px-2 text-red-600" onClick={() => upd({ modules: c.modules.filter((_, k) => k !== i) })} aria-label="Delete week"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>}
            </div>))}
          {!locked && <button className="btn-ghost w-full" onClick={() => upd({ modules: [...c.modules, { week: c.modules.length + 1, title: "New module", topics: [], skills: [], activities: [], outcomes: [], is_new: true }] })}><Plus className="h-4 w-4" />Add week</button>}
        </div>)}

      {tab === "outcomes" && (
        <Card>
          <div className="space-y-2">
            {c.learning_outcomes.map((o, i) => (
              <div key={o.id} className="grid items-center gap-2 md:grid-cols-[60px_110px_1fr_auto]">
                <Badge color={o.is_new ? "orange" : "blue"}>{o.id}</Badge>
                <select className={ed} disabled={locked} value={o.bloom} aria-label={`${o.id} Bloom level`}
                  onChange={(e) => upd({ learning_outcomes: c.learning_outcomes.map((x, k) => (k === i ? { ...x, bloom: e.target.value } : x)) })}>
                  {["Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create"].map((b) => <option key={b}>{b}</option>)}</select>
                <input className={ed} disabled={locked} value={o.text} aria-label={`${o.id} text`} onChange={(e) => upd({ learning_outcomes: c.learning_outcomes.map((x, k) => (k === i ? { ...x, text: e.target.value } : x)) })} />
                {!locked && <button className="btn-ghost btn-sm px-2 text-red-600" aria-label={`Delete ${o.id}`} onClick={() => upd({ learning_outcomes: c.learning_outcomes.filter((_, k) => k !== i) })}><Trash2 className="h-3.5 w-3.5" /></button>}
              </div>))}
          </div>
          {!locked && <button className="btn-ghost btn-sm mt-3" onClick={() => upd({ learning_outcomes: [...c.learning_outcomes, { id: `LO${c.learning_outcomes.length + 1}`, text: "", bloom: "Apply", skills: [], is_new: true }] })}><Plus className="h-4 w-4" />Add outcome</button>}
        </Card>)}

      {tab === "assessment" && (
        <Card title={<span>Total weight: <span className={totalWeight === 100 ? "text-comet-700" : "text-red-600"}>{totalWeight}%</span>{totalWeight !== 100 && " — must equal 100% to save"}</span>}>
          <div className="space-y-2">
            {c.assessments.map((a, i) => (
              <div key={i} className="grid items-start gap-2 md:grid-cols-[200px_90px_1fr_auto]">
                <input className={`${ed} font-semibold`} disabled={locked} value={a.name} aria-label="Assessment name" onChange={(e) => upd({ assessments: c.assessments.map((x, k) => (k === i ? { ...x, name: e.target.value } : x)) })} />
                <div className="relative"><input type="number" min={0} max={100} className={`${ed} pr-6`} disabled={locked} value={a.weight} aria-label={`${a.name} weight`}
                  onChange={(e) => upd({ assessments: c.assessments.map((x, k) => (k === i ? { ...x, weight: +e.target.value } : x)) })} /><span className="absolute right-2 top-1.5 text-xs text-slate-400">%</span></div>
                <textarea className={`${ed} h-16 text-xs`} disabled={locked} value={a.description} aria-label={`${a.name} description`} onChange={(e) => upd({ assessments: c.assessments.map((x, k) => (k === i ? { ...x, description: e.target.value } : x)) })} />
                {!locked && <button className="btn-ghost btn-sm px-2 text-red-600" aria-label={`Delete ${a.name}`} onClick={() => upd({ assessments: c.assessments.filter((_, k) => k !== i) })}><Trash2 className="h-3.5 w-3.5" /></button>}
              </div>))}
          </div>
          {!locked && <button className="btn-ghost btn-sm mt-3" onClick={() => upd({ assessments: [...c.assessments, { name: "New assessment", type: "assignment", weight: 0, description: "", outcomes: [], skills: [] }] })}><Plus className="h-4 w-4" />Add assessment</button>}
        </Card>)}

      {tab === "project" && (
        <Card>
          <div className="space-y-3">
            <input className={`${ed} font-semibold`} disabled={locked} value={c.project.title} aria-label="Project title" onChange={(e) => upd({ project: { ...c.project, title: e.target.value } })} />
            <textarea className={`${ed} h-24`} disabled={locked} value={c.project.description} aria-label="Project description" onChange={(e) => upd({ project: { ...c.project, description: e.target.value } })} />
            <label className="label">Deliverables (one per line)</label>
            <textarea className={`${ed} h-28 text-sm`} disabled={locked} value={c.project.deliverables.join("\n")} onChange={(e) => upd({ project: { ...c.project, deliverables: lines(e.target.value) } })} />
            <div className="flex flex-wrap gap-1">{c.project.skills.map((s) => <Badge key={s} color="green">{s}</Badge>)}</div>
          </div>
        </Card>)}

      {tab === "alignment" && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title={`${c.framework} standards × learning outcomes`} padded={false}>
            {c.accreditation.length === 0 ? <p className="p-5 text-sm text-slate-500">No accreditation framework selected.</p> : (
              <div className="overflow-x-auto p-3">
                <table className="text-xs"><thead><tr><th className="p-1 text-left">Standard</th>{c.learning_outcomes.map((o) => <th key={o.id} className="p-1 text-slate-500">{o.id}</th>)}</tr></thead>
                  <tbody>{c.accreditation.map((a) => (
                    <tr key={a.standard}><td className="whitespace-nowrap p-1 pr-3 font-medium text-slate-700">{a.standard}</td>
                      {c.learning_outcomes.map((o) => <td key={o.id} className="p-0.5"><div className={`mx-auto h-5 w-5 rounded-sm ${a.outcomes.includes(o.id) ? "bg-comet-600" : "bg-slate-100"}`}
                        title={`${a.standard} ${a.outcomes.includes(o.id) ? "is assessed by" : "is not mapped to"} ${o.id}`} /></td>)}</tr>))}</tbody></table>
              </div>)}
          </Card>
          <Card title="Program goals">
            <ul className="space-y-2 text-sm">{c.program_goals.map((g) => (
              <li key={g.goal} className="flex items-start justify-between gap-3"><span>{g.goal}</span>
                <span className="flex flex-wrap justify-end gap-1">{g.outcomes.length ? g.outcomes.map((o) => <Badge key={o} color="blue">{o}</Badge>) : <Badge color="red">not yet addressed</Badge>}</span></li>))}</ul>
          </Card>
        </div>)}

      {tab === "changes" && (
        <Card title="What changed and why">
          <ul className="space-y-2 text-sm text-slate-700">{c.change_log.map((x, i) => <li key={i} className="flex gap-2"><Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-flame-500" />{x}</li>)}</ul>
        </Card>)}
    </div>
  );
}
