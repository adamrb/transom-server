import { useId, useRef, useState, type ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { Icon } from '@/components/Icon';
import { MenuItem, Popover } from '@/components/Popover';

export interface SelectOption<T extends string> {
  value: T;
  label: string;
  /** One line under the label in the list. */
  description?: string;
  disabled?: boolean;
}

export interface SelectProps<T extends string> {
  /** Accessible name; shown as the floating label unless `hideLabel`. */
  label: string;
  hideLabel?: boolean;
  value: T | null;
  onChange: (value: T) => void;
  options: readonly SelectOption<T>[];
  /** Shown when nothing is selected (or when the options are empty, e.g. "Loading…"). */
  placeholder?: string;
  /** Helper (or error) text under the field. */
  helper?: ReactNode;
  error?: boolean;
  disabled?: boolean;
  /** md = 48 px, sm = 40 px (matches TextField). */
  size?: 'md' | 'sm';
  className?: string;
}

/**
 * M3 outlined select: a combobox button that opens a listbox in a `Popover` (menu on desktop, a
 * sheet on phone). Works inside a modal <dialog> (the popover portals into it). Arrow keys move
 * through the options; the chosen one is focused and checked when the list opens.
 */
export function Select<T extends string>({
  label,
  hideLabel,
  value,
  onChange,
  options,
  placeholder = 'Choose…',
  helper,
  error,
  disabled,
  size = 'md',
  className,
}: SelectProps<T>) {
  const id = useId();
  const listId = `${id}-list`;
  const helperId = helper ? `${id}-helper` : undefined;
  const trigger = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const current = options.find((o) => o.value === value) ?? null;
  const empty = options.length === 0;
  const isDisabled = disabled || empty;
  // Focus moved into the list on open; every way out (pick, Escape, scrim) brings it back.
  const close = () => {
    setOpen(false);
    trigger.current?.focus();
  };

  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <button
        ref={trigger}
        id={id}
        type="button"
        role="combobox"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-describedby={helperId}
        aria-invalid={error || undefined}
        data-value={value ?? undefined}
        disabled={isDisabled}
        onClick={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            setOpen(true);
          }
        }}
        className={cn(
          'relative flex w-full items-center gap-2 border bg-transparent pr-2.5 pl-3.5 text-left text-on-surface transition-[border-color,box-shadow] dur-short focus-ring',
          size === 'sm' ? 'h-10 rounded-[10px] text-body-m' : 'h-12 rounded-md text-body-l',
          error
            ? 'border-error'
            : open
              ? 'border-primary shadow-[inset_0_0_0_1px_var(--primary)]'
              : 'border-outline',
          'hover:bg-state-hover disabled:opacity-[.38] disabled:hover:bg-transparent',
        )}
      >
        <span className={cn('min-w-0 flex-1 truncate', !current && 'text-on-surface-variant')}>
          {current ? current.label : placeholder}
        </span>
        <Icon
          name="keyboard_arrow_down"
          size={20}
          className={cn(
            'shrink-0 text-on-surface-variant transition-transform dur-short',
            open && 'rotate-180',
          )}
        />
        {!hideLabel && (
          <span
            aria-hidden
            className={cn(
              'pointer-events-none absolute -top-2 left-3 bg-(--field-bg) px-1 text-body-s',
              error ? 'text-error' : open ? 'text-primary' : 'text-on-surface-variant',
            )}
          >
            {label}
          </span>
        )}
      </button>
      {helper && (
        <div
          id={helperId}
          className={cn('px-1 text-body-s', error ? 'text-error' : 'text-on-surface-variant')}
        >
          {helper}
        </div>
      )}
      <Popover
        open={open}
        onClose={close}
        anchorRef={trigger}
        role="listbox"
        id={listId}
        align="start"
        matchAnchorWidth
        label={label}
        title={label}
        className="max-w-[calc(100vw-16px)]"
      >
        {options.map((o) => (
          <MenuItem
            key={o.value}
            role="option"
            selected={o.value === value}
            description={o.description}
            disabled={o.disabled}
            onClick={() => {
              close();
              if (o.value !== value) onChange(o.value);
            }}
          >
            {o.label}
          </MenuItem>
        ))}
      </Popover>
    </div>
  );
}
