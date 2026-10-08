import { describe, expect, it } from 'vitest';
import { decodeFrame, FrameError } from '../../src/lib/protocol/binary';

function audioFrame(seq: number, flags: number, samples: number[]): ArrayBuffer {
  const buf = new ArrayBuffer(12 + samples.length * 2);
  const v = new DataView(buf);
  v.setUint8(0, 1);
  v.setUint8(1, flags);
  v.setUint32(4, seq, true);
  v.setUint32(8, 12000, true);
  samples.forEach((s, i) => {
    v.setInt16(12 + i * 2, s, true);
  });
  return buf;
}

function wfFrame(bins: number[], declared = bins.length): ArrayBuffer {
  const buf = new ArrayBuffer(16 + bins.length);
  const v = new DataView(buf);
  v.setUint8(0, 2);
  v.setUint16(2, declared, true);
  v.setUint32(4, 9, true);
  v.setUint32(8, 14_000_000, true);
  v.setUint32(12, 12_000, true);
  bins.forEach((b, i) => {
    v.setUint8(16 + i, b);
  });
  return buf;
}

describe('decodeFrame', () => {
  it('decodes little-endian audio to float samples', () => {
    const f = decodeFrame(audioFrame(7, 1, [16384, -32768, 0]));
    expect(f.kind).toBe('audio');
    if (f.kind !== 'audio') return;
    expect(f.seq).toBe(7);
    expect(f.sampleRate).toBe(12000);
    expect(f.adcOverload).toBe(true);
    expect(Array.from(f.samples)).toEqual([0.5, -1, 0]);
  });

  it('decodes waterfall rows', () => {
    const f = decodeFrame(wfFrame([1, 2, 3]));
    expect(f.kind).toBe('waterfall');
    if (f.kind !== 'waterfall') return;
    expect([f.seq, f.startHz, f.spanHz]).toEqual([9, 14_000_000, 12_000]);
    expect(Array.from(f.bins)).toEqual([1, 2, 3]);
  });

  it('rejects malformed frames', () => {
    expect(() => decodeFrame(new ArrayBuffer(0))).toThrow(FrameError);
    expect(() => decodeFrame(new Uint8Array([9]).buffer)).toThrow(FrameError);
    expect(() => decodeFrame(audioFrame(1, 0, [1]).slice(0, 13))).toThrow(FrameError);
    expect(() => decodeFrame(wfFrame([1, 2, 3], 4))).toThrow(FrameError);
  });
});
