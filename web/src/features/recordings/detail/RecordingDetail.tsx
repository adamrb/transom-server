import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { Card, IconButton, LinearProgress, TopAppBar, useSnackbar } from '@/components';
import {
  ApiError,
  errorMessage,
  useRecording,
  useRenameSpeakers,
  useTranscript,
  type Highlight,
  type Recording,
  type Transcript,
} from '@/api';
import { copyText } from '@/features/shell';
import { cn } from '@/lib/cn';
import { fmtWhen } from '@/lib/format';
import { RenameDialog } from '../actions/RenameDialog';
import { MoreMenu, type RecordingAction } from '../actions/MoreMenu';
import { buildJumpSections, type JumpItem } from '../lib/jump';
import { cleanSummary, titleOf } from '../lib/summary';
import { paragraphsOf, transcriptHasText } from '../lib/transcript';
import { JumpToMenu } from '../player/JumpToMenu';
import { Player } from '../player/Player';
import { usePlayerStore } from '../player/usePlayer';
import { AutomationsCard } from './AutomationsCard';
import { DetailHeader } from './DetailHeader';
import { DetailSkeleton } from './DetailSkeleton';
import { ErrorCard } from './ErrorCard';
import { HighlightsCard } from './HighlightsCard';
import { InFlightCard } from './InFlightCard';
import { SummaryCard } from './SummaryCard';
import { TranscriptCard } from './TranscriptCard';

export interface RecordingDetailProps {
  id: string;
  /** Phone (and embedded): the Back button. */
  onBack?: () => void;
  /** Runs an action from a chip or the More menu (dialogs live in the page). */
  onAction: (action: RecordingAction, rec: Recording, transcript: Transcript | null) => void;
  /** Phone: full-screen overlay; desktop: the right pane. */
  layout: 'pane' | 'screen';
  /** Embedded in the Android app: no bar background, room for the app's tab bar. */
  embedded?: boolean;
  className?: string;
}

const FLASH_MS = 250;

/**
 * One recording: small top bar (Back on phone, Jump to, More), the scrolling body (title, meta,
 * chips, in-flight / error, Summary, Highlights, Transcript, Automations) and the docked player.
 */
export function RecordingDetail({ id, onBack, onAction, layout, embedded, className }: RecordingDetailProps) {
  const snackbar = useSnackbar();
  const store = usePlayerStore();
  const recQ = useRecording(id);
  const rec = recQ.data;
  const transcriptQ = useTranscript(id, rec?.status === 'done');
  const transcript = rec?.status === 'done' ? (transcriptQ.data ?? null) : null;
  const renameSpeakers = useRenameSpeakers();

  const body = useRef<HTMLDivElement>(null);
  const [scrolled, setScrolled] = useState(false);
  const [flash, setFlash] = useState(-1);
  const [jumpOpen, setJumpOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [speaker, setSpeaker] = useState<string | null>(null);
  const speakersUnsupported = useRef(false);
  const jumpAnchor = useRef<HTMLButtonElement>(null);
  const jumpAnchorPlayer = useRef<HTMLButtonElement>(null);
  const [jumpFrom, setJumpFrom] = useState<'bar' | 'player'>('bar');
  const moreAnchor = useRef<HTMLButtonElement>(null);

  // A new recording: back to the top, and whatever else was playing stops at once (the player
  // controls for it are gone; the old dashboard reset audio on every change of recording).
  useEffect(() => {
    if (body.current) body.current.scrollTop = 0;
    setScrolled(false);
    const loaded = store.getSnapshot().id;
    if (loaded && loaded !== id) store.reset();
  }, [id, store]);

  // The player follows the open (finished) recording; markers are the bookmarks.
  const title = rec ? titleOf(rec) : '';
  const when = rec ? fmtWhen(rec.started_at || rec.uploaded_at) : '';
  const markers = useMemo(
    () => (transcript?.highlights.length ? transcript.highlights.map((h) => h.at) : (rec?.marks ?? [])),
    [transcript, rec?.marks],
  );
  const canPlay = rec?.status === 'done';
  useEffect(() => {
    if (!rec) return;
    if (canPlay) store.load({ id: rec.id, title, subtitle: when, duration_s: rec.duration_s }, markers);
    // A recording that cannot play (pending, failed, stored) shows no player: stop whatever was
    // playing, as the old dashboard did when the open recording changed.
    else store.reset();
  }, [store, rec, canPlay, title, when, markers]);

  const summary = useMemo(() => (rec?.summary ? cleanSummary(rec.summary) : ''), [rec?.summary]);
  const hasText = transcriptHasText(transcript);
  const paras = useMemo(() => paragraphsOf(transcript), [transcript]);
  const jumpSections = useMemo(() => buildJumpSections(rec, transcript), [rec, transcript]);

  const reveal = useCallback((index: number) => {
    if (index < 0) return;
    document.getElementById(`para-${index}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' });
    setFlash(index);
    setTimeout(() => setFlash(-1), FLASH_MS);
  }, []);
  const jumpToBookmark = useCallback(
    (index: number, h: Highlight) => {
      const para = document.getElementById(`bookmark-${index}`)?.closest<HTMLElement>('[data-paragraph]');
      reveal(para ? Number(para.dataset.paragraph) : -1);
      void store.seek(Number(h.start) || 0);
    },
    [reveal, store],
  );
  const onJump = (item: JumpItem) => {
    if (item.kind === 'top') body.current?.scrollTo?.({ top: 0, behavior: 'smooth' });
    else if (item.kind === 'bookmark' && transcript)
      jumpToBookmark(item.bookmark, transcript.highlights[item.bookmark]);
    else if (item.kind === 'paragraph') reveal(item.paragraph);
  };

  const copySummary = async () => {
    const r = await copyText(summary);
    if (r === 'copied') snackbar.show('Summary copied');
    else if (r === 'failed') snackbar.error('Copy failed');
  };

  const SPEAKERS_UNSUPPORTED = "Your server doesn't support renaming speakers yet.";
  const openRenameSpeaker = (name: string) => {
    if (speakersUnsupported.current) snackbar.error(SPEAKERS_UNSUPPORTED);
    else setSpeaker(name);
  };
  const onRenameSpeaker = (name: string) => {
    if (!rec) return;
    renameSpeakers.mutate(
      { id: rec.id, renames: { [speaker!]: name } },
      {
        onSuccess: () => {
          setSpeaker(null);
          snackbar.show(`Renamed to ${name}`);
        },
        onError: (e) => {
          if (e instanceof ApiError && e.notFound) {
            // An older server: remember it, close the dialog, say so once per attempt.
            speakersUnsupported.current = true;
            setSpeaker(null);
            snackbar.error(SPEAKERS_UNSUPPORTED);
          } else snackbar.error(errorMessage(e, "Couldn't rename the speaker."));
        },
      },
    );
  };

  const act = (a: RecordingAction) => rec && onAction(a, rec, transcript);
  const showPlayer = !!rec && canPlay;
  const screen = layout === 'screen';
  const vars = {
    // The phone overlay covers the bottom navigation, so nothing needs to clear it there.
    ...(screen && !embedded ? { '--content-bottom-pad': '0px' } : {}),
  } as CSSProperties;

  return (
    <div
      data-detail={id}
      style={vars}
      className={cn('relative flex min-h-0 flex-col bg-surface', screen && 'fixed inset-0 z-30', className)}
    >
      <TopAppBar
        variant="small"
        as="div"
        scrolled={scrolled}
        className={cn(embedded && 'bg-transparent')}
        leading={onBack && <IconButton icon="arrow_back" label="Back" onClick={onBack} />}
        title={scrolled ? title : ''}
        actions={
          rec && (
            <>
              {paras.length > 0 && (
                <IconButton
                  ref={jumpAnchor}
                  icon="format_list_bulleted"
                  label="Jump to"
                  aria-haspopup="menu"
                  aria-expanded={jumpOpen && jumpFrom === 'bar'}
                  onClick={() => {
                    setJumpFrom('bar');
                    setJumpOpen(true);
                  }}
                />
              )}
              <IconButton
                ref={moreAnchor}
                icon="more_vert"
                label="More actions"
                aria-haspopup="menu"
                aria-expanded={moreOpen}
                onClick={() => setMoreOpen(true)}
              />
            </>
          )
        }
      />
      {recQ.isPending && <LinearProgress label="Loading recording" className="mx-6 -mt-px" />}
      <div
        ref={body}
        onScroll={(e) => setScrolled(e.currentTarget.scrollTop > 40)}
        className={cn(
          'min-h-0 flex-1 overflow-y-auto px-8 [scrollbar-width:thin] max-md:px-4',
          showPlayer
            ? 'pb-[calc(var(--content-bottom-pad)+180px)]'
            : 'pb-[calc(var(--content-bottom-pad)+32px)]',
        )}
      >
        <div className="mx-auto flex max-w-[820px] flex-col gap-3.5">
          {recQ.isPending ? (
            <DetailSkeleton />
          ) : recQ.error ? (
            <Card className="mt-6" role="alert">
              <p className="m-0 text-body-m text-error">
                {recQ.error instanceof ApiError && recQ.error.notFound
                  ? 'This recording is no longer on your server.'
                  : errorMessage(recQ.error, "Couldn't load this recording.")}
              </p>
            </Card>
          ) : rec ? (
            <>
              <DetailHeader
                rec={rec}
                transcript={transcript}
                onRename={() => act('rename')}
                onCopy={() => act('copy')}
                onExport={() => act('export')}
                onDownload={() => act('download')}
              />
              {(rec.status === 'pending' || rec.status === 'transcribing') && <InFlightCard rec={rec} />}
              <ErrorCard rec={rec} />
              <SummaryCard summary={summary} onCopy={copySummary} />
              {transcript && <HighlightsCard highlights={transcript.highlights} onJump={jumpToBookmark} />}
              {(rec.status === 'done' || rec.status === 'stored') && (
                <TranscriptCard
                  rec={rec}
                  transcript={transcript}
                  loading={transcriptQ.isPending}
                  error={transcriptQ.error}
                  onRetry={() => void transcriptQ.refetch()}
                  flashIndex={flash}
                  onRenameSpeaker={openRenameSpeaker}
                />
              )}
              <AutomationsCard rec={rec} />
            </>
          ) : null}
        </div>
      </div>
      {showPlayer && (
        <div
          className={cn('absolute inset-x-6 z-[5] mx-auto max-w-[820px] max-md:inset-x-2')}
          style={{ bottom: `calc(var(--content-bottom-pad, 0px) + ${screen ? 8 : 16}px)` }}
        >
          <Player
            trailing={
              paras.length > 0 ? (
                <IconButton
                  ref={jumpAnchorPlayer}
                  icon="format_list_bulleted"
                  label="Jump to"
                  aria-haspopup="menu"
                  aria-expanded={jumpOpen && jumpFrom === 'player'}
                  onClick={() => {
                    setJumpFrom('player');
                    setJumpOpen(true);
                  }}
                />
              ) : undefined
            }
          />
        </div>
      )}
      <JumpToMenu
        open={jumpOpen}
        onClose={() => setJumpOpen(false)}
        anchorRef={jumpFrom === 'player' ? jumpAnchorPlayer : jumpAnchor}
        sections={jumpSections}
        onSelect={onJump}
      />
      <MoreMenu
        open={moreOpen}
        onClose={() => setMoreOpen(false)}
        anchorRef={moreAnchor}
        hasText={hasText}
        onAction={act}
      />
      <RenameDialog
        open={speaker !== null}
        title="Rename speaker"
        label={`New name for “${speaker ?? ''}”`}
        value={speaker ?? ''}
        maxLength={64}
        busy={renameSpeakers.isPending}
        onCancel={() => setSpeaker(null)}
        onSubmit={onRenameSpeaker}
      />
    </div>
  );
}
