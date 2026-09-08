import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SnackbarProvider } from '@/components/Snackbar';
import { CopyField } from './index';

function wrap(ui: React.ReactElement) {
  return render(<SnackbarProvider>{ui}</SnackbarProvider>);
}

describe('CopyField', () => {
  it('shows a labelled read-only value and copies it', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    wrap(<CopyField label="Server address" value="https://pb.example" copiedMessage="Address copied" />);
    const input = screen.getByLabelText('Server address') as HTMLInputElement;
    expect(input).toHaveValue('https://pb.example');
    expect(input).toHaveAttribute('readonly');
    await userEvent.click(screen.getByRole('button', { name: 'Copy server address' }));
    expect(writeText).toHaveBeenCalledWith('https://pb.example');
    expect(await screen.findByText('Address copied')).toBeInTheDocument();
  });

  it('masks a secret until revealed', async () => {
    wrap(<CopyField label="Token" value="abcdefgh" secret />);
    const input = screen.getByLabelText('Token') as HTMLInputElement;
    expect(input.value).toBe('••••••••');
    expect(input).toHaveAttribute('data-masked', 'true');
    await userEvent.click(screen.getByRole('button', { name: 'Show token' }));
    expect(input.value).toBe('abcdefgh');
    expect(screen.getByRole('button', { name: 'Hide token' })).toBeInTheDocument();
  });
});
