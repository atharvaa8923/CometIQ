import { AlertTriangle, Award, CheckCircle2, CircleDot, GraduationCap, Loader2, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";

export interface SkillHit { skill: string; category: string; importance: string; level: number; sources: string[]; learn_in?: string[] }
export interface MatchResult { score: number; base_score?: number; bonus?: number; bonus_items?: { title: string; points: number }[]; label: string; summary: string; matched: SkillHit[]; partial: SkillHit[]; missing: SkillHit[] }

export function FitBadge({ score, label }: { score: number; label: string }) {
  const tone = score >= 70 ? "bg-comet-700 text-white" : score >= 50 ? "bg-comet-100 text-comet-800" : score >= 30 ? "bg-amber-100 text-amber-800" : "bg-slate-100 text-slate-600";
  return (
    <div className={`flex w-20 shrink-0 flex-col items-center rounded-lg px-2 py-1.5 ${tone}`} title={`${label}: ${score}% weighted skill match`}>
      <span className="text-lg font-bold leading-none">{Math.round(score)}%</span>
      <span className="mt-0.5 text-[10px] font-semibold uppercase tracking-wide">{label}</span>
    </div>
  );
}

const Row = ({ s, kind, showLearn }: { s: SkillHit; kind: "matched" | "partial" | "missing"; showLearn?: boolean }) => {
  const Icon = kind === "matched" ? CheckCircle2 : kind === "partial" ? CircleDot : AlertTriangle;
  const color = kind === "matched" ? "#0ca30c" : kind === "partial" ? "#d97706" : "#d03b3b";
  return (
    <li className="flex items-start gap-2 text-sm">
      <Icon className="mt-0.5 h-4 w-4 shrink-0" style={{ color }} aria-label={kind} />
      <div className="min-w-0 flex-1">
        <span className="font-medium text-slate-800">{s.skill}</span>
        <span className={`ml-1.5 text-[11px] font-semibold uppercase ${s.importance === "required" ? "text-slate-600" : "text-slate-500"}`}>{s.importance}</span>
        {s.sources.length > 0 && <div className="text-xs text-slate-500">Evidence: {s.sources.join(", ")}{kind === "partial" ? ` · level ${Math.round(s.level * 100)}%` : ""}</div>}
        {showLearn && kind === "missing" && (s.learn_in?.length ? (
          <div className="text-xs text-comet-700"><GraduationCap className="mr-1 inline h-3.5 w-3.5" />Learn it in {s.learn_in.join(", ")} · <Link to="/path" className="font-semibold underline">add to my plan</Link></div>
        ) : <div className="text-xs text-slate-500">No catalog course teaches this yet</div>)}
      </div>
    </li>
  );
};

/** Transparent fit analysis: every point of the score is visible here. */
export function Breakdown({ m, showLearn }: { m: MatchResult; showLearn?: boolean }) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">{m.summary}. Score = required skills ×1.0 + preferred ×0.5, weighted by evidence level (resume, completed course or verified certificate = full; in-progress, pending or secondary course topic = partial).</p>
      {!!m.bonus && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg bg-flame-50 px-3 py-2 text-sm text-flame-900">
          <Award className="h-4 w-4 text-flame-500" aria-hidden />
          <span>Base {Math.round(m.base_score ?? 0)}% <b>+ {m.bonus} bonus</b> for verified {m.bonus_items?.map((b) => `${b.title} (+${b.points})`).join(", ")} = <b>{Math.round(m.score)}%</b></span>
        </div>)}
      <div className="grid gap-4 md:grid-cols-3">
        {([["matched", "You have", m.matched], ["partial", "Partially", m.partial], ["missing", "Missing", m.missing]] as const).map(([k, title, list]) => (
          <div key={k}>
            <div className="label">{title} ({list.length})</div>
            {list.length ? <ul className="space-y-2">{list.map((s) => <Row key={s.skill} s={s} kind={k} showLearn={showLearn} />)}</ul> : <div className="text-sm text-slate-500">—</div>}
          </div>))}
      </div>
    </div>
  );
}

interface Explanation { headline: string; strengths: string[]; gaps: string[]; next_steps: string[]; engine: string }

/** "Explain this match" — Claude when configured, otherwise the built-in explainer. */
export function AiExplain({ path }: { path: string }) {
  const [x, setX] = useState<Explanation | null>(null);
  const [busy, setBusy] = useState(false);
  if (!x) return (
    <button className="btn-ghost btn-sm" disabled={busy} onClick={async () => { setBusy(true); try { setX(await api.post<Explanation>(path)); } finally { setBusy(false); } }}>
      {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4 text-flame-500" />}Explain this match</button>);
  const List = ({ title, items }: { title: string; items: string[] }) => (
    <div><div className="label">{title}</div><ul className="list-disc space-y-1 pl-4 text-sm text-slate-700">{items.map((i) => <li key={i}>{i}</li>)}</ul></div>);
  return (
    <div className="rounded-xl border border-flame-200 bg-gradient-to-br from-flame-50 to-white p-4">
      <div className="mb-3 flex items-start gap-2 text-sm font-semibold text-slate-800"><Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-flame-500" />{x.headline}</div>
      <div className="grid gap-4 md:grid-cols-3"><List title="Strengths" items={x.strengths} /><List title="Gaps" items={x.gaps} /><List title="Next steps" items={x.next_steps} /></div>
      <div className="mt-2 text-right text-[11px] text-slate-500">{x.engine === "claude" ? "Written by Claude from the score breakdown" : "CometIQ built-in explainer"}</div>
    </div>
  );
}
