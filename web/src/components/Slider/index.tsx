import { forwardRef, useState, type InputHTMLAttributes } from 'react';
import { cn } from '@/lib/cn';

export interface SliderProps extends Omit<
  InputHTMLAttributes<HTMLInputElement>,
  'type' | 'value' | 'onChange' | 'min' | 'max' | 'step'
> {
  value: number;
  min?: number;
  max: number;
  step?: number;
  /** Fires continuously while dragging or pressing arrow keys (seek preview). */
  onChange: (value: number) => void;
  /** Fires when the pointer is released or a key is let go (seek commit). */
  onCommit?: (value: number) => void;
  /** Positions (same units as value) drawn as 6 px amber dots: the bookmarks. */
  markers?: number[];
  /** End of the buffered range (same units as value): a faint bar from the handle to it. */
  buffered?: number;
  /** Human text for assistive tech, e.g. the clock time. */
  formatValue?: (value: number) => string;
  label: string;
}

/**
 * M3 slider: 4 px track, primary fill, 4 × 20 handle, optional bookmark markers and buffered
 * range. A real range input sits on top (transparent) so keyboard, touch and screen readers all
 * work natively.
 */
export const Slider = forwardRef<HTMLInputElement, SliderProps>(function Slider(
  {
    value,
    min = 0,
    max,
    step = 0.1,
    onChange,
    onCommit,
    markers = [],
    buffered,
    formatValue,
    label,
    className,
    disabled,
    ...rest
  },
  ref,
) {
  const [active, setActive] = useState(false);
  const span = max - min || 1;
  const pctNum = (v: number) => Math.min(100, Math.max(0, ((v - min) / span) * 100));
  const pct = (v: number) => `${pctNum(v)}%`;
  const valuePct = pctNum(value);
  const bufferedPct = buffered === undefined ? 0 : pctNum(buffered);
  const commit = () => {
    setActive(false);
    onCommit?.(value);
  };
  return (
    <div
      className={cn(
        'relative flex h-7 items-center',
        // Keyboard focus: a ring around the handle (M3), not the native rectangle around the track.
        '[&:has(input:focus-visible)_[data-handle]]:outline-2 [&:has(input:focus-visible)_[data-handle]]:outline-offset-4 [&:has(input:focus-visible)_[data-handle]]:outline-primary',
        disabled && 'opacity-[.38]',
        className,
      )}
    >
      <div className="relative h-1 w-full rounded-full bg-surface-container-highest dark:bg-outline">
        {bufferedPct > valuePct && (
          <div
            aria-hidden
            data-buffered
            className="absolute inset-y-0 rounded-full bg-on-surface-variant/25"
            style={{ left: pct(value), width: `${bufferedPct - valuePct}%` }}
          />
        )}
        <div className="absolute inset-y-0 left-0 rounded-full bg-primary" style={{ width: pct(value) }} />
        {markers.map((m, i) => (
          <span
            key={i}
            aria-hidden
            data-marker
            className="absolute top-1/2 size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-warning"
            style={{ left: pct(m) }}
          />
        ))}
        <div
          aria-hidden
          data-handle
          className={cn(
            'absolute top-1/2 h-5 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary transition-[height] dur-short',
            active && 'h-6',
          )}
          style={{ left: pct(value) }}
        />
      </div>
      <input
        ref={ref}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        aria-label={label}
        aria-valuetext={formatValue ? formatValue(value) : undefined}
        onChange={(e) => onChange(Number(e.target.value))}
        onPointerDown={() => setActive(true)}
        onPointerUp={commit}
        onPointerCancel={commit}
        onKeyUp={(e) => {
          if (
            ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End', 'PageUp', 'PageDown'].includes(
              e.key,
            )
          )
            commit();
        }}
        onBlur={() => active && commit()}
        className="absolute inset-0 m-0 h-full w-full cursor-pointer appearance-none bg-transparent opacity-0 outline-none [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:size-5 [&::-moz-range-thumb]:size-5 [&::-moz-range-thumb]:opacity-0"
        {...rest}
      />
    </div>
  );
});
