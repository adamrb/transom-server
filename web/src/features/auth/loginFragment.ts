import { isValidToken } from '@/api/token';

/**
 * Login link: `/#token=<value>` unlocks without typing (fragments are never sent to the server).
 * Any `#token` fragment is scrubbed from the URL and history immediately, even when malformed,
 * so a rejected secret never lingers. The candidate is decoded and validated but NOT adopted
 * here: the auth provider adopts it only after the server confirms it.
 *
 * Must run before the HashRouter mounts (it would otherwise read `token=…` as a route).
 * Returns the candidate token, or '' if the fragment is absent, malformed, or fails the grammar.
 */
export function consumeLoginFragment(
  loc: Location = window.location,
  hist: History = window.history,
): string {
  const m = loc.hash.match(/^#\/?token=(.*)$/);
  if (!m) return '';
  hist.replaceState(null, '', loc.pathname + loc.search);
  let candidate = '';
  try {
    candidate = decodeURIComponent(m[1]);
  } catch {
    candidate = '';
  }
  return isValidToken(candidate) ? candidate : '';
}
