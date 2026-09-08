import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { storage } from '@/lib/storage';

export type ThemeChoice = 'system' | 'light' | 'dark';
export type ResolvedTheme = 'light' | 'dark';

export const THEME_STORAGE_KEY = 'pb_theme';

export interface ThemeContextValue {
  /** What the user (or the URL) chose. */
  theme: ThemeChoice;
  /** What is actually on screen once "system" is resolved. */
  resolved: ResolvedTheme;
  /** Change the theme. Saved to localStorage unless the URL forced one. */
  setTheme: (t: ThemeChoice) => void;
  /** Flip between light and dark (the rail icon button). */
  toggle: () => void;
  /** True when `?theme=` is in the URL (the Android app's choice); then nothing is saved. */
  forced: boolean;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function normalizeTheme(v: string | null | undefined): ThemeChoice {
  return v === 'light' || v === 'dark' ? v : 'system';
}

function readInitial(search: string): { theme: ThemeChoice; forced: boolean } {
  const q = new URLSearchParams(search).get('theme');
  if (q) return { theme: normalizeTheme(q), forced: true };
  const attr = typeof document !== 'undefined' ? document.documentElement.getAttribute('data-theme') : null;
  return { theme: normalizeTheme(attr ?? storage.get(THEME_STORAGE_KEY)), forced: false };
}

function systemDark(): boolean {
  return typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-color-scheme: dark)').matches;
}

export function ThemeProvider({ children, search }: { children: ReactNode; search?: string }) {
  const initial = useMemo(
    () => readInitial(search ?? (typeof location !== 'undefined' ? location.search : '')),
    [search],
  );
  const [theme, setThemeState] = useState<ThemeChoice>(initial.theme);
  const [sysDark, setSysDark] = useState(systemDark);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)');
    if (!mq) return;
    const onChange = (e: MediaQueryListEvent) => setSysDark(e.matches);
    mq.addEventListener?.('change', onChange);
    return () => mq.removeEventListener?.('change', onChange);
  }, []);

  const setTheme = useCallback(
    (t: ThemeChoice) => {
      const next = normalizeTheme(t);
      setThemeState(next);
      // A theme handed over in the URL (the app's) is not the user's saved choice.
      if (!initial.forced) storage.set(THEME_STORAGE_KEY, next);
    },
    [initial.forced],
  );

  const resolved: ResolvedTheme = theme === 'system' ? (sysDark ? 'dark' : 'light') : theme;
  const toggle = useCallback(() => setTheme(resolved === 'dark' ? 'light' : 'dark'), [resolved, setTheme]);

  const value = useMemo<ThemeContextValue>(
    () => ({ theme, resolved, setTheme, toggle, forced: initial.forced }),
    [theme, resolved, setTheme, toggle, initial.forced],
  );
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>');
  return ctx;
}
