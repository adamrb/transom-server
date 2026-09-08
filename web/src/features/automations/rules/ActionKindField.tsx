import { RadioGroup } from '@/components/Radio';
import type { ActionType } from '@/api/types';
import { ACTION_KINDS } from './actionWords';

export interface ActionKindFieldProps {
  value: ActionType;
  onChange: (kind: ActionType) => void;
  disabled?: boolean;
}

const OPTIONS = ACTION_KINDS.map((k) => ({ key: k.key, label: k.label, description: k.hint, icon: k.icon }));

/**
 * "What happens" as a radio list in user words (Send it to the agent / Save a note in a folder /
 * Just record the decision), each with a one-line hint.
 */
export function ActionKindField({ value, onChange, disabled }: ActionKindFieldProps) {
  return (
    <RadioGroup<ActionType>
      label="What happens"
      value={value}
      onChange={onChange}
      options={OPTIONS}
      disabled={disabled}
    />
  );
}
