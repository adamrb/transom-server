import type { ZodType } from 'zod';
import { tokenStore } from './token';

export const API_BASE = '/api/v1';

/** Dispatched on window when the server answers 401: the auth provider shows the gate. */
export const AUTH_REQUIRED_EVENT = 'pb:auth-required';

/** Default sentence when the server gave none. Never a status code. */
export const GENERIC_ERROR = 'Something went wrong. Try again.';

/**
 * A failed request. `message` is always something a person can read: the server's `detail`
 * sentence when it sent one (4xx only; 5xx bodies are not for people), otherwise a fallback.
 * Status codes stay on `.status` for logic (404 = the server does not have this endpoint yet),
 * never in UI copy.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string | null;
  constructor(status: number, detail: string | null, fallback = GENERIC_ERROR) {
    super(detail || fallback);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
  get unauthorized() {
    return this.status === 401;
  }
  get notFound() {
    return this.status === 404;
  }
  get conflict() {
    return this.status === 409;
  }
  /** The message to show, preferring the server's sentence over the caller's fallback. */
  userMessage(fallback: string): string {
    return this.detail || fallback;
  }
}

/** A network failure (server unreachable). */
export class NetworkError extends Error {
  constructor() {
    super("Can't reach your server");
    this.name = 'NetworkError';
  }
}

/** The text to show for any thrown value. Never leaks status codes or exception internals. */
export function errorMessage(err: unknown, fallback = GENERIC_ERROR): string {
  if (err instanceof ApiError) return err.userMessage(fallback);
  if (err instanceof NetworkError) return err.message;
  return fallback;
}

export interface RequestOptions extends Omit<RequestInit, 'body'> {
  /** JSON body (serialised, content-type set). Use `formData` for uploads. */
  json?: unknown;
  formData?: FormData;
  /** Query string parameters; null/undefined/'' are dropped. */
  query?: Record<string, string | number | boolean | null | undefined>;
  /** Send without the bearer header (login requests). */
  anonymous?: boolean;
  /** Use this token instead of the stored one (auth check of a candidate). */
  token?: string;
  /** Do not broadcast AUTH_REQUIRED on 401 (auth check of a candidate token). */
  silent401?: boolean;
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`;
  if (!query) return url;
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(query))
    if (v !== null && v !== undefined && v !== '') qs.set(k, String(v));
  const s = qs.toString();
  return s ? `${url}?${s}` : url;
}

/** The server's `detail` when it is a sentence for people (4xx only). */
export async function readDetail(r: Response): Promise<string | null> {
  if (r.status >= 500) return null;
  try {
    const d = (await r.clone().json())?.detail;
    return typeof d === 'string' && d.trim() ? d.trim() : null;
  } catch {
    return null;
  }
}

/**
 * fetch with the bearer header. Resolves with the Response for any status except 401, which
 * broadcasts AUTH_REQUIRED and throws. Network failures throw NetworkError.
 */
export async function apiFetch(path: string, opts: RequestOptions = {}): Promise<Response> {
  const { json, formData, query, anonymous, token, silent401, headers, ...init } = opts;
  const h = new Headers(headers);
  if (!anonymous) {
    const t = token ?? tokenStore.get();
    if (t) h.set('Authorization', `Bearer ${t}`);
  }
  let body: BodyInit | undefined;
  if (json !== undefined) {
    h.set('Content-Type', 'application/json');
    body = JSON.stringify(json);
  } else if (formData) body = formData;
  let r: Response;
  try {
    r = await fetch(buildUrl(path, query), { ...init, headers: h, body });
  } catch {
    throw new NetworkError();
  }
  if (r.status === 401 && !anonymous) {
    if (!silent401) window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT));
    throw new ApiError(401, null, 'Please sign in again.');
  }
  return r;
}

/** apiFetch + ok check: throws ApiError with the server's detail for any non-2xx response. */
export async function apiRequest(path: string, opts?: RequestOptions): Promise<Response> {
  const r = await apiFetch(path, opts);
  if (!r.ok) throw new ApiError(r.status, await readDetail(r));
  return r;
}

/**
 * JSON request validated against a zod schema. 204 resolves to null. A response that does not
 * match the schema throws an ApiError (status 0) so the UI shows a sentence, not a stack trace;
 * the mismatch is logged for developers.
 */
export async function apiJson<T>(path: string, schema: ZodType<T>, opts?: RequestOptions): Promise<T> {
  const r = await apiRequest(path, opts);
  if (r.status === 204) return null as T;
  const data: unknown = await r.json();
  const parsed = schema.safeParse(data);
  if (!parsed.success) {
    if (import.meta.env.DEV && import.meta.env.MODE !== 'test')
      console.error(`[api] ${path}: response did not match schema`, parsed.error.issues, data);
    throw new ApiError(0, null, 'Your server answered in a way this app did not expect.');
  }
  return parsed.data;
}

/** Parse a Content-Disposition header for the download name. */
export function filenameFromDisposition(cd: string | null, fallback: string): string {
  if (!cd) return fallback;
  const m = cd.match(/filename\*=UTF-8''([^;]+)/i) || cd.match(/filename="([^"]+)"/i);
  if (!m) return fallback;
  try {
    return decodeURIComponent(m[1]);
  } catch {
    return m[1];
  }
}
