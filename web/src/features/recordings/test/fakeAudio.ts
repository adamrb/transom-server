/**
 * A stand-in for HTMLAudioElement: jsdom's media element cannot play. Tests fire events with
 * `emit` and inspect `src`, `currentTime`, `paused`, `playbackRate`.
 */
import type { AudioLike } from '../player/playerStore';

export class FakeAudio extends EventTarget implements AudioLike {
  src = '';
  preload = 'none';
  currentTime = 0;
  duration = NaN;
  paused = true;
  playbackRate = 1;
  readyState = 0;
  buffered = { length: 0, start: () => 0, end: () => 0 };
  played: number[] = [];

  async play() {
    this.paused = false;
    this.played.push(this.currentTime);
    this.dispatchEvent(new Event('play'));
  }
  pause() {
    this.paused = true;
    this.dispatchEvent(new Event('pause'));
  }
  removeAttribute(name: string) {
    if (name === 'src') this.src = '';
  }
  /** Simulate the browser reading the metadata. */
  loaded(duration: number) {
    this.duration = duration;
    this.readyState = 1;
    this.dispatchEvent(new Event('loadedmetadata'));
  }
  tick(time: number) {
    this.currentTime = time;
    this.dispatchEvent(new Event('timeupdate'));
  }
  emit(name: string) {
    this.dispatchEvent(new Event(name));
  }
}
