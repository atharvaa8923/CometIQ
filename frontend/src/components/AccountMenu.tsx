import { Bell, Download, Settings, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, download, tokenStore } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useApi } from "../lib/hooks";
import { useToast } from "../lib/toast";
import { ErrorBox, Field, Modal } from "./ui";

interface Notif { id: number; title: string; body: string; link: string | null; read: boolean; created_at: string }

export function NotificationBell() {
  const nav = useNavigate();
  const { data, reload } = useApi<{ unread: number; items: Notif[] }>("/notifications");
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { const t = setInterval(reload, 60000); return () => clearInterval(t); }, [reload]);
  useEffect(() => {
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close); return () => document.removeEventListener("mousedown", close);
  }, []);
  const toggle = async () => {
    setOpen(!open);
    if (!open && data?.unread) { await api.post("/notifications/read-all"); setTimeout(reload, 1500); }
  };
  return (
    <div className="relative" ref={ref}>
      <button className="relative rounded-full p-2 text-slate-600 hover:bg-slate-100" onClick={toggle} aria-label={`Notifications${data?.unread ? `, ${data.unread} unread` : ""}`} aria-expanded={open}>
        <Bell className="h-5 w-5" />
        {!!data?.unread && <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-flame-600 px-1 text-[10px] font-bold text-white">{data.unread}</span>}
      </button>
      {open && (
        <div className="absolute right-0 z-30 mt-2 w-80 rounded-xl border border-slate-200 bg-white shadow-xl" role="dialog" aria-label="Notifications">
          <div className="border-b border-slate-100 px-4 py-2 text-sm font-semibold text-slate-700">Notifications</div>
          <ul className="max-h-96 overflow-y-auto">
            {!data?.items.length && <li className="px-4 py-6 text-center text-sm text-slate-500">You're all caught up.</li>}
            {data?.items.map((n) => (
              <li key={n.id}><button className={`w-full px-4 py-3 text-left hover:bg-slate-50 ${n.read ? "" : "bg-flame-50/50"}`} onClick={() => { setOpen(false); if (n.link) nav(n.link); }}>
                <div className="text-sm font-semibold text-slate-800">{n.title}</div>
                <div className="text-xs text-slate-600">{n.body}</div>
                <div className="mt-0.5 text-[11px] text-slate-500">{new Date(n.created_at).toLocaleString()}</div>
              </button></li>))}
          </ul>
        </div>)}
    </div>
  );
}

export function AccountSettings() {
  const { user, logout } = useAuth();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [delPw, setDelPw] = useState("");
  const [delConfirm, setDelConfirm] = useState("");
  const [delErr, setDelErr] = useState<string | null>(null);
  const deleteAccount = async (e: React.FormEvent) => {
    e.preventDefault(); setDelErr(null);
    try { await api.post("/privacy/delete-account", { password: delPw, confirm: delConfirm }); logout(); window.location.href = "/"; }
    catch (x) { setDelErr((x as Error).message); }
  };
  const [notifs, setNotifs] = useState(user?.email_notifications ?? true);
  const [cur, setCur] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState<string | null>(null);
  if (!user) return null;
  const saveNotifs = async (v: boolean) => { setNotifs(v); await api.patch("/auth/me", { email_notifications: v }); toast(v ? "Email notifications on" : "Email notifications off"); };
  const changePw = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    try { const r = await api.post<{ token: string }>("/auth/change-password", { current_password: cur, new_password: pw }); tokenStore.set(r.token); setCur(""); setPw(""); toast("Password changed — other devices were signed out"); }
    catch (x) { setErr((x as Error).message); }
  };
  return (
    <>
      <button className="rounded-full p-2 text-slate-600 hover:bg-slate-100" onClick={() => setOpen(true)} aria-label="Account settings"><Settings className="h-5 w-5" /></button>
      <Modal open={open} onClose={() => setOpen(false)} title="Account settings">
        <div className="space-y-6">
          <div className="text-sm"><div className="font-semibold text-slate-800">{user.full_name}</div><div className="text-slate-500">{user.email}</div></div>
          <label className="flex items-center justify-between gap-3 text-sm"><span>Email me about verifications, plan reviews and applications</span>
            <input type="checkbox" className="h-4 w-4 accent-comet-600" checked={notifs} onChange={(e) => saveNotifs(e.target.checked)} /></label>
{user.sso
            ? <p className="border-t border-slate-100 pt-4 text-sm text-slate-600">You sign in with your institution's single sign-on, so your password is managed there.</p>
            : (<>
            <form onSubmit={changePw} className="space-y-3 border-t border-slate-100 pt-4">
            <div className="text-sm font-semibold text-slate-700">Change password</div>
            <ErrorBox error={err} />
            <Field label="Current password"><input className="input" type="password" required autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} /></Field>
            <Field label="New password" hint="At least 8 characters"><input className="input" type="password" minLength={8} required autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
            <button className="btn-primary btn-sm">Change password</button>
          </form>
            </>)}
          <div className="space-y-3 border-t border-slate-100 pt-4">
            <div className="text-sm font-semibold text-slate-700">Your data</div>
            <p className="text-xs text-slate-500">See what CometIQ stores in the <Link to="/privacy" className="text-comet-700 underline" onClick={() => setOpen(false)}>Privacy Notice</Link>.</p>
            <button type="button" className="btn-ghost btn-sm" onClick={() => download("/privacy/export", "cometiq-my-data.json")}><Download className="h-4 w-4" />Download my data</button>
            <details className="rounded-lg border border-red-200 p-3">
              <summary className="cursor-pointer text-sm font-semibold text-red-700">Delete my account</summary>
              <form onSubmit={deleteAccount} className="mt-3 space-y-2">
                <p className="text-xs text-slate-600">This permanently deletes your account and personal data (plans, submissions, applications). It cannot be undone.</p>
                <ErrorBox error={delErr} />
                {!user.sso && <Field label="Password"><input className="input" type="password" required autoComplete="current-password" value={delPw} onChange={(e) => setDelPw(e.target.value)} /></Field>}
                <Field label='Type DELETE to confirm'><input className="input" required value={delConfirm} onChange={(e) => setDelConfirm(e.target.value)} /></Field>
                <button className="btn btn-sm bg-red-600 text-white hover:bg-red-700" disabled={delConfirm.trim().toUpperCase() !== "DELETE"}><Trash2 className="h-4 w-4" />Permanently delete</button>
              </form>
            </details>
          </div>
        </div>
      </Modal>
    </>
  );
}


/** Asks for (re)consent when the privacy notice/terms version changed since the user last accepted. */
export function ConsentGate() {
  const { user } = useAuth();
  const { data } = useApi<{ version: string }>("/privacy/policy");
  const [accepted, setAccepted] = useState(false);
  if (!user || !data || accepted || user.consent_version === data.version) return null;
  const accept = async () => { await api.post("/privacy/consent"); setAccepted(true); };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4" role="dialog" aria-modal="true" aria-labelledby="consent-title">
      <div className="card max-w-md p-6">
        <h2 id="consent-title" className="text-lg font-bold text-comet-900">Before you continue</h2>
        <p className="mt-2 text-sm text-slate-600">Please review how CometIQ uses your information. You can download or delete your data at any time from Account settings.</p>
        <div className="mt-3 flex gap-4 text-sm"><Link to="/privacy" target="_blank" className="font-semibold text-comet-700 underline">Privacy Notice</Link><Link to="/terms" target="_blank" className="font-semibold text-comet-700 underline">Terms of Use</Link></div>
        <button className="btn-primary mt-5 w-full" onClick={accept} autoFocus>I agree</button>
      </div>
    </div>
  );
}
