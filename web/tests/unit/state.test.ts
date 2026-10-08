import { describe, expect, it } from 'vitest';
import type { Decode, ServerMessage, Station } from '../../src/lib/protocol/generated';
import {
  initialState,
  mappableStations,
  MAX_DECODES,
  reduce,
  stationList,
  type AppState,
} from '../../src/lib/state/state';

const base: Decode = {
  v: 1,
  type: 'decode',
  kind: 'activity',
  utc: '2026-10-08T02:26:58.000Z',
  text: 'K0OG: KN4CRD SNR +02',
  snr_db: -20,
  offset_hz: 702,
  dial_hz: 14_078_000,
  freq_hz: 14_078_702,
  speed: 'normal',
  from_call: 'K0OG',
  to_call: null,
  grid: null,
};

const station = (callsign: string, heard: string, grid: string | null): Station => ({
  v: 1,
  type: 'station',
  callsign,
  last_heard_utc: heard,
  snr_db: -10,
  grid,
  offset_hz: 700,
  dial_hz: 14_078_000,
  heard_count: 1,
});

const apply = (state: AppState, ...msgs: ServerMessage[]): AppState =>
  msgs.reduce((s, message) => reduce(s, { type: 'server', message, now: 0 }), state);

describe('reducer', () => {
  it('collapses activity + directed records of one transmission into one directed row', () => {
    const s = apply(initialState, base, { ...base, kind: 'directed', to_call: 'KN4CRD' });
    expect(s.decodes).toHaveLength(1);
    expect(s.decodes[0]?.kind).toBe('directed');
    expect(s.decodes[0]?.to_call).toBe('KN4CRD');
    // order independence
    const t = apply(initialState, { ...base, kind: 'directed', to_call: 'KN4CRD' }, base);
    expect(t.decodes[0]?.kind).toBe('directed');
  });

  it('keeps distinct transmissions and bounds the timeline', () => {
    const many: Decode[] = Array.from({ length: MAX_DECODES + 10 }, (_, i) => ({
      ...base,
      offset_hz: i,
    }));
    const s = apply(initialState, ...many);
    expect(s.decodes).toHaveLength(MAX_DECODES);
    expect(s.decodes[0]?.offset_hz).toBe(10);
  });

  it('history replaces, live messages append', () => {
    const s = apply(initialState, base, {
      v: 1,
      type: 'history',
      decodes: [{ ...base, offset_hz: 1 }],
      stations: [station('A1A', '2026-10-08T00:00:00Z', 'EN34')],
    });
    expect(s.decodes.map((d) => d.offset_hz)).toEqual([1]);
    expect(Object.keys(s.stations)).toEqual(['A1A']);
  });

  it('only stations with valid grids are mappable; list is newest first', () => {
    const s = apply(
      initialState,
      station('OLD', '2026-10-08T00:00:00Z', 'EN34'),
      station('NEW', '2026-10-08T01:00:00Z', null),
      station('BAD', '2026-10-08T02:00:00Z', 'ZZ99'),
    );
    expect(stationList(s).map((x) => x.callsign)).toEqual(['BAD', 'NEW', 'OLD']);
    expect(mappableStations(s).map((x) => x.callsign)).toEqual(['OLD']);
    expect(s.stations['BAD']?.grid).toBeNull();
  });

  it('tracks link, errors and binary freshness', () => {
    let s = reduce(initialState, { type: 'link', link: 'open' });
    s = reduce(s, { type: 'binary', channel: 'waterfall', now: 42 });
    s = apply(s, { v: 1, type: 'error', code: 'rate_limited', message: 'slow down' });
    expect([s.link, s.lastWaterfallAt, s.lastError?.code]).toEqual(['open', 42, 'rate_limited']);
    expect(reduce(s, { type: 'clear-error' }).lastError).toBeNull();
  });
});
