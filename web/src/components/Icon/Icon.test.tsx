import { render, screen } from '@testing-library/react';
import { Icon, ICON_NAMES } from './index';
import { iconPath } from './icons';

describe('Icon', () => {
  it('renders a path for every registered glyph', () => {
    for (const name of ICON_NAMES) expect(iconPath(name).length).toBeGreaterThan(10);
  });

  it('is decorative by default and labelled on request', () => {
    const { rerender } = render(<Icon name="search" />);
    const svg = document.querySelector('svg')!;
    expect(svg).toHaveAttribute('aria-hidden', 'true');
    expect(svg).toHaveAttribute('width', '24');
    rerender(<Icon name="search" size={20} label="Search" />);
    expect(screen.getByRole('img', { name: 'Search' })).toHaveAttribute('width', '20');
  });
});
