import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AppShell, sectionForPath } from './AppShell';
import { EmbeddedProvider, parseEmbedded } from './EmbeddedProvider';
import { SectionAppBar } from './SectionAppBar';
import { normalizeLegacyHash } from './legacyHash';
import { appBridge, copyText, shareMarkdown } from './bridge';
import { AuthProvider } from '@/features/auth';
import { ThemeProvider } from '@/theme';
import { SnackbarProvider } from '@/components/Snackbar';
import { tokenStore } from '@/api/token';
import { makeTestQueryClient } from '@/test/render';
import { TEST_TOKEN } from '@/test/msw';
import * as bp from '@/lib/breakpoints';

function Page({ name }: { name: string }) {
  return (
    <>
      <SectionAppBar title={name} />
      <div>{name} body</div>
    </>
  );
}

function renderShell({ route = '/', search = '' } = {}) {
  tokenStore.set(TEST_TOKEN);
  return render(
    <QueryClientProvider client={makeTestQueryClient()}>
      <ThemeProvider search={search}>
        <EmbeddedProvider search={search}>
          <SnackbarProvider>
            <AuthProvider>
              <MemoryRouter initialEntries={[route]}>
                <Routes>
                  <Route element={<AppShell />}>
                    <Route path="/" element={<Page name="Recordings" />} />
                    <Route path="/rec/:id" element={<Page name="Recordings" />} />
                    <Route path="/automations" element={<Page name="Automations" />} />
                    <Route path="/settings" element={<Page name="Settings" />} />
                  </Route>
                </Routes>
              </MemoryRouter>
            </AuthProvider>
          </SnackbarProvider>
        </EmbeddedProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe('legacy hash and embedded params', () => {
  it('rewrites the old bare hashes to router hashes in place', () => {
    const replaceState = vi.fn();
    const hist = { replaceState, state: null } as unknown as History;
    expect(normalizeLegacyHash({ hash: '#rec/abc%20d', pathname: '/', search: '' } as Location, hist)).toBe(
      '#/rec/abc%20d',
    );
    expect(
      normalizeLegacyHash({ hash: '#automations', pathname: '/', search: '?embedded=1' } as Location, hist),
    ).toBe('#/automations');
    expect(normalizeLegacyHash({ hash: '#settings', pathname: '/', search: '' } as Location, hist)).toBe(
      '#/settings',
    );
    expect(normalizeLegacyHash({ hash: '#/rec/x', pathname: '/', search: '' } as Location, hist)).toBeNull();
    expect(
      normalizeLegacyHash({ hash: '#token=abc', pathname: '/', search: '' } as Location, hist),
    ).toBeNull();
    expect(replaceState).toHaveBeenLastCalledWith(null, '', '/#/settings');
  });

  it('parses embedded, tab and ignores tab when not embedded', () => {
    expect(parseEmbedded('?embedded=1&tab=settings')).toEqual({ embedded: true, initialTab: 'settings' });
    expect(parseEmbedded('?embedded=1&tab=bogus')).toEqual({ embedded: true, initialTab: null });
    expect(parseEmbedded('?tab=settings')).toEqual({ embedded: false, initialTab: null });
    expect(parseEmbedded('')).toEqual({ embedded: false, initialTab: null });
    expect(sectionForPath('/rec/1')).toBe('recordings');
    expect(sectionForPath('/automations')).toBe('automations');
  });
});

describe('AppShell', () => {
  afterEach(() => vi.restoreAllMocks());

  it('shows the rail with theme and sign-out on desktop and navigates between sections', async () => {
    vi.spyOn(bp, 'useIsDesktop').mockReturnValue(true);
    renderShell();
    expect(screen.getByRole('navigation', { name: 'Sections' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Recordings' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Automations' }));
    expect(screen.getByRole('heading', { level: 1, name: 'Automations' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Automations' })).toHaveAttribute('aria-current', 'page');
    await userEvent.click(screen.getByRole('button', { name: /Switch to dark theme/ }));
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(localStorage.getItem('pb_theme')).toBe('dark');
  });

  it('shows the bottom navigation and the app-bar theme toggle on phone', () => {
    vi.spyOn(bp, 'useIsDesktop').mockReturnValue(false);
    renderShell({ route: '/settings' });
    const nav = screen.getByRole('navigation', { name: 'Sections' });
    expect(nav.className).toContain('fixed');
    expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull();
    expect(screen.getByRole('button', { name: /Switch to/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Settings' })).toBeInTheDocument();
  });

  it('draws no chrome when embedded, honours tab= and does not persist theme=', async () => {
    vi.spyOn(bp, 'useIsDesktop').mockReturnValue(false);
    renderShell({ search: '?embedded=1&tab=automations&theme=dark' });
    await waitFor(() => expect(screen.getByText('Automations body')).toBeInTheDocument());
    expect(screen.queryByRole('navigation')).toBeNull();
    expect(screen.queryByRole('banner')).toBeNull();
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(localStorage.getItem('pb_theme')).toBeNull();
    const app = document.getElementById('app')!;
    expect(app.style.getPropertyValue('--content-bottom-pad')).toBe('120px');
    expect(document.documentElement.hasAttribute('data-embedded')).toBe(true);
  });

  it('keeps a deep link over tab= when embedded', async () => {
    vi.spyOn(bp, 'useIsDesktop').mockReturnValue(false);
    renderShell({ route: '/rec/abc', search: '?embedded=1&tab=settings' });
    expect(screen.getByText('Recordings body')).toBeInTheDocument();
  });
});

describe('native bridge', () => {
  afterEach(() => {
    delete window.TransomApp;
  });

  it('detects the Android bridge exactly like the old dashboard', () => {
    expect(appBridge()).toBeNull();
    window.TransomApp = { copyText: vi.fn(), shareMarkdown: vi.fn() };
    expect(appBridge()).toBe(window.TransomApp);
  });

  it('copies through the clipboard, else the bridge; shares through the bridge, else downloads', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    expect(await copyText('hello')).toBe('copied');
    expect(writeText).toHaveBeenCalledWith('hello');

    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
    const copy = vi.fn();
    const share = vi.fn();
    window.TransomApp = { copyText: copy, shareMarkdown: share };
    expect(await copyText('hi')).toBe('bridge');
    expect(copy).toHaveBeenCalledWith('hi');
    expect(shareMarkdown('t.md', '# T')).toBe('bridge');
    expect(share).toHaveBeenCalledWith('t.md', '# T');

    delete window.TransomApp;
    const createObjectURL = vi.fn(() => 'blob:x');
    const revokeObjectURL = vi.fn();
    Object.assign(URL, { createObjectURL, revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    expect(shareMarkdown('t.md', '# T')).toBe('downloaded');
    expect(click).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:x');
  });
});
