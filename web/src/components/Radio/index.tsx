import { useId, type ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { Icon, type IconName } from '@/components/Icon';

export interface RadioProps {
  /** Shared by every radio in the group (arrow keys move between radios with the same name). */
  name: string;
  value: string;
  checked: boolean;
  onChange: (value: string) => void;
  label: ReactNode;
  /** One line under the label, body-m on-surface-variant. */
  description?: ReactNode;
  /** Leading Material Symbol beside the radio. */
  icon?: IconName;
  disabled?: boolean;
  className?: string;
}

/**
 * One M3 radio row: a 20 px ring (primary when checked) beside a label and an optional
 * description, the whole row a click target with a secondary-container tint when selected.
 * Wraps a real radio input so the native group semantics (arrow keys, one selected) come free.
 */
export function Radio({
  name,
  value,
  checked,
  onChange,
  label,
  description,
  icon,
  disabled,
  className,
}: RadioProps) {
  return (
    <label
      data-checked={checked || undefined}
      className={cn(
        'flex items-start gap-3 rounded-md px-3 py-2.5 transition-colors dur-short ease-standard',
        'has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-primary',
        disabled ? 'cursor-default opacity-[.38]' : 'cursor-pointer',
        checked ? 'bg-secondary-container text-on-secondary-container' : !disabled && 'hover:bg-state-hover',
        className,
      )}
    >
      <input
        type="radio"
        name={name}
        value={value}
        checked={checked}
        disabled={disabled}
        onChange={() => onChange(value)}
        className="peer sr-only"
      />
      <span
        aria-hidden
        className={cn(
          'mt-0.5 grid size-5 shrink-0 place-items-center rounded-full border-2',
          checked ? 'border-primary' : 'border-on-surface-variant',
        )}
      >
        {checked && <span className="size-2.5 rounded-full bg-primary" />}
      </span>
      {icon && (
        <Icon
          name={icon}
          size={20}
          className={cn('mt-0.5', checked ? 'text-on-secondary-container' : 'text-on-surface-variant')}
        />
      )}
      <span className="min-w-0 flex-1">
        <span className="block text-body-l text-on-surface">{label}</span>
        {description && (
          <span className={cn('block text-body-m', checked ? 'opacity-90' : 'text-on-surface-variant')}>
            {description}
          </span>
        )}
      </span>
    </label>
  );
}

export interface RadioOption<T extends string> {
  key: T;
  label: ReactNode;
  description?: ReactNode;
  icon?: IconName;
  disabled?: boolean;
}

export interface RadioGroupProps<T extends string> {
  /** The question the options answer ("What happens"). Rendered as the legend. */
  label: ReactNode;
  /** Keep the legend for assistive tech only. */
  hideLabel?: boolean;
  value: T;
  onChange: (value: T) => void;
  options: readonly RadioOption<T>[];
  disabled?: boolean;
  className?: string;
}

/** A labelled list of `Radio`s (fieldset + legend, role radiogroup). */
export function RadioGroup<T extends string>({
  label,
  hideLabel,
  value,
  onChange,
  options,
  disabled,
  className,
}: RadioGroupProps<T>) {
  const name = useId();
  const labelId = `${name}-label`;
  return (
    <fieldset
      className={cn('m-0 min-w-0 border-0 p-0', className)}
      aria-labelledby={labelId}
      disabled={disabled}
    >
      <legend
        id={labelId}
        className={cn('mb-1 px-1 text-body-s text-on-surface-variant', hideLabel && 'sr-only')}
      >
        {label}
      </legend>
      <div role="radiogroup" aria-labelledby={labelId} className="flex flex-col gap-1">
        {options.map((o) => (
          <Radio
            key={o.key}
            name={name}
            value={o.key}
            checked={o.key === value}
            onChange={() => onChange(o.key)}
            label={o.label}
            description={o.description}
            icon={o.icon}
            disabled={disabled || o.disabled}
          />
        ))}
      </div>
    </fieldset>
  );
}
