import { Check, CheckCircle2, Download, FileText, GitPullRequest, MessageSquarePlus, PencilLine, Send, XCircle } from "lucide-react";
import { Fragment, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Badge, Card, ErrorBox, Field, Modal, PageHeader, Spinner, Tabs } from "../../components/ui";
import { api, download, waitForTask } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { PSTATUS, type ProposalBrief } from "./CurriculumHome";

interface Row { type: "equal" | "insert" | "delete" | "replace"; l: number | null; left: string | null; r: number | null; right: string | null }
interface Comment { id: string; author: string | null; author_id: string | null; anchor: string | null; anchor_text: string | null; revision: number; body: string; resolved: boolean; created_at: string }
interface Review { id: string; reviewer: string | null; vote: "approve" | "request_changes"; body: string | null; revision: number; created_at: string; current: boolean }
interface Full extends ProposalBrief {
  summary: string; base_version: { id: string; version: number; semester: string | null } | null; forge_draft_id: string | null;
  proposed_text: string; diff: Row[]; comments: Comment[]; reviews: Review[]; can_edit: boolean; can_review: boolean; adopted_version_id: string | null;
  evidence: { current_score: number | null; projected_score: number | null; score_basis: string; sample: { name: string; total?: number; date_from?: string; date_to?: string };
    decisions: { id: string; skill: string; label: string; rationale: string; reviewer: string | null; decided_at: string; covered_in: string[]; revisit_term: string | null; postings_requesting: number | null; postings_in_sample: number | null; syllabus_version: number | null }[] };
}
interface Form {
  note: string; course: { code: string; title: string; credits: number | null; catalog_year: string | null; programs: string[] };
  change_type: string; summary: string; justification: string[]; outcomes_current: string[]; outcomes_proposed: string[]; assessments_proposed: string[];
  other_courses: string[]; evidence: Record<string, string | number | null>; approvals: { reviewer: string; vote: string; date: string; comment: string }[]; required_approvals: number;
}

export default function Proposal() {
  const { id } = useParams();
  const nav = useNavigate();
  const { data: p, loading, error, setData, reload } = useApi<Full>(`/curriculum/proposals/${id}`);
  const [tab, setTab] = useState<"changes" | "evidence" | "conversation" | "form">("changes");
  const [editing, setEditing] = useState(false);
  const [adopting, setAdopting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (loading && !p) return <Spinner />;
  if (error || !p) return <ErrorBox error={error ?? "Not found"} />;
  const act = async (path: string, body?: unknown) => {
    setErr(null);
    try { setData({ ...p, ...(await api.post<Full>(`/curriculum/proposals/${p.id}/${path}`, body ?? {})) }); } catch (e) { setErr((e as Error).message); }
  };
  const st = PSTATUS[p.status];
  const file = `change-request-${p.syllabus?.code?.replace(/\s+/g, "_")}-${p.number}`;
  return (
    <div className="space-y-5">
      <PageHeader icon={<GitPullRequest className="h-5 w-5" />} title={`${p.title}`}
        subtitle={`Proposal #${p.number} · ${p.syllabus?.code} ${p.syllabus?.title} · by ${p.author ?? "—"} · revision ${p.revision}`}
        actions={<>
          <Badge color={st.color}>{st.label}</Badge>
          {p.can_edit && ["draft", "changes_requested"].includes(p.status) && <button className="btn-ghost btn-sm" onClick={() => setEditing(true)}><PencilLine className="h-4 w-4" />Edit</button>}
          {p.can_edit && ["draft", "changes_requested"].includes(p.status) && <button className="btn-primary btn-sm" onClick={() => act("submit")}><Send className="h-4 w-4" />{p.status === "draft" ? "Submit for review" : "Resubmit (new revision)"}</button>}
          {p.can_edit && p.status === "approved" && <button className="btn-accent btn-sm" onClick={() => setAdopting(true)}><CheckCircle2 className="h-4 w-4" />Adopt as next syllabus version</button>}
          {p.can_edit && !["adopted", "withdrawn"].includes(p.status) && <button className="btn-ghost btn-sm" onClick={() => confirm("Withdraw this proposal?") && act("withdraw")}>Withdraw</button>}
        </>} />
      {err && <p role="alert" className="rounded bg-red-50 p-2 text-sm text-red-800">{err}</p>}
      <div className="grid gap-5 xl:grid-cols-[1fr_300px]">
        <div className="min-w-0 space-y-4">
          <Tabs value={tab} onChange={setTab} tabs={[{ id: "changes", label: "Changes" }, { id: "evidence", label: "Evidence" },
            { id: "conversation", label: `Conversation (${p.comments.length + p.reviews.length})` }, { id: "form", label: "Change request form" }]} />
          {tab === "changes" && <Diff p={p} onUpdate={(n) => setData({ ...p, ...n })} />}
          {tab === "evidence" && <Evidence p={p} />}
          {tab === "conversation" && <Conversation p={p} onUpdate={(n) => setData({ ...p, ...n })} />}
          {tab === "form" && <ChangeForm id={p.id} />}
        </div>
        <aside className="space-y-4">
          <Card title="Approvals">
            <div className="text-2xl font-bold text-slate-800">{p.tally.approvals}<span className="text-base font-normal text-slate-600"> / {p.tally.required} required</span></div>
            {p.tally.changes_requested > 0 && <p className="text-sm text-amber-800">{p.tally.changes_requested} reviewer(s) requested changes</p>}
            <ul className="mt-3 space-y-1.5 text-sm">{p.reviews.filter((r) => r.current).map((r) => (
              <li key={r.id} className="flex items-center gap-2">{r.vote === "approve" ? <Check className="h-4 w-4 text-green-700" aria-hidden /> : <XCircle className="h-4 w-4 text-amber-700" aria-hidden />}
                {r.reviewer ?? "Former faculty member"}<span className="text-xs text-slate-500">{r.vote === "approve" ? "approved" : "requested changes"}</span></li>))}</ul>
            <p className="mt-2 text-xs text-slate-500">Only votes on the current revision count. The author can't approve their own proposal.</p>
          </Card>
          <Card title="Details">
            <dl className="space-y-1.5 text-sm">
              <div><dt className="text-xs text-slate-500">Based on</dt><dd>syllabus v{p.base_version?.version} {p.base_version?.semester ?? ""}</dd></div>
              <div><dt className="text-xs text-slate-500">Effective term</dt><dd>{p.effective_term ?? <span className="text-amber-800">not set</span>}</dd></div>
              <div><dt className="text-xs text-slate-500">Mention-based coverage</dt><dd>{p.evidence.current_score ?? "—"}% → projected {p.evidence.projected_score ?? "—"}%</dd></div>
              <div><dt className="text-xs text-slate-500">Open comments</dt><dd>{p.open_comments}</dd></div>
            </dl>
            {p.syllabus && <Link className="mt-2 inline-block text-sm font-semibold text-comet-700 hover:underline" to={`/gap/course/${p.syllabus.id}`}>Course history →</Link>}
          </Card>
          <Card title="Change request">
            <div className="flex flex-wrap gap-2">
              <button className="btn-ghost btn-sm" onClick={() => download(`/curriculum/proposals/${p.id}/change-request.pdf`, `${file}.pdf`)}><Download className="h-4 w-4" />PDF</button>
              <button className="btn-ghost btn-sm" onClick={() => download(`/curriculum/proposals/${p.id}/change-request.docx`, `${file}.docx`)}><FileText className="h-4 w-4" />Word</button>
            </div>
            {p.status !== "approved" && p.status !== "adopted" && <p className="mt-2 text-xs text-slate-500">Draft form: approvals are still pending.</p>}
          </Card>
        </aside>
      </div>
      {editing && <EditModal p={p} onClose={() => setEditing(false)} onSaved={(n) => { setData({ ...p, ...n }); setEditing(false); }} />}
      <Modal open={adopting} onClose={() => setAdopting(false)} title="Adopt as the next syllabus version">
        <AdoptForm p={p} onDone={async () => { setAdopting(false); reload(); }} onGo={(sid) => nav(`/gap/course/${sid}`)} />
      </Modal>
    </div>
  );
}

// ── Side-by-side diff with line comments ───────────────────────────────────────
function Diff({ p, onUpdate }: { p: Full; onUpdate: (n: Full) => void }) {
  const [open, setOpen] = useState<Set<number>>(new Set());
  const [composer, setComposer] = useState<string | null>(null);
  const byAnchor = new Map<string, Comment[]>();
  p.comments.forEach((c) => c.anchor && byAnchor.set(c.anchor, [...(byAnchor.get(c.anchor) ?? []), c]));
  // collapse long unchanged runs, keeping 3 lines of context around changes and comments
  const keep = p.diff.map((r, i) => r.type !== "equal" || byAnchor.has(`L${r.l}`) || byAnchor.has(`R${r.r}`) ||
    p.diff.slice(Math.max(0, i - 3), i + 4).some((x) => x.type !== "equal"));
  const blocks: ({ kind: "row"; i: number } | { kind: "gap"; from: number; to: number })[] = [];
  p.diff.forEach((_, i) => {
    if (keep[i] || open.has(i)) blocks.push({ kind: "row", i });
    else if (blocks.at(-1)?.kind === "gap") (blocks.at(-1) as { to: number }).to = i;
    else blocks.push({ kind: "gap", from: i, to: i });
  });
  const changed = p.diff.filter((r) => r.type !== "equal").length;
  const cls = (t: Row["type"], side: "l" | "r") => t === "insert" && side === "r" ? "bg-green-50" : t === "delete" && side === "l" ? "bg-red-50"
    : t === "replace" ? (side === "l" ? "bg-red-50" : "bg-green-50") : "";
  return (
    <Card padded={false} title={<span className="text-sm">Syllabus v{p.base_version?.version} → proposed (revision {p.revision}) · {changed} changed line{changed === 1 ? "" : "s"}</span>}>
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Side-by-side changes">
        <table className="w-full table-fixed border-collapse font-mono text-xs">
          <colgroup><col className="w-10" /><col /><col className="w-10" /><col /></colgroup>
          <thead><tr className="bg-slate-50 font-sans text-[11px] uppercase text-slate-600"><th colSpan={2} className="px-2 py-1.5 text-left">Current syllabus</th><th colSpan={2} className="px-2 py-1.5 text-left">Proposed</th></tr></thead>
          <tbody>{blocks.map((b) => b.kind === "gap" ? (
            <tr key={`g${b.from}`}><td colSpan={4} className="bg-slate-50 px-2 py-1 text-center font-sans">
              <button className="text-xs font-semibold text-comet-700 hover:underline" onClick={() => setOpen(new Set([...open, ...Array.from({ length: b.to - b.from + 1 }, (_, k) => b.from + k)]))}>
                Show {b.to - b.from + 1} unchanged lines</button></td></tr>
          ) : (() => {
            const r = p.diff[b.i];
            const anchor = r.r ? `R${r.r}` : `L${r.l}`;
            const cs = [...(byAnchor.get(`L${r.l}`) ?? []), ...(r.r ? byAnchor.get(`R${r.r}`) ?? [] : [])];
            return (
              <Fragment key={b.i}>
                <tr className="group align-top">
                  <td className={`select-none px-1 text-right text-slate-500 ${cls(r.type, "l")}`}>{r.l ?? ""}</td>
                  <td className={`whitespace-pre-wrap break-words px-2 py-0.5 text-slate-800 ${cls(r.type, "l")}`}>{r.type !== "equal" && r.left !== null && <span className="mr-1 text-red-700" aria-label="removed">−</span>}{r.left ?? ""}</td>
                  <td className={`relative select-none px-1 text-right text-slate-500 ${cls(r.type, "r")}`}>
                    <button className="absolute -left-2 top-0 hidden rounded bg-comet-700 p-0.5 text-white group-hover:block focus:block" aria-label={`Comment on line ${anchor}`} onClick={() => setComposer(anchor)}><MessageSquarePlus className="h-3.5 w-3.5" /></button>
                    {r.r ?? ""}</td>
                  <td className={`whitespace-pre-wrap break-words px-2 py-0.5 text-slate-800 ${cls(r.type, "r")}`}>{r.type !== "equal" && r.right !== null && <span className="mr-1 text-green-700" aria-label="added">+</span>}{r.right ?? ""}</td>
                </tr>
                {(cs.length > 0 || composer === anchor) && <tr><td colSpan={4} className="bg-slate-50 px-3 py-2 font-sans">
                  {cs.map((c) => <CommentView key={c.id} p={p} c={c} onUpdate={onUpdate} />)}
                  {composer === anchor && <Composer p={p} anchor={anchor} onDone={(n) => { setComposer(null); if (n) onUpdate(n); }} />}
                </td></tr>}
              </Fragment>);
          })())}</tbody>
        </table>
      </div>
    </Card>
  );
}

function CommentView({ p, c, onUpdate }: { p: Full; c: Comment; onUpdate: (n: Full) => void }) {
  return (
    <div className={`mb-2 rounded border bg-white p-2 text-sm ${c.resolved ? "border-slate-200 opacity-60" : "border-slate-300"}`}>
      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600"><b className="text-slate-800">{c.author ?? "Former faculty member"}</b>
        {new Date(c.created_at).toLocaleString()} · revision {c.revision}{c.anchor && <> · on line {c.anchor}</>}
        <button className="ml-auto font-semibold text-comet-700 hover:underline" onClick={async () => onUpdate(await api.post<Full>(`/curriculum/proposals/${p.id}/comments/${c.id}/resolve`))}>{c.resolved ? "Reopen" : "Resolve"}</button></div>
      {c.anchor_text && <div className="mt-1 truncate rounded bg-slate-50 px-1 font-mono text-[11px] text-slate-600">{c.anchor_text}</div>}
      <p className="mt-1 text-slate-800">{c.body}</p>
    </div>
  );
}

function Composer({ p, anchor, onDone }: { p: Full; anchor: string | null; onDone: (n?: Full) => void }) {
  const [body, setBody] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const send = async () => {
    try { onDone(await api.post<Full>(`/curriculum/proposals/${p.id}/comments`, { body, anchor })); setBody(""); } catch (e) { setErr((e as Error).message); }
  };
  return (
    <div className="space-y-2">
      <label className="sr-only" htmlFor={`c-${anchor ?? "general"}`}>Comment</label>
      <textarea id={`c-${anchor ?? "general"}`} className="input min-h-[60px]" value={body} onChange={(e) => setBody(e.target.value)} placeholder={anchor ? `Comment on line ${anchor}` : "Add a comment"} />
      {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
      <div className="flex gap-2"><button className="btn-primary btn-sm" disabled={body.trim().length < 2} onClick={send}>Comment</button>
        {anchor && <button className="btn-ghost btn-sm" onClick={() => onDone()}>Cancel</button>}</div>
    </div>
  );
}

// ── Evidence ───────────────────────────────────────────────────────────────────
function Evidence({ p }: { p: Full }) {
  const e = p.evidence;
  return (
    <div className="space-y-4">
      <Card>
        <p className="text-sm text-slate-700">{p.summary || <span className="text-slate-500">No summary.</span>}</p>
        <p className="mt-3 text-sm text-slate-600">Mention-based coverage <b>{e.current_score ?? "—"}%</b> → projected <b>{e.projected_score ?? "—"}%</b> against
          {" "}{e.sample?.name}{e.sample?.total ? ` (${e.sample.total} postings, ${e.sample.date_from ?? "?"} to ${e.sample.date_to ?? "?"})` : ""}. <span className="text-xs">({e.score_basis})</span></p>
      </Card>
      <Card title="Faculty decisions behind this proposal" padded={false}>
        <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Decisions">
          <table className="table-base"><thead><tr><th>Skill</th><th>Decision</th><th>Rationale</th><th>Evidence</th><th>Decided</th></tr></thead>
            <tbody>{e.decisions.map((d) => (
              <tr key={d.id}><td className="font-medium">{d.skill}</td><td>{d.label}{d.covered_in.length ? ` (${d.covered_in.join(", ")})` : ""}{d.revisit_term ? ` (revisit ${d.revisit_term})` : ""}</td>
                <td className="max-w-sm text-sm">{d.rationale}</td>
                <td className="text-xs">{d.postings_requesting !== null ? `${d.postings_requesting} of ${d.postings_in_sample} postings` : "—"} · syllabus v{d.syllabus_version ?? "?"}</td>
                <td className="text-xs">{d.reviewer ?? "—"}<div className="text-slate-500">{new Date(d.decided_at).toLocaleDateString()}</div></td></tr>))}</tbody></table>
        </div>
      </Card>
    </div>
  );
}

// ── Conversation & reviews ─────────────────────────────────────────────────────
function Conversation({ p, onUpdate }: { p: Full; onUpdate: (n: Full) => void }) {
  const [vote, setVote] = useState<"approve" | "request_changes">("approve");
  const [body, setBody] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const items = [...p.comments.filter((c) => !c.anchor).map((c) => ({ t: c.created_at, c })), ...p.reviews.map((r) => ({ t: r.created_at, r }))]
    .sort((a, b) => a.t.localeCompare(b.t));
  const submit = async () => {
    setErr(null);
    try { onUpdate(await api.post<Full>(`/curriculum/proposals/${p.id}/reviews`, { vote, body })); setBody(""); } catch (e) { setErr((e as Error).message); }
  };
  return (
    <div className="space-y-4">
      <Card>
        {!items.length ? <p className="text-sm text-slate-500">No reviews or general comments yet. Line comments appear on the Changes tab.</p> : (
          <ol className="space-y-3">{items.map((x, i) => "r" in x && x.r ? (
            <li key={i} className={`rounded-lg border p-3 text-sm ${x.r.vote === "approve" ? "border-green-200 bg-green-50" : "border-amber-200 bg-amber-50"}`}>
              <div className="flex items-center gap-2 font-semibold">{x.r.vote === "approve" ? <Check className="h-4 w-4 text-green-700" aria-hidden /> : <XCircle className="h-4 w-4 text-amber-700" aria-hidden />}
                {x.r.reviewer ?? "Former faculty member"} {x.r.vote === "approve" ? "approved" : "requested changes"}
                <span className="text-xs font-normal text-slate-600">revision {x.r.revision}{!x.r.current && " (earlier revision)"} · {new Date(x.r.created_at).toLocaleString()}</span></div>
              {x.r.body && <p className="mt-1 text-slate-800">{x.r.body}</p>}
            </li>) : "c" in x && x.c ? <li key={i}><CommentView p={p} c={x.c} onUpdate={onUpdate} /></li> : null)}</ol>)}
      </Card>
      <Card title="Add a general comment"><Composer p={p} anchor={null} onDone={(n) => n && onUpdate(n)} /></Card>
      {p.can_review && ["in_review", "changes_requested", "approved"].includes(p.status) && (
        <Card title={`Review revision ${p.revision}`}>
          <fieldset className="flex flex-wrap gap-3"><legend className="sr-only">Your review</legend>
            <label className="inline-flex items-center gap-2 text-sm"><input type="radio" name="vote" checked={vote === "approve"} onChange={() => setVote("approve")} />Approve</label>
            <label className="inline-flex items-center gap-2 text-sm"><input type="radio" name="vote" checked={vote === "request_changes"} onChange={() => setVote("request_changes")} />Request changes</label>
          </fieldset>
          <Field label={vote === "request_changes" ? "What needs to change (required)" : "Comment (optional)"}>
            <textarea className="input min-h-[70px]" value={body} onChange={(e) => setBody(e.target.value)} /></Field>
          {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
          <button className="btn-primary btn-sm mt-2" onClick={submit}>Submit review</button>
        </Card>)}
    </div>
  );
}

function ChangeForm({ id }: { id: string }) {
  const { data: f, loading } = useApi<Form>(`/curriculum/proposals/${id}/change-request.json`);
  if (loading || !f) return <Spinner />;
  const List = ({ items }: { items: string[] }) => items.length ? <ul className="list-disc space-y-1 pl-5">{items.map((x, i) => <li key={i}>{x}</li>)}</ul> : <p className="text-slate-500">None</p>;
  return (
    <Card>
      <div className="space-y-4 text-sm">
        <p className="rounded bg-amber-50 p-2 text-xs text-amber-900">{f.note}</p>
        <table className="table-base"><tbody>
          {[["Course", `${f.course.code} ${f.course.title}`], ["Credit hours", f.course.credits ?? "—"], ["Catalog year", f.course.catalog_year ?? "—"], ["Programs", f.course.programs.join(", ") || "—"]].map(([a, b]) => (
            <tr key={String(a)}><th className="w-40 text-left">{a}</th><td>{b}</td></tr>))}</tbody></table>
        <div><h3 className="font-semibold text-slate-800">Type of change</h3><p>{f.change_type}</p></div>
        <div><h3 className="font-semibold text-slate-800">Summary</h3><p>{f.summary || "—"}</p></div>
        <div><h3 className="font-semibold text-slate-800">Justification</h3><List items={f.justification} /></div>
        <div className="grid gap-4 md:grid-cols-2">
          <div><h3 className="font-semibold text-slate-800">Current learning outcomes</h3><List items={f.outcomes_current} /></div>
          <div><h3 className="font-semibold text-slate-800">Proposed learning outcomes</h3><List items={f.outcomes_proposed} /></div>
        </div>
        <div><h3 className="font-semibold text-slate-800">Impact on other courses</h3><List items={f.other_courses} /></div>
        <div><h3 className="font-semibold text-slate-800">Approvals ({f.required_approvals} required)</h3><List items={f.approvals.map((a) => `${a.reviewer}: ${a.vote}, ${a.date}${a.comment ? ` — ${a.comment}` : ""}`)} /></div>
      </div>
    </Card>
  );
}

function EditModal({ p, onClose, onSaved }: { p: Full; onClose: () => void; onSaved: (n: Full) => void }) {
  const [f, setF] = useState({ title: p.title, summary: p.summary, effective_term: p.effective_term ?? "", proposed_text: p.proposed_text });
  const [err, setErr] = useState<string | null>(null);
  const save = async () => { try { onSaved(await api.put<Full>(`/curriculum/proposals/${p.id}`, f)); } catch (e) { setErr((e as Error).message); } };
  return (
    <Modal open onClose={onClose} title={`Edit proposal #${p.number}`} wide>
      <div className="space-y-3">
        <Field label="Title"><input className="input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
        <div className="grid gap-3 md:grid-cols-[1fr_200px]">
          <Field label="Summary"><textarea className="input min-h-[60px]" value={f.summary} onChange={(e) => setF({ ...f, summary: e.target.value })} /></Field>
          <Field label="Effective term"><input className="input" value={f.effective_term} onChange={(e) => setF({ ...f, effective_term: e.target.value })} placeholder="Fall 2027" /></Field>
        </div>
        <Field label="Proposed syllabus text" hint="This exact text is what reviewers approve and what becomes the next syllabus version.">
          <textarea className="input min-h-[320px] font-mono text-xs" value={f.proposed_text} onChange={(e) => setF({ ...f, proposed_text: e.target.value })} /></Field>
        {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
        <button className="btn-primary" onClick={save}>Save</button>
      </div>
    </Modal>
  );
}

function AdoptForm({ p, onDone, onGo }: { p: Full; onDone: () => void; onGo: (sid: string) => void }) {
  const [semester, setSemester] = useState(p.effective_term ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const go = async () => {
    setBusy(true); setErr(null);
    try { const r = await api.post<{ task_id: string }>(`/curriculum/proposals/${p.id}/adopt`, { semester }); await waitForTask(r.task_id); onDone(); if (p.syllabus) onGo(p.syllabus.id); }
    catch (e) { setErr((e as Error).message); setBusy(false); }
  };
  return (
    <div className="space-y-3 text-sm">
      <p>The approved text becomes syllabus version {(p.base_version?.version ?? 0) + 1} of {p.syllabus?.code}. It is analyzed against the same job sample, the accepted decisions are marked implemented, and the score change appears in Course history.</p>
      <Field label="Semester"><input className="input" value={semester} onChange={(e) => setSemester(e.target.value)} /></Field>
      {err && <p role="alert" className="text-red-700">{err}</p>}
      <button className="btn-accent w-full" disabled={busy || semester.trim().length < 4} onClick={go}>{busy ? "Adopting and analyzing…" : "Adopt"}</button>
    </div>
  );
}
