/** Join class names, skipping falsy values. */
export function cn(...parts: Array<string | false | null | undefined | 0>): string {
  let out = '';
  for (const p of parts) if (p) out += (out ? ' ' : '') + p;
  return out;
}
