import { type HTMLAttributes } from 'react';
import { cn } from '@/lib/cn';

export interface ProgressRingProps extends Omit<HTMLAttributes<HTMLSpanElement>, 'children'> {
  /** 0..1. Omit for an indeterminate (spinning) ring. */
  value?: number | null;
  /** Diameter in px. */
  size?: number;
  /** Stroke width in px. */
  stroke?: number;
  /** amber (in-flight, the default) or primary. */
  tone?: 'warning' | 'primary';
  /** Show the percentage inside (determinate only). */
  showValue?: boolean;
  label?: string;
}

/** Circular progress. Determinate rings fill clockwise from the top; indeterminate rings spin (1.4 s). */
export function ProgressRing({
  value,
  size = 36,
  stroke = 3,
  tone = 'warning',
  showValue,
  label,
  className,
  ...rest
}: ProgressRingProps) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const determinate = typeof value === 'number' && !Number.isNaN(value);
  const v = determinate ? Math.min(1, Math.max(0, value)) : 0;
  const color = tone === 'warning' ? 'text-warning' : 'text-primary';
  return (
    <span
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={determinate ? Math.round(v * 100) : undefined}
      data-indeterminate={determinate ? undefined : true}
      className={cn('relative inline-grid shrink-0 place-items-center', color, className)}
      style={{ width: size, height: size }}
      {...rest}
    >
      <svg
        viewBox={`0 0 ${size} ${size}`}
        width={size}
        height={size}
        className="absolute inset-0"
        aria-hidden
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={stroke}
          className="stroke-surface-container-highest"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          stroke="currentColor"
          strokeDasharray={determinate ? `${c * v} ${c * (1 - v)}` : `${c * 0.25} ${c * 0.75}`}
          className={cn('origin-center -rotate-90', !determinate && 'animate-[spin_1.4s_linear_infinite]')}
        />
      </svg>
      {determinate && showValue && (
        <span className="relative text-[11px] leading-none font-semibold tnum">{Math.round(v * 100)}%</span>
      )}
    </span>
  );
}
