import { ExternalLink, Search } from "lucide-react";
import { useState } from "react";
import { Badge, Card, Modal, PageHeader, Spinner, Tabs } from "../components/ui";
import { useApi } from "../lib/hooks";

interface CourseBrief { id: string; code: string; title: string; credits: number }
interface Program { id: string; name: string; type: string; department: string; total_sch: number; is_stem: boolean; core_count: number; concentrations: { id: string; name: string }[] }
interface ProgramDetail extends Omit<Program, "concentrations" | "core_count"> {
  core_sch: number; elective_sch: number; catalog_url: string; prereq_notes: string;
  core: (CourseBrief & { or_group: number })[];
  concentrations: { id: string; name: string; required_sch: number; notes: string; courses: CourseBrief[] }[];
}
interface CourseDetail extends CourseBrief { description: string; prerequisites: (CourseBrief & { group: number })[]; unlocks: CourseBrief[]; skills: { id: number; name: string; category: string; weight: number }[] }
interface SkillRow { id: number; name: string; category: string; is_emerging: boolean; job_count: number }

export function CourseModal({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { data, loading } = useApi<CourseDetail>(id ? `/courses/${id}` : null);
  const groups = new Map<number, CourseBrief[]>();
  data?.prerequisites.forEach((p) => groups.set(p.group, [...(groups.get(p.group) ?? []), p]));
  return (
    <Modal open={!!id} onClose={onClose} title={data ? `${data.code} — ${data.title}` : "Course"} wide>
      {loading || !data ? <Spinner /> : (
        <div className="space-y-4 text-sm">
          <p className="text-slate-600">{data.description || "No catalog description."}</p>
          <div>
            <div className="label">Prerequisites</div>
            {groups.size === 0 ? <span className="text-slate-500">None</span> : (
              <div className="space-y-1">{[...groups.values()].map((g, i) => (
                <div key={i}>{i > 0 && <span className="mr-1 text-xs font-bold text-slate-400">AND</span>}
                  {g.map((c, j) => <span key={c.id}>{j > 0 && <span className="mx-1 text-xs font-bold text-flame-600">OR</span>}<Badge color="blue">{c.code}</Badge></span>)}
                </div>))}
              </div>
            )}
          </div>
          {data.unlocks.length > 0 && <div><div className="label">Unlocks</div><div className="flex flex-wrap gap-1">{data.unlocks.map((u) => <Badge key={u.id}>{u.code}</Badge>)}</div></div>}
          <div><div className="label">Skills taught (knowledge graph)</div>
            <div className="flex flex-wrap gap-1">{data.skills.length ? data.skills.map((s) => <Badge key={s.id} color={s.weight >= 1 ? "green" : "slate"} title={s.category}>{s.name}</Badge>) : <span className="text-slate-500">No mapped skills yet</span>}</div>
          </div>
        </div>
      )}
    </Modal>
  );
}

function ProgramView({ id, onCourse }: { id: string; onCourse: (id: string) => void }) {
  const { data, loading } = useApi<ProgramDetail>(`/programs/${id}`);
  if (loading || !data) return <Spinner />;
  const CourseChip = ({ c }: { c: CourseBrief }) => (
    <button onClick={() => onCourse(c.id)} className="rounded-md border border-slate-200 px-2 py-1 text-left text-xs hover:border-comet-400 hover:bg-comet-50">
      <span className="font-semibold text-comet-800">{c.code}</span> <span className="text-slate-600">{c.title}</span>
    </button>
  );
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 text-xs">
        <Badge color="green">{data.type}</Badge><Badge>{data.total_sch} SCH</Badge>{data.is_stem && <Badge color="blue">STEM</Badge>}
        {data.catalog_url && <a href={data.catalog_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-semibold text-flame-600">Catalog <ExternalLink className="h-3 w-3" /></a>}
      </div>
      {data.prereq_notes && <p className="text-xs text-slate-500"><b>Program prerequisites:</b> {data.prereq_notes}</p>}
      <div><div className="label">Core ({data.core_sch} SCH)</div>
        <div className="flex flex-wrap gap-2">{data.core.map((c) => <div key={c.id} className="flex items-center gap-1">{c.or_group > 0 && <Badge color="orange">OR {c.or_group}</Badge>}<CourseChip c={c} /></div>)}</div>
      </div>
      {data.concentrations.map((cn) => (
        <div key={cn.id}><div className="label">{cn.name}{cn.required_sch > 0 ? ` · ${cn.required_sch} SCH` : ""}</div>
          <div className="flex flex-wrap gap-2">{cn.courses.map((c) => <CourseChip key={c.id} c={c} />)}</div>
        </div>
      ))}
    </div>
  );
}

export default function Catalog() {
  const [tab, setTab] = useState<"programs" | "courses" | "skills">("programs");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<string | null>(null);
  const [course, setCourse] = useState<string | null>(null);
  const programs = useApi<Program[]>("/programs");
  const courses = useApi<(CourseBrief & { subject: string })[]>(`/courses?limit=500&q=${encodeURIComponent(q)}`);
  const skills = useApi<SkillRow[]>("/skills");

  return (
    <div>
      <PageHeader title="Knowledge Graph" subtitle="Programs, courses, prerequisites and skills shared by every module" />
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "programs", label: "Programs" }, { id: "courses", label: "Courses" }, { id: "skills", label: "Skills" }]} />
      {tab === "programs" && (
        <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
          <Card padded={false} className="max-h-[70vh] overflow-y-auto">
            {programs.loading ? <Spinner /> : programs.data?.map((p) => (
              <button key={p.id} onClick={() => setSel(p.id)} className={`block w-full border-b border-slate-100 px-4 py-3 text-left text-sm hover:bg-slate-50 ${sel === p.id ? "bg-comet-50" : ""}`}>
                <div className="font-semibold text-slate-800">{p.name}</div>
                <div className="text-xs text-slate-500">{p.type} · {p.department} · {p.total_sch} SCH</div>
              </button>
            ))}
          </Card>
          <Card title={programs.data?.find((p) => p.id === sel)?.name ?? "Select a program"}>
            {sel ? <ProgramView id={sel} onCourse={setCourse} /> : <p className="text-sm text-slate-500">Choose a program to see its core, OR-groups and concentrations.</p>}
          </Card>
        </div>
      )}
      {tab === "courses" && (
        <Card padded={false}>
          <div className="relative border-b border-slate-100 p-3"><Search className="absolute left-6 top-5 h-4 w-4 text-slate-400" />
            <input className="input pl-9" placeholder="Search by code or title…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search courses" /></div>
          <div className="max-h-[65vh] overflow-y-auto">
            <table className="table-base"><thead><tr><th>Code</th><th>Title</th><th>Credits</th></tr></thead>
              <tbody>{courses.data?.map((c) => (
                <tr key={c.id} className="cursor-pointer hover:bg-slate-50" onClick={() => setCourse(c.id)}>
                  <td className="font-semibold text-comet-800">{c.code}</td><td>{c.title}</td><td>{c.credits}</td></tr>))}
              </tbody></table>
          </div>
        </Card>
      )}
      {tab === "skills" && (
        <Card padded={false}>
          <table className="table-base"><thead><tr><th>Skill</th><th>Category</th><th>Open jobs requiring it</th></tr></thead>
            <tbody>{skills.data?.slice().sort((a, b) => b.job_count - a.job_count).map((s) => (
              <tr key={s.id}><td className="font-medium">{s.name} {s.is_emerging && <Badge color="orange">Emerging</Badge>}</td><td className="text-slate-500">{s.category}</td><td>{s.job_count}</td></tr>))}
            </tbody></table>
        </Card>
      )}
      <CourseModal id={course} onClose={() => setCourse(null)} />
    </div>
  );
}
