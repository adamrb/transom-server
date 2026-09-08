import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SegmentedButton } from './index';

describe('SegmentedButton', () => {
  it('is a radiogroup that marks the selected segment with a check', async () => {
    const onChange = vi.fn();
    render(
      <SegmentedButton
        label="Theme"
        value="light"
        onChange={onChange}
        options={[
          { key: 'system', label: 'System', icon: 'contrast' },
          { key: 'light', label: 'Light', icon: 'light_mode' },
          { key: 'dark', label: 'Dark', icon: 'dark_mode' },
        ]}
      />,
    );
    expect(screen.getByRole('radiogroup', { name: 'Theme' })).toBeInTheDocument();
    const light = screen.getByRole('radio', { name: 'Light' });
    expect(light).toBeChecked();
    expect(light.querySelector('svg[data-icon="check"]')).toBeInTheDocument();
    expect(
      screen.getByRole('radio', { name: 'Dark' }).querySelector('svg[data-icon="dark_mode"]'),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'Dark' }));
    expect(onChange).toHaveBeenCalledWith('dark');
  });
});
