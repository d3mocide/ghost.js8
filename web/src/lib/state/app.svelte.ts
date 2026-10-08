/**
 * The running application: reactive state (Svelte runes) wired to the bridge
 * client and the audio player. Waterfall frames bypass reactivity and go
 * straight to registered renderers.
 */
import { AudioPlayer, type PlayerStats } from '../audio/player';
import { BridgeClient, defaultBridgeUrl } from '../protocol/client';
import type { WaterfallFrame } from '../protocol/binary';
import type { ClientMessage, ServerMessage } from '../protocol/generated';
import { initialState, reduce, type Action, type AppState } from './state';

type WaterfallListener = (frame: WaterfallFrame) => void;

export class GhostApp {
  state: AppState = $state(initialState);
  audioEnabled = $state(false);
  audioError = $state<string | null>(null);
  muted = $state(false);
  volume = $state(0.8);
  audioStats = $state<PlayerStats | null>(null);
  now = $state(Date.now());
  /** When this view started; older traffic (history) never raises live alerts. */
  readonly startedAt = Date.now();

  private readonly client: BridgeClient;
  private readonly player = new AudioPlayer();
  // Deliberately non-reactive: frames go straight to canvases, not through Svelte.
  // eslint-disable-next-line svelte/prefer-svelte-reactivity
  private readonly waterfallListeners = new Set<WaterfallListener>();
  private clock: ReturnType<typeof setInterval> | null = null;
  private lastBinaryTick = { audio: 0, waterfall: 0 };

  constructor(url: string = defaultBridgeUrl()) {
    this.client = new BridgeClient(url, {
      onMessage: (message: ServerMessage) => {
        this.dispatch({ type: 'server', message, now: Date.now() });
      },
      onLink: (link) => {
        this.dispatch({ type: 'link', link });
      },
      onFrame: (frame) => {
        const t = Date.now();
        if (frame.kind === 'audio') {
          if (this.audioEnabled) this.player.push(frame.samples);
          this.markBinary('audio', t);
        } else {
          for (const l of this.waterfallListeners) l(frame);
          this.markBinary('waterfall', t);
        }
      },
    });
    this.player.onStats = (s) => {
      this.audioStats = s;
    };
  }

  start(): void {
    this.client.start();
    this.clock = setInterval(() => {
      this.now = Date.now();
    }, 1000);
  }

  /** Release sockets, timers and audio (view leave). */
  async stop(): Promise<void> {
    this.client.stop();
    if (this.clock !== null) clearInterval(this.clock);
    this.clock = null;
    this.waterfallListeners.clear();
    await this.disableAudio();
  }

  dispatch(action: Action): void {
    this.state = reduce(this.state, action);
  }

  send(message: ClientMessage): boolean {
    return this.client.send(message);
  }

  onWaterfall(listener: WaterfallListener): () => void {
    this.waterfallListeners.add(listener);
    this.resubscribe();
    return () => {
      this.waterfallListeners.delete(listener);
      this.resubscribe();
    };
  }

  /** Must be called from a user gesture. */
  async enableAudio(): Promise<void> {
    this.audioError = null;
    try {
      await this.player.start(this.state.hello?.limits?.audio_sample_rate ?? 12_000);
      this.player.setVolume(this.volume);
      this.player.setMuted(this.muted);
      this.audioEnabled = true;
      this.resubscribe();
    } catch (err) {
      this.audioError = err instanceof Error ? err.message : String(err);
    }
  }

  async disableAudio(): Promise<void> {
    this.audioEnabled = false;
    this.resubscribe();
    await this.player.stop();
  }

  setVolume(v: number): void {
    this.volume = v;
    this.player.setVolume(v);
  }

  setMuted(m: boolean): void {
    this.muted = m;
    this.player.setMuted(m);
  }

  private resubscribe(): void {
    this.client.subscribe(this.audioEnabled, this.waterfallListeners.size > 0);
  }

  private markBinary(channel: 'audio' | 'waterfall', t: number): void {
    // Throttle reactive updates: freshness only needs ~2 Hz resolution.
    if (t - this.lastBinaryTick[channel] < 500) return;
    this.lastBinaryTick[channel] = t;
    this.dispatch({ type: 'binary', channel, now: t });
  }
}
