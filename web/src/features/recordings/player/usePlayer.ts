import { createContext, useContext, useEffect, useRef, useSyncExternalStore } from 'react';
import { useSnackbar } from '@/components';
import { paragraphAt } from '../lib/transcript';
import { playerStore, type PlayerState, type PlayerStore } from './playerStore';

/** Tests may hand the tree a store with a fake audio element. */
export const PlayerStoreContext = createContext<PlayerStore>(playerStore);

export function usePlayerStore(): PlayerStore {
  return useContext(PlayerStoreContext);
}

/** The whole player state (re-renders on every time update: use in player UI only). */
export function usePlayer(): [PlayerState, PlayerStore] {
  const store = usePlayerStore();
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  return [state, store];
}

/** A slice of the player state; re-renders only when the selected value changes. */
export function usePlayerSelector<T>(select: (s: PlayerState) => T): T {
  const store = usePlayerStore();
  return useSyncExternalStore(
    store.subscribe,
    () => select(store.getSnapshot()),
    () => select(store.getSnapshot()),
  );
}

/** Index of the paragraph now playing for recording `id`, or -1 (nothing loaded / other recording). */
export function useNowPlayingIndex(id: string | null | undefined, starts: number[]): number {
  return usePlayerSelector((s) => (id && s.id === id ? paragraphAt(starts, s.currentTime) : -1));
}

/** Shows each playback failure in the snackbar. Mount once, in the recordings page. */
export function usePlayerErrors() {
  const snackbar = useSnackbar();
  const store = usePlayerStore();
  const errorSeq = usePlayerSelector((s) => s.errorSeq);
  // Only failures that happen while mounted are shown: an old one must not reappear on remount.
  const seen = useRef(errorSeq);
  useEffect(() => {
    if (errorSeq === seen.current) return;
    seen.current = errorSeq;
    const msg = store.getSnapshot().lastError;
    if (msg) snackbar.error(msg);
  }, [errorSeq, snackbar, store]);
}
