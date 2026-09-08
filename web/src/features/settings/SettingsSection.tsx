import { type HTMLAttributes, type ReactNode } from 'react';
import { Avatar } from '@/components/Avatar';
import { Card } from '@/components/Card';
import { ListItem, type ListItemProps } from '@/components/ListItem';
import { type IconName } from '@/components/Icon';
import { cn } from '@/lib/cn';

export interface SettingsSectionProps extends Omit<HTMLAttributes<HTMLElement>, 'title'> {
  /** title-l heading (Appearance, Vocabulary, …). */
  title: string;
  /** Trailing header actions (a refresh icon button). */
  actions?: ReactNode;
  /** Section body: a Card of rows, or free content. `card` wraps children in a tight card. */
  card?: boolean;
  children: ReactNode;
}

/**
 * One settings section: heading row (title-l plus optional actions) and its body. Sections stack
 * with 28 px between them; the first has no top margin.
 */
export function SettingsSection({
  title,
  actions,
  card,
  className,
  children,
  ...rest
}: SettingsSectionProps) {
  return (
    <section className={cn('first:mt-0 [&:not(:first-child)]:mt-7', className)} {...rest}>
      <div className="mb-3 flex min-h-10 items-center gap-3">
        <h2 className="m-0 flex-1 font-display text-title-l text-on-surface">{title}</h2>
        {actions}
      </div>
      {card ? <Card padding="tight">{children}</Card> : children}
    </section>
  );
}

export interface SettingsRowProps extends Omit<ListItemProps, 'leading' | 'shape'> {
  /** Leading glyph in a 40 px rounded square. */
  icon: IconName;
  /** Align the glyph with the headline instead of the row centre (rows with extra content). */
  alignTop?: boolean;
}

/** A flat settings row: icon avatar, headline, supporting line (wraps to two lines), trailing control. */
export function SettingsRow({ icon, alignTop, className, wrap = true, ...rest }: SettingsRowProps) {
  return (
    <ListItem
      shape="flat"
      wrap={wrap}
      leading={
        <Avatar
          kind="icon"
          icon={icon}
          size={40}
          shape="rounded"
          className={alignTop ? 'self-start' : undefined}
        />
      }
      className={cn(alignTop && 'items-start', className)}
      {...rest}
    />
  );
}
