import { describe, expect, it } from 'vitest';
import {
  bearingDeg,
  compass,
  destination,
  greatCircle,
  nightPolygon,
  ring,
  solarPosition,
} from '../../src/lib/geo';
import { distanceKm } from '../../src/lib/grid';

describe('geo', () => {
  it('computes bearings', () => {
    expect(Math.round(bearingDeg([0, 0], [0, 10]))).toBe(0);
    expect(Math.round(bearingDeg([0, 0], [10, 0]))).toBe(90);
    expect(Math.round(bearingDeg([0, 0], [0, -10]))).toBe(180);
    expect(Math.round(bearingDeg([0, 0], [-10, 0]))).toBe(270);
    expect(compass(45)).toBe('NE');
    expect(compass(359)).toBe('N');
    expect(compass(181)).toBe('S');
  });

  it('puts ring points at the requested distance', () => {
    const home: [number, number] = [-84, 34];
    for (const p of ring(home, 1000, 12)) {
      expect(Math.round(distanceKm(home, p))).toBe(1000);
    }
    expect(destination([0, 0], 90, 111.19)[0]).toBeCloseTo(1, 1);
  });

  it('draws a continuous great circle between two points', () => {
    const path = greatCircle([-84, 34], [139, 35], 20);
    expect(path[0]?.[0]).toBeCloseTo(-84, 5);
    expect(path.at(-1)?.[1]).toBeCloseTo(35, 3);
    for (let i = 1; i < path.length; i++) {
      expect(Math.abs((path[i]?.[0] ?? 0) - (path[i - 1]?.[0] ?? 0))).toBeLessThan(60);
    }
  });

  it('finds the sun near the tropic at the June solstice', () => {
    const { declDeg, subLonDeg } = solarPosition(new Date(Date.UTC(2026, 5, 21, 12, 0, 0)));
    expect(declDeg).toBeGreaterThan(23.2);
    expect(declDeg).toBeLessThan(23.6);
    expect(Math.abs(subLonDeg)).toBeLessThan(3);
  });

  it('shades the southern pole in northern summer and the northern pole in winter', () => {
    const summer = nightPolygon(new Date(Date.UTC(2026, 5, 21, 12)));
    expect(summer.some((p) => p[1] === -90)).toBe(true);
    const winter = nightPolygon(new Date(Date.UTC(2026, 11, 21, 12)));
    expect(winter.some((p) => p[1] === 90)).toBe(true);
  });
});
