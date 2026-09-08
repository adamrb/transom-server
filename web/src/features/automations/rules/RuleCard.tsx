import { Avatar } from '@/components/Avatar';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { StatusChip } from '@/components/Chip';
import { Switch } from '@/components/Switch';
import type { Route } from '@/api/types';
import { cn } from '@/lib/cn';
import { actionChip, actionIcon } from './actionWords';

export interface RuleCardProps {
  route: Route;
  onToggle: (route: Route, enabled: boolean) => void;
  onEdit: (route: Route) => void;
  onDelete: (route: Route) => void;
  /** A toggle is still being saved: the switch is held until the server answers. */
  busy?: boolean;
}

/**
 * One rule: leading action glyph, name, on/off switch; the description; a chip saying what the
 * rule does in user words, then Edit and (to the right, red) Delete. Turned-off rules are dimmed.
 * The switch reflects the cached rule, which `useUpdateRoute` flips optimistically.
 */
export function RuleCard({ route, onToggle, onEdit, onDelete, busy }: RuleCardProps) {
  const off = !route.enabled;
  const dim = off ? 'opacity-50 transition-opacity dur-medium' : 'transition-opacity dur-medium';
  const icon = actionIcon(route.action_type);
  return (
    <Card
      data-rule-id={route.id}
      data-enabled={route.enabled}
      className="mb-2.5 flex flex-col gap-2.5 px-5 py-4 max-md:px-4"
      padding="none"
      role="listitem"
      aria-label={route.name}
    >
      <div className="flex items-center gap-3.5">
        <Avatar kind="icon" icon={icon} size={40} shape="rounded" className={dim} />
        <h3 className={cn('m-0 min-w-0 flex-1 truncate text-title-m text-on-surface', dim)}>{route.name}</h3>
        <Switch
          checked={route.enabled}
          disabled={busy}
          aria-busy={busy || undefined}
          onChange={(v) => onToggle(route, v)}
          label={`Turn “${route.name}” on or off`}
        />
      </div>
      {route.description && (
        <p
          className={cn(
            'm-0 whitespace-pre-line text-body-m text-on-surface-variant md:ml-[54px] [overflow-wrap:anywhere]',
            dim,
          )}
        >
          {route.description}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2 md:ml-[54px]">
        <StatusChip tone="tag" icon={icon} className={dim}>
          {actionChip(route)}
        </StatusChip>
        <span className="flex-1" />
        <Button variant="text" size="sm" icon="edit" onClick={() => onEdit(route)}>
          Edit
        </Button>
        <Button variant="danger" size="sm" onClick={() => onDelete(route)}>
          Delete
        </Button>
      </div>
    </Card>
  );
}
