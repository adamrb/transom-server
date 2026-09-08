import { useId, useState } from 'react';
import { cn } from '@/lib/cn';
import { Icon, type IconName } from '@/components/Icon';

export interface DecisionLineProps {
  /** The matched rule's name, or a sentence such as "Nothing matched". */
  name: string;
  /** Why the assistant decided that. */
  reason?: string | null;
  /** wand_stars for a matched rule (default), check_circle for "nothing matched", error for a failure. */
  icon?: IconName;
  /** Collapsed (default): the reason sits behind a "Why?" button. Inline: shown under the name. */
  reasonCollapsed?: boolean;
  tone?: 'default' | 'muted' | 'error';
  className?: string;
}

/** One decision: glyph, the rule (bold) and, behind "Why?", the assistant's reasoning. */
export function DecisionLine({
  name,
  reason,
  icon = 'wand_stars',
  reasonCollapsed = true,
  tone = 'default',
  className,
}: DecisionLineProps) {
  const [open, setOpen] = useState(false);
  const reasonId = useId();
  const why = reason?.trim() || null;
  const showReason = !!why && (!reasonCollapsed || open);
  return (
    <div
      data-decision
      className={cn(
        'flex items-start gap-2 text-body-m',
        tone === 'error' ? 'text-error' : 'text-on-surface-body',
        className,
      )}
    >
      <Icon
        name={icon}
        size={18}
        className={cn('mt-px shrink-0', tone === 'error' ? 'text-error' : 'text-on-surface-variant')}
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span
            className={cn(
              'font-medium',
              tone === 'muted'
                ? 'text-on-surface-variant'
                : tone === 'error'
                  ? 'text-error'
                  : 'text-on-surface',
            )}
          >
            {name}
          </span>
          {why && reasonCollapsed && (
            <button
              type="button"
              aria-expanded={open}
              aria-controls={showReason ? reasonId : undefined}
              onClick={(e) => {
                e.stopPropagation();
                setOpen((o) => !o);
              }}
              className="-my-0.5 rounded-xs px-1 text-label-m text-primary hover:bg-state-hover focus-ring"
            >
              {open ? 'Hide' : 'Why?'}
            </button>
          )}
        </div>
        {showReason && (
          <p id={reasonId} className="m-0 mt-0.5 text-on-surface-variant [overflow-wrap:anywhere]">
            {why}
          </p>
        )}
      </div>
    </div>
  );
}
