import { Button } from '@/components/Button';
import { StatusChip } from '@/components/Chip';
import { Icon } from '@/components/Icon';
import { useSnackbar } from '@/components/Snackbar';
import { errorMessage, isDeliveryWorking, useRetryDelivery, type Delivery } from '@/api';
import { fmtWhen, plural } from '@/lib/format';
import { cn } from '@/lib/cn';
import { actionIcon } from '../rules/actionWords';

export interface OutcomeLineProps {
  delivery: Delivery;
  className?: string;
}

/** The two layers of a delivery, read the way the old dashboard did. */
export function deliveryState(d: Delivery) {
  const rs = d.result_status;
  const failed = d.status === 'failed' || rs === 'failed';
  const unknown = rs === 'unknown';
  const working = !failed && isDeliveryWorking(d);
  const legacyOk = d.status === 'ok' && !rs;
  const outcome = d.result_summary?.trim() || '';
  let note: string | null = null;
  if (!outcome && !failed && !working) {
    if (unknown) note = 'No result came back';
    else if (legacyOk && d.action_type === 'webhook') note = 'Sent';
  }
  return { failed, unknown, working, outcome, note, retryable: failed || unknown };
}

/**
 * What a rule's hand-off did: the rule (with its action glyph), a chip only while Working or
 * when Failed, "3 tries" when it took more than one, Retry when it can be retried, and the
 * agent's own sentence about the outcome standing alone underneath.
 */
export function OutcomeLine({ delivery: d, className }: OutcomeLineProps) {
  const retry = useRetryDelivery();
  const snackbar = useSnackbar();
  const s = deliveryState(d);
  const onRetry = () =>
    retry.mutate(d.id, {
      onSuccess: () => snackbar.show('Trying again'),
      onError: (err) => snackbar.error(errorMessage(err, 'Couldn’t retry.')),
    });
  return (
    <div
      data-delivery={d.id}
      className={cn(
        'mt-2.5 flex flex-wrap items-center gap-x-2.5 gap-y-2 rounded-md bg-surface-container-low px-3.5 py-3 dark:bg-surface-container-high',
        className,
      )}
    >
      <span className="inline-flex min-w-0 items-center gap-2 font-medium text-on-surface">
        <Icon name={actionIcon(d.action_type)} size={18} className="shrink-0 text-on-surface-variant" />
        <span className="truncate">{d.route_name ?? 'Rule'}</span>
      </span>
      {s.failed && <StatusChip tone="failed">Failed</StatusChip>}
      {s.working && <StatusChip tone="inflight">Working</StatusChip>}
      {s.note && <span className="text-body-s text-on-surface-variant">{s.note}</span>}
      {(d.attempts ?? 0) > 1 && (
        <span className="text-body-s text-on-surface-variant tnum">
          {plural(d.attempts!, 'try', 'tries')}
        </span>
      )}
      <span className="flex-1" />
      {s.retryable && (
        <Button variant="outlined" size="sm" icon="refresh" onClick={onRetry} loading={retry.isPending}>
          Retry
        </Button>
      )}
      {s.outcome && (
        <p className="m-0 basis-full text-body-m text-on-surface-body [overflow-wrap:anywhere]">
          {s.outcome}
          {d.result_at && <span className="text-on-surface-variant"> · {fmtWhen(d.result_at)}</span>}
        </p>
      )}
      {s.failed && !s.outcome && (
        <div className="basis-full text-body-m">
          <p className="m-0 text-error">Couldn’t hand this off.</p>
          {d.last_error && (
            <details className="group mt-1">
              <summary className="inline-flex h-7 cursor-pointer list-none items-center gap-1 rounded-sm px-1.5 text-label-m text-on-surface-variant hover:bg-state-hover focus-ring [&::-webkit-details-marker]:hidden">
                <Icon
                  name="keyboard_arrow_down"
                  size={16}
                  className="transition-transform group-open:rotate-180"
                />
                Details
              </summary>
              <pre className="m-0 mt-1 overflow-auto rounded-sm bg-surface-container-highest p-2.5 font-mono text-[12.5px] leading-5 whitespace-pre-wrap text-on-surface-variant">
                {d.last_error}
              </pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
