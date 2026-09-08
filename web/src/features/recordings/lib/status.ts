/**
 * Status words: only while something is happening (waiting, transcribing, identifying speakers,
 * summarizing), when it failed, and for silent / untranscribed recordings. Finished recordings
 * show nothing. Same words as the old dashboard.
 */
import type { Recording } from '@/api';
import type { StatusTone as ChipTone } from '@/components';

export interface StatusWord {
  label: string;
  tone: ChipTone;
  /** 0..99 while transcribing with a known progress. */
  pct: number | null;
}

const STAGE: Record<string, string> = {
  transcribing: 'Transcribing',
  diarizing: 'Identifying speakers',
  summarizing: 'Summarizing',
};

/** Percentage shown while transcribing (capped at 99: the last percent is the summary). */
export function progressPct(rec: Pick<Recording, 'progress' | 'stage'>): number | null {
  return typeof rec.progress === 'number' && rec.stage === 'transcribing'
    ? Math.min(99, Math.floor(rec.progress * 100))
    : null;
}

export function stageLabel(rec: Pick<Recording, 'status' | 'stage'>): string {
  return STAGE[rec.stage ?? ''] ?? 'Transcribing';
}

/** The chip for a list row / header, or null for a finished recording. */
export function statusWord(
  rec: Pick<Recording, 'status' | 'stage' | 'progress' | 'no_speech'>,
): StatusWord | null {
  if (rec.status === 'transcribing') {
    const pct = progressPct(rec);
    return { label: `${stageLabel(rec)}${pct != null ? ` ${pct}%` : ''}`, tone: 'inflight', pct };
  }
  if (rec.status === 'pending') return { label: 'Waiting', tone: 'inflight', pct: null };
  if (rec.status === 'failed') return { label: 'Failed', tone: 'failed', pct: null };
  if (rec.status === 'stored') return { label: 'Not transcribed', tone: 'neutral', pct: null };
  if (rec.no_speech) return { label: 'No speech', tone: 'neutral', pct: null };
  return null;
}

/** The short reason under an in-flight status word. */
export function inFlightReason(rec: Pick<Recording, 'status'>): string {
  return rec.status === 'pending'
    ? 'Your server will start on it shortly.'
    : 'The transcript appears here as soon as it is ready.';
}

/** The in-flight card heading: "Waiting in the queue", "Transcribing 42%", "Identifying speakers"… */
export function inFlightHeading(rec: Pick<Recording, 'status' | 'stage' | 'progress'>): string {
  if (rec.status === 'pending') return 'Waiting in the queue';
  const pct = progressPct(rec);
  return `${stageLabel(rec)}${pct != null ? ` ${pct}%` : ''}`;
}
