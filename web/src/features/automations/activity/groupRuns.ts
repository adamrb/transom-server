import type { LogRun } from '@/api/types';

export interface RunGroup {
  /** The recording these runs belong to (null when the server did not say). */
  recordingId: string | null;
  /** Newest first; `runs[0]` is the one the card shows, the rest sit behind "Earlier runs". */
  runs: LogRun[];
}

const time = (iso: string | null | undefined) => {
  const t = iso ? new Date(iso).getTime() : NaN;
  return Number.isNaN(t) ? 0 : t;
};

/**
 * Newest first; consecutive runs for the same recording collapse into one group so a recording
 * that was re-run three times takes one card, not three (exactly as the old dashboard did).
 */
export function groupRuns(runs: readonly LogRun[]): RunGroup[] {
  const sorted = [...runs].sort((a, b) => time(b.created_at) - time(a.created_at));
  const groups: RunGroup[] = [];
  for (const run of sorted) {
    const last = groups[groups.length - 1];
    const id = run.recording_id ?? null;
    if (last && last.recordingId && last.recordingId === id) last.runs.push(run);
    else groups.push({ recordingId: id, runs: [run] });
  }
  return groups;
}

/**
 * Never a hex id: the server's `recording_title`, then the embedded recording's title or file
 * name, "Deleted recording" when the recording is gone, else "Recording".
 */
export function runTitle(run: LogRun): string {
  if (run.recording_title) return run.recording_title;
  if (run.recording_deleted) return 'Deleted recording';
  if (run.recording?.title) return run.recording.title;
  if (run.recording?.filename) return run.recording.filename;
  if (run.recording === null && run.recording_id) return 'Deleted recording';
  return 'Recording';
}

export function runRecordedAt(run: LogRun): string | null {
  return run.recorded_at ?? run.recording?.started_at ?? null;
}

/** The card opens the recording only when it still exists. */
export function runCanOpen(run: LogRun): boolean {
  return !!run.recording_id && !run.recording_deleted && !!(run.recording_title || run.recording);
}
