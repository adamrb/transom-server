import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { TopAppBar } from '@/components';
import type { Recording } from '@/api';
import { useEmbedded } from '@/features/shell/EmbeddedProvider';
import { useIsDesktop } from '@/lib/breakpoints';
import { MoreMenu } from './actions/MoreMenu';
import { useRecordingActions } from './actions/useRecordingActions';
import { GettingStarted } from './detail/GettingStarted';
import { RecordingDetail } from './detail/RecordingDetail';
import { ListPane } from './list/ListPane';
import { MiniPlayer } from './player/MiniPlayer';
import { PlayerSheet } from './player/PlayerSheet';
import { usePlayerErrors, usePlayerSelector, usePlayerStore } from './player/usePlayer';

const recPath = (id: string) => `/rec/${encodeURIComponent(id)}`;

/** Space toggles playback unless the focus is somewhere that uses the key itself. */
function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  if (el.isContentEditable) return true;
  const tag = el.tagName;
  if (
    tag === 'INPUT' ||
    tag === 'TEXTAREA' ||
    tag === 'SELECT' ||
    tag === 'BUTTON' ||
    tag === 'A' ||
    tag === 'SUMMARY'
  )
    return true;
  const role = el.getAttribute('role');
  return (
    !!role && ['button', 'menuitem', 'checkbox', 'radio', 'slider', 'tab', 'switch', 'option'].includes(role)
  );
}

/**
 * Recordings: two panes from 840 px (list + detail or the getting-started card); on phone the list
 * fills the screen and a recording opens as its own route (`#/rec/:id`) with a Back button, while
 * the mini player keeps whatever is playing reachable above the bottom navigation.
 */
export function RecordingsPage() {
  const { id = null } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const desktop = useIsDesktop();
  const { embedded } = useEmbedded();
  const store = usePlayerStore();
  const loadedId = usePlayerSelector((s) => s.id);
  // The mini player appears once playback has started, not for every recording merely opened.
  const started = usePlayerSelector((s) => s.started);
  usePlayerErrors();

  // Nothing plays without its controls on screen: closing the desktop detail (back to the list
  // only) and leaving the Recordings section both stop playback.
  useEffect(() => {
    if (desktop && !id) store.reset();
  }, [desktop, id, store]);
  useEffect(() => () => store.reset(), [store]);

  const [sheetOpen, setSheetOpen] = useState(false);
  const [rowMenu, setRowMenu] = useState<{ rec: Recording; anchor: HTMLElement } | null>(null);
  const rowAnchor = useRef<HTMLElement | null>(null);

  const goBack = useCallback(() => {
    const fromList = !desktop && (location.state as { fromList?: boolean } | null)?.fromList;
    if (fromList) navigate(-1);
    else navigate('/', { replace: true });
  }, [desktop, location.state, navigate]);

  const open = useCallback(
    (recId: string) => {
      if (desktop) navigate(recPath(recId), { replace: true });
      else navigate(recPath(recId), { state: { fromList: true } });
    },
    [desktop, navigate],
  );

  const actions = useRecordingActions({
    onDeleted: (deleted) => {
      if (deleted === id) goBack();
    },
  });

  // Keyboard: Space toggles playback; Escape closes the phone detail (menus/dialogs handle their own).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;
      if (e.key === ' ' && !isTypingTarget(e.target)) {
        if (!store.getSnapshot().id) return;
        e.preventDefault();
        store.toggle();
      } else if (
        e.key === 'Escape' &&
        !desktop &&
        id &&
        !document.querySelector('dialog[open], [data-presentation]') // dialogs and menus close themselves
      ) {
        goBack();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [store, desktop, id, goBack]);

  const onMore = useCallback((rec: Recording, anchor: HTMLElement) => {
    rowAnchor.current = anchor;
    setRowMenu({ rec, anchor });
  }, []);
  const connectPhone = () => navigate('/settings');

  const showMini = !desktop && !id && !!loadedId && started;
  const list = (
    <ListPane
      selectedId={id}
      onOpen={open}
      onConnectPhone={connectPhone}
      onMore={desktop ? undefined : onMore}
      footer={showMini ? <div aria-hidden className="h-[80px]" /> : undefined}
      className="flex min-h-0 flex-1 flex-col"
    />
  );

  return (
    <>
      {desktop ? (
        <div className="grid h-full min-h-0 grid-cols-[340px_minmax(0,1fr)] lg:grid-cols-[400px_minmax(0,1fr)]">
          {list}
          {id ? (
            <RecordingDetail
              key={id}
              id={id}
              layout="pane"
              embedded={embedded}
              onBack={embedded ? goBack : undefined}
              onAction={actions.act}
            />
          ) : (
            <div className="flex min-h-0 flex-col">
              {!embedded && <TopAppBar variant="small" as="div" title="" />}
              <GettingStarted />
            </div>
          )}
        </div>
      ) : id ? (
        <RecordingDetail
          key={id}
          id={id}
          layout="screen"
          embedded={embedded}
          onBack={goBack}
          onAction={actions.act}
        />
      ) : (
        <>
          {list}
          {showMini && <MiniPlayer onOpen={() => setSheetOpen(true)} />}
          <PlayerSheet
            open={sheetOpen && showMini}
            onClose={() => setSheetOpen(false)}
            subtitle={<PlayerSubtitle />}
          />
        </>
      )}
      <MoreMenu
        open={!!rowMenu}
        onClose={() => setRowMenu(null)}
        anchorRef={rowAnchor}
        hasText={!!rowMenu && rowMenu.rec.has_transcript && !rowMenu.rec.no_speech}
        onAction={(a) => rowMenu && actions.act(a, rowMenu.rec)}
      />
      {actions.dialogs}
    </>
  );
}

function PlayerSubtitle() {
  const subtitle = usePlayerSelector((s) => s.subtitle);
  return <>{subtitle}</>;
}
