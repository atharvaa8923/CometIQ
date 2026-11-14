import { LogOut, Menu, Sparkles } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { useApi } from "../lib/hooks";
import { NAV, ROLE_LABEL } from "../lib/modules";
import { Logo } from "./Logo";

export default function Layout() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const { data: meta } = useApi<{ ai_enabled: boolean }>("/meta");
  if (!user) return null;
  const items = NAV.filter((n) => n.roles.includes(user.role));

  return (
    <div className="flex min-h-screen">
      <aside className={`fixed inset-y-0 left-0 z-30 flex w-64 flex-col bg-comet-900 text-comet-50 transition-transform lg:static lg:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="px-5 py-5"><Logo light size="sm" /></div>
        <nav className="flex-1 space-y-1 px-3" aria-label="Main">
          {items.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/app"} onClick={() => setOpen(false)}
              className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
                isActive ? "bg-white/10 text-white" : "text-comet-100/80 hover:bg-white/5 hover:text-white"}`}>
              <span className={`flex h-7 w-7 items-center justify-center rounded-md ${n.accent ?? "bg-white/10"} text-white`}>{n.icon}</span>
              <span>{n.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="m-3 rounded-lg bg-white/5 p-3 text-xs">
          <div className="flex items-center gap-1.5 font-semibold text-flame-300"><Sparkles className="h-3.5 w-3.5" />
            {meta?.ai_enabled ? "Claude AI connected" : "Built-in AI engine"}</div>
          <div className="mt-0.5 text-comet-100/70">{meta?.ai_enabled ? "Extraction & generation use Claude." : "Add ANTHROPIC_API_KEY to enable Claude."}</div>
        </div>
      </aside>
      {open && <div className="fixed inset-0 z-20 bg-black/30 lg:hidden" onClick={() => setOpen(false)} />}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-white/90 px-4 py-3 backdrop-blur lg:px-8">
          <div className="flex items-center gap-3">
            <button className="rounded p-1.5 hover:bg-slate-100 lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu"><Menu className="h-5 w-5" /></button>
            <div className="truncate text-sm text-slate-500"><span className="font-semibold text-comet-800">{user.org.name}</span></div>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <div className="text-sm font-semibold text-slate-800">{user.full_name}</div>
              <div className="text-xs text-slate-500">{ROLE_LABEL[user.role]}{user.company ? ` · ${user.company}` : ""}</div>
            </div>
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-flame-500 text-sm font-bold text-white">
              {user.full_name.split(" ").map((p) => p[0]).slice(0, 2).join("")}
            </div>
            <button className="btn-ghost btn-sm" onClick={logout} title="Sign out"><LogOut className="h-4 w-4" /><span className="hidden sm:inline">Sign out</span></button>
          </div>
        </header>
        <main className="flex-1 px-4 py-6 lg:px-8"><Outlet /></main>
      </div>
    </div>
  );
}
