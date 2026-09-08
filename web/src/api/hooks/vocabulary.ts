import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiJson } from '../client';
import { qk } from '../keys';
import { VocabularyImportSchema, VocabularySaveSchema, VocabularySchema, type VocabEntry } from '../types';

/** The vocabulary: entries plus the plain-text editor form. */
export function useVocabulary() {
  return useQuery({ queryKey: qk.vocabulary, queryFn: () => apiJson('/vocabulary', VocabularySchema) });
}

/** Body entries for PUT / import: weights are optional (the server keeps existing ones). */
export type VocabEntryInput = Pick<VocabEntry, 'term' | 'aliases'> &
  Partial<Pick<VocabEntry, 'source' | 'weight'>>;

/**
 * Parse the editor text into entries: one term per line, `Term = mis-hearing, mis-hearing`;
 * blank lines and `#` comments are ignored. Returns the entries and how many lines were ignored
 * (the editor footer shows the count).
 */
export function parseVocabularyText(text: string): { entries: VocabEntryInput[]; ignored: number } {
  const entries: VocabEntryInput[] = [];
  let ignored = 0;
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith('#')) {
      ignored++;
      continue;
    }
    const [termPart, ...rest] = line.split('=');
    const term = termPart.replace(/\s+/g, ' ').trim().slice(0, 64);
    if (!term) {
      ignored++;
      continue;
    }
    const aliases = rest
      .join('=')
      .split(',')
      .map((a) => a.replace(/\s+/g, ' ').trim())
      .filter(Boolean)
      .slice(0, 20);
    entries.push({ term, aliases });
  }
  return { entries: entries.slice(0, 600), ignored };
}

/** Replace the whole list (what the editor saves). */
export function useSaveVocabulary() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (entries: VocabEntryInput[]) =>
      apiJson('/vocabulary', VocabularySaveSchema, { method: 'PUT', json: { entries } }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.vocabulary }),
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
