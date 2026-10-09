import { describe, expect, it } from 'vitest';
import { isNoiseFrame, speedChip, talkLinks } from '../../src/lib/traffic';
import type { LonLat } from '../../src/lib/geo';

describe('isNoiseFrame', () => {
  it.each(['', '  ', '…', '……', '… …', '...'])('flags %j as noise', (t) => {
    expect(isNoiseFrame(t)).toBe(true);
  });
  it.each(['CQ', 'A', '7?P', 'IZ', 'HELLO …'])('keeps %j', (t) => {
    expect(isNoiseFrame(t)).toBe(false);
  });
});

describe('speedChip', () => {
  it('labels only the speeds that differ from normal', () => {
    expect(speedChip('normal')).toBeNull();
    expect(speedChip('unknown')).toBeNull();
    expect(speedChip('fast')).toBe('FAST');
    expect(speedChip('Slow')).toBe('SLOW');
    expect(speedChip('turbo')).toBe('TURBO');
  });
});

describe('talkLinks', () => {
  const where: Record<string, LonLat> = { K4JU: [-80, 34], KQ4PDG: [-85, 33], W9ZOM: [-95, 38] };
  const locate = (c: string): LonLat | null => where[c] ?? null;
  const d = (from: string | null, to: string | null, at: number, kind = 'directed') => ({
    kind,
    from_call: from,
    to_call: to,
    receivedAt: at,
  });

  it('links a talker to the station they addressed and counts repeats', () => {
    const links = talkLinks(
      [d('K4JU', 'KQ4PDG', 10), d('K4JU', 'KQ4PDG', 20), d('KQ4PDG', 'K4JU', 30)],
      locate,
      40,
      100,
    );
    expect(links.map((l) => [l.key, l.count])).toEqual([
      ['K4JU>KQ4PDG', 2],
      ['KQ4PDG>K4JU', 1],
    ]);
    expect(links[0]?.lastMs).toBe(20);
  });

  it('ignores group addresses, unknown grids, activity frames and old messages', () => {
    const links = talkLinks(
      [
        d('K4JU', '@GHOSTNET', 10),
        d('K4JU', 'N0NE', 10),
        d('K4JU', 'W9ZOM', 10, 'activity'),
        d('K4JU', 'W9ZOM', 1),
        d('K4JU', 'K4JU', 30),
      ],
      locate,
      1000,
      100,
    );
    expect(links).toEqual([]);
  });
});
