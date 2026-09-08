import type { IconName } from '@/components/Icon';
import type { ActionType, Route } from '@/api/types';

/**
 * Everything the UI says about an action kind, in user words. The server's names (webhook /
 * markdown / none) never reach the screen.
 */
export interface ActionKindWords {
  key: ActionType;
  icon: IconName;
  /** Radio label in the editor: what the rule will do. */
  label: string;
  /** One supporting sentence under the radio label. */
  hint: string;
}

export const ACTION_KINDS: readonly ActionKindWords[] = [
  {
    key: 'webhook',
    icon: 'send',
    label: 'Send it to the agent',
    hint: 'Hands the transcript to your agent at a web address.',
  },
  {
    key: 'markdown',
    icon: 'description',
    label: 'Save a note in a folder',
    hint: 'Writes a markdown note into your vault.',
  },
  {
    key: 'none',
    icon: 'block',
    label: 'Just record the decision',
    hint: 'Nothing is sent or saved; the match shows in the activity log.',
  },
];

export function actionIcon(type: ActionType | null | undefined): IconName {
  return ACTION_KINDS.find((k) => k.key === type)?.icon ?? 'block';
}

/** The chip on a rule card: "Sends to the agent", "Saves a note in Inbox", "Just records the decision". */
export function actionChip(route: Pick<Route, 'action_type' | 'action_config'>): string {
  if (route.action_type === 'webhook') return 'Sends to the agent';
  if (route.action_type === 'markdown') return `Saves a note in ${route.action_config?.folder || 'a folder'}`;
  return 'Just records the decision';
}
