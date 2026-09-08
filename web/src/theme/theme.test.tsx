import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ThemeProvider, useTheme, normalizeTheme } from './ThemeProvider';

function Probe() {
  const { theme, resolved, setTheme, toggle, forced } = useTheme();
  return (
    <>
      <div data-testid="theme">{theme}</div>
      <div data-testid="resolved">{resolved}</div>
      <div data-testid="forced">{String(forced)}</div>
      <button onClick={() => setTheme('dark')}>dark</button>
      <button onClick={() => setTheme('system')}>system</button>
      <button onClick={toggle}>toggle</button>
    </>
  );
}

describe('ThemeProvider', () => {
  afterEach(() => document.documentElement.setAttribute('data-theme', 'system'));

  it('normalizes values', () => {
    expect(normalizeTheme('dark')).toBe('dark');
    expect(normalizeTheme('purple')).toBe('system');
    expect(normalizeTheme(null)).toBe('system');
  });

  it('starts from the saved choice, writes data-theme, persists changes, toggles', async () => {
    localStorage.setItem('pb_theme', 'dark');
    document.documentElement.setAttribute('data-theme', 'dark'); // what the pre-paint script did
    render(
      <ThemeProvider search="">
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId('theme')).toHaveTextContent('dark');
    expect(screen.getByTestId('resolved')).toHaveTextContent('dark');
    await userEvent.click(screen.getByText('toggle'));
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(localStorage.getItem('pb_theme')).toBe('light');
    await userEvent.click(screen.getByText('system'));
    expect(screen.getByTestId('theme')).toHaveTextContent('system');
    expect(screen.getByTestId('resolved')).toHaveTextContent('light'); // jsdom matchMedia stub: not dark
  });

  it('honours ?theme= without saving it', async () => {
    render(
      <ThemeProvider search="?theme=dark">
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId('forced')).toHaveTextContent('true');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    await userEvent.click(screen.getByText('toggle'));
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(localStorage.getItem('pb_theme')).toBeNull();
  });
});
