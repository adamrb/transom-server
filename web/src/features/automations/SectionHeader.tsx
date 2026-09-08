import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

export interface SectionHeaderProps {
  title: string;
  /** Heading id, for `aria-labelledby` on the section. */
  id?: string;
  /** One sentence under the heading. */
  description?: ReactNode;
  /** Trailing button(s). */
  actions?: ReactNode;
  className?: string;
}

/** "Rules" / "Activity" header: title-l, optional sentence, trailing actions. 28 px above, 12 below. */
export function SectionHeader({ title, id, description, actions, className }: SectionHeaderProps) {
  return (
    <div className={cn('mb-3 first:mt-0 [&:not(:first-child)]:mt-7', className)}>
      <div className="flex min-h-10 items-center gap-3">
        <h2 id={id} className="m-0 flex-1 font-display text-title-l text-on-surface">
          {title}
        </h2>
        {actions}
      </div>
      {description && <p className="m-0 mt-1 text-body-m text-on-surface-variant">{description}</p>}
    </div>
  );
}
