import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/Button';
import { Dialog } from '@/components/Dialog';
import { TextField } from '@/components/TextField';
import { useSnackbar } from '@/components/Snackbar';
import { ApiError, errorMessage } from '@/api/client';
import { parseVocabularyLines, useImportVocabulary, VOCAB_LIMITS } from '@/api/hooks/vocabulary';
import { plural } from '@/lib/format';
import { FilePicker } from '@/components/FilePicker';
import { readFileText } from '@/lib/bridge';

export interface ImportDialogProps {
  open: boolean;
  onClose: () => void;
}

const MAX_FILE_BYTES = 2_000_000;

/**
 * Import…: paste terms (same `Term = mis-hearing, mis-hearing` lines) or pick a text file, then
 * POST them; the server merges (existing terms and mis-hearings are kept). Reports how many terms
 * were new in a snackbar.
 */
export function ImportDialog({ open, onClose }: ImportDialogProps) {
  const [text, setText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);
  /** Only the latest picked file may fill the text area (a slow read must not win late). */
  const readSeq = useRef(0);
  const snackbar = useSnackbar();
  const importMut = useImportVocabulary();

  useEffect(() => {
    if (open) {
      setText('');
      setFile(null);
      setError(null);
      importMut.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when the dialog opens
  }, [open]);

  const pick = (f: File | null) => {
    setFile(f);
    setError(null);
    if (!f) return;
    // The text area always mirrors the chosen file, so a rejected file never leaves stale text
    // behind to be imported by mistake.
    setText('');
    if (f.size > MAX_FILE_BYTES) {
      setError('That file is too large.');
      return;
    }
    const seq = ++readSeq.current;
    readFileText(f)
      .then((t) => {
        if (seq === readSeq.current) setText(t);
      })
      .catch(() => {
        if (seq === readSeq.current) setError("Couldn't read that file.");
      });
  };

  const submit = () => {
    const entries = parseVocabularyLines(text).flatMap((l) =>
      l.kind === 'entry' ? [{ term: l.term, aliases: l.aliases }] : [],
    );
    if (!entries.length) return setError('Nothing to import.');
    if (entries.length > VOCAB_LIMITS.entries)
      return setError(`Up to ${VOCAB_LIMITS.entries} terms at a time.`);
    setError(null);
    importMut.mutate(entries, {
      onSuccess: (d) => {
        onClose();
        const n = d.added ?? 0;
        snackbar.show(n ? `${plural(n, 'term')} added` : 'Nothing new to add');
      },
      onError: (e) =>
        setError(
          e instanceof ApiError && e.notFound
            ? "Your server doesn't support importing yet."
            : errorMessage(e, "Couldn't import. Try again."),
        ),
    });
  };

  const busy = importMut.isPending;
  return (
    <Dialog
      open={open}
      onClose={() => !busy && onClose()}
      title="Import vocabulary"
      size="md"
      initialFocusRef={textRef}
      actions={
        <>
          <Button variant="text" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={submit} loading={busy}>
            Import
          </Button>
        </>
      }
    >
      <p>
        Paste terms, one per line, or pick a text file. Terms you already have are kept; new ones are added.
      </p>
      <div className="mt-4 flex flex-col gap-4">
        <FilePicker
          label="Text file"
          accept=".txt,.md,.csv,text/plain"
          file={file}
          onChange={pick}
          disabled={busy}
        />
        <TextField
          ref={textRef}
          multiline
          tonal
          mono
          label="Or paste here"
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setError(null);
          }}
          placeholder={'Plaud\nParrot Deck = Parted Deck'}
          spellCheck={false}
          disabled={busy}
          error={!!error}
          helper={error ?? undefined}
          className="[&_textarea]:min-h-[140px]"
        />
      </div>
    </Dialog>
  );
}
