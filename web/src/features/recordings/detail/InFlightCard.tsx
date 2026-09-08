import { Card, LinearProgress } from '@/components';
import type { Recording } from '@/api';
import { inFlightHeading, inFlightReason, progressPct } from '../lib/status';

/**
 * While a recording is pending or transcribing: "Waiting in the queue" / "Transcribing 42%" /
 * "Identifying speakers" / "Summarizing", one sentence, and a progress bar (determinate while the
 * percentage is known). The detail polls every 5 s so this refreshes on its own.
 */
export function InFlightCard({ rec }: { rec: Recording }) {
  const pct = progressPct(rec);
  return (
    <Card title={inFlightHeading(rec)} role="status" aria-live="polite" data-testid="inflight-card">
      <p className="m-0 mb-3 text-body-m text-on-surface-variant">{inFlightReason(rec)}</p>
      <LinearProgress value={pct != null ? pct / 100 : undefined} label={inFlightHeading(rec)} />
    </Card>
  );
}
