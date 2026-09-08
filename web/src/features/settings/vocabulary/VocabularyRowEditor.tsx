import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Button } from '@/components/Button';
import { TextField } from '@/components/TextField';
import { VOCAB_LIMITS } from '@/api/hooks/vocabulary';

export interface VocabularyRowEditorProps {
  /** Existing values when editing; empty when adding. */
  term?: string;
  aliases?: string[];
  /** Is this term already used by another row? (case-insensitive) */
  isDuplicate: (term: string) => boolean;
  onSave: (entry: { term: string; aliases: string[] }) => void;
  onCancel: () => void;
  /** Button label: "Add" or "Done". */
  saveLabel?: string;
}

const squash = (s: string) => s.replace(/\s+/g, ' ').trim();

/**
 * Inline editor for one vocabulary row: the term and the mis-hearings it should replace,
 * comma-separated. Validates what the text format cannot express (an equals sign in a term) and
 * duplicates, then hands back a clean entry.
 */
export function VocabularyRowEditor({
  term: initialTerm = '',
  aliases: initialAliases = [],
  isDuplicate,
  onSave,
  onCancel,
  saveLabel = 'Done',
}: VocabularyRowEditorProps) {
  const [term, setTerm] = useState(initialTerm);
  const [aliases, setAliases] = useState(initialAliases.join(', '));
  const [error, setError] = useState<string | null>(null);
  const termRef = useRef<HTMLInputElement>(null);
  useEffect(() => termRef.current?.focus(), []);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const t = squash(term);
    if (!t) return setError('Enter the term.');
    if (t.includes('=')) return setError("A term can't contain an equals sign.");
    if (t.length > VOCAB_LIMITS.term) return setError(`Terms are up to ${VOCAB_LIMITS.term} characters.`);
    if (isDuplicate(t)) return setError('You already have this term.');
    const list = aliases
      .split(',')
      .map(squash)
      .filter((a) => a && a.toLowerCase() !== t.toLowerCase());
    if (list.length > VOCAB_LIMITS.aliases)
      return setError(`Up to ${VOCAB_LIMITS.aliases} mis-hearings per term.`);
    onSave({ term: t, aliases: list });
  };

  return (
    <form
      onSubmit={submit}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          e.preventDefault();
          onCancel();
        }
      }}
      className="flex flex-col gap-3 border-t border-outline-variant py-3.5 first:border-t-0"
      aria-label={initialTerm ? `Edit ${initialTerm}` : 'New term'}
    >
      <div className="flex flex-wrap gap-3">
        <TextField
          ref={termRef}
          label="Term"
          value={term}
          onChange={(e) => {
            setTerm(e.target.value);
            setError(null);
          }}
          placeholder="Plaud Bridge"
          maxLength={VOCAB_LIMITS.term}
          autoComplete="off"
          spellCheck={false}
          className="min-w-[180px] flex-1"
        />
        <TextField
          label="Heard as (optional, comma-separated)"
          value={aliases}
          onChange={(e) => {
            setAliases(e.target.value);
            setError(null);
          }}
          placeholder="Plogged Bridge, Plod Bridge"
          autoComplete="off"
          spellCheck={false}
          className="min-w-[220px] flex-[2]"
        />
      </div>
      <div className="flex items-center gap-2">
        <span role={error ? 'alert' : undefined} className="flex-1 text-body-s text-error">
          {error}
        </span>
        <Button variant="text" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" variant="tonal" size="sm">
          {saveLabel}
        </Button>
      </div>
    </form>
  );
}
