import { Award, Copy, Download, ExternalLink, GraduationCap, Send, Share2 } from "lucide-react";
import { useState } from "react";
import { Card, Empty, Spinner } from "../../components/ui";
import { api, download } from "../../lib/api";
import { useToast } from "../../lib/toast";
import { useApi } from "../../lib/hooks";

export interface BadgeT {
  id: string; skill: string; category: string; course_code: string; course_title: string | null; level: "practiced" | "mastered";
  term: string | null; issued_at: string; status: string; public?: boolean; public_token?: string; revoked_reason?: string | null;
  in_canvas?: boolean; canvas_error?: string | null;
  basis: { source: string; syllabus_semester?: string | null; syllabus_version?: number | null; confirmed_by?: string | null; confirmed_at?: string | null;
           completion_verified_by?: string | null; completion_verified_at?: string | null };
}

export function BadgeCard({ b, children }: { b: BadgeT; children?: React.ReactNode }) {
  return (
    <div className={`rounded-xl border p-4 ${b.status === "active" ? "border-comet-200 bg-gradient-to-br from-white to-comet-50" : "border-slate-200 bg-slate-50 opacity-70"}`}>
      <div className="flex items-start gap-3">
        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${b.level === "mastered" ? "bg-comet-700" : "bg-comet-500"} text-white`}><Award className="h-5 w-5" aria-hidden /></div>
        <div className="min-w-0">
          <div className="font-bold text-comet-900">{b.skill}</div>
          <div className="text-xs font-semibold uppercase tracking-wide text-comet-700">Faculty-verified · {b.level}</div>
          <div className="mt-1 text-sm text-slate-700">{b.course_code}{b.course_title ? ` ${b.course_title}` : ""}{b.term ? ` · ${b.term}` : ""}</div>
        </div>
      </div>
      <p className="mt-2 text-xs text-slate-600">
        {b.basis.source === "curriculum map" ? "Faculty set this course's level in the program curriculum map" : "Faculty confirmed students practice this skill in the course"}
        {b.basis.syllabus_semester ? ` (${b.basis.syllabus_semester} syllabus)` : ""}{b.basis.confirmed_by ? `: ${b.basis.confirmed_by}` : ""}.
        {b.basis.completion_verified_by ? ` Completion verified by ${b.basis.completion_verified_by}.` : ""}
      </p>
      {b.status !== "active" && <p className="mt-1 text-xs font-semibold text-red-700">Revoked{b.revoked_reason ? `: ${b.revoked_reason}` : ""}</p>}
      {children}
    </div>
  );
}

export default function Badges() {
  const { data, loading, setData, reload } = useApi<{ badges: BadgeT[]; pending: { course_id: string; course_code: string; course_title: string; skills: string[] }[];
    canvas_credentials?: boolean }>("/badges/mine");
  const [copied, setCopied] = useState<string | null>(null);
  const toast = useToast();
  const linkedin = async (b: BadgeT) => {
    const tab = window.open("", "_blank");   // opened now, while the click still counts, so pop-up blockers allow it
    try {
      const r = await api.get<{ linkedin_url: string | null }>(`/badges/${b.id}/openbadge`);
      if (r.linkedin_url && tab) { tab.opener = null; tab.location.href = r.linkedin_url; } else tab?.close();
    } catch (e) { tab?.close(); toast((e as Error).message, "error"); }
  };
  const sendToCanvas = async (b: BadgeT) => {
    try { await api.post(`/badges/${b.id}/send-to-canvas`); toast("Sent to Canvas Credentials"); reload(); }
    catch (e) { toast((e as Error).message, "error"); }
  };
  if (loading || !data) return <Spinner />;
  const toggle = async (b: BadgeT) => {
    const nb = await api.put<BadgeT>(`/badges/${b.id}/share`, { public: !b.public });
    setData({ ...data, badges: data.badges.map((x) => (x.id === b.id ? nb : x)) });
  };
  const link = (b: BadgeT) => `${window.location.origin}/badge/${b.public_token}`;
  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-comet-200 bg-comet-50 p-4 text-sm text-comet-900">
        <b>Faculty-verified skills.</b> You earn a badge when faculty have confirmed that a course has students practice a skill, and an advisor
        has verified that you completed the course. Employers see these as stronger evidence than a resume line, and you can share a verification link.
      </div>
      {!data.badges.length ? <Empty icon={<Award className="h-8 w-8" />} title="No badges yet">Add your completed UTD courses under “Courses & certifications”. Once an advisor verifies them, badges appear here.</Empty> : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{data.badges.map((b) => (
          <BadgeCard key={b.id} b={b}>
            {b.status === "active" && <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-comet-100 pt-3">
              <label className="inline-flex items-center gap-2 text-sm"><input type="checkbox" className="accent-comet-600" checked={!!b.public} onChange={() => toggle(b)} />Share a verification link</label>
              {b.public && <>
                <button className="btn-ghost btn-sm" onClick={() => { navigator.clipboard?.writeText(link(b)); setCopied(b.id); }}><Copy className="h-3.5 w-3.5" />{copied === b.id ? "Copied" : "Copy link"}</button>
                <a className="btn-ghost btn-sm" href={link(b)} target="_blank" rel="noreferrer"><ExternalLink className="h-3.5 w-3.5" />Open</a>
                <button className="btn-ghost btn-sm" onClick={() => linkedin(b)} aria-label={`Add to LinkedIn: ${b.skill}`}><Share2 className="h-3.5 w-3.5" aria-hidden />Add to LinkedIn</button>
                {data.canvas_credentials && (b.in_canvas
                  ? <span className="chip bg-green-50 text-green-800">In Canvas</span>
                  : <button className="btn-ghost btn-sm" onClick={() => sendToCanvas(b)} aria-label={`Send to Canvas: ${b.skill}`}><Send className="h-3.5 w-3.5" aria-hidden />Send to Canvas</button>)}</>}
              <button className="btn-ghost btn-sm" onClick={() => download(`/badges/${b.id}/openbadge.jwt`, `${b.skill.replace(/\s+/g, "_")}-${b.level}.jwt`)}
                aria-label={`Open Badge for ${b.skill} (download)`} title="Open Badges 3.0 credential, signed by the university (for digital wallets and badge platforms)">
                <Download className="h-3.5 w-3.5" aria-hidden />Open Badge</button>
              {b.canvas_error && <p className="w-full text-xs text-red-700">Canvas: {b.canvas_error}</p>}
            </div>}
          </BadgeCard>))}
        </div>)}
      {data.pending.length > 0 && (
        <Card title={<span className="flex items-center gap-2"><GraduationCap className="h-4 w-4 text-comet-700" />Badges waiting for verified completion</span>}>
          <ul className="space-y-2 text-sm">{data.pending.map((p) => (
            <li key={p.course_id}><b>{p.course_code} {p.course_title}</b>: {p.skills.join(", ")}. Submit the course with proof under “Courses & certifications” so an advisor can verify it.</li>))}</ul>
        </Card>)}
    </div>
  );
}
