import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiJson } from '../client';
import { qk } from '../keys';
import {
  VocabularyImportSchema,
  VocabularySaveSchema,
  VocabularySchema,
  type VocabEntry,
  type Vocabulary,
} from '../types';

/** The vocabulary: entries plus the plain-text editor form. */
export function useVocabulary() {
  return useQuery({ queryKey: qk.vocabulary, queryFn: () => apiJson('/vocabulary', VocabularySchema) });
}

/** Body entries for PUT / import: weights are optional (the server keeps existing ones). */
export type VocabEntryInput = Pick<VocabEntry, 'term' | 'aliases'> &
  Partial<Pick<VocabEntry, 'source' | 'weight'>>;

/** Limits mirrored from the server (app/vocabulary.py). */
export const VOCAB_LIMITS = { entries: 600, term: 64, aliases: 20 } as const;

/**
 * One line of the editor text, classified. `blank` and `comment` (`# …`) lines are kept but not
 * saved; `ignored` lines have nothing before the equals sign and are dropped on save (the editor
 * footer counts them); `entry` lines carry a term and its mis-hearings.
 */
export type VocabLine =
  | { kind: 'blank' | 'comment' | 'ignored'; raw: string }
  | { kind: 'entry'; raw: string; term: string; aliases: string[] };

const squash = (s: string) => s.replace(/\s+/g, ' ').trim();

/** Classify one raw line. Splits on the first `=` only, so an alias may contain one. */
export function parseVocabularyLine(raw: string): VocabLine {
  const line = raw.trim();
  if (!line) return { kind: 'blank', raw };
  if (line.startsWith('#')) return { kind: 'comment', raw };
  const eq = line.indexOf('=');
  const termPart = eq === -1 ? line : line.slice(0, eq);
  const rest = eq === -1 ? '' : line.slice(eq + 1);
  const term = squash(termPart).slice(0, VOCAB_LIMITS.term);
  if (!term) return { kind: 'ignored', raw };
  const aliases = rest.split(',').map(squash).filter(Boolean).slice(0, VOCAB_LIMITS.aliases);
  return { kind: 'entry', raw, term, aliases };
}

/** Every line of the editor text, in order (indexes match `text.split('\n')`). */
export function parseVocabularyLines(text: string): VocabLine[] {
  return text.split('\n').map(parseVocabularyLine);
}

/**
 * Parse the editor text into entries: one term per line, `Term = mis-hearing, mis-hearing`;
 * blank lines and `#` comments are skipped. Returns the entries (capped at the server's limit)
 * and how many lines would be ignored because nothing precedes the equals sign.
 */
export function parseVocabularyText(text: string): { entries: VocabEntryInput[]; ignored: number } {
  const entries: VocabEntryInput[] = [];
  let ignored = 0;
  for (const line of parseVocabularyLines(text)) {
    if (line.kind === 'ignored') ignored++;
    else if (line.kind === 'entry') entries.push({ term: line.term, aliases: line.aliases });
  }
  return { entries: entries.slice(0, VOCAB_LIMITS.entries), ignored };
}

/** One editor line for an entry: `Term = alias, alias`, or just `Term`. The server writes the same. */
export function serializeVocabularyEntry(entry: Pick<VocabEntry, 'term' | 'aliases'>): string {
  return entry.aliases.length ? `${entry.term} = ${entry.aliases.join(', ')}` : entry.term;
}

/**
 * The editor text for a list of entries, one line each, in the given order. `sorted` orders them
 * by lower-cased term the way the server writes `editor_text`.
 */
export function serializeVocabularyText(
  entries: Pick<VocabEntry, 'term' | 'aliases'>[],
  { sorted = false }: { sorted?: boolean } = {},
): string {
  const list = sorted
    ? [...entries].sort((a, b) => {
        const x = a.term.toLowerCase();
        const y = b.term.toLowerCase();
        return x < y ? -1 : x > y ? 1 : 0;
      })
    : entries;
  return list.map(serializeVocabularyEntry).join('\n');
}

/**
 * Replace the whole list (what the editor saves). The PUT answers with the normalised entries, so
 * the cache is updated from them at once (the editor text the server would write is the sorted
 * serialisation) and then refetched for the rest (hotwords).
 */
export function useSaveVocabulary() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (entries: VocabEntryInput[]) =>
      apiJson('/vocabulary', VocabularySaveSchema, { method: 'PUT', json: { entries } }),
    onSuccess: (saved) => {
      qc.setQueryData<Vocabulary>(qk.vocabulary, (old) => ({
        hotwords: old?.hotwords ?? '',
        ...old,
        entries: saved.entries,
        editor_text: serializeVocabularyText(saved.entries, { sorted: true }),
      }));
      void qc.invalidateQueries({ queryKey: qk.vocabulary });
    },
  });
}

/** Merge entries in (Import…): existing terms and aliases are kept. */
export function useImportVocabulary() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (entries: VocabEntryInput[]) =>
      apiJson('/vocabulary/import', VocabularyImportSchema, { method: 'POST', json: { entries } }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.vocabulary }),
  });
}
