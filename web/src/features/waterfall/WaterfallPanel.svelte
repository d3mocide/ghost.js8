<script lang="ts">
  import Panel from '../../components/Panel.svelte';
  import Pill from '../../components/Pill.svelte';
  import { useApp } from '../../lib/state/context';
  import { WaterfallRenderer } from '../../lib/waterfall/renderer';
  import { COLORMAPS, type ColormapName } from '../../lib/waterfall/colormap';
  import type { TuningModel } from '../../lib/protocol/generated';

  const app = useApp();
  const STORAGE_KEY = 'ghostjs8.colormap';
  let canvas: HTMLCanvasElement | undefined = $state();
  let wrap: HTMLDivElement | undefined = $state();
  let colormap = $state<ColormapName>(loadColormap());
  let width = $state(0);

  const tuning = $derived<TuningModel>(
    app.state.session?.tuning ?? {
      dial_hz: 14_078_000,
      mode: 'usb',
      low_cut_hz: 100,
      high_cut_hz: 3000,
    },
  );
  // Visible window in audio-offset terms, like JS8Call's waterfall: -500 .. +3500 Hz.
  const OFFSET_LO = -500;
  const OFFSET_HI = 3500;
  const view = $derived(
    tuning.mode === 'usb'
      ? { lo: tuning.dial_hz + OFFSET_LO, hi: tuning.dial_hz + OFFSET_HI }
      : { lo: tuning.dial_hz - OFFSET_HI, hi: tuning.dial_hz - OFFSET_LO },
  );
  const fresh = $derived(
    app.state.lastWaterfallAt !== null && app.now - app.state.lastWaterfallAt < 5000,
  );
  const ticks = [0, 500, 1000, 1500, 2000, 2500, 3000];

  function xForOffset(offset: number): number {
    const frac = (offset - OFFSET_LO) / (OFFSET_HI - OFFSET_LO);
    return (tuning.mode === 'usb' ? frac : 1 - frac) * 100;
  }

  function loadColormap(): ColormapName {
    try {
      const v = localStorage.getItem(STORAGE_KEY);
      if (v && (COLORMAPS as readonly string[]).includes(v)) return v as ColormapName;
    } catch {
      /* storage unavailable: default */
    }
    return 'spectre';
  }

  $effect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, colormap);
    } catch {
      /* ignore */
    }
  });

  $effect(() => {
    if (!canvas || !wrap) return;
    const renderer = new WaterfallRenderer(canvas, colormap);
    const target = wrap;
    const resize = (): void => {
      const r = target.getBoundingClientRect();
      width = r.width;
      renderer.resize(r.width, r.height, window.devicePixelRatio || 1);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(target);
    const off = app.onWaterfall((frame) => {
      renderer.setView(view.lo, view.hi);
      renderer.push(frame);
    });
    return () => {
      ro.disconnect();
      off(); // unsubscribes the waterfall channel when this view goes away
    };
  });
</script>

<Panel id="waterfall" code="W/F" title="Waterfall" flush>
  {#snippet actions()}
    <Pill tone={fresh ? 'ok' : 'warn'} label={fresh ? 'live' : 'stale'} />
    <label class="sr-only" for="colormap">Colormap</label>
    <select id="colormap" class="input cmap" bind:value={colormap}>
      {#each COLORMAPS as c (c)}<option value={c}>{c}</option>{/each}
    </select>
  {/snippet}
  <div class="axis mono" aria-hidden="true">
    {#each ticks as t (t)}
      <span style:left={`${String(xForOffset(t))}%`}>{t}</span>
    {/each}
  </div>
  <div class="wrap" bind:this={wrap}>
    <canvas
      bind:this={canvas}
      data-testid="waterfall-canvas"
      aria-label="Waterfall spectrum, newest at top"
    ></canvas>
    <div
      class="passband"
      style:left={`${String(Math.min(xForOffset(tuning.low_cut_hz), xForOffset(tuning.high_cut_hz)))}%`}
      style:width={`${String(Math.abs(xForOffset(tuning.high_cut_hz) - xForOffset(tuning.low_cut_hz)))}%`}
      aria-hidden="true"
    ></div>
    {#if !fresh}
      <div class="stale" role="status">
        {app.state.session?.state === 'connected'
          ? 'WATERFALL STALE — NO ROWS ARRIVING'
          : 'NO WATERFALL — RECEIVER NOT CONNECTED'}
      </div>
    {/if}
  </div>
  <p class="sr-only">
    Axis shows audio offset in hertz from the dial, {width > 0 ? 'zero to three thousand' : ''}.
  </p>
</Panel>

<style>
  .axis {
    position: relative;
    height: 20px;
    border-bottom: 1px solid var(--g-border);
    font-size: 10px;
    color: var(--g-text-muted);
  }
  .axis span {
    position: absolute;
    top: 3px;
    transform: translateX(-50%);
  }
  .wrap {
    position: relative;
    height: clamp(180px, 32vh, 420px);
    background: #020308;
  }
  canvas {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    image-rendering: pixelated;
  }
  .passband {
    position: absolute;
    top: 0;
    bottom: 0;
    border-left: 1px solid rgb(61 255 154 / 0.55);
    border-right: 1px solid rgb(61 255 154 / 0.55);
    background: rgb(61 255 154 / 0.04);
    pointer-events: none;
  }
  .stale {
    position: absolute;
    inset: auto 0 0;
    padding: var(--g-space-1) var(--g-space-2);
    background: rgb(5 6 10 / 0.75);
    color: var(--g-warn);
    font-family: var(--g-font-mono);
    font-size: var(--g-text-xs);
    letter-spacing: var(--g-tracking-caps);
  }
  .cmap {
    min-height: 28px;
    width: auto;
    font-size: var(--g-text-xs);
  }
</style>
