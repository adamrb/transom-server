import { TextField } from '@/components/TextField';

export interface MarkdownFieldsProps {
  folder: string;
  onFolder: (v: string) => void;
  error?: string;
  disabled?: boolean;
}

/** Where the note goes: a folder inside the notes export folder on the server. */
export function MarkdownFields({ folder, onFolder, error, disabled }: MarkdownFieldsProps) {
  return (
    <TextField
      label="Folder in your vault"
      icon="folder"
      autoComplete="off"
      spellCheck={false}
      placeholder="Meetings/Work"
      value={folder}
      onChange={(e) => onFolder(e.target.value)}
      error={!!error}
      helper={error ?? 'Inside your notes export folder on the server. Created if it is missing.'}
      disabled={disabled}
    />
  );
}
