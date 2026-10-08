/** Waterfall colormaps as 256-entry RGBA lookup tables. */

export type ColormapName = 'spectre' | 'viridis' | 'inferno' | 'grey';
export const COLORMAPS: readonly ColormapName[] = ['spectre', 'viridis', 'inferno', 'grey'];

type Stop = readonly [number, number, number, number]; // position 0..1, r, g, b

/**
 * Default "aurora": ink -> indigo -> violet -> azure -> aqua-mint -> white.
 * Monotonic in lightness. Mirrored by the bridge's recorded-net PNG palette.
 */
const SPECTRE: readonly Stop[] = [
  [0.0, 3, 4, 12],
  [0.3, 22, 20, 68],
  [0.5, 62, 44, 140],
  [0.66, 46, 130, 206],
  [0.8, 94, 234, 212],
  [0.92, 204, 250, 240],
  [1.0, 255, 255, 255],
];
const VIRIDIS: readonly Stop[] = [
  [0.0, 68, 1, 84],
  [0.25, 59, 82, 139],
  [0.5, 33, 145, 140],
  [0.75, 94, 201, 98],
  [1.0, 253, 231, 37],
];
const INFERNO: readonly Stop[] = [
  [0.0, 0, 0, 4],
  [0.25, 87, 16, 110],
  [0.5, 188, 55, 84],
  [0.75, 249, 142, 9],
  [1.0, 252, 255, 164],
];
const GREY: readonly Stop[] = [
  [0.0, 0, 0, 0],
  [1.0, 255, 255, 255],
];
const STOPS: Record<ColormapName, readonly Stop[]> = {
  spectre: SPECTRE,
  viridis: VIRIDIS,
  inferno: INFERNO,
  grey: GREY,
};

const cache = new Map<ColormapName, Uint32Array>();

/** Packed little-endian RGBA (as written by Uint32Array over ImageData). */
export function colormapLut(name: ColormapName): Uint32Array {
  const hit = cache.get(name);
  if (hit) return hit;
  const stops = STOPS[name];
  const lut = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    const t = i / 255;
    let k = 0;
    while (k < stops.length - 2 && t > (stops[k + 1]?.[0] ?? 1)) k++;
    const a: Stop = stops[k] ?? [0, 0, 0, 0];
    const b = stops[k + 1] ?? a;
    const f = b[0] === a[0] ? 0 : (t - a[0]) / (b[0] - a[0]);
    const r = Math.round(a[1] + (b[1] - a[1]) * f);
    const g = Math.round(a[2] + (b[2] - a[2]) * f);
    const bl = Math.round(a[3] + (b[3] - a[3]) * f);
    lut[i] = (255 << 24) | (bl << 16) | (g << 8) | r;
  }
  cache.set(name, lut);
  return lut;
}
