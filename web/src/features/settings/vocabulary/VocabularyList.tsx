import { useState } from 'react';
import { Button } from '@/components/Button';
import { IconButton } from '@/components/IconButton';
import { cn } from '@/lib/cn';
import { plural } from '@/lib/format';
import type { VocabularyRow } from './useVocabularyEditor';
import { VocabularyRowEditor } from './VocabularyRowEditor';

export interface VocabularyListProps {
  rows: VocabularyRow[];
  /** Lower-cased filter; rows whose term or mis-hearings contain it are shown. */
  filter: string;
  /** Total rows before filtering (for the empty copy). */
  total: number;
  hasTerm: (term: string, exceptLine?: number) => boolean;
  onAdd: (entry: { term: string; aliases: string[] }) => void;
  onUpdate: (line: number, entry: { term: string; aliases: string[] }) => void;
  onRemove: (line: number) => void;
  /** Show the add form (opened from the toolbar). */
  adding: boolean;
  onAddingChange: (adding: boolean) => void;
  disabled?: boolean;
}

export function matchesFilter(row: Pick<VocabularyRow, 'term' | 'aliases'>, filter: string): boolean {
  if (!filter) return true;
  const q = filter.toLowerCase();
  return row.term.toLowerCase().includes(q) || row.aliases.some((a) => a.toLowerCase().includes(q));
}

/**
 * The vocabulary as rows: term, the mis-hearings it corrects, edit and remove. The list scrolls
 * inside a fixed-height box (hundreds of terms are normal); the add form sits under it. One row
 * edits at a time. Rows are keyed by line so edits land on the right line even while a filter
 * hides neighbours.
 */
export function VocabularyList({
  rows,
  filter,
  total,
  hasTerm,
  onAdd,
  onUpdate,
  onRemove,
  adding,
  onAddingChange,
  disabled,
}: VocabularyListProps) {
  const [editing, setEditing] = useState<number | null>(null);
  const visible = rows.filter((r) => matchesFilter(r, filter));
  // One change at a time: rows are addressed by line, and removing a row above an open editor
  // would shift the line the editor writes back to.
  const locked = disabled || editing !== null;

  return (
    <div className="overflow-hidden rounded-md bg-surface-container-low [--field-bg:var(--sc-low)]">
      <div className="max-h-[420px] overflow-y-auto px-4" role="list" aria-label="Vocabulary terms">
        {visible.length === 0 && (
          <div className="py-5 text-center text-body-m text-on-surface-variant">
            {total === 0 ? 'No custom vocabulary yet. Add a term, or import a list.' : 'No terms match.'}
          </div>
        )}
        {visible.map((row) =>
          editing === row.line ? (
            <div role="listitem" key={row.line}>
              <VocabularyRowEditor
                term={row.term}
                aliases={row.aliases}
                isDuplicate={(t) => hasTerm(t, row.line)}
                onCancel={() => setEditing(null)}
                onSave={(entry) => {
                  onUpdate(row.line, entry);
                  setEditing(null);
                }}
              />
            </div>
          ) : (
            <div
              role="listitem"
              key={row.line}
              className={cn(
                'flex min-h-12 items-center gap-2 border-t border-outline-variant py-1 first:border-t-0',
                disabled && 'opacity-[.38]',
              )}
            >
              <div className="min-w-0 flex-1">
                <div className="truncate text-body-l text-on-surface">{row.term}</div>
                {row.aliases.length > 0 && (
                  <div className="truncate text-body-m text-on-surface-variant">
                    <span className="text-on-surface-variant/80">Heard as </span>
                    {row.aliases.join(', ')}
                  </div>
                )}
              </div>
              <IconButton
                icon="edit"
                label={`Edit ${row.term}`}
                disabled={locked}
                onClick={() => {
                  onAddingChange(false);
                  setEditing(row.line);
                }}
              />
              <IconButton
                icon="delete"
                label={`Remove ${row.term}`}
                disabled={locked}
                onClick={() => onRemove(row.line)}
              />
            </div>
          ),
        )}
      </div>
      <div className="border-t border-outline-variant px-4">
        {adding ? (
          <VocabularyRowEditor
            isDuplicate={(t) => hasTerm(t)}
            saveLabel="Add"
            onCancel={() => onAddingChange(false)}
            onSave={(entry) => {
              onAdd(entry);
              onAddingChange(false);
            }}
          />
        ) : (
          <div className="flex items-center gap-3 py-1.5">
            <Button
              variant="text"
              size="sm"
              icon="add"
              disabled={locked}
              onClick={() => {
                setEditing(null);
                onAddingChange(true);
              }}
            >
              Add a term
            </Button>
            {filter && visible.length > 0 && (
              <span className="ml-auto text-body-s text-on-surface-variant tnum">
                Showing {plural(visible.length, 'match', 'matches')}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
