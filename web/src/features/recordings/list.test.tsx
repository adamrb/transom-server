import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse, server } from '@/test/msw';
import * as fx from '@/test/fixtures';
import * as bp from '@/lib/breakpoints';
import { listStateStore } from './list/useListState';
import { renderRecordings } from './test/renderPage';

const ALL = [
  fx.recordingPending,
  fx.recordingTranscribing,
  fx.recordingDone,
  fx.recordingSilent,
  fx.recordingFailed,
];

beforeEach(() => {
  vi.setSystemTime(new Date('2026-09-08T20:00:00Z'));
  listStateStore.reset();
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

/** Capture the list requests the page makes. */
function captureList(rows: (url: URL) => unknown[]) {
  const urls: URL[] = [];
  server.use(
    http.get('/api/v1/recordings', ({ request }) => {
      const url = new URL(request.url);
      urls.push(url);
      return HttpResponse.json({ recordings: rows(url) });
    }),
  );
  return urls;
}

describe('recordings list', () => {
  it('groups rows by day and shows status words only while something is happening', async () => {
    captureList(() => [
      ...ALL,
      {
        ...fx.recordingDone,
        id: 'rec_yesterday',
        title: 'Garage inventory',
        started_at: '2026-09-07T18:47:00Z',
      },
    ]);
    renderRecordings();
    await screen.findByRole('button', { name: /Political Fight/ });

    expect(screen.getByText('Today')).toBeInTheDocument();
    expect(screen.getByText('Yesterday')).toBeInTheDocument();

    const pending = screen.getByRole('button', { name: /Waiting/ });
    expect(within(pending).getByText('rec_42.mp3')).toBeInTheDocument();
    expect(within(pending).getByText('Waiting')).toBeInTheDocument();
    expect(within(pending).getByText('Your server will start on it shortly')).toBeInTheDocument();
    const transcribing = screen.getByRole('button', { name: /Transcribing 42%/ });
    expect(within(transcribing).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '42');
    expect(
      within(screen.getByRole('button', { name: /Silent recording/ })).getByText('No speech'),
    ).toBeInTheDocument();
    expect(within(screen.getByRole('button', { name: /Failed/ })).getByText('Failed')).toBeInTheDocument();
    const done = screen.getByRole('button', { name: /Political Fight/ });
    expect(within(done).queryByText(/Waiting|Transcribing|Failed|No speech/)).toBeNull();
    // finished: time · duration · preview, and the bookmark count on the right
    expect(within(done).getByText(/2h 19m/)).toBeInTheDocument();
    expect(within(done).getByText('2')).toBeInTheDocument();
  });

  it('shows what the automations did under a finished row, never under one still in flight', async () => {
    const summary = {
      state: 'done',
      line: 'Vault notes: Filed: Notes/Dogs.md',
      items: [{ route_name: 'Vault notes', state: 'done', summary: 'Filed: Notes/Dogs.md' }],
      run_id: 'run-1',
      run_at: '2026-09-08T00:30:00Z',
    };
    captureList(() => [
      { ...fx.recordingDone, automations: summary },
      { ...fx.recordingTranscribing, automations: summary },
      {
        ...fx.recordingDone,
        id: 'rec_failed_auto',
        title: 'Broken hand-off',
        automations: {
          state: 'failed',
          line: 'Ask Claude: HTTP 500',
          items: [{ route_name: 'Ask Claude', state: 'failed', summary: 'HTTP 500' }],
        },
      },
      { ...fx.recordingDone, id: 'rec_plain', title: 'Nothing ran', automations: null },
    ]);
    renderRecordings();
    const done = await screen.findByRole('button', { name: /Political Fight/ });
    const line = within(done).getByTestId('row-automations');
    expect(line).toHaveTextContent('Vault notes: Filed: Notes/Dogs.md');
    expect(within(line).getByText('Vault notes:')).toHaveClass('font-medium');
    expect(within(screen.getByRole('button', { name: /Transcribing 42%/ })).queryByTestId('row-automations')).toBeNull();
    expect(within(screen.getByRole('button', { name: /Broken hand-off/ })).getByTestId('row-automations')).toHaveClass('text-error');
    expect(within(screen.getByRole('button', { name: /Nothing ran/ })).queryByTestId('row-automations')).toBeNull();
  });

  it('sends the filter chip as the status parameter, including no_speech', async () => {
    const urls = captureList((url) =>
      url.searchParams.get('status') === 'no_speech' ? [fx.recordingSilent] : ALL,
    );
    renderRecordings();
    await screen.findByRole('button', { name: /Political Fight/ });
    await userEvent.click(screen.getByRole('checkbox', { name: 'No speech' }));
    await waitFor(() => expect(urls.at(-1)?.searchParams.get('status')).toBe('no_speech'));
    await waitFor(() => expect(screen.queryByRole('button', { name: /Political Fight/ })).toBeNull());
    expect(screen.getByRole('checkbox', { name: 'No speech' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'All' })).not.toBeChecked();
  });

  it('searches with q (debounced) and marks the hit in the snippet', async () => {
    const urls = captureList((url) =>
      url.searchParams.get('q')
        ? [
            {
              ...fx.recordingDone,
              match_field: 'transcript',
              match_snippet: 'Everyone, it appears, hates datacenters. Polls show…',
            },
          ]
        : ALL,
    );
    renderRecordings();
    await screen.findByRole('button', { name: /Political Fight/ });
    await userEvent.type(screen.getByRole('searchbox'), 'datacenters');
    await waitFor(() => expect(urls.at(-1)?.searchParams.get('q')).toBe('datacenters'));
    await waitFor(() => expect(screen.getByText('datacenters', { selector: 'mark' })).toBeInTheDocument());
    // one request per debounce, not per keystroke
    expect(urls.filter((u) => u.searchParams.get('q')).length).toBe(1);
    expect(screen.queryByRole('button', { name: /Silent recording/ })).toBeNull();
  });

  it('caps the search term at the 200 characters the server accepts', async () => {
    const urls = captureList(() => []);
    renderRecordings();
    await screen.findByText('No recordings yet');
    const box = screen.getByRole('searchbox');
    await userEvent.click(box);
    await userEvent.paste('x'.repeat(230));
    await waitFor(() => expect(urls.at(-1)?.searchParams.get('q')?.length).toBe(200));
    expect((box as HTMLInputElement).value.length).toBe(200);
  });

  it('shows the empty states', async () => {
    const urls = captureList((url) => (url.searchParams.get('q') ? [] : []));
    renderRecordings();
    expect(await screen.findByText('No recordings yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Connect a phone' })).toBeInTheDocument();
    await userEvent.type(screen.getByRole('searchbox'), 'zzz');
    expect(await screen.findByText('No recordings match “zzz”.')).toBeInTheDocument();
    await userEvent.click(
      within(screen.getByRole('region', { name: 'Recording list' })).getByRole('button', {
        name: 'Clear search',
      }),
    );
    expect(await screen.findByText('No recordings yet')).toBeInTheDocument();
    expect(urls.length).toBeGreaterThan(1);
  });

  it('loads more with offset and keeps every row', async () => {
    const page1 = Array.from({ length: 50 }, (_, i) => ({
      ...fx.recordingDone,
      id: `r${i}`,
      title: `Row ${i}`,
    }));
    const page2 = [{ ...fx.recordingDone, id: 'r50', title: 'Row 50' }];
    const urls = captureList((url) => (url.searchParams.get('offset') === '50' ? page2 : page1));
    renderRecordings();
    await screen.findByRole('button', { name: /Row 49/ });
    expect(urls[0].searchParams.get('limit')).toBe('50');
    expect(urls[0].searchParams.get('offset')).toBe('0');
    await userEvent.click(screen.getByRole('button', { name: 'Load more' }));
    await screen.findByRole('button', { name: /Row 50/ });
    expect(urls.at(-1)?.searchParams.get('offset')).toBe('50');
    expect(screen.getAllByRole('button', { name: /^Row/ })).toHaveLength(51);
    expect(screen.queryByRole('button', { name: 'Load more' })).toBeNull();
  }, 15_000); // renders 100 rows; the 5 s default trips when other suites share the CPU

  it('moves between rows with the arrow keys and opens with Enter', async () => {
    captureList(() => ALL);
    renderRecordings();
    const first = await screen.findByRole('button', { name: /Waiting/ });
    first.focus();
    await userEvent.keyboard('{ArrowDown}');
    expect(screen.getByRole('button', { name: /Transcribing 42%/ })).toHaveFocus();
    await userEvent.keyboard('{ArrowDown}{ArrowDown}{ArrowUp}');
    expect(screen.getByRole('button', { name: /Political Fight/ })).toHaveFocus();
    await userEvent.keyboard('{Enter}');
    // phone: the detail takes over the screen, with a Back button
    expect(await screen.findByRole('button', { name: 'Back' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { level: 2, name: /Political Fight/ })).toBeInTheDocument();
  });

  it('keeps the list beside the detail on desktop and marks the open row', async () => {
    vi.spyOn(bp, 'useIsDesktop').mockReturnValue(true);
    captureList(() => ALL);
    renderRecordings({ route: '/rec/rec_done' });
    const row = await screen.findByRole('button', { name: /Political Fight/ });
    expect(row).toHaveAttribute('aria-current', 'true');
    expect(await screen.findByRole('heading', { level: 2, name: /Political Fight/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Back' })).toBeNull();
  });

  it('shows the getting-started card on desktop when nothing is open, and stops hidden playback', async () => {
    vi.spyOn(bp, 'useIsDesktop').mockReturnValue(true);
    captureList(() => ALL);
    // something was playing when the detail closed (e.g. its recording was deleted)
    const { store } = renderRecordings({ setup: (s) => s.load({ id: 'x', title: 'X', duration_s: 10 }) });
    expect(await screen.findByText('Getting started')).toBeInTheDocument();
    await waitFor(() => expect(store.getSnapshot().id).toBeNull());
  });
});
