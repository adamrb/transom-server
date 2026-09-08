/**
 * The vanilla dashboard used bare hashes: `#rec/<id>`, `#automations`, `#settings`. The router
 * uses `#/rec/<id>`, `#/automations`, `#/settings`. Old links and the Android app's deep links keep
 * working: this rewrites the hash in place (replaceState, no history entry) before the router
 * mounts. Returns the new hash, or null when nothing changed.
 */
export function normalizeLegacyHash(
  loc: Location = window.location,
  hist: History = window.history,
): string | null {
  const m = loc.hash.match(/^#(rec\/.+|automations|settings)$/);
  if (!m) return null;
  const next = `#/${m[1]}`;
  hist.replaceState(hist.state, '', loc.pathname + loc.search + next);
  return next;
}
