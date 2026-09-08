import { memo } from 'react';
import { Icon } from '@/components';
import type { Paragraph } from '@/api';
import { cn } from '@/lib/cn';
import { fmtClock } from '@/lib/format';
import { Highlighted } from '../lib/Highlighted';
import { SpeakerPill } from './SpeakerPill';

export interface TranscriptParagraphProps {
  index: number;
  paragraph: Paragraph;
  /** Show the speaker pill (the speaker changed). */
  showSpeaker: boolean;
  tone: number;
  now: boolean;
  flash: boolean;
  /** Find term and, when a hit in this paragraph is the current one, its index within it. */
  find: string;
  currentMatch: number;
  onSeek: (seconds: number) => void;
  onRenameSpeaker: (name: string) => void;
}

/**
 * One speaker turn. The speaker pill appears only on a speaker change; the time + play pill shows
 * in the top-right corner on hover (always, as a small chip, on phone); bookmarked paragraphs carry
 * an amber bar and a star; the now-playing paragraph is tinted. No timestamps in the text itself.
 */
export const TranscriptParagraph = memo(function TranscriptParagraph({
  index,
  paragraph: p,
  showSpeaker,
  tone,
  now,
  flash,
  find,
  currentMatch,
  onSeek,
  onRenameSpeaker,
}: TranscriptParagraphProps) {
  const start = Number(p.start) || 0;
  const marked = p.bookmarks.length > 0;
  return (
    <div
      id={`para-${index}`}
      data-paragraph={index}
      data-start={start}
      data-now={now || undefined}
      className={cn(
        // Desktop reserves a right column for the time + play chip so text never runs under it.
        // A jump lands the paragraph flush under the app bar (no sliver of the one before it).
        'group relative rounded-md py-1.5 pr-3 pl-3.5 transition-colors [scroll-margin-block:0px_160px] md:pr-24',
        now && 'bg-selection-tint',
        flash ? 'bg-warning-container duration-0' : 'duration-[1500ms]',
      )}
    >
      {p.bookmarks.map((b) => (
        <span key={b} id={`bookmark-${b}`} className="absolute -top-2" aria-hidden />
      ))}
      {marked && (
        <span aria-hidden className="absolute top-2.5 bottom-2 left-0 w-1 rounded-full bg-highlight-bar" />
      )}
      <button
        type="button"
        title="Play from here"
        aria-label={`Play from ${fmtClock(start)}`}
        onClick={() => onSeek(start)}
        className={cn(
          'inline-flex h-7 items-center gap-1 rounded-full bg-surface-container-high pr-2.5 pl-1.5 text-[12px] text-on-surface-variant tnum focus-ring',
          // Desktop: in the corner, on hover (always, where no pointer can hover). Phone: a chip floated right.
          'md:absolute md:top-1.5 md:right-2 md:opacity-0 md:transition-opacity md:dur-short md:group-hover:opacity-100 md:focus-visible:opacity-100 md:[@media(hover:none)]:opacity-100',
          showSpeaker && 'md:top-[22px]',
          'max-md:float-right max-md:mb-0.5 max-md:ml-2 max-md:h-6 max-md:text-[11px]',
          showSpeaker && 'max-md:mt-4',
        )}
      >
        <Icon name="play_arrow" size={16} />
        {fmtClock(start)}
      </button>
      {showSpeaker && p.speaker && (
        <div className="mt-3.5 mb-1.5">
          <SpeakerPill name={p.speaker} tone={tone} onClick={() => onRenameSpeaker(p.speaker!)} />
        </div>
      )}
      <p className="m-0 text-transcript text-on-surface-body">
        {marked && <Icon name="star_fill" size={14} className="mr-1.5 -mt-0.5 text-warning" />}
        <Highlighted text={p.text} term={find} current={currentMatch} />
      </p>
    </div>
  );
});
