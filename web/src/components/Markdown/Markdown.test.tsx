import { render, screen } from '@testing-library/react';
import { Markdown } from './index';

describe('Markdown', () => {
  it('renders GFM with bold, lists and headings, and never raw HTML', async () => {
    render(
      <Markdown
        headingIds
      >{`## Decisions\n\n**Ship it** on Monday.\n\n- one\n- two\n\n<script>alert(1)</script>`}</Markdown>,
    );
    // the renderer is loaded on demand; the plain text shows meanwhile
    const h = await screen.findByRole('heading', { name: 'Decisions' });
    expect(h.tagName).toBe('H4');
    expect(h).toHaveAttribute('id', 'sum-h-0');
    expect(screen.getByText('Ship it').tagName).toBe('STRONG');
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(document.querySelector('script')).toBeNull();
    expect(screen.queryByText(/alert/)).toBeNull();
  });

  it('shows the text as paragraphs while the renderer loads', () => {
    render(<Markdown>{`First paragraph.\n\nSecond paragraph.`}</Markdown>);
    // synchronously, before the lazy chunk resolves
    expect(screen.getByText('First paragraph.')).toBeInTheDocument();
    expect(screen.getByText('Second paragraph.')).toBeInTheDocument();
  });

  it('opens links in a new tab and drops images', async () => {
    render(<Markdown>{`[site](https://example.com) ![x](https://example.com/x.png)`}</Markdown>);
    const a = await screen.findByRole('link', { name: 'site' });
    expect(a).toHaveAttribute('target', '_blank');
    expect(a).toHaveAttribute('rel', 'noopener noreferrer');
    expect(document.querySelector('img')).toBeNull();
  });
});
