import { cn } from '@/lib/cn';

/** Sticky day group heading: Today, Yesterday, Sun, Sep 6, Dec 24, 2025. */
export function DayHeader({ children, className }: { children: string; className?: string }) {
  return (
    <div
      role="presentation"
      data-day-header
      className={cn(
        'sticky top-0 z-[1] bg-surface px-3 pt-4 pb-2 text-title-s text-on-surface-variant first:pt-1',
        className,
      )}
    >
      {children}
    </div>
  );
}
