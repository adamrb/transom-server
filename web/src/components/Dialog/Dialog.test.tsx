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

  it('sizes the card: sm 400, md 560, lg 720', () => {
    const { rerender } = render(<Dialog open onClose={() => {}} title="T" />);
    const dlg = () => screen.getByRole('dialog');
    expect(dlg()).toHaveAttribute('data-size', 'sm');
    expect(dlg().className).toContain('w-[400px]');
    rerender(<Dialog open onClose={() => {}} title="T" size="md" />);
    expect(dlg().className).toContain('w-[560px]');
    rerender(<Dialog open onClose={() => {}} title="T" size="lg" />);
    expect(dlg().className).toContain('w-[720px]');
    expect(dlg()).toHaveAttribute('data-presentation', 'dialog');
  });

  it('goes full screen on phone with a top bar: close glyph, title, actions', async () => {
    // jsdom's matchMedia never matches, so the breakpoint reads as phone.
    const onClose = vi.fn();
    render(
      <Dialog open fullScreen onClose={onClose} title="New rule" actions={<button>Save</button>}>
        <p>Form</p>
      </Dialog>,
    );
    const dlg = screen.getByRole('dialog', { name: 'New rule' });
    expect(dlg).toHaveAttribute('data-presentation', 'fullscreen');
    expect(dlg.className).not.toContain('w-[400px]');
    const bar = dlg.firstElementChild as HTMLElement;
    expect(bar).toContainElement(screen.getByRole('button', { name: 'Close' }));
    expect(bar).toContainElement(screen.getByRole('button', { name: 'Save' }));
    await userEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalled();
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
    expect(del).toHaveAttribute('data-variant', 'danger-filled');
    expect(del.className).toContain('bg-error');
    expect(del.className).not.toContain('bg-primary');
    await userEvent.click(del);
    expect(onConfirm).toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalled();
  });
});
