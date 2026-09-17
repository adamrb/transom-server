import { useMemo, type KeyboardEvent, type ReactNode } from 'react';
import { Button, EmptyState, Skeleton, SkeletonListItem } from '@/components';
import { errorMessage, type Recording } from '@/api';
import { fmtDayHeader } from '@/lib/format';
import { DayHeader } from './DayHeader';
import { RecordingRow } from './RecordingRow';

export interface RecordingListProps {
  recordings: Recording[];
  /** The search term in effect for these rows (marks the snippets). */
  q: string;
  /** Whether a filter chip other than All is selected (changes the empty text). */
  filtered: boolean;
  loading: boolean;
  error: unknown;
  hasMore: boolean;
  loadingMore: boolean;
  selectedId: string | null;
  onOpen: (id: string) => void;
  onLoadMore: () => void;
  onRetry: () => void;
  onClearSearch: () => void;
  onConnectPhone: () => void;
  /** Phone: the ⋮ on each row. */
  onMore?: (rec: Recording, anchor: HTMLElement) => void;
  /** Extra content under the list (spacing for the mini player). */
  footer?: ReactNode;
}

type Entry = { key: string; kind: 'day'; label: string } | { key: string; kind: 'row'; rec: Recording };

/** Rows grouped by day (the server orders by upload time, so a day may appear twice: keyed by occurrence). */
export function groupByDay(recordings: Recording[], now = new Date()): Entry[] {
  const out: Entry[] = [];
  let lastDay: string | null = null;
  let groups = 0;
  for (const rec of recordings) {
    const day = fmtDayHeader(rec.started_at || rec.uploaded_at, now) || 'Undated';
    if (day !== lastDay) {
      lastDay = day;
      out.push({ key: `day:${day}#${groups++}`, kind: 'day', label: day });
    }
    out.push({ key: rec.id, kind: 'row', rec });
  }
  return out;
}

/**
 * The recordings list: day groups with sticky headers, keyed rows (polling never re-mounts a row),
 * Load more, and the loading / empty / error states. Arrow keys move between rows; Enter opens.
 */
export function RecordingList({
  recordings,
  q,
  filtered,
  loading,
  error,
  hasMore,
  loadingMore,
  selectedId,
  onOpen,
  onLoadMore,
  onRetry,
  onClearSearch,
  onConnectPhone,
  onMore,
  footer,
}: RecordingListProps) {
  const entries = useMemo(() => groupByDay(recordings), [recordings]);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    const rows = [...e.currentTarget.querySelectorAll<HTMLElement>('[data-row]')];
    const i = rows.indexOf(document.activeElement as HTMLElement);
    if (i < 0) return;
    e.preventDefault();
    const next = rows[i + (e.key === 'ArrowDown' ? 1 : -1)];
    next?.focus();
  };

  let body: ReactNode;
  if (loading && !recordings.length) {
    body = (
      <div aria-busy="true" aria-label="Loading recordings" className="flex flex-col gap-1.5">
        <div className="px-3 pt-1 pb-2">
          <Skeleton width={56} height={12} />
        </div>
        {Array.from({ length: 8 }, (_, i) => (
          <SkeletonListItem key={i} />
        ))}
      </div>
    );
  } else if (error && !recordings.length) {
    body = (
      <div role="alert" className="px-4 py-6 text-center text-body-m text-on-surface-variant">
        <p className="m-0 mb-3">{errorMessage(error, "Couldn't load recordings.")}</p>
        <Button variant="tonal" size="sm" onClick={onRetry}>
          Try again
        </Button>
      </div>
    );
  } else if (!recordings.length) {
    body = q ? (
      <div className="px-4 py-6 text-center text-body-m text-on-surface-variant">
        <p className="m-0 mb-3">No recordings match “{q}”.</p>
        <Button variant="tonal" size="sm" onClick={onClearSearch}>
          Clear search
        </Button>
      </div>
    ) : filtered ? (
      <div className="px-4 py-6 text-center text-body-m text-on-surface-variant">No recordings here.</div>
    ) : (
      <EmptyState
        icon="graphic_eq"
        headline="No recordings yet"
        description="Recordings sync from the Transom app on your phone and show up here a few seconds later."
        action={
          <Button variant="tonal" icon="qr_code" onClick={onConnectPhone}>
            Connect a phone
          </Button>
        }
        className="min-h-[60vh]"
      />
    );
  } else {
    body = (
      <>
        {entries.map((e) =>
          e.kind === 'day' ? (
            <DayHeader key={e.key}>{e.label}</DayHeader>
          ) : (
            <RecordingRow
              key={e.key}
              rec={e.rec}
              q={q}
              selected={e.rec.id === selectedId}
              onOpen={onOpen}
              onMore={onMore}
            />
          ),
        )}
        {hasMore && (
          <div className="flex justify-center py-3">
            <Button variant="tonal" size="sm" loading={loadingMore} onClick={onLoadMore}>
              Load more
            </Button>
          </div>
        )}
      </>
    );
  }

  return (
    <div
      role="region"
      aria-label="Recording list"
      onKeyDown={onKeyDown}
      className="flex min-h-0 flex-1 flex-col overflow-y-auto px-3 pt-1 pb-(--content-bottom-pad) [scrollbar-width:thin]"
    >
      {body}
      {footer}
    </div>
  );
}
