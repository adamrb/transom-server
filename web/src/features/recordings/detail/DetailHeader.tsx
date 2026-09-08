import { Chip, StatusChip } from '@/components';
import type { Recording, Transcript } from '@/api';
import { fmtDuration, fmtWhen } from '@/lib/format';
import { statusWord } from '../lib/status';
import { titleOf } from '../lib/summary';
import { transcriptHasText } from '../lib/transcript';

export interface DetailHeaderProps {
  rec: Recording;
  transcript: Transcript | null | undefined;
  onRename: () => void;
  onCopy: () => void;
  onExport: () => void;
  onDownload: () => void;
}

/**
 * Title (click to rename), the meta line (when · duration · speakers · bookmarks, plus a status
 * word only while in flight / failed / silent), and the assist chips.
 */
export function DetailHeader({ rec, transcript, onRename, onCopy, onExport, onDownload }: DetailHeaderProps) {
  const word = statusWord(rec);
  const speakers = transcript?.speakers.length ?? 0;
  const marks = rec.marks?.length ?? 0;
  const hasText = transcriptHasText(transcript);
  return (
    <header className="mb-5">
      <h2 className="m-0 -ml-1.5 mt-2 mb-1 flex">
        <button
          type="button"
          title="Rename"
          onClick={onRename}
          className="min-w-0 rounded-sm px-1.5 py-0.5 text-left font-display text-headline-m text-on-surface transition-colors dur-short hover:bg-state-hover focus-ring max-md:text-headline-s"
        >
          {titleOf(rec)}
        </button>
      </h2>
      <div className="mb-4 flex flex-wrap items-center gap-2 text-body-m text-on-surface-variant tnum">
        <span>
          {fmtWhen(rec.started_at || rec.uploaded_at)}
          {rec.duration_s ? ` · ${fmtDuration(rec.duration_s)}` : ''}
        </span>
        {speakers > 1 && (
          <StatusChip tone="tag" icon="group">
            {speakers} speakers
          </StatusChip>
        )}
        {marks > 0 && (
          <StatusChip tone="star" icon="star_fill">
            {marks} highlight{marks === 1 ? '' : 's'}
          </StatusChip>
        )}
        {word && <StatusChip tone={word.tone}>{word.label}</StatusChip>}
      </div>
      {rec.status === 'done' && (
        <div className="flex flex-wrap gap-2">
          {hasText && (
            <Chip icon="content_copy" onClick={onCopy}>
              Copy transcript
            </Chip>
          )}
          {hasText && (
            <Chip icon="ios_share" onClick={onExport}>
              Export markdown
            </Chip>
          )}
          <Chip icon="download" onClick={onDownload}>
            Download audio
          </Chip>
        </div>
      )}
    </header>
  );
}
