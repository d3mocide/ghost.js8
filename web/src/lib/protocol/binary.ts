/**
 * Binary WebSocket frames from the bridge. Spec: docs/protocol.md.
 * All integers little-endian. Mirrors bridge/src/ghostjs8/contract/binary.py.
 */

export const CHANNEL_AUDIO = 0x01;
export const CHANNEL_WATERFALL = 0x02;
export const AUDIO_HEADER_BYTES = 12;
export const WATERFALL_HEADER_BYTES = 16;

export interface AudioFrame {
  readonly kind: 'audio';
  readonly seq: number;
  readonly sampleRate: number;
  readonly adcOverload: boolean;
  /** Mono samples scaled to [-1, 1). */
  readonly samples: Float32Array;
}

export interface WaterfallFrame {
  readonly kind: 'waterfall';
  readonly seq: number;
  readonly startHz: number;
  readonly spanHz: number;
  /** u8 per bin; dBm ~= value - 255. */
  readonly bins: Uint8Array;
}

export type BinaryFrame = AudioFrame | WaterfallFrame;

export class FrameError extends Error {}

export function decodeFrame(buffer: ArrayBuffer): BinaryFrame {
  const view = new DataView(buffer);
  if (buffer.byteLength < 1) throw new FrameError('empty frame');
  const channel = view.getUint8(0);
  if (channel === CHANNEL_AUDIO) return decodeAudio(buffer, view);
  if (channel === CHANNEL_WATERFALL) return decodeWaterfall(buffer, view);
  throw new FrameError(`unknown channel 0x${channel.toString(16)}`);
}

function decodeAudio(buffer: ArrayBuffer, view: DataView): AudioFrame {
  if (buffer.byteLength < AUDIO_HEADER_BYTES) throw new FrameError('truncated audio header');
  const pcmBytes = buffer.byteLength - AUDIO_HEADER_BYTES;
  if (pcmBytes % 2 !== 0) throw new FrameError('odd PCM byte count');
  const n = pcmBytes / 2;
  const samples = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    samples[i] = view.getInt16(AUDIO_HEADER_BYTES + i * 2, true) / 32768;
  }
  return {
    kind: 'audio',
    seq: view.getUint32(4, true),
    sampleRate: view.getUint32(8, true),
    adcOverload: (view.getUint8(1) & 0x01) !== 0,
    samples,
  };
}

function decodeWaterfall(buffer: ArrayBuffer, view: DataView): WaterfallFrame {
  if (buffer.byteLength < WATERFALL_HEADER_BYTES)
    throw new FrameError('truncated waterfall header');
  const bins = view.getUint16(2, true);
  if (buffer.byteLength !== WATERFALL_HEADER_BYTES + bins) {
    throw new FrameError(
      `waterfall row has ${String(buffer.byteLength - 16)} bytes, header says ${String(bins)}`,
    );
  }
  return {
    kind: 'waterfall',
    seq: view.getUint32(4, true),
    startHz: view.getUint32(8, true),
    spanHz: view.getUint32(12, true),
    bins: new Uint8Array(buffer, WATERFALL_HEADER_BYTES, bins),
  };
}
