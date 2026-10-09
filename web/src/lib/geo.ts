/** Spherical geometry for the station map. All points are [lon, lat] in degrees. */
export type LonLat = readonly [number, number];

const R_KM = 6371;
const RAD = Math.PI / 180;
const DEG = 180 / Math.PI;

/** Initial great-circle bearing from a to b, 0..360 degrees clockwise from north. */
export function bearingDeg(a: LonLat, b: LonLat): number {
  const p1 = a[1] * RAD;
  const p2 = b[1] * RAD;
  const dl = (b[0] - a[0]) * RAD;
  const y = Math.sin(dl) * Math.cos(p2);
  const x = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl);
  return (Math.atan2(y, x) * DEG + 360) % 360;
}

/** The point `km` away from `from` along `bearing` degrees. */
export function destination(from: LonLat, bearing: number, km: number): [number, number] {
  const d = km / R_KM;
  const t = bearing * RAD;
  const p1 = from[1] * RAD;
  const l1 = from[0] * RAD;
  const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(t));
  const l2 =
    l1 +
    Math.atan2(Math.sin(t) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2));
  return [((((l2 * DEG + 540) % 360) + 360) % 360) - 180, p2 * DEG];
}

/** A ring of constant great-circle distance around `center`, as a closed polyline. */
export function ring(center: LonLat, km: number, steps = 72): [number, number][] {
  const pts: [number, number][] = [];
  for (let i = 0; i <= steps; i++) pts.push(destination(center, (i * 360) / steps, km));
  return pts;
}

/** Points along the great circle from a to b (inclusive), for drawing a path. */
export function greatCircle(a: LonLat, b: LonLat, steps = 48): [number, number][] {
  const toVec = (p: LonLat): [number, number, number] => [
    Math.cos(p[1] * RAD) * Math.cos(p[0] * RAD),
    Math.cos(p[1] * RAD) * Math.sin(p[0] * RAD),
    Math.sin(p[1] * RAD),
  ];
  const va = toVec(a);
  const vb = toVec(b);
  const dot = Math.min(1, Math.max(-1, va[0] * vb[0] + va[1] * vb[1] + va[2] * vb[2]));
  const omega = Math.acos(dot);
  if (omega < 1e-9) return [[a[0], a[1]]];
  const out: [number, number][] = [];
  let prevLon = a[0];
  for (let i = 0; i <= steps; i++) {
    const f = i / steps;
    const k1 = Math.sin((1 - f) * omega) / Math.sin(omega);
    const k2 = Math.sin(f * omega) / Math.sin(omega);
    const x = k1 * va[0] + k2 * vb[0];
    const y = k1 * va[1] + k2 * vb[1];
    const z = k1 * va[2] + k2 * vb[2];
    let lon = Math.atan2(y, x) * DEG;
    // Keep the path continuous across the antimeridian.
    while (lon - prevLon > 180) lon -= 360;
    while (lon - prevLon < -180) lon += 360;
    prevLon = lon;
    out.push([lon, Math.atan2(z, Math.hypot(x, y)) * DEG]);
  }
  return out;
}

/** Sub-solar point: declination and longitude of the sun at `date`, in degrees. */
export function solarPosition(date: Date): { declDeg: number; subLonDeg: number } {
  const d = date.getTime() / 86_400_000 - 10957.5; // days since J2000.0
  const g = (357.528 + 0.9856003 * d) * RAD;
  const L = 280.46 + 0.9856474 * d;
  const lambda = (L + 1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) * RAD;
  const eps = (23.439 - 0.0000004 * d) * RAD;
  const decl = Math.asin(Math.sin(eps) * Math.sin(lambda));
  const ra = Math.atan2(Math.cos(eps) * Math.sin(lambda), Math.cos(lambda)) * DEG;
  const gmst = 280.46061837 + 360.98564736629 * d;
  const sub = ((((ra - gmst) % 360) + 540) % 360) - 180;
  return { declDeg: decl * DEG, subLonDeg: sub };
}

/** Polygon ring covering the night side of the Earth (the grey line is its edge). */
export function nightPolygon(date: Date, stepDeg = 3): [number, number][] {
  const { declDeg, subLonDeg } = solarPosition(date);
  const tanDecl = Math.tan(Math.max(1e-3, Math.abs(declDeg)) * RAD) * (declDeg < 0 ? -1 : 1);
  const edge: [number, number][] = [];
  for (let lon = -180; lon <= 180; lon += stepDeg) {
    const lat = Math.atan(-Math.cos((lon - subLonDeg) * RAD) / tanDecl) * DEG;
    edge.push([lon, lat]);
  }
  // Night holds the pole opposite the sun's hemisphere.
  const pole = declDeg >= 0 ? -90 : 90;
  return [...edge, [180, pole], [-180, pole], edge[0] ?? [-180, 0]];
}

/** Compass point for a bearing, e.g. 45 -> "NE". */
export function compass(bearing: number): string {
  const names = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
  return names[Math.round(((bearing % 360) + 360) / 45) % 8] ?? 'N';
}
