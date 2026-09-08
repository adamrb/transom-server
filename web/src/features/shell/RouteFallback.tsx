import type { ReactNode } from 'react';
import { Button } from '@/components/Button';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { SkeletonListItem } from '@/components/Skeleton';
import { SectionAppBar } from './SectionAppBar';

/**
 * What a section shows while its code chunk downloads (the pages are loaded on demand): the
 * section's app bar and a few skeleton rows, so the frame is in place before the content.
 */
export function RouteFallback({ title }: { title: string }) {
  return (
    <div className="flex min-h-0 flex-1 flex-col" aria-busy="true" aria-label={`Loading ${title}`}>
      <SectionAppBar title={title} />
      <div className="flex flex-col gap-2 px-6 pt-(--content-top-pad) pb-(--content-bottom-pad) max-md:px-4">
        <div className="mx-auto flex w-full max-w-[860px] flex-col gap-2">
          <SkeletonListItem />
          <SkeletonListItem />
          <SkeletonListItem />
        </div>
      </div>
    </div>
  );
}

/**
 * A part of the app that could not be loaded (its chunk failed to download, typically because a
 * deployment replaced the assets under an open tab). In user words, with a way out.
 */
export function LoadFailed({ what = 'this screen', onRetry }: { what?: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="mx-auto flex max-w-[480px] flex-col items-start gap-3 px-6 py-8">
      <p className="m-0 text-body-l text-on-surface">Couldn't load {what}.</p>
      <p className="m-0 text-body-m text-on-surface-variant">
        Your connection may have dropped, or the server was just updated. Reloading usually fixes it.
      </p>
      <div className="flex gap-2">
        <Button onClick={() => window.location.reload()}>Reload</Button>
        {onRetry && (
          <Button variant="text" onClick={onRetry}>
            Try again
          </Button>
        )}
      </div>
    </div>
  );
}

/** Error boundary for a lazily loaded part: shows `LoadFailed` with Reload / Try again. */
export function LoadBoundary({
  what,
  resetKey,
  children,
}: {
  what?: string;
  resetKey?: unknown;
  children: ReactNode;
}) {
  return (
    <ErrorBoundary resetKey={resetKey} fallback={(retry) => <LoadFailed what={what} onRetry={retry} />}>
      {children}
    </ErrorBoundary>
  );
}
