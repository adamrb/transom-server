import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, apiJson, apiRequest } from '../client';
import { POLL, qk } from '../keys';
import { session, STORAGE_KEYS } from '@/lib/storage';
import {
  DeliverySchema,
  PreviewSchema,
  RecordingRoutingSchema,
  RouterRunSchema,
  RouterStatusSchema,
  RouteSchema,
  RoutesSchema,
  RoutingLogSchema,
  type Delivery,
  type RecordingRouting,
  type RouteBody,
  type RouterRun,
} from '../types';

/* ------------------------------------------ rules ------------------------------------------ */

/** All rules (routes), enabled or not. */
export function useRoutes() {
  return useQuery({ queryKey: qk.routes, queryFn: () => apiJson('/routes', RoutesSchema) });
}

export function useCreateRoute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RouteBody) => apiJson('/routes', RouteSchema, { method: 'POST', json: body }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.routes }),
  });
}

/**
 * PUT a rule. The server rebuilds `action_config` from the body, so a webhook rule's secret header
 * must be resent every time: the new value when the user typed one, otherwise the route's current
 * `action_config.auth_header` ("Set. Leave blank to keep it."); omit it only to clear it.
 */
export function useUpdateRoute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: RouteBody }) =>
      apiJson(`/routes/${encodeURIComponent(id)}`, RouteSchema, { method: 'PUT', json: body }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.routes }),
  });
}

export function useDeleteRoute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await apiRequest(`/routes/${encodeURIComponent(id)}`, { method: 'DELETE' });
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.routes }),
  });
}

/* ------------------------------------------ status ----------------------------------------- */

/** Whether automations are turned on and set up on the server (the banner). Never show `.model`. */
export function useRouterStatus() {
  return useQuery({
    queryKey: qk.router.status,
    queryFn: () => apiJson('/router/status', RouterStatusSchema),
    staleTime: 60_000,
  });
}

/* --------------------------------------- activity log --------------------------------------- */

/** Recent runs with deliveries and the recording each belongs to. Polls every 15 s while mounted. */
export function useRoutingLog(limit = 50) {
  return useQuery({
    queryKey: qk.router.log(limit),
    queryFn: () => apiJson('/routing/log', RoutingLogSchema, { query: { limit } }),
    refetchInterval: POLL.idle,
  });
}

/** A delivery whose consumer has the job but has not reported yet. */
export const isDeliveryWorking = (d: Pick<Delivery, 'result_status' | 'status'>) =>
  d.result_status === 'queued' || (d.status === 'pending' && !d.result_status);

export const routingWorking = (r: RecordingRouting | undefined) => !!r?.deliveries.some(isDeliveryWorking);

/** Runs and deliveries for one recording. Polls every 15 s while a delivery is still working. */
export function useRecordingRouting(id: string | null | undefined, enabled = true) {
  return useQuery({
    queryKey: qk.recordings.routing(id ?? ''),
    queryFn: () => apiJson(`/recordings/${encodeURIComponent(id!)}/routing`, RecordingRoutingSchema),
    enabled: !!id && enabled,
    refetchInterval: (query) => (routingWorking(query.state.data) ? POLL.routingWorking : false),
  });
}

/* ------------------------------------- run / preview / retry ------------------------------------- */

function newIdempotencyKey(): string {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

/**
 * The idempotency key for "run automations" on a recording, kept in sessionStorage so a reload
 * while the request is out does not start a second run. Cleared once the run has completed.
 */
export const routeKeyStore = {
  get: (id: string) => session.get(STORAGE_KEYS.routeKey(id)),
  ensure(id: string): string {
    const k = session.get(STORAGE_KEYS.routeKey(id));
    if (k) return k;
    const fresh = newIdempotencyKey();
    session.set(STORAGE_KEYS.routeKey(id), fresh);
    return fresh;
  },
  clear: (id: string) => session.remove(STORAGE_KEYS.routeKey(id)),
};

/** Instructions typed for a re-run, kept per recording across a reload. */
export const routeInstructionsStore = {
  get: (id: string) => session.get(STORAGE_KEYS.routeInstructions(id)),
  set: (id: string, v: string) =>
    v
      ? session.set(STORAGE_KEYS.routeInstructions(id), v)
      : session.remove(STORAGE_KEYS.routeInstructions(id)),
  clear: (id: string) => session.remove(STORAGE_KEYS.routeInstructions(id)),
};

/**
 * Run automations on a recording (again). Sends an Idempotency-Key from `routeKeyStore` so a
 * re-sent request returns the run already made. On success the key is cleared and the
 * recording's routing plus the activity log refetch.
 */
export function useRunAutomations() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, instructions }: { id: string; instructions?: string | null }): Promise<RouterRun> =>
      apiJson(`/recordings/${encodeURIComponent(id)}/route`, RouterRunSchema, {
        method: 'POST',
        headers: { 'Idempotency-Key': routeKeyStore.ensure(id) },
        json: { instructions: instructions?.trim() || null },
      }),
    onSuccess: (_run, { id }) => {
      routeKeyStore.clear(id);
      void qc.invalidateQueries({ queryKey: qk.recordings.routing(id) });
      void qc.invalidateQueries({ queryKey: qk.router.all });
    },
    onError: (err, { id }) => {
      // A definitive 4xx means the server saw and refused it: a new attempt needs a new key.
      // A 5xx, a proxy error or a network failure may have run the automations anyway, so the
      // key stays and the retry replays that run instead of starting a second one.
      if (err instanceof ApiError && err.status >= 400 && err.status < 500) routeKeyStore.clear(id);
    },
  });
}

/** Dry run: what would automations do? Nothing is delivered or recorded. */
export function usePreviewAutomations() {
  return useMutation({
    mutationFn: ({ id, instructions }: { id: string; instructions?: string | null }) =>
      apiJson(`/recordings/${encodeURIComponent(id)}/route/preview`, PreviewSchema, {
        method: 'POST',
        json: { instructions: instructions?.trim() || null },
      }),
  });
}

/** Retry a failed delivery (or one whose consumer never reported). */
export function useRetryDelivery() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (deliveryId: string) =>
      apiJson(`/deliveries/${encodeURIComponent(deliveryId)}/retry`, DeliverySchema, { method: 'POST' }),
    onSuccess: (d) => {
      if (d.recording_id) void qc.invalidateQueries({ queryKey: qk.recordings.routing(d.recording_id) });
      void qc.invalidateQueries({ queryKey: qk.router.all });
    },
  });
}
