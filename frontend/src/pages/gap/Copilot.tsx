import { ArrowRight, GitPullRequest, RotateCcw, Save, Sparkles, TrendingDown, TrendingUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Card, ErrorBox, Field, Modal, PageHeader, Spinner } from "../../components/ui";
import { api, waitForTask } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { StatusTag, type Status } from "../../lib/viz";

interface Change {
  skill: string; category: string; from: Status; to: Status; points: number; share: number; priority: string; job_count: number; postings: number;
  required_count: number; preferred_count: number; sources: Record<string, number>; first_posted: string | null; last_posted: string | null;
  mentions_from: number; mentions_to: number; excerpts: string[]; map_from: string; map_to: string; also_in: { course: string; level: string; source: string }[];
}
interface Preview {
  base: { label: string; score: number }; draft: { score: number; skills_detected: number }; delta: number;
  sample: { name: string; postings: number; top_n: number }; scoring_version: string; changes: Change[];
  added_outside_top: string[]; removed_outside_top: string[]; overlaps: { skill: string; courses: string[] }[]; programs: string[]; note: string;
}
interface History { syllabus: { id: string; code: string | null; title: string; semester: string | null }; versions: { id: string; version: number; semester: string | null }[] }

const LEVEL_NAME: Record<string, string> = { "-": "not addressed", I: "introduced", P: "practiced", M: "mastered" };
const fmt = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v).toFixed(1)}`;

function sentence(c: Change) {
  const verb = c.mentions_to > c.mentions_from ? "You added" : "You removed";
  const what = c.mentions_to > c.mentions_from ? (c.excerpts[0] ? `“${c.excerpts[0].slice(0, 70)}${c.excerpts[0].length > 70 ? "…" : ""}”` : `${c.skill} content`) : `mentions of ${c.skill}`;
  return `${verb} ${what}: ${c.skill} moves from ${c.from} to ${c.to}, ${fmt(c.points)} points.`;
}

export default function Copilot() {
  const { sid } = useParams();
  const nav = useNavigate();
  const { data: hist, error } = useApi<History>(`/gap/syllabi/${sid}/history`);
  const last = hist?.versions.at(-1);
  const { data: cur } = useApi<{ text: string }>(last ? `/gap/syllabi/${sid}/versions/${last.id}/text` : null);
  const [text, setText] = useState<string | null>(null);
  const [p, setP] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialog, setDialog] = useState<"version" | "proposal" | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const seq = useRef(0);

  useEffect(() => { if (cur && text === null) setText(cur.text); }, [cur, text]);
  useEffect(() => {
    if (text === null || !sid) return;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      const n = ++seq.current;
      setBusy(true);
      try { const r = await api.post<Preview>("/gap/copilot/preview", { syllabus_id: sid, text }); if (n === seq.current) setP(r); } finally { if (n === seq.current) setBusy(false); }
    }, 600);
    return () => window.clearTimeout(timer.current);
  }, [text, sid]);

  if (error) return <ErrorBox error={error} />;
  if (!hist || text === null) return <Spinner />;
  const changed = cur && text !== cur.text;
  return (
    <div className="space-y-4">
      <PageHeader icon={<Sparkles className="h-5 w-5" />} title={`Syllabus copilot · ${hist.syllabus.code ?? ""} ${hist.syllabus.title}`}
        subtitle={`Editing from syllabus v${last?.version ?? "?"}${last?.semester ? ` (${last.semester})` : ""}. The score and evidence update as you type.`}
        actions={<>
          <Link to={`/gap/course/${sid}`} className="btn-ghost btn-sm">Course history</Link>
          <button className="btn-ghost btn-sm" disabled={!changed} onClick={() => cur && setText(cur.text)}><RotateCcw className="h-4 w-4" />Reset</button>
          <button className="btn-ghost btn-sm" disabled={!changed} onClick={() => setDialog("version")}><Save className="h-4 w-4" />Save as new version</button>
          <button className="btn-primary btn-sm" disabled={!changed} onClick={() => setDialog("proposal")}><GitPullRequest className="h-4 w-4" />Open a proposal</button>
        </>} />
      <div className="grid gap-4 xl:grid-cols-[1fr_440px]">
        <Card padded={false}>
          <label htmlFor="copilot-text" className="sr-only">Syllabus text</label>
          <textarea id="copilot-text" className="block h-[calc(100vh-230px)] min-h-[520px] w-full resize-none rounded-xl border-0 p-4 font-mono text-[13px] leading-relaxed text-slate-800 focus:ring-2 focus:ring-comet-600"
            value={text} onChange={(e) => setText(e.target.value)} spellCheck />
        </Card>
        <aside className="space-y-4 xl:sticky xl:top-4 xl:self-start" aria-live="polite">
          <Card>
            <div className="flex items-end justify-between gap-3">
              <div>
                <div className="text-xs font-semibold uppercase text-slate-500">Mention-based coverage</div>
                <div className="mt-1 flex items-center gap-2 text-2xl font-bold text-slate-800">
                  <span className="text-slate-500">{p ? Math.round(p.base.score) : "—"}%</span><ArrowRight className="h-5 w-5 text-slate-400" aria-hidden />
                  <span>{p ? Math.round(p.draft.score) : "—"}%</span>
                </div>
              </div>
              {p && <div className={`flex items-center gap-1 rounded-lg px-2 py-1 text-lg font-bold ${p.delta > 0 ? "bg-green-50 text-green-800" : p.delta < 0 ? "bg-red-50 text-red-800" : "bg-slate-100 text-slate-700"}`}>
                {p.delta > 0 ? <TrendingUp className="h-5 w-5" aria-hidden /> : p.delta < 0 ? <TrendingDown className="h-5 w-5" aria-hidden /> : null}{fmt(p.delta)}</div>}
            </div>
            {p && <p className="mt-2 text-xs text-slate-600">Against {p.sample.name} ({p.sample.postings} postings, top {p.sample.top_n} skills) · scoring {p.scoring_version}{busy ? " · updating…" : ""}</p>}
          </Card>
          <Card title="What your edits change">
            {!p ? <Spinner /> : !p.changes.length ? <p className="text-sm text-slate-600">No in-demand skill has changed status yet. Add a lab, assignment or weekly topic that uses a skill, and the effect appears here.</p> : (
              <ul className="space-y-3">{p.changes.map((c) => (
                <li key={c.skill} className="rounded-lg border border-slate-200 p-3 text-sm">
                  <p className="font-medium text-slate-800">{sentence(c)}</p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs"><StatusTag s={c.from} /><ArrowRight className="h-3 w-3 text-slate-400" aria-hidden /><StatusTag s={c.to} />
                    <span className="text-slate-600">· mentions {c.mentions_from} → {c.mentions_to}</span></div>
                  <p className="mt-1.5 text-xs text-slate-700"><b>{c.job_count}</b> of {c.postings} sampled postings ask for {c.skill} ({c.required_count} required, {c.preferred_count} preferred){Object.keys(c.sources).length ? ` · ${Object.entries(c.sources).map(([k, v]) => `${k} ${v}`).join(", ")}` : ""}{c.first_posted ? ` · posted ${c.first_posted} to ${c.last_posted}` : ""}</p>
                  <p className="text-xs text-slate-700">Curriculum map for this course: <b>{LEVEL_NAME[c.map_from]}</b> → <b>{LEVEL_NAME[c.map_to]}</b> (unverified until a faculty review)</p>
                  {c.also_in.length > 0 && <p className="text-xs text-slate-600">Also in: {c.also_in.map((x) => `${x.course} (${x.level}, ${x.source})`).join(", ")}</p>}
                </li>))}</ul>)}
          </Card>
          {p && p.overlaps.length > 0 && <Card title="Possible overlap">
            <ul className="space-y-1 text-sm">{p.overlaps.map((o) => <li key={o.skill}><b>{o.skill}</b> is already practiced in {o.courses.join(", ")}. Consider a prerequisite link or shared materials instead of repeating it.</li>)}</ul>
          </Card>}
          {p && (p.added_outside_top.length > 0 || p.removed_outside_top.length > 0) && <Card title="Other skills detected">
            {p.added_outside_top.length > 0 && <p className="text-sm text-slate-700">Now mentioned (not among the top skills in this job sample): {p.added_outside_top.join(", ")}</p>}
            {p.removed_outside_top.length > 0 && <p className="mt-1 text-sm text-slate-700">No longer mentioned: {p.removed_outside_top.join(", ")}</p>}
          </Card>}
          {p && <p className="text-xs text-slate-500">{p.note}{p.programs.length ? ` Part of: ${p.programs.join("; ")}.` : ""}</p>}
        </aside>
      </div>
      <SaveDialog kind={dialog} sid={sid!} text={text} code={hist.syllabus.code} delta={p?.delta ?? 0} skills={p?.changes.filter((c) => c.points > 0).map((c) => c.skill) ?? []}
        onClose={() => setDialog(null)} onDone={(to) => nav(to)} />
    </div>
  );
}

function SaveDialog({ kind, sid, text, code, delta, skills, onClose, onDone }: { kind: "version" | "proposal" | null; sid: string; text: string; code: string | null; delta: number; skills: string[]; onClose: () => void; onDone: (to: string) => void }) {
  const [term, setTerm] = useState("");
  const [note, setNote] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (kind) { setTitle(skills.length ? `Add ${skills.join(", ")} to ${code ?? "the course"}` : `Revise ${code ?? "the course"}`); setNote(skills.length ? `Adds ${skills.join(", ")} (${delta > 0 ? "+" : ""}${delta} points, mention-based)` : ""); } }, [kind]); // eslint-disable-line react-hooks/exhaustive-deps
  const go = async () => {
    setBusy(true); setErr(null);
    try {
      if (kind === "version") {
        const fd = new FormData(); fd.append("semester", term); fd.append("change_note", note); fd.append("text", text);
        const r = await api.post<{ task_id: string }>(`/gap/syllabi/${sid}/versions`, fd); await waitForTask(r.task_id); onDone(`/gap/course/${sid}`);
      } else {
        const r = await api.post<{ id: string }>("/curriculum/proposals", { syllabus_id: sid, title, summary: note, effective_term: term, proposed_text: text });
        onDone(`/curriculum/proposals/${r.id}`);
      }
    } catch (e) { setErr((e as Error).message); setBusy(false); }
  };
  return (
    <Modal open={!!kind} onClose={onClose} title={kind === "version" ? "Save as a new syllabus version" : "Open a curriculum proposal"}>
      <div className="space-y-3 text-sm">
        <p className="text-slate-600">{kind === "version" ? "The edited text becomes the next syllabus version and is analyzed against the same job sample. Earlier versions stay in Course history."
          : "Colleagues review the edited text as a diff against the current syllabus and approve it before it is adopted."}</p>
        {kind === "proposal" && <Field label="Title"><input className="input" value={title} onChange={(e) => setTitle(e.target.value)} /></Field>}
        <Field label={kind === "version" ? "Semester" : "Effective term"}><input className="input" value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Fall 2027" /></Field>
        <Field label={kind === "version" ? "What changed" : "Summary for reviewers"}><textarea className="input min-h-[60px]" value={note} onChange={(e) => setNote(e.target.value)} /></Field>
        {err && <p role="alert" className="text-red-700">{err}</p>}
        <button className="btn-primary w-full" onClick={go} disabled={busy || (kind === "version" ? term.trim().length < 4 : title.trim().length < 5)}>{busy ? "Saving…" : kind === "version" ? "Save and analyze" : "Create draft proposal"}</button>
      </div>
    </Modal>
  );
}
