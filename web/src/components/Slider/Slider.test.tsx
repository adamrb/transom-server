import { fireEvent, render, screen } from '@testing-library/react';
import { Slider } from './index';

describe('Slider', () => {
  it('exposes a range input with value text and markers', () => {
    render(
      <Slider
        value={30}
        max={120}
        markers={[10, 60]}
        onChange={() => {}}
        label="Position"
        formatValue={(v) => `${v}s`}
      />,
    );
    const input = screen.getByRole('slider', { name: 'Position' });
    expect(input).toHaveValue('30');
    expect(input).toHaveAttribute('aria-valuetext', '30s');
    expect(document.querySelectorAll('[data-marker]')).toHaveLength(2);
    expect((document.querySelector('[data-handle]') as HTMLElement).style.left).toBe('25%');
  });

  it('draws the buffered range from the handle to the buffered end', () => {
    const { rerender } = render(
      <Slider value={20} max={100} buffered={60} onChange={() => {}} label="Position" />,
    );
    const bar = document.querySelector('[data-buffered]') as HTMLElement;
    expect(bar.style.left).toBe('20%');
    expect(bar.style.width).toBe('40%');
    // nothing behind the playhead
    rerender(<Slider value={70} max={100} buffered={60} onChange={() => {}} label="Position" />);
    expect(document.querySelector('[data-buffered]')).toBeNull();
  });

  it('previews on change and commits on release', () => {
    const onChange = vi.fn();
    const onCommit = vi.fn();
    render(<Slider value={0} max={100} onChange={onChange} onCommit={onCommit} label="Position" />);
    const input = screen.getByRole('slider');
    fireEvent.pointerDown(input);
    fireEvent.change(input, { target: { value: '40' } });
    expect(onChange).toHaveBeenCalledWith(40);
    expect(onCommit).not.toHaveBeenCalled();
    fireEvent.pointerUp(input);
    expect(onCommit).toHaveBeenCalledTimes(1);
    fireEvent.keyUp(input, { key: 'ArrowRight' });
    expect(onCommit).toHaveBeenCalledTimes(2);
  });
});
