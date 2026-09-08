import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from './AuthProvider';
import { Gate } from './Gate';
import { consumeLoginFragment } from './loginFragment';
import { rememberLoginRequest, savedLoginRequest } from './useQrLogin';
import { AUTH_REQUIRED_EVENT } from '@/api/client';
import { tokenStore } from '@/api/token';
import { makeTestQueryClient } from '@/test/render';
import { http, HttpResponse, server, TEST_TOKEN } from '@/test/msw';

function Status() {
  const { status, signOut } = useAuth();
  return (
    <>
      <div data-testid="status">{status}</div>
      <button onClick={() => void signOut()}>sign out</button>
    </>
  );
}

function renderAuth(initialCandidate = '', ui = <Status />) {
  const qc = makeTestQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <AuthProvider initialCandidate={initialCandidate}>{ui}</AuthProvider>
    </QueryClientProvider>,
  );
}

describe('consumeLoginFragment', () => {
  it('returns the token and scrubs the fragment from the URL, even when malformed', () => {
    const replaceState = vi.fn();
    const loc = { hash: '#token=abc%20def', pathname: '/', search: '?x=1' } as Location;
    expect(consumeLoginFragment(loc, { replaceState } as unknown as History)).toBe(''); // space fails the grammar
    expect(replaceState).toHaveBeenCalledWith(null, '', '/?x=1');
    expect(
      consumeLoginFragment(
        { hash: '#token=good-token', pathname: '/', search: '' } as Location,
        { replaceState } as unknown as History,
      ),
    ).toBe('good-token');
    expect(
      consumeLoginFragment(
        { hash: '#/rec/1', pathname: '/', search: '' } as Location,
        { replaceState } as unknown as History,
      ),
    ).toBe('');
    expect(replaceState).toHaveBeenCalledTimes(2);
  });
});

describe('AuthProvider', () => {
  it('is signed out without a token, adopts a valid stored token, rejects a bad one', async () => {
    const { unmount } = renderAuth();
    expect(screen.getByTestId('status')).toHaveTextContent('signed-out');
    unmount();

    tokenStore.set(TEST_TOKEN);
    const r2 = renderAuth();
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'));
    r2.unmount();

    tokenStore.set('stale-token');
    renderAuth();
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-out'));
  });

  it('prefers a login-link candidate over the stored token and stores it once accepted', async () => {
    tokenStore.set('old-token');
    renderAuth(TEST_TOKEN);
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'));
    expect(localStorage.getItem('pb_token')).toBe(TEST_TOKEN);
  });

  it('returns to the gate on auth-required and on sign out (POST /auth/logout, token cleared)', async () => {
    tokenStore.set(TEST_TOKEN);
    let loggedOut = false;
    server.use(
      http.post('/api/v1/auth/logout', () => {
        loggedOut = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderAuth();
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'));
    act(() => window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT)));
    expect(screen.getByTestId('status')).toHaveTextContent('signed-out');

    tokenStore.set(TEST_TOKEN);
    await userEvent.click(screen.getByText('sign out'));
    await waitFor(() => expect(loggedOut).toBe(true));
    expect(localStorage.getItem('pb_token')).toBeNull();
    expect(screen.getByTestId('status')).toHaveTextContent('signed-out');
  });
});

describe('AuthProvider across tabs', () => {
  it('signs out when another tab removes the token and signs in when one appears', async () => {
    tokenStore.set(TEST_TOKEN);
    renderAuth();
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'));
    localStorage.removeItem('pb_token');
    act(() => window.dispatchEvent(new StorageEvent('storage', { key: 'pb_token', newValue: null })));
    expect(screen.getByTestId('status')).toHaveTextContent('signed-out');
    localStorage.setItem('pb_token', TEST_TOKEN);
    act(() => window.dispatchEvent(new StorageEvent('storage', { key: 'pb_token', newValue: TEST_TOKEN })));
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'));
  });
});

describe('Gate', () => {
  it('shows a QR from a fresh login request, remembers it, and signs in when the phone approves', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let polls = 0;
    server.use(
      http.get('/api/v1/login-requests/:id', () => {
        polls++;
        return polls < 2
          ? HttpResponse.json({ status: 'pending' })
          : HttpResponse.json({ status: 'approved', token: TEST_TOKEN });
      }),
    );
    renderAuth(
      '',
      <>
        <Gate />
        <Status />
      </>,
    );
    await waitFor(() => expect(screen.getByRole('img', { name: 'Sign-in QR code' })).toBeInTheDocument());
    expect(savedLoginRequest()?.id).toBe('req_1');
    expect(screen.getByRole('status')).toHaveTextContent('Waiting for your phone…');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100); // first poll: pending
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100); // second poll: approved
    });
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'));
    expect(savedLoginRequest()).toBeNull();
    vi.useRealTimers();
  });

  it('reuses a remembered request instead of minting another', async () => {
    let created = 0;
    server.use(
      http.post('/api/v1/login-requests', () => {
        created++;
        return HttpResponse.json(
          { id: 'req_new', expires_at: new Date(Date.now() + 180_000).toISOString(), poll_seconds: 2 },
          { status: 201 },
        );
      }),
    );
    rememberLoginRequest({
      id: 'req_saved',
      expires_at: new Date(Date.now() + 120_000).toISOString(),
      poll_seconds: 2,
    });
    renderAuth('', <Gate />);
    await waitFor(() => expect(screen.getByRole('img', { name: 'Sign-in QR code' })).toBeInTheDocument());
    expect(created).toBe(0);
    // An almost-expired one is not worth reusing.
    rememberLoginRequest({
      id: 'req_old',
      expires_at: new Date(Date.now() + 5_000).toISOString(),
      poll_seconds: 2,
    });
    expect(savedLoginRequest()).toBeNull();
  });

  it('explains when the server has no QR sign-in and still accepts a pasted token', async () => {
    server.use(
      http.post('/api/v1/login-requests', () => HttpResponse.json({ detail: 'Not Found' }, { status: 404 })),
    );
    renderAuth(
      '',
      <>
        <Gate />
        <Status />
      </>,
    );
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('does not support QR sign-in'));
    await userEvent.click(screen.getByRole('button', { name: 'Or enter the access token' }));
    const field = screen.getByLabelText('Access token');
    await userEvent.type(field, 'has space');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(screen.getByText('That token is not valid.')).toBeInTheDocument();
    await userEvent.clear(field);
    await userEvent.type(field, 'not-the-right-token');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() => expect(screen.getByText('That token was not accepted.')).toBeInTheDocument());
    await userEvent.clear(field);
    await userEvent.type(field, TEST_TOKEN);
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signed-in'));
  });
});
