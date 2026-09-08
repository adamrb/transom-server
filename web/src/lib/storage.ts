/**
 * localStorage / sessionStorage that never throws (private mode, WebView quirks, blocked storage).
 *
 * Keys used by the app (keep this list current; the Android app and the old dashboard share them):
 *   localStorage  pb_token   the bearer token
 *                 pb_theme   system | light | dark
 *                 pb_speed   playback speed (1 | 1.5 | 2)
 *   sessionStorage pb_login_req         the pending QR login request {id, expires_at, poll_seconds}
 *                  pb.routeKey.<recId>   idempotency key of an in-flight "run automations"
 *                  pb.routeInstr.<recId> instructions typed for a re-run, kept across a reload
 */
function safe(kind: 'local' | 'session'): Storage | null {
  try {
    const s = kind === 'local' ? window.localStorage : window.sessionStorage;
    // Some WebViews expose the object but throw on access.
    s.getItem('__probe__');
    return s;
  } catch {
    return null;
  }
}

function make(kind: 'local' | 'session') {
  return {
    get(key: string): string | null {
      try {
        return safe(kind)?.getItem(key) ?? null;
      } catch {
        return null;
      }
    },
    set(key: string, value: string): void {
      try {
        safe(kind)?.setItem(key, value);
      } catch {
        /* ignore */
      }
    },
    remove(key: string): void {
      try {
        safe(kind)?.removeItem(key);
      } catch {
        /* ignore */
      }
    },
    getJSON<T>(key: string): T | null {
      const raw = this.get(key);
      if (raw == null) return null;
      try {
        return JSON.parse(raw) as T;
      } catch {
        return null;
      }
    },
    setJSON(key: string, value: unknown): void {
      this.set(key, JSON.stringify(value));
    },
  };
}

export const storage = make('local');
export const session = make('session');

export const STORAGE_KEYS = {
  token: 'pb_token',
  theme: 'pb_theme',
  speed: 'pb_speed',
  loginRequest: 'pb_login_req',
  routeKey: (recId: string) => `pb.routeKey.${recId}`,
  routeInstructions: (recId: string) => `pb.routeInstr.${recId}`,
} as const;
