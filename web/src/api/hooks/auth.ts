import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, apiJson, apiRequest } from '../client';
import { qk } from '../keys';
import { tokenStore } from '../token';
import {
  LoginPollSchema,
  LoginRequestSchema,
  SessionsSchema,
  type LoginPoll,
  type LoginRequest,
} from '../types';

/**
 * Validate a candidate token against the server. True only on 204. Never broadcasts
 * AUTH_REQUIRED (the gate calls this while it is already showing).
 */
export async function checkToken(candidate: string): Promise<boolean> {
  try {
    const r = await apiFetch('/auth/check', { token: candidate, silent401: true });
    return r.status === 204;
  } catch {
    return false;
  }
}

/** Public: ask for a QR login request. 429 = too many pending from this client (retry in 30 s). */
export async function createLoginRequest(label: string | null): Promise<LoginRequest> {
  return apiJson('/login-requests', LoginRequestSchema, { method: 'POST', anonymous: true, json: { label } });
}

/** Public: poll a login request. `approved` carries the token exactly once. */
export async function pollLoginRequest(id: string): Promise<LoginPoll> {
  return apiJson(`/login-requests/${encodeURIComponent(id)}`, LoginPollSchema, { anonymous: true });
}

/** Approve a scanned QR from a signed-in client (the phone does this; here for completeness). */
export async function approveLoginRequest(id: string, label?: string): Promise<void> {
  await apiRequest(`/login-requests/${encodeURIComponent(id)}/approve`, {
    method: 'POST',
    json: { label: label ?? null },
  });
}

/** "Signed-in computers": sessions minted by QR approval. Hand-entered tokens are not listed. */
export function useSessions() {
  return useQuery({ queryKey: qk.sessions, queryFn: () => apiJson('/sessions', SessionsSchema) });
}

/** Sign one computer out (confirm first). */
export function useRevokeSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await apiRequest(`/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' });
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.sessions }),
  });
}

/**
 * Sign out this browser: revoke the session server-side (a no-op for a configured token; errors
 * are ignored), then forget the token. The auth provider reacts to the cleared token.
 */
export async function signOut(): Promise<void> {
  try {
    await apiRequest('/auth/logout', { method: 'POST', silent401: true });
  } catch {
    /* the token may already be dead; forgetting it is what matters */
  }
  tokenStore.clear();
}

/** Browser label for a login request: "Chrome on Linux". */
export function browserLabel(ua: string = navigator.userAgent): string {
  const os = /Windows/.test(ua)
    ? 'Windows'
    : /Mac OS X/.test(ua)
      ? 'Mac'
      : /Android/.test(ua)
        ? 'Android'
        : /iPhone|iPad/.test(ua)
          ? 'iOS'
          : /Linux/.test(ua)
            ? 'Linux'
            : '';
  const br = /Edg\//.test(ua)
    ? 'Edge'
    : /Firefox\//.test(ua)
      ? 'Firefox'
      : /Chrome\//.test(ua)
        ? 'Chrome'
        : /Safari\//.test(ua)
          ? 'Safari'
          : 'Browser';
  return [br, os].filter(Boolean).join(' on ');
}
