import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type TextareaHTMLAttributes,
} from 'react';
import { cn } from '@/lib/cn';
import { Icon, type IconName } from '@/components/Icon';

interface BaseProps {
  /** Floating label on the outline. */
  label?: string;
  /** Helper (or error) text under the field. */
  helper?: ReactNode;
  /** Error state: red outline and helper. */
  error?: boolean;
  /** Leading Material Symbol. */
  icon?: IconName;
  /** Trailing element (reveal button, clear button). */
  trailing?: ReactNode;
  /** sm = 40 px, md = 48 px. */
  size?: 'md' | 'sm';
  /** Class for the outer wrapper (width etc.). */
  className?: string;
}

export interface TextFieldProps
  extends BaseProps, Omit<InputHTMLAttributes<HTMLInputElement>, 'size' | 'className'> {
  multiline?: false;
}

export interface TextAreaFieldProps
  extends BaseProps, Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'className'> {
  multiline: true;
  /** borderless tonal text area (the vocabulary editor) */
  tonal?: boolean;
  mono?: boolean;
}

export type AnyTextFieldProps = TextFieldProps | TextAreaFieldProps;

/**
 * Outlined text field, 12 px corners (the app's), floating label, optional icon and trailing
 * element. `multiline` renders a textarea; `multiline tonal` renders the borderless tonal text
 * area used for the vocabulary editor.
 */
export const TextField = forwardRef<HTMLInputElement | HTMLTextAreaElement, AnyTextFieldProps>(
  function TextField(props, ref) {
    const { label, helper, error, icon, trailing, size = 'md', className, id: idProp, ...rest } = props;
    const autoId = useId();
    const id = idProp ?? autoId;
    const helperId = helper ? `${id}-helper` : undefined;
    const common = {
      id,
      'aria-invalid': error || undefined,
      'aria-describedby': helperId,
      className:
        'peer min-w-0 flex-1 bg-transparent outline-none placeholder:text-on-surface-variant disabled:opacity-[.38]',
    };

    if (props.multiline) {
      const { multiline: _m, tonal, mono, ...ta } = rest as TextAreaFieldProps & { multiline: true };
      void _m;
      return (
        <div className={cn('flex flex-col gap-1', className)}>
          {label && (
            <label htmlFor={id} className="text-body-s text-on-surface-variant">
              {label}
            </label>
          )}
          <textarea
            ref={ref as React.Ref<HTMLTextAreaElement>}
            {...common}
            {...ta}
            className={cn(
              // resizable, but without the bright native corner grip (it glares in dark)
              'w-full resize-y rounded-md outline-none transition-shadow dur-short [&::-webkit-resizer]:hidden',
              tonal
                ? 'min-h-[168px] border-0 bg-surface-container-high px-3.5 py-3 focus:shadow-[inset_0_0_0_2px_var(--primary)]'
                : cn(
                    'min-h-[96px] border bg-transparent px-3.5 py-3 focus:border-primary focus:shadow-[inset_0_0_0_1px_var(--primary)]',
                    error ? 'border-error' : 'border-outline',
                  ),
              mono ? 'font-mono text-mono' : 'text-body-l',
              'placeholder:text-on-surface-variant disabled:opacity-[.38]',
            )}
          />
          {helper && (
            <div
              id={helperId}
              className={cn('px-1 text-body-s', error ? 'text-error' : 'text-on-surface-variant')}
            >
              {helper}
            </div>
          )}
        </div>
      );
    }

    const { multiline: _m, ...input } = rest as Omit<InputHTMLAttributes<HTMLInputElement>, 'size'> & {
      multiline?: false;
    };
    void _m;
    return (
      <div className={cn('flex flex-col gap-1', className)}>
        <div
          className={cn(
            'relative flex items-center gap-2 border bg-transparent px-3.5 text-on-surface transition-[border-color,box-shadow] dur-short',
            size === 'sm' ? 'h-10 rounded-[10px]' : 'h-12 rounded-md',
            error ? 'border-error' : 'border-outline focus-within:border-primary',
            !error && 'focus-within:shadow-[inset_0_0_0_1px_var(--primary)]',
          )}
        >
          {icon && <Icon name={icon} size={20} className="text-on-surface-variant" />}
          <input
            ref={ref as React.Ref<HTMLInputElement>}
            {...common}
            {...input}
            className={cn(common.className, 'h-full', size === 'sm' ? 'text-body-m' : 'text-body-l')}
          />
          {label && (
            <label
              htmlFor={id}
              className={cn(
                // one line, never wider than the field: a long label must not wrap over the value
                'pointer-events-none absolute -top-2 left-3 max-w-[calc(100%-24px)] truncate bg-(--field-bg) px-1 text-body-s',
                error ? 'text-error' : 'text-on-surface-variant peer-focus:text-primary',
              )}
            >
              {label}
            </label>
          )}
          {trailing}
        </div>
        {helper && (
          <div
            id={helperId}
            className={cn('px-1 text-body-s', error ? 'text-error' : 'text-on-surface-variant')}
          >
            {helper}
          </div>
        )}
      </div>
    );
  },
);
