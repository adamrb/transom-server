import { toQR } from 'toqr';

/**
 * QR code as an SVG path, same encoder (toqr, EC level M) and same quiet zone as the vanilla
 * dashboard, so the phone app scans identical codes. Always black on white regardless of theme:
 * scanners want contrast, and the card behind it is light in the mockup.
 */
export interface QrModel {
  /** modules per side */
  size: number;
  /** SVG path data drawing every dark module as a 1×1 square */
  path: string;
  /** quiet zone in modules */
  quiet: number;
}

export function qrModel(text: string, quiet = 4): QrModel {
  const m = toQR(text, 0 /* M */);
  const n = Math.round(Math.sqrt(m.length));
  let d = '';
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) if (m[y * n + x]) d += `M${x} ${y}h1v1h-1z`;
  return { size: n, path: d, quiet };
}

/** The JSON the phone app expects inside a sign-in QR. */
export function loginQrPayload(origin: string, requestId: string): string {
  return JSON.stringify({ v: 1, kind: 'login', url: origin, id: requestId });
}
