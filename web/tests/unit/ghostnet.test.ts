import { describe, expect, it } from 'vitest';
import { classify, countdown, netIdFromHash } from '../../src/lib/ghostnet';

describe('classify', () => {
  it('flags flash traffic', () => {
    expect(classify('W1GHZ: @GSTFLASH BRIDGE OUT ON I-95').flash).toBe(true);
    expect(classify('W1GHZ: @gstflash test').flash).toBe(true);
    expect(classify('W1GHZ: NOT@GSTFLASHY').flash).toBe(false);
  });

  it('recognises GhostNet and regional groups', () => {
    expect(classify('K0OG: @GHOSTNET QSL').ghostnet).toBe(true);
    const sc = classify('KN4CRD: @GNUSASC CHECKING IN');
    expect([sc.ghostnet, sc.regional]).toEqual([true, '@GNUSASC']);
    expect(classify('K0OG: KN4CRD SNR +02')).toEqual({
      flash: false,
      ghostnet: false,
      regional: null,
    });
  });
});

describe('countdown', () => {
  it('formats durations', () => {
    expect(countdown(0, 45_000)).toBe('45s');
    expect(countdown(0, 725_000)).toBe('12m 05s');
    expect(countdown(0, 7_500_000)).toBe('2h 05m');
    expect(countdown(0, 3 * 86400_000 + 4 * 3600_000)).toBe('3d 04h');
    expect(countdown(10, 0)).toBe('0s');
  });
});

describe('netIdFromHash', () => {
  it('accepts bridge-generated ids only', () => {
    expect(netIdFromHash('#/nets/na-net-20261009T0100Z')).toBe('na-net-20261009T0100Z');
    expect(netIdFromHash('#/nets/../../etc')).toBeNull();
    expect(netIdFromHash('#/nets/')).toBeNull();
    expect(netIdFromHash('#/other')).toBeNull();
  });
});
