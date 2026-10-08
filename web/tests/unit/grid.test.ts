import { describe, expect, it } from 'vitest';
import { gridCenter, normalizeGrid } from '../../src/lib/grid';

describe('Maidenhead', () => {
  it.each([
    ['EN34', 'EN34'],
    ['fn31PR', 'FN31pr'],
    ['JO65ab12', 'JO65ab12'],
  ])('normalizes %s', (raw, norm) => {
    expect(normalizeGrid(raw)).toBe(norm);
  });

  it.each(['', 'EN', 'SN34', 'EN3', 'EN34yz', 'N0CALL', '@HB', 'EN34ab1'])('rejects %s', (raw) => {
    expect(normalizeGrid(raw)).toBeNull();
    expect(gridCenter(raw)).toBeNull();
  });

  it('matches the bridge implementation', () => {
    expect(gridCenter('EN34')).toEqual([-93, 44.5]);
    const c = gridCenter('FN31pr');
    expect(c?.map((x) => Math.round(x * 1000) / 1000)).toEqual([-72.708, 41.729]);
  });
});
