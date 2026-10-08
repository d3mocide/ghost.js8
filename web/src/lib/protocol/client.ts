/**
 * Browser side of the bridge WebSocket: reconnect with backoff, minimal
 * validation of server JSON, binary frame dispatch, and clean shutdown.
 */
import type { ClientMessage, ServerMessage } from './generated';
import { decodeFrame, FrameError, type BinaryFrame } from './binary';

export const PROTOCOL_VERSION = 1;

const SERVER_TYPES = new Set<string>([
  'hello',
  'history',
  'session',
  'health',
  'decode',
  'station',
  'receiver_status',
  'error',
  'pong',
]);

export function parseServerMessage(text: string): ServerMessage | null {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    return null;
  }
  if (typeof raw !== 'object' || raw === null) return null;
  const rec = raw as Record<string, unknown>;
  if (
    rec['v'] !== PROTOCOL_VERSION ||
    typeof rec['type'] !== 'string' ||
    !SERVER_TYPES.has(rec['type'])
  ) {
    return null;
  }
  return raw as ServerMessage;
}

export interface ClientHandlers {
  onMessage(message: ServerMessage): void;
  onFrame(frame: BinaryFrame): void;
  onLink(state: 'connecting' | 'open' | 'reconnecting' | 'closed'): void;
}

export interface SocketLike {
  binaryType: string;
  readyState: number;
  onopen: ((ev: Event) => void) | null;
  onclose: ((ev: CloseEvent) => void) | null;
  onmessage: ((ev: MessageEvent) => void) | null;
  onerror: ((ev: Event) => void) | null;
  send(data: string): void;
  close(code?: number, reason?: string): void;
}

export type SocketFactory = (url: string) => SocketLike;

export class BridgeClient {
  private socket: SocketLike | null = null;
  private stopped = true;
  private attempt = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private subscription = { audio: false, waterfall: false };

  constructor(
    private readonly url: string,
    private readonly handlers: ClientHandlers,
    private readonly makeSocket: SocketFactory = (u) => new WebSocket(u),
  ) {}

  start(): void {
    if (!this.stopped) return;
    this.stopped = false;
    this.connect();
  }

  /** Close the socket and stop reconnecting (call when leaving the view). */
  stop(): void {
    this.stopped = true;
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    const s = this.socket;
    this.socket = null;
    if (s) {
      s.onclose = s.onmessage = s.onerror = s.onopen = null;
      s.close(1000, 'view closed');
    }
    this.handlers.onLink('closed');
  }

  send(message: ClientMessage): boolean {
    const s = this.socket;
    if (!s || s.readyState !== 1) return false;
    s.send(JSON.stringify(message));
    return true;
  }

  subscribe(audio: boolean, waterfall: boolean): void {
    this.subscription = { audio, waterfall };
    this.send({ v: 1, type: 'subscribe', audio, waterfall });
  }

  private connect(): void {
    this.handlers.onLink(this.attempt === 0 ? 'connecting' : 'reconnecting');
    const s = this.makeSocket(this.url);
    this.socket = s;
    s.binaryType = 'arraybuffer';
    s.onopen = () => {
      this.attempt = 0;
      this.handlers.onLink('open');
      s.send(JSON.stringify({ v: 1, type: 'hello', client: 'ghost.js8-web' }));
      const { audio, waterfall } = this.subscription;
      s.send(JSON.stringify({ v: 1, type: 'subscribe', audio, waterfall }));
    };
    s.onmessage = (ev: MessageEvent) => {
      const data: unknown = ev.data;
      if (typeof data === 'string') {
        const msg = parseServerMessage(data);
        if (msg) this.handlers.onMessage(msg);
      } else if (data instanceof ArrayBuffer) {
        try {
          this.handlers.onFrame(decodeFrame(data));
        } catch (err) {
          if (!(err instanceof FrameError)) throw err;
        }
      }
    };
    s.onclose = () => {
      this.socket = null;
      if (this.stopped) return;
      this.attempt += 1;
      this.handlers.onLink('reconnecting');
      const delay =
        Math.min(15_000, 1000 * 2 ** Math.min(this.attempt - 1, 4)) * (0.75 + Math.random() * 0.5);
      this.timer = setTimeout(() => {
        this.timer = null;
        if (!this.stopped) this.connect();
      }, delay);
    };
    s.onerror = () => {
      /* onclose follows and handles reconnect */
    };
  }
}

export function defaultBridgeUrl(loc: Location = window.location): string {
  const scheme = loc.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${scheme}//${loc.host}/ws`;
}
