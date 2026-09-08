import { useRef, useState, type FormEvent } from 'react';
import { Button } from '@/components/Button';
import { Dialog } from '@/components/Dialog';
import { Switch } from '@/components/Switch';
import { TextField } from '@/components/TextField';
import { useSnackbar } from '@/components/Snackbar';
import {
  ApiError,
  errorMessage,
  useCreateRoute,
  useUpdateRoute,
  type ActionType,
  type Route,
  type RouteBody,
} from '@/api';
import { ActionKindField } from './ActionKindField';
import { MarkdownFields } from './MarkdownFields';
import { TryItPanel } from './TryItPanel';
import { WebhookFields } from './WebhookFields';

export interface RuleEditorProps {
  /** The rule to edit, or null for a new one. */
  route: Route | null;
  open: boolean;
  onClose: () => void;
}

type Field = 'name' | 'description' | 'url' | 'secret' | 'folder' | 'form';
interface Problem {
  field: Field;
  message: string;
}

export interface EditorDraft {
  name: string;
  description: string;
  kind: ActionType;
  url: string;
  secret: string;
  clearSecret: boolean;
  folder: string;
  enabled: boolean;
}

export function draftFromRoute(route: Route | null): EditorDraft {
  return {
    name: route?.name ?? '',
    description: route?.description ?? '',
    kind: route?.action_type ?? 'webhook',
    url: route?.action_config?.url ?? '',
    secret: '',
    clearSecret: false,
    folder: route?.action_config?.folder ?? '',
    enabled: route ? route.enabled : true,
  };
}

const HEADER_RE = /^[^:\s]+\s*:\s*.+$/;

/**
 * Turn the draft into the body the server wants, or a problem to show. The secret header is
 * write-only: a typed value replaces it, blank keeps the saved one (resent, since the server
 * rebuilds the action from the body), and "Remove" leaves it out.
 */
export function buildRouteBody(
  draft: EditorDraft,
  existing: Route | null,
): { body: RouteBody; problem?: undefined } | { body?: undefined; problem: Problem } {
  const name = draft.name.trim();
  const description = draft.description.trim();
  if (!name) return { problem: { field: 'name', message: 'Give the rule a name.' } };
  if (name.length > 64)
    return { problem: { field: 'name', message: 'The name must be 64 characters or fewer.' } };
  if (!description)
    return { problem: { field: 'description', message: 'Describe which recordings this applies to.' } };

  let action_config: Record<string, unknown> = {};
  if (draft.kind === 'webhook') {
    const url = draft.url.trim();
    if (!url) return { problem: { field: 'url', message: 'Enter the agent’s address.' } };
    if (!/^https?:\/\//i.test(url))
      return { problem: { field: 'url', message: 'The address must start with http:// or https://.' } };
    action_config = { url };
    const secret = draft.secret.trim();
    if (secret) {
      if (!HEADER_RE.test(secret))
        return { problem: { field: 'secret', message: 'The secret header must look like “Name: value”.' } };
      action_config.auth_header = secret;
    } else if (existing?.action_config?.auth_header && !draft.clearSecret) {
      action_config.auth_header = existing.action_config.auth_header;
    }
  } else if (draft.kind === 'markdown') {
    const folder = draft.folder.trim().replace(/^\/+|\/+$/g, '');
    if (!folder) return { problem: { field: 'folder', message: 'Enter a folder.' } };
    if (folder.split('/').includes('..'))
      return { problem: { field: 'folder', message: 'The folder must be a relative path without “..”.' } };
    action_config = { folder };
  }
  return { body: { name, description, action_type: draft.kind, action_config, enabled: draft.enabled } };
}

/** The server's refusal in user words. */
export function saveErrorMessage(err: unknown, name: string): string {
  if (err instanceof ApiError) {
    if (err.conflict) return `There is already a rule named “${name}”. Pick another name.`;
    if (err.notFound) return 'Your server doesn’t support automations yet.';
  }
  return errorMessage(err, 'Couldn’t save the rule. Try again.');
}

/**
 * Add / edit a rule. A dialog on desktop, a full-screen dialog on phone. Validation problems show
 * under the field they concern; the server's refusals show above the buttons.
 */
export function RuleEditor({ route, open, onClose }: RuleEditorProps) {
  const [draft, setDraft] = useState<EditorDraft>(() => draftFromRoute(route));
  const [problem, setProblem] = useState<Problem | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const create = useCreateRoute();
  const update = useUpdateRoute();
  const snackbar = useSnackbar();
  const saving = create.isPending || update.isPending;

  const patch = (p: Partial<EditorDraft>) => {
    setDraft((d) => ({ ...d, ...p }));
    if (problem) setProblem(null);
  };

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (saving) return;
    const built = buildRouteBody(draft, route);
    if (built.problem) {
      setProblem(built.problem);
      return;
    }
    const onError = (err: unknown) =>
      setProblem({ field: 'form', message: saveErrorMessage(err, built.body.name) });
    const onSuccess = () => {
      snackbar.show(route ? 'Rule saved' : 'Rule added');
      onClose();
    };
    if (route) update.mutate({ id: route.id, body: built.body }, { onSuccess, onError });
    else create.mutate(built.body, { onSuccess, onError });
  };

  const err = (field: Field) => (problem?.field === field ? problem.message : undefined);
  const formId = 'rule-editor-form';

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={route ? 'Edit rule' : 'New rule'}
      size="md"
      fullScreen
      initialFocusRef={nameRef}
      actions={
        <>
          <Button variant="text" onClick={onClose} disabled={saving} className="max-md:hidden">
            Cancel
          </Button>
          <Button type="submit" form={formId} loading={saving}>
            Save
          </Button>
        </>
      }
    >
      <form id={formId} onSubmit={submit} noValidate className="flex flex-col gap-5 pt-1">
        <TextField
          ref={nameRef}
          label="Name"
          placeholder="Work meetings"
          maxLength={64}
          autoComplete="off"
          value={draft.name}
          onChange={(e) => patch({ name: e.target.value })}
          error={!!err('name')}
          helper={err('name')}
          disabled={saving}
        />
        <TextField
          multiline
          label="When should this run?"
          placeholder="Anything that sounds like a work meeting, standup, or 1:1."
          rows={4}
          maxLength={4000}
          value={draft.description}
          onChange={(e) => patch({ description: e.target.value })}
          error={!!err('description')}
          helper={
            err('description') ??
            'Describe the recordings this applies to, in plain words. The assistant reads this to decide whether a recording matches.'
          }
          disabled={saving}
        />
        <ActionKindField value={draft.kind} onChange={(kind) => patch({ kind })} disabled={saving} />
        {draft.kind === 'webhook' && (
          <WebhookFields
            url={draft.url}
            onUrl={(url) => patch({ url })}
            secret={draft.secret}
            onSecret={(secret) => patch({ secret })}
            hasSavedSecret={!!route?.action_config?.auth_header}
            clearSecret={draft.clearSecret}
            onClearSecret={(clearSecret) => patch({ clearSecret, secret: clearSecret ? '' : draft.secret })}
            errors={{ url: err('url'), secret: err('secret') }}
            disabled={saving}
          />
        )}
        {draft.kind === 'markdown' && (
          <MarkdownFields
            folder={draft.folder}
            onFolder={(folder) => patch({ folder })}
            error={err('folder')}
            disabled={saving}
          />
        )}
        <label className="flex cursor-pointer items-center gap-4 rounded-md">
          <span className="flex-1">
            <span className="block text-body-l text-on-surface">Turned on</span>
            <span className="block text-body-m text-on-surface-variant">
              Turned-off rules are kept but never run.
            </span>
          </span>
          <Switch checked={draft.enabled} onChange={(enabled) => patch({ enabled })} label="Turned on" />
        </label>
        {route && <TryItPanel />}
        {problem?.field === 'form' && (
          <p role="alert" className="m-0 text-body-m text-error">
            {problem.message}
          </p>
        )}
      </form>
    </Dialog>
  );
}
