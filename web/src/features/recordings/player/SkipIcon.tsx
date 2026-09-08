import { Icon } from '@/components';
import { cn } from '@/lib/cn';

/**
 * The 15 s back / 30 s forward glyph: the Material `replay` arrow (mirrored for forward) with the
 * number of seconds inside, as the mockup draws it. Material Symbols has no replay_15.
 */
export function SkipIcon({ seconds, direction }: { seconds: number; direction: 'back' | 'forward' }) {
  return (
    <span className="relative inline-grid size-6 place-items-center">
      <Icon
        name="replay"
        size={24}
        className={cn('absolute inset-0', direction === 'forward' && '-scale-x-100')}
      />
      <span aria-hidden className="relative pt-[3px] text-[8px] leading-none font-bold tnum">
        {seconds}
      </span>
    </span>
  );
}
