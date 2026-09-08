import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import { http, HttpResponse, server } from '@/test/msw';
import * as fx from '@/test/fixtures';
import type { Session } from '@/api/types';
import { SessionsSection } from './SessionsSection';

const other: Session = {
  id: 'sess_2',
  label: null,
  created_at: '2026-09-06T20:00:00Z',
  last_used_at: null,
  current: false,
};

describe('SessionsSection', () => {
  it('lists each computer with its badge and times, plus the hand-token note', async () => {
    server.use(
      http.get('/api/v1/sessions', () => HttpResponse.json({ sessions: [fx.sessionCurrent, other] })),
    );
    renderWithProviders(<SessionsSection />);
    expect(await screen.findByText('Chrome on Linux')).toBeInTheDocument();
    expect(screen.getByText('this computer')).toBeInTheDocument();
    expect(screen.getByText(/^Signed in .* · last used .*/)).toBeInTheDocument();
    // null label → "Web browser"; no last_used_at → no "last used"
    expect(screen.getByText('Web browser')).toBeInTheDocument();
    expect(screen.getAllByText(/^Signed in /)).toHaveLength(2);
    expect(screen.getByText('Tokens entered by hand are not listed.')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Sign out' })).toHaveLength(2);
  });

  it('revokes a computer after confirming', async () => {
    let deleted: string | null = null;
    let sessions = [fx.sessionCurrent, other];
    server.use(
      http.get('/api/v1/sessions', () => HttpResponse.json({ sessions })),
      http.delete('/api/v1/sessions/:id', ({ params }) => {
        deleted = params.id as string;
        sessions = sessions.filter((s) => s.id !== params.id);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderWithProviders(<SessionsSection />);
    await screen.findByText('Web browser');
    const row = screen.getByText('Web browser').closest('[class*="border-t"]')!;
    await userEvent.click(within(row as HTMLElement).getByRole('button', { name: 'Sign out' }));

    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveTextContent('Sign out this computer?');
    expect(dialog).toHaveTextContent('Web browser will have to sign in again.');
    // Cancel first: nothing happens.
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(deleted).toBeNull();
    expect(screen.queryByRole('dialog')).toBeNull();

    await userEvent.click(within(row as HTMLElement).getByRole('button', { name: 'Sign out' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Sign out' }));
    await waitFor(() => expect(deleted).toBe('sess_2'));
    expect(await screen.findByText('Signed out')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText('Web browser')).toBeNull());
    expect(screen.getByText('Chrome on Linux')).toBeInTheDocument();
  });

  it('shows the server sentence when a revoke fails', async () => {
    server.use(
      http.delete('/api/v1/sessions/:id', () =>
        HttpResponse.json({ detail: 'That session was already signed out.' }, { status: 409 }),
      ),
    );
    renderWithProviders(<SessionsSection />);
    await screen.findByText('Chrome on Linux');
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Sign out' }));
    expect(await screen.findByText('That session was already signed out.')).toBeInTheDocument();
  });

  it('has an empty note and an older-server note', async () => {
    server.use(http.get('/api/v1/sessions', () => HttpResponse.json({ sessions: [] })));
    const { unmount } = renderWithProviders(<SessionsSection />);
    expect(
      await screen.findByText(
        'No computers signed in with a QR code. Tokens entered by hand are not listed.',
      ),
    ).toBeInTheDocument();
    unmount();

    server.use(
      http.get('/api/v1/sessions', () => HttpResponse.json({ detail: 'Not Found' }, { status: 404 })),
    );
    renderWithProviders(<SessionsSection />);
    expect(await screen.findByText('Your server does not list signed-in computers yet.')).toBeInTheDocument();
  });

  it('refreshes on demand', async () => {
    let gets = 0;
    server.use(
      http.get('/api/v1/sessions', () => {
        gets++;
        return HttpResponse.json({ sessions: [fx.sessionCurrent] });
      }),
    );
    renderWithProviders(<SessionsSection />);
    await screen.findByText('Chrome on Linux');
    await userEvent.click(screen.getByRole('button', { name: 'Refresh signed-in computers' }));
    await waitFor(() => expect(gets).toBe(2));
  });
});
