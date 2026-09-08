import { describe, expect, it } from 'vitest';
import type { Delivery, Recording, Transcript } from '@/api';
import {
  recordingDone,
  recordingFailed,
  recordingPending,
  recordingSilent,
  recordingTranscribing,
  transcript,
} from '@/test/fixtures';
import { deliveryView, latestRun, previewText } from './lib/automations';
import { buildJumpSections } from './lib/jump';
import { inFlightHeading, statusWord } from './lib/status';
import { cleanSummary, cleanTitle, titleOf } from './lib/summary';
import {
  countMatches,
  paragraphAt,
  paragraphsOf,
  speakerChanges,
  speakerTones,
  transcriptPlainText,
} from './lib/transcript';
import { groupByDay } from './list/RecordingList';
import { stripSpeakerLabel } from './list/RecordingRow';

/* The old dashboard's transcriptPlainText, verbatim, as the oracle for the copy text. */
function oldTranscriptPlainText(t: {
  paragraphs?: { speaker?: string | null; text: string }[];
  text?: string;
}) {
  const paras = t?.paragraphs;
  if (paras && paras.length)
    return paras.map((p) => (p.speaker ? p.speaker + ': ' : '') + p.text).join('\n\n');
  return t?.text || '';
}

describe('summary helpers', () => {
  it('cleans titles and picks the title of a recording', () => {
    expect(cleanTitle('## **Title:** Standup notes')).toBe('Standup notes');
    expect(titleOf(recordingDone)).toBe(recordingDone.title);
    expect(titleOf({ ...recordingDone, title: null, no_speech: true })).toBe('Silent recording');
    expect(titleOf({ ...recordingDone, title: null, summary: '\n# Garage list\nbody' })).toBe('Garage list');
    expect(titleOf({ ...recordingDone, title: null, summary: null })).toBe(recordingDone.filename);
  });

  it('strips the leading Summary heading and "nothing to report" sections like the old dashboard', () => {
    const raw =
      '## Summary\n\nA short talk about data centers.\n\n## Action Items\n\n- No action items were requested.\n\n## Decisions\nNone.\n\n## Highlights\n- The polls moved from 51% to 75%.\n';
    expect(cleanSummary(raw)).toBe(
      'A short talk about data centers.\n\n## Highlights\n- The polls moved from 51% to 75%.',
    );
    expect(cleanSummary('**Title:** Foo\n\n**Summary**\n\nBody')).toBe('Body');
    expect(cleanSummary('')).toBe('');
  });
});

describe('transcript helpers', () => {
  it('builds the same copy text as the old dashboard', () => {
    expect(transcriptPlainText(transcript)).toBe(oldTranscriptPlainText(transcript));
    expect(transcriptPlainText(transcript)).toBe(
      'Speaker 1: Everyone, it appears, hates datacenters.\n\nSpeaker 2: Before we get into it, a quick word.',
    );
    const noParas: Transcript = { ...transcript, paragraphs: [], text: 'plain text' };
    expect(transcriptPlainText(noParas)).toBe('plain text');
    expect(transcriptPlainText(null)).toBe('');
  });

  it('falls back to grouping segments by speaker when a document has no paragraphs', () => {
    const t: Transcript = {
      ...transcript,
      paragraphs: [],
      segments: [
        { start: 0, end: 1, text: 'a', speaker: 'Speaker 1' },
        { start: 1, end: 2, text: 'b', speaker: 'Speaker 1' },
        { start: 2, end: 3, text: 'c', speaker: 'Speaker 2' },
      ],
    };
    expect(paragraphsOf(t).map((p) => `${p.speaker}:${p.text}`)).toEqual(['Speaker 1:a b', 'Speaker 2:c']);
  });

  it('keys speaker tones by the original label so a rename keeps the colour', () => {
    expect([...speakerTones(transcript)]).toEqual([
      ['Speaker 1', 1],
      ['Speaker 2', 2],
    ]);
    const renamed: Transcript = {
      ...transcript,
      speaker_names: { 'Speaker 2': 'Alex' },
      paragraphs: transcript.paragraphs.map((p) =>
        p.speaker === 'Speaker 2' ? { ...p, speaker: 'Alex' } : p,
      ),
    };
    expect(speakerTones(renamed).get('Alex')).toBe(2);
    // Swapped names: the tones follow the originals.
    const swapped: Transcript = {
      ...transcript,
      speaker_names: { 'Speaker 1': 'Speaker 2', 'Speaker 2': 'Speaker 1' },
      paragraphs: transcript.paragraphs.map((p) => ({
        ...p,
        speaker: p.speaker === 'Speaker 1' ? 'Speaker 2' : 'Speaker 1',
      })),
    };
    expect(speakerTones(swapped).get('Speaker 2')).toBe(1);
    expect(speakerTones(swapped).get('Speaker 1')).toBe(2);
  });

  it('finds speaker changes, matches and the paragraph at a time', () => {
    expect(speakerChanges(transcript.paragraphs)).toEqual([0, 1]);
    expect(countMatches('Data center, data center!', 'data center')).toBe(2);
    expect(countMatches('x', '')).toBe(0);
    expect(paragraphAt([0, 95], 50)).toBe(0);
    expect(paragraphAt([0, 95], 95)).toBe(1);
    expect(paragraphAt([10, 95], 5)).toBe(-1);
  });
});

describe('status words', () => {
  it('shows words only while in flight, failed, silent or untranscribed', () => {
    expect(statusWord(recordingPending)).toMatchObject({ label: 'Waiting', tone: 'inflight' });
    expect(statusWord(recordingTranscribing)).toMatchObject({ label: 'Transcribing 42%', pct: 42 });
    expect(statusWord({ ...recordingTranscribing, stage: 'diarizing' })).toMatchObject({
      label: 'Identifying speakers',
    });
    expect(statusWord({ ...recordingTranscribing, stage: 'summarizing', progress: 1 })).toMatchObject({
      label: 'Summarizing',
    });
    expect(statusWord(recordingFailed)).toMatchObject({ label: 'Failed', tone: 'failed' });
    expect(statusWord({ ...recordingDone, status: 'stored' })).toMatchObject({ label: 'Not transcribed' });
    expect(statusWord(recordingSilent)).toMatchObject({ label: 'No speech', tone: 'neutral' });
    expect(statusWord(recordingDone)).toBeNull();
    expect(inFlightHeading(recordingPending)).toBe('Waiting in the queue');
    expect(inFlightHeading(recordingTranscribing)).toBe('Transcribing 42%');
  });

  it('caps the percentage at 99 and drops the speaker label from previews', () => {
    expect(statusWord({ ...recordingTranscribing, progress: 0.999 })?.label).toBe('Transcribing 99%');
    expect(stripSpeakerLabel('Speaker 1: Hello there')).toBe('Hello there');
    expect(stripSpeakerLabel('Note: buy milk')).toBe('Note: buy milk');
  });
});

describe('day groups', () => {
  it('groups by day and keys a repeated day by occurrence', () => {
    const now = new Date('2026-09-08T20:00:00Z');
    const a: Recording = { ...recordingDone, id: 'a', started_at: '2026-09-08T10:00:00Z' };
    const b: Recording = { ...recordingDone, id: 'b', started_at: '2026-09-07T10:00:00Z' };
    const c: Recording = { ...recordingDone, id: 'c', started_at: '2026-09-08T09:00:00Z' };
    const entries = groupByDay([a, b, c], now);
    expect(entries.map((e) => (e.kind === 'day' ? `day:${e.label}` : e.rec.id))).toEqual([
      'day:Today',
      'a',
      'day:Yesterday',
      'b',
      'day:Today',
      'c',
    ]);
    const keys = entries.filter((e) => e.kind === 'day').map((e) => e.key);
    expect(new Set(keys).size).toBe(3);
  });
});

describe('automations helpers', () => {
  const base: Delivery = {
    id: 'd',
    recording_id: 'r',
    router_run_id: 'run',
    route_id: 'rt',
    route_name: 'Ask Claude',
    status: 'ok',
    attempts: 1,
    last_error: null,
    action_type: 'webhook',
    created_at: null,
    result_status: null,
    result_summary: null,
    result_at: null,
    payload_bytes: null,
  };

  it('shows the outcome alone and chips only while working or failed', () => {
    expect(deliveryView({ ...base, result_status: 'done', result_summary: 'Filed it.' })).toMatchObject({
      chip: null,
      outcome: 'Filed it.',
      note: '',
      retryable: false,
    });
    expect(deliveryView(base)).toMatchObject({ chip: null, note: 'Sent' });
    expect(deliveryView({ ...base, result_status: 'queued' })).toMatchObject({ chip: 'working' });
    expect(deliveryView({ ...base, status: 'pending' })).toMatchObject({ chip: 'working' });
    expect(deliveryView({ ...base, status: 'failed', attempts: 3, last_error: 'boom' })).toMatchObject({
      chip: 'failed',
      tries: 3,
      retryable: true,
      errorDetail: 'boom',
    });
    expect(deliveryView({ ...base, result_status: 'unknown' })).toMatchObject({
      note: 'No result came back',
      retryable: true,
    });
  });

  it('picks the latest run and its deliveries', () => {
    const r1 = {
      id: '1',
      recording_id: 'r',
      created_at: '2026-09-08T00:00:00Z',
      model: null,
      decision: null,
      error: null,
      idempotency_key: null,
      instructions: null,
      deliveries: [],
    };
    const r2 = { ...r1, id: '2', created_at: '2026-09-08T01:00:00Z', deliveries: [base] };
    expect(latestRun({ runs: [r1, r2], deliveries: [] }).last?.id).toBe('2');
    expect(latestRun({ runs: [r1], deliveries: [base] }).deliveries).toEqual([base]);
    expect(latestRun(undefined).last).toBeNull();
  });

  it('words the preview like the old dashboard', () => {
    expect(previewText({ route_name: 'A', reason: 'why', matches: [] })).toBe('Would run “A” — why');
    expect(
      previewText({
        matches: [
          { route_name: 'A', reason: 'why' },
          { route_name: 'B', reason: null },
        ],
      }),
    ).toBe('Would run “A” and “B” — why');
    expect(previewText({ matches: [], reason: 'nothing fits' })).toBe('Nothing would match — nothing fits');
    expect(previewText({ matches: [] })).toBe('Nothing would match');
  });
});

describe('jump to', () => {
  it('lists back to top, highlights, speaker changes and 10-minute marks', () => {
    const sections = buildJumpSections(recordingDone, transcript);
    expect(sections[0].items[0]).toMatchObject({ kind: 'top', label: 'Back to top' });
    expect(sections[1]).toMatchObject({ label: 'Highlights' });
    expect(sections[1].items[0]).toMatchObject({ kind: 'bookmark', time: '1:36', at: 95, paragraph: 1 });
    expect(sections[2]).toMatchObject({ label: 'Speaker changes' });
    expect(sections[2].items.map((i) => i.label)).toEqual(['Speaker 1', 'Speaker 2']);
    // 8386 s long with paragraphs at 0 and 95: the first 10-minute mark has no paragraph after it.
    expect(sections.find((s) => s.label === 'Every 10 minutes')).toBeUndefined();
    const long: Transcript = {
      ...transcript,
      paragraphs: [
        ...transcript.paragraphs,
        { speaker: 'Speaker 1', text: 'later on', start: 650, end: 700, bookmarks: [] },
        { speaker: 'Speaker 1', text: 'much later', start: 1300, end: 1400, bookmarks: [] },
      ],
    };
    const tens = buildJumpSections(recordingDone, long).find((s) => s.label === 'Every 10 minutes');
    expect(tens?.items.map((i) => ('time' in i ? i.time : ''))).toEqual(['10:00', '20:00']);
    expect(buildJumpSections(recordingDone, null)).toHaveLength(1);
  });
});
