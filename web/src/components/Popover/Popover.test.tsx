import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useRef, useState } from 'react';
import { MenuItem, MenuSeparator, Popover } from './index';

function Harness({ as }: { as?: 'auto' | 'menu' | 'sheet' }) {
  const [open, setOpen] = useState(false);
  const anchor = useRef<HTMLButtonElement>(null);
  return (
    <>
      <button ref={anchor} onClick={() => setOpen(true)}>
        More
      </button>
      <Popover
        open={open}
        onClose={() => setOpen(false)}
        anchorRef={anchor}
        as={as}
        title="Options"
        label="Options"
      >
        <MenuItem icon="content_copy">Copy</MenuItem>
        <MenuItem icon="ios_share">Export</MenuItem>
        <MenuSeparator />
        <MenuItem icon="delete" danger>
          Delete…
        </MenuItem>
      </Popover>
    </>
  );
}

describe('Popover', () => {
  it('opens as a menu, focuses the first item, arrows between items and closes on Escape', async () => {
    render(<Harness as="menu" />);
    await userEvent.click(screen.getByRole('button', { name: 'More' }));
    const menu = screen.getByRole('menu', { name: 'Options' });
    expect(menu).toHaveAttribute('data-presentation', 'menu');
    const items = screen.getAllByRole('menuitem');
    expect(items).toHaveLength(3);
    await act(async () => {});
    expect(items[0]).toHaveFocus();
    await userEvent.keyboard('{ArrowDown}');
    expect(items[1]).toHaveFocus();
    await userEvent.keyboard('{ArrowUp}{ArrowUp}');
    expect(items[2]).toHaveFocus();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('portals into the open <dialog> around its anchor, or into a given container', async () => {
    function InDialog({ container }: { container?: HTMLElement }) {
      const [open, setOpen] = useState(true);
      const anchor = useRef<HTMLButtonElement>(null);
      return (
        <dialog open data-testid="host">
          <button ref={anchor}>More</button>
          <Popover
            open={open}
            onClose={() => setOpen(false)}
            anchorRef={anchor}
            as="menu"
            container={container}
          >
            <MenuItem>Copy</MenuItem>
          </Popover>
        </dialog>
      );
    }
    const { unmount } = render(<InDialog />);
    expect(screen.getByRole('menu').closest('dialog')).toBe(screen.getByTestId('host'));
    unmount();
    const elsewhere = document.createElement('div');
    document.body.appendChild(elsewhere);
    render(<InDialog container={elsewhere} />);
    expect(screen.getByRole('menu').parentElement).toBe(elsewhere);
    elsewhere.remove();
  });

  it('renders as a bottom sheet dialog with a title and closes on the scrim', async () => {
    render(<Harness as="sheet" />);
    await userEvent.click(screen.getByRole('button', { name: 'More' }));
    const sheet = screen.getByRole('dialog', { name: 'Options' });
    expect(sheet).toHaveAttribute('data-presentation', 'sheet');
    expect(screen.getByRole('heading', { name: 'Options' })).toBeInTheDocument();
    await userEvent.click(document.querySelector('[data-scrim]')!);
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
