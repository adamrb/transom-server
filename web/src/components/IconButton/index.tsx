import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { cn } from '@/lib/cn';
import { Icon, type IconName, type IconSize } from '@/components/Icon';

export type IconButtonVariant = 'standard' | 'tonal' | 'filled';
export type IconButtonSize = 'md' | 'lg' | 'xl';

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: IconName;
  /** Required: icon buttons have no visible text. Becomes aria-label and title. */
  label: string;
  variant?: IconButtonVariant;
  /** md = 40 px (20 px glyph), lg = 56 px (28), xl = 64 px (32). */
  size?: IconButtonSize;
  /** Override the glyph size (rail uses 22 in a 40 px button). */
  iconSize?: IconSize;
  /** Toggle state: `true` colours the glyph on-surface, the pressed look. */
  selected?: boolean;
  /** Hide the tooltip (title) when the parent supplies its own. */
  noTitle?: boolean;
}

const SIZE: Record<IconButtonSize, { box: string; icon: IconSize }> = {
  md: { box: 'size-10', icon: 20 },
  lg: { box: 'size-14', icon: 28 },
  xl: { box: 'size-16', icon: 32 },
};

const VARIANT: Record<IconButtonVariant, string> = {
  standard: 'text-on-surface-variant hover:bg-state-hover active:bg-state-press',
  tonal: 'bg-secondary-container text-on-secondary-container state-layer',
  filled: 'bg-primary text-on-primary state-layer',
};

/** 40 px round icon button with an M3 state layer. */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  {
    icon,
    label,
    variant = 'standard',
    size = 'md',
    iconSize,
    selected,
    noTitle,
    className,
    type = 'button',
    ...rest
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      aria-label={label}
      title={noTitle ? undefined : label}
      aria-pressed={selected === undefined ? undefined : selected}
      className={cn(
        'inline-grid shrink-0 place-items-center rounded-full transition-colors dur-short ease-standard focus-ring',
        'disabled:opacity-[.38] disabled:cursor-default',
        SIZE[size].box,
        VARIANT[variant],
        selected && variant === 'standard' && 'text-on-surface',
        className,
      )}
      {...rest}
    >
      <Icon name={icon} size={iconSize ?? SIZE[size].icon} />
    </button>
  );
});
