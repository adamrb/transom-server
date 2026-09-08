/**
 * Sample API payloads matching app/main.py shapes. Reuse in feature tests; extend as needed.
 */
import type {
  ApkInfo,
  Delivery,
  LogRun,
  Recording,
  Route,
  RouterRun,
  Session,
  Stats,
  Transcript,
  Vocabulary,
} from '@/api/types';

export const recordingDone: Recording = {
  id: 'rec_done',
  device_sn: 'PL123',
  session_id: 41,
  filename: 'rec_41.mp3',
  sha256: 'a'.repeat(64),
  size_bytes: 4_200_000,
  duration_s: 8386,
  started_at: '2026-09-08T00:25:00Z',
  source: 'plaud',
  uploaded_at: '2026-09-08T00:26:00Z',
  status: 'done',
  attempts: 1,
  title: 'The Political Fight Over AI Data Centers',
  summary: 'A podcast episode about data center politics.',
  marks: [96, 2855],
  progress: null,
  stage: null,
  error: null,
  error_detail: null,
  has_transcript: true,
  no_speech: false,
  text_preview: 'Everyone, it appears, hates datacenters.',
  match_field: null,
  match_snippet: null,
};

export const recordingPending: Recording = {
  ...recordingDone,
  id: 'rec_pending',
  filename: 'rec_42.mp3',
  status: 'pending',
  title: null,
  summary: null,
  marks: [],
  stage: 'queued',
  has_transcript: false,
  text_preview: null,
  duration_s: 72,
};

export const recordingTranscribing: Recording = {
  ...recordingPending,
  id: 'rec_transcribing',
  status: 'transcribing',
  stage: 'transcribing',
  progress: 0.42,
};

export const recordingFailed: Recording = {
  ...recordingPending,
  id: 'rec_failed',
  status: 'failed',
  stage: null,
  error: "Couldn't read the audio file.",
  error_detail: 'ffmpeg: invalid data found when processing input',
};

export const recordingSilent: Recording = {
  ...recordingDone,
  id: 'rec_silent',
  title: 'Silent recording',
  summary: null,
  marks: [],
  no_speech: true,
  text_preview: null,
  duration_s: 4,
};

export const transcript: Transcript = {
  text: 'Speaker 1: Everyone, it appears, hates datacenters.\n\nSpeaker 2: Before we get into it, a quick word.',
  segments: [
    { start: 0, end: 5.2, text: 'Everyone, it appears, hates datacenters.', speaker: 'Speaker 1' },
    { start: 95, end: 99, text: 'Before we get into it, a quick word.', speaker: 'Speaker 2' },
  ],
  paragraphs: [
    {
      speaker: 'Speaker 1',
      text: 'Everyone, it appears, hates datacenters.',
      start: 0,
      end: 5.2,
      bookmarks: [],
    },
    {
      speaker: 'Speaker 2',
      text: 'Before we get into it, a quick word.',
      start: 95,
      end: 99,
      bookmarks: [0],
    },
  ],
  highlights: [
    { at: 96, start: 95, end: 99, speakers: ['Speaker 2'], text: 'Before we get into it, a quick word.' },
  ],
  speakers: ['Speaker 1', 'Speaker 2'],
  speaker_names: {},
  no_speech: false,
  title: recordingDone.title,
  summary: recordingDone.summary,
  duration_s: 8386,
  language: 'en',
  model: 'large-v3',
  engine: 'faster-whisper',
  marks: [96, 2855],
};

export const stats: Stats = {
  recordings: 5,
  total_bytes: 21_000_000,
  total_duration_s: 8462,
  by_status: { done: 3, pending: 1, failed: 1 },
};

export const routeAgent: Route = {
  id: 'route_agent',
  name: 'Ask Claude',
  description: 'Anything addressed to the assistant.',
  action_type: 'webhook',
  action_config: { url: 'https://agent.example/hook', auth_header: null, folder: null },
  enabled: true,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
};

export const routeNotes: Route = {
  ...routeAgent,
  id: 'route_notes',
  name: 'Vault notes',
  description: 'Thoughts and ideas worth keeping.',
  action_type: 'markdown',
  action_config: { url: null, auth_header: null, folder: 'Inbox' },
  enabled: false,
};

export const deliveryDone: Delivery = {
  id: 'dlv_done',
  recording_id: recordingDone.id,
  router_run_id: 'run_1',
  route_id: routeAgent.id,
  route_name: routeAgent.name,
  status: 'ok',
  attempts: 1,
  last_error: null,
  action_type: 'webhook',
  created_at: '2026-09-08T00:30:00Z',
  result_status: 'done',
  result_summary: 'Filed the note.',
  result_at: '2026-09-08T00:31:00Z',
  payload_bytes: 1200,
};

export const deliveryFailed: Delivery = {
  ...deliveryDone,
  id: 'dlv_failed',
  status: 'failed',
  attempts: 3,
  last_error: "Couldn't reach the agent (timed out after 30 s)",
  result_status: null,
  result_summary: null,
  result_at: null,
};

export const run: RouterRun = {
  id: 'run_1',
  recording_id: recordingDone.id,
  created_at: '2026-09-08T00:30:00Z',
  model: 'some-model',
  decision: { routes: [{ name: routeAgent.name, reason: 'The speaker asks for a note.' }] },
  error: null,
  idempotency_key: null,
  instructions: null,
  deliveries: [deliveryDone],
};

export const logRun: LogRun = {
  ...run,
  recording: {
    id: recordingDone.id,
    title: recordingDone.title,
    filename: recordingDone.filename,
    started_at: recordingDone.started_at,
  },
  recording_title: recordingDone.title,
  recording_deleted: false,
  recorded_at: recordingDone.started_at,
};

export const vocabulary: Vocabulary = {
  entries: [
    { term: 'Plaud Bridge', aliases: ['Plogged Bridge', 'Plod Bridge'], source: 'manual', weight: 0 },
    { term: 'Obsidian', aliases: [], source: 'manual', weight: 0 },
  ],
  editor_text: 'Plaud Bridge = Plogged Bridge, Plod Bridge\nObsidian',
  hotwords: 'Plaud Bridge, Obsidian',
};

export const sessionCurrent: Session = {
  id: 'sess_1',
  label: 'Chrome on Linux',
  created_at: '2026-09-08T15:48:00Z',
  last_used_at: '2026-09-08T17:52:00Z',
  current: true,
};

export const apkInfo: ApkInfo = {
  version_code: 15,
  version_name: '0.5.0',
  filename: '15-app.apk',
  sha256: 'b'.repeat(64),
  size_bytes: 21_800_000,
  uploaded_at: '2026-09-08T17:37:00Z',
  min_sdk: 26,
  notes: 'UX overhaul.',
};
