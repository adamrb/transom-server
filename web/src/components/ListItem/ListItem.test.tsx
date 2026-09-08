import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ListItem } from './index';

describe('ListItem', () => {
  it('renders headline, supporting, leading and trailing', () => {
    render(
      <ListItem
        leading={<span data-testid="lead" />}
        headline="Standup"
        supporting="9:05 AM · 24m"
        trailing="2"
      />,
    );
    expect(screen.getByText('Standup')).toBeInTheDocument();
    expect(screen.getByText('9:05 AM · 24m')).toBeInTheDocument();
    expect(screen.getByTestId('lead')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('is keyboard operable when clickable and reflects selection', async () => {
    const onClick = vi.fn();
    render(<ListItem headline="Row" onClick={onClick} selected />);
    const row = screen.getByRole('button', { name: 'Row' });
    expect(row).toHaveAttribute('tabindex', '0');
    expect(row).toHaveAttribute('aria-selected', 'true');
    row.focus();
    await userEvent.keyboard('{Enter}');
    await userEvent.keyboard(' ');
    await userEvent.click(row);
    expect(onClick).toHaveBeenCalledTimes(3);
  });

  it('is not focusable when static', () => {
    render(<ListItem headline="Static" />);
    expect(screen.getByText('Static').closest('[role="button"]')).toBeNull();
  });
});
