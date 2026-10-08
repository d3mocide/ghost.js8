<script lang="ts">
  import { useApp } from '../../lib/state/context';
  import { situation } from '../../lib/state/situation';
  import Pill from '../../components/Pill.svelte';

  let { onSwitch }: { onSwitch: () => void } = $props();
  const app = useApp();
  const s = $derived(situation(app.state, app.now));
</script>

<div
  class="situation {s.tone}"
  data-testid="situation"
  data-code={s.code}
  role="status"
  aria-live="polite"
>
  <Pill tone={s.tone} label={s.headline} />
  <p>{s.detail}</p>
  {#if s.suggestSwitch}
    <button type="button" class="btn" onclick={onSwitch}>Switch receiver</button>
  {/if}
</div>

<style>
  .situation {
    display: flex;
    align-items: center;
    gap: var(--g-space-3);
    flex-wrap: wrap;
    padding: var(--g-space-2) var(--g-space-3);
    border: 1px solid var(--g-border);
    border-radius: var(--g-radius-m);
    background: var(--g-glass);
    backdrop-filter: blur(var(--g-glass-blur));
  }
  .situation.alert {
    border-color: rgb(255 77 94 / 0.5);
    box-shadow: 0 0 24px rgb(255 77 94 / 0.12) inset;
  }
  .situation.warn {
    border-color: rgb(255 184 77 / 0.4);
  }
  p {
    margin: 0;
    flex: 1 1 18rem;
    color: var(--g-text-muted);
    font-size: var(--g-text-s);
  }
</style>
