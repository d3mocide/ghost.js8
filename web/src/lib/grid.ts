/** Maidenhead locators. Mirrors bridge/src/ghostjs8/util/maidenhead.py. Only valid grids are mapped. */

const GRID = /^[A-R]{2}(?:[0-9]{2}(?:[A-X]{2}(?:[0-9]{2})?)?)?$/;

export function normalizeGrid(grid: string | null | undefined): string | null {
  if (!grid) return null;
  const g = grid.trim().toUpperCase();
  if (![4, 6, 8].includes(g.length) || !GRID.test(g)) return null;
  return g.slice(0, 4) + g.slice(4, 6).toLowerCase() + g.slice(6);
}

/** [lon, lat] of the square's centre, or null for an invalid grid. */
export function gridCenter(grid: string | null | undefined): [number, number] | null {
  const g = normalizeGrid(grid)?.toUpperCase();
  if (!g) return null;
  const c = (i: number): number => g.charCodeAt(i) - 65;
  const d = (i: number): number => Number(g[i]);
  let lon = c(0) * 20 - 180 + d(2) * 2;
  let lat = c(1) * 10 - 90 + d(3);
  let w = 2;
  let h = 1;
  if (g.length >= 6) {
    lon += c(4) * (2 / 24);
    lat += c(5) * (1 / 24);
    w = 2 / 24;
    h = 1 / 24;
  }
  if (g.length === 8) {
    lon += d(6) * (2 / 240);
    lat += d(7) * (1 / 240);
    w = 2 / 240;
    h = 1 / 240;
  }
  return [lon + w / 2, lat + h / 2];
}
