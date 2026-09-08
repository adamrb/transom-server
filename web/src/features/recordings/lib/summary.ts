/**
 * Summary and title helpers, ported from the vanilla dashboard (`cleanTitle`, `cleanSummary`,
 * `titleOf`) so titles and summaries read exactly as before.
 */
import type { Recording } from '@/api';

/** Plain-text title from a summary's first line: no heading marks, bold marks or "Title:" label. */
export function cleanTitle(line: string): string {
  return line
    .replace(/^#+\s*/, '')
    .replace(/\*\*/g, '')
    .replace(/^\s*title\s*:\s*/i, '')
    .trim();
}

/** The name a recording shows: its title, "Silent recording", the summary's first line, or the file name. */
export function titleOf(rec: Pick<Recording, 'title' | 'no_speech' | 'summary' | 'filename'>): string {
  if (rec.title) return rec.title;
  if (rec.no_speech) return 'Silent recording';
  if (rec.summary) {
    for (const raw of rec.summary.split('\n')) {
      const l = cleanTitle(raw);
      if (l) return l;
    }
  }
  return rec.filename || 'Recording';
}

// Summaries from older prompts open with a "Summary" heading (the card already says that) and
// carry "Action Items: none" style sections. Both go.
const FILLER_RE =
  /^\s*[-*•]?\s*\(?\s*(none|n\/a|no (specific |explicit )?(action items?|highlights?|next steps?|decisions?|tasks?)( were)?( requested| identified| mentioned| noted| discussed)?[^.]*|nothing (to note|specific)[^.]*)\.?\)?\s*$/i;
const LIST_HEAD = /^(action items?|highlights?|next steps?|decisions?|tasks?|to-?dos?|follow-?ups?)$/i;
const OPENER =
  /^\s*[-*•]?\s*\(?\s*(none|n\/a|no (specific |explicit |clear )?(action items?|highlights?|next steps?|decisions?|tasks?|to-?dos?|follow-?ups?)\b|nothing (to note|specific|actionable)|there (are|were) no\b)/i;
const PLAIN_LABEL =
  /^(action items?|highlights?|next steps?|decisions?|tasks?|to-?dos?|follow-?ups?)\s*:\s*$/i;

const isHeading = (l: string) => /^#{1,6}\s+/.test(l) || /^\*\*[^*]+\*\*:?\s*$/.test(l.trim());
const headingText = (l: string) =>
  l
    .replace(/^#{1,6}\s+/, '')
    .replace(/\*\*/g, '')
    .replace(/:$/, '')
    .trim();

/**
 * Strip a leading "Summary" heading (and a "Title:" line) and drop sections that only say
 * there is nothing to report ("Action items: none"). Identical to the old dashboard.
 */
export function cleanSummary(text: string | null | undefined): string {
  const lines = (text || '').split('\n');
  for (let pass = 0; pass < 2; pass++) {
    let i = 0;
    while (i < lines.length && !lines[i].trim()) i++;
    if (
      i < lines.length &&
      ((isHeading(lines[i]) && /^summary$/i.test(headingText(lines[i]))) ||
        /^\s*(\*\*)?title(\*\*)?\s*:/i.test(lines[i]))
    )
      lines.splice(i, 1);
    else break;
  }
  const isBoundary = (l: string) => isHeading(l) || PLAIN_LABEL.test(l.trim());
  const out: string[] = [];
  for (let k = 0; k < lines.length; k++) {
    const plainHead = PLAIN_LABEL.test(lines[k].trim());
    if (isHeading(lines[k]) || plainHead) {
      let j = k + 1;
      const body: string[] = [];
      while (j < lines.length && !isBoundary(lines[j])) {
        body.push(lines[j]);
        j++;
      }
      const meaningful = body.filter((l) => l.trim());
      const listHead = plainHead || LIST_HEAD.test(headingText(lines[k]));
      const filler =
        !meaningful.length ||
        meaningful.every((l) => FILLER_RE.test(l)) ||
        (listHead &&
          OPENER.test(meaningful[0]) &&
          !meaningful.slice(1).some((l) => /^\s*[-*•]\s+/.test(l) && !FILLER_RE.test(l)));
      if (filler) {
        k = j - 1;
        continue;
      }
    }
    out.push(lines[k]);
  }
  return out
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}
