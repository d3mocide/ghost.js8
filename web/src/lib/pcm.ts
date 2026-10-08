/**
 * Convert big-endian signed 16-bit PCM bytes to an Int16Array in host order.
 * Shared helper; the browser receives little-endian PCM from the bridge, but
 * tests and tooling use this to reason about Kiwi framing.
 */
export function int16FromBigEndian(bytes: Uint8Array): Int16Array {
  if (bytes.byteLength % 2 !== 0) {
    throw new RangeError(`PCM byte length ${String(bytes.byteLength)} is not a multiple of 2`);
  }
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const out = new Int16Array(bytes.byteLength / 2);
  for (let i = 0; i < out.length; i++) out[i] = view.getInt16(i * 2, false);
  return out;
}
