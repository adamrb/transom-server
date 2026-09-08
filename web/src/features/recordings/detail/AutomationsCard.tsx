import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Card, Icon, SkeletonText, useSnackbar } from '@/components';
import {
  ApiError,
  errorMessage,
  qk,
  useRecordingRouting,
  useRetryDelivery,
  type Recording,
  type RouterRun,
} from '@/api';
import { fmtWhen } from '@/lib/format';
import { latestRun } from '../lib/automations';
import { DeliveryRow } from './DeliveryRow';
import { Disclosure } from './Disclosure';
import { RunAutomationsRow } from './RunAutomationsRow';

/** The last run's decision: which rules matched and why, or that nothing did. */
function Decision({ run }: { run: RouterRun }) {
  const routes = run.decision?.routes ?? [];
  return (
    <div className="flex flex-col gap-1.5">
      {run.error && (
        <div>
          <div className="text-body-m text-error">Couldn't run automations.</div>
          <Disclosure>{run.error}</Disclosure>
        </div>
      )}
      {routes.map((r, i) => (
        <div key={i} className="flex items-start gap-2 text-body-m text-on-surface-body">
          <Icon name="wand_stars" size={18} className="mt-px shrink-0 text-on-surface-variant" />
          <span>
            <b className="font-medium text-on-surface">{r.name}</b>
            {r.reason && <span className="text-on-surface-variant"> — {r.reason}</span>}
          </span>
        </div>
      ))}
      {!routes.length && !run.error && (
        <div className="flex items-start gap-2 text-body-m text-on-surface-body">
          <Icon name="check_circle" size={18} className="mt-px shrink-0 text-on-surface-variant" />
          <span>
            <b className="font-medium text-on-surface">Nothing matched</b>
            {run.decision?.reason && (
              <span className="text-on-surface-variant"> — {run.decision.reason}</span>
            )}
          </span>
        </div>
      )}
    </div>
  );
}

/**
 * The Automations card of a recording: last run, its decision, the deliveries with their outcomes
 * (Retry when failed or unreported), and the run / preview row. Hidden when the server has no
 * automations (404); polls while a delivery is still working.
 */
/** While a finished recording has no run yet, look again this often, this many times (5 minutes). */
const CATCH_UP_EVERY_MS = 15_000;
const CATCH_UP_TIMES = 20;

export function AutomationsCard({ rec }: { rec: Recording }) {
  const snackbar = useSnackbar();
  const qc = useQueryClient();
  const routing = useRecordingRouting(rec.id);
  const retry = useRetryDelivery();
  const canRun = rec.status === 'done' && !rec.no_speech;
  const invalidate = () => void qc.invalidateQueries({ queryKey: qk.recordings.routing(rec.id) });

  // The automatic run starts a little after transcription finishes (also after transcribing
  // again), while `useRecordingRouting` stops polling once nothing is working. So: refetch the
  // moment the recording turns done and start a bounded catch-up…
  const prevStatus = useRef(rec.status);
  const [catchUp, setCatchUp] = useState(0);
  useEffect(() => {
    const became = prevStatus.current !== 'done' && rec.status === 'done';
    prevStatus.current = rec.status;
    if (became) {
      invalidate();
      setCatchUp((n) => n + 1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rec.status, rec.id]);
  // …and keep looking for a bounded while after each such transition, or while a finished
  // recording still shows no run at all (opened after it finished).
  const noRuns = !!routing.data && routing.data.runs.length === 0;
  useEffect(() => {
    if (!canRun || !(noRuns || catchUp > 0)) return;
    let left = CATCH_UP_TIMES;
    const t = setInterval(() => {
      if (--left < 0) return clearInterval(t);
      invalidate();
    }, CATCH_UP_EVERY_MS);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canRun, noRuns, catchUp, rec.id]);

  if (routing.error instanceof ApiError && routing.error.notFound) return null;

  let body: React.ReactNode;
  if (routing.error) {
    body = (
      <p className="m-0 text-body-m text-error">
        {errorMessage(routing.error, "Couldn't load automations.")}
      </p>
    );
  } else if (!routing.data) {
    body = <SkeletonText lines={2} />;
  } else {
    const { last, deliveries } = latestRun(routing.data);
    body = last ? (
      <>
        <div className="mb-1.5 text-body-s text-on-surface-variant">Last run {fmtWhen(last.created_at)}</div>
        {last.instructions && (
          <div className="mb-1.5 text-body-s text-on-surface-variant">Your note: “{last.instructions}”</div>
        )}
        <Decision run={last} />
        {deliveries.map((d) => (
          <DeliveryRow
            key={d.id}
            delivery={d}
            retrying={retry.isPending && retry.variables === d.id}
            onRetry={(id) =>
              retry.mutate(id, {
                onSuccess: () => snackbar.show('Trying again'),
                onError: (e) => snackbar.error(errorMessage(e, "Couldn't retry.")),
              })
            }
          />
        ))}
      </>
    ) : (
      <p className="m-0 text-body-m text-on-surface-variant">
        {canRun
          ? 'Not run yet.'
          : rec.no_speech
            ? 'Nothing to run on a silent recording.'
            : 'Automations run once the transcript is ready.'}
      </p>
    );
  }

  return (
    <Card id="sec-automations" title="Automations">
      {body}
      {canRun && routing.data && (
        <RunAutomationsRow recordingId={rec.id} hasRun={!!latestRun(routing.data).last} />
      )}
    </Card>
  );
}
