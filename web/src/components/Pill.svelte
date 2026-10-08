<script lang="ts">
  import type { PillTone } from './pill';
  // Status is always text + icon; colour only reinforces it.
  let { tone, label, title }: { tone: PillTone; label: string; title?: string } = $props();
  const ICON: Record<PillTone, string> = {
    ok: '●',
    info: '◆',
    warn: '▲',
    alert: '■',
    unknown: '○',
  };
</script>

<span class="pill {tone}" {title}>
  <span class="icon" aria-hidden="true">{ICON[tone]}</span>{label}
</span>

<style>
  .pill {
    display: inline-flex;
    align-items: center;
    gap: 0.45em;
    padding: 3px 10px 3px 8px;
    border-radius: 999px;
    border: 1px solid color-mix(in srgb, currentColor 28%, transparent);
    font-family: var(--g-font-mono);
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    white-space: nowrap;
  }
  .icon {
    font-size: 0.75em;
    filter: drop-shadow(0 0 4px currentColor);
  }
  .ok {
    color: var(--g-signal);
    background: var(--g-signal-soft);
  }
  .info {
    color: var(--g-chrome);
    background: var(--g-chrome-soft);
  }
  .warn {
    color: var(--g-warn);
    background: var(--g-warn-soft);
  }
  .alert {
    color: var(--g-alert);
    background: var(--g-alert-soft);
  }
  .unknown {
    color: var(--g-text-muted);
    background: rgb(255 255 255 / 0.04);
  }
</style>
