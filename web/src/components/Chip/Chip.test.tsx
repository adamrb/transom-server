import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Chip, StatusChip } from './index';

describe('Chip', () => {
  it('filter chips expose a checkbox role and a check mark when selected', async () => {
    const onClick = vi.fn();
    const { rerender } = render(
      <Chip variant="filter" selected onClick={onClick}>
        All
      </Chip>,
    );
    const chip = screen.getByRole('checkbox', { name: 'All' });
    expect(chip).toBeChecked();
    expect(chip.querySelector('svg[data-icon="check"]')).toBeInTheDocument();
    await userEvent.click(chip);
    expect(onClick).toHaveBeenCalled();
    rerender(
      <Chip variant="filter" selected={false}>
        All
      </Chip>,
    );
    expect(screen.getByRole('checkbox', { name: 'All' })).not.toBeChecked();
    expect(chip.querySelector('svg')).toBeNull();
  });

  it('assist chips are plain buttons with an optional 16 px icon', () => {
    render(<Chip icon="content_copy">Copy transcript</Chip>);
    const chip = screen.getByRole('button', { name: 'Copy transcript' });
    expect(chip.querySelector('svg')).toHaveAttribute('width', '16');
  });

  it('status words carry their tone', () => {
    render(
      <>
        <StatusChip tone="inflight">Transcribing 42%</StatusChip>
        <StatusChip tone="failed" icon="error">
          Failed
        </StatusChip>
      </>,
    );
    expect(screen.getByText('Transcribing 42%')).toHaveAttribute('data-tone', 'inflight');
    expect(screen.getByText('Failed').querySelector('svg')).toHaveAttribute('width', '14');
  });
});
