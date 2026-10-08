/**
 * Pure application state + reducer. Components render from this; the
 * WebSocket client feeds it. Unit-tested without a browser.
 */
import type {
  Decode,
  Error as ServerError,
  Health,
  Hello,
  ReceiverStatus,
  ServerMessage,
  Session,
  Station,
} from '../protocol/generated';
import { normalizeGrid } from '../grid';

export type LinkState = 'connecting' | 'open' | 'reconnecting' | 'closed';

export interface DecodeRow extends Decode {
  /** Stable key: one JS8 transmission (activity + directed records collapse). */
  readonly key: string;
  readonly receivedAt: number;
}

export interface AppState {
  readonly link: LinkState;
  readonly hello: Hello | null;
  readonly session: Session | null;
  readonly health: Health | null;
  readonly receiverStatus: ReceiverStatus | null;
  readonly decodes: readonly DecodeRow[]; // oldest first
  readonly stations: Readonly<Record<string, Station>>;
  readonly lastError: ServerError | null;
  readonly lastAudioAt: number | null;
  readonly lastWaterfallAt: number | null;
}

export const MAX_DECODES = 500;

export const initialState: AppState = {
  link: 'connecting',
  hello: null,
  session: null,
  health: null,
  receiverStatus: null,
  decodes: [],
  stations: {},
  lastError: null,
  lastAudioAt: null,
  lastWaterfallAt: null,
};

export type Action =
  | { readonly type: 'server'; readonly message: ServerMessage; readonly now: number }
  | { readonly type: 'link'; readonly link: LinkState }
  | { readonly type: 'binary'; readonly channel: 'audio' | 'waterfall'; readonly now: number }
  | { readonly type: 'clear-error' };

export function decodeKey(d: Pick<Decode, 'utc' | 'offset_hz'>): string {
  return `${d.utc}|${String(d.offset_hz)}`;
}

function addDecodes(
  rows: readonly DecodeRow[],
  incoming: readonly Decode[],
  now: number,
): DecodeRow[] {
  const out = [...rows];
  const index = new Map(out.map((r, i) => [r.key, i]));
  for (const d of incoming) {
    const key = decodeKey(d);
    const at = index.get(key);
    const existing = at === undefined ? undefined : out[at];
    if (existing && at !== undefined) {
      // Same transmission reported again: keep one row, prefer the directed record's fields.
      if (d.kind === 'directed' || existing.kind !== 'directed') {
        out[at] = {
          ...existing,
          ...d,
          kind: existing.kind === 'directed' ? 'directed' : d.kind,
          key,
          receivedAt: existing.receivedAt,
        };
      }
      continue;
    }
    index.set(key, out.length);
    out.push({ ...d, grid: normalizeGrid(d.grid), key, receivedAt: now });
  }
  return out.length > MAX_DECODES ? out.slice(out.length - MAX_DECODES) : out;
}

function addStations(
  stations: Readonly<Record<string, Station>>,
  incoming: readonly Station[],
): Record<string, Station> {
  const out = { ...stations };
  for (const s of incoming) {
    out[s.callsign] = { ...s, grid: normalizeGrid(s.grid) };
  }
  return out;
}

export function reduce(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'link':
      return { ...state, link: action.link };
    case 'binary':
      return action.channel === 'audio'
        ? { ...state, lastAudioAt: action.now }
        : { ...state, lastWaterfallAt: action.now };
    case 'clear-error':
      return { ...state, lastError: null };
    case 'server':
      return reduceServer(state, action.message, action.now);
  }
}

function reduceServer(state: AppState, m: ServerMessage, now: number): AppState {
  switch (m.type) {
    case 'hello':
      return { ...state, hello: m };
    case 'history':
      return {
        ...state,
        decodes: addDecodes([], m.decodes, now),
        stations: addStations({}, m.stations),
      };
    case 'session':
      return { ...state, session: m };
    case 'health':
      return { ...state, health: m };
    case 'receiver_status':
      return { ...state, receiverStatus: m };
    case 'decode':
      return { ...state, decodes: addDecodes(state.decodes, [m], now) };
    case 'station':
      return { ...state, stations: addStations(state.stations, [m]) };
    case 'error':
      return { ...state, lastError: m };
    case 'pong':
      return state;
  }
}

/** Stations sorted by most recently heard. */
export function stationList(state: AppState): Station[] {
  return Object.values(state.stations).sort((a, b) =>
    b.last_heard_utc.localeCompare(a.last_heard_utc),
  );
}

/** Stations with a valid grid, for the map. */
export function mappableStations(state: AppState): Station[] {
  return stationList(state).filter((s) => normalizeGrid(s.grid) !== null);
}
