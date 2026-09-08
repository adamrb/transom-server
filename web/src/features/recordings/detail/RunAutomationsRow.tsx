import { useState } from 'react';
import { Button, TextField, useSnackbar } from '@/components';
import {
  ApiError,
  errorMessage,
  routeInstructionsStore,
  routeKeyStore,
  usePreviewAutomations,
  useRunAutomations,
} from '@/api';
import { cn } from '@/lib/cn';
import { previewText } from '../lib/automations';

export interface RunAutomationsRowProps {
  recordingId: string;
  /** A run exists already: the button says "Run again". */
  hasRun: boolean;
}

/**
 * The instructions saved for a run whose idempotency key is still pending, as the box should
 * show them on return (or after a reload). Instructions left behind by a run that completed while
 * the recording was closed (the hook clears the key, nothing clears them) are dropped here, so
 * they can never ride into a second, unintended run.
 */
function pendingInstructions(id: string): string {
  const saved = routeInstructionsStore.get(id);
  if (saved == null) return '';
  if (routeKeyStore.get(id)) return saved;
  routeInstructionsStore.clear(id);
  return '';
}

/**
 * Instructions field + "Run automations" / "Run again" + "Preview". The instructions ride along
 * with the idempotency key: they are saved in sessionStorage when a run starts and a retry after a
 * lost reply replays exactly them (`useRunAutomations` sends the key and clears both once the
 * run is settled; this row supplies the instructions saved with it, not whatever the box holds
 * now), as the old dashboard did.
 */
export function RunAutomationsRow({ recordingId: id, hasRun }: RunAutomationsRowProps) {
  const snackbar = useSnackbar();
  const [draft, setDraft] = useState(() => pendingInstructions(id));
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const [previewSupported, setPreviewSupported] = useState(true);
  const run = useRunAutomations();
  const preview = usePreviewAutomations();

  const onRun = () => {
    let instructions: string;
    if (routeKeyStore.get(id)) {
      instructions = routeInstructionsStore.get(id) ?? '';
      setDraft(instructions);
    } else {
      instructions = draft.trim();
      routeInstructionsStore.set(id, instructions);
    }
    setMessage(null);
    run.mutate(
      { id, instructions },
      {
        onSuccess: () => {
          setDraft('');
          snackbar.show('Automations ran');
        },
        onError: (err) => {
          if (err instanceof ApiError && err.status >= 400 && err.status < 500) {
            setMessage({
              text: err.conflict
                ? err.userMessage('Automations need a finished transcript.')
                : err.userMessage("Couldn't run automations."),
              error: true,
            });
          } else if (!(err instanceof ApiError && err.unauthorized)) {
            setMessage({
              text: "Couldn't run automations. Try again; a lost reply will not run them twice.",
              error: true,
            });
          }
        },
      },
    );
  };

  const onPreview = () => {
    setMessage(null);
    preview.mutate(
      { id, instructions: draft.trim() },
      {
        onSuccess: (d) => setMessage({ text: previewText(d), error: false }),
        onError: (err) => {
          if (err instanceof ApiError && err.notFound) {
            setPreviewSupported(false);
            snackbar.error("Your server doesn't support previews yet.");
            return;
          }
          setMessage({ text: errorMessage(err, "Couldn't check the automations."), error: true });
        },
      },
    );
  };

  return (
    <div className="mt-3.5">
      <div className="flex flex-wrap items-center gap-2.5">
        <TextField
          icon="edit"
          aria-label="Instructions"
          placeholder="Anything to add? e.g. file this as a work meeting"
          maxLength={2000}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !run.isPending) onRun();
          }}
          className="min-w-[220px] flex-1"
        />
        <Button variant="filled" loading={run.isPending} onClick={onRun}>
          {run.isPending ? 'Running…' : hasRun ? 'Run again' : 'Run automations'}
        </Button>
        {previewSupported && (
          <Button
            variant="text"
            loading={preview.isPending}
            onClick={onPreview}
            title="See what would happen, without doing it"
          >
            {preview.isPending ? 'Checking…' : 'Preview'}
          </Button>
        )}
      </div>
      {message && (
        <p
          role="status"
          data-testid="automations-message"
          className={cn('mt-2 mb-0 text-body-m', message.error ? 'text-error' : 'text-on-surface-variant')}
        >
          {message.text}
        </p>
      )}
    </div>
  );
}
