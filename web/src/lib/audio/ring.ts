/**
 * Bounded PCM ring buffer with drop/resync semantics, used inside the
 * AudioWorklet. Latency never grows: overflow drops the oldest samples, and
 * an underrun outputs silence until `prebuffer` samples have accumulated.
 * Framework-free and allocation-free on the hot path.
 */
export class PcmRing {
  private readonly buf: Float32Array;
  private read = 0;
  private write = 0;
  private count = 0;
  private primed = false;
  /** Samples discarded to keep latency bounded. */
  dropped = 0;
  /** Output samples filled with silence because no audio was available. */
  underruns = 0;

  constructor(
    readonly capacity: number,
    readonly prebuffer: number,
  ) {
    if (prebuffer > capacity) throw new RangeError('prebuffer exceeds capacity');
    this.buf = new Float32Array(capacity);
  }

  get available(): number {
    return this.count;
  }

  push(samples: Float32Array): void {
    let src = samples;
    if (src.length > this.capacity) {
      this.dropped += src.length - this.capacity;
      src = src.subarray(src.length - this.capacity);
    }
    const overflow = this.count + src.length - this.capacity;
    if (overflow > 0) {
      this.read = (this.read + overflow) % this.capacity;
      this.count -= overflow;
      this.dropped += overflow;
    }
    for (let i = 0; i < src.length; i++) {
      this.buf[this.write] = src[i] ?? 0;
      this.write = (this.write + 1) % this.capacity;
    }
    this.count += src.length;
  }

  /** Fill `out` completely; returns the number of real (non-silence) samples. */
  pull(out: Float32Array): number {
    if (!this.primed && this.count >= this.prebuffer) this.primed = true;
    if (!this.primed) {
      out.fill(0);
      this.underruns += out.length;
      return 0;
    }
    const n = Math.min(out.length, this.count);
    for (let i = 0; i < n; i++) {
      out[i] = this.buf[this.read] ?? 0;
      this.read = (this.read + 1) % this.capacity;
    }
    this.count -= n;
    if (n < out.length) {
      out.fill(0, n);
      this.underruns += out.length - n;
      this.primed = false; // resync: wait for a fresh prebuffer instead of stuttering
    }
    return n;
  }

  clear(): void {
    this.read = this.write = this.count = 0;
    this.primed = false;
  }
}
