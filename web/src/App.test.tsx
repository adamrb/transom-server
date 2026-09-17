import { render, screen, waitFor } from '@testing-library/react';
import App from './App';
import { tokenStore } from '@/api/token';
import { TEST_TOKEN } from '@/test/msw';

describe('App', () => {
  afterEach(() => {
    window.location.hash = '';
  });

  it('shows the sign-in gate without a token', async () => {
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Transom' })).toBeInTheDocument();
    expect(screen.getByText('Sign in with your phone')).toBeInTheDocument();
  });

  it('opens the shell on the recordings section with a valid token', async () => {
    tokenStore.set(TEST_TOKEN);
    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 1, name: 'Recordings' })).toBeInTheDocument(),
    );
    expect(screen.queryByText('Sign in with your phone')).toBeNull();
  });

  it('adopts a login-link candidate', async () => {
    render(<App loginCandidate={TEST_TOKEN} />);
    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 1, name: 'Recordings' })).toBeInTheDocument(),
    );
    expect(localStorage.getItem('pb_token')).toBe(TEST_TOKEN);
  });
});
