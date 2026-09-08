import { z } from 'zod';
import {
  ApiError,
  apiJson,
  apiRequest,
  AUTH_REQUIRED_EVENT,
  errorMessage,
  filenameFromDisposition,
  NetworkError,
} from './client';
import { tokenStore } from './token';
import { http, HttpResponse, server, TEST_TOKEN } from '@/test/msw';

describe('api client', () => {
  it('sends the stored bearer token and validates the response', async () => {
    tokenStore.set(TEST_TOKEN);
    const stats = await apiJson('/stats', z.looseObject({ recordings: z.number() }));
    expect(stats.recordings).toBe(5);
  });

  it('broadcasts auth-required on 401 and throws an ApiError without a status in the message', async () => {
    tokenStore.set('wrong-token');
    const listener = vi.fn();
    window.addEventListener(AUTH_REQUIRED_EVENT, listener);
    await expect(apiRequest('/stats')).rejects.toBeInstanceOf(ApiError);
    expect(listener).toHaveBeenCalledTimes(1);
    try {
      await apiRequest('/stats');
    } catch (e) {
      expect((e as ApiError).unauthorized).toBe(true);
      expect((e as ApiError).message).not.toMatch(/401/);
    }
    window.removeEventListener(AUTH_REQUIRED_EVENT, listener);
  });

  it('turns the FastAPI detail into the message for 4xx and hides 5xx bodies', async () => {
    tokenStore.set(TEST_TOKEN);
    server.use(
      http.get('/api/v1/recordings/:id/transcript', () =>
        HttpResponse.json({ detail: "The transcript isn't ready yet." }, { status: 409 }),
      ),
      http.get('/api/v1/routes', () =>
        HttpResponse.json({ detail: 'Traceback (most recent call last)…' }, { status: 500 }),
      ),
    );
    const conflict = await apiRequest('/recordings/x/transcript').catch((e) => e as ApiError);
    expect(conflict).toBeInstanceOf(ApiError);
    expect((conflict as ApiError).conflict).toBe(true);
    expect((conflict as ApiError).message).toBe("The transcript isn't ready yet.");
    expect(errorMessage(conflict, 'fallback')).toBe("The transcript isn't ready yet.");

    const boom = await apiRequest('/routes').catch((e) => e as ApiError);
    expect((boom as ApiError).detail).toBeNull();
    expect(errorMessage(boom, "Couldn't load rules.")).toBe("Couldn't load rules.");
    expect((boom as ApiError).message).not.toMatch(/Traceback|500/);
  });

  it('rejects responses that do not match the schema with a sentence', async () => {
    tokenStore.set(TEST_TOKEN);
    server.use(http.get('/api/v1/stats', () => HttpResponse.json({ recordings: 'five' })));
    const err = await apiJson('/stats', z.looseObject({ recordings: z.number() })).catch(
      (e) => e as ApiError,
    );
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).message).toMatch(/did not expect/);
  });

  it('maps network failures to NetworkError with user words', async () => {
    tokenStore.set(TEST_TOKEN);
    server.use(http.get('/api/v1/stats', () => HttpResponse.error()));
    const err = await apiRequest('/stats').catch((e) => e);
    expect(err).toBeInstanceOf(NetworkError);
    expect(errorMessage(err)).toBe("Can't reach your server");
  });

  it('parses download names from Content-Disposition', () => {
    expect(
      filenameFromDisposition(`attachment; filename="t.md"; filename*=UTF-8''Caf%C3%A9.md`, 'x.md'),
    ).toBe('Café.md');
    expect(filenameFromDisposition('attachment; filename="plain.md"', 'x.md')).toBe('plain.md');
    expect(filenameFromDisposition(null, 'x.md')).toBe('x.md');
  });
});
