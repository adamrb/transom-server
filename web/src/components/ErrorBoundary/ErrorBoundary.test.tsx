import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { ErrorBoundary } from './index';

function Boom({ when }: { when: boolean }) {
  if (when) throw new Error('chunk failed');
  return <p>Loaded</p>;
}

describe('ErrorBoundary', () => {
  const quiet = () => vi.spyOn(console, 'error').mockImplementation(() => {});

  it('shows the fallback instead of crashing and can retry', async () => {
    quiet();
    const onError = vi.fn();
    function Harness() {
      const [broken, setBroken] = useState(true);
      return (
        <ErrorBoundary
          onError={onError}
          fallback={(retry) => (
            <button
              onClick={() => {
                setBroken(false);
                retry();
              }}
            >
              Try again
            </button>
          )}
        >
          <Boom when={broken} />
        </ErrorBoundary>
      );
    }
    render(<Harness />);
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
    expect(onError).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(screen.getByText('Loaded')).toBeInTheDocument();
  });

  it('re-mounts the children when resetKey changes', () => {
    quiet();
    const { rerender } = render(
      <ErrorBoundary fallback={<p>Failed</p>} resetKey="a">
        <Boom when />
      </ErrorBoundary>,
    );
    expect(screen.getByText('Failed')).toBeInTheDocument();
    rerender(
      <ErrorBoundary fallback={<p>Failed</p>} resetKey="b">
        <Boom when={false} />
      </ErrorBoundary>,
    );
    expect(screen.getByText('Loaded')).toBeInTheDocument();
  });
});
