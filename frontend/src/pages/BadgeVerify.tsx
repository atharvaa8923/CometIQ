import { BadgeCheck, CheckCircle2, Download, ShieldAlert, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Logo } from "../components/Logo";
import { BadgeCard, type BadgeT } from "./match/Badges";

type Pub = BadgeT & { holder: string; institution: string; valid: boolean; statement: string };
interface Check { check: string; ok: boolean; detail: string }

/** Verifies the signed Open Badges 3.0 credential behind this page, the same way any badge platform would. */
function SignedCredential({ token }: { token: string }) {
  const [res, setRes] = useState<{ valid: boolean; checks: Check[] } | null>(null);
  const [jws, setJws] = useState<string | null>(null);
  useEffect(() => {
    fetch(`/api/public/ob/credentials/${token}`).then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((c: { jwt: string }) => { setJws(c.jwt); return fetch("/api/public/ob/verify", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ credential: c.jwt }) }); })
      .then((r) => r.json()).then(setRes).catch(() => setRes(null));
  }, [token]);
  if (!res) return null;
  const save = () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([jws ?? ""], { type: "application/vc+jwt" })); a.download = "open-badge.jwt"; a.click(); };
  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <div className="mb-2 flex items-center justify-between gap-2"><span className="text-sm font-semibold text-slate-800">Open Badges 3.0 credential</span>
        <button className="btn-ghost btn-sm" onClick={save}><Download className="h-3.5 w-3.5" aria-hidden />Download</button></div>
      <ul className="space-y-1 text-xs">{res.checks.map((c) => (
        <li key={c.check} className="flex items-start gap-2">{c.ok ? <CheckCircle2 className="h-4 w-4 shrink-0 text-green-600" aria-hidden /> : <XCircle className="h-4 w-4 shrink-0 text-red-600" aria-hidden />}
          <span><b className="capitalize">{c.check}</b>: {c.detail}</span></li>))}</ul>
    </div>);
}

export default function BadgeVerify() {
  const { token } = useParams();
  const [b, setB] = useState<Pub | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => { fetch(`/api/public/badges/${token}`).then((r) => (r.ok ? r.json() : Promise.reject())).then(setB).catch(() => setErr(true)); }, [token]);
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
      <div className="w-full max-w-lg space-y-4">
        <div className="flex justify-center"><Logo /></div>
        {err && <div className="card flex items-center gap-3 p-6 text-slate-700"><ShieldAlert className="h-6 w-6 text-red-600" aria-hidden />This badge does not exist or its holder has not shared it.</div>}
        {b && <div className="card space-y-4 p-6">
          <div className={`flex items-center gap-2 font-semibold ${b.valid ? "text-green-800" : "text-red-700"}`}>
            {b.valid ? <BadgeCheck className="h-5 w-5" aria-hidden /> : <ShieldAlert className="h-5 w-5" aria-hidden />}{b.valid ? "Valid credential" : "This badge was revoked"}</div>
          <h1 className="text-xl font-bold text-comet-900">{b.holder}</h1>
          <BadgeCard b={b} />
          <p className="text-sm text-slate-700">{b.statement}</p>
          {token && <SignedCredential token={token} />}
          <p className="text-xs text-slate-500">Issued {new Date(b.issued_at).toLocaleDateString()} by {b.institution} through CometIQ.</p>
        </div>}
      </div>
    </main>
  );
}
