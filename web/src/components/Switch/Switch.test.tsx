import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Switch } from './index';

describe('Switch', () => {
  it('is a labelled switch that reports changes', async () => {
    const onChange = vi.fn();
    render(<Switch checked={false} onChange={onChange} label="Turn “Ask Claude” on or off" />);
    const sw = screen.getByRole('switch', { name: 'Turn “Ask Claude” on or off' });
    expect(sw).not.toBeChecked();
    await userEvent.click(sw);
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it('shows the check mark when on and ignores clicks when disabled', async () => {
    const onChange = vi.fn();
    render(<Switch checked onChange={onChange} label="Rule" disabled />);
    expect(document.querySelector('svg[data-icon="check"]')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('switch'));
    expect(onChange).not.toHaveBeenCalled();
  });
});
