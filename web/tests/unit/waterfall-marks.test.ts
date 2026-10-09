import { describe, expect, it } from 'vitest';
import { decodeMarks, MARK_LIFETIME_MS, signalWidthHz } from '../../src/lib/waterfall/marks';
import type { DecodeRow } from '../../src/lib/state/state';

function row(offset: number, receivedAt: number, extra: Partial<DecodeRow> = {}): DecodeRow {
  return {
    v: 1,
    type: 'decode',
    kind: 'activity',
    utc: '2026-10-09T01:00:00Z',
    text: 'CQ',
    snr_db: -12,
    offset_hz: offset,
    dial_hz: 7_107_000,
    freq_hz: null,
    speed: 'normal',
    from_call: null,
    to_call: null,
    grid: null,
    key: `k${String(offset)}-${String(receivedAt)}`,
    receivedAt,
    ...extra,
  };
}

const view = { lo: -500, hi: 3500, flip: false };

describe('decodeMarks', () => {
  it('places a signal on the offset axis with its speed-dependent width', () => {
    const [m] = decodeMarks([row(1500, 1000)], 1000, view);
    expect(m?.left).toBeCloseTo(50, 5); // (1500+500)/4000
    expect(m?.width).toBeCloseTo(1.25, 5); // 50 Hz of 4000
    expect(signalWidthHz('turbo')).toBeGreaterThan(signalWidthHz('normal'));
    expect(m?.alpha).toBe(1);
  });

  it('mirrors the axis for lower sideband', () => {
    const [m] = decodeMarks([row(0, 0)], 0, { lo: -500, hi: 3500, flip: true });
    expect(m?.left).toBeGreaterThan(80);
  });

  it('drops marks that are old or outside the window and fades the rest', () => {
    const now = 100_000;
    const marks = decodeMarks(
      [
        row(1000, now - MARK_LIFETIME_MS - 1),
        row(1200, now - MARK_LIFETIME_MS / 2),
        row(9000, now),
      ],
      now,
      view,
    );
    expect(marks).toHaveLength(1);
    expect(marks[0]?.alpha).toBeGreaterThan(0.2);
    expect(marks[0]?.alpha).toBeLessThan(1);
  });

  it('flags directed messages', () => {
    const [m] = decodeMarks([row(900, 0, { kind: 'directed' })], 0, view);
    expect(m?.directed).toBe(true);
    expect(m?.title).toContain('900 Hz');
  });
});
