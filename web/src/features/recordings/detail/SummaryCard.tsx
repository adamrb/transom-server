import { Card, IconButton, Markdown } from '@/components';

export interface SummaryCardProps {
  /** Already cleaned (see `cleanSummary`). */
  summary: string;
  onCopy?: () => void;
}

/** The summary as Markdown, with a copy button in the heading. Nothing renders for an empty summary. */
export function SummaryCard({ summary, onCopy }: SummaryCardProps) {
  if (!summary) return null;
  return (
    <Card
      id="sec-summary"
      title="Summary"
      actions={onCopy && <IconButton icon="content_copy" label="Copy summary" onClick={onCopy} />}
    >
      <Markdown headingIds>{summary}</Markdown>
    </Card>
  );
}
