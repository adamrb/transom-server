import { render, screen } from '@testing-library/react';
import { EmptyState } from './index';

describe('EmptyState', () => {
  it('renders glyph, headline, description and action', () => {
    render(
      <EmptyState
        icon="qr_code"
        headline="No recordings yet"
        description="Recordings sync from the app."
        action={<button>Connect a phone</button>}
      />,
    );
    expect(screen.getByRole('heading', { name: 'No recordings yet' })).toBeInTheDocument();
    expect(screen.getByText('Recordings sync from the app.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Connect a phone' })).toBeInTheDocument();
    expect(document.querySelector('svg[data-icon="qr_code"]')).toBeInTheDocument();
  });

  it('has a compact variant', () => {
    render(<EmptyState compact headline="Coming soon" />);
    expect(screen.getByRole('heading', { name: 'Coming soon' }).className).toContain('text-title-m');
  });
});
