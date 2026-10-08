import { afterEach, describe, expect, it, vi } from 'vitest';
import { BridgeClient, parseServerMessage, type SocketLike } from '../../src/lib/protocol/client';

class FakeSocket implements SocketLike {
  binaryType = 'blob';
  readyState = 0;
  sent: string[] = [];
  closed: number | null = null;
  onopen: ((ev: Event) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  send(data: string): void {
    this.sent.push(data);
  }
  close(code?: number): void {
    this.closed = code ?? 1000;
  }
  open(): void {
    this.readyState = 1;
    this.onopen?.(new Event('open'));
  }
  message(data: unknown): void {
    this.onmessage?.({ data } as MessageEvent);
  }
  drop(): void {
    this.readyState = 3;
    this.onclose?.({} as CloseEvent);
  }
}

afterEach(() => {
  vi.useRealTimers();
});

describe('parseServerMessage', () => {
  it('accepts known v1 messages only', () => {
    expect(parseServerMessage('{"v":1,"type":"pong","utc":"x"}')?.type).toBe('pong');
    expect(parseServerMessage('{"v":2,"type":"pong"}')).toBeNull();
    expect(parseServerMessage('{"v":1,"type":"transmit"}')).toBeNull();
    expect(parseServerMessage('nope')).toBeNull();
    expect(parseServerMessage('[]')).toBeNull();
  });
});

describe('BridgeClient', () => {
  it('connects, says hello, re-subscribes, dispatches, reconnects and cleans up', () => {
    vi.useFakeTimers();
    const sockets: FakeSocket[] = [];
    const links: string[] = [];
    const messages: string[] = [];
    const frames: string[] = [];
    const client = new BridgeClient(
      'ws://x/ws',
      {
        onMessage: (m) => messages.push(m.type),
        onFrame: (f) => frames.push(f.kind),
        onLink: (l) => links.push(l),
      },
      () => {
        const s = new FakeSocket();
        sockets.push(s);
        return s;
      },
    );
    client.start();
    client.subscribe(true, false);
    const s0 = sockets[0];
    if (!s0) throw new Error('no socket');
    s0.open();
    expect(s0.binaryType).toBe('arraybuffer');
    expect(s0.sent.map((x) => JSON.parse(x) as { type: string }).map((x) => x.type)).toEqual([
      'hello',
      'subscribe',
    ]);
    expect(JSON.parse(s0.sent[1] ?? '{}')).toMatchObject({ audio: true, waterfall: false });

    s0.message('{"v":1,"type":"pong","utc":"x"}');
    s0.message('garbage');
    const wf = new ArrayBuffer(17);
    new DataView(wf).setUint8(0, 2);
    new DataView(wf).setUint16(2, 1, true);
    s0.message(wf);
    s0.message(new ArrayBuffer(3)); // malformed binary: ignored, no throw
    expect(messages).toEqual(['pong']);
    expect(frames).toEqual(['waterfall']);

    s0.drop();
    expect(links.at(-1)).toBe('reconnecting');
    vi.advanceTimersByTime(20_000);
    expect(sockets).toHaveLength(2);

    client.stop();
    expect(sockets[1]?.closed).toBe(1000);
    expect(links.at(-1)).toBe('closed');
    vi.advanceTimersByTime(60_000);
    expect(sockets).toHaveLength(2); // no reconnect after stop
  });
});
