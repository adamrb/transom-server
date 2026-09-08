/**
 * Audio playback state shared by the docked player, the phone mini player, the player sheet and
 * the transcript's now-playing marker. One <audio> element lives outside React; components read
 * the state through `usePlayer()` (useSyncExternalStore).
 *
 * Playback streams from a signed link (`POST audio-link`, one hour) so the browser can seek with
 * Range requests. When the server has no signed links (404) the audio is fetched as a blob once.
 * A link that expired or was rejected gets one fresh link, then we give up. Speed is kept in
 * localStorage `pb_speed`, as the old dashboard did.
 */
import { ApiError, fetchAudioBlob, fetchAudioLink, errorMessage } from '@/api';
import { storage, STORAGE_KEYS } from '@/lib/storage';

export type Speed = 1 | 1.5 | 2;
export const SPEEDS: Speed[] = [1, 1.5, 2];
export const SKIP_BACK_S = 15;
export const SKIP_FORWARD_S = 30;

/** The subset of HTMLAudioElement the store uses (tests inject a fake). */
export interface AudioLike extends EventTarget {
  src: string;
  preload: string;
  currentTime: number;
  duration: number;
  paused: boolean;
  playbackRate: number;
  readyState: number;
  buffered: { length: number; start(i: number): number; end(i: number): number };
  play(): Promise<void>;
  pause(): void;
  removeAttribute(name: string): void;
}

export interface PlayerRecording {
  id: string;
  title: string;
  /** The date line shown under the title in the player sheet. */
  subtitle?: string;
  duration_s?: number | null;
}

export interface PlayerState {
  /** The loaded recording, or null when nothing is loaded. */
  id: string | null;
  title: string;
  subtitle: string;
  /** Seconds. From the audio metadata once known, else the recording's duration. */
  duration: number;
  currentTime: number;
  playing: boolean;
  /** Playback has been started at least once for this recording (the phone mini player appears). */
  started: boolean;
  /** Fetching a link / blob, or the browser is buffering. */
  loading: boolean;
  speed: Speed;
  /** End of the buffered range that contains the playhead (seconds). */
  buffered: number;
  /** Bookmark positions drawn on the slider (seconds). */
  markers: number[];
  /** Bumped on every playback failure; `lastError` is the sentence to show. */
  errorSeq: number;
  lastError: string | null;
}

export interface PlayerStoreDeps {
  createAudio?: () => AudioLike;
  fetchLink?: typeof fetchAudioLink;
  fetchBlob?: typeof fetchAudioBlob;
  now?: () => number;
}

const LINK_REFRESH_MARGIN_MS = 60_000;

function readSpeed(): Speed {
  const s = parseFloat(storage.get(STORAGE_KEYS.speed) ?? '');
  return (SPEEDS as number[]).includes(s) ? (s as Speed) : 1;
}

export class PlayerStore {
  private state: PlayerState = {
    id: null,
    title: '',
    subtitle: '',
    duration: 0,
    currentTime: 0,
    playing: false,
    started: false,
    loading: false,
    speed: readSpeed(),
    buffered: 0,
    markers: [],
    errorSeq: 0,
    lastError: null,
  };
  private listeners = new Set<() => void>();
  private audio: AudioLike | null = null;
  private mode: 'link' | 'blob' | null = null;
  private expires = 0;
  private ready = false;
  private retried = false;
  private blobUrl: string | null = null;
  /** null = unknown, false = the server answered 404 to audio-link (older server). */
  private linksSupported: boolean | null = null;
  private loadSeq = 0;
  private readonly deps: Required<PlayerStoreDeps>;

  constructor(deps: PlayerStoreDeps = {}) {
    this.deps = {
      createAudio: deps.createAudio ?? (() => new Audio()),
      fetchLink: deps.fetchLink ?? fetchAudioLink,
      fetchBlob: deps.fetchBlob ?? fetchAudioBlob,
      now: deps.now ?? (() => Date.now()),
    };
  }

  /* ------------------------------------ store plumbing ------------------------------------ */

  subscribe = (fn: () => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };

  getSnapshot = () => this.state;

  private set(patch: Partial<PlayerState>) {
    this.state = { ...this.state, ...patch };
    for (const l of this.listeners) l();
  }

  private fail(message: string) {
    this.set({ loading: false, errorSeq: this.state.errorSeq + 1, lastError: message });
  }

  /* --------------------------------------- the element --------------------------------------- */

  private element(): AudioLike {
    if (this.audio) return this.audio;
    const a = this.deps.createAudio();
    a.preload = 'metadata';
    a.playbackRate = this.state.speed;
    a.addEventListener('loadedmetadata', () => {
      if (Number.isFinite(a.duration) && a.duration > 0) this.set({ duration: a.duration });
    });
    a.addEventListener('timeupdate', () =>
      this.set({ currentTime: a.currentTime || 0, buffered: this.bufferedEnd(a) }),
    );
    a.addEventListener('progress', () => this.set({ buffered: this.bufferedEnd(a) }));
    a.addEventListener('play', () => this.set({ playing: true, started: true }));
    a.addEventListener('pause', () => this.set({ playing: false }));
    a.addEventListener('ended', () => this.set({ playing: false }));
    a.addEventListener('waiting', () => this.set({ loading: true }));
    a.addEventListener('playing', () => this.set({ loading: false }));
    a.addEventListener('canplay', () => this.set({ loading: false }));
    a.addEventListener('error', () => void this.onError());
    this.audio = a;
    return a;
  }

  private bufferedEnd(a: AudioLike): number {
    const b = a.buffered;
    const t = a.currentTime || 0;
    let best = 0;
    for (let i = 0; i < b.length; i++) {
      const end = b.end(i);
      if (b.start(i) <= t + 0.5 && end >= t) return end;
      best = Math.max(best, end);
    }
    return best;
  }

  private async onError() {
    const seq = this.loadSeq;
    // A signed link that expired (or was rejected) gets one fresh link, then we give up.
    if (this.mode === 'link' && !this.retried && this.state.id) {
      this.retried = true;
      try {
        await this.refreshLink();
        return;
      } catch {
        /* fall through */
      }
      if (seq !== this.loadSeq) return; // another recording took over meanwhile: not its error
    }
    if (this.ready) this.fail("Couldn't play the audio.");
    else this.set({ loading: false });
  }

  /* ---------------------------------------- loading ---------------------------------------- */

  /**
   * Make `rec` the loaded recording (stops whatever was playing when it is a different one) and
   * fetch its link so the browser reads the duration without downloading the file.
   */
  load(rec: PlayerRecording, markers: number[] = []): void {
    if (this.state.id === rec.id) {
      this.set({
        title: rec.title,
        subtitle: rec.subtitle ?? '',
        markers,
        duration: this.state.duration || Number(rec.duration_s) || 0,
      });
      return;
    }
    this.reset();
    this.set({
      id: rec.id,
      title: rec.title,
      subtitle: rec.subtitle ?? '',
      duration: Number(rec.duration_s) || 0,
      markers,
    });
    void this.prepare(rec.id);
  }

  setMarkers(markers: number[]) {
    this.set({ markers });
  }

  private async prepare(id: string) {
    if (this.linksSupported === false) {
      this.mode = 'blob';
      return;
    }
    const seq = ++this.loadSeq;
    try {
      const link = await this.fetchLink(id);
      if (seq !== this.loadSeq || this.state.id !== id || this.ready) return;
      if (!link) {
        this.mode = 'blob';
        return;
      }
      this.useLink(link.url, link.expires_at);
    } catch (e) {
      if (seq !== this.loadSeq || this.state.id !== id) return; // superseded: leave the new load alone
      if (!(e instanceof ApiError && e.unauthorized)) this.mode = 'blob';
    }
  }

  /** null when the server has no signed links (404). */
  private async fetchLink(id: string): Promise<{ url: string; expires_at: number } | null> {
    try {
      const l = await this.deps.fetchLink(id);
      this.linksSupported = true;
      return l;
    } catch (e) {
      if (e instanceof ApiError && e.notFound) {
        this.linksSupported = false;
        return null;
      }
      throw e;
    }
  }

  private useLink(url: string, expiresAt: number) {
    const a = this.element();
    this.mode = 'link';
    this.expires = Number(expiresAt) || 0;
    a.preload = 'metadata';
    a.src = url;
    this.ready = true;
  }

  /** Have a playable source on the element; false when it could not be loaded. */
  private async ensureAudio(): Promise<boolean> {
    const id = this.state.id;
    if (!id) return false;
    const a = this.element();
    if (this.ready) {
      if (
        this.mode === 'link' &&
        this.expires &&
        this.expires * 1000 - this.deps.now() < LINK_REFRESH_MARGIN_MS
      ) {
        const before = this.loadSeq;
        try {
          await this.refreshLink();
        } catch {
          /* play with the current link; the error handler retries */
        }
        if (before !== this.loadSeq) return false; // reset or reloaded while refreshing
      }
      return true;
    }
    this.set({ loading: true });
    const seq = ++this.loadSeq;
    try {
      if (this.mode !== 'blob' && this.linksSupported !== false) {
        const l = await this.fetchLink(id);
        if (seq !== this.loadSeq || this.state.id !== id) return false;
        if (l) {
          this.useLink(l.url, l.expires_at);
          return true;
        }
      }
      const blob = await this.deps.fetchBlob(id);
      if (seq !== this.loadSeq || this.state.id !== id) return false;
      if (this.blobUrl) URL.revokeObjectURL(this.blobUrl);
      this.blobUrl = URL.createObjectURL(blob);
      this.mode = 'blob';
      a.src = this.blobUrl;
      this.ready = true;
      return true;
    } catch (e) {
      // A failure of a load that was superseded is not the current recording's failure.
      if (seq === this.loadSeq && this.state.id === id)
        this.fail(errorMessage(e, "Couldn't load the audio."));
      return false;
    } finally {
      if (seq === this.loadSeq) this.set({ loading: false });
    }
  }

  private async refreshLink() {
    const id = this.state.id;
    const a = this.element();
    if (!id) return;
    const t = a.currentTime;
    const wasPlaying = !a.paused;
    const seq = this.loadSeq;
    const l = await this.fetchLink(id);
    // Dropped if the recording changed, or was reset and reopened, while the request was out.
    if (!l || this.state.id !== id || seq !== this.loadSeq) return;
    this.expires = Number(l.expires_at) || 0;
    a.addEventListener(
      'loadedmetadata',
      this.whileCurrent(() => {
        a.currentTime = t;
        if (wasPlaying) a.play().catch(() => {});
      }),
      { once: true },
    );
    a.src = l.url;
  }

  /* --------------------------------------- transport --------------------------------------- */

  async play(): Promise<void> {
    const a = this.element();
    if (!(await this.ensureAudio())) return;
    a.playbackRate = this.state.speed;
    try {
      await a.play();
    } catch (e) {
      if ((e as { name?: string })?.name !== 'AbortError') this.fail("Couldn't play the audio.");
    }
  }

  pause(): void {
    this.audio?.pause();
  }

  toggle(): void {
    if (this.audio && !this.audio.paused) this.pause();
    else void this.play();
  }

  /** Move the playhead. Loads the audio first when needed; plays unless `autoplay` is false. */
  async seek(sec: number, { autoplay = true }: { autoplay?: boolean } = {}): Promise<void> {
    const a = this.element();
    if (!(await this.ensureAudio())) return;
    const target = Math.max(0, sec);
    const go = () => {
      a.currentTime = target;
      this.set({ currentTime: target });
      if (autoplay) {
        a.playbackRate = this.state.speed;
        a.play().catch(() => {});
      }
    };
    if (a.readyState >= 1) go();
    else {
      this.set({ currentTime: target });
      a.addEventListener('loadedmetadata', this.whileCurrent(go), { once: true });
    }
  }

  /**
   * Wrap a deferred callback so it is dropped if another recording (or source) was loaded in the
   * meantime: the audio element is shared, so a stale `loadedmetadata` listener must not seek or
   * play the recording that replaced the one it was meant for.
   */
  private whileCurrent(fn: () => void): () => void {
    const id = this.state.id;
    const seq = this.loadSeq;
    return () => {
      if (this.state.id === id && this.loadSeq === seq) fn();
    };
  }

  /** Live position while dragging the slider (no seek yet). */
  preview(sec: number) {
    this.set({ currentTime: Math.max(0, sec) });
  }

  skip(deltaSeconds: number): void {
    const a = this.audio;
    const cur = a && a.readyState >= 1 ? a.currentTime : this.state.currentTime;
    const max = this.state.duration || Infinity;
    void this.seek(Math.min(max, Math.max(0, cur + deltaSeconds)), { autoplay: !!a && !a.paused });
  }

  setSpeed(speed: Speed): void {
    storage.set(STORAGE_KEYS.speed, String(speed));
    if (this.audio) this.audio.playbackRate = speed;
    this.set({ speed });
  }

  /** Stop and forget the loaded recording (deleted, re-transcribed, or the mini player was closed). */
  reset(): void {
    this.loadSeq++;
    if (this.audio) {
      try {
        this.audio.pause();
      } catch {
        /* ignore */
      }
      this.audio.removeAttribute('src');
    }
    if (this.blobUrl) {
      URL.revokeObjectURL(this.blobUrl);
      this.blobUrl = null;
    }
    this.mode = null;
    this.expires = 0;
    this.ready = false;
    this.retried = false;
    this.set({
      id: null,
      title: '',
      subtitle: '',
      duration: 0,
      currentTime: 0,
      playing: false,
      started: false,
      loading: false,
      buffered: 0,
      markers: [],
      lastError: null,
    });
  }

  /** Forget the recording only if it is the loaded one. */
  resetIf(id: string) {
    if (this.state.id === id) this.reset();
  }
}

/** The app's one player. */
export const playerStore = new PlayerStore();
