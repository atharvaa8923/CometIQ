import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ErrorBox, Field } from "../components/ui";
import { useAuth } from "../lib/auth";
import { AuthShell } from "./Login";

export default function Register() {
  const { register } = useAuth();
  const nav = useNavigate();
  const [mode, setMode] = useState<"join" | "create">("join");
  const [f, setF] = useState({ full_name: "", email: "", password: "", role: "student", join_code: "", org_name: "", company: "" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      await register({
        full_name: f.full_name, email: f.email, password: f.password,
        role: mode === "create" ? "faculty" : f.role,
        ...(mode === "join" ? { join_code: f.join_code } : { org_name: f.org_name }),
        ...(f.role === "employer" ? { company: f.company } : {}),
      });
      nav("/app");
    } catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  };

  return (
    <AuthShell title="Create your account">
      <div className="mb-4 grid grid-cols-2 gap-1 rounded-lg bg-slate-100 p-1 text-sm font-semibold">
        {(["join", "create"] as const).map((m) => (
          <button key={m} type="button" onClick={() => setMode(m)} className={`rounded-md py-1.5 ${mode === m ? "bg-white text-comet-800 shadow" : "text-slate-500"}`}>
            {m === "join" ? "Join an institution" : "New institution"}
          </button>
        ))}
      </div>
      <form onSubmit={submit} className="space-y-3">
        <ErrorBox error={err} />
        <Field label="Full name"><input className="input" required value={f.full_name} onChange={set("full_name")} /></Field>
        <Field label="Email"><input className="input" type="email" required value={f.email} onChange={set("email")} /></Field>
        <Field label="Password" hint="At least 8 characters"><input className="input" type="password" minLength={8} required value={f.password} onChange={set("password")} /></Field>
        {mode === "join" ? (
          <>
            <Field label="I am a">
              <select className="input" value={f.role} onChange={set("role")}>
                <option value="student">Student</option><option value="faculty">Faculty member</option><option value="advisor">Academic advisor</option><option value="employer">Employer / recruiter</option>
              </select>
            </Field>
            {f.role === "employer" && <Field label="Company"><input className="input" required value={f.company} onChange={set("company")} /></Field>}
            <Field label="Institution join code" hint="Ask your administrator. Demo: COMET-UTD"><input className="input uppercase" required value={f.join_code} onChange={set("join_code")} /></Field>
          </>
        ) : (
          <Field label="Institution name" hint="You'll be its administrator and get a join code to invite others."><input className="input" required value={f.org_name} onChange={set("org_name")} /></Field>
        )}
        <button className="btn-accent w-full" disabled={busy}>{busy ? "Creating…" : "Create account"}</button>
      </form>
      <p className="mt-4 text-center text-sm text-slate-500">Already have an account? <Link to="/login" className="font-semibold text-comet-700">Sign in</Link></p>
    </AuthShell>
  );
}
