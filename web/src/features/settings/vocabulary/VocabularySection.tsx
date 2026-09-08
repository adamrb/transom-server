import { useState } from 'react';
import { Avatar } from '@/components/Avatar';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { SegmentedButton } from '@/components/SegmentedButton';
import { Skeleton } from '@/components/Skeleton';
import { TextField } from '@/components/TextField';
import { useSnackbar } from '@/components/Snackbar';
import { ApiError, errorMessage } from '@/api/client';
import { useSaveVocabulary, useVocabulary, VOCAB_LIMITS } from '@/api/hooks/vocabulary';
import { plural } from '@/lib/format';
import { SettingsSection } from '../SettingsSection';
import { ImportDialog } from './ImportDialog';
import { VocabularyList, matchesFilter } from './VocabularyList';
import { useVocabularyEditor, type VocabularyMode } from './useVocabularyEditor';

const MODES = [
  { key: 'list', label: 'List', icon: 'format_list_bulleted' },
  { key: 'text', label: 'Text', icon: 'description' },
] as const;

function Code({ children }: { children: string }) {
  return (
    <code className="rounded-[6px] bg-surface-container-high px-1.5 py-px font-mono text-[.92em] text-on-surface">
      {children}
    </code>
  );
}

/**
 * Vocabulary: the names and terms the transcriber should get right, with the mis-hearings each
 * one corrects. Two views of the same text: a row list (default) and the raw text. Dirty tracking
 * against the server's text; Save and Revert live directly under the editor; Import… merges a
 * pasted or uploaded list.
 */
export function VocabularySection() {
  const query = useVocabulary();
  const editor = useVocabularyEditor(query);
  const save = useSaveVocabulary();
  const snackbar = useSnackbar();
  const [mode, setMode] = useState<VocabularyMode>('list');
  const [filter, setFilter] = useState('');
  const [adding, setAdding] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  const unsupported = query.error instanceof ApiError && query.error.notFound;
  const tooMany = editor.rows.length > VOCAB_LIMITS.entries;
  const filterKey = filter.trim().toLowerCase();

  const onSave = () => {
    save.mutate(editor.entriesForSave(), {
      onSuccess: () => {
        editor.adoptServer();
        snackbar.show('Vocabulary saved. It applies to new transcriptions.');
      },
      onError: (e) => snackbar.error(errorMessage(e, "Couldn't save the vocabulary.")),
    });
  };

  const status = editor.dirty ? 'Unsaved changes' : query.data ? 'Saved · applies to new transcriptions' : '';
  const notes = [
    editor.ignored
      ? `${plural(editor.ignored, 'line')} will be ignored (nothing before the equals sign)`
      : '',
    tooMany
      ? `Up to ${VOCAB_LIMITS.entries} terms; remove ${editor.rows.length - VOCAB_LIMITS.entries} to save`
      : '',
  ].filter(Boolean);

  const filteredLines = filterKey
    ? editor.text.split('\n').filter((l) => l.toLowerCase().includes(filterKey))
    : [];

  return (
    <SettingsSection title="Vocabulary">
      <Card>
        <div className="flex items-start gap-4">
          <Avatar kind="icon" icon="spellcheck" size={40} shape="rounded" />
          <div className="min-w-0 flex-1">
            <div className="text-body-l text-on-surface">
              Names and terms the transcriber should get right
            </div>
            <div className="mt-0.5 text-body-m text-on-surface-variant">
              Add a term and the ways it usually comes out wrong, and every new transcript is corrected. In
              the text view each line is <Code>Plaud Bridge = Plogged Bridge, Plod Bridge</Code>; lines
              starting with <Code>#</Code> are notes.
            </div>
          </div>
        </div>

        {query.isPending ? (
          <div className="mt-4 flex flex-col gap-3" aria-busy="true" aria-label="Loading vocabulary">
            <Skeleton height={40} width="60%" />
            <Skeleton height={168} />
          </div>
        ) : unsupported ? (
          <p className="mt-4 mb-0 text-body-m text-on-surface-variant">
            Your server doesn't support custom vocabulary yet.
          </p>
        ) : query.isError && !query.data ? (
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <span className="flex-1 text-body-m text-error">
              {errorMessage(query.error, "Couldn't load the vocabulary.")}
            </span>
            <Button variant="outlined" size="sm" icon="refresh" onClick={() => void query.refetch()}>
              Retry
            </Button>
          </div>
        ) : (
          <>
            <div className="mt-4 mb-2.5 flex flex-wrap items-center gap-3">
              <TextField
                size="sm"
                icon="search"
                type="search"
                placeholder="Find a term"
                aria-label="Find a term"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="min-w-[200px] flex-1 md:max-w-[320px]"
              />
              {/* Count and view toggle share a row; on phone the pair wraps under the filter. */}
              <div className="flex min-w-[260px] flex-1 items-center gap-3">
                <span className="flex-1 text-body-s text-on-surface-variant tnum">
                  {editor.counts.terms
                    ? `${plural(editor.counts.terms, 'term')} · ${editor.counts.withCorrections} with corrections`
                    : 'No custom vocabulary yet.'}
                </span>
                <SegmentedButton<VocabularyMode>
                  size="sm"
                  label="Editor view"
                  value={mode}
                  onChange={(m) => {
                    setMode(m);
                    setAdding(false);
                  }}
                  options={[...MODES]}
                />
              </div>
            </div>

            {mode === 'list' ? (
              <VocabularyList
                rows={editor.rows}
                filter={filterKey}
                total={editor.rows.length}
                hasTerm={editor.hasTerm}
                onAdd={editor.addRow}
                onUpdate={editor.updateRow}
                onRemove={editor.removeRow}
                adding={adding}
                onAddingChange={setAdding}
                disabled={save.isPending}
              />
            ) : filterKey ? (
              <pre
                className="m-0 max-h-[320px] overflow-auto rounded-md bg-surface-container-high px-3.5 py-3 font-mono text-mono whitespace-pre-wrap text-on-surface"
                aria-label="Matching lines"
              >
                {filteredLines.length ? filteredLines.join('\n') : 'No matching lines.'}
              </pre>
            ) : (
              <TextField
                multiline
                tonal
                mono
                aria-label="Vocabulary text"
                value={editor.text}
                onChange={(e) => editor.setText(e.target.value)}
                rows={8}
                spellCheck={false}
                disabled={save.isPending}
                placeholder={'Plaud\nPlaud Bridge = Plogged Bridge\nObsidian'}
              />
            )}

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="mr-auto text-body-s text-on-surface-variant max-md:basis-full">
                {mode === 'text' && filterKey
                  ? `Showing ${plural(filteredLines.length, 'matching line')}. Clear the filter to edit.`
                  : [status, ...notes].filter(Boolean).join(' · ')}
              </span>
              <Button
                variant="text"
                size="sm"
                icon="upload"
                disabled={editor.dirty || save.isPending}
                title={editor.dirty ? 'Save or revert your changes first' : undefined}
                onClick={() => setImportOpen(true)}
              >
                Import…
              </Button>
              <Button
                variant="text"
                size="sm"
                disabled={!editor.dirty || save.isPending}
                onClick={editor.revert}
              >
                Revert
              </Button>
              <Button size="sm" disabled={!editor.dirty || tooMany} loading={save.isPending} onClick={onSave}>
                Save
              </Button>
            </div>
          </>
        )}
      </Card>
      <ImportDialog open={importOpen} onClose={() => setImportOpen(false)} />
    </SettingsSection>
  );
}

export { matchesFilter };
