import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

/** GET a resource; returns data, loading, error and a reload function. */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(!!path);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    if (!path) return;
    setLoading(true);
    setError(null);
    api.get<T>(path).then(setData).catch((e) => setError(e.message)).finally(() => setLoading(false));
  }, [path]);
  useEffect(load, [load]);
  return { data, loading, error, reload: load, setData };
}
