import { useCallback, useEffect, useRef, useState } from 'react';

export interface AsyncState<T> {
  data: T | undefined;
  error: Error | undefined;
  loading: boolean;
  reload: () => void;
}

/** Runs `fn` whenever `deps` change; keeps previous data while refetching. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<Error>();
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(undefined);
    fnRef.current()
      .then((d) => { if (alive) { setData(d); setLoading(false); } })
      .catch((e: unknown) => { if (alive) { setError(e instanceof Error ? e : new Error(String(e))); setLoading(false); } });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);
  // While the results are being rebuilt (503) or the backend is unreachable (0),
  // try again on our own so the page comes back without a manual reload.
  useEffect(() => {
    const status = (error as { status?: number } | undefined)?.status;
    if (status !== 503 && status !== 0) return;
    const t = window.setTimeout(() => setNonce((n) => n + 1), 15000);
    return () => window.clearTimeout(t);
  }, [error]);
  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, error, loading, reload };
}
