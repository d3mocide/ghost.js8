/**
 * Canvas waterfall: newest row on top, older rows scroll down. The backing
 * store tracks panel size x devicePixelRatio. Pixel mapping lives in blit.ts.
 */
import { blitRow, DEFAULT_LEVELS, type Levels } from './blit';
import { colormapLut, type ColormapName } from './colormap';
import type { WaterfallFrame } from '../protocol/binary';

export class WaterfallRenderer {
  private readonly ctx: CanvasRenderingContext2D;
  private row: ImageData | null = null;
  private lut: Uint32Array;
  private viewLo = 0;
  private viewHi = 1;
  private levels: Levels = DEFAULT_LEVELS;
  private rowHeight = 1;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    colormap: ColormapName = 'spectre',
  ) {
    const ctx = canvas.getContext('2d', { alpha: false });
    if (!ctx) throw new Error('2D canvas unavailable');
    this.ctx = ctx;
    this.lut = colormapLut(colormap);
  }

  resize(cssWidth: number, cssHeight: number, dpr: number): void {
    const w = Math.max(1, Math.round(cssWidth * dpr));
    const h = Math.max(1, Math.round(cssHeight * dpr));
    // Skip only when the backing store is already sized and the row buffer exists;
    // a renderer rebuilt on an unchanged canvas still needs its row allocated.
    if (w === this.canvas.width && h === this.canvas.height && this.row) return;
    this.canvas.width = w;
    this.canvas.height = h;
    this.rowHeight = Math.max(1, Math.round(dpr));
    this.row = this.ctx.createImageData(w, 1);
    this.clear();
  }

  setView(loHz: number, hiHz: number): void {
    this.viewLo = loHz;
    this.viewHi = Math.max(loHz + 1, hiHz);
  }

  setColormap(name: ColormapName): void {
    this.lut = colormapLut(name);
  }

  setLevels(levels: Levels): void {
    this.levels = levels;
  }

  clear(): void {
    const v = this.lut[0] ?? 0; // little-endian RGBA packed as ABGR
    this.ctx.fillStyle = `rgb(${String(v & 255)} ${String((v >>> 8) & 255)} ${String((v >>> 16) & 255)})`;
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
  }

  push(frame: WaterfallFrame): void {
    const row = this.row;
    if (!row) return;
    const { width, height } = this.canvas;
    const rh = this.rowHeight;
    // Scroll everything down by one row, then paint the newest row at the top.
    this.ctx.drawImage(this.canvas, 0, 0, width, height - rh, 0, rh, width, height - rh);
    blitRow(
      frame.bins,
      {
        startHz: frame.startHz,
        spanHz: frame.spanHz,
        viewLoHz: this.viewLo,
        viewHiHz: this.viewHi,
      },
      new Uint32Array(row.data.buffer),
      this.lut,
      this.levels,
    );
    for (let y = 0; y < rh; y++) this.ctx.putImageData(row, 0, y);
  }
}
