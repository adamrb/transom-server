import type { KeyboardEvent, MouseEvent } from 'react';
import { Card } from '@/components/Card';
import { fmtWhen, plural } from '@/lib/format';
import { cn } from '@/lib/cn';
import { GroupedRuns } from './GroupedRuns';
import { OutcomeLine } from './OutcomeLine';
import { RunDecisions } from './RunDecisions';
import { runCanOpen, runRecordedAt, runTitle, type RunGroup } from './groupRuns';

export interface ActivityCardProps {
  group: RunGroup;
  /** Open the recording (`#/rec/<id>`). Not called for deleted recordings. */
  onOpen: (recordingId: string) => void;
}

/**
 * One recording's automation activity: title (a link to the recording unless it was deleted),
 * when it ran, when it was recorded, your note if you added one, what matched and why, what each
 * rule's hand-off did, and older runs of the same recording behind "Earlier runs".
 */
export function ActivityCard({ group, onOpen }: ActivityCardProps) {
  const [run, ...earlier] = group.runs;
  const title = runTitle(run);
  const recordedAt = runRecordedAt(run);
  const canOpen = runCanOpen(run);
  const open = () => {
    if (canOpen && run.recording_id) onOpen(run.recording_id);
  };
  // The whole card opens the recording, except clicks on the controls inside it.
  const onCardClick = (e: MouseEvent<HTMLDivElement>) => {
    if (!canOpen) return;
    if ((e.target as Element).closest('button, summary, details, a, input')) return;
    open();
  };
  const onTitleKey = (e: KeyboardEvent<HTMLElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      open();
    }
  };

  return (
    <Card
      role="listitem"
      aria-label={title}
      data-run-id={run.id}
      data-recording-id={run.recording_id ?? undefined}
      className={cn(
        'mb-2.5 px-5 py-3.5 max-md:px-4',
        canOpen && 'cursor-pointer hover:bg-card-raised transition-colors dur-medium',
      )}
      padding="none"
      onClick={onCardClick}
    >
      <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
        {canOpen ? (
          <button
            type="button"
            onClick={open}
            onKeyDown={onTitleKey}
            className="min-w-[160px] flex-1 rounded-xs text-left text-title-m text-on-surface hover:underline hover:underline-offset-[3px] focus-ring [overflow-wrap:anywhere]"
          >
            {title}
          </button>
        ) : (
          <span
            className={cn(
              'min-w-[160px] flex-1 text-title-m',
              run.recording_deleted ? 'text-on-surface-variant italic' : 'text-on-surface',
            )}
          >
            {title}
          </span>
        )}
        {earlier.length > 0 && (
          <span className="text-body-s text-on-surface-variant tnum">{plural(group.runs.length, 'run')}</span>
        )}
        <time
          dateTime={run.created_at ?? undefined}
          className="whitespace-nowrap text-body-s text-on-surface-variant tnum"
        >
          {fmtWhen(run.created_at)}
        </time>
      </div>
      {(recordedAt || run.instructions) && (
        <div className="mt-0.5 text-[13px] text-on-surface-variant [overflow-wrap:anywhere]">
          {recordedAt && <>Recorded {fmtWhen(recordedAt)}</>}
          {recordedAt && run.instructions && ' · '}
          {run.instructions && <>Your note: “{run.instructions}”</>}
        </div>
      )}
      <RunDecisions run={run} className="mt-2" />
      {run.deliveries.map((d) => (
        <OutcomeLine key={d.id} delivery={d} />
      ))}
      <GroupedRuns runs={earlier} />
    </Card>
  );
}
