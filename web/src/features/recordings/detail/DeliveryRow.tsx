import { Button, Icon, StatusChip } from '@/components';
import type { Delivery } from '@/api';
import { fmtWhen } from '@/lib/format';
import { deliveryView } from '../lib/automations';
import { Disclosure } from './Disclosure';

export interface DeliveryRowProps {
  delivery: Delivery;
  onRetry: (deliveryId: string) => void;
  retrying?: boolean;
}

/** One hand-off to a rule: the rule's name, its outcome text, and a chip only while working or failed. */
export function DeliveryRow({ delivery, onRetry, retrying }: DeliveryRowProps) {
  const v = deliveryView(delivery);
  return (
    <div
      data-delivery={delivery.id}
      className="mt-2.5 flex flex-wrap items-center gap-x-2.5 gap-y-2 rounded-md bg-surface-container-low px-3.5 py-3 dark:bg-surface-container-high"
    >
      <span className="inline-flex items-center gap-2 text-body-m font-medium text-on-surface">
        <Icon
          name={
            delivery.action_type === 'markdown'
              ? 'description'
              : delivery.action_type === 'webhook'
                ? 'send'
                : 'wand_stars'
          }
          size={18}
          className="text-on-surface-variant"
        />
        {v.name}
      </span>
      {v.chip === 'failed' && <StatusChip tone="failed">Failed</StatusChip>}
      {v.chip === 'working' && <StatusChip tone="inflight">Working</StatusChip>}
      {v.note && <span className="text-body-s text-on-surface-variant">{v.note}</span>}
      {v.tries > 1 && <span className="text-body-s text-on-surface-variant">{v.tries} tries</span>}
      <span className="flex-1" />
      {v.retryable && (
        <Button
          variant="outlined"
          size="sm"
          icon="refresh"
          loading={retrying}
          onClick={() => onRetry(delivery.id)}
        >
          Retry
        </Button>
      )}
      {v.outcome && (
        <div className="basis-full text-body-m whitespace-pre-wrap [overflow-wrap:anywhere] text-on-surface-body">
          {v.outcome}
          {v.outcomeAt && <span className="text-on-surface-variant"> · {fmtWhen(v.outcomeAt)}</span>}
        </div>
      )}
      {v.errorDetail && (
        <div className="basis-full">
          <Disclosure className="mt-0">{v.errorDetail}</Disclosure>
        </div>
      )}
    </div>
  );
}
