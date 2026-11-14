const TOKEN_KEY = "cometiq_token";

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`/api${path}`, { method, headers, body: payload });
  if (res.status === 401 && token) {
    tokenStore.clear();
    window.location.href = "/login";
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : Array.isArray(j.detail) ? j.detail.map((d: { msg: string }) => d.msg).join("; ") : msg;
    } catch { /* not json */ }
    throw new ApiError(res.status, msg);
  }
  const ct = res.headers.get("content-type") || "";
  return (ct.includes("application/json") ? res.json() : (res.blob() as unknown)) as T;
}

export const api = {
  get: <T,>(p: string) => request<T>("GET", p),
  post: <T,>(p: string, b?: unknown) => request<T>("POST", p, b),
  put: <T,>(p: string, b?: unknown) => request<T>("PUT", p, b),
  patch: <T,>(p: string, b?: unknown) => request<T>("PATCH", p, b),
  del: <T,>(p: string) => request<T>("DELETE", p),
};

/** Download a file from an authenticated endpoint. */
export async function download(path: string, filename: string) {
  const blob = await request<Blob>("GET", path);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export interface TaskStatus { id: string; status: "queued" | "running" | "done" | "failed"; progress: string | null; result: Record<string, unknown> | null; error: string | null }

/** Poll a background task until it finishes. Resolves with its result; rejects if it failed. */
export async function waitForTask(taskId: string, onProgress?: (t: TaskStatus) => void, timeoutMs = 10 * 60 * 1000): Promise<Record<string, unknown>> {
  const start = Date.now();
  for (let delay = 600; ; delay = Math.min(delay * 1.4, 3000)) {
    const t = await api.get<TaskStatus>(`/tasks/${taskId}`);
    onProgress?.(t);
    if (t.status === "done") return t.result ?? {};
    if (t.status === "failed") throw new ApiError(500, t.error ?? "The job failed");
    if (Date.now() - start > timeoutMs) throw new ApiError(504, "This is taking longer than expected — check back in a minute.");
    await new Promise((r) => setTimeout(r, delay));
  }
}
