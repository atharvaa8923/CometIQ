import { Loader2, X } from "lucide-react";
import { useEffect, type ReactNode } from "react";

export function PageHeader({ title, subtitle, icon, actions, accent = "comet" }: {
  title: string; subtitle?: string; icon?: ReactNode; actions?: ReactNode; accent?: "comet" | "flame" | "navy";
}) {
  const bg = accent === "flame" ? "bg-flame-500" : accent === "navy" ? "bg-navy-500" : "bg-comet-600";
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="flex items-center gap-3">
        {icon && <div className={`flex h-11 w-11 items-center justify-center rounded-full text-white ${bg}`}>{icon}</div>}
        <div>
          <h1 className="text-2xl font-bold text-comet-900">{title}</h1>
          {subtitle && <p className="text-sm text-slate-500">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ title, actions, children, className = "", padded = true }: {
  title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; padded?: boolean;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-5 py-3">
          <h2 className="text-sm font-semibold text-slate-700">{title}</h2>
          {actions}
        </div>
      )}
      <div className={padded ? "p-5" : ""}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, hint, tone = "comet" }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "comet" | "flame" | "navy" | "slate" }) {
  const color = { comet: "text-comet-700", flame: "text-flame-600", navy: "text-navy-500", slate: "text-slate-700" }[tone];
  return (
    <div className="card p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-bold ${color}`}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

const BADGE: Record<string, string> = {
  green: "bg-comet-100 text-comet-800", orange: "bg-flame-100 text-flame-700", red: "bg-red-100 text-red-700",
  blue: "bg-sky-100 text-sky-800", slate: "bg-slate-100 text-slate-700", purple: "bg-violet-100 text-violet-700",
  yellow: "bg-amber-100 text-amber-800",
};
export function Badge({ children, color = "slate", title }: { children: ReactNode; color?: keyof typeof BADGE | string; title?: string }) {
  return <span title={title} className={`chip ${BADGE[color] ?? BADGE.slate}`}>{children}</span>;
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return <div className="flex items-center gap-2 p-6 text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin" />{label}</div>;
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>;
}

export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
      {icon && <div className="mb-3 text-slate-500">{icon}</div>}
      <div className="font-semibold text-slate-700">{title}</div>
      {children && <div className="mt-1 max-w-md text-sm text-slate-500">{children}</div>}
    </div>
  );
}

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4 pt-16" onClick={onClose}>
      <div className={`card w-full ${wide ? "max-w-3xl" : "max-w-lg"}`} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={title}>
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
          <h2 className="font-semibold text-slate-800">{title}</h2>
          <button className="rounded p-1 text-slate-500 hover:bg-slate-100" onClick={onClose} aria-label="Close"><X className="h-4 w-4" /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: ReactNode }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="mb-4 flex gap-1 border-b border-slate-200" role="tablist">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={value === t.id} onClick={() => onChange(t.id)}
          className={`-mb-px border-b-2 px-4 py-2 text-sm font-semibold ${value === t.id ? "border-flame-500 text-comet-800" : "border-transparent text-slate-500 hover:text-slate-700"}`}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

/** Horizontal score bar 0–100. */
export function ScoreBar({ value, tone, label = "Score" }: { value: number; tone?: "auto" | "comet" | "flame"; label?: string }) {
  const v = Math.max(0, Math.min(100, value));
  const color = tone === "flame" ? "bg-flame-500" : tone === "comet" ? "bg-comet-600" : v >= 70 ? "bg-comet-600" : v >= 45 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="h-2 w-full rounded-full bg-slate-100" role="progressbar" aria-label={label} aria-valuenow={Math.round(v)} aria-valuemin={0} aria-valuemax={100}>
      <div className={`h-2 rounded-full ${color}`} style={{ width: `${v}%` }} />
    </div>
  );
}

/** Ring gauge for a headline score. */
export function ScoreRing({ value, size = 120, label }: { value: number; size?: number; label?: string }) {
  const r = (size - 14) / 2, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, value));
  const color = v >= 70 ? "#17684a" : v >= 45 ? "#d97706" : "#dc2626";
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} stroke="#e2e8f0" strokeWidth={10} fill="none" />
        <circle cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth={10} fill="none" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - v / 100)} />
      </svg>
      <div className="absolute text-center">
        <div className="text-2xl font-bold" style={{ color }}>{Math.round(v)}%</div>
        {label && <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</div>}
      </div>
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}
