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
import { cn } from '@/lib/cn';

export interface SnackbarAction {
  label: string;
  onClick: () => void;
}

export interface SnackbarOptions {
  /** error snackbars stay a little longer (4 s vs 2.2 s), like the old toasts. */
  kind?: 'default' | 'error';
  action?: SnackbarAction;
  /** ms; default by kind. */
  duration?: number;
}

export interface SnackbarApi {
  /** Show a short confirmation ("Transcript copied"). Replaces any visible snackbar. */
  show: (message: string, options?: SnackbarOptions) => void;
  /** Convenience for failures: user words only, never status codes. */
  error: (message: string) => void;
  hide: () => void;
}

interface Snack extends SnackbarOptions {
  id: number;
  message: string;
}

const SnackbarContext = createContext<SnackbarApi | null>(null);

export function SnackbarProvider({ children }: { children: ReactNode }) {
  const [snack, setSnack] = useState<Snack | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const seq = useRef(0);

  const hide = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    setSnack(null);
  }, []);

  const show = useCallback((message: string, options: SnackbarOptions = {}) => {
    if (timer.current) clearTimeout(timer.current);
    const id = ++seq.current;
    setSnack({ id, message, ...options });
    const duration = options.duration ?? (options.kind === 'error' ? 4000 : options.action ? 5000 : 2200);
    timer.current = setTimeout(() => setSnack((s) => (s?.id === id ? null : s)), duration);
  }, []);

  const api = useMemo<SnackbarApi>(
    () => ({ show, hide, error: (m) => show(m, { kind: 'error' }) }),
    [show, hide],
  );
  useEffect(() => () => hide(), [hide]);

  return (
    <SnackbarContext.Provider value={api}>
      {children}
      <SnackbarHost snack={snack} onHide={hide} />
    </SnackbarContext.Provider>
  );
}

export function useSnackbar(): SnackbarApi {
  const ctx = useContext(SnackbarContext);
  if (!ctx) throw new Error('useSnackbar must be used inside <SnackbarProvider>');
  return ctx;
}

/**
 * The single on-screen snackbar: inverse surface, 48 px, bottom centre. Its bottom offset follows
 * `--snackbar-bottom` (set by the shell: 24 px desktop, above the bottom nav on phone, 140 px
 * embedded) so it never hides behind navigation or the Android app's tab bar.
 */
export function SnackbarHost({ snack, onHide }: { snack: Snack | null; onHide: () => void }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!snack) {
      setVisible(false);
      return;
    }
    const raf = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(raf);
  }, [snack]);
  return (
    <div
      role="status"
      aria-live="polite"
      data-kind={snack?.kind ?? 'default'}
      className={cn(
        'pointer-events-none fixed left-1/2 z-[60] flex h-12 max-w-[calc(100vw-32px)] items-center gap-2 rounded-sm px-4 text-body-m shadow-e3',
        'bottom-(--snackbar-bottom,24px) -translate-x-1/2 transition-[opacity,transform] dur-medium ease-emph-decel',
        snack?.kind === 'error'
          ? 'bg-error-container text-on-error-container'
          : 'bg-inverse-surface text-inverse-on-surface',
        snack && visible ? 'translate-y-0 opacity-100' : 'translate-y-4 opacity-0',
      )}
    >
      {snack && (
        <>
          <span className="truncate">{snack.message}</span>
          {snack.action && (
            <button
              type="button"
              className="pointer-events-auto h-9 rounded-sm px-2 font-medium underline underline-offset-2 hover:bg-state-hover focus-ring"
              onClick={() => {
                // Hide first so an action that shows another snackbar ("Restored") is not wiped.
                onHide();
                snack.action?.onClick();
              }}
            >
              {snack.action.label}
            </button>
          )}
        </>
      )}
    </div>
  );
}
