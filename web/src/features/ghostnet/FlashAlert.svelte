<script lang="ts">
  // Loud, accessible alert for @GSTFLASH traffic (GhostNet emergency flash).
  import { useApp } from '../../lib/state/context';
  import { classify } from '../../lib/ghostnet';
  import { utcTime } from '../../lib/format';
  import { SvelteSet } from 'svelte/reactivity';

  const app = useApp();
  const dismissed = new SvelteSet<string>();
  // Only live traffic alerts (not history replayed on connect).
  const flashes = $derived(
    app.state.decodes.filter(
      (d) => classify(d.text).flash && Date.parse(d.utc) > app.startedAt - 60_000,
    ),
  );
  const current = $derived(flashes.findLast((d) => !dismissed.has(d.key)));

  function dismiss(): void {
    for (const d of flashes) dismissed.add(d.key);
  }
</script>

{#if current}
  <div class="flash" role="alert" data-testid="flash-alert">
    <span class="badge mono" aria-hidden="true">■ FLASH</span>
    <div class="body">
      <strong class="mono">@GSTFLASH {utcTime(current.utc)}Z</strong>
      <span class="mono text">{current.text}</span>
      <span class="hint"
        >Emergency flash traffic. GhostNet guidance: relay to the highest-level HQ within range.</span
      >
    </div>
    <button type="button" class="btn" onclick={dismiss}>Acknowledge</button>
  </div>
{/if}

<style>
  .flash {
    display: flex;
    gap: var(--g-space-3);
    align-items: center;
    flex-wrap: wrap;
    padding: var(--g-space-3) var(--g-space-4);
    border: 1px solid rgb(251 113 133 / 0.6);
    border-radius: var(--g-radius-l);
    background:
      linear-gradient(90deg, rgb(251 113 133 / 0.22), rgb(251 113 133 / 0.06)), var(--g-glass);
    backdrop-filter: blur(var(--g-glass-blur)) saturate(var(--g-glass-saturate));
    -webkit-backdrop-filter: blur(var(--g-glass-blur)) saturate(var(--g-glass-saturate));
    box-shadow: 0 0 40px -8px rgb(251 113 133 / 0.45);
    animation: pulse 1.2s var(--g-ease) 3;
  }
  .badge {
    color: var(--g-alert);
    font-weight: 600;
    letter-spacing: 0.12em;
  }
  .body {
    flex: 1 1 18rem;
    display: grid;
    gap: 2px;
  }
  .text {
    color: var(--g-text);
    overflow-wrap: anywhere;
  }
  .hint {
    color: var(--g-text-muted);
    font-size: var(--g-text-xs);
  }
  @keyframes pulse {
    50% {
      box-shadow: 0 0 56px -4px rgb(251 113 133 / 0.65);
    }
  }
</style>
