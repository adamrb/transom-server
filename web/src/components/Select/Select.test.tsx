import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { Select } from './index';

type Id = 'a' | 'b' | 'c';
const OPTIONS = [
  { value: 'a' as Id, label: 'Alpha', description: 'First' },
  { value: 'b' as Id, label: 'Beta' },
  { value: 'c' as Id, label: 'Gamma', disabled: true },
];

function Harness({ inDialog }: { inDialog?: boolean }) {
  const [v, setV] = useState<Id | null>('b');
  const select = <Select<Id> label="Recording" value={v} onChange={setV} options={OPTIONS} />;
  if (!inDialog) return select;
  return <dialog open>{select}</dialog>;
}

describe('Select', () => {
  it('is a combobox showing the chosen label and opens a listbox with the selection checked', async () => {
    render(<Harness />);
    const combo = screen.getByRole('combobox', { name: 'Recording' });
    expect(combo).toHaveTextContent('Beta');
    expect(combo).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(combo);
    const list = screen.getByRole('listbox', { name: 'Recording' });
    const options = within(list).getAllByRole('option');
    expect(options).toHaveLength(3);
    expect(within(list).getByRole('option', { name: /Beta/ })).toHaveAttribute('aria-selected', 'true');
    expect(within(list).getByRole('option', { name: /Beta/ })).toHaveFocus();
    expect(within(list).getByRole('option', { name: /Gamma/ })).toBeDisabled();
    expect(screen.getByText('First')).toBeInTheDocument();
  });

  it('points aria-controls at the listbox and returns focus on Escape', async () => {
    render(<Harness />);
    const combo = screen.getByRole('combobox', { name: 'Recording' });
    await userEvent.click(combo);
    const list = screen.getByRole('listbox', { name: 'Recording' });
    expect(combo).toHaveAttribute('aria-controls', list.id);
    expect(list.id).not.toBe('');
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('listbox')).toBeNull();
    expect(combo).toHaveFocus();
  });

  it('changes the value on click and returns focus to the combobox', async () => {
    render(<Harness />);
    const combo = screen.getByRole('combobox', { name: 'Recording' });
    await userEvent.click(combo);
    await userEvent.click(screen.getByRole('option', { name: /Alpha/ }));
    expect(screen.queryByRole('listbox')).toBeNull();
    expect(combo).toHaveTextContent('Alpha');
    expect(combo).toHaveAttribute('data-value', 'a');
    expect(combo).toHaveFocus();
  });

  it('shows the placeholder and disables itself without options', () => {
    render(<Select label="Recording" value={null} onChange={() => {}} options={[]} placeholder="Loading…" />);
    const combo = screen.getByRole('combobox', { name: 'Recording' });
    expect(combo).toHaveTextContent('Loading…');
    expect(combo).toBeDisabled();
  });

  it('portals the list into the surrounding open dialog', async () => {
    render(<Harness inDialog />);
    await userEvent.click(screen.getByRole('combobox', { name: 'Recording' }));
    const list = screen.getByRole('listbox', { name: 'Recording' });
    expect(list.closest('dialog')).not.toBeNull();
  });
});
