import { forwardRef, type ButtonHTMLAttributes, type HTMLAttributes, type ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { Icon, type IconName } from '@/components/Icon';

/* ---------------------------------- assist / filter chips ---------------------------------- */

export interface ChipProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  /** assist: an action (Copy transcript). filter: a toggle (All, Waiting…). */
  variant?: 'assist' | 'filter';
  /** filter chips only: selected shows a check mark and the tonal container. */
  selected?: boolean;
  icon?: IconName;
  children: ReactNode;
}

/** 32 px, 8 px corners, 16 px icons. Filter chips render a check mark when selected. */
export const Chip = forwardRef<HTMLButtonElement, ChipProps>(function Chip(
  { variant = 'assist', selected, icon, className, children, type = 'button', ...rest },
  ref,
) {
  const isFilter = variant === 'filter';
  const leading: IconName | undefined = isFilter && selected ? 'check' : icon;
  return (
    <button
      ref={ref}
      type={type}
      role={isFilter ? 'checkbox' : undefined}
      aria-checked={isFilter ? !!selected : undefined}
      data-variant={variant}
      className={cn(
        'inline-flex h-8 items-center gap-2 whitespace-nowrap rounded-sm border px-3 text-label-l select-none',
        'transition-[background-color,border-color] dur-medium ease-standard focus-ring',
        'disabled:opacity-[.38] disabled:cursor-default',
        isFilter && selected
          ? 'border-transparent bg-secondary-container text-on-secondary-container'
          : 'border-outline text-on-surface hover:bg-state-hover active:bg-state-press',
        className,
      )}
      {...rest}
    >
      {leading && <Icon name={leading} size={16} className="-ml-1" />}
      {children}
    </button>
  );
});

/* ------------------------------------- status words ------------------------------------- */

export type StatusTone = 'inflight' | 'failed' | 'neutral' | 'ok' | 'tag' | 'star';

export interface StatusChipProps extends HTMLAttributes<HTMLSpanElement> {
  /** inflight (amber, only while pending/transcribing), failed (red), neutral (No speech,
   *  Not transcribed), ok ("this computer"), tag (meta such as "2 speakers"), star (bookmark count). */
  tone: StatusTone;
  icon?: IconName;
  children: ReactNode;
}

const TONE: Record<StatusTone, string> = {
  inflight: 'bg-warning-container text-on-warning-container',
  failed: 'bg-error-container text-on-error-container',
  neutral: 'bg-surface-container-high text-on-surface-variant',
  ok: 'bg-success-container text-on-success-container',
  tag: 'bg-surface-container-high text-on-surface-variant',
  star: 'bg-warning-container text-on-warning-container',
};

/**
 * Status word: 24 px tonal container, no border, 14 px icon. Finished recordings show nothing;
 * these appear only while in flight, when failed, for No speech / Not transcribed, and as tags.
 */
export function StatusChip({ tone, icon, className, children, ...rest }: StatusChipProps) {
  return (
    <span
      data-tone={tone}
      className={cn(
        'inline-flex h-6 items-center gap-1 whitespace-nowrap rounded-status px-2 text-label-m tnum',
        TONE[tone],
        className,
      )}
      {...rest}
    >
      {icon && <Icon name={icon} size={14} />}
      {children}
    </span>
  );
}
