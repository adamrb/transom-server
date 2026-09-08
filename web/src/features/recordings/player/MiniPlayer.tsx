import { Icon, IconButton, LinearProgress } from '@/components';
import { cn } from '@/lib/cn';
import { fmtClock } from '@/lib/format';
import { usePlayer } from './usePlayer';

export interface MiniPlayerProps {
  /** Tap on the title area: open the player sheet. */
  onOpen: () => void;
  className?: string;
}

/**
 * Phone: a 64 px bar above the bottom navigation while a recording is loaded. Title, time /
 * duration, play/pause and close; a thin progress line along the bottom edge. Tapping it opens
 * the full player in a sheet.
 */
export function MiniPlayer({ onOpen, className }: MiniPlayerProps) {
  const [p, store] = usePlayer();
  if (!p.id) return null;
  return (
    <div
      data-mini-player
      className={cn(
        'fixed inset-x-3 z-30 flex h-16 items-center gap-3 overflow-hidden rounded-lg bg-surface-container-high pl-3 pr-2 shadow-e1 dark:bg-surface-container-highest',
        className,
      )}
      style={{ bottom: 'calc(var(--content-bottom-pad, 0px) + 8px)' }}
    >
      <button
        type="button"
        className="flex min-w-0 flex-1 items-center gap-3 text-left focus-ring rounded-md"
        onClick={onOpen}
        aria-label={`Open player: ${p.title}`}
      >
        <span className="inline-grid size-10 shrink-0 place-items-center rounded-md bg-spk1 text-on-spk1">
          <Icon name="graphic_eq" size={20} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-body-m font-medium text-on-surface">{p.title}</span>
          <span className="block text-body-s text-on-surface-variant tnum">
            {fmtClock(p.currentTime)} · {p.duration ? fmtClock(p.duration) : '–:––'}
          </span>
        </span>
      </button>
      <IconButton
        icon={p.playing ? 'pause' : 'play_arrow'}
        label={p.playing ? 'Pause' : 'Play'}
        selected
        onClick={() => store.toggle()}
      />
      <IconButton icon="close" label="Close player" onClick={() => store.reset()} />
      <LinearProgress
        thin
        value={p.duration ? p.currentTime / p.duration : 0}
        label="Position"
        className="absolute inset-x-4 bottom-0 rounded-none bg-transparent"
      />
    </div>
  );
}
