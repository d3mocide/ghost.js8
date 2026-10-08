import { describe, expect, it } from 'vitest';
import { blitRow } from '../../src/lib/waterfall/blit';
import { colormapLut, COLORMAPS } from '../../src/lib/waterfall/colormap';

const lut = Uint32Array.from({ length: 256 }, (_, i) => i); // identity: colour index == level
const levels = { floor: 0, ceiling: 255 };

describe('colormaps', () => {
  it('builds opaque 256-entry LUTs, dark to light', () => {
    for (const name of COLORMAPS) {
      const l = colormapLut(name);
      expect(l.length).toBe(256);
      expect(l.every((v) => v >>> 24 === 255)).toBe(true);
      const lum = (v: number): number => (v & 255) + ((v >>> 8) & 255) + ((v >>> 16) & 255);
      expect(lum(l[255] ?? 0)).toBeGreaterThan(lum(l[0] ?? 0));
    }
  });
});

describe('blitRow', () => {
  it('maps bins 1:1 when the view equals the row', () => {
    const out = new Uint32Array(4);
    blitRow(
      new Uint8Array([0, 85, 170, 255]),
      { startHz: 0, spanHz: 4, viewLoHz: 0, viewHiHz: 4 },
      out,
      lut,
      levels,
    );
    expect(Array.from(out)).toEqual([0, 85, 170, 255]);
  });

  it('keeps narrow peaks when zoomed out (max per pixel)', () => {
    const bins = new Uint8Array(8);
    bins[5] = 200;
    const out = new Uint32Array(2);
    blitRow(bins, { startHz: 0, spanHz: 8, viewLoHz: 0, viewHiHz: 8 }, out, lut, levels);
    expect(Array.from(out)).toEqual([0, 200]);
  });

  it('paints background outside the row coverage', () => {
    const out = new Uint32Array(4);
    blitRow(
      new Uint8Array([255, 255]),
      { startHz: 100, spanHz: 2, viewLoHz: 98, viewHiHz: 102 },
      out,
      lut,
      levels,
    );
    expect(Array.from(out)).toEqual([0, 0, 255, 255]);
  });

  it('applies levels and clamps', () => {
    const out = new Uint32Array(3);
    blitRow(
      new Uint8Array([10, 60, 250]),
      { startHz: 0, spanHz: 3, viewLoHz: 0, viewHiHz: 3 },
      out,
      lut,
      {
        floor: 50,
        ceiling: 100,
      },
    );
    expect(Array.from(out)).toEqual([0, 51, 255]);
  });
});
