import { fmtClock, fmtDayHeader, fmtDuration, fmtSize, fmtWhen, plural } from './format';
import { loginQrPayload, qrModel } from './qr';
import { cn } from './cn';
import { session, storage } from './storage';

describe('format', () => {
  it('formats durations like the old dashboard', () => {
    expect(fmtDuration(16)).toBe('16s');
    expect(fmtDuration(252)).toBe('4m 12s');
    expect(fmtDuration(8386)).toBe('2h 19m');
    expect(fmtDuration(null)).toBe('');
  });
  it('formats sizes and clocks', () => {
    expect(fmtSize(21_800_000)).toBe('21.8 MB');
    expect(fmtSize(412_000)).toBe('412 kB');
    expect(fmtClock(5)).toBe('0:05');
    expect(fmtClock(252)).toBe('4:12');
    expect(fmtClock(4193)).toBe('1:09:53');
  });
  it('uses Today / Yesterday words', () => {
    const now = new Date(2026, 8, 8, 18, 0);
    const today = new Date(2026, 8, 8, 0, 25).toISOString();
    const yesterday = new Date(2026, 8, 7, 18, 47).toISOString();
    const older = new Date(2026, 8, 3, 18, 47).toISOString();
    expect(fmtWhen(today, now)).toMatch(/^Today 12:25/);
    expect(fmtWhen(yesterday, now)).toMatch(/^Yesterday 6:47/);
    expect(fmtWhen(older, now)).toMatch(/^Sep 3, 6:47/);
    expect(fmtDayHeader(older, now)).toMatch(/Sep 3/);
    expect(fmtWhen('garbage')).toBe('');
    expect(plural(1, 'recording')).toBe('1 recording');
    expect(plural(3, 'recording')).toBe('3 recordings');
  });
});

describe('qr', () => {
  it('encodes the login payload into a square module grid with a quiet zone', () => {
    const payload = loginQrPayload('https://plaud.example', 'abc123');
    expect(JSON.parse(payload)).toEqual({ v: 1, kind: 'login', url: 'https://plaud.example', id: 'abc123' });
    const m = qrModel(payload);
    expect(m.size).toBeGreaterThan(20);
    expect(m.quiet).toBe(4);
    expect(m.path.startsWith('M')).toBe(true);
  });
});

describe('cn and storage', () => {
  it('joins truthy classes', () => {
    expect(cn('a', false, null, undefined, 0, 'b')).toBe('a b');
  });
  it('round-trips JSON and tolerates garbage', () => {
    storage.setJSON('k', { a: 1 });
    expect(storage.getJSON<{ a: number }>('k')).toEqual({ a: 1 });
    session.set('bad', '{');
    expect(session.getJSON('bad')).toBeNull();
    storage.remove('k');
    expect(storage.get('k')).toBeNull();
  });
});
