import { useParams } from 'react-router-dom';
import { EmptyState } from '@/components/EmptyState';
import { SectionAppBar } from '@/features/shell/SectionAppBar';

/**
 * Placeholder. The recordings team replaces this with the two-pane list + detail (see README.md).
 * Keep the SectionAppBar (hidden when embedded) and the scroll container padding rule.
 */
export function RecordingsPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <section className="flex min-h-0 flex-1 flex-col" aria-labelledby="recordings-title">
      <SectionAppBar title="Recordings" id="recordings-title" />
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto pt-(--content-top-pad) pb-(--content-bottom-pad)">
        <EmptyState
          icon="graphic_eq"
          headline={id ? 'Recording coming soon' : 'Recordings coming soon'}
          description={
            id
              ? `This screen will open recording ${id} with its summary, transcript and player.`
              : 'The list, search, filters and the detail pane are being built here.'
          }
        />
      </div>
    </section>
  );
}
