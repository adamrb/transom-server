import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { RadioGroup } from './index';

type Kind = 'webhook' | 'markdown' | 'none';

function Harness({ disabled }: { disabled?: boolean }) {
  const [kind, setKind] = useState<Kind>('webhook');
  return (
    <RadioGroup<Kind>
      label="What happens"
      value={kind}
      onChange={setKind}
      disabled={disabled}
      options={[
        {
          key: 'webhook',
          label: 'Send it to the agent',
          description: 'A request to a web address.',
          icon: 'send',
        },
        { key: 'markdown', label: 'Save a note in a folder', icon: 'description' },
        { key: 'none', label: 'Just record the decision', disabled: true },
      ]}
    />
  );
}

describe('RadioGroup', () => {
  it('is a labelled radiogroup with one checked radio and descriptions', () => {
    render(<Harness />);
    expect(screen.getByRole('radiogroup', { name: 'What happens' })).toBeInTheDocument();
    const radios = screen.getAllByRole('radio');
    expect(radios).toHaveLength(3);
    expect(screen.getByRole('radio', { name: /Send it to the agent/ })).toBeChecked();
    expect(screen.getByText('A request to a web address.')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Just record/ })).toBeDisabled();
  });

  it('selects on click and moves with the arrow keys', async () => {
    render(<Harness />);
    await userEvent.click(screen.getByText('Save a note in a folder'));
    expect(screen.getByRole('radio', { name: /Save a note/ })).toBeChecked();
    expect(screen.getByRole('radio', { name: /Send it/ })).not.toBeChecked();
    screen.getByRole('radio', { name: /Save a note/ }).focus();
    await userEvent.keyboard('{ArrowUp}');
    expect(screen.getByRole('radio', { name: /Send it/ })).toBeChecked();
  });

  it('disables the whole group', () => {
    render(<Harness disabled />);
    for (const r of screen.getAllByRole('radio')) expect(r).toBeDisabled();
  });
});
