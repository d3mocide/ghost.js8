import { describe, expect, it } from 'vitest';
import { distanceKm, gridCenter, isProxied, normalizeGrid } from '../../src/lib/grid';

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

describe('distanceKm', () => {
  it('is ~111 km per degree and zero for the same point', () => {
    expect(Math.round(distanceKm([0, 0], [0, 1]))).toBe(111);
    expect(distanceKm([10, 10], [10, 10])).toBe(0);
  });
});

describe('isProxied', () => {
  it('flags proxy.kiwisdr.com names only', () => {
    expect(isProxied('22017.proxy.kiwisdr.com')).toBe(true);
    expect(isProxied('SSI.Proxy.KiwiSDR.com')).toBe(true);
    expect(isProxied('midtn.dynu.net')).toBe(false);
    expect(isProxied('proxy.kiwisdr.com.evil.example')).toBe(false);
  });
});
