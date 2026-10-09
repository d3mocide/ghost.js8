import { describe, expect, it } from 'vitest';
import { PcmRing } from '../../src/lib/audio/ring';

const seq = (from: number, n: number): Float32Array =>
  Float32Array.from({ length: n }, (_, i) => from + i);

describe('PcmRing', () => {
  it('outputs silence until prebuffered, then plays in order', () => {
    const r = new PcmRing(16, 4);
    const out = new Float32Array(3);
    r.push(seq(1, 3));
    expect(r.pull(out)).toBe(0);
    expect(Array.from(out)).toEqual([0, 0, 0]);
    r.push(seq(4, 3));
    expect(r.pull(out)).toBe(3);
    expect(Array.from(out)).toEqual([1, 2, 3]);
  });

  it('is bounded: overflow drops the oldest samples', () => {
    const r = new PcmRing(4, 1);
    r.push(seq(1, 6));
    expect(r.available).toBe(4);
    expect(r.dropped).toBe(2);
    const out = new Float32Array(4);
    r.pull(out);
    expect(Array.from(out)).toEqual([3, 4, 5, 6]);
  });

  it('a single oversized push keeps only the newest capacity samples', () => {
    const r = new PcmRing(3, 1);
    r.push(seq(1, 10));
    const out = new Float32Array(3);
    r.pull(out);
    expect(Array.from(out)).toEqual([8, 9, 10]);
    expect(r.dropped).toBe(7);
  });

  it('resyncs after an underrun instead of stuttering', () => {
    const r = new PcmRing(16, 4);
    r.push(seq(1, 5));
    const out = new Float32Array(4);
    r.pull(out); // 1..4
    expect(r.pull(out)).toBe(1); // 5 then silence -> underrun
    expect(r.underruns).toBe(3);
    r.push(seq(6, 2));
    expect(r.pull(out)).toBe(0); // waits for a fresh prebuffer
    r.push(seq(8, 2));
    expect(r.pull(out)).toBe(4);
    expect(Array.from(out)).toEqual([6, 7, 8, 9]);
  });

  it('caps the backlog below capacity and resyncs to the newest audio', () => {
    const r = new PcmRing(16, 2, 4);
    r.push(seq(1, 6));
    expect(r.available).toBe(4);
    expect(r.dropped).toBe(2);
    const out = new Float32Array(4);
    r.pull(out);
    expect(Array.from(out)).toEqual([3, 4, 5, 6]);
  });

  it('rejects impossible configuration and clears', () => {
    expect(() => new PcmRing(2, 3)).toThrow(RangeError);
    expect(() => new PcmRing(4, 3, 2)).toThrow(RangeError);
    expect(() => new PcmRing(4, 1, 5)).toThrow(RangeError);
    const r = new PcmRing(4, 1);
    r.push(seq(1, 2));
    r.clear();
    expect(r.available).toBe(0);
  });
});
