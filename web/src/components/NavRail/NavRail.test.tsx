import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { NavRail } from './index';

const dests = [
  { key: 'recordings', label: 'Recordings', icon: 'graphic_eq' },
  { key: 'automations', label: 'Automations', icon: 'wand_stars' },
  { key: 'settings', label: 'Settings', icon: 'settings' },
] as const;

describe('NavRail', () => {
  it('marks the active destination and switches on click', async () => {
    const onChange = vi.fn();
    render(
      <NavRail
        destinations={[...dests]}
        value="recordings"
        onChange={onChange}
        footer={<button>Sign out</button>}
      />,
    );
    expect(screen.getByRole('navigation', { name: 'Sections' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Recordings' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('button', { name: 'Settings' })).not.toHaveAttribute('aria-current');
    await userEvent.click(screen.getByRole('button', { name: 'Automations' }));
    expect(onChange).toHaveBeenCalledWith('automations');
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Recordings' }).querySelector('svg')).toHaveAttribute(
      'width',
      '22',
    );
  });
});
