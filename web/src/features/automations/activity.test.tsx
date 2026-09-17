import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes, useLocation } from 'react-router-dom';
import { renderWithProviders } from '@/test/render';
import { http, HttpResponse, server } from '@/test/msw';
import * as fx from '@/test/fixtures';
import type { LogRun } from '@/api';
import { ActivityCard } from './activity/ActivityCard';
import { ActivitySection } from './activity/ActivitySection';
import { OutcomeLine, deliveryState } from './activity/OutcomeLine';
import { groupRuns, runCanOpen, runTitle } from './activity/groupRuns';

const runAt = (id: string, created_at: string, extra: Partial<LogRun> = {}): LogRun => ({
  ...fx.logRun,
  id,
  created_at,
  ...extra,
});

const deletedRun: LogRun = runAt('run_deleted', '2026-09-07T10:00:00Z', {
  recording_id: 'rec_gone',
  recording: null,
  recording_title: null,
  recording_deleted: true,
  recorded_at: null,
  deliveries: [],
});

describe('groupRuns', () => {
  it('sorts newest first and groups consecutive runs of the same recording', () => {
    const a1 = runAt('a1', '2026-09-08T01:00:00Z');
    const a2 = runAt('a2', '2026-09-08T03:00:00Z');
    const a3 = runAt('a3', '2026-09-08T02:00:00Z');
    const other = runAt('b1', '2026-09-07T23:00:00Z', { recording_id: 'rec_other' });
    const old = runAt('a0', '2026-09-07T20:00:00Z');
    const groups = groupRuns([a1, other, a2, old, a3]);
    expect(groups.map((g) => g.runs.map((r) => r.id))).toEqual([['a2', 'a3', 'a1'], ['b1'], ['a0']]);
    expect(groups[0].recordingId).toBe(fx.recordingDone.id);
  });

  it('never groups runs without a recording id', () => {
    const x = runAt('x', '2026-09-08T01:00:00Z', { recording_id: null });
    const y = runAt('y', '2026-09-08T00:00:00Z', { recording_id: null });
    expect(groupRuns([x, y])).toHaveLength(2);
  });

  it('titles a run by the recording title, and "Deleted recording" when it is gone', () => {
    expect(runTitle(fx.logRun)).toBe(fx.recordingDone.title);
    expect(runTitle(deletedRun)).toBe('Deleted recording');
    expect(
      runTitle({ ...fx.logRun, recording_title: null, recording: { ...fx.logRun.recording!, title: null } }),
    ).toBe(fx.recordingDone.filename);
    expect(runTitle({ ...fx.logRun, recording_title: null, recording: undefined, recording_id: null })).toBe(
      'Recording',
    );
    expect(runCanOpen(fx.logRun)).toBe(true);
    expect(runCanOpen(deletedRun)).toBe(false);
  });
});

describe('deliveryState', () => {
  it('shows chips only while working or when failed', () => {
    expect(deliveryState(fx.deliveryDone)).toMatchObject({
      failed: false,
      working: false,
      outcome: 'Filed the note.',
      note: null,
      retryable: false,
    });
    expect(deliveryState(fx.deliveryFailed)).toMatchObject({ failed: true, working: false, retryable: true });
    expect(deliveryState({ ...fx.deliveryDone, status: 'pending', result_status: 'queued' })).toMatchObject({
      working: true,
      retryable: false,
    });
    expect(
      deliveryState({ ...fx.deliveryDone, status: 'ok', result_status: 'unknown', result_summary: null }),
    ).toMatchObject({ note: 'No result came back', retryable: true });
    expect(
      deliveryState({ ...fx.deliveryDone, status: 'ok', result_status: null, result_summary: null }),
    ).toMatchObject({ note: 'Sent' });
  });
});

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="location">{loc.pathname}</div>;
}

const renderCard = (runs: LogRun[], onOpen = vi.fn()) => {
  const utils = renderWithProviders(
    <>
      <ActivityCard group={{ recordingId: runs[0].recording_id ?? null, runs }} onOpen={onOpen} />
      <LocationProbe />
    </>,
    { route: '/automations' },
  );
  return { ...utils, onOpen };
};

describe('ActivityCard', () => {
  it('shows the title, times, the matched rule with its reason behind Why?, and the outcome alone', async () => {
    renderCard([fx.logRun]);
    const card = screen.getByRole('listitem', { name: fx.recordingDone.title! });
    expect(card).toHaveTextContent('Recorded');
    expect(card).toHaveTextContent('Ask Claude');
    expect(card).not.toHaveTextContent('The speaker asks for a note.');
    await userEvent.click(within(card).getByRole('button', { name: 'Why?' }));
    expect(card).toHaveTextContent('The speaker asks for a note.');
    expect(card).toHaveTextContent('Filed the note.');
    expect(within(card).queryByText('Failed')).not.toBeInTheDocument();
    expect(within(card).queryByText('Working')).not.toBeInTheDocument();
    expect(within(card).queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
    expect(card).not.toHaveTextContent('some-model');
  });

  it('opens the recording when clicked, but not from its controls', async () => {
    const { onOpen } = renderCard([fx.logRun]);
    const card = screen.getByRole('listitem', { name: fx.recordingDone.title! });
    await userEvent.click(within(card).getByRole('button', { name: 'Why?' }));
    expect(onOpen).not.toHaveBeenCalled();
    await userEvent.click(within(card).getByText('Filed the note.'));
    expect(onOpen).toHaveBeenCalledWith(fx.recordingDone.id);
    await userEvent.click(within(card).getByRole('button', { name: fx.recordingDone.title! }));
    expect(onOpen).toHaveBeenCalledTimes(2);
  });

  it('names a deleted recording and does not open it', async () => {
    const { onOpen } = renderCard([deletedRun]);
    const card = screen.getByRole('listitem', { name: 'Deleted recording' });
    expect(within(card).queryByRole('button', { name: 'Deleted recording' })).not.toBeInTheDocument();
    await userEvent.click(card);
    expect(onOpen).not.toHaveBeenCalled();
    expect(card).not.toHaveTextContent('rec_gone');
  });

  it('tucks repeat runs behind "Earlier runs" and shows the note you typed', async () => {
    const latest = runAt('r3', '2026-09-08T03:00:00Z', { instructions: 'file this as a work meeting' });
    const earlier = [
      runAt('r2', '2026-09-08T02:00:00Z', { decision: { routes: [] }, deliveries: [] }),
      runAt('r1', '2026-09-08T01:00:00Z'),
    ];
    renderCard([latest, ...earlier]);
    const card = screen.getByRole('listitem', { name: fx.recordingDone.title! });
    expect(card).toHaveTextContent('3 runs');
    expect(card).toHaveTextContent('Your note: “file this as a work meeting”');
    const summary = within(card).getByText('Earlier runs (2)');
    expect(summary.closest('details')).not.toHaveAttribute('open');
    await userEvent.click(summary);
    expect(summary.closest('details')).toHaveAttribute('open');
    expect(card).toHaveTextContent('Nothing matched');
  });

  it('shows Failed with the tries and a Retry that reports back', async () => {
    let retried: string | null = null;
    server.use(
      http.post('/api/v1/deliveries/:id/retry', ({ params }) => {
        retried = String(params.id);
        return HttpResponse.json({ ...fx.deliveryFailed, status: 'pending', attempts: 4 });
      }),
    );
    renderWithProviders(<OutcomeLine delivery={fx.deliveryFailed} />);
    expect(screen.getByText('Failed')).toBeInTheDocument();
    expect(screen.getByText('3 tries')).toBeInTheDocument();
    expect(screen.getByText('Couldn’t hand this off.')).toBeInTheDocument();
    // the raw error only behind Details
    expect(screen.getByText('Details').closest('details')).not.toHaveAttribute('open');
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await screen.findByText('Trying again');
    expect(retried).toBe(fx.deliveryFailed.id);
  });

  it('shows Working while the agent has the job', () => {
    renderWithProviders(
      <OutcomeLine
        delivery={{ ...fx.deliveryDone, status: 'pending', result_status: 'queued', result_summary: null }}
      />,
    );
    expect(screen.getByText('Working')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
  });
});

describe('ActivitySection', () => {
  it('navigates to the recording from a card', async () => {
    renderWithProviders(
      <Routes>
        <Route
          path="/automations"
          element={
            <>
              <ActivitySection />
              <LocationProbe />
            </>
          }
        />
        <Route path="/rec/:id" element={<LocationProbe />} />
      </Routes>,
      { route: '/automations' },
    );
    const title = await screen.findByRole('button', { name: fx.recordingDone.title! });
    await userEvent.click(title);
    expect(screen.getByTestId('location')).toHaveTextContent(`/rec/${fx.recordingDone.id}`);
  });

  it('puts cards under day headings', async () => {
    const now = new Date();
    const today = new Date(now.getTime() - 60_000).toISOString();
    // Noon local time yesterday: "now minus 26 hours" lands two calendar days back when the
    // test runs in the first hours after local midnight.
    const y = new Date(now);
    y.setDate(y.getDate() - 1);
    y.setHours(12, 0, 0, 0);
    const yesterday = y.toISOString();
    const older = '2025-12-24T10:00:00Z';
    server.use(
      http.get('/api/v1/routing/log', () =>
        HttpResponse.json({
          runs: [
            runAt('t1', today),
            runAt('y1', yesterday, { recording_id: 'rec_y' }),
            runAt('o1', older, { recording_id: 'rec_o' }),
          ],
        }),
      ),
    );
    renderWithProviders(<ActivitySection />);
    expect(await screen.findByRole('heading', { name: 'Today' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Yesterday' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Dec 24, 2025/ })).toBeInTheDocument();
    expect(screen.getAllByRole('list')).toHaveLength(3);
  });

  it('shows the empty state and a Refresh button', async () => {
    server.use(http.get('/api/v1/routing/log', () => HttpResponse.json({ runs: [] })));
    renderWithProviders(<ActivitySection />);
    expect(await screen.findByRole('heading', { name: 'Nothing has run yet' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument();
  });
});
