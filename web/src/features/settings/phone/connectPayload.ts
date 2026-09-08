/**
 * What the "Connect a phone" QR encodes, byte for byte what the old dashboard's `openConnect`
 * produced: `{"v":1,"url":<origin>,"token":<token>}`. The Android app parses exactly this.
 */
export function connectPayload(origin: string, token: string): string {
  return JSON.stringify({ v: 1, url: origin, token });
}

/** The sign-in link: opens the dashboard already signed in (the fragment never reaches the server). */
export function loginLink(origin: string, token: string): string {
  return `${origin}/#token=${encodeURIComponent(token)}`;
}
