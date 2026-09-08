import { type CSSProperties, type HTMLAttributes } from 'react';
import { cn } from '@/lib/cn';

export interface SkeletonProps extends HTMLAttributes<HTMLSpanElement> {
  width?: number | string;
  height?: number | string;
  /** circle for avatars */
  shape?: 'rounded' | 'circle';
}

/** Shimmering placeholder block (1.6 s loop). Use inside `aria-busy` regions. */
export function Skeleton({
  width = '100%',
  height = 14,
  shape = 'rounded',
  className,
  style,
  ...rest
}: SkeletonProps) {
  const s: CSSProperties = { width, height, ...style };
  return (
    <span
      aria-hidden
      data-skeleton
      className={cn(
        'block animate-[shimmer_1.6s_linear_infinite] bg-[linear-gradient(90deg,var(--sc-high)_25%,var(--sc-highest)_50%,var(--sc-high)_75%)] bg-[length:200%_100%]',
        shape === 'circle' ? 'rounded-full' : 'rounded-[6px]',
        className,
      )}
      style={s}
      {...rest}
    />
  );
}

/** A recordings-list row while loading: avatar, headline, supporting line. */
export function SkeletonListItem() {
  return (
    <div className="flex min-h-[72px] items-center gap-4 rounded-lg bg-card py-3 pl-3 pr-4" aria-hidden>
      <Skeleton width={36} height={36} shape="circle" />
      <div className="flex-1">
        <Skeleton width="70%" height={14} className="my-[5px]" />
        <Skeleton width="45%" height={12} className="my-1" />
      </div>
    </div>
  );
}

/** Text lines for a loading card body. */
export function SkeletonText({ lines = 3 }: { lines?: number }) {
  const widths = ['90%', '96%', '70%', '84%', '60%'];
  return (
    <div aria-hidden className="flex flex-col gap-3">
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} width={widths[i % widths.length]} height={16} />
      ))}
    </div>
  );
}
