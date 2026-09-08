import type { ReactNode } from 'react';
import { Icon } from '@/components';
import { cn } from '@/lib/cn';

/** "Details" disclosure for raw text (error_detail, a delivery's last error): closed by default. */
export function Disclosure({
  summary = 'Details',
  children,
  className,
}: {
  summary?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <details className={cn('mt-2 group', className)}>
      <summary className="inline-flex h-8 cursor-pointer list-none items-center gap-1 rounded-sm pr-2.5 pl-1.5 text-[13px] font-medium text-on-surface-variant hover:bg-state-hover focus-ring [&::-webkit-details-marker]:hidden">
        <Icon
          name="keyboard_arrow_down"
          size={16}
          className="transition-transform dur-short group-open:rotate-180"
        />
        {summary}
      </summary>
      <pre className="mt-1.5 mb-0 overflow-auto rounded-md bg-surface-container-high p-3 font-mono text-[12.5px] leading-relaxed whitespace-pre-wrap [overflow-wrap:anywhere] text-on-surface-body">
        {children}
      </pre>
    </details>
  );
}
