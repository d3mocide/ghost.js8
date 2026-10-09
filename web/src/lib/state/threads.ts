/**
 * Stitches JS8 activity frames into per-station threads.
 *
 * A JS8 message goes out as one frame per slot, so the raw activity feed shows
 * it in pieces, interleaved with every other station on the band. Frames from
 * one station share an audio offset (it drifts a few hertz at most) and arrive
 * a slot apart. This groups them on that basis; it is a display aid, not a
 * decoder, and a frame the decoder missed shows as a gap marker.
 */
import type { DecodeRow } from './state';

/** Frames more than this many hertz apart are different stations. */
export const OFFSET_TOLERANCE_HZ = 15;
/** Beyond this many slots of silence a new thread starts. */
const MAX_GAP_SLOTS = 2.5;
/** Beyond this many slots, a frame in between was probably missed. */
const MISSED_SLOTS = 1.5;
export const GAP_MARK = '[…]'; // distinct from the decoder's own … for undecodable text

/** Seconds per JS8 transmit slot for a decode's speed label. */
export function slotSeconds(speed: string): number {
  switch (speed.toLowerCase()) {
    case 'slow':
      return 30;
    case 'fast':
      return 10;
    case 'turbo':
      return 6;
    default:
      return 15;
  }
}

export interface Thread {
  readonly kind: 'thread';
  readonly key: string;
  readonly offset_hz: number;
  readonly firstUtc: string;
  readonly lastUtc: string;
  readonly snr_db: number;
  readonly frames: number;
  readonly gaps: number;
  readonly text: string;
}

export interface Single {
  readonly kind: 'single';
  readonly key: string;
  readonly row: DecodeRow;
}

export type TrafficItem = Thread | Single;

interface Open {
  key: string;
  offset: number;
  slotMs: number;
  firstUtc: string;
  lastUtc: string;
  lastMs: number;
  snr: number;
  frames: number;
  gaps: number;
  parts: string[];
}

/**
 * `rows` oldest first. Returns items newest-first by last update. Directed
 * messages are already assembled by JS8Call and pass through unchanged.
 */
export function groupThreads(rows: readonly DecodeRow[]): TrafficItem[] {
  const items: [number, TrafficItem][] = [];
  const open: Open[] = [];

  for (const row of rows) {
    const ms = Date.parse(row.utc);
    if (row.kind !== 'activity' || Number.isNaN(ms)) {
      items.push([Number.isNaN(ms) ? 0 : ms, { kind: 'single', key: row.key, row }]);
      continue;
    }
    const slotMs = slotSeconds(row.speed) * 1000;
    let best: Open | null = null;
    for (const t of open) {
      const dt = ms - t.lastMs;
      if (dt < 0 || dt > MAX_GAP_SLOTS * t.slotMs) continue;
      if (Math.abs(row.offset_hz - t.offset) > OFFSET_TOLERANCE_HZ) continue;
      if (
        best === null ||
        Math.abs(row.offset_hz - t.offset) < Math.abs(row.offset_hz - best.offset)
      )
        best = t;
    }
    if (best === null) {
      best = {
        key: `thread:${row.key}`,
        offset: row.offset_hz,
        slotMs,
        firstUtc: row.utc,
        lastUtc: row.utc,
        lastMs: ms,
        snr: row.snr_db,
        frames: 0,
        gaps: 0,
        parts: [],
      };
      open.push(best);
    } else if (ms - best.lastMs > MISSED_SLOTS * best.slotMs) {
      best.gaps += 1;
      best.parts.push(GAP_MARK);
    }
    best.parts.push(row.text);
    best.frames += 1;
    best.offset = row.offset_hz;
    best.lastUtc = row.utc;
    best.lastMs = ms;
    best.snr = row.snr_db;
  }

  for (const t of open) {
    items.push([
      t.lastMs,
      {
        kind: 'thread',
        key: t.key,
        offset_hz: t.offset,
        firstUtc: t.firstUtc,
        lastUtc: t.lastUtc,
        snr_db: t.snr,
        frames: t.frames,
        gaps: t.gaps,
        text: t.parts.join(' '),
      },
    ]);
  }
  return items.sort((a, b) => b[0] - a[0]).map(([, item]) => item);
}
