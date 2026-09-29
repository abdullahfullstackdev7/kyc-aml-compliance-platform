import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

export function useApi<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    api
      .get<T>(path)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Failed to load");
      });
    return () => {
      cancelled = true;
    };
  }, [path]);

  return { data, error, loading: data === null && error === null };
}
