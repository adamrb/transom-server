import { type ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { Icon, type IconName } from '@/components/Icon';

export interface SegmentOption<K extends string = string> {
  key: K;
  label: ReactNode;
  icon?: IconName;
  disabled?: boolean;
}

export interface SegmentedButtonProps<K extends string = string> {
  options: SegmentOption<K>[];
  value: K;
  onChange: (key: K) => void;
  label: string;
  /** md = 40 px, sm = 32 px */
  size?: 'md' | 'sm';
  /** Segments share the width equally (phone Settings). */
  fill?: boolean;
  className?: string;
}

/** Single-select segmented buttons (System / Light / Dark). Selected segment is tonal with a check. */
export function SegmentedButton<K extends string = string>({
  options,
  value,
  onChange,
  label,
  size = 'md',
  fill,
  className,
}: SegmentedButtonProps<K>) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={cn(
        'inline-flex overflow-hidden rounded-md border border-outline',
        size === 'sm' ? 'h-8' : 'h-10',
        fill && 'flex w-full',
        className,
      )}
    >
      {options.map((o) => {
        const on = o.key === value;
        return (
          <button
            key={o.key}
            type="button"
            role="radio"
            aria-checked={on}
            disabled={o.disabled}
            onClick={() => onChange(o.key)}
            className={cn(
              'inline-flex items-center justify-center gap-2 border-r border-outline text-label-l transition-colors dur-medium ease-standard last:border-r-0 focus-ring',
              size === 'sm' ? 'px-3 text-[13px]' : 'px-4',
              fill && 'flex-1',
              on
                ? 'bg-secondary-container text-on-secondary-container'
                : 'text-on-surface hover:bg-state-hover',
              'disabled:opacity-[.38]',
            )}
          >
            {on ? <Icon name="check" size={16} /> : o.icon ? <Icon name={o.icon} size={16} /> : null}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
