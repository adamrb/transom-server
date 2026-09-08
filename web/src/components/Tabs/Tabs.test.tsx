import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { Tabs } from './index';

function Harness() {
  const [v, setV] = useState<'a' | 'b' | 'c'>('a');
  return (
    <Tabs
      label="Sections"
      value={v}
      onChange={setV}
      tabs={[
        { key: 'a', label: 'Summary' },
        { key: 'b', label: 'Transcript' },
        { key: 'c', label: 'Off', disabled: true },
      ]}
    />
  );
}

describe('Tabs', () => {
  it('selects on click and moves with arrow keys, skipping disabled tabs', async () => {
    render(<Harness />);
    const a = screen.getByRole('tab', { name: 'Summary' });
    const b = screen.getByRole('tab', { name: 'Transcript' });
    expect(a).toHaveAttribute('aria-selected', 'true');
    expect(b).toHaveAttribute('tabindex', '-1');
    await userEvent.click(b);
    expect(b).toHaveAttribute('aria-selected', 'true');
    b.focus();
    await userEvent.keyboard('{ArrowRight}');
    expect(a).toHaveAttribute('aria-selected', 'true');
    expect(a).toHaveFocus();
    await userEvent.keyboard('{End}');
    expect(b).toHaveAttribute('aria-selected', 'true');
  });
});
