import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button } from './index';

describe('Button', () => {
  it('renders every variant with its data attribute', () => {
    render(
      <>
        <Button variant="filled">Filled</Button>
        <Button variant="tonal">Tonal</Button>
        <Button variant="outlined">Outlined</Button>
        <Button variant="text">Text</Button>
        <Button variant="danger">Danger</Button>
      </>,
    );
    for (const v of ['filled', 'tonal', 'outlined', 'text', 'danger']) {
      expect(screen.getByRole('button', { name: new RegExp(v, 'i') })).toHaveAttribute('data-variant', v);
    }
  });

  it('fires onClick, and not while loading or disabled', async () => {
    const onClick = vi.fn();
    const { rerender } = render(<Button onClick={onClick}>Go</Button>);
    await userEvent.click(screen.getByRole('button', { name: 'Go' }));
    expect(onClick).toHaveBeenCalledTimes(1);
    rerender(
      <Button onClick={onClick} loading>
        Go
      </Button>,
    );
    const busy = screen.getByRole('button', { name: 'Go' });
    expect(busy).toBeDisabled();
    expect(busy).toHaveAttribute('aria-busy', 'true');
  });

  it('shows a leading icon and defaults to type=button', () => {
    render(
      <Button icon="add" variant="tonal">
        Add rule
      </Button>,
    );
    const btn = screen.getByRole('button', { name: 'Add rule' });
    expect(btn).toHaveAttribute('type', 'button');
    expect(btn.querySelector('svg[data-icon="add"]')).toBeInTheDocument();
  });
});
