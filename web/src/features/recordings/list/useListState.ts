import { useEffect, useState, useSyncExternalStore } from 'react';
import type { RecordingFilter } from '@/api';

export interface ListState {
  /** What is typed in the search bar (undebounced). */
  q: string;
  /** The selected filter chip; '' = All. */
  status: RecordingFilter | '';
}

export interface FilterOption {
  key: RecordingFilter | '';
  label: string;
}

/** The filter chips, in order. `no_speech` and `stored` are server filters too. */
export const FILTERS: FilterOption[] = [
  { key: '', label: 'All' },
  { key: 'pending', label: 'Waiting' },
  { key: 'transcribing', label: 'Transcribing' },
  { key: 'failed', label: 'Failed' },
  { key: 'no_speech', label: 'No speech' },
  { key: 'stored', label: 'Not transcribed' },
];

/**
 * Search and filter live outside React so they survive the phone's list ⇄ detail route switch
 * (the list pane unmounts while a recording is open) and any remount of the page.
 */
let state: ListState = { q: '', status: '' };
const listeners = new Set<() => void>();
const subscribe = (fn: () => void) => {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
};
const get = () => state;
function update(patch: Partial<ListState>) {
  state = { ...state, ...patch };
  for (const l of listeners) l();
}

export const listStateStore = { get, update, subscribe, reset: () => update({ q: '', status: '' }) };

export function useListState() {
  const s = useSyncExternalStore(subscribe, get, get);
  return {
    ...s,
    setQ: (q: string) => update({ q }),
    setStatus: (status: RecordingFilter | '') => update({ status }),
    clearSearch: () => update({ q: '' }),
  };
}

/** `value` once it has stopped changing for `ms` (the search box → the query). */
export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}
