<script lang="ts">
  import Panel from '../../components/Panel.svelte';
  import Pill from '../../components/Pill.svelte';
  import { useApp } from '../../lib/state/context';
  import { WaterfallRenderer } from '../../lib/waterfall/renderer';
  import { COLORMAPS, type ColormapName } from '../../lib/waterfall/colormap';
  import type { TuningModel } from '../../lib/protocol/generated';
  import { untrack } from 'svelte';

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

  // One renderer per canvas. The colormap is applied by its own effect below so
  // that changing it does not rebuild the renderer on the same canvas.
  let renderer: WaterfallRenderer | undefined;

  $effect(() => {
    if (!canvas || !wrap) return;
    const current = new WaterfallRenderer(
      canvas,
      untrack(() => colormap),
    );
    renderer = current;
    const target = wrap;
    const resize = (): void => {
      const r = target.getBoundingClientRect();
      width = r.width;
      current.resize(r.width, r.height, window.devicePixelRatio || 1);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(target);
    const off = app.onWaterfall((frame) => {
      current.setView(view.lo, view.hi);
      current.push(frame);
    });
    return () => {
      ro.disconnect();
      off(); // unsubscribes the waterfall channel when this view goes away
      renderer = undefined;
    };
  });

  $effect(() => {
    renderer?.setColormap(colormap);
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
    height: 22px;
    margin: 0 var(--g-space-3); /* same inset as .wrap so ticks line up */
    font-size: 10px;
    color: var(--g-text-muted);
  }
  .axis span {
    position: absolute;
    top: 4px;
    transform: translateX(-50%);
  }
  .wrap {
    position: relative;
    height: clamp(220px, 38vh, 520px);
    margin: 0 var(--g-space-3) var(--g-space-3);
    border-radius: var(--g-radius-m);
    overflow: hidden;
    background: #03040c;
    box-shadow:
      inset 0 0 0 1px var(--g-hairline),
      inset 0 10px 30px rgb(0 0 0 / 0.5);
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
    border-left: 1px solid rgb(103 232 249 / 0.5);
    border-right: 1px solid rgb(167 139 250 / 0.5);
    background: linear-gradient(90deg, rgb(103 232 249 / 0.05), rgb(167 139 250 / 0.05));
    pointer-events: none;
  }
  .stale {
    position: absolute;
    left: 50%;
    bottom: var(--g-space-3);
    transform: translateX(-50%);
    padding: 6px 14px;
    border-radius: var(--g-radius-pill);
    border: 1px solid rgb(252 211 77 / 0.3);
    background: rgb(5 6 12 / 0.7);
    backdrop-filter: blur(8px);
    color: var(--g-warn);
    font-family: var(--g-font-mono);
    font-size: var(--g-text-xs);
    letter-spacing: 0.08em;
    white-space: nowrap;
  }
  .cmap {
    min-height: 30px;
    width: auto;
    border-radius: var(--g-radius-pill);
    font-size: var(--g-text-xs);
  }
</style>
