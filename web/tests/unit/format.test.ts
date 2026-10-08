import { describe, expect, it } from 'vitest';
import { bandFor, JS8_BANDS } from '../../src/lib/bands';
import { ago, formatMHz, formatSnr, utcTime } from '../../src/lib/format';

describe('format', () => {
  it('formats frequencies and SNR', () => {
    expect(formatMHz(14_078_000)).toBe('14.078 000');
    expect(formatMHz(7_078_705)).toBe('7.078 705');
    expect(formatSnr(2)).toBe('+02');
    expect(formatSnr(-22)).toBe('−22');
    expect(formatSnr(null)).toBe('—');
  });

  it('formats UTC and ages', () => {
    expect(utcTime('2026-10-08T02:26:58.000Z')).toBe('02:26:58');
    const now = Date.parse('2026-10-08T03:00:00Z');
    expect(ago('2026-10-08T02:59:30Z', now)).toBe('30s');
    expect(ago('2026-10-08T01:00:00Z', now)).toBe('2h');
    expect(ago(null, now)).toBe('never');
  });

  it('has JS8Call default band presets', () => {
    expect(JS8_BANDS.find((b) => b.band === '20m')?.dialHz).toBe(14_078_000);
    expect(bandFor(7_078_000)).toBe('40m');
    expect(bandFor(9_000_000)).toBeNull();
  });
});
