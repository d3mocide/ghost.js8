import { describe, expect, it } from 'vitest';
import {
  GHOST,
  GHOST_EYES,
  RAMP,
  flicker,
  ghostTint,
  msToNextSlot,
  rampChar,
  ringChar,
  ringIntensity,
  staticField,
  valueNoise,
} from '../../src/lib/backdrop/ascii';

describe('ascii backdrop helpers', () => {
  it('value noise and the static field stay in [0, 1]', () => {
    for (let i = 0; i < 2000; i++) {
      const x = (i * 0.37) % 97;
      const y = (i * 0.61) % 53;
      const n = valueNoise(x, y);
      expect(n).toBeGreaterThanOrEqual(0);
      expect(n).toBeLessThanOrEqual(1);
      const f = staticField(x, y, i * 0.05);
      expect(f).toBeGreaterThanOrEqual(0);
      expect(f).toBeLessThanOrEqual(1);
      const k = flicker(i, i * 2, i * 0.1);
      expect(k).toBeGreaterThanOrEqual(0);
      expect(k).toBeLessThan(1.0000001);
    }
  });

  it('leaves most of the field empty so panels stay readable', () => {
    let empty = 0;
    const n = 4000;
    for (let i = 0; i < n; i++) if (staticField(i % 120, Math.floor(i / 120), 3) === 0) empty++;
    expect(empty / n).toBeGreaterThan(0.4);
  });

  it('maps intensity to the ramp, with jitter at most one step', () => {
    expect(rampChar(0)).toBe(' ');
    expect(rampChar(1)).toBe(RAMP.at(-1));
    const mid = RAMP.indexOf(rampChar(0.5));
    expect(Math.abs(RAMP.indexOf(rampChar(0.5, 0.05)) - mid)).toBeLessThanOrEqual(1);
    expect(Math.abs(RAMP.indexOf(rampChar(0.5, 0.95)) - mid)).toBeLessThanOrEqual(1);
  });

  it('rings peak on the wavefront and fade out with age', () => {
    const age = 1;
    const front = ringIntensity(14 * age, age);
    expect(front).toBeGreaterThan(ringIntensity(14 * age + 4, age));
    expect(front).toBeGreaterThan(ringIntensity(14 * age - 4, age));
    expect(ringIntensity(14 * 3, 3)).toBeLessThan(front);
    expect(ringIntensity(0, 10)).toBe(0);
    expect(ringIntensity(0, -1)).toBe(0);
  });

  it('draws rings as ((( ~ )))', () => {
    expect(ringChar(-5, 0)).toBe('(');
    expect(ringChar(5, 0)).toBe(')');
    expect(ringChar(0, 5)).toBe('~');
  });

  it('aligns slot pulses to UTC 15-second boundaries', () => {
    expect(msToNextSlot(Date.UTC(2026, 9, 9, 1, 0, 0))).toBe(0);
    expect(msToNextSlot(Date.UTC(2026, 9, 9, 1, 0, 1))).toBe(14_000);
    expect(msToNextSlot(Date.UTC(2026, 9, 9, 1, 0, 14, 900))).toBe(100);
  });

  it('keeps the ghost sprite rectangular', () => {
    const w = GHOST[0]?.length;
    for (const line of GHOST) expect(line.length).toBe(w);
  });

  it('draws two eyes in the ghost sprite', () => {
    const eyes = GHOST.join('')
      .split('')
      .filter((ch) => GHOST_EYES.includes(ch));
    expect(eyes.length).toBe(2);
  });

  it('tints the ghost from aqua on the left to violet on the right', () => {
    expect(ghostTint(0, 12)).toEqual([103, 232, 249]);
    expect(ghostTint(11, 12)).toEqual([167, 139, 250]);
    expect(ghostTint(0, 1)).toEqual([103, 232, 249]);
  });
});
