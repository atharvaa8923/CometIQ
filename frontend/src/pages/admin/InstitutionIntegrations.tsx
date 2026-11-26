import { Award, BookOpen, Briefcase, CheckCircle2, KeyRound, Loader2, Send, ShieldCheck, Upload, XCircle } from "lucide-react";
import { useRef, useState } from "react";
import { Card } from "../../components/ui";
import { api, waitForTask } from "../../lib/api";
import { useToast } from "../../lib/toast";

export interface Institution {
  sso: { enabled: boolean; name: string; issuer: string | null; required: boolean; domains: string[]; auto_provision: boolean; redirect_uri: string; linked_accounts: number };
  canvas: { enabled: boolean; base_url: string | null; redirect_uri: string; connected_faculty: number; imported_courses: number };
  credentials: { enabled: boolean; base_url: string; auto_send: boolean; sent: number; waiting: number; errors: number };
  open_badges: { enabled: boolean; kid?: string; source?: string; detail?: string; jwks_url: string; issuer_url: string; linkedin_org_id: string | null };
  handshake: { feed: boolean; open_postings: number; closed_postings: number };
}

function OnOff({ on, label }: { on: boolean; label?: string }) {
  return on ? <span className="chip bg-green-50 text-green-800"><CheckCircle2 className="h-3.5 w-3.5 text-green-600" aria-hidden />{label ?? "On"}</span>
    : <span className="chip bg-slate-100 text-slate-600"><XCircle className="h-3.5 w-3.5" aria-hidden />{label ?? "Not configured"}</span>;
}

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return <div className="flex flex-wrap justify-between gap-2 border-b border-slate-100 py-1.5 last:border-0"><dt className="text-slate-500">{k}</dt><dd className="text-right text-slate-800">{children}</dd></div>;
}

const Code = ({ children }: { children: React.ReactNode }) => <code className="break-all rounded bg-slate-100 px-1 text-xs">{children}</code>;

/** Single sign-on, Canvas, Canvas Credentials, Open Badges and Handshake: status, setup values and actions. */
export default function InstitutionIntegrations({ data, reload }: { data: Institution; reload: () => void }) {
  const toast = useToast();
  const file = useRef<HTMLInputElement>(null);
  const [hs, setHs] = useState<{ busy: boolean; msg: string | null; error?: boolean }>({ busy: false, msg: null });
  const [sending, setSending] = useState(false);

  const uploadHandshake = async (e: React.FormEvent) => {
    e.preventDefault();
    const f = file.current?.files?.[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    setHs({ busy: true, msg: "Importing…" });
    try {
      const r = await api.post<Record<string, number>>("/admin/handshake/import", fd);
      setHs({ busy: false, msg: `${r.in_file} postings in the file: ${r.added} new, ${r.updated} updated, ${r.reopened} reopened, ${r.closed_missing} closed (no longer listed), ${r.expired} expired, ${r.skipped} rows skipped. ${r.open_now} Handshake postings open now.` });
      reload();
    } catch (x) { setHs({ busy: false, msg: (x as Error).message, error: true }); }
  };
  const sendAll = async () => {
    setSending(true);
    try {
      const t = await api.post<{ task_id: string }>("/badges/credentials/send");
      const r = await waitForTask(t.task_id) as Record<string, number>;
      toast(`Sent ${r.sent} badge${r.sent === 1 ? "" : "s"} to Canvas Credentials${r.failed ? `, ${r.failed} failed` : ""}`, r.failed ? "error" : undefined);
      reload();
    } catch (x) { toast((x as Error).message, "error"); } finally { setSending(false); }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title={<span className="flex items-center gap-2"><KeyRound className="h-4 w-4 text-flame-500" aria-hidden />Single sign-on</span>} actions={<OnOff on={data.sso.enabled} />}>
        <dl className="text-sm">
          {data.sso.enabled ? <>
            <Row k="Button">Sign in with {data.sso.name}</Row>
            <Row k="Identity provider"><Code>{data.sso.issuer}</Code></Row>
            <Row k="Email domains">{data.sso.domains.map((d) => "@" + d).join(", ")}</Row>
            <Row k="Passwords for these domains">{data.sso.required ? "Turned off (SSO required)" : "Still allowed"}</Row>
            <Row k="New accounts">{data.sso.auto_provision ? "Created on first sign-in" : "Only existing accounts"}</Row>
            <Row k="Linked accounts">{data.sso.linked_accounts}</Row>
          </> : <p className="text-slate-600">Let faculty, staff and students sign in with their NetID through Microsoft Entra ID or a Shibboleth identity provider (OpenID Connect).
            Register CometIQ with the university's identity team, then set <Code>SSO_ENABLED</Code>, <Code>SSO_ISSUER</Code>, <Code>SSO_CLIENT_ID</Code> and <Code>SSO_CLIENT_SECRET</Code>.</p>}
          <Row k="Redirect URI to register"><Code>{data.sso.redirect_uri}</Code></Row>
        </dl>
      </Card>

      <Card title={<span className="flex items-center gap-2"><BookOpen className="h-4 w-4 text-flame-500" aria-hidden />Canvas</span>} actions={<OnOff on={data.canvas.enabled} />}>
        <dl className="text-sm">
          {data.canvas.enabled ? <>
            <Row k="Canvas"><Code>{data.canvas.base_url}</Code></Row>
            <Row k="Faculty connected">{data.canvas.connected_faculty}</Row>
            <Row k="Courses imported">{data.canvas.imported_courses}</Row>
          </> : <p className="text-slate-600">Faculty import a course's syllabus page and graded assignments (with rubrics) straight from Canvas. A Canvas admin creates a developer key; set <Code>CANVAS_BASE_URL</Code>, <Code>CANVAS_CLIENT_ID</Code> and <Code>CANVAS_CLIENT_SECRET</Code>.</p>}
          <Row k="Redirect URI for the developer key"><Code>{data.canvas.redirect_uri}</Code></Row>
        </dl>
      </Card>

      <Card title={<span className="flex items-center gap-2"><Award className="h-4 w-4 text-flame-500" aria-hidden />Badges in Canvas Credentials</span>} actions={<OnOff on={data.credentials.enabled} />}>
        {data.credentials.enabled ? <div className="space-y-3 text-sm">
          <dl>
            <Row k="Sent">{data.credentials.sent}</Row>
            <Row k="Shared, not sent yet">{data.credentials.waiting}</Row>
            <Row k="Failed">{data.credentials.errors}</Row>
            <Row k="New shared badges">{data.credentials.auto_send ? "Sent automatically" : "Sent by an admin or the student"}</Row>
          </dl>
          <button className="btn-primary btn-sm" onClick={sendAll} disabled={sending || !data.credentials.waiting}>
            {sending ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Send className="h-4 w-4" aria-hidden />}Send {data.credentials.waiting} waiting badge{data.credentials.waiting === 1 ? "" : "s"}</button>
          <p className="text-xs text-slate-500">Only badges a student chose to share are sent. Revoking a badge in CometIQ revokes it in Canvas Credentials too.</p>
        </div> : <p className="text-sm text-slate-600">Send faculty-verified badges into students' Canvas Backpack. Set <Code>CREDENTIALS_TOKEN</Code> and <Code>CREDENTIALS_ISSUER_ID</Code> from the university's Canvas Credentials issuer.</p>}
      </Card>

      <Card title={<span className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-flame-500" aria-hidden />Open Badges 3.0 and LinkedIn</span>} actions={<OnOff on={data.open_badges.enabled} label={data.open_badges.enabled ? "Signing" : "No key"} />}>
        <dl className="text-sm">
          {data.open_badges.enabled ? <>
            <Row k="Signing key">{data.open_badges.source}</Row>
            <Row k="Key id"><Code>{data.open_badges.kid}</Code></Row>
          </> : <p className="text-amber-800">{data.open_badges.detail}</p>}
          <Row k="Public keys"><a className="text-comet-700 underline" href={data.open_badges.jwks_url} target="_blank" rel="noreferrer">jwks.json</a></Row>
          <Row k="Issuer profile"><a className="text-comet-700 underline" href={data.open_badges.issuer_url} target="_blank" rel="noreferrer">issuer</a></Row>
          <Row k="LinkedIn organization">{data.open_badges.linkedin_org_id ?? "Not set (LINKEDIN_ORG_ID): the university's name is used"}</Row>
        </dl>
        <p className="mt-2 text-xs text-slate-500">Every badge is a signed credential that students download for wallets and badge platforms; shared badges get a prefilled LinkedIn "Add to profile" link.</p>
      </Card>

      <Card title={<span className="flex items-center gap-2"><Briefcase className="h-4 w-4 text-flame-500" aria-hidden />Handshake job postings</span>} className="lg:col-span-2">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2 text-sm text-slate-600">
            <p>Import the jobs export from Handshake (Jobs, then Export) as CSV or Excel. Each import is a full snapshot: postings no longer listed, or past their expiration date, are closed.</p>
            <p><b className="text-slate-800">{data.handshake.open_postings}</b> open · {data.handshake.closed_postings} closed{data.handshake.feed ? " · nightly pull from HANDSHAKE_FEED_URL is on" : ""}</p>
          </div>
          <form onSubmit={uploadHandshake} className="space-y-2">
            <label className="label" htmlFor="hs-file">Handshake export</label>
            <input id="hs-file" ref={file} type="file" accept=".csv,.xlsx,.json" className="input" required />
            <button className="btn-primary btn-sm" disabled={hs.busy}>{hs.busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Upload className="h-4 w-4" aria-hidden />}Import postings</button>
            {hs.msg && <p className={`text-xs ${hs.error ? "text-red-700" : "text-slate-600"}`} role="status">{hs.msg}</p>}
          </form>
        </div>
      </Card>
    </div>);
}
