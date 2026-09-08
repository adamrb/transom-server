import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SnackbarProvider, useSnackbar } from './index';

function Trigger() {
  const snackbar = useSnackbar();
  return (
    <>
      <button onClick={() => snackbar.show('Transcript copied')}>copy</button>
      <button onClick={() => snackbar.error("Couldn't export the transcript.")}>fail</button>
      <button
        onClick={() =>
          snackbar.show('Deleted', { action: { label: 'Undo', onClick: () => snackbar.show('Restored') } })
        }
      >
        del
      </button>
    </>
  );
}

describe('Snackbar', () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  it('shows a message, replaces it, and hides after its duration', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(
      <SnackbarProvider>
        <Trigger />
      </SnackbarProvider>,
    );
    await user.click(screen.getByText('copy'));
    expect(screen.getByRole('status')).toHaveTextContent('Transcript copied');
    await user.click(screen.getByText('fail'));
    expect(screen.getByRole('status')).toHaveTextContent("Couldn't export the transcript.");
    expect(screen.getByRole('status')).toHaveAttribute('data-kind', 'error');
    act(() => vi.advanceTimersByTime(4100));
    expect(screen.getByRole('status')).toHaveTextContent('');
  });

  it('runs the action and dismisses', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(
      <SnackbarProvider>
        <Trigger />
      </SnackbarProvider>,
    );
    await user.click(screen.getByText('del'));
    await user.click(screen.getByRole('button', { name: 'Undo' }));
    expect(screen.getByRole('status')).toHaveTextContent('Restored');
  });
});
