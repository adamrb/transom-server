import { render, screen } from '@testing-library/react';
import { Markdown } from './index';

describe('Markdown', () => {
  it('renders GFM with bold, lists and headings, and never raw HTML', () => {
    render(
      <Markdown
        headingIds
      >{`## Decisions\n\n**Ship it** on Monday.\n\n- one\n- two\n\n<script>alert(1)</script>`}</Markdown>,
    );
    const h = screen.getByRole('heading', { name: 'Decisions' });
    expect(h.tagName).toBe('H4');
    expect(h).toHaveAttribute('id', 'sum-h-0');
    expect(screen.getByText('Ship it').tagName).toBe('STRONG');
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(document.querySelector('script')).toBeNull();
    expect(screen.queryByText(/alert/)).toBeNull();
  });

  it('opens links in a new tab and drops images', () => {
    render(<Markdown>{`[site](https://example.com) ![x](https://example.com/x.png)`}</Markdown>);
    const a = screen.getByRole('link', { name: 'site' });
    expect(a).toHaveAttribute('target', '_blank');
    expect(a).toHaveAttribute('rel', 'noopener noreferrer');
    expect(document.querySelector('img')).toBeNull();
  });
});
