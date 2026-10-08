/**
 * WebAudio playback of the receiver's 12 kHz PCM. The AudioContext runs at
 * 12 kHz so the browser does the resampling. Must be started from a user
 * gesture (autoplay policy). stop() releases every audio resource.
 */
import workletUrl from './pcm-worklet.ts?worker&url';

export interface PlayerStats {
  buffered: number;
  dropped: number;
  underruns: number;
}

export class AudioPlayer {
  private ctx: AudioContext | null = null;
  private node: AudioWorkletNode | null = null;
  private gain: GainNode | null = null;
  private volume = 0.8;
  private muted = false;
  onStats: ((stats: PlayerStats) => void) | null = null;

  get running(): boolean {
    return this.ctx !== null;
  }

  async start(sampleRate = 12_000): Promise<void> {
    if (this.ctx) return;
    const ctx = new AudioContext({ sampleRate, latencyHint: 'interactive' });
    try {
      await ctx.audioWorklet.addModule(workletUrl);
      const node = new AudioWorkletNode(ctx, 'ghost-pcm', {
        numberOfInputs: 0,
        outputChannelCount: [1],
      });
      const gain = ctx.createGain();
      node.connect(gain).connect(ctx.destination);
      node.port.onmessage = (ev: MessageEvent<PlayerStats>) => this.onStats?.(ev.data);
      this.ctx = ctx;
      this.node = node;
      this.gain = gain;
      this.applyGain();
      await ctx.resume();
    } catch (err) {
      await ctx.close();
      throw err;
    }
  }

  push(samples: Float32Array): void {
    // Transfer, don't copy: the buffer belongs to the worklet from here on.
    this.node?.port.postMessage(samples, [samples.buffer]);
  }

  setVolume(volume: number): void {
    this.volume = Math.min(1, Math.max(0, volume));
    this.applyGain();
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
    this.applyGain();
  }

  async stop(): Promise<void> {
    const ctx = this.ctx;
    this.node?.port.close();
    this.node?.disconnect();
    this.gain?.disconnect();
    this.ctx = this.node = this.gain = null;
    if (ctx) await ctx.close();
  }

  private applyGain(): void {
    if (this.gain && this.ctx) {
      this.gain.gain.setTargetAtTime(this.muted ? 0 : this.volume, this.ctx.currentTime, 0.02);
    }
  }
}
