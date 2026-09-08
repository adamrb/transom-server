import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import { AuthProvider } from '@/features/auth';
import { EmbeddedProvider } from '@/features/shell';
import { SettingsPage } from './SettingsPage';

describe('SettingsPage', () => {
  it('offers the theme choice and a sign-out on every width', async () => {
    renderWithProviders(
      <EmbeddedProvider search="">
        <AuthProvider>
          <SettingsPage />
        </AuthProvider>
      </EmbeddedProvider>,
    );
    expect(screen.getByRole('radiogroup', { name: 'Theme' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'Dark' }));
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    await waitFor(() => expect(localStorage.getItem('pb_token')).toBeNull());
  });
});
