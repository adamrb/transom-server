import { render, screen } from '@testing-library/react';
import { TopAppBar } from './index';

describe('TopAppBar', () => {
  it('renders a large h1 section title with actions', () => {
    render(<TopAppBar title="Recordings" actions={<button>Theme</button>} />);
    const h = screen.getByRole('heading', { level: 1, name: 'Recordings' });
    expect(h.className).toContain('text-headline-l');
    expect(screen.getByRole('button', { name: 'Theme' })).toBeInTheDocument();
    expect(screen.getByRole('banner')).toBeInTheDocument();
  });

  it('renders a small bar with a leading element and a lower heading level', () => {
    render(<TopAppBar variant="small" as="h2" title="Detail" leading={<button>Back</button>} scrolled />);
    expect(screen.getByRole('heading', { level: 2, name: 'Detail' }).className).toContain('text-title-l');
    expect(screen.getByRole('button', { name: 'Back' })).toBeInTheDocument();
    expect(screen.getByRole('banner').className).toContain('bg-surface-container');
  });
});
