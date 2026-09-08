import { Slider, type SliderProps } from '@/components';
import { cn } from '@/lib/cn';

export interface PlayerSliderProps extends SliderProps {
  /** End of the buffered range (same units as value), drawn as a faint bar past the playhead. */
  buffered?: number;
}

/**
 * The shared Slider plus a buffered-range bar. The bar is an overlay from the playhead to the
 * buffered end (never over the primary fill), pointer-events off so the range input underneath
 * keeps every gesture. (A `buffered` prop on the shared Slider would make this wrapper go away.)
 */
export function PlayerSlider({ buffered = 0, value, max, min = 0, className, ...rest }: PlayerSliderProps) {
  const span = max - min || 1;
  const pct = (v: number) => Math.min(100, Math.max(0, ((v - min) / span) * 100));
  const from = pct(value);
  const to = pct(buffered);
  return (
    <div className={cn('relative', className)}>
      <Slider value={value} max={max} min={min} {...rest} />
      {to > from && (
        <div
          aria-hidden
          data-buffered
          className="pointer-events-none absolute top-1/2 h-1 -translate-y-1/2 rounded-full bg-on-surface-variant/25"
          style={{ left: `${from}%`, width: `${to - from}%` }}
        />
      )}
    </div>
  );
}
