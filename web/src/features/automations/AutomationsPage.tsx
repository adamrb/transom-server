import { EmptyState } from '@/components/EmptyState';
import { SectionAppBar } from '@/features/shell/SectionAppBar';

/**
 * Placeholder. The automations team replaces this with the status banner, rules and activity log
 * (see README.md). Keep the SectionAppBar and the scroll container padding rule.
 */
export function AutomationsPage() {
  return (
    <section className="flex min-h-0 flex-1 flex-col" aria-labelledby="automations-title">
      <SectionAppBar title="Automations" id="automations-title" />
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-6 pt-(--content-top-pad) pb-(--content-bottom-pad) max-md:px-4">
        <EmptyState
          icon="wand_stars"
          headline="Automations coming soon"
          description="Rules, the activity log and the rule editor are being built here."
        />
      </div>
    </section>
  );
}
