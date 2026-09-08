import { type HTMLAttributes, type ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { Icon, type IconName } from '@/components/Icon';

export type BannerTone = 'success' | 'warning' | 'error' | 'neutral';

export interface BannerProps extends HTMLAttributes<HTMLDivElement> {
  tone?: BannerTone;
  icon?: IconName;
  /** Trailing action (a text button). */
  action?: ReactNode;
  children: ReactNode;
}

const TONE: Record<BannerTone, { cls: string; icon: IconName }> = {
  success: { cls: 'bg-success-container text-on-success-container', icon: 'check_circle' },
  warning: { cls: 'bg-warning-container text-on-warning-container', icon: 'warning' },
  error: { cls: 'bg-error-container text-on-error-container', icon: 'error' },
  neutral: { cls: 'bg-surface-container-high text-on-surface-variant', icon: 'description' },
};

/** Tonal status banner with an icon, no border (Automations "on", connection warnings). */
export function Banner({ tone = 'neutral', icon, action, className, children, ...rest }: BannerProps) {
  const t = TONE[tone];
  return (
    <div
      role={tone === 'error' || tone === 'warning' ? 'alert' : 'status'}
      data-tone={tone}
      className={cn(
        'flex items-center gap-3.5 rounded-lg px-4.5 py-3.5 text-body-m [&_b]:font-medium',
        t.cls,
        className,
      )}
      {...rest}
    >
      <Icon name={icon ?? t.icon} size={22} className="shrink-0" />
      <div className="flex-1">{children}</div>
      {action}
    </div>
  );
}
