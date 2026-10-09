import { describe, expect, it, vi } from 'vitest';
import { WaterfallRenderer } from '../../src/lib/waterfall/renderer';
import type { WaterfallFrame } from '../../src/lib/protocol/binary';

/** Just enough of a 2D canvas for the renderer: sizes and the calls it makes. */
function fakeCanvas(): HTMLCanvasElement {
  const ctx = {
    createImageData: (w: number, h: number) => ({
      data: new Uint8ClampedArray(w * h * 4),
      width: w,
      height: h,
    }),
    fillRect: vi.fn(),
    drawImage: vi.fn(),
    putImageData: vi.fn(),
    fillStyle: '',
  };
  return { width: 0, height: 0, getContext: () => ctx } as unknown as HTMLCanvasElement;
}

const frame: WaterfallFrame = {
  startHz: 14_078_000,
  spanHz: 12_000,
  bins: new Uint8Array(1024).fill(200),
} as unknown as WaterfallFrame;

describe('WaterfallRenderer', () => {
  it('paints rows on a renderer rebuilt over an already-sized canvas', () => {
    const canvas = fakeCanvas();
    const first = new WaterfallRenderer(canvas, 'spectre');
    first.resize(300, 100, 1);

    // What a colormap change used to do: a new renderer on the same canvas.
    const second = new WaterfallRenderer(canvas, 'viridis');
    second.resize(300, 100, 1);
    second.setView(14_078_000 - 500, 14_078_000 + 3500);

    const ctx = canvas.getContext('2d') as unknown as { putImageData: ReturnType<typeof vi.fn> };
    ctx.putImageData.mockClear();
    second.push(frame);
    expect(ctx.putImageData).toHaveBeenCalled();
  });
});
