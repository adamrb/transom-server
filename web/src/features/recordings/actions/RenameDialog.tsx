import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Button, Dialog, TextField } from '@/components';

export interface RenameDialogProps {
  open: boolean;
  title: ReactNode;
  label: string;
  /** Initial value; the field selects it on open. */
  value: string;
  maxLength?: number;
  ok?: string;
  busy?: boolean;
  onCancel: () => void;
  /** Called with the collapsed, trimmed name; not called when unchanged. */
  onSubmit: (name: string) => void;
}

/**
 * The prompt used for renaming a recording or a speaker: one text field, "Type a name." when it
 * is left blank, whitespace collapsed like the old dashboard did.
 */
export function RenameDialog({
  open,
  title,
  label,
  value,
  maxLength = 120,
  ok = 'Save',
  busy,
  onCancel,
  onSubmit,
}: RenameDialogProps) {
  const [draft, setDraft] = useState(value);
  const [error, setError] = useState('');
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (open) {
      setDraft(value);
      setError('');
      // The dialog focuses after showModal(); select the text one tick later.
      const t = setTimeout(() => {
        input.current?.focus();
        input.current?.select();
      }, 0);
      return () => clearTimeout(t);
    }
  }, [open, value]);

  const submit = () => {
    const v = draft.replace(/\s+/g, ' ').trim();
    if (!v) {
      setError('Type a name.');
      return;
    }
    if (v === value) {
      onCancel();
      return;
    }
    onSubmit(v);
  };

  return (
    <Dialog
      open={open}
      onClose={onCancel}
      title={title}
      initialFocusRef={input}
      actions={
        <>
          <Button variant="text" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={submit} loading={busy}>
            {ok}
          </Button>
        </>
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="pt-1"
      >
        <TextField
          ref={input}
          label={label}
          value={draft}
          maxLength={maxLength}
          autoComplete="off"
          error={!!error}
          helper={error || undefined}
          onChange={(e) => {
            setDraft(e.target.value);
            if (error) setError('');
          }}
        />
      </form>
    </Dialog>
  );
}
