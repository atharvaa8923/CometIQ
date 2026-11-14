export function Logo({ light = false, size = "md" }: { light?: boolean; size?: "sm" | "md" | "lg" }) {
  const text = size === "lg" ? "text-4xl" : size === "sm" ? "text-lg" : "text-2xl";
  const icon = size === "lg" ? 44 : size === "sm" ? 24 : 32;
  return (
    <div className="flex items-center gap-2 select-none">
      <svg width={icon} height={icon} viewBox="0 0 64 64" aria-hidden="true">
        <path d="M6 44C14 22 32 10 58 8 38 15 24 26 16 46z" fill="#e87500" />
        <circle cx="34" cy="38" r="12" fill="none" stroke={light ? "#fff" : "#0e4231"} strokeWidth="6" />
        <path d="M52 4l2.2 5.8L60 12l-5.8 2.2L52 20l-2.2-5.8L44 12l5.8-2.2z" fill="#ffa65c" />
      </svg>
      <span className={`${text} font-extrabold tracking-tight ${light ? "text-white" : "text-comet-900"}`}>
        COMET<span className="text-flame-500">IQ</span>
      </span>
    </div>
  );
}
