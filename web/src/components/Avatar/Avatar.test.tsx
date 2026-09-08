import { render, screen } from '@testing-library/react';
import { Avatar } from './index';

describe('Avatar', () => {
  it('picks the glyph for each finished/failed kind', () => {
    const { container } = render(
      <>
        <Avatar kind="waveform" />
        <Avatar kind="group" />
        <Avatar kind="silent" />
        <Avatar kind="failed" />
        <Avatar kind="icon" icon="palette" />
        <Avatar kind="text" text="1" />
      </>,
    );
    const icons = [...container.querySelectorAll('svg[data-icon]')].map((s) => s.getAttribute('data-icon'));
    expect(icons).toEqual(['graphic_eq', 'group', 'volume_off', 'error', 'palette']);
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(container.querySelector('[data-kind="failed"]')!.className).toContain('bg-error-container');
  });

  it('renders rings for waiting and progress', () => {
    render(
      <>
        <Avatar kind="waiting" label="Waiting" />
        <Avatar kind="progress" value={0.42} label="Transcribing" />
      </>,
    );
    expect(screen.getByRole('progressbar', { name: 'Waiting' })).toHaveAttribute(
      'data-indeterminate',
      'true',
    );
    expect(screen.getByRole('progressbar', { name: 'Transcribing' })).toHaveAttribute('aria-valuenow', '42');
    expect(screen.getByText('42%')).toBeInTheDocument();
  });
});
