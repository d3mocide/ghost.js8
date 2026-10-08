<script lang="ts">
  // Fixed, decorative ASCII field behind the glass. Rings ripple out when a
  // station is decoded; a soft pulse marks each 15-second JS8 slot.
  import { useApp } from '../lib/state/context';
  import { AsciiBackdrop } from '../lib/backdrop/ascii';
  import { backdrop } from '../lib/backdrop/mode.svelte';

  const app = useApp();
  let canvas: HTMLCanvasElement | undefined = $state();
  let engine: AsciiBackdrop | undefined;

  $effect(() => {
    if (!canvas || backdrop.mode !== 'signal') return;
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let fx: AsciiBackdrop;
    try {
      fx = new AsciiBackdrop(canvas, { still: motion.matches });
    } catch {
      return; // no 2D canvas: the gradient alone is fine
    }
    engine = fx;
    const resize = (): void => {
      fx.resize(window.innerWidth, window.innerHeight, window.devicePixelRatio || 1);
    };
    const onMotion = (): void => {
      fx.setStill(motion.matches);
    };
    const onVisibility = (): void => {
      if (document.hidden) fx.stop();
      else fx.start();
    };
    resize();
    fx.start();
    window.addEventListener('resize', resize);
    motion.addEventListener('change', onMotion);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      fx.stop();
      engine = undefined;
      window.removeEventListener('resize', resize);
      motion.removeEventListener('change', onMotion);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  });

  // New decodes ripple out with the sender's callsign (history on connect does not).
  // The decode list is bounded, so track the last key rather than the length.
  let lastKey: string | null | undefined;
  $effect(() => {
    const decodes = app.state.decodes;
    const latest = decodes.at(-1)?.key ?? null;
    if (lastKey === undefined || latest === lastKey) {
      lastKey = latest;
      return;
    }
    const idx = lastKey === null ? -1 : decodes.findIndex((d) => d.key === lastKey);
    const fresh = idx < 0 ? decodes.slice(-1) : decodes.slice(idx + 1).slice(-4);
    lastKey = latest;
    for (const d of fresh) engine?.ping(d.from_call ?? null, d.kind === 'directed' ? 1 : 0.8);
  });
</script>

{#if backdrop.mode === 'signal'}
  <canvas class="backdrop" bind:this={canvas} aria-hidden="true" data-testid="backdrop"></canvas>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    width: 100vw;
    height: 100vh;
    z-index: -1;
    pointer-events: none;
  }
  @media (prefers-reduced-transparency: reduce) {
    .backdrop {
      display: none;
    }
  }
</style>
