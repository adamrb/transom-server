import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BottomNav } from './index';

describe('BottomNav', () => {
  it('renders the destinations with the active one current', async () => {
    const onChange = vi.fn();
    render(
      <BottomNav
        destinations={[
          { key: 'recordings', label: 'Recordings', icon: 'graphic_eq' },
          { key: 'settings', label: 'Settings', icon: 'settings' },
        ]}
        value="settings"
        onChange={onChange}
      />,
    );
    expect(screen.getByRole('button', { name: 'Settings' })).toHaveAttribute('aria-current', 'page');
    await userEvent.click(screen.getByRole('button', { name: 'Recordings' }));
    expect(onChange).toHaveBeenCalledWith('recordings');
  });
});
