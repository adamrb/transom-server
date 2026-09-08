import { createContext, useContext, useEffect, useMemo, type ReactNode } from 'react';

export type SectionKey = 'recordings' | 'automations' | 'settings';

export interface EmbeddedContextValue {
  /** `?embedded=1`: loaded inside the Android app, which supplies tabs, theme and sign-in. */
  embedded: boolean;
  /** `?tab=` when embedded: the section the app wants open. */
  initialTab: SectionKey | null;
  /** Bottom padding content needs so the app's floating tab bar does not cover it (px). */
  bottomPadding: number;
}

const EmbeddedContext = createContext<EmbeddedContextValue>({
  embedded: false,
  initialTab: null,
  bottomPadding: 0,
});

export const EMBEDDED_BOTTOM_PAD = 120;

export function parseEmbedded(search: string): Pick<EmbeddedContextValue, 'embedded' | 'initialTab'> {
  const q = new URLSearchParams(search);
  const embedded = q.has('embedded') && q.get('embedded') !== '0';
  const tab = q.get('tab');
  const initialTab: SectionKey | null =
    tab === 'automations' || tab === 'settings' || tab === 'recordings' ? tab : null;
  return { embedded, initialTab: embedded ? initialTab : null };
}

export function EmbeddedProvider({ children, search }: { children: ReactNode; search?: string }) {
  const value = useMemo<EmbeddedContextValue>(() => {
    const p = parseEmbedded(search ?? window.location.search);
    return { ...p, bottomPadding: p.embedded ? EMBEDDED_BOTTOM_PAD : 0 };
  }, [search]);
  useEffect(() => {
    document.documentElement.toggleAttribute('data-embedded', value.embedded);
  }, [value.embedded]);
  return <EmbeddedContext.Provider value={value}>{children}</EmbeddedContext.Provider>;
}

export function useEmbedded(): EmbeddedContextValue {
  return useContext(EmbeddedContext);
}
