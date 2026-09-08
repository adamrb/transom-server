import { Icon } from '@/components/Icon';
import { cn } from '@/lib/cn';

export interface SkipIconProps {
  /** The number drawn inside the arrow (15, 30). */
  seconds: number;
  direction: 'back' | 'forward';
  /** Box size in px (the glyph scales with it). */
  size?: 20 | 24 | 28;
  className?: string;
}

/**
 * The "skip n seconds" glyph: Material's `replay` arrow (mirrored for forward) with the seconds
 * inside, as the player mockup draws it. Material Symbols only ships replay_5/10/30, so this
 * composes any number. Decorative; the parent button carries the label.
 */
export function SkipIcon({ seconds, direction, size = 24, className }: SkipIconProps) {
  const text =
    size === 20 ? 'text-[7px] pt-[2px]' : size === 28 ? 'text-[9px] pt-[4px]' : 'text-[8px] pt-[3px]';
  return (
    <span
      aria-hidden
      data-skip={direction}
      className={cn('relative inline-grid place-items-center', className)}
      style={{ width: size, height: size }}
    >
      <Icon
        name="replay"
        size={size}
        className={cn('absolute inset-0', direction === 'forward' && '-scale-x-100')}
      />
      <span className={cn('relative leading-none font-bold tnum', text)}>{seconds}</span>
    </span>
  );
}
