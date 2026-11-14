import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, tokenStore } from "./api";

export type Role = "admin" | "faculty" | "student" | "employer" | "advisor";
export interface User {
  id: string; email: string; full_name: string; role: Role; company?: string | null; email_notifications?: boolean; consent_version?: string | null;
  org: { id: string; name: string; slug: string; plan: string };
}
interface AuthCtx {
  user: User | null; loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (body: Record<string, unknown>) => Promise<User>;
  logout: () => void;
}

const Ctx = createContext<AuthCtx>(null!);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!tokenStore.get()) { setLoading(false); return; }
    api.get<User>("/auth/me").then(setUser).catch(() => tokenStore.clear()).finally(() => setLoading(false));
  }, []);

  const finish = (r: { token: string; user: User }) => { tokenStore.set(r.token); setUser(r.user); return r.user; };
  const login = useCallback(async (email: string, password: string) =>
    finish(await api.post<{ token: string; user: User }>("/auth/login", { email, password })), []);
  const register = useCallback(async (body: Record<string, unknown>) =>
    finish(await api.post<{ token: string; user: User }>("/auth/register", body)), []);
  const logout = useCallback(() => { tokenStore.clear(); setUser(null); }, []);

  return <Ctx.Provider value={{ user, loading, login, register, logout }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
