import { Card, Icon } from '@/components';
import type { Highlight } from '@/api';
import { fmtClock } from '@/lib/format';

export interface HighlightsCardProps {
  highlights: Highlight[];
  /** Reveal the bookmarked paragraph and play from the press. */
  onJump: (index: number, highlight: Highlight) => void;
}

/** The recorder's button presses: a star, the time, and the words spoken around it. */
export function HighlightsCard({ highlights, onJump }: HighlightsCardProps) {
  if (!highlights.length) return null;
  return (
    <Card
      id="sec-highlights"
      title={
        <>
          Highlights{' '}
          <span className="ml-1 text-body-s font-normal text-on-surface-variant">marked on the recorder</span>
        </>
      }
    >
      <ul className="m-0 -mx-2 list-none p-0">
        {highlights.map((h, i) => (
          <li key={i}>
            <button
              type="button"
              title="Jump to this spot in the transcript and play"
              onClick={() => onJump(i, h)}
              className="flex w-full items-center gap-3 rounded-md px-2 py-2 text-left hover:bg-state-hover focus-ring"
            >
              <span className="inline-flex w-[84px] shrink-0 items-center gap-1 text-[13px] font-medium text-warning tnum">
                <Icon name="star_fill" size={16} />
                {fmtClock(h.at)}
              </span>
              <span className="flex-1 text-[15px] leading-[22px] text-on-surface-body">
                {h.text || <span className="text-on-surface-variant">(no speech near this mark)</span>}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
