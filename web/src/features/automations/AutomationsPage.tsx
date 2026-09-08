import { ApiError, useRouterStatus, useRoutes, useRoutingLog } from '@/api';
import { SectionAppBar } from '@/features/shell/SectionAppBar';
import { ActivitySection } from './activity/ActivitySection';
import { RulesSection } from './rules/RulesSection';
import { StatusBanner } from './StatusBanner';

/**
 * Automations: whether they are on (banner), the rules, and the activity log. Works the same
 * embedded in the Android app (the app bar hides itself; the shell pads top and bottom).
 */
export function AutomationsPage() {
  const status = useRouterStatus();
  const unsupported = status.isError && status.error instanceof ApiError && status.error.notFound;
  return (
    <section className="flex min-h-0 flex-1 flex-col" aria-labelledby="automations-title">
      <SectionAppBar title="Automations" id="automations-title" />
      <div className="min-h-0 flex-1 overflow-y-auto px-6 pt-(--content-top-pad) pb-(--content-bottom-pad) max-md:px-4">
        <div className="mx-auto max-w-[860px] pb-6">
          {unsupported ? (
            <StatusBanner status={undefined} error={status.error} className="mb-6" />
          ) : (
            <AutomationsBody status={status} />
          )}
        </div>
      </div>
    </section>
  );
}

/** Banner + sections. Rules and the log are fetched only when the server has automations at all. */
function AutomationsBody({ status }: { status: ReturnType<typeof useRouterStatus> }) {
  const routes = useRoutes();
  const log = useRoutingLog(50);
  const lastRunAt = log.data?.runs.reduce<string | null>(
    (best, r) => (r.created_at && (!best || r.created_at > best) ? r.created_at : best),
    null,
  );
  return (
    <>
      <StatusBanner
        status={status.data}
        error={status.error}
        loading={status.isPending}
        routes={routes.data?.routes}
        lastRunAt={lastRunAt}
        className="mb-6"
      />
      <RulesSection />
      <ActivitySection />
    </>
  );
}
