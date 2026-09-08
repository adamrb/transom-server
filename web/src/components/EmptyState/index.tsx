import { type HTMLAttributes, type ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { Icon, type IconName } from '@/components/Icon';

export interface EmptyStateProps extends HTMLAttributes<HTMLDivElement> {
  icon?: IconName;
  headline: ReactNode;
  /** One sentence. */
  description?: ReactNode;
  /** Usually a tonal Button. */
  action?: ReactNode;
  /** compact: smaller glyph and spacing for a card or side pane. */
  compact?: boolean;
}

/** Centred glyph, title-l headline, one sentence, optional action. */
export function EmptyState({
  icon = 'graphic_eq',
  headline,
  description,
  action,
  compact,
  className,
  ...rest
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-1 flex-col items-center justify-center gap-2 px-8 py-6 text-center text-on-surface-variant',
        className,
      )}
      {...rest}
    >
      <div
        className={cn(
          'mb-3 grid place-items-center rounded-full bg-surface-container-high text-on-surface-variant',
          compact ? 'size-16' : 'size-24',
        )}
      >
        {/* CSS size wins over the width/height attributes: 44 px in the large glyph. */}
        <Icon name={icon} size={compact ? 28 : 32} className={compact ? undefined : 'size-11'} />
      </div>
      <h3 className={cn('m-0 font-display text-on-surface', compact ? 'text-title-m' : 'text-title-l')}>
        {headline}
      </h3>
      {description && <p className="m-0 mb-3 max-w-[320px] text-body-m">{description}</p>}
      {action}
    </div>
  );
}
