import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConfirmDialog, Dialog } from './index';

describe('Dialog', () => {
  it('renders title, body and actions when open and nothing when closed', () => {
    const { rerender } = render(
      <Dialog open onClose={() => {}} title="Rename" actions={<button>Save</button>}>
        <p>Body</p>
      </Dialog>,
    );
    expect(screen.getByRole('dialog', { name: 'Rename' })).toBeInTheDocument();
    expect(screen.getByText('Body')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();
    rerender(<Dialog open={false} onClose={() => {}} title="Rename" />);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('confirm dialog wires both buttons and marks destructive confirms', async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Delete recording?"
        ok="Delete"
        danger
        onConfirm={onConfirm}
        onCancel={onCancel}
      >
        <p>This cannot be undone.</p>
      </ConfirmDialog>,
    );
    const del = screen.getByRole('button', { name: 'Delete' });
    expect(del.className).toContain('bg-error');
    await userEvent.click(del);
    expect(onConfirm).toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalled();
  });
});
