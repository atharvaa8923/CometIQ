import { BadgeCheck, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Logo } from "../components/Logo";
import { BadgeCard, type BadgeT } from "./match/Badges";

type Pub = BadgeT & { holder: string; institution: string; valid: boolean; statement: string };

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
          <p className="text-xs text-slate-500">Issued {new Date(b.issued_at).toLocaleDateString()} by {b.institution} through CometIQ.</p>
        </div>}
      </div>
    </main>
  );
}
