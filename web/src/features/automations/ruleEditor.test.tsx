import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import { http, HttpResponse, server } from '@/test/msw';
import * as fx from '@/test/fixtures';
import { RuleEditor, buildRouteBody, draftFromRoute, saveErrorMessage } from './rules/RuleEditor';
import { previewMatches } from './rules/TryItPanel';
import { ApiError, type Route } from '@/api';

const withSecret: Route = {
  ...fx.routeAgent,
  action_config: {
    url: 'https://agent.example/hook',
    auth_header: 'Authorization: Bearer old',
    folder: null,
  },
};

const dialog = () => screen.getByRole('dialog');

describe('buildRouteBody', () => {
  it('validates in user words before anything is sent', () => {
    const d = draftFromRoute(null);
    expect(buildRouteBody(d, null).problem).toEqual({ field: 'name', message: 'Give the rule a name.' });
    expect(buildRouteBody({ ...d, name: 'x'.repeat(65) }, null).problem?.field).toBe('name');
    expect(buildRouteBody({ ...d, name: 'A' }, null).problem).toEqual({
      field: 'description',
      message: 'Describe which recordings this applies to.',
    });
    expect(buildRouteBody({ ...d, name: 'A', description: 'B' }, null).problem?.field).toBe('url');
    expect(buildRouteBody({ ...d, name: 'A', description: 'B', url: 'ftp://x' }, null).problem?.message).toBe(
      'The address must start with http:// or https://.',
    );
    expect(
      buildRouteBody({ ...d, name: 'A', description: 'B', url: 'https://x', secret: 'nocolon' }, null).problem
        ?.field,
    ).toBe('secret');
    expect(buildRouteBody({ ...d, name: 'A', description: 'B', kind: 'markdown' }, null).problem?.field).toBe(
      'folder',
    );
    expect(
      buildRouteBody({ ...d, name: 'A', description: 'B', kind: 'markdown', folder: 'a/../b' }, null).problem
        ?.message,
    ).toBe('The folder must be a relative path without “..”.');
    expect(
      buildRouteBody({ ...d, name: 'A', description: 'B', kind: 'markdown', folder: '/Inbox/' }, null).body,
    ).toEqual({
      name: 'A',
      description: 'B',
      action_type: 'markdown',
      action_config: { folder: 'Inbox' },
      enabled: true,
    });
    expect(
      buildRouteBody({ ...d, name: 'A', description: 'B', kind: 'none' }, null).body?.action_config,
    ).toEqual({});
  });

  it('keeps, replaces or removes the saved secret header', () => {
    const d = draftFromRoute(withSecret);
    // blank: resend the saved one, the server rebuilds action_config from the body
    expect(buildRouteBody(d, withSecret).body?.action_config).toEqual({
      url: 'https://agent.example/hook',
      auth_header: 'Authorization: Bearer old',
    });
    // typed: the new one
    expect(buildRouteBody({ ...d, secret: 'X-Key: new' }, withSecret).body?.action_config.auth_header).toBe(
      'X-Key: new',
    );
    // removed: left out
    expect(buildRouteBody({ ...d, clearSecret: true }, withSecret).body?.action_config).toEqual({
      url: 'https://agent.example/hook',
    });
    // a rule that never had one sends none
    expect(buildRouteBody(draftFromRoute(fx.routeAgent), fx.routeAgent).body?.action_config).toEqual({
      url: 'https://agent.example/hook',
    });
  });

  it('turns server refusals into sentences', () => {
    expect(saveErrorMessage(new ApiError(409, "route named 'A' already exists"), 'A')).toBe(
      'There is already a rule named “A”. Pick another name.',
    );
    expect(saveErrorMessage(new ApiError(404, 'Not Found'), 'A')).toBe(
      'Your server doesn’t support automations yet.',
    );
    expect(saveErrorMessage(new ApiError(400, 'invalid action_config: url too long'), 'A')).toBe(
      'invalid action_config: url too long',
    );
    expect(saveErrorMessage(new Error('boom'), 'A')).toBe('Couldn’t save the rule. Try again.');
  });
});

describe('RuleEditor', () => {
  it('creates a rule and reports problems inline first', async () => {
    let posted: Record<string, unknown> | null = null;
    server.use(
      http.post('/api/v1/routes', async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...fx.routeAgent, ...posted, id: 'new' }, { status: 201 });
      }),
    );
    const onClose = vi.fn();
    renderWithProviders(<RuleEditor route={null} open onClose={onClose} />);
    expect(dialog()).toHaveTextContent('New rule');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(screen.getByText('Give the rule a name.')).toBeInTheDocument();
    expect(posted).toBeNull();

    await userEvent.type(screen.getByLabelText('Name'), 'Work meetings');
    await userEvent.type(screen.getByLabelText('When should this run?'), 'Standups and 1:1s.');
    await userEvent.click(screen.getByRole('radio', { name: /Save a note in a folder/ }));
    expect(screen.queryByLabelText('Agent address')).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('Folder in your vault'), 'Meetings');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted).toEqual({
      name: 'Work meetings',
      description: 'Standups and 1:1s.',
      action_type: 'markdown',
      action_config: { folder: 'Meetings' },
      enabled: true,
    });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(await screen.findByText('Rule added')).toBeInTheDocument();
  });

  it('shows a duplicate-name refusal from the server inline', async () => {
    server.use(
      http.post('/api/v1/routes', () =>
        HttpResponse.json({ detail: "route named 'Ask Claude' already exists" }, { status: 409 }),
      ),
    );
    renderWithProviders(<RuleEditor route={null} open onClose={() => {}} />);
    await userEvent.type(screen.getByLabelText('Name'), 'Ask Claude');
    await userEvent.type(screen.getByLabelText('When should this run?'), 'Requests.');
    await userEvent.type(screen.getByLabelText('Agent address'), 'https://agent.example/hook');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'There is already a rule named “Ask Claude”. Pick another name.',
    );
    expect(dialog()).toBeInTheDocument();
  });

  it('keeps the saved secret header when the field is left blank, with Show/Hide', async () => {
    let put: Record<string, unknown> | null = null;
    server.use(
      http.put('/api/v1/routes/:id', async ({ request }) => {
        put = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...withSecret, ...put });
      }),
    );
    renderWithProviders(<RuleEditor route={withSecret} open onClose={() => {}} />);
    expect(dialog()).toHaveTextContent('Edit rule');
    const secret = screen.getByLabelText('Secret header (optional)') as HTMLInputElement;
    expect(secret).toHaveAttribute('placeholder', 'Set. Leave blank to keep it.');
    expect(secret.value).toBe('');
    expect(secret.type).toBe('password');
    await userEvent.click(screen.getByRole('button', { name: 'Show the secret header' }));
    expect(secret.type).toBe('text');
    await userEvent.click(screen.getByRole('button', { name: 'Hide the secret header' }));
    expect(secret.type).toBe('password');

    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(put).not.toBeNull());
    expect((put as unknown as { action_config: Record<string, unknown> }).action_config).toEqual({
      url: 'https://agent.example/hook',
      auth_header: 'Authorization: Bearer old',
    });
  });

  it('sends the typed secret header, or drops it when asked to remove it', async () => {
    const puts: Record<string, unknown>[] = [];
    server.use(
      http.put('/api/v1/routes/:id', async ({ request }) => {
        const b = (await request.json()) as Record<string, unknown>;
        puts.push(b);
        return HttpResponse.json({ ...withSecret, ...b });
      }),
    );
    const { unmount } = renderWithProviders(<RuleEditor route={withSecret} open onClose={() => {}} />);
    await userEvent.type(screen.getByLabelText('Secret header (optional)'), 'X-Key: fresh');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect((puts[0] as { action_config: Record<string, unknown> }).action_config.auth_header).toBe(
      'X-Key: fresh',
    );
    unmount();

    renderWithProviders(<RuleEditor route={withSecret} open onClose={() => {}} />);
    await userEvent.click(screen.getByRole('checkbox', { name: 'Remove the saved secret header' }));
    expect(screen.getByLabelText('Secret header (optional)')).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(puts).toHaveLength(2));
    expect((puts[1] as { action_config: Record<string, unknown> }).action_config).toEqual({
      url: 'https://agent.example/hook',
    });
  });

  it('a rule without a saved header shows the example placeholder and no Remove chip', () => {
    renderWithProviders(<RuleEditor route={fx.routeAgent} open onClose={() => {}} />);
    expect(screen.getByLabelText('Secret header (optional)')).toHaveAttribute(
      'placeholder',
      'Authorization: Bearer …',
    );
    expect(
      screen.queryByRole('checkbox', { name: 'Remove the saved secret header' }),
    ).not.toBeInTheDocument();
  });
});

describe('Try it on a recording', () => {
  it('is offered only when editing a saved rule', async () => {
    renderWithProviders(<RuleEditor route={null} open onClose={() => {}} />);
    expect(screen.queryByRole('heading', { name: 'Try it on a recording' })).not.toBeInTheDocument();
  });

  it('previews the picked recording and lists every matched rule with its reason', async () => {
    let previewed: string | null = null;
    server.use(
      http.post('/api/v1/recordings/:id/route/preview', ({ params }) => {
        previewed = String(params.id);
        return HttpResponse.json({
          route_id: fx.routeAgent.id,
          route_name: fx.routeAgent.name,
          reason: 'A request.',
          model: 'm',
          matches: [
            {
              route_id: fx.routeAgent.id,
              route_name: fx.routeAgent.name,
              reason: 'A request for the assistant.',
            },
            { route_id: fx.routeNotes.id, route_name: fx.routeNotes.name, reason: 'Worth keeping.' },
          ],
        });
      }),
    );
    renderWithProviders(<RuleEditor route={fx.routeAgent} open onClose={() => {}} />);
    const panel = await screen.findByRole('region', { name: 'Try it on a recording' });
    // the newest finished recording with speech is picked by default; silent and unfinished ones are not offered
    const picker = within(panel).getByRole('combobox', { name: 'Recording' }) as HTMLSelectElement;
    await waitFor(() => expect(picker).toHaveValue(fx.recordingDone.id));
    expect(picker).toBeEnabled();
    expect(within(picker).getAllByRole('option')).toHaveLength(1);
    expect(within(picker).getByRole('option', { name: /The Political Fight/ })).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole('button', { name: 'Try' }));
    const result = await within(panel).findByTestId('try-it-result');
    expect(previewed).toBe(fx.recordingDone.id);
    expect(result).toHaveTextContent('Would run these rules:');
    expect(result).toHaveTextContent('Ask Claude');
    expect(result).toHaveTextContent('A request for the assistant.');
    expect(result).toHaveTextContent('Vault notes');
    expect(result).toHaveTextContent('Worth keeping.');
    expect(result).not.toHaveTextContent('m');
  });

  it('says when nothing would match', async () => {
    server.use(
      http.post('/api/v1/recordings/:id/route/preview', () =>
        HttpResponse.json({
          route_id: null,
          route_name: null,
          reason: 'Just a chat.',
          model: 'm',
          matches: [],
        }),
      ),
    );
    renderWithProviders(<RuleEditor route={fx.routeAgent} open onClose={() => {}} />);
    const panel = await screen.findByRole('region', { name: 'Try it on a recording' });
    await waitFor(() =>
      expect(within(panel).getByRole('combobox', { name: 'Recording' })).toHaveValue(fx.recordingDone.id),
    );
    await userEvent.click(within(panel).getByRole('button', { name: 'Try' }));
    const result = await within(panel).findByTestId('try-it-result');
    expect(result).toHaveTextContent('Nothing would match');
    expect(result).toHaveTextContent('Just a chat.');
  });

  it('hides itself on a server without previews', async () => {
    server.use(
      http.post('/api/v1/recordings/:id/route/preview', () =>
        HttpResponse.json({ detail: 'Not Found' }, { status: 404 }),
      ),
    );
    renderWithProviders(<RuleEditor route={fx.routeAgent} open onClose={() => {}} />);
    const panel = await screen.findByRole('region', { name: 'Try it on a recording' });
    await waitFor(() =>
      expect(within(panel).getByRole('combobox', { name: 'Recording' })).toHaveValue(fx.recordingDone.id),
    );
    await userEvent.click(within(panel).getByRole('button', { name: 'Try' }));
    await waitFor(() =>
      expect(screen.queryByRole('region', { name: 'Try it on a recording' })).not.toBeInTheDocument(),
    );
  });

  it('falls back to the single match of an older server', () => {
    expect(previewMatches({ route_name: 'A', reason: 'r', matches: [] })).toEqual([
      { name: 'A', reason: 'r' },
    ]);
    expect(previewMatches({ route_name: null, reason: 'none', matches: [] })).toEqual([]);
  });
});
