import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from '@tanstack/react-query';
import { apiJson, apiRequest, filenameFromDisposition } from '../client';
import { POLL, qk } from '../keys';
import {
  AudioLinkSchema,
  isInFlight,
  RecordingListSchema,
  RecordingSchema,
  RetranscribeSchema,
  TranscriptSchema,
  type AudioLink,
  type Recording,
  type RecordingList,
  type RecordingListParams,
  type Transcript,
} from '../types';

/* ---------------------------------------- reads ---------------------------------------- */

export async function fetchRecordings(params: RecordingListParams = {}): Promise<RecordingList> {
  return apiJson('/recordings', RecordingListSchema, {
    query: {
      limit: params.limit,
      offset: params.offset,
      status: params.status || undefined,
      q: params.q || undefined,
    },
  });
}

/**
 * The recordings list. Polls every 15 s, every 5 s while any listed recording is pending or
 * transcribing (paused while the tab is hidden). Pass `q`/`status` for search and filter chips;
 * use `offset` for "Load more" (feature: merge pages with the same query key).
 */
export function useRecordings(
  params: RecordingListParams = {},
  options?: Partial<UseQueryOptions<RecordingList>>,
) {
  return useQuery({
    queryKey: qk.recordings.list(params),
    queryFn: () => fetchRecordings(params),
    refetchInterval: (query) => (query.state.data?.recordings.some(isInFlight) ? POLL.inFlight : POLL.idle),
    placeholderData: (prev) => prev, // keep rows on screen while a search refetches
    ...options,
  });
}

/** Rows per page of the recordings list ("Load more" asks for the next page by `offset`). */
export const RECORDINGS_PAGE = 50;

/**
 * The recordings list in pages: page n is `offset = n * RECORDINGS_PAGE`. `fetchNextPage` is
 * "Load more"; `hasNextPage` when the last page was full. Polls like `useRecordings` (every page
 * is refetched in order, so every loaded row stays current). Rows are de-duplicated by id.
 */
export function useRecordingPages(params: Pick<RecordingListParams, 'q' | 'status'> = {}) {
  const key: Required<Pick<RecordingListParams, 'q' | 'status'>> = {
    q: params.q || '',
    status: params.status || '',
  };
  return useInfiniteQuery({
    queryKey: [...qk.recordings.all, 'pages', key] as const,
    queryFn: ({ pageParam }) => fetchRecordings({ ...key, limit: RECORDINGS_PAGE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (last, pages) =>
      last.recordings.length >= RECORDINGS_PAGE
        ? pages.reduce((n, p) => n + p.recordings.length, 0)
        : undefined,
    refetchInterval: (query) =>
      query.state.data?.pages.some((p) => p.recordings.some(isInFlight)) ? POLL.inFlight : POLL.idle,
    placeholderData: (prev) => prev, // keep rows on screen while a search refetches
    select: (data) => {
      const seen = new Set<string>();
      const recordings: Recording[] = [];
      for (const page of data.pages)
        for (const r of page.recordings)
          if (!seen.has(r.id)) {
            seen.add(r.id);
            recordings.push(r);
          }
      return { recordings, pages: data.pages.length };
    },
  });
}

export async function fetchRecording(id: string): Promise<Recording> {
  return apiJson(`/recordings/${encodeURIComponent(id)}`, RecordingSchema);
}

/** One recording. Polls every 5 s while it is pending or transcribing, otherwise not at all. */
export function useRecording(id: string | null | undefined, options?: Partial<UseQueryOptions<Recording>>) {
  return useQuery({
    queryKey: qk.recordings.detail(id ?? ''),
    queryFn: () => fetchRecording(id!),
    enabled: !!id,
    refetchInterval: (query) => (query.state.data && isInFlight(query.state.data) ? POLL.inFlight : false),
    ...options,
  });
}

export async function fetchTranscript(id: string): Promise<Transcript> {
  return apiJson(`/recordings/${encodeURIComponent(id)}/transcript`, TranscriptSchema);
}

/**
 * The transcript document. 409 (not ready yet) surfaces as an ApiError with `.conflict`; the
 * detail pane should show the in-flight state instead of an error. Only enabled once the
 * recording says `has_transcript`.
 */
export function useTranscript(id: string | null | undefined, enabled = true) {
  return useQuery({
    queryKey: qk.recordings.transcript(id ?? ''),
    queryFn: () => fetchTranscript(id!),
    enabled: !!id && enabled,
    staleTime: 60_000,
  });
}

/** A one-hour signed URL for `<audio src>` (works without a header). */
export async function fetchAudioLink(id: string): Promise<AudioLink> {
  return apiJson(`/recordings/${encodeURIComponent(id)}/audio-link`, AudioLinkSchema, { method: 'POST' });
}

/** The audio as a blob (download button, or playback fallback when audio links are unsupported). */
export async function fetchAudioBlob(id: string): Promise<Blob> {
  const r = await apiRequest(`/recordings/${encodeURIComponent(id)}/audio`);
  return r.blob();
}

/** Markdown export: same file the Android app produces. Returns the text and the file name. */
export async function fetchExportMarkdown(id: string): Promise<{ name: string; markdown: string }> {
  const r = await apiRequest(`/recordings/${encodeURIComponent(id)}/export.md`);
  return {
    name: filenameFromDisposition(r.headers.get('content-disposition'), 'transcript.md'),
    markdown: await r.text(),
  };
}

/* -------------------------------------- mutations -------------------------------------- */

/** PATCH title. Updates the cached row and detail in place, then refetches the list. */
export function useRenameRecording() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      apiJson(`/recordings/${encodeURIComponent(id)}`, RecordingSchema, { method: 'PATCH', json: { title } }),
    onSuccess: (rec) => {
      qc.setQueryData(qk.recordings.detail(rec.id), rec);
      void qc.invalidateQueries({ queryKey: qk.recordings.all });
    },
  });
}

/** PATCH speaker names: { "Speaker 1": "Alex" }. Returns the updated transcript. */
export function useRenameSpeakers() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, renames }: { id: string; renames: Record<string, string> }) =>
      apiJson(`/recordings/${encodeURIComponent(id)}/speakers`, TranscriptSchema, {
        method: 'PATCH',
        json: { renames },
      }),
    onSuccess: (t, { id }) => {
      qc.setQueryData(qk.recordings.transcript(id), t);
      void qc.invalidateQueries({ queryKey: qk.recordings.all });
    },
  });
}

/** Reset a recording so the worker transcribes it again (confirm first: the transcript is deleted). */
export function useRetranscribe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiJson(`/recordings/${encodeURIComponent(id)}/retranscribe`, RetranscribeSchema, { method: 'POST' }),
    onSuccess: (_d, id) => {
      qc.removeQueries({ queryKey: qk.recordings.transcript(id) });
      void qc.invalidateQueries({ queryKey: qk.recordings.all });
      void qc.invalidateQueries({ queryKey: qk.stats });
    },
  });
}

/** Delete a recording and its files (confirm first). */
export function useDeleteRecording() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await apiRequest(`/recordings/${encodeURIComponent(id)}`, { method: 'DELETE' });
    },
    onSuccess: (_d, id) => {
      qc.removeQueries({ queryKey: qk.recordings.detail(id) });
      qc.removeQueries({ queryKey: qk.recordings.transcript(id) });
      qc.removeQueries({ queryKey: qk.recordings.routing(id) });
      void qc.invalidateQueries({ queryKey: qk.recordings.all });
      void qc.invalidateQueries({ queryKey: qk.stats });
    },
  });
}
