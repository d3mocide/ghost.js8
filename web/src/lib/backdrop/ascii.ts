/**
 * ASCII "signal" backdrop: drifting ionospheric static, radio-wave rings when a
 * station is heard, a soft pulse on every 15-second JS8 slot, and the odd ghost.
 *
 * Purely decorative and framework-free. The pure helpers below are unit-tested;
 * `AsciiBackdrop` owns the canvas and the animation loop.
 */

/** Static density ramp, sparse → dense. Index 0 is "nothing drawn". */
export const RAMP = ' .·:-~=+*';
export const SLOT_MS = 15_000;
const CELL_W = 11;
const CELL_H = 18;
const FPS = 16;
const RING_SPEED = 14; // cells per second
const RING_LIFE_S = 5.5;
const LABEL_LIFE_S = 4.5;
const MAX_RINGS = 8;
const STILL_T = 37; // the fixed moment drawn for reduced motion
const HUE_BUCKETS = 10;
const ALPHA_BUCKETS = 8;

/** A small ghost, drawn in violet, drifting across now and then. */
export const GHOST = [
  '  .-""""-.  ',
  ' /  o  o  \\ ',
  '|    __    |',
  '|          |',
  '|          |',
  ' \\/\\/\\/\\/\\/ ',
];

// ---------------------------------------------------------------- pure helpers

function hash(ix: number, iy: number): number {
  let h = (ix * 374_761_393 + iy * 668_265_263) | 0;
  h = Math.imul(h ^ (h >>> 13), 1_274_126_177);
  return ((h ^ (h >>> 16)) >>> 0) / 4_294_967_295;
}

const fade = (t: number): number => t * t * (3 - 2 * t);

/** Smooth 2D value noise in [0, 1]. */
export function valueNoise(x: number, y: number): number {
  const ix = Math.floor(x);
  const iy = Math.floor(y);
  const fx = fade(x - ix);
  const fy = fade(y - iy);
  const a = hash(ix, iy);
  const b = hash(ix + 1, iy);
  const c = hash(ix, iy + 1);
  const d = hash(ix + 1, iy + 1);
  return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy;
}

/** Two drifting noise layers: slow bands of static that roll like the ionosphere. */
export function staticField(col: number, row: number, t: number): number {
  const n1 = valueNoise(col * 0.055 + t * 0.06, row * 0.11 - t * 0.025);
  const n2 = valueNoise(col * 0.13 - t * 0.09 + 40, row * 0.07 + t * 0.04 + 17);
  const n = n1 * 0.65 + n2 * 0.35;
  const v = (n - 0.5) / 0.32; // most of the field stays empty
  return v <= 0 ? 0 : v >= 1 ? 1 : v * v;
}

/**
 * Ramp character for an intensity in [0, 1]; ' ' means skip. `jitter` in [0, 1)
 * nudges the glyph up or down one step so the static crackles instead of tiling.
 */
export function rampChar(v: number, jitter = 0.5): string {
  if (v <= 0) return ' ';
  const base = Math.floor(v * RAMP.length) + (jitter < 0.2 ? -1 : jitter > 0.8 ? 1 : 0);
  const i = Math.max(0, Math.min(RAMP.length - 1, base));
  return RAMP[i] ?? ' ';
}

/** Per-cell flicker in [0, 1), changing a few times a second. */
export function flicker(col: number, row: number, t: number): number {
  return hash(col * 7 + Math.floor(t * 6), row * 13 - Math.floor(t * 4));
}

/** Gaussian ring profile: 1 on the wavefront, falling off either side, fading with age. */
export function ringIntensity(dist: number, ageS: number): number {
  if (ageS < 0 || ageS > RING_LIFE_S) return 0;
  const r = ageS * RING_SPEED;
  const d = dist - r;
  const life = 1 - ageS / RING_LIFE_S;
  return Math.exp(-(d * d) / 2.2) * life * life;
}

/** Wave glyph by angle so rings read as ((( · ))). */
export function ringChar(dx: number, dy: number): string {
  const ax = Math.abs(dx);
  const ay = Math.abs(dy) * (CELL_H / CELL_W);
  if (ay > ax * 2.2) return '~';
  return dx < 0 ? '(' : ')';
}

/** Milliseconds until the next 15-second JS8 slot boundary (UTC-aligned). */
export function msToNextSlot(nowMs: number): number {
  const r = nowMs % SLOT_MS;
  return r === 0 ? 0 : SLOT_MS - r;
}

// ---------------------------------------------------------------- renderer

interface Ring {
  col: number;
  row: number;
  born: number; // seconds (renderer clock)
  label: string | null;
  strength: number;
}

interface Ghost {
  born: number;
  row: number;
  dir: 1 | -1;
}

export interface BackdropOptions {
  /** Draw one frame and stop (reduced motion). */
  still?: boolean;
  /** Override for tests. */
  random?: () => number;
}

const AQUA: readonly [number, number, number] = [103, 232, 249];
const VIOLET: readonly [number, number, number] = [167, 139, 250];
const MINT: readonly [number, number, number] = [94, 234, 212];

function rgba(c: readonly [number, number, number], a: number): string {
  return `rgba(${String(c[0])},${String(c[1])},${String(c[2])},${a.toFixed(3)})`;
}

/** Precomputed fill styles: [hue bucket][alpha bucket], aqua → violet across the screen. */
function buildStyles(maxAlpha: number): string[][] {
  const out: string[][] = [];
  for (let h = 0; h < HUE_BUCKETS; h++) {
    const f = h / (HUE_BUCKETS - 1);
    const c: [number, number, number] = [
      Math.round(AQUA[0] + (VIOLET[0] - AQUA[0]) * f),
      Math.round(AQUA[1] + (VIOLET[1] - AQUA[1]) * f),
      Math.round(AQUA[2] + (VIOLET[2] - AQUA[2]) * f),
    ];
    const row: string[] = [];
    for (let a = 0; a < ALPHA_BUCKETS; a++) row.push(rgba(c, ((a + 1) / ALPHA_BUCKETS) * maxAlpha));
    out.push(row);
  }
  return out;
}

export class AsciiBackdrop {
  private readonly ctx: CanvasRenderingContext2D;
  private readonly random: () => number;
  private readonly styles = buildStyles(0.32);
  private readonly ringStyles = [0.15, 0.3, 0.45, 0.6].map((a) => rgba(MINT, a));
  private cols = 0;
  private rows = 0;
  private dpr = 1;
  private rings: Ring[] = [];
  private ghost: Ghost | null = null;
  private nextGhostAt = 20;
  private raf = 0;
  private lastFrame = 0;
  private t0 = performance.now();
  private slotTimer: ReturnType<typeof setTimeout> | undefined;
  private running = false;
  private still: boolean;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    opts: BackdropOptions = {},
  ) {
    const ctx = canvas.getContext('2d', { alpha: true });
    if (!ctx) throw new Error('2D canvas unavailable');
    this.ctx = ctx;
    this.random = opts.random ?? Math.random;
    this.still = opts.still ?? false;
  }

  resize(width: number, height: number, dpr: number): void {
    this.dpr = Math.min(2, Math.max(1, dpr));
    this.canvas.width = Math.round(width * this.dpr);
    this.canvas.height = Math.round(height * this.dpr);
    this.cols = Math.ceil(width / CELL_W) + 1;
    this.rows = Math.ceil(height / CELL_H) + 1;
    if (!this.running || this.still) this.draw(this.still ? STILL_T : this.clock());
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    if (this.still) {
      // A pleasant fixed moment, with the ghost part-way across.
      this.ghost = { born: STILL_T - 14, row: Math.max(4, this.rows * 0.62), dir: 1 };
      this.draw(STILL_T);
      return;
    }
    this.scheduleSlot();
    const loop = (ms: number): void => {
      if (!this.running) return;
      this.raf = requestAnimationFrame(loop);
      if (ms - this.lastFrame < 1000 / FPS) return;
      this.lastFrame = ms;
      this.draw(this.clock());
    };
    this.raf = requestAnimationFrame(loop);
  }

  stop(): void {
    this.running = false;
    cancelAnimationFrame(this.raf);
    clearTimeout(this.slotTimer);
  }

  setStill(still: boolean): void {
    if (still === this.still) return;
    this.stop();
    this.still = still;
    this.start();
  }

  /** A station was heard: ripple out from somewhere, with its callsign at the centre. */
  ping(label: string | null, strength = 1): void {
    if (this.still || this.cols === 0) return;
    const margin = 6;
    this.rings.push({
      col: margin + this.random() * Math.max(1, this.cols - 2 * margin),
      row: margin / 2 + this.random() * Math.max(1, this.rows - margin),
      born: this.clock(),
      label,
      strength,
    });
    if (this.rings.length > MAX_RINGS) this.rings.shift();
  }

  private clock(): number {
    return (performance.now() - this.t0) / 1000;
  }

  private scheduleSlot(): void {
    this.slotTimer = setTimeout(
      () => {
        this.ping(null, 0.45);
        this.scheduleSlot();
      },
      msToNextSlot(Date.now()) + 5,
    );
  }

  private draw(t: number): void {
    const { ctx, cols, rows, dpr } = this;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    ctx.font = `13px 'JetBrains Mono', ui-monospace, monospace`;
    ctx.textBaseline = 'top';

    this.rings = this.rings.filter((r) => t - r.born <= Math.max(RING_LIFE_S, LABEL_LIFE_S));
    const ghost = this.updateGhost(t);

    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < cols; col++) {
        let ring = 0;
        let rdx = 0;
        let rdy = 0;
        for (const r of this.rings) {
          const dx = col - r.col;
          const dy = (row - r.row) * (CELL_H / CELL_W);
          const v = ringIntensity(Math.hypot(dx, dy), t - r.born) * r.strength;
          if (v > ring) {
            ring = v;
            rdx = dx;
            rdy = dy;
          }
        }
        const x = col * CELL_W;
        const y = row * CELL_H;
        if (ring > 0.12) {
          const i = Math.min(this.ringStyles.length - 1, Math.floor(ring * this.ringStyles.length));
          ctx.fillStyle = this.ringStyles[i] ?? '';
          ctx.fillText(ringChar(rdx, rdy), x, y);
          continue;
        }
        const v = staticField(col, row, t);
        const ch = rampChar(v, flicker(col, row, t));
        if (ch === ' ') continue;
        const h = Math.min(HUE_BUCKETS - 1, Math.floor((col / cols) * HUE_BUCKETS));
        const a = Math.min(ALPHA_BUCKETS - 1, Math.floor(v * ALPHA_BUCKETS));
        ctx.fillStyle = this.styles[h]?.[a] ?? '';
        ctx.fillText(ch, x, y);
      }
    }

    this.drawLabels(t);
    if (ghost) this.drawGhost(ghost.col, ghost.row);
  }

  private drawLabels(t: number): void {
    const { ctx } = this;
    ctx.font = `600 14px 'JetBrains Mono', ui-monospace, monospace`;
    for (const r of this.rings) {
      if (!r.label) continue;
      const age = t - r.born;
      if (age > LABEL_LIFE_S) continue;
      const a = Math.min(1, age * 3) * (1 - age / LABEL_LIFE_S);
      const text = `· ${r.label} ·`;
      const w = ctx.measureText(text).width;
      ctx.fillStyle = rgba(MINT, 0.55 * a);
      ctx.fillText(text, r.col * CELL_W - w / 2, r.row * CELL_H);
    }
  }

  private updateGhost(t: number): { col: number; row: number } | null {
    if (!this.ghost && t >= this.nextGhostAt && this.rows > 12) {
      this.ghost = {
        born: t,
        row: 4 + this.random() * (this.rows - 12),
        dir: this.random() < 0.5 ? 1 : -1,
      };
    }
    const g = this.ghost;
    if (!g) return null;
    const width = GHOST[0]?.length ?? 12;
    const span = this.cols + width * 2;
    const travelS = Math.max(30, span / 2.2);
    const p = (t - g.born) / travelS;
    if (p >= 1) {
      this.ghost = null;
      this.nextGhostAt = t + 45 + this.random() * 60;
      return null;
    }
    const col = g.dir === 1 ? -width + p * span : this.cols + width - p * span - width;
    return { col, row: g.row + Math.sin((t - g.born) * 1.3) * 0.8 };
  }

  private drawGhost(col: number, row: number): void {
    const { ctx } = this;
    ctx.font = `13px 'JetBrains Mono', ui-monospace, monospace`;
    ctx.fillStyle = rgba(VIOLET, 0.42);
    GHOST.forEach((line, i) => {
      ctx.fillText(line, col * CELL_W, (row + i) * CELL_H);
    });
  }
}
