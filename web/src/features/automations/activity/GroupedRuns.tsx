import { Icon } from '@/components/Icon';
import type { LogRun } from '@/api/types';
import { fmtWhen } from '@/lib/format';
import { RunDecisions } from './RunDecisions';
import { OutcomeLine } from './OutcomeLine';

export interface GroupedRunsProps {
  /** The older runs of the same recording, newest first. */
  runs: LogRun[];
}

/** "Earlier runs (n)" disclosure under a card whose recording was run more than once. */
export function GroupedRuns({ runs }: GroupedRunsProps) {
  if (!runs.length) return null;
  return (
    <details className="group mt-2">
      <summary
        className="inline-flex h-8 cursor-pointer list-none items-center gap-1 rounded-sm pr-2.5 pl-1.5 text-[13px] font-medium text-on-surface-variant hover:bg-state-hover focus-ring [&::-webkit-details-marker]:hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <Icon
          name="keyboard_arrow_down"
          size={18}
          className="transition-transform dur-short group-open:rotate-180"
        />
        Earlier runs ({runs.length})
      </summary>
      <ul className="m-0 list-none p-0">
        {runs.map((run) => (
          <li key={run.id} className="mt-3 border-t border-outline-variant pt-3">
            <div className="text-[13px] text-on-surface-variant">
              {fmtWhen(run.created_at)}
              {run.instructions && <> · Your note: “{run.instructions}”</>}
            </div>
            <RunDecisions run={run} className="mt-1.5" />
            {run.deliveries.map((d) => (
              <OutcomeLine key={d.id} delivery={d} />
            ))}
          </li>
        ))}
      </ul>
    </details>
  );
}
