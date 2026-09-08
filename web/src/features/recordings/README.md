# Recordings feature (`src/features/recordings`)

Entry: `RecordingsPage` (routes `#/` and `#/rec/:id`). Two panes from 840 px (list + detail, or
list + the getting-started card); on phone the list fills the screen and a recording opens as its
own route with a Back button (pushed from the list, so the device Back key returns; a deep link
replaces to the list instead). Embedded (`?embedded=1`): no section bar, the detail keeps its Back
button, content clears the app's tab bar via `--content-bottom-pad`.

Reference behaviour: `app/static/index.html` on `main` (the vanilla dashboard). Visual target:
`/tmp/plaud-ux/design/material/mockup.html`; screenshots of this build: `/tmp/plaud-ux/design/react-b1-*.png`.

## Layout

```
recordings/
  RecordingsPage.tsx        layout, navigation (open / back), Space = play/pause, Escape closes the
                            phone detail, row ⋮ menu, mini player + player sheet on phone
  list/
    ListPane.tsx            SectionAppBar + SearchBar (250 ms debounce) + FilterChips + RecordingList
    RecordingList.tsx       day groups (DayHeader), keyed rows, Load more, loading / empty / error,
                            arrow keys between rows (Enter/Space open via ListItem)
    RecordingRow.tsx        Avatar (waveform / silent / waiting ring / progress ring / failed),
                            title, status word + reason while in flight, time · duration · preview
                            (search hits <mark>ed), bookmark count, phone ⋮
    FilterChips.tsx         All ✓, Waiting, Transcribing, Failed, No speech, Not transcribed
    useListState.ts         search + filter in a module store (survives the phone route switch)
  detail/                   (loaded on demand: `RecordingsPage` lazy-imports RecordingDetail and shows
                            DetailSkeleton until the chunk arrives)
    RecordingDetail.tsx     small TopAppBar (Back, Jump to, More; title once scrolled), the cards,
                            the docked Player, JumpToMenu, MoreMenu, speaker RenameDialog
    DetailHeader.tsx        title (click → rename), when · duration · speakers · highlights (+ status
                            word while in flight), assist chips Copy / Export / Download
    InFlightCard.tsx        "Waiting in the queue" / "Transcribing 42%" / "Identifying speakers" /
                            "Summarizing" with LinearProgress (the detail polls every 5 s)
    ErrorCard.tsx           rec.error, raw error_detail behind Disclosure
    SummaryCard.tsx         Markdown of cleanSummary(), copy button
    HighlightsCard.tsx      ★ time + text rows; click reveals the paragraph and plays from the press
    TranscriptCard.tsx      paragraphs, find (Enter / Shift+Enter, "2 of 5"), now-playing marker
    TranscriptParagraph.tsx SpeakerPill on speaker change, time+play chip in a reserved right column
                            on desktop (hover to show; always shown where nothing can hover), floated
                            chip on phone, amber bar + star on bookmarked paragraphs, flash after a jump
    AutomationsCard.tsx     last run, decision, DeliveryRow (outcome alone; chips only Working /
                            Failed; Retry), RunAutomationsRow (instructions, Run / Run again, Preview).
                            Polling is the hook's: `useRecordingRouting(id, { catchUp })` looks every
                            15 s while a finished recording has no run yet or for 5 min after it
                            turned done (the automatic run starts a little after transcription)
  player/
    playerStore.ts          the audio element + state (signed link, blob fallback on 404, link refresh
                            on error / expiry, speed in pb_speed, skips, markers), usePlayer hooks
    Player.tsx              docked card / sheet body: `Slider` (buffered + markers), times, speed,
                            `IconButton` + shared `SkipIcon` for 15 s back / 30 s forward
    MiniPlayer.tsx, PlayerSheet.tsx, JumpToMenu.tsx
  actions/
    useRecordingActions.tsx copy (same text as before), export (shareMarkdown), download, rename,
                            transcribe again (ConfirmDialog), delete (danger ConfirmDialog)
    MoreMenu.tsx, RenameDialog.tsx
  lib/                      summary.ts (cleanSummary, cleanTitle, titleOf), transcript.ts
                            (paragraphsOf, transcriptPlainText, speakerTones, …), status.ts,
                            automations.ts (deliveryView, previewText, latestRun), jump.ts, Highlighted.tsx
  test/                     FakeAudio, renderRecordings (routes + a PlayerStore on the fake element)
  *.test.ts(x)              lib, list, detail (+ automations card), player store
```

## Rules kept from the old dashboard

- Copy text: `transcriptPlainText` = "Speaker: paragraph" blocks joined by blank lines, else the
  flat text. Export: the server's `export.md`, shared through the app bridge when embedded.
- Speaker tones (`spk1..4`) are keyed by the ORIGINAL engine label in first-appearance order
  (`speaker_names` maps original → current name), so a rename keeps the colour.
- Run automations: `useRunAutomations` sends the `Idempotency-Key` from sessionStorage; the
  instructions typed are saved beside it (`routeInstructionsStore`) and frozen while a key is
  pending, so a retry after a lost reply replays the same request. The hook clears both once the
  run settles (success or a definitive refusal).
- Status words only while in flight / failed / silent / untranscribed. No timestamps in the
  transcript body; the gutter pill and the bookmarks are the jump points.
- Newer-endpoint 404s degrade: no signed links → blob playback; no preview → the button goes;
  no automations → no card; no speaker rename → a sentence.

## Data hooks

`useRecordingPages` (infinite, `offset` pages of 50, polls 15 s / 5 s in flight), `useRecording`,
`useTranscript` (only once the recording is done), `useRecordingRouting`, and the mutations in
`@/api`. The player reads `fetchAudioLink` / `fetchAudioBlob` directly (injectable for tests).
