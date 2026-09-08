import { useEffect, useState } from 'react';

/**
 * One breakpoint, matching the mockup: ≥ 840 px is "desktop" (navigation rail, two-pane
 * recordings, popover menus); below it is "phone" (bottom navigation, full-screen detail,
 * bottom sheets). Tailwind: use the `md:` variant (840px) for the same split.
 */
export const DESKTOP_MIN_PX = 840;
export const DESKTOP_QUERY = `(min-width: ${DESKTOP_MIN_PX}px)`;
/** Between 840 and 1099 the recordings list pane narrows to 340 px. */
export const NARROW_DESKTOP_QUERY = `(min-width: ${DESKTOP_MIN_PX}px) and (max-width: 1099px)`;

export function useMediaQuery(query: string): boolean {
  const get = () =>
    typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(query).matches : false;
  const [matches, setMatches] = useState(get);
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mq = window.matchMedia(query);
    const onChange = (e: MediaQueryListEvent) => setMatches(e.matches);
    setMatches(mq.matches);
    mq.addEventListener?.('change', onChange);
    return () => mq.removeEventListener?.('change', onChange);
  }, [query]);
  return matches;
}

/** True at ≥ 840 px. */
export function useIsDesktop(): boolean {
  return useMediaQuery(DESKTOP_QUERY);
}

/** True below 840 px. */
export function useIsPhone(): boolean {
  return !useIsDesktop();
}
