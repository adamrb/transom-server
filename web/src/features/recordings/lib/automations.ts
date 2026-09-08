/**
 * Automations card logic, ported from the old dashboard's `loadRoutingSection`, `renderDelivery`
 * and `previewText`.
 */
import type { Delivery, Preview, RecordingRouting, RouterRun } from '@/api';

/** The most recent run and the deliveries to show with it (the run's own, else the recording's). */
export function latestRun(data: RecordingRouting | undefined): {
  last: RouterRun | null;
  deliveries: Delivery[];
} {
  const runs = data?.runs ?? [];
  const last = runs.length
    ? runs.reduce((a, b) => (new Date(b.created_at ?? 0) > new Date(a.created_at ?? 0) ? b : a))
    : null;
  const deliveries = (last?.deliveries.length ? last.deliveries : data?.deliveries) ?? [];
  return { last, deliveries };
}

export interface DeliveryView {
  name: string;
  /** Working (amber) or Failed (red); nothing when the outcome text speaks for itself. */
  chip: 'working' | 'failed' | null;
  /** Short note when there is no outcome: "No result came back", "Sent". */
  note: string;
  tries: number;
  retryable: boolean;
  outcome: string;
  outcomeAt: string | null;
  /** Raw error text, shown only behind a disclosure and only without an outcome. */
  errorDetail: string;
}

/**
 * Two layers: the hand-off (`status`) and what the agent reported back (`result_*`). A result
 * summary stands alone; chips appear only while working or when something failed.
 */
export function deliveryView(d: Delivery): DeliveryView {
  const rs = d.result_status;
  const isFailed = d.status === 'failed' || rs === 'failed';
  const unknown = rs === 'unknown';
  const working = !isFailed && (rs === 'queued' || d.status === 'pending');
  const legacyOk = d.status === 'ok' && !rs;
  const outcome = d.result_summary || '';
  let note = '';
  if (!outcome && !isFailed && !working)
    note = unknown ? 'No result came back' : legacyOk && d.action_type === 'webhook' ? 'Sent' : '';
  return {
    name: d.route_name ?? 'Rule',
    chip: isFailed ? 'failed' : working ? 'working' : null,
    note,
    tries: d.attempts ?? 0,
    retryable: isFailed || unknown,
    outcome,
    outcomeAt: outcome ? (d.result_at ?? null) : null,
    errorDetail: isFailed && !outcome ? d.last_error || '' : '',
  };
}

/** "Would run “Ask Claude” — reason", "Would run “A” and “B” — reason", "Nothing would match — reason". */
export function previewText(d: Preview): string {
  const ms = d.matches.length
    ? d.matches.filter((m) => m.route_name)
    : d.route_name
      ? [{ route_name: d.route_name, reason: d.reason }]
      : [];
  if (!ms.length) return `Nothing would match${d.reason ? ` — ${d.reason}` : ''}`;
  if (ms.length === 1) return `Would run “${ms[0].route_name}”${ms[0].reason ? ` — ${ms[0].reason}` : ''}`;
  return (
    'Would run ' +
    ms.map((m) => `“${m.route_name}”`).join(' and ') +
    (ms[0].reason ? ` — ${ms[0].reason}` : '')
  );
}
