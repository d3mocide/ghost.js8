<script lang="ts">
  import type { Snippet } from 'svelte';

  let {
    title,
    code,
    id,
    actions,
    children,
    flush = false,
  }: {
    title: string;
    code: string;
    id: string;
    actions?: Snippet;
    children: Snippet;
    flush?: boolean;
  } = $props();
</script>

<section class="panel" aria-labelledby={`${id}-title`} data-testid={`panel-${id}`}>
  <header>
    <span class="mark" aria-hidden="true"></span>
    <h2 id={`${id}-title`}>{title}</h2>
    <span class="code" aria-hidden="true">{code}</span>
    {#if actions}<div class="actions">{@render actions()}</div>{/if}
  </header>
  <div class="body" class:flush>
    {@render children()}
  </div>
</section>

<style>
  .panel {
    position: relative;
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    background:
      linear-gradient(160deg, rgb(255 255 255 / 0.055), rgb(255 255 255 / 0.015) 40%),
      var(--g-glass);
    border: 1px solid var(--g-border);
    border-radius: var(--g-radius-l);
    box-shadow: var(--g-shadow), var(--g-inner-glow);
    backdrop-filter: blur(var(--g-glass-blur)) saturate(var(--g-glass-saturate));
    -webkit-backdrop-filter: blur(var(--g-glass-blur)) saturate(var(--g-glass-saturate));
    overflow: hidden;
    isolation: isolate;
  }
  @supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
    .panel {
      background: var(--g-glass-solid);
    }
  }
  .panel::before {
    /* lit edge: brighter along the top, fading down the sides */
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    padding: 1px;
    background: linear-gradient(180deg, var(--g-edge-hi), transparent 35%);
    mask:
      linear-gradient(#000 0 0) content-box,
      linear-gradient(#000 0 0);
    mask-composite: exclude;
    pointer-events: none;
    z-index: 1;
  }
  header {
    display: flex;
    align-items: center;
    gap: var(--g-space-2);
    padding: var(--g-space-3) var(--g-space-4);
    min-height: 52px;
  }
  .mark {
    width: 4px;
    height: 16px;
    border-radius: 2px;
    background: var(--g-accent);
    box-shadow: 0 0 12px rgb(125 211 252 / 0.55);
    flex: none;
  }
  h2 {
    margin: 0;
    font-family: var(--g-font-ui);
    font-size: var(--g-text-m);
    font-weight: 600;
    letter-spacing: 0.005em;
    color: var(--g-text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .code {
    font-family: var(--g-font-mono);
    font-size: 10px;
    letter-spacing: 0.1em;
    color: var(--g-text-dim);
    flex: none;
  }
  .actions {
    margin-left: auto;
    display: flex;
    gap: var(--g-space-2);
    align-items: center;
  }
  .body {
    padding: 0 var(--g-space-4) var(--g-space-4);
    min-height: 0;
    flex: 1;
    overflow: auto;
  }
  .body.flush {
    padding: 0;
    border-top: 1px solid var(--g-hairline);
  }
</style>
