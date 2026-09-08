import { memo, type ComponentProps } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { MarkdownProps } from './index';

type MdComponents = NonNullable<ComponentProps<typeof ReactMarkdown>['components']>;

/**
 * The real renderer (react-markdown + remark-gfm, about 40 KB gzipped), loaded on demand by
 * `Markdown`. Raw HTML is never rendered (react-markdown escapes it). Links open in a new tab.
 * Body text is 15/24 on-surface-body, bold is on-surface 500 (the app's summary style).
 */
const MarkdownRenderer = memo(function MarkdownRenderer({ children, headingIds }: MarkdownProps) {
  let seq = 0;
  const heading = (Tag: 'h4') =>
    function Heading(props: ComponentProps<'h4'>) {
      const id = headingIds ? `sum-h-${seq++}` : undefined;
      return <Tag id={id} {...props} className="mt-4 mb-1.5 text-title-m text-on-surface first:mt-0" />;
    };
  const components: MdComponents = {
    h1: heading('h4'),
    h2: heading('h4'),
    h3: heading('h4'),
    h4: heading('h4'),
    h5: heading('h4'),
    h6: heading('h4'),
    p: (p) => <p {...p} className="mb-2.5 last:mb-0" />,
    strong: (p) => <strong {...p} className="font-medium text-on-surface" />,
    ul: (p) => <ul {...p} className="mb-2.5 list-disc pl-[22px] last:mb-0" />,
    ol: (p) => <ol {...p} className="mb-2.5 list-decimal pl-[22px] last:mb-0" />,
    li: (p) => <li {...p} className="mb-0.5" />,
    a: (p) => (
      <a
        {...p}
        target="_blank"
        rel="noopener noreferrer"
        className="text-on-surface underline underline-offset-2"
      />
    ),
    code: (p) => (
      <code {...p} className="rounded-[6px] bg-surface-container-high px-1.5 py-px font-mono text-[.92em]" />
    ),
    pre: (p) => (
      <pre {...p} className="mb-2.5 overflow-auto rounded-md bg-surface-container-high p-3 text-[13px]" />
    ),
    blockquote: (p) => (
      <blockquote {...p} className="mb-2.5 border-l-4 border-outline-variant pl-3 text-on-surface-variant" />
    ),
    hr: () => <hr className="my-3 border-0 border-t border-outline-variant" />,
    table: (p) => <table {...p} className="mb-2.5 w-full border-collapse text-body-m" />,
    th: (p) => <th {...p} className="border-b border-outline px-2 py-1 text-left font-medium" />,
    td: (p) => <td {...p} className="border-b border-outline-variant px-2 py-1 align-top" />,
    img: () => null, // summaries never carry images; do not fetch remote content
  };
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components} skipHtml>
      {children}
    </ReactMarkdown>
  );
});

export default MarkdownRenderer;
