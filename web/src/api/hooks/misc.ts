import { useQuery } from '@tanstack/react-query';
import { apiJson } from '../client';
import { POLL, qk } from '../keys';
import { HealthSchema, StatsSchema } from '../types';

/**
 * Recording counts and total duration. Polls every 15 s; its failure (not a 401) is the
 * "Can't reach your server" signal, so read `isError` for the connection banner.
 */
export function useStats() {
  return useQuery({
    queryKey: qk.stats,
    queryFn: () => apiJson('/stats', StatsSchema),
    refetchInterval: POLL.idle,
    refetchIntervalInBackground: true,
  });
}

/** Public liveness check (no auth). */
export function useHealth(enabled = true) {
  return useQuery({
    queryKey: qk.health,
    queryFn: () => apiJson('/health', HealthSchema, { anonymous: true }),
    enabled,
    staleTime: 60_000,
  });
}
