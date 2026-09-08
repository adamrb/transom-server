import { useCallback, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ConfirmDialog, useSnackbar } from '@/components';
import {
  errorMessage,
  fetchAudioBlob,
  fetchExportMarkdown,
  fetchTranscript,
  qk,
  useDeleteRecording,
  useRenameRecording,
  useRetranscribe,
  type Recording,
  type Transcript,
} from '@/api';
import { copyText, downloadBlob, shareMarkdown } from '@/features/shell';
import { titleOf } from '../lib/summary';
import { transcriptPlainText } from '../lib/transcript';
import { usePlayerStore } from '../player/usePlayer';
import { RenameDialog } from './RenameDialog';
import type { RecordingAction } from './MoreMenu';

export interface UseRecordingActionsOptions {
  /** After a recording was deleted (leave its detail). */
  onDeleted?: (id: string) => void;
}

/**
 * The recording actions behind the chips, the More menu and the row menu: copy, export, download,
 * rename, transcribe again (confirmed), delete (confirmed, destructive). Returns `act` and the
 * dialogs to render once in the page.
 */
export function useRecordingActions({ onDeleted }: UseRecordingActionsOptions = {}) {
  const snackbar = useSnackbar();
  const qc = useQueryClient();
  const player = usePlayerStore();
  const rename = useRenameRecording();
  const retranscribe = useRetranscribe();
  const del = useDeleteRecording();
  const [dialog, setDialog] = useState<{ kind: 'rename' | 'retranscribe' | 'delete'; rec: Recording } | null>(
    null,
  );
  const close = () => setDialog(null);

  /** The transcript to copy: the one on screen, else fetched (a row menu on the list). Throws on failure. */
  const transcriptFor = useCallback(
    async (rec: Recording, t?: Transcript | null): Promise<Transcript | null> => {
      if (t) return t;
      if (rec.status !== 'done') return null;
      return qc.fetchQuery({
        queryKey: qk.recordings.transcript(rec.id),
        queryFn: () => fetchTranscript(rec.id),
      });
    },
    [qc],
  );

  const copy = useCallback(
    async (rec: Recording, t?: Transcript | null) => {
      let transcript: Transcript | null;
      try {
        transcript = await transcriptFor(rec, t);
      } catch (e) {
        return snackbar.error(errorMessage(e, "Couldn't load the transcript."));
      }
      const text = transcriptPlainText(transcript);
      if (!text) return snackbar.show('No transcript to copy');
      const r = await copyText(text);
      if (r === 'copied') snackbar.show('Transcript copied');
      else if (r === 'failed') snackbar.error('Copy failed');
      // 'bridge': the app shows its own toast.
    },
    [snackbar, transcriptFor],
  );

  const exportMd = useCallback(
    async (rec: Recording) => {
      try {
        const { name, markdown } = await fetchExportMarkdown(rec.id);
        if (shareMarkdown(name, markdown) === 'downloaded') snackbar.show('Markdown exported');
      } catch (e) {
        snackbar.error(errorMessage(e, "Couldn't export the transcript."));
      }
    },
    [snackbar],
  );

  const download = useCallback(
    async (rec: Recording) => {
      snackbar.show('Preparing download…');
      try {
        downloadBlob(await fetchAudioBlob(rec.id), rec.filename || 'recording.mp3');
      } catch (e) {
        snackbar.error(errorMessage(e, "Couldn't download the audio."));
      }
    },
    [snackbar],
  );

  const act = useCallback(
    (action: RecordingAction, rec: Recording, transcript?: Transcript | null) => {
      switch (action) {
        case 'copy':
          return void copy(rec, transcript);
        case 'export':
          return void exportMd(rec);
        case 'download':
          return void download(rec);
        case 'rename':
        case 'retranscribe':
        case 'delete':
          return setDialog({ kind: action, rec });
      }
    },
    [copy, exportMd, download],
  );

  const dialogs: ReactNode = (
    <>
      <RenameDialog
        open={dialog?.kind === 'rename'}
        title="Rename recording"
        label="Title"
        value={dialog ? titleOf(dialog.rec) : ''}
        busy={rename.isPending}
        onCancel={close}
        onSubmit={(title) =>
          dialog &&
          rename.mutate(
            { id: dialog.rec.id, title },
            {
              onSuccess: () => {
                close();
                snackbar.show('Renamed');
              },
              onError: (e) => snackbar.error(errorMessage(e, "Couldn't rename the recording.")),
            },
          )
        }
      />
      <ConfirmDialog
        open={dialog?.kind === 'retranscribe'}
        title="Transcribe this recording again?"
        ok="Transcribe again"
        busy={retranscribe.isPending}
        onCancel={close}
        onConfirm={() =>
          dialog &&
          retranscribe.mutate(dialog.rec.id, {
            onSuccess: (_d, id) => {
              close();
              player.resetIf(id);
              snackbar.show('Transcribing again');
            },
            onError: (e) => snackbar.error(errorMessage(e, "Couldn't start transcribing again.")),
          })
        }
      >
        <p>
          The current transcript and summary will be thrown away and made again from the audio. Speaker names
          and highlights are worked out afresh.
        </p>
        <p className="text-body-s text-on-surface-variant">Long recordings take a while.</p>
      </ConfirmDialog>
      <ConfirmDialog
        open={dialog?.kind === 'delete'}
        title="Delete this recording?"
        ok="Delete"
        danger
        busy={del.isPending}
        onCancel={close}
        onConfirm={() =>
          dialog &&
          del.mutate(dialog.rec.id, {
            onSuccess: (_d, id) => {
              close();
              player.resetIf(id);
              snackbar.show('Recording deleted');
              onDeleted?.(id);
            },
            onError: (e) => snackbar.error(errorMessage(e, "Couldn't delete the recording.")),
          })
        }
      >
        <p>
          <b className="font-medium text-on-surface">{dialog ? titleOf(dialog.rec) : 'This recording'}</b> and
          its transcript will be removed from your server. This cannot be undone.
        </p>
      </ConfirmDialog>
    </>
  );

  return { act, dialogs };
}
