import { AlertTriangle, CheckCircle2, CircleDashed, XCircle } from "lucide-react";

/** Reserved status palette (never reused for series). Always paired with icon + label. */
export const STATUS = {
  covered: { color: "#0ca30c", label: "Covered", Icon: CheckCircle2, text: "text-green-800", bg: "bg-green-50" },
  partial: { color: "#fab219", label: "Partial", Icon: AlertTriangle, text: "text-amber-800", bg: "bg-amber-50" },
  missing: { color: "#d03b3b", label: "Missing", Icon: XCircle, text: "text-red-800", bg: "bg-red-50" },
} as const;
export type Status = keyof typeof STATUS;

export function StatusTag({ s }: { s: Status }) {
  const x = STATUS[s];
  return <span className={`chip ${x.bg} ${x.text}`}><x.Icon className="h-3.5 w-3.5" style={{ color: x.color }} aria-hidden />{x.label}</span>;
}

export function StatusLegend() {
  return (
    <div className="flex flex-wrap gap-3 text-xs text-slate-600" aria-label="Legend">
      {(Object.keys(STATUS) as Status[]).map((k) => { const x = STATUS[k]; return (
        <span key={k} className="inline-flex items-center gap-1"><x.Icon className="h-3.5 w-3.5" style={{ color: x.color }} aria-hidden />{x.label}</span>); })}
    </div>
  );
}

export const PRIORITY_COLOR: Record<string, string> = { critical: "red", high: "orange", medium: "yellow", low: "slate" };

/** Sequential single-hue (blue) steps for ordinal heatmap cells: none / partial / strong. */
export const HEAT = { 0: "#f0efec", 0.5: "#86b6ef", 1: "#256abf" } as Record<number, string>;
export const EmptyIcon = CircleDashed;
