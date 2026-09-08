import { renderHook, waitFor } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { routeBody, useRoutes, useRoutingLog, useUpdateRoute } from './automations';
import { POLL, qk } from '../keys';
import { tokenStore } from '../token';
import { http, HttpResponse, server, TEST_TOKEN } from '@/test/msw';
import { makeTestQueryClient } from '@/test/render';
import * as fx from '@/test/fixtures';

function wrapper() {
  const qc = makeTestQueryClient();
  const W = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, W };
}

beforeEach(() => tokenStore.set(TEST_TOKEN));

describe('routeBody', () => {
  it('sends every field the server replaces, with the patch applied', () => {
    expect(routeBody(fx.routeNotes, { enabled: true })).toEqual({
      name: 'Vault notes',
      description: 'Thoughts and ideas worth keeping.',
      action_type: 'markdown',
      action_config: fx.routeNotes.action_config,
      enabled: true,
    });
  });
});

describe('useUpdateRoute', () => {
  it('updates the cached rule at once and keeps the server answer', async () => {
    const { qc, W } = wrapper();
    const routes = renderHook(() => useRoutes(), { wrapper: W });
    await waitFor(() => expect(routes.result.current.data?.routes).toHaveLength(2));
    const update = renderHook(() => useUpdateRoute(), { wrapper: W });
    let release: () => void = () => {};
    let saved: Record<string, unknown> | null = null;
    server.use(
      http.put('/api/v1/routes/:id', async ({ request }) => {
        saved = (await request.json()) as Record<string, unknown>;
        await new Promise<void>((r) => (release = r));
        return HttpResponse.json({ ...fx.routeNotes, ...saved });
      }),
      // After the save the list refetches; the server now knows the new state.
      http.get('/api/v1/routes', () =>
        HttpResponse.json({
          routes: [fx.routeAgent, saved ? { ...fx.routeNotes, ...saved } : fx.routeNotes],
        }),
      ),
    );
    update.result.current.mutate({ id: fx.routeNotes.id, body: routeBody(fx.routeNotes, { enabled: true }) });
    await waitFor(() =>
      expect(
        qc.getQueryData<{ routes: { id: string; enabled: boolean }[] }>(qk.routes)?.routes[1].enabled,
      ).toBe(true),
    );
    expect(update.result.current.isPending).toBe(true);
    release();
    await waitFor(() => expect(update.result.current.isSuccess).toBe(true));
    await waitFor(() => expect(qc.isFetching({ queryKey: qk.routes })).toBe(0));
    expect(routes.result.current.data?.routes[1].enabled).toBe(true);
  });

  it('rolls the cache back when the server refuses', async () => {
    const { qc, W } = wrapper();
    const routes = renderHook(() => useRoutes(), { wrapper: W });
    await waitFor(() => expect(routes.result.current.data?.routes).toHaveLength(2));
    let release: () => void = () => {};
    server.use(
      http.put('/api/v1/routes/:id', async () => {
        await new Promise<void>((r) => (release = r));
        return HttpResponse.json({ detail: 'no' }, { status: 500 });
      }),
    );
    const update = renderHook(() => useUpdateRoute(), { wrapper: W });
    update.result.current.mutate({
      id: fx.routeAgent.id,
      body: routeBody(fx.routeAgent, { enabled: false }),
    });
    await waitFor(() =>
      expect(qc.getQueryData<{ routes: { enabled: boolean }[] }>(qk.routes)?.routes[0].enabled).toBe(false),
    );
    release();
    await waitFor(() => expect(update.result.current.isError).toBe(true));
    await waitFor(() => expect(routes.result.current.data?.routes[0].enabled).toBe(true));
  });
});

describe('useRoutingLog', () => {
  it('loads the log with the limit and polls every 15 s', async () => {
    let seen = '';
    server.use(
      http.get('/api/v1/routing/log', ({ request }) => {
        seen = new URL(request.url).search;
        return HttpResponse.json({ runs: [fx.logRun] });
      }),
    );
    const { W } = wrapper();
    const { result } = renderHook(() => useRoutingLog(25), { wrapper: W });
    await waitFor(() => expect(result.current.data?.runs).toHaveLength(1));
    expect(seen).toBe('?limit=25');
    expect(POLL.idle).toBe(15_000);
  });
});
