import { Icon } from '@/components/Icon';
import type { RouterRun } from '@/api/types';
import { cn } from '@/lib/cn';
import { DecisionLine } from './DecisionLine';

export interface RunDecisionsProps {
  run: Pick<RouterRun, 'decision' | 'error'>;
  className?: string;
}

/**
 * What one run decided: a line per matched rule, "Nothing matched" when none did, and when the
 * run itself failed a plain sentence with the raw error behind "Details".
 */
export function RunDecisions({ run, className }: RunDecisionsProps) {
  const routes = run.decision?.routes ?? [];
  const decisionReason = (run.decision as { reason?: string | null } | null | undefined)?.reason ?? null;
  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      {run.error && (
        <div>
          <DecisionLine icon="error" name="Couldn’t run automations." tone="error" />
          <details className="group ml-[26px]">
            <summary className="inline-flex h-7 cursor-pointer list-none items-center gap-1 rounded-sm px-1.5 text-label-m text-on-surface-variant hover:bg-state-hover focus-ring [&::-webkit-details-marker]:hidden">
              <Icon
                name="keyboard_arrow_down"
                size={16}
                className="transition-transform group-open:rotate-180"
              />
              Details
            </summary>
            <pre className="m-0 mt-1 overflow-auto rounded-sm bg-surface-container-highest p-2.5 font-mono text-[12.5px] leading-5 whitespace-pre-wrap text-on-surface-variant">
              {run.error}
            </pre>
          </details>
        </div>
      )}
      {routes.map((r, i) => (
        <DecisionLine key={`${r.name}-${i}`} name={r.name} reason={r.reason} />
      ))}
      {!routes.length && !run.error && (
        <DecisionLine icon="check_circle" name="Nothing matched" reason={decisionReason} tone="muted" />
      )}
    </div>
  );
}
