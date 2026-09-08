import { forwardRef, type HTMLAttributes, type ReactNode } from 'react';
import { cn } from '@/lib/cn';

export type CardTone = 'default' | 'low' | 'high';

export interface CardProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  /** default: card surface (white in light, sc in dark). low: one step down. high: one step up. */
  tone?: CardTone;
  /** 0 = tonal only (the norm). 1–3 add a shadow (player, menus). */
  elevation?: 0 | 1 | 2 | 3;
  /** tight: 4 px vertical padding for stacked settings rows. none: no padding. */
  padding?: 'default' | 'tight' | 'none';
  /** Optional heading row: title-m plus trailing actions. */
  title?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
}

const TONE: Record<CardTone, string> = {
  default: 'bg-card',
  low: 'bg-surface-container-low',
  high: 'bg-card-raised',
};
const SHADOW = ['', 'shadow-e1', 'shadow-e2', 'shadow-e3'] as const;
const PAD = {
  default: 'px-5 py-4 max-md:px-4 max-md:py-3.5',
  tight: 'px-5 py-1 max-md:px-4',
  none: '',
} as const;

/** Tonal card, 16 px corners, no border (the app separates surfaces by tone). */
export const Card = forwardRef<HTMLDivElement, CardProps>(function Card(
  { tone = 'default', elevation = 0, padding = 'default', title, actions, className, children, ...rest },
  ref,
) {
  return (
    <div
      ref={ref}
      // Floating text-field labels inside a card need the card's colour behind them.
      className={cn(
        'rounded-lg [--field-bg:var(--card)]',
        TONE[tone],
        SHADOW[elevation],
        PAD[padding],
        className,
      )}
      {...rest}
    >
      {(title || actions) && (
        <div className="mb-2 flex min-h-10 items-center gap-2">
          {title && <h3 className="m-0 flex-1 text-title-m text-on-surface">{title}</h3>}
          {actions}
        </div>
      )}
      {children}
    </div>
  );
});
