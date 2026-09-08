import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { Icon, type IconName } from '@/components/Icon';

export interface TabItem<K extends string = string> {
  key: K;
  label: ReactNode;
  icon?: IconName;
  disabled?: boolean;
}

export interface TabsProps<K extends string = string> {
  tabs: TabItem<K>[];
  value: K;
  onChange: (key: K) => void;
  label: string;
  /** primary: underline indicator (page sections). secondary: smaller, no icons. */
  variant?: 'primary' | 'secondary';
  className?: string;
}

/**
 * M3 tabs with a sliding underline indicator. Arrow keys move between tabs (roving tabindex),
 * Home/End jump. Pair the panel with `id={panelId(key)}` via `useTabsIds`, or simply render the
 * active panel below.
 */
export function Tabs<K extends string = string>({
  tabs,
  value,
  onChange,
  label,
  variant = 'primary',
  className,
}: TabsProps<K>) {
  const id = useId();
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const enabled = tabs.filter((t) => !t.disabled);

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = enabled.findIndex((t) => t.key === value);
    let next: TabItem<K> | undefined;
    if (e.key === 'ArrowRight') next = enabled[(i + 1) % enabled.length];
    else if (e.key === 'ArrowLeft') next = enabled[(i - 1 + enabled.length) % enabled.length];
    else if (e.key === 'Home') next = enabled[0];
    else if (e.key === 'End') next = enabled[enabled.length - 1];
    if (!next) return;
    e.preventDefault();
    onChange(next.key);
    refs.current[next.key]?.focus();
  };

  return (
    <div
      role="tablist"
      aria-label={label}
      onKeyDown={onKey}
      className={cn('flex border-b border-outline-variant', className)}
    >
      {tabs.map((t) => {
        const on = t.key === value;
        return (
          <button
            key={t.key}
            ref={(el) => {
              refs.current[t.key] = el;
            }}
            role="tab"
            type="button"
            id={`${id}-tab-${t.key}`}
            aria-selected={on}
            aria-controls={`${id}-panel-${t.key}`}
            tabIndex={on ? 0 : -1}
            disabled={t.disabled}
            onClick={() => onChange(t.key)}
            className={cn(
              'state-layer relative flex flex-1 flex-col items-center justify-center gap-0.5 px-4 text-label-l transition-colors dur-medium ease-standard focus-ring',
              variant === 'primary' ? 'h-12' : 'h-10',
              on ? 'text-primary' : 'text-on-surface-variant',
              'disabled:opacity-[.38]',
            )}
          >
            {t.icon && variant === 'primary' && <Icon name={t.icon} size={20} />}
            <span>{t.label}</span>
            <span
              aria-hidden
              className={cn(
                'absolute inset-x-4 bottom-0 h-[3px] rounded-t-full bg-primary transition-opacity dur-medium',
                on ? 'opacity-100' : 'opacity-0',
              )}
            />
          </button>
        );
      })}
    </div>
  );
}
