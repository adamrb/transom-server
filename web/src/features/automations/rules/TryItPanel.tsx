import { useMemo, useState } from 'react';
import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import {
  ApiError,
  errorMessage,
  usePreviewAutomations,
  useRecordings,
  type Preview,
  type Recording,
} from '@/api';
import { fmtWhen } from '@/lib/format';
import { cn } from '@/lib/cn';
import { DecisionLine } from '../activity/DecisionLine';

const recordingTitle = (r: Recording) => r.title || r.filename;
const recordedAt = (r: Recording) => r.started_at || r.uploaded_at;

/** The server may name several rules (`matches`); older servers carry only the first. */
export function previewMatches(p: Preview): { name: string; reason: string | null }[] {
  const ms = p.matches
    .filter((m) => m.route_name)
    .map((m) => ({ name: m.route_name!, reason: m.reason ?? null }));
  if (ms.length) return ms;
  return p.route_name ? [{ name: p.route_name, reason: p.reason ?? null }] : [];
}

export interface TryItPanelProps {
  className?: string;
}

/**
 * "Try it on a recording": pick a recent finished recording and see which saved rules it would
 * match and why. A dry run: nothing is delivered or written to the log. Hides itself on a server
 * without previews.
 */
export function TryItPanel({ className }: TryItPanelProps) {
  const recordings = useRecordings({ limit: 40 });
  const preview = usePreviewAutomations();
  const [pickedId, setPickedId] = useState<string | null>(null);
  const [unsupported, setUnsupported] = useState(false);

  const candidates = useMemo(
    () =>
      (recordings.data?.recordings ?? [])
        .filter((r) => r.status === 'done' && !r.no_speech)
        .sort((a, b) => new Date(recordedAt(b)).getTime() - new Date(recordedAt(a)).getTime())
        .slice(0, 20),
    [recordings.data],
  );
  const picked = candidates.find((r) => r.id === pickedId) ?? candidates[0] ?? null;

  if (unsupported) return null;

  const run = () => {
    if (!picked) return;
    preview.mutate(
      { id: picked.id },
      {
        onError: (err) => {
          if (err instanceof ApiError && err.notFound) setUnsupported(true);
        },
      },
    );
  };

  const result = preview.data;
  const matches = result ? previewMatches(result) : [];

  return (
    <section className={cn('rounded-lg bg-surface-container p-4', className)} aria-labelledby="try-it-title">
      <h3 id="try-it-title" className="m-0 text-title-s text-on-surface">
        Try it on a recording
      </h3>
      <p className="m-0 mt-0.5 mb-3 text-body-s text-on-surface-variant">
        Checks which saved rules a recording would match, without doing anything. Save first to try changes
        made here.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {/* A native select: it lives in the dialog's top layer (a portalled menu would sit
            behind the modal and be inert) and gives the phone its own picker. */}
        <span className="relative min-w-0 flex-1">
          <select
            aria-label="Recording"
            value={picked?.id ?? ''}
            disabled={!candidates.length}
            onChange={(e) => {
              setPickedId(e.target.value);
              preview.reset();
            }}
            className={cn(
              'h-8 w-full appearance-none truncate rounded-[10px] border border-outline bg-transparent pr-8 pl-3 text-[13px] leading-5 font-medium text-on-surface',
              'hover:bg-state-hover focus-ring disabled:opacity-[.38]',
            )}
          >
            {candidates.length === 0 && (
              <option value="">
                {recordings.isPending ? 'Loading recordings…' : 'No finished recordings yet'}
              </option>
            )}
            {candidates.map((r) => (
              <option key={r.id} value={r.id}>
                {recordingTitle(r)} · {fmtWhen(recordedAt(r))}
              </option>
            ))}
          </select>
          <Icon
            name="keyboard_arrow_down"
            size={16}
            className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-on-surface-variant"
          />
        </span>
        <Button variant="tonal" size="sm" onClick={run} loading={preview.isPending} disabled={!picked}>
          Try
        </Button>
      </div>
      {preview.isError && !(preview.error instanceof ApiError && preview.error.notFound) && (
        <p role="alert" className="m-0 mt-3 text-body-m text-error">
          {errorMessage(preview.error, 'Couldn’t check that recording.')}
        </p>
      )}
      {result && (
        <div role="status" className="mt-3 flex flex-col gap-1.5" data-testid="try-it-result">
          {matches.length ? (
            <>
              <div className="text-body-s text-on-surface-variant">
                Would run {matches.length === 1 ? 'this rule' : 'these rules'}:
              </div>
              {matches.map((m, i) => (
                <DecisionLine
                  key={`${m.name}-${i}`}
                  name={m.name}
                  reason={m.reason}
                  reasonCollapsed={false}
                />
              ))}
            </>
          ) : (
            <DecisionLine
              icon="check_circle"
              name="Nothing would match"
              reason={result.reason}
              reasonCollapsed={false}
              tone="muted"
            />
          )}
        </div>
      )}
    </section>
  );
}
