import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import { AuthProvider } from '@/features/auth';
import { EmbeddedProvider } from '@/features/shell';
import { SettingsPage } from './SettingsPage';

function renderPage(search = '') {
  return renderWithProviders(
    <EmbeddedProvider search={search}>
      <AuthProvider>
        <SettingsPage />
      </AuthProvider>
    </EmbeddedProvider>,
  );
}

describe('SettingsPage', () => {
  it('stacks every section in order and keeps sign out last', async () => {
    renderPage();
    const heads = await screen.findAllByRole('heading', { level: 2 });
    expect(heads.map((h) => h.textContent)).toEqual([
      'Appearance',
      'Vocabulary',
      'Signed-in computers',
      'Phone',
      'Android app',
      'This computer',
    ]);
    expect(screen.getByRole('heading', { level: 1, name: 'Settings' })).toBeInTheDocument();
  });

  it('offers the theme choice and a sign-out on every width', async () => {
    renderPage();
    expect(screen.getByRole('radiogroup', { name: 'Theme' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'Dark' }));
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    const thisComputer = screen.getByRole('heading', { name: 'This computer' }).closest('section')!;
    await userEvent.click(within(thisComputer).getByRole('button', { name: 'Sign out' }));
    await waitFor(() => expect(localStorage.getItem('pb_token')).toBeNull());
  });

  it('renders without a section app bar when embedded', async () => {
    renderPage('?embedded=1&tab=settings');
    await screen.findByRole('heading', { level: 2, name: 'Vocabulary' });
    expect(screen.queryByRole('heading', { level: 1 })).toBeNull();
  });
});
