import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse, server } from '@/test/msw';
import * as fx from '@/test/fixtures';
import type { Transcript } from '@/api';
import { transcriptPlainText } from './lib/transcript';
import { renderRecordings } from './test/renderPage';

beforeEach(() => {
  vi.setSystemTime(new Date('2026-09-08T20:00:00Z'));
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

/** Three turns: Speaker 1, Speaker 2, Speaker 1 again (the second pill must not repeat). */
const threeTurns: Transcript = {
  ...fx.transcript,
  paragraphs: [
    ...fx.transcript.paragraphs,
    { speaker: 'Speaker 1', text: 'Back to the numbers.', start: 120, end: 130, bookmarks: [] },
  ],
};

describe('recording detail', () => {
  it('shows the in-flight state with progress and no transcript request', async () => {
    const transcriptCalls = vi.fn();
    server.use(
      http.get('/api/v1/recordings/:id/transcript', () => {
        transcriptCalls();
        return HttpResponse.json({ detail: 'not ready' }, { status: 409 });
      }),
    );
    renderRecordings({ route: '/rec/rec_transcribing' });
    expect(await screen.findByRole('heading', { name: 'Transcribing 42%' })).toBeInTheDocument();
    const card = screen.getByTestId('inflight-card');
    expect(within(card).getByText('The transcript appears here as soon as it is ready.')).toBeInTheDocument();
    expect(within(card).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '42');
    expect(screen.queryByRole('region', { name: 'Player' })).toBeNull();
    expect(transcriptCalls).not.toHaveBeenCalled();
  });

  it('shows "Waiting in the queue" for a pending recording and stops any playback', async () => {
    const { store, audio } = renderRecordings({ route: '/rec/rec_pending' });
    store.load({ id: 'other', title: 'Other', duration_s: 10 });
    expect(await screen.findByRole('heading', { name: 'Waiting in the queue' })).toBeInTheDocument();
    expect(screen.getByText('Your server will start on it shortly.')).toBeInTheDocument();
    await waitFor(() => expect(store.getSnapshot().id).toBeNull());
    expect(audio.src).toBe('');
  });

  it('shows the friendly error with the raw detail behind a disclosure', async () => {
    renderRecordings({ route: '/rec/rec_failed' });
    expect(await screen.findByRole('heading', { name: 'Something went wrong' })).toBeInTheDocument();
    expect(screen.getByText("Couldn't read the audio file.")).toBeInTheDocument();
    const details = screen.getByText('Details').closest('details')!;
    expect(details.open).toBe(false);
    expect(details).toHaveTextContent('ffmpeg: invalid data found when processing input');
  });

  it('strips the Summary heading and "no action items" filler from the summary', async () => {
    server.use(
      http.get('/api/v1/recordings/rec_done', () =>
        HttpResponse.json({
          ...fx.recordingDone,
          summary:
            '## Summary\n\nThe body of the summary.\n\n## Action Items\n\n- No action items were requested.',
        }),
      ),
    );
    renderRecordings({ route: '/rec/rec_done' });
    expect(await screen.findByText('The body of the summary.')).toBeInTheDocument();
    expect(screen.queryByText(/Action Items/)).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Summary', level: 4 })).toBeNull();
    expect(screen.getByRole('heading', { name: 'Summary', level: 3 })).toBeInTheDocument();
  });

  it('labels speakers only when they change, with a stable tone, and renames through PATCH', async () => {
    let renames: Record<string, string> | null = null;
    let current: Transcript = threeTurns; // the server keeps the renamed document
    server.use(
      http.get('/api/v1/recordings/:id/transcript', () => HttpResponse.json(current)),
      http.patch('/api/v1/recordings/:id/speakers', async ({ request }) => {
        renames = ((await request.json()) as { renames: Record<string, string> }).renames;
        const name = Object.values(renames)[0];
        current = {
          ...threeTurns,
          speaker_names: renames,
          speakers: ['Speaker 1', name],
          paragraphs: threeTurns.paragraphs.map((p) =>
            p.speaker === 'Speaker 2' ? { ...p, speaker: name } : p,
          ),
        };
        return HttpResponse.json(current);
      }),
    );
    renderRecordings({ route: '/rec/rec_done' });
    const pills = await screen.findAllByRole('button', { name: /^Rename speaker/ });
    // one pill per speaker change (three turns, three pills), never on a paragraph of the same speaker
    expect(pills.map((p) => p.textContent)).toEqual(['1Speaker 1', '2Speaker 2', '1Speaker 1']);
    expect(pills[1]).toHaveAttribute('data-tone', '2');
    expect(pills[2]).toHaveAttribute('data-tone', '1');
    // bookmarked paragraph: the star and the anchor for the highlight
    expect(document.getElementById('bookmark-0')).not.toBeNull();

    await userEvent.click(pills[1]);
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('heading', { name: 'Rename speaker' })).toBeInTheDocument();
    const input = within(dialog).getByLabelText('New name for “Speaker 2”');
    await userEvent.clear(input);
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(within(dialog).getByText('Type a name.')).toBeInTheDocument();
    await userEvent.type(input, '  Alex  ');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(renames).toEqual({ 'Speaker 2': 'Alex' }));
    const renamed = await screen.findByRole('button', { name: 'Rename speaker Alex' });
    expect(renamed).toHaveAttribute('data-tone', '2');
    expect(screen.getAllByRole('button', { name: /^Rename speaker/ })).toHaveLength(3);
    expect(await screen.findByText('Renamed to Alex')).toBeInTheDocument();
    expect(screen.getByText('2 speakers')).toBeInTheDocument();
  });

  it('closes the rename dialog and says so when the server cannot rename speakers', async () => {
    server.use(
      http.patch('/api/v1/recordings/:id/speakers', () =>
        HttpResponse.json({ detail: 'Not Found' }, { status: 404 }),
      ),
    );
    renderRecordings({ route: '/rec/rec_done' });
    await userEvent.click(await screen.findByRole('button', { name: 'Rename speaker Speaker 2' }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText(/New name for/), 'X');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(await screen.findByText("Your server doesn't support renaming speakers yet.")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    // the next click does not open the dialog again
    await userEvent.click(screen.getByRole('button', { name: 'Rename speaker Speaker 2' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('copies the transcript exactly as the old dashboard did', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    renderRecordings({ route: '/rec/rec_done' });
    await userEvent.click(await screen.findByRole('button', { name: 'Copy transcript' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(transcriptPlainText(fx.transcript)));
    expect(writeText.mock.calls[0][0]).toBe(
      'Speaker 1: Everyone, it appears, hates datacenters.\n\nSpeaker 2: Before we get into it, a quick word.',
    );
    expect(await screen.findByText('Transcript copied')).toBeInTheDocument();
  });

  it('exports markdown as a download with the server file name', async () => {
    const createObjectURL = vi.fn(() => 'blob:x');
    const revokeObjectURL = vi.fn();
    Object.assign(URL, { createObjectURL, revokeObjectURL });
    let name = '';
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      name = this.download;
    });
    renderRecordings({ route: '/rec/rec_done' });
    await userEvent.click(await screen.findByRole('button', { name: 'Export markdown' }));
    await waitFor(() => expect(name).toBe('title.md'));
    expect(await screen.findByText('Markdown exported')).toBeInTheDocument();
  });

  it('finds in the transcript and steps through the hits with Enter', async () => {
    renderRecordings({ route: '/rec/rec_done' });
    const find = await screen.findByRole('textbox', { name: 'Find in transcript' });
    await userEvent.type(find, 'it');
    await waitFor(() => expect(screen.getAllByText('it', { selector: 'mark' })).toHaveLength(2));
    expect(screen.getByText('1 of 2')).toBeInTheDocument();
    await userEvent.keyboard('{Enter}');
    expect(screen.getByText('2 of 2')).toBeInTheDocument();
    await userEvent.keyboard('{Shift>}{Enter}{/Shift}');
    expect(screen.getByText('1 of 2')).toBeInTheDocument();
    await userEvent.clear(find);
    await userEvent.type(find, 'zzz');
    expect(await screen.findByText('No matches')).toBeInTheDocument();
  });

  it('offers Jump to with back to top, highlights and speaker changes', async () => {
    renderRecordings({ route: '/rec/rec_done' });
    await screen.findByRole('heading', { level: 2, name: /Political Fight/ });
    await userEvent.click(screen.getAllByRole('button', { name: 'Jump to' })[0]);
    const menu = await screen.findByRole('dialog', { name: 'Jump to' }); // phone: a sheet
    expect(within(menu).getByRole('menuitem', { name: 'Back to top' })).toBeInTheDocument();
    expect(within(menu).getByText('Highlights')).toBeInTheDocument();
    expect(within(menu).getByRole('menuitem', { name: /1:36/ })).toHaveTextContent('Before we get into it');
    expect(within(menu).getByText('Speaker changes')).toBeInTheDocument();
    expect(within(menu).getByRole('menuitem', { name: /1:35/ })).toHaveTextContent('Speaker 2');
  });

  it('stops the previous recording as soon as another one opens', async () => {
    const { store } = renderRecordings({ route: '/rec/rec_done' });
    store.load({ id: 'other', title: 'Other', duration_s: 10 });
    expect(store.getSnapshot().id).toBe('other');
    await screen.findByRole('heading', { level: 2, name: /Political Fight/ });
    await waitFor(() => expect(store.getSnapshot().id).toBe('rec_done'));
  });

  it('tells when the transcript could not be fetched for copying', async () => {
    server.use(
      http.get('/api/v1/recordings/:id/transcript', () =>
        HttpResponse.json({ detail: 'The transcript file is missing on the server.' }, { status: 409 }),
      ),
    );
    renderRecordings();
    const row = await screen.findByRole('button', { name: /Political Fight/ });
    await userEvent.click(within(row).getByRole('button', { name: 'More' }));
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Copy transcript' }));
    expect(await screen.findByText('The transcript file is missing on the server.')).toBeInTheDocument();
    expect(screen.queryByText('No transcript to copy')).toBeNull();
  });

  it('shows the player for a finished recording and seeks from a paragraph time', async () => {
    const { audio } = renderRecordings({ route: '/rec/rec_done' });
    const player = await screen.findByRole('region', { name: 'Player' });
    await waitFor(() => expect(audio.src).toContain('/audio?sig='));
    expect(within(player).getByText('2:19:46')).toBeInTheDocument();
    audio.loaded(8386);
    await userEvent.click(screen.getByRole('button', { name: 'Play from 1:35' }));
    await waitFor(() => expect(audio.currentTime).toBe(95));
    expect(audio.paused).toBe(false);
    expect(within(player).getByRole('button', { name: 'Pause' })).toBeInTheDocument();
    // the now-playing paragraph is marked
    audio.tick(96);
    await waitFor(() =>
      expect(document.querySelector('[data-paragraph="1"]')).toHaveAttribute('data-now', 'true'),
    );
  });

  it('confirms delete, then leaves the recording and says so', async () => {
    const deleted = vi.fn();
    server.use(
      http.delete('/api/v1/recordings/:id', ({ params }) => {
        deleted(params.id);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderRecordings({ route: '/rec/rec_done' });
    await screen.findByRole('heading', { level: 2, name: /Political Fight/ });
    await userEvent.click(screen.getByRole('button', { name: 'More actions' }));
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Delete…' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('heading', { name: 'Delete this recording?' })).toBeInTheDocument();
    expect(dialog).toHaveTextContent('This cannot be undone.');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(deleted).toHaveBeenCalledWith('rec_done'));
    expect(await screen.findByText('Recording deleted')).toBeInTheDocument();
    // back on the list (phone)
    expect(await screen.findByRole('searchbox')).toBeInTheDocument();
  });

  it('confirms transcribing again and explains what it does', async () => {
    const posted = vi.fn();
    server.use(
      http.post('/api/v1/recordings/:id/retranscribe', ({ params }) => {
        posted(params.id);
        return HttpResponse.json({ id: params.id, status: 'pending' });
      }),
    );
    renderRecordings({ route: '/rec/rec_done' });
    await screen.findByRole('heading', { level: 2, name: /Political Fight/ });
    await userEvent.click(screen.getByRole('button', { name: 'More actions' }));
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Transcribe again…' }));
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveTextContent('The current transcript and summary will be thrown away');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Transcribe again' }));
    await waitFor(() => expect(posted).toHaveBeenCalledWith('rec_done'));
    expect(await screen.findByText('Transcribing again')).toBeInTheDocument();
  });

  it('renames the recording from the title', async () => {
    let title = '';
    server.use(
      http.patch('/api/v1/recordings/:id', async ({ request }) => {
        title = ((await request.json()) as { title: string }).title;
        return HttpResponse.json({ ...fx.recordingDone, title });
      }),
      // the refetch after the rename sees the new title, as the real server would return it
      http.get('/api/v1/recordings/rec_done', () =>
        HttpResponse.json({ ...fx.recordingDone, title: title || fx.recordingDone.title }),
      ),
    );
    renderRecordings({ route: '/rec/rec_done' });
    await userEvent.click(await screen.findByRole('button', { name: /Political Fight/ }));
    const dialog = await screen.findByRole('dialog');
    const input = within(dialog).getByLabelText('Title');
    await userEvent.clear(input);
    await userEvent.type(input, 'Data center politics{Enter}');
    await waitFor(() => expect(title).toBe('Data center politics'));
    expect(
      await screen.findByRole('heading', { level: 2, name: 'Data center politics' }),
    ).toBeInTheDocument();
    expect(await screen.findByText('Renamed')).toBeInTheDocument();
  });

  it('says when a recording is gone', async () => {
    renderRecordings({ route: '/rec/nope' });
    expect(await screen.findByText('This recording is no longer on your server.')).toBeInTheDocument();
  });
});

describe('automations card', () => {
  it('shows the last run, its decision and delivery outcome without a chip', async () => {
    renderRecordings({ route: '/rec/rec_done' });
    expect(await screen.findByText(/Last run/)).toBeInTheDocument();
    expect(screen.getByText('Ask Claude', { selector: 'b' })).toBeInTheDocument();
    expect(screen.getByText(/The speaker asks for a note\./)).toBeInTheDocument();
    const dlv = document.querySelector('[data-delivery="dlv_done"]')!;
    expect(dlv).toHaveTextContent('Filed the note.');
    expect(within(dlv as HTMLElement).queryByText(/Working|Failed/)).toBeNull();
    expect(screen.getByRole('button', { name: 'Run again' })).toBeInTheDocument();
  });

  it('shows Failed with Retry and retries the delivery', async () => {
    const retried = vi.fn();
    server.use(
      http.get('/api/v1/recordings/:id/routing', () =>
        HttpResponse.json({ runs: [{ ...fx.run, deliveries: [fx.deliveryFailed] }], deliveries: [] }),
      ),
      http.post('/api/v1/deliveries/:id/retry', ({ params }) => {
        retried(params.id);
        return HttpResponse.json({ ...fx.deliveryFailed, status: 'ok' });
      }),
    );
    renderRecordings({ route: '/rec/rec_done' });
    const dlv = (await screen.findByText('Failed')).closest('[data-delivery]') as HTMLElement;
    expect(dlv).toHaveTextContent('3 tries');
    expect(within(dlv).getByText('Details').closest('details')).toHaveTextContent("Couldn't reach the agent");
    await userEvent.click(within(dlv).getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(retried).toHaveBeenCalledWith('dlv_failed'));
    expect(await screen.findByText('Trying again')).toBeInTheDocument();
  });

  it('runs with an idempotency key kept across a lost reply, and persists the instructions', async () => {
    const keys: (string | null)[] = [];
    const bodies: unknown[] = [];
    let fail = true;
    server.use(
      http.post('/api/v1/recordings/:id/route', async ({ request }) => {
        keys.push(request.headers.get('Idempotency-Key'));
        bodies.push(await request.json());
        if (fail) return HttpResponse.json({ detail: 'nope' }, { status: 502 });
        return HttpResponse.json(fx.run);
      }),
    );
    // Instructions left over from a run that finished while the recording was closed are dropped.
    sessionStorage.setItem('pb.routeInstr.rec_done', 'stale instructions');
    renderRecordings({ route: '/rec/rec_done' });
    const box = await screen.findByRole('textbox', { name: 'Instructions' });
    expect(box).toHaveValue('');
    expect(sessionStorage.getItem('pb.routeInstr.rec_done')).toBeNull();
    await userEvent.type(box, 'file this as a work meeting');

    await userEvent.click(screen.getByRole('button', { name: 'Run again' }));
    expect(await screen.findByText(/a lost reply will not run them twice/)).toBeInTheDocument();
    expect(keys).toHaveLength(1);
    expect(keys[0]).toMatch(/^[A-Za-z0-9_-]{16,}$/);
    // The key and the instructions that went with it wait for the replay.
    expect(sessionStorage.getItem('pb.routeKey.rec_done')).toBe(keys[0]);
    expect(sessionStorage.getItem('pb.routeInstr.rec_done')).toBe('file this as a work meeting');
    // What is typed now must not change the request that will be replayed.
    await userEvent.type(box, ' and more');
    expect(sessionStorage.getItem('pb.routeInstr.rec_done')).toBe('file this as a work meeting');

    fail = false;
    await userEvent.click(screen.getByRole('button', { name: 'Run again' }));
    await waitFor(() => expect(keys).toHaveLength(2));
    expect(keys[1]).toBe(keys[0]);
    expect(bodies[1]).toEqual({ instructions: 'file this as a work meeting' });
    expect(await screen.findByText('Automations ran')).toBeInTheDocument();
    await waitFor(() => expect(sessionStorage.getItem('pb.routeKey.rec_done')).toBeNull());
    expect(sessionStorage.getItem('pb.routeInstr.rec_done')).toBeNull();
    expect(box).toHaveValue('');
  });

  it('previews what would run', async () => {
    renderRecordings({ route: '/rec/rec_done' });
    await userEvent.click(await screen.findByRole('button', { name: 'Preview' }));
    expect(await screen.findByTestId('automations-message')).toHaveTextContent(
      'Would run “Ask Claude” — A request.',
    );
  });

  it('hides the card when the server has no automations, and the run row on a silent recording', async () => {
    server.use(
      http.get('/api/v1/recordings/:id/routing', () => HttpResponse.json({ detail: 'no' }, { status: 404 })),
    );
    renderRecordings({ route: '/rec/rec_done' });
    await screen.findByRole('heading', { level: 2, name: /Political Fight/ });
    expect(screen.queryByRole('heading', { name: 'Automations' })).toBeNull();
  });

  it('refetches the runs once a recording opened while pending finishes transcribing', async () => {
    const routingCalls = vi.fn();
    server.use(
      http.get('/api/v1/recordings/:id/routing', () => {
        routingCalls();
        return HttpResponse.json({ runs: [], deliveries: [] });
      }),
    );
    const { queryClient } = renderRecordings({ route: '/rec/rec_pending' });
    expect(await screen.findByText('Automations run once the transcript is ready.')).toBeInTheDocument();
    expect(routingCalls).toHaveBeenCalledTimes(1);
    // the 5 s poll brings the finished recording
    queryClient.setQueryData(['recordings', 'detail', 'rec_pending'], {
      ...fx.recordingPending,
      status: 'done',
      has_transcript: true,
    });
    await waitFor(() => expect(routingCalls).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('Not run yet.')).toBeInTheDocument();
  });

  it('says nothing runs on a silent recording', async () => {
    server.use(
      http.get('/api/v1/recordings/:id/routing', () => HttpResponse.json({ runs: [], deliveries: [] })),
    );
    renderRecordings({ route: '/rec/rec_silent' });
    expect(await screen.findByText('Nothing to run on a silent recording.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Run/ })).toBeNull();
  });
});
