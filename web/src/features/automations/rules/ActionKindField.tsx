import { useId } from 'react';
import { cn } from '@/lib/cn';
import { Icon } from '@/components/Icon';
import type { ActionType } from '@/api/types';
import { ACTION_KINDS } from './actionWords';

export interface ActionKindFieldProps {
  value: ActionType;
  onChange: (kind: ActionType) => void;
  disabled?: boolean;
}

/**
 * "What happens" as a radio list in user words (Send it to the agent / Save a note in a folder /
 * Just record the decision), each with a one-line hint. Native radios, drawn M3-style.
 */
export function ActionKindField({ value, onChange, disabled }: ActionKindFieldProps) {
  const name = useId();
  const labelId = `${name}-label`;
  return (
    <fieldset className="m-0 min-w-0 border-0 p-0" aria-labelledby={labelId} disabled={disabled}>
      <legend id={labelId} className="mb-1 px-1 text-body-s text-on-surface-variant">
        What happens
      </legend>
      <div role="radiogroup" aria-labelledby={labelId} className="flex flex-col gap-1">
        {ACTION_KINDS.map((k) => {
          const on = k.key === value;
          return (
            <label
              key={k.key}
              data-checked={on || undefined}
              className={cn(
                'flex cursor-pointer items-start gap-3 rounded-md px-3 py-2.5 transition-colors dur-short ease-standard',
                'has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-primary',
                on ? 'bg-secondary-container text-on-secondary-container' : 'hover:bg-state-hover',
              )}
            >
              <input
                type="radio"
                name={name}
                value={k.key}
                checked={on}
                onChange={() => onChange(k.key)}
                className="peer sr-only"
              />
              <span
                aria-hidden
                className={cn(
                  'mt-0.5 grid size-5 shrink-0 place-items-center rounded-full border-2',
                  on ? 'border-primary' : 'border-on-surface-variant',
                )}
              >
                {on && <span className="size-2.5 rounded-full bg-primary" />}
              </span>
              <Icon
                name={k.icon}
                size={20}
                className={cn('mt-0.5', on ? 'text-on-secondary-container' : 'text-on-surface-variant')}
              />
              <span className="min-w-0 flex-1">
                <span className="block text-body-l text-on-surface">{k.label}</span>
                <span className={cn('block text-body-m', on ? 'opacity-90' : 'text-on-surface-variant')}>
                  {k.hint}
                </span>
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
