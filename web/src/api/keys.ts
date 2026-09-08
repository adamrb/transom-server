import type { RecordingListParams } from './types';

/**
 * Query keys, one factory per resource. Invalidate a whole resource with its `all` key
 * (`queryClient.invalidateQueries({ queryKey: qk.recordings.all })`).
 */
export const qk = {
  health: ['health'] as const,
  stats: ['stats'] as const,
  sessions: ['sessions'] as const,
  recordings: {
    all: ['recordings'] as const,
    list: (params: RecordingListParams = {}) => ['recordings', 'list', params] as const,
    detail: (id: string) => ['recordings', 'detail', id] as const,
    transcript: (id: string) => ['recordings', 'transcript', id] as const,
    routing: (id: string) => ['recordings', 'routing', id] as const,
  },
  routes: ['routes'] as const,
  router: {
    status: ['router', 'status'] as const,
    log: (limit: number) => ['router', 'log', limit] as const,
    all: ['router'] as const,
  },
  vocabulary: ['vocabulary'] as const,
  apk: ['apk', 'info'] as const,
} as const;

/** Polling cadence (ms): the list every 15 s, 5 s while anything is pending or transcribing. */
export const POLL = {
  idle: 15_000,
  inFlight: 5_000,
  /** a recording left open while the agent works */
  routingWorking: 15_000,
} as const;
