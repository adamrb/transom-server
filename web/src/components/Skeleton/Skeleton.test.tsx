import { render } from '@testing-library/react';
import { Skeleton, SkeletonListItem, SkeletonText } from './index';

describe('Skeleton', () => {
  it('sizes itself and is hidden from assistive tech', () => {
    const { container } = render(<Skeleton width={120} height={12} shape="circle" />);
    const el = container.firstElementChild as HTMLElement;
    expect(el).toHaveAttribute('aria-hidden', 'true');
    expect(el.style.width).toBe('120px');
    expect(el.style.height).toBe('12px');
    expect(el.className).toContain('rounded-full');
  });

  it('composes list rows and text lines', () => {
    const { container } = render(
      <>
        <SkeletonListItem />
        <SkeletonText lines={4} />
      </>,
    );
    expect(container.querySelectorAll('[data-skeleton]')).toHaveLength(3 + 4);
  });
});
