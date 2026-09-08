import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '@/api/client';
import { browserLabel, createLoginRequest, pollLoginRequest } from '@/api/hooks/auth';
import type { LoginRequest } from '@/api/types';
import { session, STORAGE_KEYS } from '@/lib/storage';

export type QrPhase =
  | 'starting' // asking the server for a code
  | 'waiting' // code on screen, polling
  | 'hiccup' // poll failed once; still the same code
  | 'renewing' // code expired, getting a new one
  | 'rate-limited' // too many codes; retry in 30 s
  | 'offline' // could not reach the server; retry in 30 s
  | 'unsupported' // server has no QR sign-in
  | 'approved';

export interface QrLoginState {
  phase: QrPhase;
  request: LoginRequest | null;
  /** Sentence under the code, in user words. */
  message: string;
}

const MESSAGES: Record<QrPhase, string> = {
  starting: 'Getting a sign-in code…',
  waiting: 'Waiting for your phone…',
  hiccup: 'Waiting for your phone… (connection hiccup, retrying)',
  renewing: 'Code expired, getting a new one…',
  'rate-limited': 'Too many sign-in codes requested recently. Trying again in 30 seconds…',
  offline: 'Could not reach the server for QR sign-in. Retrying in 30 seconds…',
  unsupported: 'This server does not support QR sign-in yet.',
  approved: 'Signed in.',
};

const RETRY_MS = 30_000;
const FIRST_POLL_MS = 2_000;
/** A remembered request must still have this long to live to be worth reusing. */
const REUSE_MARGIN_MS = 15_000;

/** A reload should not abandon a pending request and mint another (five abandoned ones hit the per-client cap). */
export function savedLoginRequest(now = Date.now()): LoginRequest | null {
  const v = session.getJSON<LoginRequest>(STORAGE_KEYS.loginRequest);
  if (!v || !v.id || !v.expires_at) return null;
  const exp = new Date(v.expires_at).getTime();
  return Number.isFinite(exp) && exp - now > REUSE_MARGIN_MS
    ? { ...v, poll_seconds: v.poll_seconds || 2 }
    : null;
}

export function rememberLoginRequest(req: LoginRequest | null) {
  if (req) session.setJSON(STORAGE_KEYS.loginRequest, req);
  else session.remove(STORAGE_KEYS.loginRequest);
}

/**
 * QR sign-in: ask the server for a short-lived login request, show its id as a QR the phone app
 * scans, poll until the phone approves, then hand the minted token to `onToken`. One active
 * request per open gate, reused from sessionStorage across reloads until it expires.
 */
export function useQrLogin(onToken: (token: string) => void, enabled = true): QrLoginState {
  const [state, setState] = useState<QrLoginState>({
    phase: 'starting',
    request: null,
    message: MESSAGES.starting,
  });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const alive = useRef(true);
  // Bumped on every (re)mount. A start() still awaiting the server from a previous effect run
  // (StrictMode runs effects twice in development) sees a newer generation and gives up, so one
  // gate never holds two login requests.
  const gen = useRef(0);
  const reqRef = useRef<LoginRequest | null>(null);
  const onTokenRef = useRef(onToken);
  onTokenRef.current = onToken;

  const set = useCallback((phase: QrPhase, request: LoginRequest | null = reqRef.current) => {
    reqRef.current = request;
    if (alive.current) setState({ phase, request, message: MESSAGES[phase] });
  }, []);

  const schedule = useCallback((fn: () => void, ms: number) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(fn, ms);
  }, []);

  const start = useCallback(async () => {
    if (timer.current) clearTimeout(timer.current);
    const mine = gen.current;
    let req = savedLoginRequest();
    if (!req) {
      set('starting', null);
      try {
        req = await createLoginRequest(browserLabel());
        if (gen.current !== mine) return; // superseded while the request was out: leave it for the newer run
        rememberLoginRequest(req);
      } catch (e) {
        if (!alive.current || gen.current !== mine) return;
        if (e instanceof ApiError && e.notFound) return set('unsupported', null);
        if (e instanceof ApiError && e.status === 429) {
          set('rate-limited', null);
          return schedule(() => void start(), RETRY_MS);
        }
        set('offline', null);
        return schedule(() => void start(), RETRY_MS);
      }
      if (!alive.current) return;
    }
    set('waiting', req);

    const poll = async () => {
      const current = reqRef.current;
      if (!current || !alive.current) return;
      let data: Awaited<ReturnType<typeof pollLoginRequest>> | null = null;
      try {
        data = await pollLoginRequest(current.id);
      } catch {
        // Transport error or garbage: keep the same request and try again; only an explicit
        // "expired" replaces it (each replacement costs a per-client slot).
        data = null;
      }
      if (!alive.current || reqRef.current !== current) return;
      if (data?.status === 'approved' && data.token) {
        rememberLoginRequest(null);
        set('approved', null);
        onTokenRef.current(data.token);
        return;
      }
      if (data?.status === 'expired') {
        rememberLoginRequest(null);
        set('renewing', null);
        void start();
        return;
      }
      set(data ? 'waiting' : 'hiccup', current);
      schedule(() => void poll(), (current.poll_seconds || 2) * 1000 * (data ? 1 : 3));
    };
    schedule(() => void poll(), FIRST_POLL_MS);
  }, [schedule, set]);

  useEffect(() => {
    alive.current = true;
    gen.current += 1;
    if (enabled) void start();
    return () => {
      alive.current = false;
      if (timer.current) clearTimeout(timer.current);
      reqRef.current = null;
    };
  }, [enabled, start]);

  return state;
}
