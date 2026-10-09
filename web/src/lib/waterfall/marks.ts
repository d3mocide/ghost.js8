/**
 * Where recent decodes sit on the waterfall's audio-offset axis, so the display
 * shows which signals the decoder actually copied (not just what is audible).
 */
import type { DecodeRow } from '../state/state';

/** Marks fade out over this long after the frame was decoded. */
export const MARK_LIFETIME_MS = 60_000;

/** Approximate occupied bandwidth of a JS8 signal by speed, in hertz. */
export function signalWidthHz(speed: string): number {
  switch (speed.toLowerCase()) {
    case 'slow':
      return 25;
    case 'fast':
      return 80;
    case 'turbo':
      return 160;
    case 'ultra':
      return 250;
    default:
      return 50;
  }
}

export interface DecodeMark {
  readonly key: string;
  /** Percent of the strip width. */
  readonly left: number;
  readonly width: number;
  /** 1 when fresh, fading to 0.2. */
  readonly alpha: number;
  readonly directed: boolean;
  readonly title: string;
}

export function decodeMarks(
  rows: readonly DecodeRow[],
  now: number,
  view: { readonly lo: number; readonly hi: number; readonly flip: boolean },
): DecodeMark[] {
  const span = view.hi - view.lo;
  if (span <= 0) return [];
  const pct = (offset: number): number => {
    const f = (offset - view.lo) / span;
    return (view.flip ? 1 - f : f) * 100;
  };
  const out: DecodeMark[] = [];
  for (const d of rows) {
    const age = now - d.receivedAt;
    if (age < 0 || age > MARK_LIFETIME_MS) continue;
    const a = pct(d.offset_hz);
    const b = pct(d.offset_hz + signalWidthHz(d.speed));
    const left = Math.min(a, b);
    if (left > 100 || Math.max(a, b) < 0) continue; // outside the visible window
    out.push({
      key: d.key,
      left: Math.max(0, left),
      width: Math.max(0.8, Math.abs(b - a)),
      alpha: 1 - (age / MARK_LIFETIME_MS) * 0.8,
      directed: d.kind === 'directed',
      title: `${String(d.offset_hz)} Hz · ${d.snr_db > 0 ? '+' : ''}${String(d.snr_db)} dB · ${d.text}`,
    });
  }
  return out;
}
