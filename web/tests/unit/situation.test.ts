import { describe, expect, it } from 'vitest';
import type { Component, Health, Session } from '../../src/lib/protocol/generated';
import { situation } from '../../src/lib/state/situation';
import { initialState, type AppState } from '../../src/lib/state/state';

const NOW = Date.parse('2026-10-08T03:00:00Z');
const ok: Component = { state: 'ok', since: '2026-10-08T02:00:00Z', last_seen: null, detail: '' };
const down = (detail: string): Component => ({ ...ok, state: 'down', detail });

function health(
  over: Partial<Health['components']> = {},
  lastDecode: string | null = null,
): Health {
  return {
    v: 1,
    type: 'health',
    utc: '2026-10-08T03:00:00Z',
    overall: 'listening',
    last_decode_utc: lastDecode,
    components: {
      bridge: ok,
      decoder_process: ok,
      decoder_api: ok,
      decoder_capture: ok,
      receiver: ok,
      audio: ok,
      waterfall: ok,
      ...over,
    },
  };
}

function session(over: Partial<Session> = {}): Session {
  return {
    v: 1,
    type: 'session',
    state: 'connected',
    receiver: { host: 'kiwi.example', port: 8073, name: null, tls: false },
    tuning: { dial_hz: 14_078_000, mode: 'usb', low_cut_hz: 100, high_cut_hz: 3000 },
    subscribers: 1,
    reject_reason: null,
    detail: '',
    next_retry_utc: null,
    ...over,
  };
}

const state = (over: Partial<AppState>): AppState => ({ ...initialState, link: 'open', ...over });
const code = (s: AppState): string => situation(s, NOW).code;

describe('situation', () => {
  it('link first', () => {
    expect(code({ ...initialState, link: 'reconnecting' })).toBe('link');
  });

  it('decoder offline is an alert, independent of the band', () => {
    expect(
      code(
        state({
          health: health({ decoder_process: down('JS8Call process not running') }),
          session: session(),
        }),
      ),
    ).toBe('decoder-down');
  });

  it('receiver full and busy are explained and offer switching', () => {
    const full = situation(
      state({ health: health(), session: session({ state: 'rejected', reject_reason: 'full' }) }),
      NOW,
    );
    expect([full.code, full.suggestSwitch]).toEqual(['receiver-full', true]);
    expect(
      code(
        state({ health: health(), session: session({ state: 'rejected', reject_reason: 'busy' }) }),
      ),
    ).toBe('receiver-busy');
  });

  it('ADC overload says volume will not fix it', () => {
    const s = situation(
      state({
        health: health(),
        session: session(),
        receiverStatus: {
          v: 1,
          type: 'receiver_status',
          adc_overload: true,
          rssi_dbm: -20,
          info: {},
        },
      }),
      NOW,
    );
    expect(s.code).toBe('adc-overload');
    expect(s.detail).toMatch(/volume cannot fix/i);
    expect(s.suggestSwitch).toBe(true);
  });

  it('band quiet is not a fault', () => {
    const s = situation(
      state({ health: health({}, '2026-10-08T02:40:00Z'), session: session() }),
      NOW,
    );
    expect([s.code, s.tone]).toEqual(['band-quiet', 'info']);
  });

  it('recent decodes mean listening', () => {
    expect(code(state({ health: health({}, '2026-10-08T02:59:00Z'), session: session() }))).toBe(
      'listening',
    );
  });

  it('no receiver selected', () => {
    expect(
      code(state({ health: health(), session: session({ state: 'idle', receiver: null }) })),
    ).toBe('no-receiver');
  });
});
