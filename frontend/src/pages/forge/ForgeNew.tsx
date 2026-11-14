import { BookOpen, Loader2, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Badge, Card, Empty, ErrorBox, Field, PageHeader, Spinner } from "../../components/ui";
import { api } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { PRIORITY_COLOR, StatusTag, type Status } from "../../lib/viz";

interface Syl { id: string; title: string; code: string | null; latest: { id: string; score: number; target: string } | null }
interface Gap { name: string; category: string; demand: number; priority: string; status: Status; taught_in: string[] }

export default function ForgeNew() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const syllabi = useApi<Syl[]>("/gap/syllabi");
  const opts = useApi<{ frameworks: string[]; program_goals: string[] }>("/forge/options");
  const [aid, setAid] = useState(params.get("analysis") ?? "");
  const analysis = useApi<{ score: number; target: string; gaps: Gap[]; syllabus: { title: string } }>(aid ? `/gap/analyses/${aid}` : null);
  const [focus, setFocus] = useState<string[]>([]);
  const [weeks, setWeeks] = useState(15);
  const [framework, setFramework] = useState("AACSB");
  const [goals, setGoals] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { if (!aid && syllabi.data?.length) setAid(syllabi.data.find((s) => s.latest)?.latest?.id ?? ""); }, [syllabi.data, aid]);
  useEffect(() => { if (analysis.data) setFocus(analysis.data.gaps.filter((g) => g.priority === "critical" || g.priority === "high").slice(0, 6).map((g) => g.name)); }, [analysis.data]);
  useEffect(() => { if (opts.data && !goals) setGoals(opts.data.program_goals.join("\n")); }, [opts.data, goals]);

  const toggle = (n: string) => setFocus((f) => (f.includes(n) ? f.filter((x) => x !== n) : [...f, n]));
  const go = async () => {
    setBusy(true); setErr(null);
    try {
      const d = await api.post<{ id: string }>("/forge/drafts", { analysis_id: aid, focus_skills: focus, weeks, framework, program_goals: goals.split("\n") });
      nav(`/forge/${d.id}`);
    } catch (e) { setErr((e as Error).message); setBusy(false); }
  };

  if (syllabi.loading) return <Spinner />;
  if (!syllabi.data?.some((s) => s.latest)) return <Empty icon={<BookOpen className="h-8 w-8" />} title="Run a CometGap analysis first">CometForge builds on a gap report.<div className="mt-4"><Link to="/gap/new" className="btn-primary">Analyze a syllabus</Link></div></Empty>;

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <PageHeader icon={<BookOpen className="h-5 w-5" />} accent="flame" title="New syllabus draft" subtitle="Turn gap analysis into an updated, future-ready syllabus" />
      <ErrorBox error={err} />
      <Card title="1 · Source gap report">
        <select className="input" value={aid} onChange={(e) => setAid(e.target.value)} aria-label="Gap report">
          {syllabi.data.filter((s) => s.latest).map((s) => <option key={s.id} value={s.latest!.id}>{s.code} {s.title} — {Math.round(s.latest!.score)}% vs {s.latest!.target}</option>)}
        </select>
      </Card>
      <Card title={`2 · Gaps to close (${focus.length} selected)`}>
        {analysis.loading || !analysis.data ? <Spinner /> : (
          <div className="grid gap-2 md:grid-cols-2">
            {analysis.data.gaps.slice(0, 16).map((g) => (
              <label key={g.name} className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-sm ${focus.includes(g.name) ? "border-flame-400 bg-flame-50" : "border-slate-200"}`}>
                <input type="checkbox" className="mt-1 accent-flame-500" checked={focus.includes(g.name)} onChange={() => toggle(g.name)} />
                <div className="flex-1">
                  <div className="flex flex-wrap items-center gap-2 font-semibold text-slate-800">{g.name}<Badge color={PRIORITY_COLOR[g.priority]}>{g.priority}</Badge><StatusTag s={g.status} /></div>
                  <div className="text-xs text-slate-500">{Math.round(g.demand * 100)}% of postings{g.taught_in.length ? ` · also in ${g.taught_in.join(", ")}` : ""}</div>
                </div>
              </label>))}
          </div>)}
      </Card>
      <Card title="3 · Course design options">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Term length (weeks)"><input type="number" min={8} max={18} className="input" value={weeks} onChange={(e) => setWeeks(+e.target.value)} /></Field>
          <Field label="Accreditation framework"><select className="input" value={framework} onChange={(e) => setFramework(e.target.value)}>
            {opts.data?.frameworks.map((f) => <option key={f}>{f}</option>)}</select></Field>
          <div className="md:col-span-2"><Field label="Program goals (one per line)"><textarea className="input h-28" value={goals} onChange={(e) => setGoals(e.target.value)} /></Field></div>
        </div>
      </Card>
      <button className="btn-accent w-full py-3" onClick={go} disabled={busy || !aid}>
        {busy ? <><Loader2 className="h-4 w-4 animate-spin" />Generating syllabus…</> : <><Sparkles className="h-4 w-4" />Generate updated syllabus</>}</button>
    </div>
  );
}
