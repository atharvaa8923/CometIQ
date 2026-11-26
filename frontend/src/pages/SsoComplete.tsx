import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ErrorBox, Spinner } from "../components/ui";
import { useAuth } from "../lib/auth";
import { AuthShell } from "./Login";

/** The single sign-on callback lands here with the session token in the URL fragment (never sent to a server). */
export default function SsoComplete() {
  const { signInWithToken } = useAuth();
  const nav = useNavigate();
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    const frag = new URLSearchParams(window.location.hash.slice(1));
    const token = frag.get("token");
    const next = frag.get("next") || "/app";
    window.history.replaceState(null, "", window.location.pathname);   // drop the token from the address bar and history
    if (!token) { setErr("The sign-in did not complete. Try again."); return; }
    signInWithToken(token)
      .then(() => nav(next.startsWith("/") && !next.startsWith("//") ? next : "/app", { replace: true }))
      .catch(() => setErr("The sign-in did not complete. Try again."));
  }, [signInWithToken, nav]);
  return (
    <AuthShell title="Signing you in…">
      {err ? <div className="space-y-4"><ErrorBox error={err} /><Link className="btn-primary" to="/login">Back to sign-in</Link></div> : <Spinner />}
    </AuthShell>
  );
}
