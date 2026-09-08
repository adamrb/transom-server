import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { SearchBar } from './index';

function Harness({ trailing }: { trailing?: React.ReactNode }) {
  const [v, setV] = useState('');
  return <SearchBar value={v} onChange={setV} trailing={trailing} />;
}

describe('SearchBar', () => {
  it('is a labelled search input that clears itself', async () => {
    render(<Harness trailing={<button>Filters</button>} />);
    const input = screen.getByRole('searchbox', { name: 'Search recordings' });
    expect(screen.getByRole('button', { name: 'Filters' })).toBeInTheDocument();
    await userEvent.type(input, 'data');
    expect(input).toHaveValue('data');
    expect(screen.queryByRole('button', { name: 'Filters' })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Clear search' }));
    expect(input).toHaveValue('');
    expect(screen.getByRole('button', { name: 'Filters' })).toBeInTheDocument();
  });
});
