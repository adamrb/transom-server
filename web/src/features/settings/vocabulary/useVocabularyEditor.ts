import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  parseVocabularyLines,
  serializeVocabularyEntry,
  type useVocabulary,
  type VocabEntryInput,
} from '@/api/hooks/vocabulary';
import type { VocabEntry } from '@/api/types';
import { tokenStore } from '@/api/token';

export type VocabularyMode = 'list' | 'text';

/** A term row in list mode: the parsed entry plus which line of the text it lives on. */
export interface VocabularyRow {
  line: number;
  term: string;
  aliases: string[];
  /** Where the term came from; imported ("obsidian") terms keep their source on save. */
  source: VocabEntry['source'];
}

export interface VocabularyEditorState {
  /** The text being edited (the server's `editor_text` until the user changes something). */
  text: string;
  /** What the server holds right now; null until loaded. */
  serverText: string | null;
  dirty: boolean;
  rows: VocabularyRow[];
  /** Lines that would be dropped on save (nothing before the equals sign). */
  ignored: number;
  counts: { terms: number; withCorrections: number };
  setText: (text: string) => void;
  addRow: (entry: Pick<VocabEntry, 'term' | 'aliases'>) => void;
  updateRow: (line: number, entry: Pick<VocabEntry, 'term' | 'aliases'>) => void;
  removeRow: (line: number) => void;
  revert: () => void;
  /** Forget local edits once the server has accepted them; the next data adopts the server text. */
  adoptServer: () => void;
  /** Entries to PUT: parsed from the text, sources carried over from the loaded vocabulary. */
  entriesForSave: () => VocabEntryInput[];
  /** Is this term (case-insensitive) already on another line? */
  hasTerm: (term: string, exceptLine?: number) => boolean;
}

/**
 * The draft outlives the Settings page: switching to another section and back (which unmounts the
 * page; hash navigation never fires beforeunload) keeps unsaved edits. A reload still asks first.
 */
let keptDraft: string | null = null;
let wired = false;

/** Leaving or reloading the tab with a pinned draft asks first, whichever section is open. */
function warnBeforeUnload(e: BeforeUnloadEvent) {
  e.preventDefault();
  e.returnValue = '';
}
function setKeptDraft(v: string | null) {
  const had = keptDraft !== null;
  keptDraft = v;
  if (v !== null && !had) window.addEventListener('beforeunload', warnBeforeUnload);
  else if (v === null && had) window.removeEventListener('beforeunload', warnBeforeUnload);
}
/** Forget a kept draft (sign-out, tests). */
export function resetKeptVocabularyDraft(): void {
  setKeptDraft(null);
}
function useKeptDraft(): [string | null, (v: string | null) => void] {
  // Edits must not outlive the sign-in they were made under.
  if (!wired) {
    wired = true;
    tokenStore.subscribe((token) => {
      if (!token) resetKeptVocabularyDraft();
    });
  }
  const [draft, set] = useState<string | null>(keptDraft);
  const setDraft = useCallback((v: string | null) => {
    setKeptDraft(v);
    set(v);
  }, []);
  return [draft, setDraft];
}

/**
 * Dirty-tracking editor over the vocabulary text. The draft is `null` while it follows the
 * server, so a refetch (poll, focus, another tab saving) can never overwrite local edits: once
 * the user types, the draft is pinned until Save or Revert. Editing back to exactly the server
 * text un-pins it, like the old dashboard's `vocabDirty()` check.
 */
export function useVocabularyEditor(query: ReturnType<typeof useVocabulary>): VocabularyEditorState {
  const serverText = query.data ? query.data.editor_text : null;
  const [draft, setDraft] = useKeptDraft();

  // A brand-new server text while un-pinned simply shows; while pinned it only moves the baseline.
  useEffect(() => {
    if (draft !== null && serverText !== null && draft === serverText) setDraft(null);
  }, [draft, serverText]);

  const text = draft ?? serverText ?? '';
  const dirty = draft !== null && serverText !== null && draft !== serverText;

  const setText = useCallback((next: string) => setDraft(next === serverText ? null : next), [serverText]);

  const lines = useMemo(() => parseVocabularyLines(text), [text]);
  const sources = useMemo(() => {
    const m = new Map<string, VocabEntry['source']>();
    for (const e of query.data?.entries ?? []) m.set(e.term.toLowerCase(), e.source);
    return m;
  }, [query.data]);

  const rows = useMemo<VocabularyRow[]>(
    () =>
      lines.flatMap((l, i) =>
        l.kind === 'entry'
          ? [
              {
                line: i,
                term: l.term,
                aliases: l.aliases,
                source: sources.get(l.term.toLowerCase()) ?? 'manual',
              },
            ]
          : [],
      ),
    [lines, sources],
  );
  const ignored = useMemo(() => lines.filter((l) => l.kind === 'ignored').length, [lines]);
  const counts = useMemo(
    () => ({ terms: rows.length, withCorrections: rows.filter((r) => r.aliases.length > 0).length }),
    [rows],
  );

  const replaceLines = useCallback(
    (fn: (raw: string[]) => string[]) => {
      const raw = text.split('\n');
      setText(fn(raw).join('\n'));
    },
    [text, setText],
  );

  const addRow = useCallback(
    (entry: Pick<VocabEntry, 'term' | 'aliases'>) =>
      replaceLines((raw) => {
        const kept = raw.length === 1 && raw[0].trim() === '' ? [] : raw;
        // Drop a single trailing blank line so terms stay contiguous.
        if (kept.length && kept[kept.length - 1].trim() === '') kept.pop();
        return [...kept, serializeVocabularyEntry(entry)];
      }),
    [replaceLines],
  );
  const updateRow = useCallback(
    (line: number, entry: Pick<VocabEntry, 'term' | 'aliases'>) =>
      replaceLines((raw) => raw.map((r, i) => (i === line ? serializeVocabularyEntry(entry) : r))),
    [replaceLines],
  );
  const removeRow = useCallback(
    (line: number) => replaceLines((raw) => raw.filter((_, i) => i !== line)),
    [replaceLines],
  );

  const revert = useCallback(() => setDraft(null), []);
  const adoptServer = revert;

  const entriesForSave = useCallback(
    () => rows.map<VocabEntryInput>((r) => ({ term: r.term, aliases: r.aliases, source: r.source })),
    [rows],
  );
  const hasTerm = useCallback(
    (term: string, exceptLine?: number) => {
      const key = term.trim().toLowerCase();
      return rows.some((r) => r.line !== exceptLine && r.term.toLowerCase() === key);
    },
    [rows],
  );

  return {
    text,
    serverText,
    dirty,
    rows,
    ignored,
    counts,
    setText,
    addRow,
    updateRow,
    removeRow,
    revert,
    adoptServer,
    entriesForSave,
    hasTerm,
  };
}
