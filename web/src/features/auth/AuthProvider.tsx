import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { AUTH_REQUIRED_EVENT } from '@/api/client';
import { checkToken, signOut as apiSignOut } from '@/api/hooks/auth';
import { isValidToken, tokenStore } from '@/api/token';

export type AuthStatus = 'checking' | 'signed-out' | 'signed-in';

export interface AuthContextValue {
  status: AuthStatus;
  /**
   * Validate a candidate against the server and adopt it on success. Returns true iff adopted.
   * A failed check while already signed in is a no-op, so a bogus login link cannot tear down a
   * working session.
   */
  signIn: (candidate: string) => Promise<boolean>;
  /** Revoke this browser's session (best effort) and forget the token. */
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export interface AuthProviderProps {
  children: ReactNode;
  /** Token from a `#token=` login link, consumed in main.tsx before the router mounted. */
  initialCandidate?: string;
}

export function AuthProvider({ children, initialCandidate = '' }: AuthProviderProps) {
  const qc = useQueryClient();
  const [status, setStatus] = useState<AuthStatus>(() =>
    initialCandidate || tokenStore.get() ? 'checking' : 'signed-out',
  );
  const statusRef = useRef(status);
  statusRef.current = status;
  // Monotonic counter so a superseded check cannot clobber a newer result.
  const attempt = useRef(0);

  const signIn = useCallback(async (candidate: string): Promise<boolean> => {
    if (!isValidToken(candidate)) return false;
    const mine = ++attempt.current;
    const ok = await checkToken(candidate);
    if (mine !== attempt.current) return false;
    if (ok) {
      tokenStore.set(candidate);
      setStatus('signed-in');
    } else if (statusRef.current !== 'signed-in') {
      setStatus('signed-out');
    }
    return ok;
  }, []);

  const signOut = useCallback(async () => {
    attempt.current++;
    await apiSignOut();
    qc.clear();
    setStatus('signed-out');
  }, [qc]);

  // Boot: a login-link candidate wins over the stored token (the old dashboard did the same).
  useEffect(() => {
    const candidate = initialCandidate || tokenStore.get() || '';
    if (candidate) void signIn(candidate);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The server said 401 (a revoked session, a rotated token): back to the gate.
  useEffect(() => {
    const onRequired = () => {
      attempt.current++;
      setStatus('signed-out');
    };
    window.addEventListener(AUTH_REQUIRED_EVENT, onRequired);
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, onRequired);
  }, []);

  // Signed out (or in) from another tab: tokenStore relays the browser's `storage` event.
  useEffect(
    () =>
      tokenStore.subscribe((t, source) => {
        if (source !== 'storage') return; // our own set/clear already updated the status
        if (!t) setStatus((s) => (s === 'signed-in' ? 'signed-out' : s));
        else if (statusRef.current === 'signed-out') void signIn(t);
      }),
    [signIn],
  );

  const value = useMemo<AuthContextValue>(() => ({ status, signIn, signOut }), [status, signIn, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
