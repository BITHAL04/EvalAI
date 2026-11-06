"use client";

import { useMutation, useQuery, useQueryClient, type UseQueryOptions } from "@tanstack/react-query";
import { useCallback } from "react";
import { toast } from "sonner";
import { useSession } from "./auth";
import { API_URL } from "./config";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public fields: { field: string; message: string }[] = []) {
    super(message);
  }
}

export const INSTITUTION_KEY = "evalai_institution";

export async function parseError(res: Response): Promise<ApiError> {
  let body: { detail?: { code?: string; message?: string; errors?: { field: string; message: string }[] } | string } = {};
  try { body = await res.json(); } catch { /* not JSON */ }
  const d = typeof body.detail === "object" ? body.detail : { message: body.detail };
  const fallback = res.status === 429 ? "Too many requests. Try again shortly." : res.status >= 500 ? "The server could not complete this request." : "Request failed.";
  return new ApiError(res.status, d?.code ?? "error", d?.message ?? fallback, d?.errors ?? []);
}

export function useApi() {
  const { getToken } = useSession();
  return useCallback(async <T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> => {
    const token = await getToken();
    const headers = new Headers(init.headers);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    try { const inst = localStorage.getItem(INSTITUTION_KEY); if (inst) headers.set("X-Institution-Id", inst); } catch {}
    let body = init.body;
    if (init.json !== undefined) { headers.set("Content-Type", "application/json"); body = JSON.stringify(init.json); }
    let res: Response;
    try {
      res = await fetch(`${API_URL}/api/v1${path}`, { ...init, headers, body });
    } catch {
      throw new ApiError(0, "network", "Cannot reach the EvalAI API. Check your connection or NEXT_PUBLIC_API_URL.");
    }
    if (!res.ok) throw await parseError(res);
    if (res.status === 204) return undefined as T;
    return res.json() as Promise<T>;
  }, [getToken]);
}

export function useApiQuery<T>(key: unknown[], path: string | null, opts: Partial<UseQueryOptions<T, ApiError>> = {}) {
  const api = useApi();
  const { signedIn } = useSession();
  return useQuery<T, ApiError>({ queryKey: key, queryFn: () => api<T>(path!), enabled: !!path && signedIn && (opts.enabled ?? true), ...opts });
}

type MutateArgs = { path: string; method?: string; json?: unknown };
export function useApiMutation<T = unknown>(opts: { success?: string; invalidate?: unknown[][]; onSuccess?: (d: T) => void } = {}) {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation<T, ApiError, MutateArgs>({
    mutationFn: ({ path, method = "POST", json }) => api<T>(path, { method, json }),
    onSuccess: (d) => {
      if (opts.success) toast.success(opts.success);
      opts.invalidate?.forEach((k) => qc.invalidateQueries({ queryKey: k }));
      opts.onSuccess?.(d);
    },
    onError: (e) => toast.error(e.message),
  });
}

/** Upload directly to the signed storage URL, with progress. The API never proxies file bytes. */
export function uploadWithProgress(url: string, method: string, headers: Record<string, string>, file: File, onProgress: (p: number) => void) {
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url);
    Object.entries(headers).forEach(([k, v]) => xhr.setRequestHeader(k, v));
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
    xhr.onload = () => (xhr.status < 300 ? resolve() : reject(new ApiError(xhr.status, "upload_failed", "The upload was rejected by storage. Try again.")));
    xhr.onerror = () => reject(new ApiError(0, "upload_failed", "The upload was interrupted. Check your connection and try again."));
    xhr.send(file);
  });
}
