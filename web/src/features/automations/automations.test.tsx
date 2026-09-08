import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import { http, HttpResponse, server } from '@/test/msw';
import * as fx from '@/test/fixtures';
import { EmbeddedProvider } from '@/features/shell';
import { AutomationsPage } from './AutomationsPage';
import { StatusBanner, rulesSummary } from './StatusBanner';
import { actionChip } from './rules/actionWords';
import { ApiError } from '@/api';

const renderPage = (search = '') =>
  renderWithProviders(
    <EmbeddedProvider search={search}>
      <AutomationsPage />
    </EmbeddedProvider>,
    { route: '/automations' },
  );

describe('StatusBanner', () => {
  it('says automations are on, in user words, never the model id', async () => {
    renderPage();
    // (the snackbar host is also role=status, so find the banner by its words)
    const banner = (await screen.findByText('Automations are on.')).closest('[role=status]')!;
    expect(banner).toHaveTextContent('Automations are on.');
    expect(banner).toHaveTextContent('New transcripts are checked against your rules.');
    await waitFor(() => expect(banner).toHaveTextContent('One of two rules are turned on'));
    expect(banner).toHaveTextContent('last run');
    expect(banner).not.toHaveTextContent('some-model');
    expect(banner).not.toHaveTextContent('router');
  });

  it('warns when turned off on the server', async () => {
    server.use(
      http.get('/api/v1/router/status', () =>
        HttpResponse.json({ enabled: false, configured: true, model: 'some-model' }),
      ),
    );
    renderPage();
    const banner = await screen.findByRole('alert');
    expect(banner).toHaveTextContent('Automations are turned off on the server.');
    expect(banner).toHaveTextContent('Rules are kept but nothing runs.');
  });

  it('warns when not set up', async () => {
    server.use(
      http.get('/api/v1/router/status', () =>
        HttpResponse.json({ enabled: true, configured: false, model: null }),
      ),
    );
    renderPage();
    expect(await screen.findByRole('alert')).toHaveTextContent('Automations are not set up on the server.');
  });

  it('tells the user the server is too old when the endpoint is missing, and hides the sections', async () => {
    server.use(
      http.get('/api/v1/router/status', () => HttpResponse.json({ detail: 'Not Found' }, { status: 404 })),
    );
    renderPage();
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Your server doesn’t support automations yet.',
    );
    expect(screen.queryByRole('heading', { name: 'Rules' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Activity' })).not.toBeInTheDocument();
  });

  it('shows the server sentence for other failures', () => {
    renderWithProviders(<StatusBanner status={undefined} error={new ApiError(500, null)} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Couldn’t check whether automations are on.');
  });

  it('summarises the rules in words', () => {
    expect(rulesSummary([])).toBe('No rules yet');
    expect(rulesSummary([{ enabled: true }])).toBe('Your rule is turned on');
    expect(rulesSummary([{ enabled: false }])).toBe('Your rule is turned off');
    expect(rulesSummary([{ enabled: true }, { enabled: true }, { enabled: true }])).toBe(
      'All three rules are turned on',
    );
    expect(rulesSummary([{ enabled: false }, { enabled: false }])).toBe(
      'None of your two rules are turned on',
    );
    expect(rulesSummary([{ enabled: true }, { enabled: false }, { enabled: true }])).toBe(
      'Two of three rules are turned on',
    );
  });
});

describe('Rules', () => {
  it('maps each action to user words', () => {
    expect(actionChip(fx.routeAgent)).toBe('Sends to the agent');
    expect(actionChip(fx.routeNotes)).toBe('Saves a note in Inbox');
    expect(actionChip({ action_type: 'markdown', action_config: {} })).toBe('Saves a note in a folder');
    expect(actionChip({ action_type: 'none', action_config: {} })).toBe('Just records the decision');
  });

  it('lists every rule with its chip, switch, Edit and Delete', async () => {
    server.use(
      http.get('/api/v1/routes', () =>
        HttpResponse.json({
          routes: [
            fx.routeAgent,
            fx.routeNotes,
            { ...fx.routeAgent, id: 'route_none', name: 'Log only', action_type: 'none', action_config: {} },
          ],
        }),
      ),
    );
    renderPage();
    const list = await screen.findByRole('list', { name: 'Rules' });
    const cards = within(list).getAllByRole('listitem');
    expect(cards).toHaveLength(3);
    expect(cards[0]).toHaveTextContent('Ask Claude');
    expect(cards[0]).toHaveTextContent('Sends to the agent');
    expect(within(cards[0]).getByRole('switch', { name: 'Turn “Ask Claude” on or off' })).toBeChecked();
    expect(cards[1]).toHaveTextContent('Saves a note in Inbox');
    expect(within(cards[1]).getByRole('switch')).not.toBeChecked();
    expect(cards[1]).toHaveAttribute('data-enabled', 'false');
    expect(cards[2]).toHaveTextContent('Just records the decision');
    expect(within(cards[0]).getByRole('button', { name: 'Edit' })).toBeInTheDocument();
    expect(within(cards[0]).getByRole('button', { name: 'Delete' })).toBeInTheDocument();
    // never the server's names
    expect(list).not.toHaveTextContent(/webhook|markdown/);
  });

  it('flips the switch at once, PUTs the whole rule and confirms with a snackbar', async () => {
    let body: Record<string, unknown> | null = null;
    let release: () => void = () => {};
    server.use(
      http.put('/api/v1/routes/:id', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        await new Promise<void>((r) => (release = r));
        return HttpResponse.json({ ...fx.routeNotes, ...body });
      }),
      // the refetch after saving sees the new state
      http.get('/api/v1/routes', () =>
        HttpResponse.json({ routes: [fx.routeAgent, body ? { ...fx.routeNotes, ...body } : fx.routeNotes] }),
      ),
    );
    renderPage();
    const sw = await screen.findByRole('switch', { name: 'Turn “Vault notes” on or off' });
    expect(sw).not.toBeChecked();
    await userEvent.click(sw);
    // optimistic: checked before the server answers
    await waitFor(() =>
      expect(screen.getByRole('switch', { name: 'Turn “Vault notes” on or off' })).toBeChecked(),
    );
    expect(screen.queryByText('“Vault notes” turned on')).not.toBeInTheDocument();
    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toEqual({
      name: fx.routeNotes.name,
      description: fx.routeNotes.description,
      action_type: 'markdown',
      action_config: fx.routeNotes.action_config,
      enabled: true,
    });
    release();
    await screen.findByText('“Vault notes” turned on');
    expect(screen.getByRole('switch', { name: 'Turn “Vault notes” on or off' })).toBeChecked();
  });

  it('reverts the switch and explains when the server refuses', async () => {
    let release: () => void = () => {};
    server.use(
      http.put('/api/v1/routes/:id', async () => {
        await new Promise<void>((r) => (release = r));
        return HttpResponse.json({ detail: 'Something broke.' }, { status: 500 });
      }),
    );
    renderPage();
    const sw = await screen.findByRole('switch', { name: 'Turn “Ask Claude” on or off' });
    expect(sw).toBeChecked();
    await userEvent.click(sw);
    await waitFor(() =>
      expect(screen.getByRole('switch', { name: 'Turn “Ask Claude” on or off' })).not.toBeChecked(),
    );
    release();
    await waitFor(() =>
      expect(screen.getByRole('switch', { name: 'Turn “Ask Claude” on or off' })).toBeChecked(),
    );
    // a server error never leaks its text; the fallback sentence shows
    expect(await screen.findByText('Couldn’t turn “Ask Claude” off.')).toBeInTheDocument();
  });

  it('deletes only after a destructive confirmation', async () => {
    let deleted: string | null = null;
    server.use(
      http.delete('/api/v1/routes/:id', ({ params }) => {
        deleted = String(params.id);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderPage();
    const list = await screen.findByRole('list', { name: 'Rules' });
    await userEvent.click(within(list).getAllByRole('button', { name: 'Delete' })[1]);
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveTextContent('Delete this rule?');
    expect(dialog).toHaveTextContent('Vault notes will stop running.');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(deleted).toBeNull();
    await userEvent.click(within(list).getAllByRole('button', { name: 'Delete' })[1]);
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(deleted).toBe(fx.routeNotes.id));
    await screen.findByText('Rule deleted');
  });

  it('shows the empty states', async () => {
    server.use(
      http.get('/api/v1/routes', () => HttpResponse.json({ routes: [] })),
      http.get('/api/v1/routing/log', () => HttpResponse.json({ runs: [] })),
    );
    renderPage();
    expect(await screen.findByRole('heading', { name: 'No rules yet' })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Add rule' })).toHaveLength(2);
    expect(await screen.findByRole('heading', { name: 'Nothing has run yet' })).toBeInTheDocument();
  });
});

describe('embedded', () => {
  it('renders no section app bar inside the Android app', async () => {
    renderPage('?embedded=1&tab=automations');
    await screen.findByRole('heading', { name: 'Rules' });
    expect(screen.queryByRole('heading', { name: 'Automations', level: 1 })).not.toBeInTheDocument();
  });

  it('renders the app bar on the web', async () => {
    renderPage('');
    await screen.findByRole('heading', { name: 'Rules' });
    expect(screen.getByRole('heading', { name: 'Automations', level: 1 })).toBeInTheDocument();
  });
});
