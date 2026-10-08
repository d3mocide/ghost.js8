/**
 * AudioWorklet: plays PCM posted from the main thread through a bounded ring.
 * Runs in AudioWorkletGlobalScope (not covered by the DOM lib), so the few
 * globals used are declared here.
 */
import { PcmRing } from './ring';

declare const sampleRate: number;
declare function registerProcessor(name: string, ctor: new () => AudioWorkletProcessorLike): void;
declare const AudioWorkletProcessor: new () => { readonly port: MessagePort };
interface AudioWorkletProcessorLike {
  process(inputs: Float32Array[][], outputs: Float32Array[][]): boolean;
}

export const PROCESSOR_NAME = 'ghost-pcm';

class GhostPcmProcessor extends AudioWorkletProcessor implements AudioWorkletProcessorLike {
  // ~1 s ceiling, ~250 ms prebuffer: enough for network jitter, never a growing backlog.
  private readonly ring = new PcmRing(Math.round(sampleRate), Math.round(sampleRate / 4));
  private frames = 0;

  constructor() {
    super();
    this.port.onmessage = (ev: MessageEvent<unknown>) => {
      const data = ev.data;
      if (data instanceof Float32Array) this.ring.push(data);
      else if (data === 'clear') this.ring.clear();
    };
  }

  process(_inputs: Float32Array[][], outputs: Float32Array[][]): boolean {
    const out = outputs[0];
    const first = out?.[0];
    if (!out || !first) return true;
    this.ring.pull(first);
    for (let c = 1; c < out.length; c++) out[c]?.set(first);
    this.frames += first.length;
    if (this.frames >= sampleRate) {
      this.frames = 0;
      this.port.postMessage({
        buffered: this.ring.available,
        dropped: this.ring.dropped,
        underruns: this.ring.underruns,
      });
    }
    return true;
  }
}

registerProcessor(PROCESSOR_NAME, GhostPcmProcessor);
