import { forwardRef, type HTMLAttributes, type KeyboardEvent, type ReactNode } from 'react';
import { cn } from '@/lib/cn';

export interface ListItemProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  /** Leading avatar / icon. */
  leading?: ReactNode;
  /** body-l, one line, ellipsised. */
  headline: ReactNode;
  /** body-m on-surface-variant, one line, ellipsised. Can hold a StatusChip. */
  supporting?: ReactNode;
  /** Right column: time, bookmark count, a switch, a button. */
  trailing?: ReactNode;
  /** Card-shaped row (recordings list) vs a flat row separated by hairlines (settings). */
  shape?: 'card' | 'flat';
  /** Highlighted with secondary-container (the open recording). */
  selected?: boolean;
  /** Makes the row a button-like item: pointer, hover layer, Enter/Space activate onClick. */
  interactive?: boolean;
  /** Extra content below the headline/supporting lines (rule descriptions). */
  children?: ReactNode;
  /** Let a plain-text supporting line wrap to two lines instead of ellipsising (settings rows). */
  wrap?: boolean;
}

/**
 * M3 list item: 72 px min height, 36 px leading avatar, 16 px gap. Card-shaped like the app's
 * recording rows; `flat` for settings rows.
 */
export const ListItem = forwardRef<HTMLDivElement, ListItemProps>(function ListItem(
  {
    leading,
    headline,
    supporting,
    trailing,
    shape = 'card',
    selected,
    interactive,
    wrap,
    className,
    children,
    onClick,
    onKeyDown,
    ...rest
  },
  ref,
) {
  const clickable = interactive ?? !!onClick;
  const handleKey = (e: KeyboardEvent<HTMLDivElement>) => {
    onKeyDown?.(e);
    if (e.defaultPrevented || !clickable || !onClick) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onClick(e as unknown as React.MouseEvent<HTMLDivElement>);
    }
  };
  return (
    <div
      ref={ref}
      role={rest.role ?? (clickable ? 'button' : undefined)}
      tabIndex={clickable ? (rest.tabIndex ?? 0) : rest.tabIndex}
      aria-selected={selected === undefined ? undefined : selected}
      data-selected={selected || undefined}
      onClick={onClick}
      onKeyDown={handleKey}
      className={cn(
        'relative flex min-h-[72px] items-center gap-4 focus-ring',
        shape === 'card'
          ? cn(
              'rounded-lg py-3 pl-3 pr-4 transition-colors dur-medium ease-standard',
              selected ? 'bg-secondary-container' : 'bg-card',
            )
          : 'py-3.5 border-t border-outline-variant first:border-t-0',
        clickable && 'cursor-pointer state-layer',
        className,
      )}
      {...rest}
    >
      {leading}
      <div className="min-w-0 flex-1">
        <div className="truncate text-body-l text-on-surface">{headline}</div>
        {supporting && (
          <div
            className={cn(
              'flex min-h-6 min-w-0 items-center gap-2 text-body-m text-on-surface-variant',
              !wrap && 'truncate',
            )}
          >
            {/* text-overflow needs a text box, not a flex container: plain text gets its own span */}
            {typeof supporting === 'string' ? (
              <span className={wrap ? 'line-clamp-2' : 'truncate'}>{supporting}</span>
            ) : (
              supporting
            )}
          </div>
        )}
        {children}
      </div>
      {trailing && (
        <div className="flex shrink-0 flex-col items-end gap-1.5 text-body-s text-on-surface-variant tnum">
          {trailing}
        </div>
      )}
    </div>
  );
});
