import { QueryClient } from '@tanstack/react-query';
import { ApiError } from './client';

/**
 * One QueryClient for the app. 4xx answers are final (no retry); network and 5xx retry twice.
 * Queries do not refetch on window focus by themselves: the polling hooks own their cadence.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: (count, err) => !(err instanceof ApiError && err.status > 0 && err.status < 500) && count < 2,
        retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
        refetchOnWindowFocus: false,
        staleTime: 5_000,
      },
      mutations: { retry: false },
    },
  });
}
