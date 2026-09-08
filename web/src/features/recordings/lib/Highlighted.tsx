import { Fragment, type ReactNode } from 'react';
import { escapeRegExp } from './transcript';

export interface HighlightedProps {
  text: string;
  /** Case-insensitive term to mark; empty renders the plain text. */
  term: string;
  /** Index (within this text) of the match to mark as current, -1 for none. */
  current?: number;
}

/**
 * Text with every occurrence of `term` wrapped in <mark> (the search snippet in a list row, the
 * find-in-transcript hits). The current find hit gets `data-current` and the solid amber look.
 */
export function Highlighted({ text, term, current = -1 }: HighlightedProps) {
  const t = term.trim();
  if (!t) return <>{text}</>;
  const re = new RegExp(escapeRegExp(t), 'ig');
  const out: ReactNode[] = [];
  let last = 0;
  let i = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(<Fragment key={`t${last}`}>{text.slice(last, m.index)}</Fragment>);
    const cur = i === current;
    out.push(
      <mark
        key={`m${m.index}`}
        data-current={cur || undefined}
        className={
          cur
            ? 'rounded-[3px] bg-warning px-0.5 text-on-primary'
            : 'rounded-[3px] bg-warning-container px-0.5 text-on-warning-container'
        }
      >
        {m[0]}
      </mark>,
    );
    last = m.index + m[0].length;
    i++;
    if (!m[0]) re.lastIndex++;
  }
  if (last < text.length) out.push(<Fragment key={`t${last}`}>{text.slice(last)}</Fragment>);
  return <>{out}</>;
}
