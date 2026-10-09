/** Small, framework-free helpers for the decoded-traffic views and the map's talk lines. */
import type { LonLat } from './geo';

/** JS8Call prints an ellipsis for a frame it heard but could not decode. */
export function isNoiseFrame(text: string): boolean {
  return /^[\s.…]*$/.test(text);
}

/** Chip text for a non-default JS8 speed; null for normal. */
export function speedChip(speed: string): string | null {
  switch (speed.toLowerCase()) {
    case 'normal':
      return null;
    case 'slow':
    case 'fast':
    case 'turbo':
    case 'ultra':
      return speed.toUpperCase();
    default:
      return null; // 'unknown' is not worth a chip
  }
}

export interface TalkLink {
  readonly key: string;
  readonly from: string;
  readonly to: string;
  readonly path: readonly [LonLat, LonLat];
  readonly count: number;
  readonly lastMs: number;
}

interface Directed {
  readonly kind: string;
  readonly from_call: string | null;
  readonly to_call: string | null;
  readonly receivedAt: number;
}

/**
 * Who has been talking to whom: one link per (from, to) pair of directed messages,
 * between stations whose grids are known. Group addresses (@HB, @GHOSTNET) are not
 * a station and never produce a link.
 */
export function talkLinks(
  rows: readonly Directed[],
  locate: (callsign: string) => LonLat | null,
  now: number,
  windowMs: number,
): TalkLink[] {
  const pairs = new Map<string, { from: string; to: string; count: number; lastMs: number }>();
  for (const d of rows) {
    if (d.kind !== 'directed' || !d.from_call || !d.to_call) continue;
    const from = d.from_call.toUpperCase();
    const to = d.to_call.toUpperCase();
    if (to.startsWith('@') || from === to) continue;
    if (now - d.receivedAt > windowMs) continue;
    const key = `${from}>${to}`;
    const cur = pairs.get(key);
    if (cur) {
      cur.count += 1;
      cur.lastMs = Math.max(cur.lastMs, d.receivedAt);
    } else {
      pairs.set(key, { from, to, count: 1, lastMs: d.receivedAt });
    }
  }
  const out: TalkLink[] = [];
  for (const [key, p] of pairs) {
    const a = locate(p.from);
    const b = locate(p.to);
    if (a && b)
      out.push({ key, from: p.from, to: p.to, path: [a, b], count: p.count, lastMs: p.lastMs });
  }
  return out;
}
