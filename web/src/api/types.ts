/**
 * Zod schemas and TypeScript types for every endpoint the dashboard uses. Shapes come from
 * app/main.py (`_public`, `_transcript_view`, `_route_public`, `_run_public`, `_delivery_public`).
 * Objects are loose (extra fields pass) so a newer server never breaks an older build; fields the
 * server may omit or null are `.nullish()`.
 */
import { z } from 'zod';

const str = z.string();
const nstr = z.string().nullish();
const nnum = z.number().nullish();

/* ------------------------------------ health / auth ------------------------------------ */

export const HealthSchema = z.looseObject({ status: str, service: nstr, version: nstr });
export type Health = z.infer<typeof HealthSchema>;

export const LoginRequestSchema = z.looseObject({
  id: str,
  expires_at: str,
  poll_seconds: z.number().default(2),
});
export type LoginRequest = z.infer<typeof LoginRequestSchema>;

export const LoginPollSchema = z.looseObject({
  status: z.enum(['pending', 'approved', 'expired']),
  token: nstr,
});
export type LoginPoll = z.infer<typeof LoginPollSchema>;

export const SessionSchema = z.looseObject({
  id: str,
  label: nstr,
  created_at: str,
  last_used_at: nstr,
  current: z.boolean().default(false),
});
export type Session = z.infer<typeof SessionSchema>;
export const SessionsSchema = z.looseObject({ sessions: z.array(SessionSchema) });

/* -------------------------------------- recordings -------------------------------------- */

/**
 * pending → transcribing → done | failed. `stored` = kept without transcription (transcription is
 * turned off or unavailable on the server); the UI calls it "Not transcribed".
 */
export const RecordingStatusSchema = z.enum(['pending', 'transcribing', 'done', 'failed', 'stored']);
export type RecordingStatus = z.infer<typeof RecordingStatusSchema>;

/** transcribing | diarizing | summarizing while transcribing; queued while pending. */
export const StageSchema = z.string().nullish();

export const RecordingSchema = z.looseObject({
  id: str,
  device_sn: nstr,
  session_id: nnum,
  filename: str,
  sha256: nstr,
  size_bytes: nnum,
  duration_s: nnum,
  started_at: nstr,
  source: nstr,
  uploaded_at: str,
  status: RecordingStatusSchema,
  attempts: nnum,
  title: nstr,
  summary: nstr,
  marks: z.array(z.number()).default([]),
  /** 0..1 while transcribing */
  progress: nnum,
  stage: StageSchema,
  /** A sentence for people ("Couldn't read the audio file."), or null. */
  error: nstr,
  /** The raw exception text; show only behind a disclosure, never in a row. */
  error_detail: nstr,
  has_transcript: z.boolean().default(false),
  /** Finished, but the audio held no speech. */
  no_speech: z.boolean().default(false),
  text_preview: nstr,
  /** Search: which field matched (title | summary | transcript) and a snippet around the hit. */
  match_field: nstr,
  match_snippet: nstr,
});
export type Recording = z.infer<typeof RecordingSchema>;
export const RecordingListSchema = z.looseObject({ recordings: z.array(RecordingSchema) });
export type RecordingList = z.infer<typeof RecordingListSchema>;

/** Server-side list filters: a status, or the virtual `no_speech` (finished, but silent). */
export type RecordingFilter = RecordingStatus | 'no_speech';

export interface RecordingListParams {
  limit?: number;
  offset?: number;
  /** pending | transcribing | done | failed | stored | no_speech (server filter) */
  status?: RecordingFilter | '';
  q?: string;
}

export const isInFlight = (r: Pick<Recording, 'status'>) =>
  r.status === 'pending' || r.status === 'transcribing';

export const StatsSchema = z.looseObject({
  recordings: z.number(),
  total_bytes: z.number().default(0),
  total_duration_s: z.number().default(0),
  by_status: z.record(z.string(), z.number()).default({}),
});
export type Stats = z.infer<typeof StatsSchema>;

export const AudioLinkSchema = z.looseObject({ url: str, expires_at: z.number() });
export type AudioLink = z.infer<typeof AudioLinkSchema>;

export const SegmentSchema = z.looseObject({
  start: nnum,
  end: nnum,
  text: z.string().default(''),
  speaker: nstr,
});
export type Segment = z.infer<typeof SegmentSchema>;

export const ParagraphSchema = z.looseObject({
  speaker: nstr,
  text: z.string().default(''),
  start: nnum,
  end: nnum,
  /** indexes into `highlights` */
  bookmarks: z.array(z.number()).default([]),
});
export type Paragraph = z.infer<typeof ParagraphSchema>;

export const HighlightSchema = z.looseObject({
  /** the button press, seconds from the start */
  at: z.number(),
  start: nnum,
  end: nnum,
  speakers: z.array(z.string()).default([]),
  text: z.string().default(''),
});
export type Highlight = z.infer<typeof HighlightSchema>;

export const TranscriptSchema = z.looseObject({
  text: z.string().default(''),
  segments: z.array(SegmentSchema).default([]),
  paragraphs: z.array(ParagraphSchema).default([]),
  highlights: z.array(HighlightSchema).default([]),
  /** distinct labels in first-appearance order */
  speakers: z.array(z.string()).default([]),
  /** original label → chosen name */
  speaker_names: z.record(z.string(), z.string()).default({}),
  no_speech: z.boolean().default(false),
  title: nstr,
  summary: nstr,
  duration_s: nnum,
  language: nstr,
  model: nstr,
  engine: nstr,
  marks: z.array(z.number()).nullish(),
});
export type Transcript = z.infer<typeof TranscriptSchema>;

export const RetranscribeSchema = z.looseObject({ id: str, status: RecordingStatusSchema });

/* -------------------------------------- automations -------------------------------------- */

export const ActionTypeSchema = z.enum(['webhook', 'markdown', 'none']);
export type ActionType = z.infer<typeof ActionTypeSchema>;

export const ActionConfigSchema = z.looseObject({
  url: nstr,
  /** "Name: value"; the server never echoes secrets back, treat as write-only */
  auth_header: nstr,
  folder: nstr,
});
export type ActionConfig = z.infer<typeof ActionConfigSchema>;

export const RouteSchema = z.looseObject({
  id: str,
  name: str,
  description: str,
  action_type: ActionTypeSchema,
  action_config: ActionConfigSchema.default({}),
  enabled: z.boolean(),
  created_at: nstr,
  updated_at: nstr,
});
export type Route = z.infer<typeof RouteSchema>;
export const RoutesSchema = z.looseObject({ routes: z.array(RouteSchema) });

/** Body for POST/PUT /routes. */
export interface RouteBody {
  name: string;
  description: string;
  action_type: ActionType;
  action_config: Record<string, unknown>;
  enabled: boolean;
}

export const RouterStatusSchema = z.looseObject({
  enabled: z.boolean(),
  configured: z.boolean(),
  /** internal model id: never show it, the status banner uses user words */
  model: nstr,
});
export type RouterStatus = z.infer<typeof RouterStatusSchema>;

export const DeliveryStatusSchema = z.enum(['pending', 'ok', 'failed']);
export const ResultStatusSchema = z.enum(['queued', 'done', 'failed', 'unknown']);

export const DeliverySchema = z.looseObject({
  id: str,
  recording_id: nstr,
  router_run_id: nstr,
  route_id: nstr,
  route_name: nstr,
  /** hand-off state */
  status: DeliveryStatusSchema.nullish(),
  attempts: nnum,
  last_error: nstr,
  action_type: ActionTypeSchema.nullish(),
  created_at: nstr,
  /** what the consumer reported: queued (working), done, failed, unknown (never reported) */
  result_status: ResultStatusSchema.nullish(),
  result_summary: nstr,
  result_at: nstr,
  payload_bytes: nnum,
});
export type Delivery = z.infer<typeof DeliverySchema>;

export const DecisionSchema = z.looseObject({
  routes: z.array(z.looseObject({ name: str, reason: nstr })).default([]),
  /** why nothing matched, when the assistant said */
  reason: nstr,
});
export type Decision = z.infer<typeof DecisionSchema>;

export const RouterRunSchema = z.looseObject({
  id: str,
  recording_id: nstr,
  created_at: nstr,
  model: nstr,
  decision: DecisionSchema.nullish(),
  error: nstr,
  idempotency_key: nstr,
  /** what the user typed for a re-run */
  instructions: nstr,
  deliveries: z.array(DeliverySchema).default([]),
});
export type RouterRun = z.infer<typeof RouterRunSchema>;

export const LogRunSchema = RouterRunSchema.extend({
  recording: z.looseObject({ id: str, title: nstr, filename: nstr, started_at: nstr }).nullish(),
  recording_title: nstr,
  recording_deleted: z.boolean().default(false),
  recorded_at: nstr,
});
export type LogRun = z.infer<typeof LogRunSchema>;
export const RoutingLogSchema = z.looseObject({ runs: z.array(LogRunSchema) });

export const RecordingRoutingSchema = z.looseObject({
  runs: z.array(RouterRunSchema),
  deliveries: z.array(DeliverySchema),
});
export type RecordingRouting = z.infer<typeof RecordingRoutingSchema>;

export const PreviewSchema = z.looseObject({
  route_id: nstr,
  route_name: nstr,
  reason: nstr,
  model: nstr,
  matches: z.array(z.looseObject({ route_id: nstr, route_name: nstr, reason: nstr })).default([]),
});
export type Preview = z.infer<typeof PreviewSchema>;

/* -------------------------------------- vocabulary -------------------------------------- */

export const VocabEntrySchema = z.looseObject({
  term: str,
  aliases: z.array(z.string()).default([]),
  source: z.enum(['manual', 'obsidian']).default('manual'),
  weight: z.number().nullish(),
});
export type VocabEntry = z.infer<typeof VocabEntrySchema>;

export const VocabularySchema = z.looseObject({
  entries: z.array(VocabEntrySchema),
  /** the editor's plain-text form: one term per line, `Term = alias, alias` */
  editor_text: z.string().default(''),
  hotwords: z.string().default(''),
});
export type Vocabulary = z.infer<typeof VocabularySchema>;
export const VocabularySaveSchema = z.looseObject({ entries: z.array(VocabEntrySchema) });
export const VocabularyImportSchema = z.looseObject({
  entries: z.array(VocabEntrySchema),
  added: z.number().default(0),
});

/* ----------------------------------------- APK ----------------------------------------- */

export const ApkInfoSchema = z.looseObject({
  version_code: z.number(),
  version_name: str,
  filename: str,
  sha256: str,
  size_bytes: z.number(),
  uploaded_at: str,
  min_sdk: nnum,
  notes: nstr,
});
export type ApkInfo = z.infer<typeof ApkInfoSchema>;

export interface ApkMetadata {
  version_code: number;
  version_name: string;
  min_sdk?: number | null;
  notes?: string | null;
}

/** 204 responses. */
export const EmptySchema = z.null();
