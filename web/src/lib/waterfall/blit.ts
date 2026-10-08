/**
 * Map one waterfall row (u8 dB bins over [startHz, startHz+spanHz)) onto a
 * pixel row covering the visible range [viewLoHz, viewHiHz). Pure function so
 * it can be unit-tested; the renderer only handles canvas plumbing.
 */
export interface RowGeometry {
  readonly startHz: number;
  readonly spanHz: number;
  readonly viewLoHz: number;
  readonly viewHiHz: number;
}

/** dB window applied to raw u8 values before the colormap. */
export interface Levels {
  readonly floor: number; // raw u8 value mapped to colour 0
  readonly ceiling: number; // raw u8 value mapped to colour 255
}

export const DEFAULT_LEVELS: Levels = { floor: 255 - 120, ceiling: 255 - 40 };

export function blitRow(
  bins: Uint8Array,
  geo: RowGeometry,
  out: Uint32Array,
  lut: Uint32Array,
  levels: Levels = DEFAULT_LEVELS,
): void {
  const width = out.length;
  const nBins = bins.length;
  const background = lut[0] ?? 0;
  if (nBins === 0 || width === 0 || geo.spanHz <= 0) {
    out.fill(background);
    return;
  }
  const range = Math.max(1, levels.ceiling - levels.floor);
  const hzPerPx = (geo.viewHiHz - geo.viewLoHz) / width;
  const binsPerHz = nBins / geo.spanHz;
  for (let x = 0; x < width; x++) {
    // Max over the bins this pixel covers, so narrow signals never vanish when zoomed out.
    const loHz = geo.viewLoHz + x * hzPerPx;
    const b0 = Math.floor((loHz - geo.startHz) * binsPerHz);
    const b1 = Math.max(b0 + 1, Math.floor((loHz + hzPerPx - geo.startHz) * binsPerHz));
    if (b1 <= 0 || b0 >= nBins) {
      out[x] = background;
      continue;
    }
    let peak = 0;
    for (let b = Math.max(0, b0); b < Math.min(nBins, b1); b++) {
      const v = bins[b] ?? 0;
      if (v > peak) peak = v;
    }
    const level = Math.min(255, Math.max(0, Math.round(((peak - levels.floor) / range) * 255)));
    out[x] = lut[level] ?? background;
  }
}
