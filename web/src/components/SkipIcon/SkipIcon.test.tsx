import { render } from '@testing-library/react';
import { SkipIcon } from './index';

describe('SkipIcon', () => {
  it('draws the replay arrow with the seconds inside, mirrored for forward', () => {
    const { container, rerender } = render(<SkipIcon seconds={15} direction="back" />);
    const box = container.querySelector('[data-skip="back"]') as HTMLElement;
    expect(box).toHaveAttribute('aria-hidden');
    expect(box).toHaveTextContent('15');
    expect(box.querySelector('svg[data-icon="replay"]')).toHaveAttribute('width', '24');
    expect(box.querySelector('svg')!.className.baseVal).not.toContain('-scale-x-100');
    rerender(<SkipIcon seconds={30} direction="forward" size={28} />);
    const fwd = container.querySelector('[data-skip="forward"]') as HTMLElement;
    expect(fwd).toHaveTextContent('30');
    expect(fwd.querySelector('svg')!.className.baseVal).toContain('-scale-x-100');
    expect(fwd.querySelector('svg')).toHaveAttribute('width', '28');
  });
});
