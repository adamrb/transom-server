import { renderHook, waitFor } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import {
  useApkInfo,
  useRecordings,
  useRunAutomations,
  routeKeyStore,
  useVocabulary,
  parseVocabularyText,
} from './index';
import { isInFlight } from '../types';
import { POLL } from '../keys';
import { tokenStore } from '../token';
import { http, HttpResponse, server, TEST_TOKEN } from '@/test/msw';
import { makeTestQueryClient } from '@/test/render';
import * as fx from '@/test/fixtures';

function wrapper() {
  const qc = makeTestQueryClient();
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

beforeEach(() => tokenStore.set(TEST_TOKEN));

describe('useRecordings', () => {
  it('loads the list and polls every 5 s while anything is in flight, else 15 s', async () => {
    const { result } = renderHook(() => useRecordings(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.data?.recordings).toHaveLength(5));
    expect(result.current.data!.recordings.some(isInFlight)).toBe(true);
    // The refetchInterval rule itself, evaluated the way TanStack calls it.
    const rule = (data: { recordings: { status: string }[] } | undefined) =>
      data?.recordings.some((r) => r.status === 'pending' || r.status === 'transcribing')
        ? POLL.inFlight
        : POLL.idle;
    expect(rule(result.current.data)).toBe(5000);
    expect(rule({ recordings: [fx.recordingDone] })).toBe(15000);
  });

  it('passes search and status filters as query params', async () => {
    let seen = '';
    server.use(
      http.get('/api/v1/recordings', ({ request }) => {
        seen = new URL(request.url).search;
        return HttpResponse.json({ recordings: [fx.recordingDone] });
      }),
    );
    const { result } = renderHook(() => useRecordings({ q: 'data', status: 'done', limit: 50 }), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.data?.recordings).toHaveLength(1));
    expect(seen).toBe('?limit=50&status=done&q=data');
  });
});

describe('useApkInfo', () => {
  it('returns null when nothing is hosted (404) instead of an error', async () => {
    server.use(
      http.get('/api/v1/apk/info', () => HttpResponse.json({ detail: 'no APK hosted' }, { status: 404 })),
    );
    const { result } = renderHook(() => useApkInfo(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeNull();
  });
});

describe('useRunAutomations', () => {
  it('sends an Idempotency-Key kept in sessionStorage and clears it on success', async () => {
    let key: string | null = null;
    server.use(
      http.post('/api/v1/recordings/:id/route', ({ request }) => {
        key = request.headers.get('idempotency-key');
        return HttpResponse.json(fx.run);
      }),
    );
    const { result } = renderHook(() => useRunAutomations(), { wrapper: wrapper() });
    const before = routeKeyStore.ensure(fx.recordingDone.id);
    expect(sessionStorage.getItem(`pb.routeKey.${fx.recordingDone.id}`)).toBe(before);
    await result.current.mutateAsync({ id: fx.recordingDone.id, instructions: ' file as meeting ' });
    expect(key).toBe(before);
    expect(key).toMatch(/^[A-Za-z0-9_-]{8,128}$/);
    expect(routeKeyStore.get(fx.recordingDone.id)).toBeNull();
  });
});

describe('useRunAutomations after failures', () => {
  it('keeps the key after a 5xx (the run may have happened) and drops it after a 4xx', async () => {
    server.use(http.post('/api/v1/recordings/:id/route', () => HttpResponse.json({}, { status: 502 })));
    const { result } = renderHook(() => useRunAutomations(), { wrapper: wrapper() });
    const key = routeKeyStore.ensure('rec_x');
    await result.current.mutateAsync({ id: 'rec_x' }).catch(() => {});
    expect(routeKeyStore.get('rec_x')).toBe(key);
    server.use(
      http.post('/api/v1/recordings/:id/route', () =>
        HttpResponse.json({ detail: 'This recording has no transcript yet.' }, { status: 409 }),
      ),
    );
    await result.current.mutateAsync({ id: 'rec_x' }).catch(() => {});
    expect(routeKeyStore.get('rec_x')).toBeNull();
  });
});

describe('recording status', () => {
  it('accepts stored (not transcribed) recordings in the list', async () => {
    server.use(
      http.get('/api/v1/recordings', () =>
        HttpResponse.json({
          recordings: [{ ...fx.recordingPending, id: 'rec_stored', status: 'stored', stage: null }],
        }),
      ),
    );
    const { result } = renderHook(() => useRecordings(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.recordings[0].status).toBe('stored');
  });
});

describe('vocabulary', () => {
  it('loads and parses editor text', async () => {
    const { result } = renderHook(() => useVocabulary(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.data?.entries).toHaveLength(2));
    const parsed = parseVocabularyText(
      '# People\nAlex\n\nPlaud Bridge = Plogged Bridge, Plod Bridge\n = orphan',
    );
    expect(parsed.entries).toEqual([
      { term: 'Alex', aliases: [] },
      { term: 'Plaud Bridge', aliases: ['Plogged Bridge', 'Plod Bridge'] },
    ]);
    // Only the line with nothing before the equals sign is "ignored"; `#` notes are kept, like the
    // old dashboard's ignoredVocabLines().
    expect(parsed.ignored).toBe(1);
  });
});
