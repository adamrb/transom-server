/**
 * Formatting helpers, ported verbatim from the vanilla dashboard so list rows, exports and
 * copy text read exactly as before.
 */

/** `16s`, `4m 12s`, `2h 19m`. Empty for null. */
export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return '';
  const s = Math.round(seconds);
  if (s >= 3600) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  if (s >= 60) return `${Math.floor(s / 60)}m ${s % 60}s`;
  return `${s}s`;
}

/** `21.8 MB`, `412 kB`. */
export function fmtSize(bytes: number | null | undefined): string {
  if (bytes == null || Number.isNaN(bytes)) return '';
  return bytes >= 1e6 ? `${(bytes / 1e6).toFixed(1)} MB` : `${Math.round(bytes / 1e3)} kB`;
}

/** Player clock: `0:05`, `4:12`, `1:09:53`. */
export function fmtClock(seconds: number | null | undefined): string {
  const s = Math.round(Number(seconds) || 0);
  const two = (n: number) => String(n).padStart(2, '0');
  return s >= 3600
    ? `${Math.floor(s / 3600)}:${two(Math.floor((s % 3600) / 60))}:${two(s % 60)}`
    : `${Math.floor(s / 60)}:${two(s % 60)}`;
}

export const sameDay = (a: Date, b: Date) =>
  a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

/** `Today`, `Yesterday`, or null. */
export function dayWord(d: Date, now: Date = new Date()): string | null {
  if (sameDay(d, now)) return 'Today';
  const y = new Date(now);
  y.setDate(now.getDate() - 1);
  if (sameDay(d, y)) return 'Yesterday';
  return null;
}

export function fmtTime(d: Date): string {
  return d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}

export function fmtDay(
  d: Date,
  { weekday = false, now = new Date() }: { weekday?: boolean; now?: Date } = {},
): string {
  const opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' };
  if (weekday) opts.weekday = 'short';
  if (d.getFullYear() !== now.getFullYear()) opts.year = 'numeric';
  return d.toLocaleDateString(undefined, opts);
}

export function parseDate(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** `Today 12:25 AM`, `Yesterday 6:47 PM`, `Sep 3, 6:47 PM`. */
export function fmtWhen(iso: string | null | undefined, now: Date = new Date()): string {
  const d = parseDate(iso);
  if (!d) return '';
  const word = dayWord(d, now);
  return word ? `${word} ${fmtTime(d)}` : `${fmtDay(d, { now })}, ${fmtTime(d)}`;
}

/** Day-group header for the recordings list: `Today`, `Yesterday`, `Sun, Sep 6`, `Dec 24, 2025`. */
export function fmtDayHeader(iso: string | null | undefined, now: Date = new Date()): string {
  const d = parseDate(iso);
  if (!d) return '';
  return dayWord(d, now) ?? fmtDay(d, { weekday: true, now });
}

/** Plural helper: `1 recording`, `3 recordings`. */
export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}
