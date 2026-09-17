/**
 * MSW server with default handlers for every endpoint, answering with the fixtures. Tests
 * override a handler with `server.use(http.get('/api/v1/…', …))` to shape a scenario.
 * Requests without a bearer header get 401 (except the public login-request routes), which is
 * how auth-gate behaviour is tested.
 */
import { http, HttpResponse, type HttpHandler, type HttpResponseResolver } from 'msw';
import { setupServer } from 'msw/node';
import * as fx from './fixtures';

export const TEST_TOKEN = 'test-token-123';

const authed = (req: Request) => req.headers.get('authorization') === `Bearer ${TEST_TOKEN}`;
const unauthorized = () => HttpResponse.json({ detail: 'invalid or missing bearer token' }, { status: 401 });

/** Wrap a handler so it demands the test bearer token. */
export function guarded(resolver: HttpResponseResolver): HttpResponseResolver {
  return (info) => (authed(info.request) ? resolver(info) : unauthorized());
}

export const handlers: HttpHandler[] = [
  http.get('/api/v1/health', () =>
    HttpResponse.json({ status: 'ok', service: 'transom', version: '0.1.0' }),
  ),

  // auth (public halves)
  http.post('/api/v1/login-requests', () =>
    HttpResponse.json(
      { id: 'req_1', expires_at: new Date(Date.now() + 180_000).toISOString(), poll_seconds: 2 },
      { status: 201 },
    ),
  ),
  http.get('/api/v1/login-requests/:id', () => HttpResponse.json({ status: 'pending' })),
  http.get('/api/v1/auth/check', ({ request }) =>
    authed(request) ? new HttpResponse(null, { status: 204 }) : unauthorized(),
  ),
  http.post(
    '/api/v1/auth/logout',
    guarded(() => new HttpResponse(null, { status: 204 })),
  ),
  http.get(
    '/api/v1/sessions',
    guarded(() => HttpResponse.json({ sessions: [fx.sessionCurrent] })),
  ),
  http.delete(
    '/api/v1/sessions/:id',
    guarded(() => new HttpResponse(null, { status: 204 })),
  ),

  // recordings
  http.get(
    '/api/v1/recordings',
    guarded(() =>
      HttpResponse.json({
        recordings: [
          fx.recordingPending,
          fx.recordingTranscribing,
          fx.recordingDone,
          fx.recordingSilent,
          fx.recordingFailed,
        ],
      }),
    ),
  ),
  http.get(
    '/api/v1/stats',
    guarded(() => HttpResponse.json(fx.stats)),
  ),
  http.get(
    '/api/v1/recordings/:id',
    guarded(({ params }) => {
      const all = [
        fx.recordingPending,
        fx.recordingTranscribing,
        fx.recordingDone,
        fx.recordingSilent,
        fx.recordingFailed,
      ];
      const rec = all.find((r) => r.id === params.id);
      return rec
        ? HttpResponse.json(rec)
        : HttpResponse.json({ detail: 'Recording not found.' }, { status: 404 });
    }),
  ),
  http.get(
    '/api/v1/recordings/:id/transcript',
    guarded(({ params }) =>
      params.id === fx.recordingDone.id
        ? HttpResponse.json(fx.transcript)
        : HttpResponse.json({ detail: "The transcript isn't ready yet." }, { status: 409 }),
    ),
  ),
  http.post(
    '/api/v1/recordings/:id/audio-link',
    guarded(({ params }) =>
      HttpResponse.json({
        url: `/api/v1/recordings/${params.id}/audio?sig=x&exp=1`,
        expires_at: Math.floor(Date.now() / 1000) + 3600,
      }),
    ),
  ),
  http.patch(
    '/api/v1/recordings/:id/speakers',
    guarded(async ({ request }) => {
      const { renames } = (await request.json()) as { renames: Record<string, string> };
      return HttpResponse.json({ ...fx.transcript, speaker_names: renames });
    }),
  ),
  http.patch(
    '/api/v1/recordings/:id',
    guarded(async ({ request }) => {
      const { title } = (await request.json()) as { title: string };
      return HttpResponse.json({ ...fx.recordingDone, title });
    }),
  ),
  http.get(
    '/api/v1/recordings/:id/export.md',
    guarded(
      () =>
        new HttpResponse('# Title\n\nbody', {
          headers: {
            'Content-Type': 'text/markdown',
            'Content-Disposition': `attachment; filename="title.md"; filename*=UTF-8''title.md`,
          },
        }),
    ),
  ),
  http.post(
    '/api/v1/recordings/:id/retranscribe',
    guarded(({ params }) => HttpResponse.json({ id: params.id, status: 'pending' })),
  ),
  http.delete(
    '/api/v1/recordings/:id',
    guarded(() => new HttpResponse(null, { status: 204 })),
  ),

  // automations
  http.get(
    '/api/v1/routes',
    guarded(() => HttpResponse.json({ routes: [fx.routeAgent, fx.routeNotes] })),
  ),
  http.post(
    '/api/v1/routes',
    guarded(async ({ request }) =>
      HttpResponse.json(
        { ...fx.routeAgent, ...((await request.json()) as object), id: 'route_new' },
        { status: 201 },
      ),
    ),
  ),
  http.put(
    '/api/v1/routes/:id',
    guarded(async ({ request, params }) =>
      HttpResponse.json({ ...fx.routeAgent, ...((await request.json()) as object), id: params.id }),
    ),
  ),
  http.delete(
    '/api/v1/routes/:id',
    guarded(() => new HttpResponse(null, { status: 204 })),
  ),
  http.get(
    '/api/v1/router/status',
    guarded(() => HttpResponse.json({ enabled: true, configured: true, model: 'some-model' })),
  ),
  http.get(
    '/api/v1/routing/log',
    guarded(() => HttpResponse.json({ runs: [fx.logRun] })),
  ),
  http.get(
    '/api/v1/recordings/:id/routing',
    guarded(() => HttpResponse.json({ runs: [fx.run], deliveries: [fx.deliveryDone] })),
  ),
  http.post(
    '/api/v1/recordings/:id/route',
    guarded(() => HttpResponse.json(fx.run)),
  ),
  http.post(
    '/api/v1/recordings/:id/route/preview',
    guarded(() =>
      HttpResponse.json({
        route_id: fx.routeAgent.id,
        route_name: fx.routeAgent.name,
        reason: 'A request.',
        model: 'm',
        matches: [{ route_id: fx.routeAgent.id, route_name: fx.routeAgent.name, reason: 'A request.' }],
      }),
    ),
  ),
  http.post(
    '/api/v1/deliveries/:id/retry',
    guarded(() => HttpResponse.json({ ...fx.deliveryFailed, status: 'ok', attempts: 4 })),
  ),

  // vocabulary
  http.get(
    '/api/v1/vocabulary',
    guarded(() => HttpResponse.json(fx.vocabulary)),
  ),
  http.put(
    '/api/v1/vocabulary',
    guarded(async ({ request }) =>
      HttpResponse.json({ entries: ((await request.json()) as { entries: unknown[] }).entries }),
    ),
  ),
  http.post(
    '/api/v1/vocabulary/import',
    guarded(() => HttpResponse.json({ entries: fx.vocabulary.entries, added: 1 })),
  ),

  // apk
  http.get(
    '/api/v1/apk/info',
    guarded(() => HttpResponse.json(fx.apkInfo)),
  ),
  http.delete(
    '/api/v1/apk',
    guarded(() => new HttpResponse(null, { status: 204 })),
  ),
];

export const server = setupServer(...handlers);
export { http, HttpResponse };
