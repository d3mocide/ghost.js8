import { describe, expect, it } from 'vitest';
import { GAP_MARK, groupThreads, slotSeconds } from '../../src/lib/state/threads';
import type { DecodeRow } from '../../src/lib/state/state';

let n = 0;
function row(sec: number, offset: number, text: string, extra: Partial<DecodeRow> = {}): DecodeRow {
  const utc = new Date(Date.UTC(2026, 9, 9, 0, 0, sec)).toISOString();
  n += 1;
  return {
    v: 1,
    type: 'decode',
    kind: 'activity',
    utc,
    text,
    snr_db: -10,
    offset_hz: offset,
    dial_hz: 7_107_000,
    freq_hz: null,
    speed: 'normal',
    from_call: null,
    to_call: null,
    grid: null,
    key: `k${String(n)}`,
    receivedAt: 0,
    ...extra,
  };
}

describe('groupThreads', () => {
  it('joins consecutive frames from one offset and separates stations', () => {
    const items = groupThreads([
      row(0, 1202, 'TONIGHT FOR THE Q'),
      row(1, 1091, 'LOCALLY, SEEING'),
      row(15, 1204, 'RAF. WILL BE Q'),
      row(16, 1090, 'CRUCES NM.'),
    ]);
    const texts = items.map((i) => (i.kind === 'thread' ? i.text : ''));
    expect(texts).toContain('TONIGHT FOR THE Q RAF. WILL BE Q');
    expect(texts).toContain('LOCALLY, SEEING CRUCES NM.');
    expect(items).toHaveLength(2);
  });

  it('marks a missed slot and starts a new thread after a long silence', () => {
    const gap = groupThreads([row(0, 1000, 'A'), row(30, 1000, 'B')]);
    expect(gap).toHaveLength(1);
    const t = gap[0];
    expect(t?.kind === 'thread' && t.text).toBe(`A ${GAP_MARK} B`);
    expect(t?.kind === 'thread' && t.gaps).toBe(1);

    expect(groupThreads([row(0, 1000, 'A'), row(60, 1000, 'B')])).toHaveLength(2);
  });

  it('keeps stations apart beyond the offset tolerance and passes directed through', () => {
    const items = groupThreads([
      row(0, 1000, 'A'),
      row(15, 1100, 'B'),
      row(20, 1000, 'DIRECTED', { kind: 'directed' }),
    ]);
    expect(items.filter((i) => i.kind === 'thread')).toHaveLength(2);
    expect(items.filter((i) => i.kind === 'single')).toHaveLength(1);
  });

  it('reports newest first and uses the speed to size the slot', () => {
    expect(slotSeconds('slow')).toBe(30);
    expect(slotSeconds('turbo')).toBe(6);
    const items = groupThreads([row(0, 900, 'OLD'), row(40, 1500, 'NEW')]);
    expect(items[0]?.kind === 'thread' && items[0].text).toBe('NEW');
  });
});
