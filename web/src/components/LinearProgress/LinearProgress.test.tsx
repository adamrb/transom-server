import { render, screen } from '@testing-library/react';
import { LinearProgress } from './index';

describe('LinearProgress', () => {
  it('is indeterminate without a value', () => {
    render(<LinearProgress label="Loading" />);
    const bar = screen.getByRole('progressbar', { name: 'Loading' });
    expect(bar).toHaveAttribute('data-indeterminate', 'true');
    expect(bar).not.toHaveAttribute('aria-valuenow');
  });

  it('reports and draws a determinate value', () => {
    render(<LinearProgress value={0.5} />);
    const bar = screen.getByRole('progressbar');
    expect(bar).toHaveAttribute('aria-valuenow', '50');
    expect((bar.firstElementChild as HTMLElement).style.width).toBe('50%');
  });
});
