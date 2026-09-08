import { type HTMLAttributes } from 'react';
import { cn } from '@/lib/cn';

export interface LinearProgressProps extends Omit<HTMLAttributes<HTMLDivElement>, 'children'> {
  /** 0..1; omit for indeterminate (1.6 s sweep). */
  value?: number | null;
  label?: string;
  /** thin = 3 px (mini player), default 4 px. */
  thin?: boolean;
}

/** 4 px track with a primary bar. Used under the detail bar while loading and in the login gate. */
export function LinearProgress({ value, label, thin, className, ...rest }: LinearProgressProps) {
  const determinate = typeof value === 'number' && !Number.isNaN(value);
  const v = determinate ? Math.min(1, Math.max(0, value)) : 0;
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={determinate ? Math.round(v * 100) : undefined}
      data-indeterminate={determinate ? undefined : true}
      className={cn(
        // Block-level: fills its container unless the caller passes a width class.
        'relative overflow-hidden rounded-full bg-surface-container-highest',
        thin ? 'h-[3px]' : 'h-1',
        className,
      )}
      {...rest}
    >
      <div
        className={cn(
          'absolute inset-y-0 left-0 rounded-full bg-primary',
          !determinate && 'w-2/5 animate-[lp-indeterminate_1.6s_var(--ease-standard)_infinite]',
        )}
        style={determinate ? { width: `${v * 100}%` } : undefined}
      />
    </div>
  );
}
