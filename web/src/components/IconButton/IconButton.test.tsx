import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { IconButton } from './index';

describe('IconButton', () => {
  it('is named by its label and reports a toggle state', () => {
    render(<IconButton icon="more_vert" label="More" selected />);
    const btn = screen.getByRole('button', { name: 'More' });
    expect(btn).toHaveAttribute('aria-pressed', 'true');
    expect(btn).toHaveAttribute('title', 'More');
    expect(btn.querySelector('svg[data-icon="more_vert"]')).toHaveAttribute('width', '20');
  });

  it('honours size and iconSize overrides and clicks', async () => {
    const onClick = vi.fn();
    render(<IconButton icon="play_arrow" label="Play" size="lg" variant="filled" onClick={onClick} />);
    const btn = screen.getByRole('button', { name: 'Play' });
    expect(btn.querySelector('svg')).toHaveAttribute('width', '28');
    await userEvent.click(btn);
    expect(onClick).toHaveBeenCalled();
    render(<IconButton icon="graphic_eq" label="Recordings" iconSize={22} noTitle />);
    const rail = screen.getByRole('button', { name: 'Recordings' });
    expect(rail).not.toHaveAttribute('title');
    expect(rail.querySelector('svg')).toHaveAttribute('width', '22');
  });
});
