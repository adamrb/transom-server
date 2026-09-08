import { type HTMLAttributes, type ReactNode } from 'react';
import { cn } from '@/lib/cn';

export interface TopAppBarProps extends Omit<HTMLAttributes<HTMLElement>, 'title'> {
  /** Section title. `large` renders it as a headline-l page title (Recordings, Automations, Settings). */
  title?: ReactNode;
  /** large: 32/40 weight-300 page title. small: 64 px bar with a title-l (detail pane). */
  variant?: 'large' | 'small';
  /** Leading element (Back button on phone). */
  leading?: ReactNode;
  /** Trailing icon buttons. */
  actions?: ReactNode;
  /** Heading level for the title (h1 for section bars, h2 in panes). */
  as?: 'h1' | 'h2' | 'div';
  /** Tints the bar when the content under it has scrolled. */
  scrolled?: boolean;
}

/**
 * Top app bar, 64 px. Section bars use the large variant with the headline-l title; the detail
 * pane bar is small with Back / Jump to / More. Hidden entirely in embedded mode by the shell.
 */
export function TopAppBar({
  title,
  variant = 'large',
  leading,
  actions,
  as = 'h1',
  scrolled,
  className,
  ...rest
}: TopAppBarProps) {
  const Tag = as;
  return (
    <header
      className={cn(
        'relative z-[3] flex shrink-0 items-center gap-1 px-4 transition-colors dur-medium',
        variant === 'large' ? 'h-16 max-md:h-auto max-md:items-end max-md:pt-6 max-md:pb-2' : 'h-16',
        scrolled ? 'bg-surface-container' : 'bg-surface',
        className,
      )}
      {...rest}
    >
      {leading}
      <Tag
        className={cn(
          'm-0 min-w-0 flex-1 truncate',
          variant === 'large'
            ? 'pl-2 font-display text-headline-l text-on-surface'
            : 'pl-1 text-title-l text-on-surface',
        )}
      >
        {title}
      </Tag>
      {actions && <div className="flex shrink-0 items-center gap-1">{actions}</div>}
    </header>
  );
}
