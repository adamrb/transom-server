import { render, screen } from '@testing-library/react';
import { Banner } from './index';

describe('Banner', () => {
  it('uses status role and the tone icon for success', () => {
    render(
      <Banner tone="success">
        <b>Automations are on.</b> Two of three rules
      </Banner>,
    );
    const el = screen.getByRole('status');
    expect(el).toHaveAttribute('data-tone', 'success');
    expect(el.querySelector('svg[data-icon="check_circle"]')).toBeInTheDocument();
  });

  it('uses alert role for warnings and renders an action', () => {
    render(
      <Banner tone="warning" action={<button>Retry</button>}>
        Can't reach your server
      </Banner>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent("Can't reach your server");
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});
