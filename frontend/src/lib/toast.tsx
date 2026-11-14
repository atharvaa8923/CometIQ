import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type Kind = "success" | "error" | "info";
const Ctx = createContext<(msg: string, kind?: Kind) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<{ id: number; msg: string; kind: Kind }[]>([]);
  const push = useCallback((msg: string, kind: Kind = "success") => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { id, msg, kind }]);
    setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), 4000);
  }, []);
  return (
    <Ctx.Provider value={push}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`rounded-lg px-4 py-3 text-sm font-medium text-white shadow-lg ${
            t.kind === "error" ? "bg-red-600" : t.kind === "info" ? "bg-navy-500" : "bg-comet-700"}`}>{t.msg}</div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
export const useToast = () => useContext(Ctx);
