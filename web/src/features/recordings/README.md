# Recordings feature (`src/features/recordings`)

Owner: recordings team. Entry: `RecordingsPage` (routes `#/` and `#/rec/:id`). The placeholder
in `RecordingsPage.tsx` shows the required frame: `SectionAppBar` (auto-hidden when embedded) plus
a scroll container with `pt-(--content-top-pad) pb-(--content-bottom-pad)`.

Reference behaviour: `app/static/index.html` on `main` (the vanilla dashboard). Everything it does
must keep working. Visual target: `/tmp/plaud-ux/design/material/mockup.html` and `shot-recordings-*`,
`shot-detail-*`, `shot-jumpto-*`, `shot-more-*`, `shot-empty-*`, `shot-loading-*`.

## What to build (from SPEC.md)

- **List** (`list/`): search (`SearchBar`, 250 ms debounce → `useRecordings({ q })`), filter chips
  (`Chip variant="filter"`: All ✓, Waiting, Transcribing, Failed, No speech, Not transcribed) in a
  horizontally scrolling row that fades at the edge, day groups (`fmtDayHeader`, sticky title-s
  headers), snippets (`match_snippet` with the hit `<mark>`ed), load more (`offset`), keyed updates
  (rows keyed by id so polling does not re-mount), keyboard navigation (arrow keys between rows,
  Enter opens). Row = `ListItem` with `Avatar` (waveform / group / silent / waiting / progress /
  failed), headline (title or filename), supporting (time · duration · preview, or a status word plus
  a short reason while in flight: "Your server will start on it shortly", "The transcript appears as
  soon as it is ready"), trailing bookmark count (`StatusChip tone="star"`) or time. Selected row uses
  `selected`. Phone rows carry a ⋮ `IconButton` that opens the More sheet.
- **Detail** (`detail/`): headline-m title (click to rename → `Dialog` with `TextField`), meta line
  (date · time · duration, `StatusChip tone="tag"` "2 speakers"), assist chips (Copy transcript,
  Export markdown, Download audio), then `Card`s: Summary (`Markdown`, `cleanSummary` port from the
  old dashboard), Highlights (star rows that seek), Transcript (find field in the heading, speaker
  label pills on speaker change using the spk1..4 tones keyed by ORIGINAL speaker id, rename on
  click → `useRenameSpeakers`, hover time + play pill, amber left bar + star on bookmarked
  paragraphs, `selection-tint` on the now-playing paragraph, no timestamps in the body), Automations
  card (last run, decision line, delivery rows, instructions `TextField` persisted via
  `routeInstructionsStore`, filled **Run again** → `useRunAutomations`, text **Preview** →
  `usePreviewAutomations`, Retry → `useRetryDelivery`), error card (`rec.error` sentence; raw
  `error_detail` only behind a disclosure), in-flight states (status words only). Loading:
  `LinearProgress` under the bar + `SkeletonText`.
- **Player** (`player/`): `fetchAudioLink` + `<audio src>` with Range streaming; on 404 fall back to
  `fetchAudioBlob`; on 403 (link expired) fetch a new link. 15 s back / 30 s forward, speed 1×/1.5×/2×
  persisted in `localStorage pb_speed` (`STORAGE_KEYS.speed`), `Slider` with bookmark markers,
  docked `Card tone="high" elevation={2}` at the bottom of the detail pane (24 px radius), phone:
  mini player (64 px above the bottom nav; `bottom: calc(var(--content-bottom-pad) + 8px)`) that
  opens `Popover as="sheet"` with the full controls. Jump to (`Popover`): Highlights first, then
  Speaker changes, each `MenuItem time=…`.
- **Actions**: More menu (`Popover` + `MenuItem`s): Copy transcript (`copyText`, reader layout
  "Speaker: paragraph" blocks, never timestamps), Export markdown (`fetchExportMarkdown` +
  `shareMarkdown`), Download audio, Rename, separator, Transcribe again… (`ConfirmDialog`),
  Delete… (`ConfirmDialog danger`). Copy/export text must be byte-identical to today's.
- **Desktop empty state**: `EmptyState` in the list + the three-step "Getting started" card in the
  detail pane. **Phone**: full-screen detail overlay with a Back button; Escape / Back closes it.
- **Deep links**: `#/rec/<id>` opens the recording; selecting a row on desktop replaces the hash,
  on phone pushes (Back returns to the list).

## Where things go

```
recordings/
  RecordingsPage.tsx      route component: layout (two-pane ≥ 840 px, single pane below)
  list/                   RecordingList, RecordingRow, FilterChips, DayHeader, useListState
  detail/                 RecordingDetail, SummaryCard, HighlightsCard, TranscriptCard, AutomationsCard
  player/                 usePlayer (audio element + link refresh), Player, MiniPlayer, JumpToMenu
  actions/                MoreMenu, RenameDialog, useRecordingActions (copy/export/download/delete)
  lib/                    summary.ts (cleanSummary, cleanTitle), transcriptText.ts (copy builders)
  *.test.tsx              MSW-backed tests (see src/test/msw.ts and src/test/fixtures.ts)
```

Hooks to use: `useRecordings`, `useRecording`, `useTranscript`, `useRecordingRouting`, and the
mutations in `@/api`. Do not call fetch directly. Show errors with `errorMessage(err, fallback)`
through `useSnackbar()`.
