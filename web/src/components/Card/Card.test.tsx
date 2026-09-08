import { render, screen } from '@testing-library/react';
import { Card } from './index';

describe('Card', () => {
  it('renders a heading row with actions and body', () => {
    render(
      <Card title="Summary" actions={<button>Copy</button>}>
        Body text
      </Card>,
    );
    expect(screen.getByRole('heading', { level: 3, name: 'Summary' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy' })).toBeInTheDocument();
    expect(screen.getByText('Body text')).toBeInTheDocument();
  });

  it('applies tone, elevation and padding classes', () => {
    const { container } = render(
      <Card tone="high" elevation={2} padding="none" data-testid="c">
        x
      </Card>,
    );
    const el = container.firstElementChild!;
    expect(el.className).toContain('bg-card-raised');
    expect(el.className).toContain('shadow-e2');
    expect(el.className).not.toContain('px-5');
  });
});
