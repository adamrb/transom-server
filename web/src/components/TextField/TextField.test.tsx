import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TextField } from './index';

describe('TextField', () => {
  it('links label, helper and error state to the input', async () => {
    const onChange = vi.fn();
    render(<TextField label="Name" helper="Type a name." error onChange={onChange} />);
    const input = screen.getByLabelText('Name');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAccessibleDescription('Type a name.');
    await userEvent.type(input, 'Ab');
    expect(onChange).toHaveBeenCalledTimes(2);
  });

  it('renders icon, trailing element and small size', () => {
    render(<TextField icon="search" size="sm" placeholder="Find" trailing={<button>Clear</button>} />);
    expect(screen.getByPlaceholderText('Find')).toBeInTheDocument();
    expect(document.querySelector('svg[data-icon="search"]')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Clear' })).toBeInTheDocument();
  });

  it('renders a tonal mono textarea when multiline', () => {
    render(<TextField multiline tonal mono label="Vocabulary" defaultValue="Alex" />);
    const ta = screen.getByLabelText('Vocabulary');
    expect(ta.tagName).toBe('TEXTAREA');
    expect(ta.className).toContain('font-mono');
    expect(ta.className).toContain('bg-surface-container-high');
  });
});
