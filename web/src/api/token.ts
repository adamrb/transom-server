import { storage, STORAGE_KEYS } from '@/lib/storage';

/**
 * The bearer token (localStorage `pb_token`), with change notifications for the auth provider.
 * A token is any run of printable non-space ASCII up to 512 chars, so it is always a legal header.
 */
export const TOKEN_RE = /^[\x21-\x7e]{1,512}$/;

/** `local` = this tab called set/clear; `storage` = another tab changed it (browser storage event). */
export type TokenSource = 'local' | 'storage';
type Listener = (token: string | null, source: TokenSource) => void;
const listeners = new Set<Listener>();
const notify = (token: string | null, source: TokenSource) => listeners.forEach((l) => l(token, source));

// Another tab signing in or out changes localStorage without going through this module; the
// browser tells us with a `storage` event (key null = storage cleared).
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key === STORAGE_KEYS.token || e.key === null) notify(tokenStore.get(), 'storage');
  });
}

export const tokenStore = {
  get(): string | null {
    const t = storage.get(STORAGE_KEYS.token);
    return t && TOKEN_RE.test(t) ? t : null;
  },
  set(token: string): void {
    storage.set(STORAGE_KEYS.token, token);
    notify(token, 'local');
  },
  clear(): void {
    storage.remove(STORAGE_KEYS.token);
    notify(null, 'local');
  },
  subscribe(l: Listener): () => void {
    listeners.add(l);
    return () => listeners.delete(l);
  },
};

export function isValidToken(candidate: string): boolean {
  return TOKEN_RE.test(candidate);
}
