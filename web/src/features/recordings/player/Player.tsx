import { useState, type ReactNode } from 'react';
import { Card, IconButton, SkipIcon, Slider } from '@/components';
import { cn } from '@/lib/cn';
import { fmtClock } from '@/lib/format';
import { SKIP_BACK_S, SKIP_FORWARD_S, SPEEDS, type Speed } from './playerStore';
import { usePlayer } from './usePlayer';

export interface PlayerProps {
  /** docked: the card at the bottom of the detail pane. sheet: inside the phone player sheet. */
  variant?: 'docked' | 'sheet';
  /** Rendered at the right of the transport row (the Jump to button). */
  trailing?: ReactNode;
  className?: string;
}

/**
 * Slider with bookmark markers and the buffered range, time / duration, speed chips, then
 * 15 s back · play/pause (56 px) · 30 s forward. Reads and drives the shared player store.
 */
export function Player({ variant = 'docked', trailing, className }: PlayerProps) {
  const [p, store] = usePlayer();
  const [drag, setDrag] = useState<number | null>(null);
  const shown = drag ?? p.currentTime;
  const max = p.duration || 0;
  const body = (
    <>
      <Slider
        label="Position"
        value={Math.min(shown, max || shown)}
        max={max || 1}
        step={0.1}
        markers={p.markers}
        buffered={p.buffered}
        disabled={!p.id}
        formatValue={fmtClock}
        onChange={(v) => {
          setDrag(v);
          store.preview(v);
        }}
        onCommit={(v) => {
          setDrag(null);
          void store.seek(v, { autoplay: false });
        }}
      />
      <div className="mt-1 flex items-center gap-2">
        <span className="min-w-[62px] text-[13px] text-on-surface-variant tnum">{fmtClock(shown)}</span>
        <div
          className="flex flex-1 items-center justify-center gap-1.5"
          role="radiogroup"
          aria-label="Playback speed"
        >
          {SPEEDS.map((s) => (
            <SpeedChip key={s} speed={s} selected={p.speed === s} onSelect={() => store.setSpeed(s)} />
          ))}
        </div>
        <span className="min-w-[62px] text-right text-[13px] text-on-surface-variant tnum">
          {max ? fmtClock(max) : '–:––'}
        </span>
      </div>
      <div className="relative mt-1.5 flex items-center justify-center gap-5">
        <IconButton
          label={`Back ${SKIP_BACK_S} seconds`}
          className="text-on-surface"
          onClick={() => store.skip(-SKIP_BACK_S)}
        >
          <SkipIcon seconds={SKIP_BACK_S} direction="back" />
        </IconButton>
        <IconButton
          icon={p.playing ? 'pause' : 'play_arrow'}
          label={p.playing ? 'Pause' : 'Play'}
          variant="filled"
          size="lg"
          aria-busy={p.loading || undefined}
          className={cn(p.loading && 'animate-pulse')}
          onClick={() => store.toggle()}
        />
        <IconButton
          label={`Forward ${SKIP_FORWARD_S} seconds`}
          className="text-on-surface"
          onClick={() => store.skip(SKIP_FORWARD_S)}
        >
          <SkipIcon seconds={SKIP_FORWARD_S} direction="forward" />
        </IconButton>
        {trailing && <div className="absolute right-0 top-1/2 -translate-y-1/2">{trailing}</div>}
      </div>
    </>
  );
  if (variant === 'sheet') return <div className={cn('px-2 pb-2', className)}>{body}</div>;
  return (
    <Card
      tone="high"
      elevation={2}
      padding="none"
      role="region"
      aria-label="Player"
      className={cn('rounded-xl px-5 pt-3 pb-3.5 max-md:px-4', className)}
    >
      {body}
    </Card>
  );
}

function SpeedChip({ speed, selected, onSelect }: { speed: Speed; selected: boolean; onSelect: () => void }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onSelect}
      className={cn(
        'h-8 rounded-full px-3 text-[13px] font-medium transition-colors dur-medium focus-ring tnum',
        selected
          ? 'bg-secondary-container text-on-secondary-container dark:bg-primary dark:text-on-primary'
          : 'bg-surface-container-high text-on-surface-variant hover:bg-surface-container-highest dark:bg-surface-container-highest',
      )}
    >
      {speed}x
    </button>
  );
}
