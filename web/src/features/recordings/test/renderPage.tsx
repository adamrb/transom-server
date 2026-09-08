import { Route, Routes } from 'react-router-dom';
import { renderWithProviders, type RenderWithProvidersOptions } from '@/test/render';
import { RecordingsPage } from '../RecordingsPage';
import { PlayerStore } from '../player/playerStore';
import { PlayerStoreContext } from '../player/usePlayer';
import { FakeAudio } from './fakeAudio';

/** The recordings routes with a fresh player store on a fake audio element. */
export function renderRecordings({
  setup,
  ...options
}: RenderWithProvidersOptions & { setup?: (store: PlayerStore) => void } = {}) {
  const audio = new FakeAudio();
  const store = new PlayerStore({
    createAudio: () => audio,
    fetchLink: async (id) => ({
      url: `/api/v1/recordings/${id}/audio?sig=x`,
      expires_at: Math.floor(Date.now() / 1000) + 3600,
    }),
    fetchBlob: async () => new Blob(['x']),
  });
  setup?.(store);
  const result = renderWithProviders(
    <PlayerStoreContext.Provider value={store}>
      <Routes>
        <Route path="/" element={<RecordingsPage />} />
        <Route path="/rec/:id" element={<RecordingsPage />} />
        <Route path="/settings" element={<div>Settings page</div>} />
      </Routes>
    </PlayerStoreContext.Provider>,
    options,
  );
  return { ...result, audio, store };
}
