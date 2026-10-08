import { describe, expect, it } from 'vitest';
import { int16FromBigEndian } from '../../src/lib/pcm';

describe('int16FromBigEndian', () => {
  it('decodes big-endian samples', () => {
    expect(Array.from(int16FromBigEndian(new Uint8Array([0x01, 0x02, 0xff, 0xfe])))).toEqual([
      0x0102, -2,
    ]);
  });

  it('rejects odd byte lengths', () => {
    expect(() => int16FromBigEndian(new Uint8Array([1, 2, 3]))).toThrow(RangeError);
  });
});
