import { type ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { Icon, type IconName } from '@/components/Icon';

export interface NavDestination<K extends string = string> {
  key: K;
  label: string;
  icon: IconName;
}

export interface NavRailProps<K extends string = string> {
  destinations: NavDestination<K>[];
  value: K;
  onChange: (key: K) => void;
  /** Brand mark at the top (defaults to the waveform tile). */
  brand?: ReactNode;
  /** Icon buttons pinned to the bottom (theme, sign out). */
  footer?: ReactNode;
  className?: string;
}

/**
 * M3 navigation rail, 80 px wide (≥ 840 px). Destinations show a 56 × 32 pill indicator when
 * active; icons are 22 px (the mockup's 24 felt big).
 */
export function NavRail<K extends string = string>({
  destinations,
  value,
  onChange,
  brand,
  footer,
  className,
}: NavRailProps<K>) {
  return (
    <nav
      aria-label="Sections"
      className={cn('flex w-20 shrink-0 flex-col items-center gap-1 bg-surface pt-3 pb-4', className)}
    >
      <div
        className="mb-6 grid size-11 place-items-center rounded-[14px] bg-primary text-on-primary"
        title="Plaud Bridge"
      >
        {brand ?? <Icon name="graphic_eq" size={24} />}
      </div>
      {destinations.map((d) => (
        <NavRailItem key={d.key} destination={d} active={d.key === value} onSelect={() => onChange(d.key)} />
      ))}
      <div className="flex-1" />
      {footer && <div className="flex flex-col items-center gap-2">{footer}</div>}
    </nav>
  );
}

export function NavRailItem<K extends string>({
  destination: d,
  active,
  onSelect,
  wide,
}: {
  destination: NavDestination<K>;
  active: boolean;
  onSelect: () => void;
  /** Bottom-nav variant: 64 px indicator, flexible width. */
  wide?: boolean;
}) {
  return (
    <button
      type="button"
      aria-current={active ? 'page' : undefined}
      data-nav={d.key}
      onClick={onSelect}
      className={cn(
        'group relative flex flex-col items-center gap-1 focus-ring',
        wide ? 'flex-1 py-0' : 'w-20 py-1.5',
        active ? 'text-on-surface' : 'text-on-surface-variant',
      )}
    >
      <span
        className={cn(
          'relative grid h-8 place-items-center rounded-full transition-colors dur-medium ease-standard',
          wide ? 'w-16' : 'w-14',
          'before:absolute before:inset-0 before:rounded-full before:bg-on-surface before:opacity-0 before:transition-opacity before:dur-short group-hover:before:opacity-[.08]',
          active && 'bg-secondary-container text-on-secondary-container',
        )}
      >
        <Icon name={d.icon} size={22} />
      </span>
      <span className={cn('text-label-m', active && 'font-bold')}>{d.label}</span>
    </button>
  );
}
