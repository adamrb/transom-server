import { render, screen } from '@testing-library/react';
import { ProgressRing } from './index';

describe('ProgressRing', () => {
  it('reports a determinate value and shows it on request', () => {
    render(<ProgressRing value={0.42} showValue label="Transcribing" />);
    const bar = screen.getByRole('progressbar', { name: 'Transcribing' });
    expect(bar).toHaveAttribute('aria-valuenow', '42');
    expect(screen.getByText('42%')).toBeInTheDocument();
  });

  it('is indeterminate without a value and clamps out-of-range values', () => {
    const { rerender } = render(<ProgressRing />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('data-indeterminate', 'true');
    rerender(<ProgressRing value={1.7} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100');
  });
});
