import { forwardRef, type InputHTMLAttributes } from 'react';
import { cn } from '@/lib/cn';
import { Icon } from '@/components/Icon';

export interface SwitchProps extends Omit<
  InputHTMLAttributes<HTMLInputElement>,
  'type' | 'onChange' | 'size'
> {
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** Required: switches have no text of their own. */
  label: string;
}

/**
 * M3 switch, 52 × 32: outlined track when off, primary track with a check mark on the thumb when on.
 * Wraps a real checkbox so it is keyboard and screen-reader operable.
 */
export const Switch = forwardRef<HTMLInputElement, SwitchProps>(function Switch(
  { checked, onChange, label, className, disabled, ...rest },
  ref,
) {
  return (
    <label
      className={cn(
        'relative inline-block h-8 w-[52px] shrink-0 select-none',
        disabled ? 'cursor-default opacity-[.38]' : 'cursor-pointer',
        className,
      )}
    >
      <input
        ref={ref}
        type="checkbox"
        role="switch"
        aria-label={label}
        aria-checked={checked}
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="peer absolute inset-0 z-10 m-0 cursor-[inherit] opacity-0"
        {...rest}
      />
      <span
        aria-hidden
        className={cn(
          'absolute inset-0 rounded-full border-2 transition-colors dur-medium ease-standard',
          'peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-primary',
          checked ? 'border-primary bg-primary' : 'border-outline bg-surface-container-highest',
        )}
      />
      <span
        aria-hidden
        className={cn(
          'absolute grid place-items-center rounded-full transition-[transform,width,height,top,left,background-color] dur-medium ease-emph-decel',
          checked
            ? 'top-1 left-1 size-6 translate-x-5 bg-on-primary text-primary'
            : 'top-2 left-2 size-4 translate-x-0 bg-outline',
        )}
      >
        {checked && <Icon name="check" size={16} />}
      </span>
    </label>
  );
});
