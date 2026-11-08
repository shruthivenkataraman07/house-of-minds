/**
 * Typed client for the House of Minds API (/api/v1). Responses are cached per URL for the
 * session; the snapshot is immutable, so identical requests never hit the server twice.
 */
import { useEffect, useState } from "react";

import type { Envelope } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";
const cache = new Map<string, Promise<unknown>>();

export class ApiError extends Error {
  constructor(public status: number, public detail: string, public recovery: string) { super(detail); }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}/api/v1${path}`, { ...init, headers: { "content-type": "application/json" } });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(r.status, body.detail ?? r.statusText, body.recovery ?? "Retry.");
  return body as T;
}

export function getJSON<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    const p = request<T>(path);
    p.catch(() => cache.delete(path));
    cache.set(path, p);
  }
  return cache.get(path) as Promise<T>;
}

export function postJSON<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export type State<T> = { data?: T; error?: ApiError; loading: boolean };

/** Fetch an enveloped endpoint; `null` path skips the request. */
export function useApi<T>(path: string | null): State<Envelope<T>> & { reload: () => void } {
  // `key` records which request the stored result belongs to; loading is derived from it.
  const [res, setRes] = useState<{ key: string; data?: Envelope<T>; error?: ApiError } | null>(null);
  const [n, setN] = useState(0);
  const key = path ? `${path}#${n}` : null;
  useEffect(() => {
    if (!path || !key) return;
    let live = true;
    getJSON<Envelope<T>>(path).then(
      (data) => { if (live) setRes({ key, data }); },
      (error: ApiError) => { if (live) setRes({ key, error }); },
    );
    return () => { live = false; };
  }, [path, key]);
  const current = res && res.key === key;
  return {
    data: res?.data, // keep the last result visible while a new period loads
    error: current ? res?.error : undefined,
    loading: !!key && !current,
    reload: () => { if (path) cache.delete(path); setN((x) => x + 1); },
  };
}
