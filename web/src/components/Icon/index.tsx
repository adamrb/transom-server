import { forwardRef, type SVGAttributes } from 'react';
import { cn } from '@/lib/cn';
import { ICON_VIEWBOX, iconPath, type IconName } from './icons';

export type { IconName } from './icons';
export { ICON_NAMES } from './icons';

/**
 * Icon sizes (px). Calibrated against the design mockup: rail 22, app-bar icon buttons 20,
 * list avatars 20 (inside a 36 px circle), buttons/chips 16, status words 14.
 */
export type IconSize = 14 | 16 | 18 | 20 | 22 | 24 | 28 | 32;

export interface IconProps extends Omit<SVGAttributes<SVGSVGElement>, 'name' | 'children'> {
  name: IconName;
  size?: IconSize;
  /** Accessible name. Omit for decorative icons (they get aria-hidden). */
  label?: string;
}

/** Material Symbols Rounded glyph, drawn in `currentColor`. */
export const Icon = forwardRef<SVGSVGElement, IconProps>(function Icon(
  { name, size = 24, label, className, ...rest },
  ref,
) {
  return (
    <svg
      ref={ref}
      viewBox={ICON_VIEWBOX}
      width={size}
      height={size}
      fill="currentColor"
      focusable="false"
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      data-icon={name}
      className={cn('inline-block shrink-0 align-middle', className)}
      {...rest}
    >
      <path d={iconPath(name)} />
    </svg>
  );
});
