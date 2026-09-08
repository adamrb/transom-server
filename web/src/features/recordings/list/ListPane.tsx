import type { ReactNode } from 'react';
import { SearchBar } from '@/components';
import { useRecordingPages, type Recording } from '@/api';
import { SectionAppBar } from '@/features/shell/SectionAppBar';
import { FilterChips } from './FilterChips';
import { RecordingList } from './RecordingList';
import { useDebounced, useListState } from './useListState';

export interface ListPaneProps {
  selectedId: string | null;
  onOpen: (id: string) => void;
  onConnectPhone: () => void;
  onMore?: (rec: Recording, anchor: HTMLElement) => void;
  /** Rendered under the rows (room for the phone mini player). */
  footer?: ReactNode;
  className?: string;
}

/** The server accepts search terms up to 200 characters. */
export const MAX_SEARCH_CHARS = 200;

/** The left pane (or the whole screen on phone): app bar, search, filter chips and the list. */
export function ListPane({ selectedId, onOpen, onConnectPhone, onMore, footer, className }: ListPaneProps) {
  const { q, status, setQ, setStatus, clearSearch } = useListState();
  const query = useDebounced(q.trim().slice(0, MAX_SEARCH_CHARS), 250);
  const pages = useRecordingPages({ q: query, status });
  const recordings = pages.data?.recordings ?? [];

  return (
    <section aria-labelledby="recordings-title" className={className}>
      <SectionAppBar title="Recordings" id="recordings-title" />
      <div className="flex flex-col gap-3 px-4 pt-(--content-top-pad) pb-1 md:pt-2">
        <SearchBar
          value={q}
          onChange={(v) => setQ(v.slice(0, MAX_SEARCH_CHARS))}
          maxLength={MAX_SEARCH_CHARS}
          placeholder="Search recordings"
        />
        <FilterChips value={status} onChange={setStatus} />
      </div>
      <RecordingList
        recordings={recordings}
        q={query}
        filtered={!!status}
        loading={pages.isPending}
        error={pages.error}
        hasMore={!!pages.hasNextPage}
        loadingMore={pages.isFetchingNextPage}
        selectedId={selectedId}
        onOpen={onOpen}
        onLoadMore={() => void pages.fetchNextPage()}
        onRetry={() => void pages.refetch()}
        onClearSearch={clearSearch}
        onConnectPhone={onConnectPhone}
        onMore={onMore}
        footer={footer}
      />
    </section>
  );
}
