import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/api';
import { PlayerStore } from './player/playerStore';
import { FakeAudio } from './test/fakeAudio';

function make(overrides: Partial<ConstructorParameters<typeof PlayerStore>[0]> = {}) {
  const audio = new FakeAudio();
  const fetchLink = vi.fn(async (id: string) => ({
    url: `/api/v1/recordings/${id}/audio?sig=${fetchLink.mock.calls.length}`,
    expires_at: Math.floor(Date.now() / 1000) + 3600,
  }));
  const fetchBlob = vi.fn(async () => new Blob(['audio']));
  const store = new PlayerStore({ createAudio: () => audio, fetchLink, fetchBlob, ...overrides });
  return { audio, store, fetchLink, fetchBlob };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

afterEach(() => vi.restoreAllMocks());

describe('player store', () => {
  it('loads a recording: fetches a link and lets the browser read the metadata', async () => {
    const { audio, store, fetchLink } = make();
    store.load({ id: 'a', title: 'A', duration_s: 120 }, [30]);
    expect(store.getSnapshot()).toMatchObject({
      id: 'a',
      title: 'A',
      duration: 120,
      markers: [30],
      playing: false,
    });
    await flush();
    expect(fetchLink).toHaveBeenCalledWith('a');
    expect(audio.src).toContain('/recordings/a/audio?sig=');
    expect(audio.preload).toBe('metadata');
    audio.loaded(121.5);
    expect(store.getSnapshot().duration).toBe(121.5);
  });

  it('plays, pauses, toggles and reports time updates', async () => {
    const { audio, store } = make();
    store.load({ id: 'a', title: 'A', duration_s: 120 });
    await flush();
    audio.loaded(120);
    await store.play();
    expect(audio.paused).toBe(false);
    expect(store.getSnapshot().playing).toBe(true);
    audio.tick(12.5);
    expect(store.getSnapshot().currentTime).toBe(12.5);
    store.toggle();
    expect(audio.paused).toBe(true);
    expect(store.getSnapshot().playing).toBe(false);
    store.toggle();
    await flush();
    expect(audio.paused).toBe(false);
  });

  it('skips 15 s back and 30 s forward, clamped to the recording', async () => {
    const { audio, store } = make();
    store.load({ id: 'a', title: 'A', duration_s: 100 });
    await flush();
    audio.loaded(100);
    audio.tick(20);
    store.skip(30);
    await flush();
    expect(audio.currentTime).toBe(50);
    store.skip(-15);
    await flush();
    expect(audio.currentTime).toBe(35);
    audio.tick(5);
    store.skip(-15);
    await flush();
    expect(audio.currentTime).toBe(0);
    audio.tick(90);
    store.skip(30);
    await flush();
    expect(audio.currentTime).toBe(100);
    // skipping while paused does not start playback
    expect(audio.paused).toBe(true);
  });

  it('seeks (and plays) from a paragraph time, waiting for the metadata when needed', async () => {
    const { audio, store } = make();
    store.load({ id: 'a', title: 'A', duration_s: 100 });
    await flush();
    const p = store.seek(42);
    await flush();
    expect(store.getSnapshot().currentTime).toBe(42); // shown at once
    audio.loaded(100);
    await p;
    expect(audio.currentTime).toBe(42);
    expect(audio.paused).toBe(false);
    await store.seek(10, { autoplay: false });
    expect(audio.currentTime).toBe(10);
  });

  it('persists the speed in localStorage pb_speed and applies it to the element', async () => {
    const { audio, store } = make();
    store.load({ id: 'a', title: 'A', duration_s: 100 });
    await flush();
    store.setSpeed(1.5);
    expect(localStorage.getItem('pb_speed')).toBe('1.5');
    expect(audio.playbackRate).toBe(1.5);
    expect(store.getSnapshot().speed).toBe(1.5);
    const again = make();
    expect(again.store.getSnapshot().speed).toBe(1.5);
    localStorage.setItem('pb_speed', '7');
    expect(make().store.getSnapshot().speed).toBe(1);
  });

  it('refreshes an expired or rejected link once, keeping the position, then gives up', async () => {
    const { audio, store, fetchLink } = make();
    store.load({ id: 'a', title: 'A', duration_s: 100 });
    await flush();
    audio.loaded(100);
    await store.play();
    audio.tick(33);
    audio.emit('error');
    await flush();
    expect(fetchLink).toHaveBeenCalledTimes(2);
    expect(audio.src).toContain('sig=2');
    audio.currentTime = 0;
    audio.loaded(100); // the new source's metadata
    expect(audio.currentTime).toBe(33);
    expect(audio.paused).toBe(false);
    const before = store.getSnapshot().errorSeq;
    audio.emit('error');
    await flush();
    expect(fetchLink).toHaveBeenCalledTimes(2);
    expect(store.getSnapshot().errorSeq).toBe(before + 1);
    expect(store.getSnapshot().lastError).toBe("Couldn't play the audio.");
  });

  it('fetches a fresh link before playing when the current one is about to expire', async () => {
    let now = 1_000_000_000_000;
    const { audio, store, fetchLink } = make({ now: () => now });
    fetchLink.mockImplementation(async (id: string) => ({
      url: `/api/v1/recordings/${id}/audio?sig=${fetchLink.mock.calls.length}`,
      expires_at: Math.floor(now / 1000) + 3600,
    }));
    store.load({ id: 'a', title: 'A', duration_s: 100 });
    await flush();
    audio.loaded(100);
    now += 3600_000 - 30_000; // 30 s left
    await store.play();
    expect(fetchLink).toHaveBeenCalledTimes(2);
  });

  it('falls back to a blob when the server has no signed links (404)', async () => {
    const { audio, store, fetchLink, fetchBlob } = make();
    fetchLink.mockRejectedValue(new ApiError(404, 'Not Found'));
    Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:audio'), revokeObjectURL: vi.fn() });
    store.load({ id: 'a', title: 'A', duration_s: 100 });
    await flush();
    expect(audio.src).toBe('');
    await store.play();
    expect(fetchBlob).toHaveBeenCalledWith('a');
    expect(audio.src).toBe('blob:audio');
    expect(audio.paused).toBe(false);
    // the next recording goes straight to the blob without asking for a link again
    store.load({ id: 'b', title: 'B', duration_s: 10 });
    await flush();
    expect(fetchLink).toHaveBeenCalledTimes(1);
  });

  it('reports a failed load in user words and resets cleanly', async () => {
    const { audio, store, fetchLink, fetchBlob } = make();
    fetchLink.mockRejectedValue(new ApiError(404, null));
    fetchBlob.mockRejectedValue(new ApiError(500, null));
    store.load({ id: 'a', title: 'A', duration_s: 100 });
    await flush();
    await store.play();
    expect(store.getSnapshot().lastError).toBe("Couldn't load the audio.");
    expect(store.getSnapshot().loading).toBe(false);
    store.resetIf('other');
    expect(store.getSnapshot().id).toBe('a');
    store.resetIf('a');
    expect(store.getSnapshot()).toMatchObject({
      id: null,
      title: '',
      currentTime: 0,
      playing: false,
      lastError: null,
    });
    expect(audio.src).toBe('');
  });

  it('drops a deferred seek when another recording is loaded before the metadata arrives', async () => {
    const { audio, store } = make();
    store.load({ id: 'a', title: 'A', duration_s: 100 });
    await flush();
    void store.seek(42); // metadata not loaded yet: waits for loadedmetadata
    await flush();
    store.load({ id: 'b', title: 'B', duration_s: 50 });
    await flush();
    audio.loaded(50); // b's metadata: the stale seek must neither move nor play b
    expect(audio.currentTime).toBe(0);
    expect(audio.paused).toBe(true);
    expect(store.getSnapshot()).toMatchObject({ id: 'b', currentTime: 0, playing: false });
  });

  it('ignores failures and refreshes of a recording that was replaced while a request was out', async () => {
    const { audio, store, fetchLink } = make();
    // A's link request is slow and then fails; B is loaded meanwhile.
    let rejectA: (e: unknown) => void = () => {};
    fetchLink.mockImplementationOnce(() => new Promise((_r, rej) => (rejectA = rej)));
    store.load({ id: 'a', title: 'A', duration_s: 100 });
    await flush();
    store.load({ id: 'b', title: 'B', duration_s: 50 });
    await flush();
    expect(audio.src).toContain('/recordings/b/audio');
    rejectA(new ApiError(500, null));
    await flush();
    // B is untouched: still on its link, no error reported.
    expect(audio.src).toContain('/recordings/b/audio');
    expect(store.getSnapshot().errorSeq).toBe(0);
    await store.play();
    expect(fetchLink).toHaveBeenCalledTimes(2); // no blob fallback was forced on B

    // A refresh that resolves after the same recording was reset and reopened is dropped.
    audio.loaded(50);
    audio.tick(20);
    let resolveRefresh: (v: { url: string; expires_at: number }) => void = () => {};
    fetchLink.mockImplementationOnce(() => new Promise((res) => (resolveRefresh = res)));
    audio.emit('error');
    await flush();
    store.reset();
    store.load({ id: 'b', title: 'B', duration_s: 50 });
    await flush();
    const fresh = audio.src;
    resolveRefresh({ url: '/stale', expires_at: 9e9 });
    await flush();
    expect(audio.src).toBe(fresh);
    expect(store.getSnapshot().currentTime).toBe(0);
  });

  it('loading the same recording again keeps playback and only refreshes the title and markers', async () => {
    const { audio, store, fetchLink } = make();
    store.load({ id: 'a', title: 'A', duration_s: 100 });
    await flush();
    audio.loaded(100);
    await store.play();
    audio.tick(20);
    store.load({ id: 'a', title: 'A renamed', duration_s: 100 }, [5]);
    expect(store.getSnapshot()).toMatchObject({
      title: 'A renamed',
      markers: [5],
      currentTime: 20,
      playing: true,
    });
    expect(fetchLink).toHaveBeenCalledTimes(1);
    expect(audio.paused).toBe(false);
  });
});
