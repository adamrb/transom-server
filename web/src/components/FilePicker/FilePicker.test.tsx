import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { FilePicker } from './index';

function Harness() {
  const [file, setFile] = useState<File | null>(null);
  return <FilePicker label="Text file" accept=".txt" file={file} onChange={setFile} helper="Plain text." />;
}

describe('FilePicker', () => {
  it('has a labelled native input and reports the chosen file', async () => {
    render(<Harness />);
    const input = screen.getByLabelText('Text file') as HTMLInputElement;
    expect(input.type).toBe('file');
    expect(input).toHaveAttribute('accept', '.txt');
    expect(screen.getByText('No file chosen')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Choose a file' })).toBeInTheDocument();
    expect(screen.getByText('Plain text.')).toBeInTheDocument();
    await userEvent.upload(input, new File(['a'], 'terms.txt', { type: 'text/plain' }));
    expect(screen.getByText('terms.txt')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Change file' })).toBeInTheDocument();
  });

  it('shows an error helper', () => {
    render(<FilePicker label="App file" file={null} onChange={() => {}} error helper="Pick an .apk file." />);
    expect(screen.getByText('Pick an .apk file.').className).toContain('text-error');
    expect(screen.getByLabelText('App file')).toHaveAttribute('aria-invalid', 'true');
  });
});
