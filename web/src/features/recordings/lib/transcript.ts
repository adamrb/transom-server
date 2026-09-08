/**
 * Transcript helpers: the reader-layout paragraphs, the plain-text copy builder (identical to the
 * old dashboard's `transcriptPlainText`), speaker tone indexes and text matching.
 */
import type { Paragraph, Transcript } from '@/api';

/**
 * The server's paragraphs (one per speaker turn, split at long pauses). Older documents without
 * paragraphs fall back to grouping the raw segments by speaker, as the old dashboard did.
 */
export function paragraphsOf(t: Transcript | null | undefined): Paragraph[] {
  if (!t) return [];
  if (t.paragraphs.length) return t.paragraphs;
  const paras: Paragraph[] = [];
  for (const s of t.segments) {
    const text = (s.text || '').trim();
    if (!text) continue;
    const last = paras[paras.length - 1];
    const speaker = s.speaker || null;
    if (last && last.speaker === speaker) {
      last.text += ' ' + text;
      last.end = s.end;
    } else paras.push({ speaker, text, start: s.start, end: s.end, bookmarks: [] });
  }
  return paras;
}

/** Clipboard text: "Speaker: paragraph" blocks separated by blank lines, never timestamps. */
export function transcriptPlainText(t: Transcript | null | undefined): string {
  const paras = t?.paragraphs;
  if (paras && paras.length)
    return paras.map((p) => (p.speaker ? p.speaker + ': ' : '') + p.text).join('\n\n');
  return t?.text || '';
}

/** Whether there is anything to read (or copy). */
export function transcriptHasText(t: Transcript | null | undefined): boolean {
  return !!t && !t.no_speech && (paragraphsOf(t).length > 0 || (t.text || '').trim().length > 0);
}

/**
 * Speaker tones (1..4) keyed by the ORIGINAL engine label in first-appearance order, so a speaker
 * keeps its colour after a rename. Paragraph labels are the current names; `speaker_names` maps
 * original label → current name, so a current name resolves back to the earliest original.
 */
export function speakerTones(t: Transcript): Map<string, number> {
  const currentToOriginal = new Map<string, string>();
  for (const [orig, name] of Object.entries(t.speaker_names))
    if (!currentToOriginal.has(name)) currentToOriginal.set(name, orig);
  const originals: string[] = [];
  const tones = new Map<string, number>();
  for (const p of paragraphsOf(t)) {
    if (!p.speaker || tones.has(p.speaker)) continue;
    const orig = currentToOriginal.get(p.speaker) ?? p.speaker;
    let idx = originals.indexOf(orig);
    if (idx < 0) {
      originals.push(orig);
      idx = originals.length - 1;
    }
    tones.set(p.speaker, (idx % 4) + 1);
  }
  return tones;
}

/** Paragraph indexes where the speaker changes (the first labelled paragraph counts). */
export function speakerChanges(paras: Paragraph[]): number[] {
  const out: number[] = [];
  let prev: string | null = null;
  paras.forEach((p, i) => {
    if (p.speaker && p.speaker !== prev) out.push(i);
    if (p.speaker) prev = p.speaker;
  });
  return out;
}

export function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Case-insensitive occurrences of `term` in `text`. */
export function countMatches(text: string, term: string): number {
  const t = term.trim();
  if (!t) return 0;
  const re = new RegExp(escapeRegExp(t), 'ig');
  let n = 0;
  while (re.exec(text)) n++;
  return n;
}

/** Index of the paragraph playing at `time` (the last one starting at or before it), or -1. */
export function paragraphAt(starts: number[], time: number): number {
  let lo = 0;
  let hi = starts.length - 1;
  let idx = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (starts[mid] <= time) {
      idx = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return idx;
}
