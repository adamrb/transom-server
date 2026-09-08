/**
 * "Jump to" entries: back to top, the bookmarks (highlights), speaker changes and, on long
 * recordings, every 10 minutes. Each points at a paragraph to reveal (and, for a bookmark, the
 * moment to play from).
 */
import type { Paragraph, Recording, Transcript } from '@/api';
import { fmtClock } from '@/lib/format';
import { paragraphsOf, speakerChanges } from './transcript';

export type JumpItem =
  | { kind: 'top'; label: string }
  | { kind: 'bookmark'; label: string; time: string; bookmark: number; at: number; paragraph: number }
  | { kind: 'paragraph'; label: string; time: string; paragraph: number };

export interface JumpSection {
  label?: string;
  items: JumpItem[];
}

const TEN_MINUTES = 600;

export function buildJumpSections(
  rec: Pick<Recording, 'duration_s'> | null | undefined,
  transcript: Transcript | null | undefined,
): JumpSection[] {
  const sections: JumpSection[] = [{ items: [{ kind: 'top', label: 'Back to top' }] }];
  if (!transcript) return sections;
  const paras: Paragraph[] = paragraphsOf(transcript);
  const bookmarkParagraph = new Map<number, number>();
  paras.forEach((p, i) => p.bookmarks.forEach((b) => bookmarkParagraph.set(b, i)));

  if (transcript.highlights.length) {
    sections.push({
      label: 'Highlights',
      items: transcript.highlights.map((h, i) => ({
        kind: 'bookmark',
        label: (h.text || '').slice(0, 60) || 'Bookmark',
        time: fmtClock(h.at),
        bookmark: i,
        at: Number(h.start) || 0,
        paragraph: bookmarkParagraph.get(i) ?? -1,
      })),
    });
  }
  const changes = speakerChanges(paras);
  if (changes.length > 1) {
    sections.push({
      label: 'Speaker changes',
      items: changes.map((i) => ({
        kind: 'paragraph',
        label: paras[i].speaker ?? '',
        time: fmtClock(paras[i].start ?? 0),
        paragraph: i,
      })),
    });
  }
  const dur = Number(rec?.duration_s) || (paras.length ? Number(paras[paras.length - 1].end) || 0 : 0);
  if (paras.length && dur >= 2 * TEN_MINUTES) {
    const items: JumpItem[] = [];
    for (let t = TEN_MINUTES; t < dur; t += TEN_MINUTES) {
      const idx = paras.findIndex((p) => (Number(p.start) || 0) >= t);
      if (idx < 0) break;
      items.push({
        kind: 'paragraph',
        label: paras[idx].text.slice(0, 50),
        time: fmtClock(t),
        paragraph: idx,
      });
    }
    if (items.length) sections.push({ label: 'Every 10 minutes', items });
  }
  return sections;
}
