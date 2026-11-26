import { CheckCircle2, ChevronDown, ChevronRight, ClipboardCheck, Gavel, PencilLine, Quote } from "lucide-react";
import { Link } from "react-router-dom";
import { useMemo, useState } from "react";
import { Badge, Card } from "../../components/ui";
import { api } from "../../lib/api";
import { PRIORITY_COLOR, StatusTag, type Status } from "../../lib/viz";

export interface EvidenceRow {
  skill_id: number; name: string; category: string; demand: number; job_count: number; required_count?: number; preferred_count?: number;
  sources?: Record<string, number>; first_posted?: string | null; last_posted?: string | null;
  status: Status; priority: string; mentions: number; excerpts?: string[]; graded_share?: number; graded_in?: string[]; evidence: string | null; in_schedule?: boolean; taught_in?: string[];
}
export interface Review {
  skill_id: number; system_status: Status; faculty_status: string; decision: "confirmed" | "corrected"; rationale: string | null;
  action: "none" | "planned" | "done"; action_note: string | null; reviewer: string | null; carried_from: string | null; updated_at: string;
}
export interface Decision {
  id: string; syllabus_id: string; skill_id: number; skill: string; analysis_id: string | null; decision: DecisionKind; decision_label: string;
  rationale: string; covered_in: string[]; revisit_term: string | null; reviewer: string | null; decided_at: string;
  evidence: Record<string, string | number | null>; status: "open" | "drafted" | "implemented" | "superseded"; forge_draft_id: string | null;
  detected_in_version: number | null; implemented_note: string | null; superseded_by: string | null;
}
export type DecisionKind = "add_here" | "covered_elsewhere" | "defer" | "out_of_scope";
export const DECISION_STATUS: Record<Decision["status"], string> = { open: "Open", drafted: "Draft linked", implemented: "Implemented", superseded: "Superseded" };
export interface ReviewSummary {
  reviewed: number; confirmed: number; corrected: number; planned: number; done: number; not_relevant: number;
  total: number; gaps_total: number; gaps_reviewed: number; reviewed_score: number | null; reviewed_demand_share: number;
}

const FACULTY_LABEL: Record<string, string> = {
  practiced: "Practiced / assessed", mentioned_only: "Mentioned only", not_covered: "Not covered", not_relevant: "Not relevant to this course",
};
const IMPLIED: Record<Status, string> = { covered: "practiced", partial: "mentioned_only", missing: "not_covered" };
const ACTION_LABEL = { none: "No action", planned: "Change planned", done: "Change made" } as const;
const PRIORITY_RANK: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };

type Filter = "gaps" | "unreviewed" | "all";

export function ReviewPanel({ analysisId, syllabusId, rows, jobCount, reviews, statuses, onChange, decisions, decisionOptions, onDecision }: {
  analysisId: string; syllabusId: string; rows: EvidenceRow[]; jobCount: number; reviews: Record<string, Review>;
  statuses: Record<string, string>; onChange: (reviews: Record<string, Review>, summary: ReviewSummary) => void;
  decisions: Record<string, Decision>; decisionOptions: Record<string, string>; onDecision: (d: Decision) => void;
}) {
  const [filter, setFilter] = useState<Filter>("gaps");
  const [open, setOpen] = useState<number | null>(null);
  const ranked = useMemo(() => [...rows].sort((a, b) =>
    (a.status === "covered" ? 1 : 0) - (b.status === "covered" ? 1 : 0) || PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority] || b.demand - a.demand), [rows]);
  const shown = ranked.filter((r) => filter === "all" || (filter === "gaps" ? r.status !== "covered" : !reviews[r.skill_id]));

  return (
    <Card title={<span className="flex items-center gap-2"><ClipboardCheck className="h-4 w-4 text-comet-700" />Faculty review — evidence for each skill</span>}
      actions={<div role="group" aria-label="Show" className="flex gap-1">
        {([["gaps", "Highest-ranked gaps"], ["unreviewed", "Not yet reviewed"], ["all", "All skills"]] as [Filter, string][]).map(([k, l]) => (
          <button key={k} className={`btn-sm ${filter === k ? "btn-primary" : "btn-ghost"}`} aria-pressed={filter === k} onClick={() => setFilter(k)}>{l}</button>))}
      </div>}>
      <p className="mb-3 text-sm text-slate-600">
        {rows.some((r) => r.graded_share !== undefined)
          ? <>The system signal comes from <b>graded work in Canvas</b>: a skill carrying at least 5% of the course grade counts as practiced; one that is only mentioned counts as partial.</>
          : <>The system signal comes from <b>keyword mentions</b> in the syllabus.</>} It is a way to prioritize review, not a finding.
        For each skill, decide whether students actually <b>practice or demonstrate</b> it. A correction needs a short rationale,
        which is saved with your name.
      </p>
      <div className="divide-y divide-slate-100 rounded-lg border border-slate-200">
        {shown.length === 0 && <div className="p-4 text-sm text-slate-500">Nothing to show for this filter.</div>}
        {shown.map((r, i) => {
          const rv = reviews[r.skill_id];
          const isOpen = open === r.skill_id;
          return (
            <div key={r.skill_id}>
              <button className="grid w-full grid-cols-[24px_28px_minmax(120px,1fr)_auto_auto] items-center gap-2 px-3 py-2.5 text-left text-sm hover:bg-slate-50 sm:grid-cols-[24px_28px_minmax(140px,1fr)_160px_120px_170px]"
                aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : r.skill_id)}>
                {isOpen ? <ChevronDown className="h-4 w-4 text-slate-500" aria-hidden /> : <ChevronRight className="h-4 w-4 text-slate-500" aria-hidden />}
                <span className="text-xs font-semibold text-slate-500">#{i + 1}</span>
                <span><span className="font-medium text-slate-800">{r.name}</span> <Badge color={PRIORITY_COLOR[r.priority]}>{r.priority}</Badge></span>
                <span className="hidden text-xs text-slate-600 sm:block"><b>{r.job_count}</b> of {jobCount} postings</span>
                <StatusTag s={r.status} />
                <span className="text-xs">{rv ? <ReviewChip rv={rv} /> : <span className="text-slate-500">Not reviewed</span>}
                  {decisions[r.skill_id] && <span className="chip mt-1 bg-violet-50 text-violet-800"><Gavel className="h-3.5 w-3.5" aria-hidden />{decisions[r.skill_id].decision_label}</span>}</span>
              </button>
              {isOpen && <ReviewEditor analysisId={analysisId} row={r} jobCount={jobCount} rv={rv} statuses={statuses}
                onSaved={(next, summary) => { onChange(next, summary); }} reviews={reviews} />}
              {isOpen && rv && rv.faculty_status !== "practiced" && (
                <DecisionEditor key={decisions[r.skill_id]?.id ?? "new"} analysisId={analysisId} syllabusId={syllabusId} row={r}
                  current={decisions[r.skill_id]} options={decisionOptions} onSaved={onDecision} />)}
            </div>);
        })}
      </div>
    </Card>
  );
}

function ReviewChip({ rv }: { rv: Review }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {rv.decision === "confirmed"
        ? <span className="chip bg-green-50 text-green-800"><CheckCircle2 className="h-3.5 w-3.5" aria-hidden />Confirmed</span>
        : <span className="chip bg-blue-50 text-blue-800"><PencilLine className="h-3.5 w-3.5" aria-hidden />Corrected</span>}
      {rv.action !== "none" && <span className="chip bg-amber-50 text-amber-800">{ACTION_LABEL[rv.action]}</span>}
    </span>);
}

function ReviewEditor({ analysisId, row, jobCount, rv, statuses, reviews, onSaved }: {
  analysisId: string; row: EvidenceRow; jobCount: number; rv?: Review; statuses: Record<string, string>; reviews: Record<string, Review>;
  onSaved: (reviews: Record<string, Review>, summary: ReviewSummary) => void;
}) {
  const [fs, setFs] = useState(rv?.faculty_status ?? IMPLIED[row.status]);
  const [rationale, setRationale] = useState(rv?.rationale ?? "");
  const [action, setAction] = useState<Review["action"]>(rv?.action ?? "none");
  const [note, setNote] = useState(rv?.action_note ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const corrected = fs !== IMPLIED[row.status];
  const needsWhy = corrected || fs === "not_relevant";
  const id = `rv-${row.skill_id}`;
  const excerpts = row.excerpts?.length ? row.excerpts : row.evidence ? [row.evidence] : [];
  const src = Object.entries(row.sources ?? {});

  const save = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await api.put<{ review: Review; review_summary: ReviewSummary }>(`/gap/analyses/${analysisId}/reviews/${row.skill_id}`,
        { faculty_status: fs, rationale, action, action_note: note });
      onSaved({ ...reviews, [row.skill_id]: r.review }, r.review_summary);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const clear = async () => {
    setBusy(true);
    try {
      const r = await api.del<{ review_summary: ReviewSummary }>(`/gap/analyses/${analysisId}/reviews/${row.skill_id}`);
      const next = { ...reviews }; delete next[row.skill_id];
      setFs(IMPLIED[row.status]); setRationale(""); setAction("none"); setNote("");
      onSaved(next, r.review_summary);
    } finally { setBusy(false); }
  };

  return (
    <div className="grid gap-4 bg-slate-50 px-4 py-4 lg:grid-cols-2">
      <div className="space-y-3 text-sm">
        <div>
          <div className="label flex items-center gap-1"><Quote className="h-3.5 w-3.5" aria-hidden />Syllabus excerpt{excerpts.length > 1 ? "s" : ""}</div>
          {excerpts.length ? <ul className="space-y-1.5">{excerpts.map((e, i) => (
            <li key={i} className="rounded border-l-4 border-comet-600 bg-white px-3 py-1.5 text-slate-700">{e}</li>))}</ul>
            : <p className="rounded bg-white px-3 py-1.5 text-slate-500">No mention of {row.name} (or its aliases) was found in the syllabus text.</p>}
          <p className="mt-1 text-xs text-slate-500">{row.mentions} keyword mention{row.mentions === 1 ? "" : "s"}{row.in_schedule ? " · named in the weekly schedule" : ""}</p>
        </div>
        {row.graded_share !== undefined && <div>
          <div className="label">Graded work (Canvas)</div>
          {row.graded_share > 0
            ? <p className="text-slate-700"><b>{Math.round(row.graded_share * 100)}%</b> of the course grade practices {row.name}
                {row.graded_in?.length ? <>: {row.graded_in.join(", ")}</> : null}.</p>
            : <p className="text-slate-700">No graded assignment or rubric criterion practices {row.name}.</p>}
        </div>}
        <div>
          <div className="label">Job-market evidence</div>
          <p className="text-slate-700"><b>{row.job_count}</b> of <b>{jobCount}</b> sampled postings request {row.name}
            {row.required_count !== undefined && <> ({row.required_count} required, {row.preferred_count} preferred)</>}.</p>
          {src.length > 0 && <p className="text-xs text-slate-600">Sources: {src.map(([k, v]) => `${k} (${v})`).join(", ")}</p>}
          <p className="text-xs text-slate-600">Posted {row.first_posted ?? "?"} to {row.last_posted ?? "?"}</p>
          {row.taught_in && row.taught_in.length > 0 && <p className="mt-1 text-xs text-slate-600">Also taught in: {row.taught_in.join(", ")}</p>}
        </div>
      </div>
      <div className="space-y-3">
        <div className="text-sm text-slate-600">System signal ({row.graded_share !== undefined ? "graded work" : "mentions"}): <StatusTag s={row.status} /></div>
        <div>
          <label className="label" htmlFor={`${id}-fs`}>Your classification</label>
          <select id={`${id}-fs`} className="input" value={fs} onChange={(e) => setFs(e.target.value)}>
            {Object.keys(statuses).map((k) => <option key={k} value={k}>{FACULTY_LABEL[k] ?? k}{k === IMPLIED[row.status] ? " (agrees with system)" : ""}</option>)}
          </select>
          <p className="mt-1 text-xs text-slate-500">{statuses[fs]}</p>
        </div>
        <div>
          <label className="label" htmlFor={`${id}-why`}>Rationale{needsWhy ? " (required)" : " (optional)"}</label>
          <textarea id={`${id}-why`} className="input min-h-[70px]" value={rationale} onChange={(e) => setRationale(e.target.value)}
            placeholder={needsWhy ? "e.g. Mentioned in the reading list only; no assignment requires it." : "Evidence you checked (assignment, rubric, lab)…"} />
        </div>
        <div className="grid gap-2 sm:grid-cols-[170px_1fr]">
          <div>
            <label className="label" htmlFor={`${id}-act`}>Follow-up</label>
            <select id={`${id}-act`} className="input" value={action} onChange={(e) => setAction(e.target.value as Review["action"])}>
              {Object.entries(ACTION_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </div>
          <div>
            <label className="label" htmlFor={`${id}-note`}>What will change</label>
            <input id={`${id}-note`} className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Add a graded SQL lab in week 4" disabled={action === "none"} />
          </div>
        </div>
        {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
        <div className="flex flex-wrap items-center gap-2">
          <button className="btn-primary btn-sm" onClick={save} disabled={busy || (needsWhy && rationale.trim().length < 10)}>
            {corrected ? "Save correction" : "Confirm"}</button>
          {rv && <button className="btn-ghost btn-sm" onClick={clear} disabled={busy}>Clear review</button>}
          {needsWhy && rationale.trim().length < 10 && <span className="text-xs text-slate-500">Add a rationale to save.</span>}
          {rv && <span className="text-xs text-slate-500">Last saved by {rv.reviewer ?? "—"}, {new Date(rv.updated_at).toLocaleString()}{rv.carried_from ? " · carried over from the previous analysis" : ""}</span>}
        </div>
      </div>
    </div>
  );
}

const DECISION_HELP: Record<DecisionKind, string> = {
  add_here: "Students should practice this skill in this course. You can generate a CometForge draft for all accepted additions.",
  covered_elsewhere: "Another course in the program already teaches and assesses it.",
  defer: "Worth doing, but not in this revision.",
  out_of_scope: "Not this course's job, even though employers ask for it.",
};

function DecisionEditor({ analysisId, syllabusId, row, current, options, onSaved }: {
  analysisId: string; syllabusId: string; row: EvidenceRow; current?: Decision; options: Record<string, string>; onSaved: (d: Decision) => void;
}) {
  const [kind, setKind] = useState<DecisionKind>(current?.decision ?? "add_here");
  const [why, setWhy] = useState(current?.rationale ?? "");
  const [codes, setCodes] = useState((current?.covered_in ?? row.taught_in ?? []).join(", "));
  const [term, setTerm] = useState(current?.revisit_term ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const id = `dec-${row.skill_id}`;
  const save = async () => {
    setBusy(true); setErr(null);
    try {
      onSaved(await api.put<Decision>(`/gap/analyses/${analysisId}/decisions/${row.skill_id}`, {
        decision: kind, rationale: why, covered_in: codes.split(",").map((c) => c.trim()).filter(Boolean), revisit_term: term }));
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const e = current?.evidence;
  return (
    <div className="border-t border-violet-100 bg-violet-50/40 px-4 py-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 font-semibold text-slate-800"><Gavel className="h-4 w-4 text-violet-700" aria-hidden />Course decision</div>
        <Link to={`/gap/course/${syllabusId}?tab=decisions`} className="text-xs font-semibold text-comet-700 hover:underline">All decisions for this course →</Link>
      </div>
      <fieldset>
        <legend className="sr-only">What should happen with {row.name}?</legend>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {(Object.keys(options) as DecisionKind[]).map((k) => (
            <label key={k} className={`cursor-pointer rounded-lg border p-2.5 text-sm ${kind === k ? "border-violet-500 bg-white ring-1 ring-violet-500" : "border-slate-200 bg-white hover:border-slate-300"}`}>
              <span className="flex items-center gap-2 font-semibold text-slate-800"><input type="radio" name={id} checked={kind === k} onChange={() => setKind(k)} />{options[k]}</span>
              <span className="mt-1 block text-xs text-slate-600">{DECISION_HELP[k]}</span>
            </label>))}
        </div>
      </fieldset>
      <div className="mt-3 grid gap-3 lg:grid-cols-[1fr_280px]">
        <div>
          <label className="label" htmlFor={`${id}-why`}>Rationale (required)</label>
          <textarea id={`${id}-why`} className="input min-h-[64px]" value={why} onChange={(ev) => setWhy(ev.target.value)}
            placeholder="e.g. Every analyst posting asks for it and no other required course has students use it." />
        </div>
        <div>
          {kind === "covered_elsewhere" && <><label className="label" htmlFor={`${id}-codes`}>Covered in (course codes)</label>
            <input id={`${id}-codes`} className="input" value={codes} onChange={(ev) => setCodes(ev.target.value)} placeholder="BUAN 6320, MIS 6326" /></>}
          {kind === "defer" && <><label className="label" htmlFor={`${id}-term`}>Revisit in</label>
            <input id={`${id}-term`} className="input" value={term} onChange={(ev) => setTerm(ev.target.value)} placeholder="Fall 2027" /></>}
        </div>
      </div>
      {err && <p role="alert" className="mt-2 text-sm text-red-700">{err}</p>}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button className="btn-primary btn-sm" onClick={save} disabled={busy || why.trim().length < 10}>{current ? "Record new decision" : "Record decision"}</button>
        {current && <span className="text-xs text-slate-600">
          Current: <b>{current.decision_label}</b> by {current.reviewer ?? "—"}, {new Date(current.decided_at).toLocaleDateString()} · {DECISION_STATUS[current.status]}
          {e && <> · based on syllabus v{e.syllabus_version ?? "?"}, sample “{e.sample_name}”, catalog {e.catalog_year ?? "n/a"}, scoring {e.scoring_version ?? "n/a"}</>}
          {current.forge_draft_id && <> · <Link className="font-semibold text-comet-700 hover:underline" to={`/gap/course/${syllabusId}?tab=proposed`}>view proposed change</Link></>}
        </span>}
      </div>
      {current && <p className="mt-1 text-xs text-slate-500">Recording a new decision keeps this one in the course history.</p>}
    </div>
  );
}
