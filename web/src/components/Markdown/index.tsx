import { lazy, memo, Suspense } from 'react';
import { cn } from '@/lib/cn';
import { ErrorBoundary } from '@/components/ErrorBoundary';

export interface MarkdownProps {
  children: string;
  className?: string;
  /** Give headings ids (`sum-h-0`, …) so "Jump to" can scroll to them. */
  headingIds?: boolean;
}

// The markdown stack is the largest dependency after React itself and no screen needs it before
// a summary or a rule description is on screen, so it loads on first use (one small chunk).
const Renderer = lazy(() => import('./MarkdownRenderer'));

/** Until the renderer arrives: the source split into paragraphs, so the text is readable at once. */
function PlainFallback({ children }: { children: string }) {
  return (
    <>
      {children
        .split(/\n{2,}/)
        .filter(Boolean)
        .map((para, i) => (
          <p key={i} className="mb-2.5 whitespace-pre-wrap last:mb-0">
            {para}
          </p>
        ))}
    </>
  );
}

/**
 * Summaries and rule descriptions: GitHub-flavoured markdown (bold, lists, headings, code).
 * Raw HTML is never rendered. Links open in a new tab. Body text is 15/24 on-surface-body,
 * bold is on-surface 500 (the app's summary style). If the renderer chunk cannot be fetched the
 * plain paragraphs simply stay.
 */
export const Markdown = memo(function Markdown({ children, className, headingIds }: MarkdownProps) {
  const plain = <PlainFallback>{children}</PlainFallback>;
  return (
    <div className={cn('text-[15px] leading-6 tracking-[.15px] text-on-surface-body', className)}>
      <ErrorBoundary fallback={plain}>
        <Suspense fallback={plain}>
          <Renderer headingIds={headingIds}>{children}</Renderer>
        </Suspense>
      </ErrorBoundary>
    </div>
  );
});
