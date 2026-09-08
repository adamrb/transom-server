import { type HTMLAttributes } from 'react';
import { cn } from '@/lib/cn';
import { Icon, type IconName } from '@/components/Icon';
import { ProgressRing } from '@/components/ProgressRing';

/**
 * The leading glyph of a recording row. One of:
 *   waveform  finished, one speaker (or undiarized)
 *   group     finished, several speakers (slate speaker tone)
 *   silent    finished, no speech
 *   waiting   pending: spinning amber ring around a clock
 *   progress  transcribing: determinate amber ring with the percentage
 *   failed    error tone
 * plus generic `icon` (settings rows, rule leads) and `text` (numbered steps).
 */
export type AvatarKind =
  'waveform' | 'group' | 'silent' | 'waiting' | 'progress' | 'failed' | 'icon' | 'text';

export interface AvatarProps extends Omit<HTMLAttributes<HTMLSpanElement>, 'children'> {
  kind: AvatarKind;
  /** progress: 0..1 */
  value?: number | null;
  /** icon kind */
  icon?: IconName;
  /** text kind */
  text?: string;
  /** Diameter, default 36 (list avatars are 36 px). */
  size?: 36 | 40;
  /** Square-ish 12 px corners instead of a circle (settings rows, rule cards). */
  shape?: 'circle' | 'rounded';
  /** In a selected list row the avatar sits on the lowest surface so it still reads. */
  selected?: boolean;
  label?: string;
}

const ICON: Partial<Record<AvatarKind, IconName>> = {
  waveform: 'graphic_eq',
  group: 'group',
  silent: 'volume_off',
  failed: 'error',
  waiting: 'schedule',
};

export function Avatar({
  kind,
  value,
  icon,
  text,
  size = 36,
  shape = 'circle',
  selected,
  label,
  className,
  ...rest
}: AvatarProps) {
  const glyph = size === 36 ? 18 : 20;
  const base = cn(
    'relative inline-grid shrink-0 place-items-center font-medium',
    size === 36 ? 'size-9' : 'size-10',
    shape === 'circle' ? 'rounded-full' : 'rounded-md',
  );
  const tone =
    kind === 'failed'
      ? 'bg-error-container text-on-error-container'
      : kind === 'group'
        ? 'bg-spk1 text-on-spk1'
        : selected
          ? 'bg-surface-container-lowest text-on-surface-variant dark:bg-surface-container-highest'
          : 'bg-surface-container-high text-on-surface-variant';

  if (kind === 'waiting' || kind === 'progress') {
    return (
      <span
        data-kind={kind}
        className={cn(base, 'bg-transparent text-warning', className)}
        aria-label={label}
        {...rest}
      >
        {/* The ring sits in its own absolutely positioned layer so the glyph stays centred on it. */}
        <span className="absolute inset-0 grid place-items-center">
          <ProgressRing
            value={kind === 'progress' ? value : undefined}
            size={size}
            showValue={kind === 'progress'}
            label={label}
          />
        </span>
        {kind === 'waiting' && <Icon name="schedule" size={size === 36 ? 16 : 18} className="relative" />}
      </span>
    );
  }
  return (
    <span
      data-kind={kind}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={cn(base, tone, className)}
      {...rest}
    >
      {kind === 'text' ? (
        <span className="text-[15px]">{text}</span>
      ) : (
        <Icon name={kind === 'icon' ? (icon ?? 'graphic_eq') : ICON[kind]!} size={glyph} />
      )}
    </span>
  );
}
