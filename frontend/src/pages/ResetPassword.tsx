import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ErrorBox, Field } from "../components/ui";
import { api, tokenStore } from "../lib/api";
import { AuthShell } from "./Login";

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null);
    try { setMsg((await api.post<{ message: string }>("/auth/forgot-password", { email })).message); }
    catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  };
  return (
    <AuthShell title="Reset your password">
      {msg ? <div className="rounded-lg border border-green-200 bg-green-50 p-4 text-sm text-green-800" role="status">{msg} Check your inbox (and spam folder).</div> : (
        <form onSubmit={submit} className="space-y-4">
          <ErrorBox error={err} />
          <p className="text-sm text-slate-600">Enter your account email and we'll send you a link to choose a new password.</p>
          <Field label="Email"><input className="input" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          <button className="btn-primary w-full" disabled={busy}>{busy ? "Sending…" : "Send reset link"}</button>
        </form>)}
      <p className="mt-4 text-center text-sm"><Link to="/login" className="font-semibold text-comet-700">Back to sign in</Link></p>
    </AuthShell>
  );
}

export default function ResetPassword() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const token = params.get("token") ?? "";
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    if (pw !== pw2) { setErr("Passwords don't match"); return; }
    setBusy(true);
    try {
      const r = await api.post<{ token: string }>("/auth/reset-password", { token, password: pw });
      tokenStore.set(r.token); nav("/app"); window.location.reload();
    } catch (x) { setErr((x as Error).message); setBusy(false); }
  };
  return (
    <AuthShell title="Choose a new password">
      {!token ? <ErrorBox error="This link is missing its token. Request a new reset email." /> : (
        <form onSubmit={submit} className="space-y-4">
          <ErrorBox error={err} />
          <Field label="New password" hint="At least 8 characters"><input className="input" type="password" minLength={8} required autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
          <Field label="Repeat new password"><input className="input" type="password" minLength={8} required autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} /></Field>
          <button className="btn-primary w-full" disabled={busy}>{busy ? "Saving…" : "Set password and sign in"}</button>
        </form>)}
      <p className="mt-4 text-center text-sm"><Link to="/forgot-password" className="font-semibold text-comet-700">Request a new link</Link></p>
    </AuthShell>
  );
}
