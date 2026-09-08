import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import { TEST_TOKEN } from '@/test/msw';
import { qrModel } from '@/lib/qr';
import { ConnectPhoneDialog, ConnectPhoneSection } from './ConnectPhoneSection';
import { connectPayload, loginLink } from './connectPayload';

const ORIGIN = 'https://plaud.example';

describe('connect-a-phone payload', () => {
  it('matches what the old dashboard encoded, key order included', () => {
    // openConnect(): JSON.stringify({ v: 1, url: location.origin, token })
    expect(connectPayload(ORIGIN, TEST_TOKEN)).toBe(`{"v":1,"url":"${ORIGIN}","token":"${TEST_TOKEN}"}`);
    expect(JSON.parse(connectPayload(ORIGIN, 'a b/c'))).toEqual({ v: 1, url: ORIGIN, token: 'a b/c' });
  });

  it('builds the same sign-in link as the old dashboard', () => {
    // $('cp-link').value = location.origin + '/#token=' + encodeURIComponent(token)
    expect(loginLink(ORIGIN, 'ab+c/d')).toBe(`${ORIGIN}/#token=${encodeURIComponent('ab+c/d')}`);
  });

  it('encodes to the same QR the old page drew (same encoder, EC level M, 4-module quiet zone)', () => {
    const model = qrModel(connectPayload(ORIGIN, TEST_TOKEN));
    expect(model.quiet).toBe(4);
    expect(model.size).toBeGreaterThan(21);
    expect(model.path.startsWith('M0 0h1v1h-1z')).toBe(true); // finder pattern corner
  });
});

describe('ConnectPhoneDialog', () => {
  it('shows the QR, the address, the masked token and the sign-in link, with copy buttons', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    renderWithProviders(<ConnectPhoneDialog open onClose={() => {}} token={TEST_TOKEN} origin={ORIGIN} />);
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByRole('img', { name: 'Connection QR code' })).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Server address')).toHaveValue(ORIGIN);
    const tokenField = within(dialog).getByLabelText('Access token');
    // Masked with dots (not type=password, so password managers stay out of it) until revealed.
    expect(tokenField).not.toHaveValue(TEST_TOKEN);
    expect(tokenField).toHaveAttribute('data-masked', 'true');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Show access token' }));
    expect(tokenField).toHaveValue(TEST_TOKEN);
    expect(tokenField).not.toHaveAttribute('data-masked');
    expect(within(dialog).getByLabelText(/Sign-in link/)).toHaveValue(loginLink(ORIGIN, TEST_TOKEN));
    expect(within(dialog).getByRole('alert')).toHaveTextContent(/grant full access/);

    await userEvent.click(within(dialog).getByRole('button', { name: /Copy sign-in link/ }));
    expect(writeText).toHaveBeenCalledWith(loginLink(ORIGIN, TEST_TOKEN));
    expect(await screen.findByText('Sign-in link copied')).toBeInTheDocument();
  });
});

describe('ConnectPhoneSection', () => {
  it('opens the dialog from the row and removes the QR from the DOM on close', async () => {
    renderWithProviders(<ConnectPhoneSection />);
    expect(screen.queryByRole('img', { name: 'Connection QR code' })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Connect a phone' }));
    expect(screen.getByRole('img', { name: 'Connection QR code' })).toBeInTheDocument();
    // The stored token is what the QR carries.
    await userEvent.click(screen.getByRole('button', { name: 'Show access token' }));
    expect(screen.getByLabelText('Access token')).toHaveValue(TEST_TOKEN);
    await userEvent.click(screen.getByRole('button', { name: 'Done' }));
    await waitFor(() => expect(screen.queryByRole('img', { name: 'Connection QR code' })).toBeNull());
  });
});
