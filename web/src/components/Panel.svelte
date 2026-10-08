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
    <span class="redact" aria-hidden="true"></span>
    <h2 id={`${id}-title`}><span class="code">{code}</span> {title}</h2>
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
    background: var(--g-glass);
    border: 1px solid var(--g-border);
    border-radius: var(--g-radius-m);
    box-shadow: var(--g-inner-glow);
    backdrop-filter: blur(var(--g-glass-blur)) saturate(var(--g-glass-saturate));
    -webkit-backdrop-filter: blur(var(--g-glass-blur)) saturate(var(--g-glass-saturate));
    overflow: hidden;
  }
  @supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
    .panel {
      background: var(--g-glass-solid);
    }
  }
  .panel::before {
    /* luminous top edge */
    content: '';
    position: absolute;
    inset: 0 0 auto;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgb(92 225 255 / 0.45), transparent);
  }
  header {
    display: flex;
    align-items: center;
    gap: var(--g-space-2);
    padding: var(--g-space-2) var(--g-space-3);
    border-bottom: 1px solid var(--g-border);
    min-height: 40px;
  }
  .redact {
    /* redaction-bar motif */
    width: 22px;
    height: 10px;
    background: repeating-linear-gradient(90deg, var(--g-text) 0 3px, transparent 3px 5px);
    opacity: 0.55;
    border-radius: 1px;
    flex: none;
  }
  h2 {
    margin: 0;
    font-family: var(--g-font-mono);
    font-size: var(--g-text-xs);
    font-weight: 600;
    letter-spacing: var(--g-tracking-caps);
    text-transform: uppercase;
    color: var(--g-text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .code {
    color: var(--g-chrome);
    margin-right: var(--g-space-1);
  }
  .actions {
    margin-left: auto;
    display: flex;
    gap: var(--g-space-2);
    align-items: center;
  }
  .body {
    padding: var(--g-space-3);
    min-height: 0;
    flex: 1;
    overflow: auto;
  }
  .body.flush {
    padding: 0;
  }
</style>
