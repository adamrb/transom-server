import { useState } from 'react';
import { Button } from '@/components/Button';
import { ConfirmDialog } from '@/components/Dialog';
import { EmptyState } from '@/components/EmptyState';
import { Skeleton } from '@/components/Skeleton';
import { useSnackbar } from '@/components/Snackbar';
import { errorMessage, routeBody, useDeleteRoute, useRoutes, useUpdateRoute, type Route } from '@/api';
import { SectionHeader } from '../SectionHeader';
import { RuleCard } from './RuleCard';
import { RuleEditor } from './RuleEditor';

type EditorState = { open: false } | { open: true; route: Route | null };

/**
 * The rules: header with "Add rule", one card per rule, the editor and the delete confirmation.
 * Toggling a rule PUTs the whole rule with `enabled` flipped (optimistically; reverts on failure).
 */
export function RulesSection() {
  const routes = useRoutes();
  const update = useUpdateRoute();
  const remove = useDeleteRoute();
  const snackbar = useSnackbar();
  const [editor, setEditor] = useState<EditorState>({ open: false });
  const [deleting, setDeleting] = useState<Route | null>(null);
  // Rules whose toggle PUT is still out: their switch is held so two PUTs cannot cross.
  const [pendingIds, setPendingIds] = useState<ReadonlySet<string>>(() => new Set());

  const toggle = (route: Route, enabled: boolean) => {
    if (pendingIds.has(route.id)) return;
    const word = enabled ? 'on' : 'off';
    setPendingIds((s) => new Set(s).add(route.id));
    update.mutate(
      { id: route.id, body: routeBody(route, { enabled }) },
      {
        onSuccess: () => snackbar.show(`“${route.name}” turned ${word}`),
        onError: (err) => snackbar.error(errorMessage(err, `Couldn’t turn “${route.name}” ${word}.`)),
        onSettled: () =>
          setPendingIds((s) => {
            const next = new Set(s);
            next.delete(route.id);
            return next;
          }),
      },
    );
  };

  const confirmDelete = () => {
    if (!deleting) return;
    remove.mutate(deleting.id, {
      onSuccess: () => {
        snackbar.show('Rule deleted');
        setDeleting(null);
      },
      onError: (err) => {
        snackbar.error(errorMessage(err, 'Couldn’t delete the rule.'));
        setDeleting(null);
      },
    });
  };

  const addButton = (
    <Button variant="tonal" icon="add" onClick={() => setEditor({ open: true, route: null })}>
      Add rule
    </Button>
  );
  const list = routes.data?.routes ?? [];

  return (
    <section aria-labelledby="rules-title">
      <SectionHeader
        title="Rules"
        id="rules-title"
        description="When a recording is transcribed, the assistant reads each rule and runs the ones that fit."
        actions={addButton}
      />
      {routes.isPending ? (
        <div aria-busy="true" aria-label="Loading rules" className="flex flex-col gap-2.5">
          {[0, 1].map((i) => (
            <div key={i} className="flex items-center gap-3.5 rounded-lg bg-card px-5 py-4 max-md:px-4">
              <Skeleton width={40} height={40} className="rounded-md" />
              <div className="flex-1">
                <Skeleton width="40%" height={16} />
                <Skeleton width="75%" height={12} className="mt-2.5" />
              </div>
              <Skeleton width={52} height={32} shape="circle" />
            </div>
          ))}
        </div>
      ) : routes.isError ? (
        <EmptyState
          compact
          icon="error"
          headline="Couldn’t load your rules"
          description={errorMessage(routes.error, 'Try again in a moment.')}
          action={
            <Button variant="tonal" icon="refresh" onClick={() => void routes.refetch()}>
              Try again
            </Button>
          }
        />
      ) : list.length === 0 ? (
        <EmptyState
          compact
          icon="wand_stars"
          headline="No rules yet"
          description="Add one to have recordings sorted for you."
          action={addButton}
        />
      ) : (
        <div role="list" aria-label="Rules">
          {list.map((route) => (
            <RuleCard
              key={route.id}
              route={route}
              onToggle={toggle}
              busy={pendingIds.has(route.id)}
              onEdit={(r) => setEditor({ open: true, route: r })}
              onDelete={setDeleting}
            />
          ))}
        </div>
      )}

      {editor.open && (
        <RuleEditor
          key={editor.route?.id ?? 'new'}
          route={editor.route}
          open
          onClose={() => setEditor({ open: false })}
        />
      )}
      <ConfirmDialog
        open={!!deleting}
        title="Delete this rule?"
        ok="Delete"
        danger
        busy={remove.isPending}
        onConfirm={confirmDelete}
        onCancel={() => setDeleting(null)}
      >
        <p>
          <b>{deleting?.name ?? 'This rule'}</b> will stop running. Its past activity stays in the log.
        </p>
      </ConfirmDialog>
    </section>
  );
}
