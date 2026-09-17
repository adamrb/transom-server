import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { Icon, type IconName } from '@/components/Icon';

export type ButtonVariant = 'filled' | 'tonal' | 'outlined' | 'text' | 'danger' | 'danger-filled';
export type ButtonSize = 'md' | 'sm';

export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  /** filled: the one thing to do. tonal: secondary. outlined: Retry / Download. text: Edit / Preview.
   *  danger: red text; place it to the right, apart from the safe actions. danger-filled: the
   *  confirming button of a destructive dialog (error / on-error in both themes). */
  variant?: ButtonVariant;
  /** md = 40 px, sm = 32 px */
  size?: ButtonSize;
  /** Leading Material Symbol, 16 px (14 px in sm). */
  icon?: IconName;
  /** Stretch to the container width (login card). */
  block?: boolean;
  /** Shows a spinner in place of the icon and disables the button. */
  loading?: boolean;
  children?: ReactNode;
}

const VARIANT: Record<ButtonVariant, string> = {
  filled: 'bg-primary text-on-primary',
  tonal: 'bg-secondary-container text-on-secondary-container',
  outlined: 'border border-outline text-on-surface',
  text: 'text-on-surface',
  danger: 'text-error',
  'danger-filled': 'bg-error text-on-error',
};

const PAD: Record<ButtonSize, Record<'default' | 'text', string>> = {
  md: { default: 'h-10 px-5 rounded-md text-label-l gap-2', text: 'h-10 px-3 rounded-md text-label-l gap-2' },
  sm: {
    default: 'h-8 px-3.5 rounded-[10px] text-[13px] leading-5 font-medium gap-1.5',
    text: 'h-8 px-2.5 rounded-[10px] text-[13px] leading-5 font-medium gap-1.5',
  },
};

/** M3 button, 12 px corners like the app's Widget.Transom.Button. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'filled',
    size = 'md',
    icon,
    block,
    loading,
    className,
    children,
    disabled,
    type = 'button',
    ...rest
  },
  ref,
) {
  const textLike = variant === 'text' || variant === 'danger';
  const iconSize = size === 'sm' ? 14 : 16;
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      data-variant={variant}
      className={cn(
        'state-layer inline-flex items-center justify-center whitespace-nowrap select-none',
        'transition-[background-color,box-shadow] dur-short ease-standard focus-ring',
        'disabled:opacity-[.38] disabled:cursor-default',
        VARIANT[variant],
        PAD[size][textLike ? 'text' : 'default'],
        block && 'w-full',
        className,
      )}
      {...rest}
    >
      {loading ? (
        <span
          aria-hidden
          className="inline-block size-4 animate-spin rounded-full border-2 border-current border-r-transparent"
        />
      ) : icon ? (
        <Icon name={icon} size={iconSize} className={children ? '-ml-1' : undefined} />
      ) : null}
      {children}
    </button>
  );
});
