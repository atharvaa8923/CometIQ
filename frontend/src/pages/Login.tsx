import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Logo } from "../components/Logo";
import { ErrorBox } from "../components/ui";
import { useAuth } from "../lib/auth";

const DEMO = [
  ["Faculty", "faculty@cometiq.app"], ["Student", "student@cometiq.app"],
  ["Employer", "employer@cometiq.app"], ["Advisor", "advisor@cometiq.app"], ["Admin", "admin@cometiq.app"],
];

export function AuthShell({ children, title }: { children: React.ReactNode; title: string }) {
  return (
    <div className="grid min-h-screen md:grid-cols-2">
      <div className="hidden flex-col justify-between bg-gradient-to-br from-comet-900 to-comet-700 p-10 text-white md:flex">
        <Link to="/"><Logo light /></Link>
        <div>
          <div className="text-3xl font-bold leading-snug">Right Skills. Right Courses.<br />Right Students. <span className="text-flame-400">Brighter Futures.</span></div>
          <p className="mt-4 text-comet-100">From industry demand to student success.</p>
        </div>
        <div className="text-xs tracking-[0.25em] text-comet-200">LEARN / INNOVATE / IMPACT</div>
      </div>
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="mb-6 md:hidden"><Logo /></div>
          <h1 className="mb-6 text-2xl font-bold text-comet-900">{title}</h1>
          {children}
        </div>
      </div>
    </div>
  );
}

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [demo, setDemo] = useState(false);
  useEffect(() => { fetch("/api/auth/public-config").then((r) => r.json()).then((c) => setDemo(!!c.demo)).catch(() => setDemo(false)); }, []);

  const submit = async (e?: React.FormEvent, creds?: [string, string]) => {
    e?.preventDefault();
    setBusy(true); setErr(null);
    try {
      await login(...(creds ?? [email, password]));
      nav("/app");
    } catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  };

  return (
    <AuthShell title="Sign in to CometIQ">
      <form onSubmit={submit} className="space-y-4">
        <ErrorBox error={err} />
        <div><label className="label" htmlFor="email">Email</label><input id="email" className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></div>
        <div><label className="label" htmlFor="pw">Password</label><input id="pw" className="input" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></div>
        <button className="btn-primary w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        <div className="text-right text-sm"><Link to="/forgot-password" className="font-semibold text-comet-700 hover:underline">Forgot password?</Link></div>
      </form>
      <p className="mt-4 text-center text-sm text-slate-500">New here? <Link to="/register" className="font-semibold text-flame-600">Create an account</Link></p>
      {demo && <div className="mt-8 rounded-lg border border-slate-200 bg-slate-50 p-4">
        <div className="label">One-click demo accounts</div>
        <div className="grid grid-cols-3 gap-2">
          {DEMO.map(([r, e]) => (
            <button key={e} type="button" className="btn-ghost btn-sm" disabled={busy} onClick={() => submit(undefined, [e, "CometIQ2026!"])}>{r}</button>
          ))}
        </div>
      </div>}
    </AuthShell>
  );
}
