import { Briefcase, GraduationCap, Library, Sparkles, X } from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Badge, Spinner } from "../components/ui";
import { useAuth } from "../lib/auth";
import { useApi } from "../lib/hooks";
import { CourseModal } from "./Catalog";

type NType = "job" | "skill" | "course" | "student";
interface GNode { id: string; type: NType; label: string; sub: string; ref: string | number | null; emerging?: boolean }
interface GEdge { source: string; target: string; weight: number; label?: string }
interface GraphData {
  scope: { role_family: string | null; program: string | null; jobs: number }; student_mode: "named" | "self" | "aggregate";
  nodes: GNode[]; edges: GEdge[]; role_families: string[]; programs: { id: string; name: string }[]; counts: Record<string, number>;
}
interface SkillDetail { name: string; category: string; is_emerging: boolean; job_count: number; share: number; required_share: number;
  by_role: { role: string; jobs: number }[]; sample_jobs: { id: string; title: string; company: string }[]; courses: { id: string; code: string; title: string; primary: boolean }[] }

// Categorical node-type colors (validated palette slots 1–4, fixed order). Labels are always visible text.
const TYPES: { type: NType; title: string; color: string; Icon: typeof Briefcase }[] = [
  { type: "job", title: "Jobs", color: "#2a78d6", Icon: Briefcase },
  { type: "skill", title: "Skills", color: "#eb6834", Icon: Sparkles },
  { type: "course", title: "Courses", color: "#1baf7a", Icon: Library },
  { type: "student", title: "Students", color: "#eda100", Icon: GraduationCap },
];
const ORDER: Record<NType, number> = { job: 0, skill: 1, course: 2, student: 3 };
const ROW = 40, HEAD = 44, NODE_H = 32;

export default function GraphMap() {
  const { user } = useAuth();
  const [fam, setFam] = useState("");
  const [prog, setProg] = useState("");
  const [nSkills, setNSkills] = useState(18);
  const { data, loading } = useApi<GraphData>(`/graph/map?role_family=${encodeURIComponent(fam)}&program_id=${prog}&max_skills=${nSkills}`);
  const [sel, setSel] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [course, setCourse] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(1000);
  useLayoutEffect(() => {
    if (!box.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, [data]);
  useEffect(() => setSel(null), [fam, prog]);
  useEffect(() => { const k = (e: KeyboardEvent) => e.key === "Escape" && setSel(null); window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k); }, []);

  const cols = useMemo(() => {
    const c: Record<NType, GNode[]> = { job: [], skill: [], course: [], student: [] };
    data?.nodes.forEach((n) => c[n.type].push(n));
    return c;
  }, [data]);
  const colW = width / 4, nodeW = Math.min(colW - 36, 230);
  const pos = useMemo(() => {
    const p: Record<string, { x: number; y: number }> = {};
    (Object.keys(cols) as NType[]).forEach((t) => cols[t].forEach((n, i) => { p[n.id] = { x: ORDER[t] * colW + (colW - nodeW) / 2, y: HEAD + i * ROW }; }));
    return p;
  }, [cols, colW, nodeW]);
  const height = HEAD + Math.max(1, ...Object.values(cols).map((c) => c.length)) * ROW + 8;

  // Focus = the full left-to-right chain through the active node (e.g. job → its skills → courses → students).
  const active = hover ?? sel;
  const focus = useMemo(() => {
    if (!active || !data) return null;
    const type = Object.fromEntries(data.nodes.map((n) => [n.id, n.type])) as Record<string, NType>;
    const out = new Map<string, GEdge[]>(), inn = new Map<string, GEdge[]>();
    data.edges.forEach((e) => { out.set(e.source, [...(out.get(e.source) ?? []), e]); inn.set(e.target, [...(inn.get(e.target) ?? []), e]); });
    const nodes = new Set([active]), edges = new Set<GEdge>();
    const walk = (start: string, dir: "out" | "in") => {
      const stack = [start];
      while (stack.length) {
        const cur = stack.pop()!;
        for (const e of (dir === "out" ? out : inn).get(cur) ?? []) {
          const nxt = dir === "out" ? e.target : e.source;
          if ((dir === "out" ? ORDER[type[nxt]] > ORDER[type[cur]] : ORDER[type[nxt]] < ORDER[type[cur]])) {
            edges.add(e);
            if (!nodes.has(nxt)) { nodes.add(nxt); stack.push(nxt); }
          }
        }
      }
    };
    walk(active, "out"); walk(active, "in");
    return { nodes, edges };
  }, [active, data]);

  const selNode = data?.nodes.find((n) => n.id === sel) ?? null;
  const skillDetail = useApi<SkillDetail>(selNode?.type === "skill" ? `/graph/skill/${selNode.ref}` : null);
  const connected = (t: NType) => (focus ? data!.nodes.filter((n) => n.type === t && focus.nodes.has(n.id) && n.id !== sel) : []);

  return (
    <div className="space-y-4">
      <div className="card flex flex-wrap items-end gap-3 p-4">
        <label className="block"><span className="label">Jobs</span>
          <select className="input w-60" value={fam} onChange={(e) => setFam(e.target.value)}><option value="">All role families</option>{data?.role_families.map((r) => <option key={r}>{r}</option>)}</select></label>
        <label className="block"><span className="label">Courses from</span>
          <select className="input w-80" value={prog} onChange={(e) => setProg(e.target.value)}><option value="">All programs</option>{data?.programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <label className="block"><span className="label">Top skills: {nSkills}</span>
          <input type="range" min={8} max={30} value={nSkills} onChange={(e) => setNSkills(+e.target.value)} className="w-40 accent-comet-600" /></label>
        <p className="ml-auto max-w-sm text-xs text-slate-500">Click any node to trace its chain: the jobs that need a skill, the courses that teach it, and the students who have it. Press Esc to clear.</p>
      </div>

      {loading || !data ? <Spinner label="Building the knowledge graph…" /> : (
        <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
          <div className="card overflow-x-auto p-3" tabIndex={0} role="region" aria-label="Knowledge graph map">
            <div ref={box} className="relative min-w-[700px]" style={{ height }}>
              {TYPES.map((t, i) => (
                <div key={t.type} className="absolute top-0 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-600" style={{ left: i * colW + (colW - nodeW) / 2, width: nodeW }}>
                  <span className="flex h-5 w-5 items-center justify-center rounded-full text-white" style={{ background: t.color }}><t.Icon className="h-3 w-3" aria-hidden /></span>
                  {t.title} <span className="font-normal text-slate-500">({data.counts[t.type + "s"] ?? cols[t.type].length})</span>
                </div>))}
              <svg className="pointer-events-none absolute inset-0" width={width} height={height} aria-hidden>
                {data.edges.map((e, i) => {
                  const a = pos[e.source], b = pos[e.target];
                  if (!a || !b) return null;
                  const x1 = a.x + nodeW, y1 = a.y + NODE_H / 2, x2 = b.x, y2 = b.y + NODE_H / 2, mx = (x1 + x2) / 2;
                  const on = focus?.edges.has(e);
                  return <path key={i} d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`} fill="none"
                    stroke={on ? "#0e4231" : "#94a3b8"} strokeOpacity={focus ? (on ? 0.85 : 0.05) : 0.18} strokeWidth={on ? 1.5 + Math.min(e.weight, 1.5) : 1} />;
                })}
              </svg>
              {data.nodes.map((n) => {
                const p = pos[n.id], t = TYPES[ORDER[n.type]];
                const dim = focus && !focus.nodes.has(n.id);
                return (
                  <button key={n.id} type="button" aria-pressed={sel === n.id} title={`${n.label}${n.sub ? " — " + n.sub : ""}`}
                    onClick={() => setSel(sel === n.id ? null : n.id)} onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)}
                    onFocus={() => setHover(n.id)} onBlur={() => setHover(null)}
                    className={`absolute flex items-center gap-2 rounded-lg border bg-white px-2 text-left text-xs shadow-sm transition-opacity focus:outline-none focus-visible:ring-2 focus-visible:ring-comet-500 ${sel === n.id ? "border-comet-700 ring-2 ring-comet-600/30" : "border-slate-200 hover:border-slate-400"}`}
                    style={{ left: p.x, top: p.y, width: nodeW, height: NODE_H, opacity: dim ? 0.25 : 1 }}>
                    <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: t.color }} aria-hidden />
                    <span className="min-w-0 flex-1 truncate"><span className="font-semibold text-slate-800">{n.label}</span>
                      {n.type === "course" && <span className="text-slate-500"> {n.sub}</span>}</span>
                    {n.emerging && <span className="text-[9px] font-bold text-flame-600">NEW</span>}
                  </button>);
              })}
            </div>
            <div className="mt-2 flex flex-wrap gap-4 px-1 text-[11px] text-slate-500">
              <span>Lines: jobs → skills they require (thicker = more postings) · skills → courses that teach them · skills/courses → students with evidence</span>
              {data.student_mode === "aggregate" && <span>Student names are hidden for faculty; counts only.</span>}
              {data.student_mode === "self" && <span>You see only yourself among students.</span>}
            </div>
          </div>

          <aside className="card h-fit p-4 text-sm xl:sticky xl:top-20" aria-live="polite">
            {!selNode ? (
              <div className="space-y-2 text-slate-600">
                <div className="font-semibold text-slate-800">Explore the feedback loop</div>
                <p>{data.scope.jobs} open postings · {data.counts.skills} skills · {data.counts.courses} courses · {data.counts.students} {data.student_mode === "aggregate" ? "student group" : "students"}.</p>
                <p>Try clicking <b>SQL</b> in Skills, or a role family in Jobs.</p>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <div><div className="text-xs font-semibold uppercase" style={{ color: TYPES[ORDER[selNode.type]].color }}>{TYPES[ORDER[selNode.type]].title.slice(0, -1)}</div>
                    <div className="text-base font-bold text-comet-900">{selNode.label}</div><div className="text-xs text-slate-500">{selNode.sub}</div></div>
                  <button className="rounded p-1 text-slate-500 hover:bg-slate-100" onClick={() => setSel(null)} aria-label="Clear selection"><X className="h-4 w-4" /></button>
                </div>
                {selNode.type === "skill" && (skillDetail.loading || !skillDetail.data ? <Spinner /> : (
                  <div className="space-y-2">
                    <div className="flex flex-wrap gap-1"><Badge color="blue">{skillDetail.data.share}% of open postings</Badge><Badge>{skillDetail.data.required_share}% list it as required</Badge>
                      {skillDetail.data.is_emerging && <Badge color="orange">Emerging</Badge>}</div>
                    <div className="text-xs text-slate-600">Most wanted by: {skillDetail.data.by_role.slice(0, 3).map((r) => `${r.role} (${r.jobs})`).join(", ")}</div>
                    <Section title="Taught in">{skillDetail.data.courses.length ? skillDetail.data.courses.map((c) => (
                      <button key={c.id} className="block text-left text-xs hover:underline" onClick={() => setCourse(c.id)}><b className="text-comet-800">{c.code}</b> {c.title}{!c.primary && <span className="text-slate-500"> (secondary topic)</span>}</button>))
                      : <span className="text-xs text-red-700">No course teaches this yet — a gap for CometGap / CometForge.</span>}</Section>
                  </div>))}
                {selNode.type === "course" && <button className="btn-ghost btn-sm" onClick={() => setCourse(String(selNode.ref))}>Course details & live sections</button>}
                {selNode.type === "job" && fam === "" && <button className="btn-ghost btn-sm" onClick={() => setFam(String(selNode.ref))}>Drill into {selNode.label} postings</button>}
                {selNode.type === "student" && user && (user.role === "admin" || user.role === "advisor") && selNode.ref && <Link className="btn-ghost btn-sm" to="/advising">Open in Advising</Link>}
                {selNode.type === "student" && user?.role === "employer" && <Link className="btn-ghost btn-sm" to="/match">Find in Talent search</Link>}
                {selNode.type === "student" && user?.role === "student" && <Link className="btn-ghost btn-sm" to="/match">My skills to learn next</Link>}
                {(["job", "skill", "course", "student"] as NType[]).filter((t) => t !== selNode.type).map((t) => {
                  const list = connected(t);
                  return list.length ? <Section key={t} title={`Connected ${TYPES[ORDER[t]].title.toLowerCase()} (${list.length})`}>
                    <div className="flex flex-wrap gap-1">{list.slice(0, 14).map((n) => <button key={n.id} onClick={() => setSel(n.id)} className="chip bg-slate-100 text-slate-700 hover:bg-slate-200">{n.label}</button>)}
                      {list.length > 14 && <span className="text-xs text-slate-500">+{list.length - 14} more</span>}</div></Section> : null;
                })}
              </div>
            )}
          </aside>
        </div>
      )}
      <CourseModal id={course} onClose={() => setCourse(null)} />
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <div><div className="label">{title}</div>{children}</div>;
}

